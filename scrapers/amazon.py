"""
需求驱动家纺生态系统 · Amazon 爬虫 (OpenCLI 版)

通过 OpenCLI + 已登录 Chromium 提取 Amazon 搜索结果

前置条件：同 tiktok_cli.py — Chromium 运行 + 登录 Amazon
"""
import subprocess, json, time, re
from typing import Optional

from loguru import logger

from .base import BaseScraper, RawPost


class AmazonScraper(BaseScraper):
    """Amazon 购物爬虫 — 通过 OpenCLI 浏览器桥"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "amazon"
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
        except Exception as e:
            logger.warning(f"Session detection failed: {e}")
        return None

    def _opencli(self, *args: str):
        """执行 OpenCLI 命令"""
        cmd = ["opencli", "browser", self.session] + list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return {}
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            return {}
        except Exception as e:
            logger.warning(f"OpenCLI error: {e}")
            return {}

    def _search(self, term: str) -> list[dict]:
        """搜索 Amazon 并提取商品"""
        url = f"https://www.amazon.com/s?k={term.replace(' ', '+')}"
        nav = self._opencli("open", url)
        page_id = nav.get("page", "")
        if not page_id:
            return []
        self._opencli("tab", "select", page_id)
        time.sleep(5)

        # 切换排序为 Best Sellers
        try:
            self._opencli("eval", """(() => {
              const sel = document.getElementById('s-result-sort-select');
              if (!sel) return 'no sort select';
              sel.value = 'exact-aware-popularity-rank';
              sel.dispatchEvent(new Event('change', {bubbles: true}));
              return 'switched to Best Sellers';
            })()""")
            time.sleep(4)
            logger.info("Amazon 排序已切换为 Best Sellers")
        except Exception as e:
            logger.warning(f"Amazon 排序切换失败，使用默认排序: {e}")

        # 提取商品卡片
        raw = self._opencli("eval", """
Array.from(document.querySelectorAll('[data-component-type=s-search-result]')).slice(0,20).map(el => {
  const titleEl = el.querySelector('h2 a, h2 span');
  const pw = el.querySelector('.a-price-whole');
  const pf = el.querySelector('.a-price-fraction');
  const ratingEl = el.querySelector('.a-icon-alt');
  const reviewsLink = el.querySelector('a[href*="customerReviews"]');
  const link = el.querySelector('h2 a');
  const img = el.querySelector('img.s-image');
  const price = pw ? (pw.textContent.replace(/[.,\s]/g,'') + '.' + (pf?.textContent?.trim() || '00')) : '';
  const linkUrl = link?.href || el.querySelector('a')?.href || '';
  const imgSrc = img?.src || '';
  return {
    title: titleEl?.textContent?.trim()?.substring(0,200) || '',
    price: price ? '$' + price : '',
    rating: ratingEl?.textContent?.trim()?.match(/[\d.]+/)?.[0] || '',
    reviews: reviewsLink?.textContent?.trim()?.replace(/[()]/g,'') || '',
    url: linkUrl,
    img: imgSrc,
  };
})
""")
        if isinstance(raw, str):
            try: return json.loads(raw)
            except: return []
        if isinstance(raw, list):
            return raw
        return []

    def fetch(self) -> list[RawPost]:
        if not self.session:
            logger.error("Amazon: No OpenCLI session")
            return []

        all_posts = []
        for term in self.search_terms:
            items = self._search(term)
            for item in items:
                title = item.get("title", "")
                if not title:
                    continue
                price_str = item.get("price", "$0").replace("$", "")
                try:
                    price = float(price_str)
                except:
                    price = 0.0
                rating = float(item.get("rating", 0) or 0)
                reviews = 0
                reviews_raw = item.get("reviews", "0")
                if reviews_raw:
                    reviews_raw = reviews_raw.strip().upper()
                    if "K" in reviews_raw:
                        reviews = int(float(reviews_raw.replace("K", "")) * 1000)
                    elif "M" in reviews_raw:
                        reviews = int(float(reviews_raw.replace("M", "")) * 1000000)
                    else:
                        reviews = int(re.sub(r'[^0-9]', '', reviews_raw) or 0)

                post = RawPost(
                    source="amazon",
                    source_id=f"amz_{hash(item.get('url','') + item.get('title','')) & 0x7FFFFFFF}",
                    title=title[:200],
                    content=f"Price: ${price:.2f} | Rating: {rating}/5 | Reviews: {reviews}",
                    url=item.get("url", ""),
                    image_url=item.get("img", ""),
                    author="Amazon",
                    score=int(reviews),  # 用评论数作排序
                    num_comments=int(rating * 10),  # 评分×10 归一化
                    created_utc=0,
                    tags=[term, "amazon"],
                    metadata={
                        "search_term": term,
                        "price": price,
                        "rating": rating,
                        "reviews": reviews,
                        "platform": "amazon",
                    },
                )
                all_posts.append(post)

            logger.info(f"Amazon '{term}': {len(items)} products")
            time.sleep(1)

        seen = set()
        unique = []
        for p in all_posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"Amazon total: {len(unique)} products")
        return unique

    def close(self):
        pass

    # ---- 以下由 Sonnet 4.6 生成 ---- #

    def fetch_reviews(self, product_url: str, limit: int = 5) -> list[dict]:
        """导航到 Amazon 商品页并提取买家评论"""
        if not product_url:
            return []

        nav = self._opencli("open", product_url)
        page_id = nav.get("page", "")
        if not page_id:
            return []
        self._opencli("tab", "select", page_id)
        time.sleep(4)

        # 尝试点 "See all reviews" 链接
        click_js = """(function() {
  var sel = ['a[data-hook="see-all-reviews-link-foot"]','a[data-hook="see-all-reviews-link"]','#reviews-medley-footer a','a[href*="product-reviews"]'];
  for(var i=0;i<sel.length;i++){var el=document.querySelector(sel[i]);if(el){el.click();return 'clicked';}}
  return 'not-found';
})()"""
        click_r = self._opencli("eval", click_js)
        if isinstance(click_r, str) and "clicked" in click_r:
            time.sleep(4)

        # 展开"Read more"
        self._opencli("eval", """(function(){
  document.querySelectorAll('[data-hook="review-body"] [data-action="reviews:expand-collapse"]').forEach(function(b){try{b.click()}catch(e){}});
})()""")
        time.sleep(1)

        # 提取评论数据
        extract_js = f"""(function() {{
  return Array.from(document.querySelectorAll('[data-hook="review"]')).slice(0,{limit}).map(function(el) {{
    var a=el.querySelector('.a-profile-name'); var author=a?a.textContent.trim():'';
    var s=el.querySelector('i.a-icon-star,i[class*="a-star-"]');
    var rating=''; if(s){{var m=s.className.match(/a-star-([\\d-]+)/); if(m) rating=m[1].replace('-','.');}}
    var t=el.querySelector('[data-hook="review-title"]');
    var title=''; if(t){{var sp=t.querySelectorAll('span'); sp.forEach(function(x){{var xt=x.textContent.trim(); if(xt.length>title.length) title=xt;}});}}
    var b=el.querySelector('[data-hook="review-body"] span'); var text=b?b.textContent.trim():'';
    var d=el.querySelector('[data-hook="review-date"]'); var date=d?d.textContent.trim():'';
    return {{author:author.substring(0,100),rating:rating,title:title.substring(0,300),text:text.substring(0,2000),date:date.substring(0,100)}};
  }});
}})()"""
        raw = self._opencli("eval", extract_js)

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except:
                return []
        if not isinstance(raw, list):
            return []

        reviews = [r for r in raw if r.get("text") or r.get("title")]
        logger.info(f"Amazon reviews: {len(reviews)} from {product_url[:60]}...")
        return reviews

    def fetch_reviews_for_all(self, posts: list, conn) -> int:
        """遍历所有 Amazon 商品，抓评论并存入数据库"""
        from db.database import insert_comment

        inserted = 0
        for post in posts:
            if isinstance(post, dict):
                source = post.get("source", "")
                source_id = post.get("source_id", "")
                url = post.get("url", "")
            else:
                source = getattr(post, "source", "")
                source_id = getattr(post, "source_id", "")
                url = getattr(post, "url", "")

            if source != "amazon" or not url:
                continue

            row = conn.execute("SELECT id FROM raw_posts WHERE source_id=?", (source_id,)).fetchone()
            if not row:
                continue
            db_id = row["id"]

            try:
                reviews = self.fetch_reviews(url, limit=self.config.get("reviews_per_product", 5))
            except Exception as e:
                logger.warning(f"Review fetch failed for {source_id}: {e}")
                continue

            for rev in reviews:
                try:
                    score = int(float(rev.get("rating") or 0) * 10)
                except:
                    score = 0
                ok = insert_comment(conn, {
                    "post_id": db_id,
                    "source": "amazon_review",
                    "author": rev.get("author", ""),
                    "content": f"[{rev.get('title', '')}] {rev.get('text', '')}"[:2000],
                    "score": score,
                    "created_utc": 0,
                })
                if ok:
                    inserted += 1
            logger.info(f"  {source_id}: {len(reviews)} reviews, {inserted} saved")
            time.sleep(2)

        logger.info(f"Amazon reviews total: {inserted} inserted")
        return inserted
