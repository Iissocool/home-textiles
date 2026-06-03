"""
需求驱动家纺生态系统 · SHEIN 爬虫 (OpenCLI 版)

通过 OpenCLI + 已登录 Chromium 提取 SHEIN 搜索结果
"""
import subprocess, json, time, re
from typing import Optional
from loguru import logger
from .base import BaseScraper, RawPost


class SheinScraper(BaseScraper):
    """SHEIN 购物爬虫 — 通过 OpenCLI 浏览器桥"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "shein"
        self.search_terms = config.get("search_terms", [])
        self.limit = min(config.get("limit", 20), 50)
        self.session = config.get("opencli_session", self._detect_session())

    def _detect_session(self) -> Optional[str]:
        try:
            r = subprocess.run(["opencli", "profile", "list"],
                capture_output=True, text=True, timeout=10)
            for line in r.stdout.split("\n"):
                m = re.search(r"(\w+)\s*[—–-]\s*connected", line)
                if m:
                    return m.group(1)
        except: return None

    def _opencli(self, *args: str):
        cmd = ["opencli", "browser", self.session] + list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return {}
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except Exception:
            return {}

    def _search(self, term: str, sort: str = "toprated") -> list[dict]:
        if sort == "toprated":
            url = f"https://us.shein.com/pdsearch/{term.replace(' ', '%20')}/?search_source=1&search_type=all&sort=7&source=sort&sourceStatus=1"
        else:
            url = f"https://us.shein.com/pdsearch/{term.replace(' ', '%20')}/?search_source=1&search_type=all"
        nav = self._opencli("open", url)
        page_id = nav.get("page", "")
        if not page_id:
            return []
        self._opencli("tab", "select", page_id)
        time.sleep(5)

        # 检测人机验证页面
        check = self._opencli("eval", """document.title.toLowerCase()""")
        if isinstance(check, str) and any(k in check for k in ("captcha", "verify", "robot", "human", "challenge", "security")):
            logger.warning(f"SHEIN 人机验证触发，等待 15 秒后重试...")
            time.sleep(15)
            self._opencli("open", url)
            time.sleep(5)
            check2 = self._opencli("eval", """document.title.toLowerCase()""")
            if isinstance(check2, str) and any(k in check2 for k in ("captcha", "verify", "robot")):
                logger.error("SHEIN 人机验证无法绕过，跳过该关键词")
                return []

        # 从 JSON-LD 结构化数据提取（含价格） — 翻页直到够数据
        all_items = []
        max_pages = 3  # 最多翻 3 页
        for page in range(1, max_pages + 1):
            if page > 1:
                page_url = f"https://us.shein.com/pdsearch/{term.replace(' ', '%20')}/?search_source=1&search_type=all&sort=7&source=sort&sourceStatus=1&page={page}"
                self._opencli("open", page_url)
                time.sleep(4)

            raw = self._opencli("eval", """
(function() {
var ss = document.querySelectorAll("script");
for(var i = 0; i < ss.length; i++) {
  var txt = ss[i].textContent || "";
  if(txt.indexOf("ItemList") !== -1) {
    try {
      var parsed = JSON.parse(txt);
      var entries = parsed["@graph"] ? parsed["@graph"][0].itemListElement : [];
      var out = [];
      for(var j = 0; j < entries.length; j++) {
        var item = entries[j].item || entries[j];
        var rating = item.aggregateRating || {};
        out.push({
          title: (item.name || "").substring(0,200),
          price: item.offers && item.offers.price ? "$" + item.offers.price : "",
          url: item.url || "",
          image: item.image || "",
          reviews: rating.reviewCount || 0,
          rating: rating.ratingValue || ""
        });
      }
      return JSON.stringify(out);
    } catch(e) {}
    break;
  }
}
return "[]";
})()
""")
            if isinstance(raw, str):
                try: all_items.extend(json.loads(raw))
                except: pass
            elif isinstance(raw, list):
                all_items.extend(raw)

            if len(all_items) >= self.limit:
                break

        logger.info(f"SHEIN '{term}': {len(all_items)} products across {page} pages")
        return all_items[:self.limit]

    def fetch(self) -> list[RawPost]:
        if not self.session:
            logger.error("SHEIN: No OpenCLI session")
            return []
        all_posts = []
        for term in self.search_terms:
            items = self._search(term)
            for item in items:
                title = item.get("title", "")
                if not title:
                    continue
                price_str = item.get("price", "$0").replace("$", "").strip()
                try:
                    price = float(price_str)
                except:
                    price = 0.0
                # 修复 SHEIN 图片 URL：去掉 OpenCLI 产生的多余域名，补全协议
                raw_img = item.get("image", "") or ""
                if raw_img.startswith("https://us.shein.com/"):
                    img_url = raw_img.replace("us.shein.com/", "").replace("https:///", "https://")
                elif raw_img.startswith("//"):
                    img_url = "https:" + raw_img
                else:
                    img_url = raw_img
                post = RawPost(
                    source="shein",
                    source_id=f"shen_{hash(item.get('url','') + title) & 0x7FFFFFFF}",
                    title=title[:200],
                    content=f"Price: ${price:.2f}",
                    url=item.get("url", ""),
                    image_url=img_url,
                    author="SHEIN",
                    score=int(price),
                    tags=[term, "shein"],
                    metadata={"search_term": term, "price": price, "platform": "shein",
                              "reviews": item.get("reviews", 0), "rating": item.get("rating", "")},
                )
                all_posts.append(post)
            logger.info(f"SHEIN '{term}': {len(items)} products")
            time.sleep(1)
        seen = set()
        unique = []
        for p in all_posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)
        logger.info(f"SHEIN total: {len(unique)} products")
        return unique

    def close(self):
        pass

    # ---- SHEIN 评论提取 ---- #

    def fetch_reviews(self, product_url: str, limit: int = 5) -> list[dict]:
        """通过 JSON-LD 提取 SHEIN 商品评论"""
        if not product_url or not self.session:
            return []

        nav = self._opencli("open", product_url)
        page_id = nav.get("page", "")
        if not page_id:
            return []
        self._opencli("tab", "select", page_id)
        time.sleep(5)

        raw = self._opencli("eval", f"""
(function() {{
  var scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for(var i=0;i<scripts.length;i++) {{
    var txt = scripts[i].textContent || "";
    if(txt.indexOf('"review"') === -1) continue;
    try {{
      var data = JSON.parse(txt);
      var items = data["@graph"] || [data];
      for(var c=0;c<items.length;c++) {{
        var reviews = items[c].review || items[c].reviews;
        if(!reviews || !Array.isArray(reviews)) continue;
        var out = [];
        for(var j=0;j<reviews.length && out.length<{limit};j++) {{
          var r = reviews[j];
          out.push({{
            author: (r.author&&r.author.name) ? r.author.name : "Anonymous",
            rating: (r.reviewRating&&r.reviewRating.ratingValue) ? String(r.reviewRating.ratingValue) : "",
            title: r.name || "",
            body: r.reviewBody || "",
            date: r.datePublished || ""
          }});
        }}
        if(out.length>0) return JSON.stringify(out);
      }}
    }} catch(e) {{}}
  }}
  return "[]";
}})()
""")
        if isinstance(raw, str):
            try: return json.loads(raw)
            except: return []
        if isinstance(raw, list):
            return raw
        return []

    def fetch_reviews_for_all(self, posts: list, conn) -> int:
        """遍历所有 SHEIN 商品，抓评论并存入数据库"""
        from db.database import insert_comment
        inserted = 0
        for post in posts:
            if isinstance(post, dict):
                url = post.get("url", "")
                source_id = post.get("source_id", "")
            else:
                url = getattr(post, "url", "")
                source_id = getattr(post, "source_id", "")
            if not url:
                continue

            row = conn.execute("SELECT id FROM raw_posts WHERE source_id=?", (source_id,)).fetchone()
            if not row:
                continue
            db_id = row["id"]

            try:
                reviews = self.fetch_reviews(url, limit=self.config.get("reviews_per_product", 5))
            except Exception as e:
                logger.warning(f"SHEIN review failed for {source_id}: {e}")
                continue

            for rev in reviews:
                try:
                    score = int(float(rev.get("rating") or 0) * 10)
                except:
                    score = 0
                ok = insert_comment(conn, {
                    "post_id": db_id,
                    "source": "shein_review",
                    "author": rev.get("author", ""),
                    "content": f"[{rev.get('title', '')}] {rev.get('body', '')}"[:2000],
                    "score": score,
                    "created_utc": 0,
                })
                if ok:
                    inserted += 1
            logger.info(f"SHEIN {source_id}: {len(reviews)} reviews")
            time.sleep(2)

        logger.info(f"SHEIN reviews total: {inserted}")
        return inserted
