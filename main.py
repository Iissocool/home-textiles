"""
需求驱动家纺 · CLI 交互入口

用法:
  python main.py --keyword "cooling sheets" --sources amazon,shein --limit 10 --sort likes
  python main.py --keyword "bamboo bedding" --sort comments
  python main.py --keyword "linen" --sources reddit,twitter,tiktok --limit 30
"""
import argparse, sys, os, time, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db.database import init_db, get_conn, insert_raw_post
from loguru import logger


def load_config() -> dict:
    import yaml
    with open(Path(__file__).resolve().parent / "config" / "config.yaml") as f:
        return yaml.safe_load(f)


def get_scraper(source: str, config: dict, batch_id: str, keyword: str, limit: int, sort: str):
    """创建爬虫实例，注入 batch_id 和 over-fetch 倍数"""
    fetch_limit = limit * 3  # over-fetch: 抓 3 倍，最终裁到 limit

    if source == "reddit":
        from scrapers.reddit import RedditScraper
        s = RedditScraper({**config.get("reddit", {}), "subreddits": ["HomeDecorating", "Bedding", "Sleep", "Mattress"], "limit": fetch_limit})
    elif source == "twitter":
        from scrapers.twitter import TwitterScraper
        s = TwitterScraper({"search_queries": [keyword], "limit": fetch_limit})
    elif source == "tiktok":
        from scrapers.tiktok_cli import TikTokCLIScraper
        s = TikTokCLIScraper({"hashtags": [keyword.replace(" ", "")], "limit": fetch_limit // 3})
    elif source == "amazon":
        from scrapers.amazon import AmazonScraper
        s = AmazonScraper({"search_terms": [keyword], "limit": fetch_limit})
    elif source == "shein":
        from scrapers.shein import SheinScraper
        s = SheinScraper({"search_terms": [keyword], "limit": fetch_limit})
    else:
        raise ValueError(f"Unknown source: {source}")

    return s


SOCIAL_SOURCES = {"reddit", "twitter", "tiktok"}
ECOM_SOURCES = {"amazon", "shein"}


def trim_and_save(posts: list, sort: str, limit: int, batch_id: str, keyword: str, conn) -> tuple:
    """Over-fetch trim: 分社媒/电商两路排序后裁切入库"""
    if not posts:
        return (0, 0)

    social = [p for p in posts if p.source in SOCIAL_SOURCES]
    ecom = [p for p in posts if p.source in ECOM_SOURCES]

    # 社媒排序：用 CLI 指定的指标
    if sort == "comments":
        social.sort(key=lambda x: x.num_comments, reverse=True)
    else:
        social.sort(key=lambda x: x.score, reverse=True)

    # 电商排序：始终按评论数（销量信号），与 CLI sort 无关
    ecom.sort(key=lambda x: x.metadata.get("reviews", 0), reverse=True)

    saved_social = _save_batch(social[:limit], batch_id, keyword, conn)
    saved_ecom = _save_batch(ecom[:limit], batch_id, keyword, conn)

    return (saved_social, saved_ecom)


def _save_batch(posts: list, batch_id: str, keyword: str, conn) -> int:
    """批量写入同组帖子"""
    saved = 0
    for p in posts:
        p.batch_id = batch_id
        p.search_keyword = keyword
        conn.execute("DELETE FROM raw_posts WHERE source=? AND source_id=?", (p.source, p.source_id))
        if insert_raw_post(conn, p.to_dict()):
            saved += 1
    return saved


def main():
    parser = argparse.ArgumentParser(description="🌐 跨境产品情报 · 按需研究工具")
    parser.add_argument("--keyword", required=True, help="搜索关键词 (e.g. 'cooling sheets')")
    parser.add_argument("--sources", default="reddit,twitter,tiktok,amazon,shein", help="数据源，逗号分隔")
    parser.add_argument("--limit", type=int, default=15, help="最终保留条数/源")
    parser.add_argument("--sort", choices=["likes", "comments"], default="likes", help="排序方式")
    parser.add_argument("--no-llm", action="store_true", help="跳过 LLM 分析")
    args = parser.parse_args()

    batch_id = datetime.now().strftime(f"%Y%m%d_%H%M%S_{args.keyword.replace(' ', '_')}")
    keyword = args.keyword
    sources = [s.strip() for s in args.sources.split(",")]

    print(f"\n🌐 跨境产品情报 · 按需研究")
    print(f"{'='*50}")
    print(f"  关键词: {keyword}")
    print(f"  数据源: {', '.join(sources)}")
    print(f"  排序:   {args.sort}")
    print(f"  每源限: {args.limit} 条 (over-fetch {args.limit*3})")
    print(f"  批次:   {batch_id}")
    print(f"{'='*50}\n")

    init_db()
    conn = get_conn()
    config = load_config()
    total = 0

    for src in sources:
        print(f"📡 抓取 {src}...", end=" ", flush=True)
        try:
            scraper = get_scraper(src, config, batch_id, keyword, args.limit, args.sort)
            posts = scraper.fetch()
            scraper.close()
            if not posts:
                print(f"📭 0 条（该关键词无匹配结果）")
            else:
                saved = trim_and_save(posts, args.sort, args.limit, batch_id, keyword, conn)
                total += sum(saved)
                print(f"✅ {len(posts)} 条 ({saved[0]} 社媒 + {saved[1]} 电商)")
        except Exception as e:
            print(f"❌ 失败: {e}")

        time.sleep(0.5)

    conn.close()
    print(f"\n✅ 共 {total} 条写入数据库 (batch_id={batch_id})")

    # 输出后续命令
    print(f"\n📋 后续操作:")
    print(f"  LLM 分析:  node router/src/router.js --batch {batch_id}")
    print(f"  刷新看板:  python scripts/generate_dashboard.py --batch {batch_id}")
    print()


if __name__ == "__main__":
    main()
