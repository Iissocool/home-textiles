"""
快速验证脚本：scraper → DB → router 全链路

用法：
  python scripts/verify_pipeline.py
"""
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db, get_conn
from scrapers.reddit import RedditScraper

print("=" * 60)
print("Home Textiles Pipeline 验证")
print("=" * 60)

# 1. 初始化 DB
print("\n[1/4] 初始化数据库...")
init_db()
print("  ✅ DB ready")

# 2. 运行 Reddit 爬虫
print("\n[2/4] 运行 Reddit 爬虫...")
config = {
    "subreddits": ["HomeDecorating", "Bedding", "Sleep", "Mattress", "InteriorDesign"],
    "sort": "top",
    "limit": 30,
}
scraper = RedditScraper(config)
posts = scraper.fetch()
scraper.close()
print(f"  ✅ {len(posts)} posts fetched")

# 3. 写入 DB
print("\n[3/4] 写入数据库...")
conn = get_conn()
saved = 0
from db.database import insert_raw_post
for p in posts:
    if insert_raw_post(conn, p.to_dict()):
        saved += 1
print(f"  ✅ {saved} posts saved")

# 4. 统计
print("\n[4/4] 数据统计:")
row_count = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
source_count = conn.execute(
    "SELECT source, COUNT(*) as cnt FROM raw_posts GROUP BY source"
).fetchall()

print(f"  总记录: {row_count}")
for row in source_count:
    print(f"  {row['source']}: {row['cnt']}")

# 按 subreddit 分布
from collections import Counter
tag_counter = Counter()
for p in posts:
    for t in p.tags:
        tag_counter[t] += 1
print("\n  按 subreddit 分布:")
for tag, cnt in tag_counter.most_common():
    print(f"    r/{tag}: {cnt}")

# 活跃度最高的 5 条
print("\n  最活跃帖子 TOP 5:")
top = conn.execute(
    "SELECT title, source, score, num_comments FROM raw_posts ORDER BY score DESC LIMIT 5"
).fetchall()
for i, row in enumerate(top, 1):
    t = row['title'][:50] + ".." if len(row['title']) > 50 else row['title']
    print(f"  {i}. [{row['source']}] {t} (score:{row['score']}, comments:{row['num_comments']})")

conn.close()
print("\n" + "=" * 60)
print(f"✅ 验证完成！{saved} 条 Reddit 帖子已存入数据库")
print(f"   接下来运行: node router/src/router.js --dry-run")
print("=" * 60)
