"""
跨境产品 · Amazon 爬虫 (OpenCLI 版)

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

        # 提取商品卡片（用 %s 占位符传 limit，避免 f-string 与 JS {} 冲突）
        js = """
Array.from(document.querySelectorAll('[data-component-type=s-search-result]')).slice(0,%s).map(el => {
  const titleEl = el.querySelector('h2 a, h2 span');
  const pw = el.querySelector('.a-price-whole');
  const pf = el.querySelector('.a-price-fraction');
  const ratingEl = el.querySelector('.a-icon-alt');
  const reviewsLink = el.querySelector('a[href*="customerReviews"]');
  const link = el.querySelector('h2 a');
  const img = el.querySelector('img.s-image');
  const price = pw ? (pw.textContent.replace(/[.,\\s]/g,'') + '.' + (pf?.textContent?.trim() || '00')) : '';
  const linkUrl = link?.href || el.querySelector('a')?.href || '';
  const imgSrc = img?.src || '';
  return {
    title: titleEl?.textContent?.trim()?.substring(0,200) || '',
    price: price ? '$' + price : '',
    rating: ratingEl?.textContent?.trim()?.match(/[\\d.]+/)?.[0] || '',
    reviews: reviewsLink?.textContent?.trim()?.replace(/[()]/g,'') || '',
    url: linkUrl,
    img: imgSrc,
  };
})
""" % self.limit
        raw = self._opencli("eval", js)
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
                price_str = item.get("price", "$0").replace("$", "").strip()
                try:
                    price = float(price_str)
                except:
                    price = 0.0
                reviews_str = item.get("reviews", "0").replace(",", "")
                try:
                    reviews_count = int(reviews_str)
                except:
                    reviews_count = 0
                post = RawPost(
                    source="amazon",
                    source_id=f"amz_{hash(item.get('url','') + title) & 0x7FFFFFFF}",
                    title=title[:200],
                    content=f"Price: ${price:.2f}",
                    url=item.get("url", ""),
                    image_url=item.get("img", ""),
                    author="Amazon",
                    score=reviews_count,
                    num_comments=0,
                    tags=[term, "amazon"],
                    metadata={
                        "search_term": term,
                        "price": price,
                        "rating": item.get("rating", 0),
                        "reviews": reviews_count,
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

    def fetch_reviews(self, product_url: str, limit: int = 5) -> list[dict]:
        """提取 Amazon 商品评论"""
        if not product_url or not self.session:
            return []
        nav = self._opencli("open", product_url)
        page_id = nav.get("page", "")
        if not page_id:
            return []
        self._opencli("tab", "select", page_id)
        time.sleep(4)
        extract_js = f"""(function() {{
  return Array.from(document.querySelectorAll('[data-hook="review"]')).slice(0,{limit}).map(function(el) {{
    var a=el.querySelector('.a-profile-name'); var author=a?a.textContent.trim():'';
    var s=el.querySelector('i.a-icon-star,i[class*="a-star-"]');
    var rating=''; if(s){{var m=s.className.match(/a-star-([\\d-]+)/); if(m) rating=m[1].replace('-','.');}}
    var t=el.querySelector('[data-hook="review-title"]'); var title=t?t.textContent.trim():'';
    var b=el.querySelector('[data-hook="review-body"]'); var body=b?b.textContent.trim().substring(0,500):'';
    return {{author:author, rating:rating, title:title, content:body}};
  }});
}})()"""
        raw = self._opencli("eval", extract_js)
        if isinstance(raw, list):
            return raw[:limit]
        return []

    def close(self):
        pass
