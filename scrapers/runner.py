"""
需求驱动家纺生态系统 · 统一抓取入口

用法:
  python -m scrapers.runner          # 抓取所有已启用的源
  python -m scrapers.runner --sources reddit,pinterest   # 只抓指定源
"""
import sys, time, json, argparse
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db, get_conn
from loguru import logger


def load_config() -> dict:
    import yaml
    config_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_source(source: str, cfg: dict) -> int:
    """运行单个数据源，返回写入条数"""
    from db.database import insert_raw_post

    if source == "reddit":
        from scrapers.reddit import RedditScraper
        scraper = RedditScraper(cfg.get("reddit", {}))
    elif source == "pinterest":
        from scrapers.pinterest import PinterestScraper
        scraper = PinterestScraper(cfg.get("pinterest", {}))
    elif source == "twitter":
        from scrapers.twitter import TwitterScraper
        scraper = TwitterScraper(cfg.get("twitter", {}))
    elif source == "tiktok":
        from scrapers.tiktok_cli import TikTokCLIScraper
        scraper = TikTokCLIScraper(cfg.get("tiktok", {}))
    elif source == "amazon":
        from scrapers.amazon import AmazonScraper
        scraper = AmazonScraper(cfg.get("amazon", {}))
    else:
        logger.error(f"Unknown source: {source}")
        return 0

    logger.info(f"Starting {source} scraper...")
    posts = scraper.fetch()
    scraper.close()

    conn = get_conn()
    saved = 0
    for p in posts:
        if insert_raw_post(conn, p.to_dict()):
            saved += 1
    conn.close()

    logger.info(f"{source}: {saved} posts saved")
    return saved


def main():
    parser = argparse.ArgumentParser(description="Home Textiles Scraper Runner")
    parser.add_argument("--sources", help="Comma-separated list of sources to run")
    args = parser.parse_args()

    config = load_config()
    init_db()

    if args.sources:
        sources = [s.strip() for s in args.sources.split(",")]
    else:
        sources = [s for s, c in config.get("sources", {}).items() if c.get("enabled", True)]

    total = 0
    for src in sources:
        src_cfg = config.get("sources", {}).get(src, {})
        if not src_cfg.get("enabled", True):
            logger.info(f"Skipping {src} (disabled)")
            continue
        n = run_source(src, config.get("sources", {}))
        total += n
        time.sleep(1)

    logger.info(f"All done. Total posts saved: {total}")


if __name__ == "__main__":
    main()
