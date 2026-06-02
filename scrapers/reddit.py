"""
需求驱动家纺生态系统 · Reddit 爬虫

数据源：PullPush API（免费、无认证、归档数据）
"""
import time
from urllib.parse import urlencode

import httpx
from loguru import logger

from .base import BaseScraper, RawPost

PULLPUSH_SEARCH = "https://api.pullpush.io/reddit/search/submission/"
PULLPUSH_COMMENTS = "https://api.pullpush.io/reddit/search/comment/"


class RedditScraper(BaseScraper):
    """Reddit 通过 PullPush 免费 API"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "reddit"
        self.subreddits = config.get("subreddits", ["HomeDecorating", "Bedding"])
        self.sort = config.get("sort", "top")
        self.time_filter = config.get("time_filter", "week")
        self.limit = min(config.get("limit", 50), 100)
        self._client = httpx.Client(
            timeout=30,
            headers={
                "User-Agent": "HomeTextilesTrendBot/1.0 (academic research)",
                "Accept": "application/json",
            },
        )

    def _fetch_sub(self, sub: str) -> list[RawPost]:
        """抓取单个 subreddit 的帖子"""
        params = {
            "subreddit": sub,
            "size": self.limit,
            "sort_type": "score",
            "order": "desc",
        }
        try:
            resp = self._client.get(PULLPUSH_SEARCH, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"PullPush r/{sub} error: {e}")
            return []

        items = data.get("data", [])
        posts = []
        for item in items:
            post = RawPost(
                source="reddit",
                source_id=f"t3_{item.get('id', '')}",
                title=item.get("title", ""),
                content=(item.get("selftext", "") or "")[:2000],
                url=f"https://www.reddit.com{item.get('permalink', '')}",
                author=item.get("author", "[deleted]"),
                score=item.get("score", 0),
                num_comments=item.get("num_comments", 0),
                created_utc=item.get("created_utc", 0),
                tags=[sub],
                metadata={
                    "subreddit": sub,
                    "upvote_ratio": item.get("upvote_ratio", 0),
                    "domain": item.get("domain", ""),
                    "is_self": item.get("is_self", True),
                },
            )
            posts.append(post)

        logger.info(f"r/{sub}: {len(posts)} posts")
        return posts

    def fetch(self) -> list[RawPost]:
        """抓取所有 subreddit"""
        all_posts = []
        for sub in self.subreddits:
            posts = self._fetch_sub(sub)
            all_posts.extend(posts)
            time.sleep(0.3)

        # 去重
        seen = set()
        unique = []
        for p in all_posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"Reddit total: {len(unique)} unique posts")
        return unique

    def fetch_comments(self, source_id: str, limit: int = 10) -> list[dict]:
        """抓取某条 Reddit 帖子的评论（PullPush API）"""
        # source_id 格式: t3_xxxxx → 只需要 xxxxx
        post_id = source_id.replace("t3_", "")
        try:
            resp = self._client.get(
                PULLPUSH_COMMENTS,
                params={"link_id": post_id, "size": limit, "sort_type": "score", "order": "desc"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Comments for {source_id} failed: {e}")
            return []

        comments = []
        for item in data.get("data", []):
            comments.append({
                "author": item.get("author", "[deleted]"),
                "content": (item.get("body", "") or "")[:1000],
                "score": item.get("score", 0),
                "created_utc": item.get("created_utc", 0),
            })
        return comments

    def close(self):
        self._client.close()
