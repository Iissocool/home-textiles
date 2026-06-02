"""测试 SHEIN 商品数据抓取"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.shein import SheinScraper
from db.database import get_conn, insert_raw_post

print("=" * 50)
print("Test SHEIN Scraper")
print("=" * 50)

config = {"search_terms": ["bedding", "sheets", "duvet cover"], "limit": 10}
scraper = SheinScraper(config)
posts = scraper.fetch()
scraper.close()

print(f"\n结果: {len(posts)} products\n")
for p in posts[:6]:
    price = p.metadata.get("price", 0)
    print(f"  {p.title[:55]}")
    print(f"    ${price:.2f}  {p.url}")
    print()

if posts:
    conn = get_conn()
    saved = sum(1 for p in posts if insert_raw_post(conn, p.to_dict()))
    conn.close()
    print(f"写入数据库: {saved} 条")
print("Done")
