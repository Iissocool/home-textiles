"""
快速测试：初始化 DB + 运行 Reddit scraper
"""
import sys, json
sys.path.insert(0, "/home/weng/projects/home-textiles")

from db.database import init_db, get_conn
from scrapers.reddit import RedditScraper

# 1. 初始化数据库
init_db()

# 2. 运行 Reddit 爬虫
config = {
    "subreddits": ["HomeDecorating", "Bedding", "Sleep"],
    "sort": "hot",
    "time_filter": "week",
    "limit": 10,
}
scraper = RedditScraper(config)
posts = scraper.fetch()
scraper.close()

print(f"\n=== Reddit 抓取结果: {len(posts)} 条帖子 ===\n")

# 3. 写入数据库
conn = get_conn()
saved = 0
for p in posts:
    from db.database import insert_raw_post
    if insert_raw_post(conn, p.to_dict()):
        saved += 1

print(f"写入数据库: {saved} 条\n")

# 4. 展示前 5 条
print(f"{'标题':<60} {'分数':<6} {'评论':<5} 来源")
print("-" * 90)
for p in posts[:5]:
    title = p.title[:55] + ".." if len(p.title) > 55 else p.title
    print(f"{title:<60} {p.score:<6} {p.num_comments:<5} r/{p.tags[0] if p.tags else '?'}")

# 5. 检查 DB
row_count = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
total = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls").fetchone()[0]
print(f"\n数据库总记录: {row_count}")
print(f"LLM 总花费: ${total:.4f}")
conn.close()
