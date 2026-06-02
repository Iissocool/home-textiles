"""测试 Amazon 商品数据抓取"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.amazon import AmazonScraper
from db.database import get_conn, insert_raw_post

print("=" * 50)
print("Test Amazon Scraper")
print("=" * 50)

config = {
    "search_terms": ["cooling sheets", "bamboo bedding", "linen duvet cover"],
    "limit": 10,
}

scraper = AmazonScraper(config)
posts = scraper.fetch()
scraper.close()

print(f"\n结果: {len(posts)} products\n")
for p in posts[:6]:
    price = p.metadata.get("price", 0)
    rating = p.metadata.get("rating", 0)
    reviews = p.metadata.get("reviews", 0)
    print(f"  {p.title[:55]}")
    print(f"    ${price:.2f}  ⭐{rating}  💬{reviews}")
    print(f"    {p.url}")
    print()

# 写入 DB
if posts:
    conn = get_conn()
    saved = 0
    for p in posts:
        if insert_raw_post(conn, p.to_dict()):
            saved += 1
    conn.close()
    print(f"写入数据库: {saved} 条")

print("=" * 50)
print("Done")
