"""验证 TikTok Playwright 爬虫"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.tiktok import TikTokScraper

print("=" * 50)
print("Test TikTok Scraper (Playwright)")
print("=" * 50)

config = {
    "hashtags": ["bedding", "hometextiles"],
    "limit": 5,
}

scraper = TikTokScraper(config)
posts = scraper.fetch()
scraper.close()

print(f"\n结果: {len(posts)} videos")
for p in posts[:3]:
    print(f"  [{p.source_id}]")
    print(f"  Title: {p.title[:60] if p.title else '(no title)'}")
    print(f"  Author: {p.author}")
    print(f"  Score: {p.score}")
    print(f"  URL: {p.url}")
    print()

print("=" * 50)
print("Done")
