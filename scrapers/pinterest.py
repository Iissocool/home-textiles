"""
需求驱动家纺生态系统 · Pinterest 爬虫

数据源：Pinterest 官方 API v5（免费，需注册 App）

接入步骤：
  1. 访问 https://developers.pinterest.com/apps/
  2. 创建 APP → 获取 Access Token
  3. 设置环境变量：export PINTEREST_TOKEN="your_token"

或者放在 .env 文件中：
  PINTEREST_TOKEN=your_token

API 免费额度：每天 200 次请求，足够每周抓一次
"""
import os
import time
from typing import Optional

import httpx
from loguru import logger

from .base import BaseScraper, RawPost

PINTEREST_API = "https://api.pinterest.com/v5"


class PinterestScraper(BaseScraper):
    """Pinterest 官方 API 爬虫"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "pinterest"
        self.search_terms = config.get("search_terms", [])
        self.limit = min(config.get("limit", 50), 100)
        self.token = os.environ.get("PINTEREST_TOKEN", "")
        self._client = httpx.Client(
            timeout=20,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            } if self.token else {},
        )

    def fetch(self) -> list[RawPost]:
        if not self.token:
            logger.warning("PINTEREST_TOKEN not set. "
                          "Set it via env or .env file. "
                          "See: https://developers.pinterest.com/apps/")
            return []

        all_posts = []
        for term in self.search_terms:
            posts = self._search(term)
            all_posts.extend(posts)
            time.sleep(0.5)

        # 去重
        seen = set()
        unique = []
        for p in all_posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"Pinterest: {len(unique)} unique pins")
        return unique

    def _search(self, term: str) -> list[RawPost]:
        """搜索 pins"""
        try:
            resp = self._client.get(
                f"{PINTEREST_API}/pins/search",
                params={
                    "query": term,
                    "page_size": min(self.limit, 50),
                },
            )
            if resp.status_code == 401:
                logger.error("Pinterest API: Unauthorized - check your token")
                return []
            if resp.status_code == 429:
                logger.warning("Pinterest API: Rate limited")
                return []
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Pinterest search '{term}' failed: {e}")
            return []

        items = data.get("items", [])
        posts = []
        for item in items:
            pin_id = item.get("id", "")
            if not pin_id:
                continue
            post = RawPost(
                source="pinterest",
                source_id=f"pin_{pin_id}",
                title=item.get("title", "") or item.get("description", "")[:200] or term,
                content=item.get("description", "")[:1000],
                url=f"https://www.pinterest.com/pin/{pin_id}/",
                author=item.get("board_owner", {}).get("username", "unknown"),
                score=0,  # Pinterest API 不返回分数
                num_comments=item.get("comment_count", 0),
                created_utc=0,  # API 不返回时间戳
                tags=[term],
                metadata={
                    "search_term": term,
                    "media_type": item.get("media", {}).get("media_type", ""),
                    "dominant_color": item.get("dominant_color", ""),
                    "board_name": item.get("board", {}).get("name", ""),
                },
            )
            posts.append(post)

        logger.info(f"Pinterest '{term}': {len(posts)} pins")
        return posts

    def close(self):
        self._client.close()
