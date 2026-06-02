"""
验证 X (Twitter) 和 TikTok 爬虫是否能实际获取数据
无 API Key 模式
"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# =========================================
# Test 1: X/Twitter via Nitter
# =========================================
print("=" * 60)
print("Test 1: X/Twitter via Nitter RSS")
print("=" * 60)

from scrapers.twitter import TwitterScraper

config = {
    "search_queries": ["cooling sheets", "bamboo bedding", "linen sheets"],
    "limit": 5,
}
scraper = TwitterScraper(config)
posts = scraper._fetch_nitter()
scraper.close()

print(f"  结果: {len(posts)} tweets")
for p in posts[:3]:
    print(f"  [{p.source}] {p.title[:60] if p.title else '(no title)'}")
    print(f"    {p.url}")
print()

# =========================================
# Test 2: TikTok via Scrapling
# =========================================
print("=" * 60)
print("Test 2: TikTok via Scrapling StealthyFetcher")
print("=" * 60)

from scrapers.tiktok import TikTokScraper

config = {
    "hashtags": ["bedding", "hometextiles"],
    "limit": 3,
}
tiktok = TikTokScraper(config)
posts = tiktok._try_browser_api("bedding")
tiktok.close()

print(f"  方法1 (Scrapling SIGI_STATE): {len(posts)} videos")
for p in posts[:2]:
    print(f"  [{p.source}] {p.title[:60]}")
    print(f"    {p.url}")

# 也试 httpx fallback
tiktok2 = TikTokScraper(config)
posts2 = tiktok2._try_web_scrape("bedding")
tiktok2.close()

print(f"\n  方法2 (httpx SIGI_STATE): {len(posts2)} videos")
for p in posts2[:2]:
    print(f"  [{p.source}] {p.title[:60]}")
    print(f"    {p.url}")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
