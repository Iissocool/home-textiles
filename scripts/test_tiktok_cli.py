"""测试 OpenCLI 版 TikTok 爬虫"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.tiktok_cli import TikTokCLIScraper
from db.database import get_conn, insert_raw_post

print("=" * 50)
print("Test TikTok via OpenCLI")
print("=" * 50)

config = {
    "hashtags": ["bedding", "hometextiles", "coolingsheets"],
    "limit": 5,
}

scraper = TikTokCLIScraper(config)
posts = scraper.fetch()
scraper.close()

print(f"\n结果: {len(posts)} videos")
for p in posts[:5]:
    print(f"  @{p.author}")
    print(f"  {p.title[:60]}...")
    print(f"  tags: {p.tags}")
    print()

# 写入数据库
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
