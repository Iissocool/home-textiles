"""
需求驱动家纺生态系统 · X (Twitter) 爬虫

数据源优先级：
  1. GetXAPI（推荐）— $0.001/次搜索，注册送 $0.1（≈100次/2000条推）
  2. X API v2 免费版（1500 条/月，仅限 Basic tier+）
  3. Nitter RSS（已失效，作 fallback）

GetXAPI 接入：
  1. 访问 https://www.getxapi.com/signup
  2. 注册 → 拿 API Key
  3. 设置环境变量：export X_API_KEY="your_key"
"""
import os
import time
from typing import Optional

import httpx
from loguru import logger

from .base import BaseScraper, RawPost

GETXAPI_BASE = "https://api.getxapi.com"
X_API_V2 = "https://api.twitter.com/2"
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.woodland.cafe",
]


class TwitterScraper(BaseScraper):
    """X/Twitter 爬虫"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "twitter"
        self.search_queries = config.get("search_queries", [])
        self.limit = min(config.get("limit", 50), 100)
        self.getxapi_key = os.environ.get("X_API_KEY", "")
        self.bearer_token = os.environ.get("X_BEARER_TOKEN", "")
        self._client = httpx.Client(timeout=20)

    def fetch(self) -> list[RawPost]:
        posts = []

        # 策略 1: GetXAPI（推荐，只需 API Key）
        if self.getxapi_key:
            posts = self._fetch_getxapi()
        # 策略 2: X API v2 Bearer Token
        elif self.bearer_token:
            posts = self._fetch_xapi_v2()
        # 策略 3: Nitter（基本已失效）
        else:
            posts = self._fetch_nitter()

        seen = set()
        unique = []
        for p in posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"X/Twitter: {len(unique)} unique tweets")
        return unique

    def _fetch_getxapi(self) -> list[RawPost]:
        """通过 GetXAPI 搜索"""
        headers = {"Authorization": f"Bearer {self.getxapi_key}"}
        all_posts = []

        for query in self.search_queries:
            try:
                resp = self._client.get(
                    f"{GETXAPI_BASE}/twitter/tweet/advanced_search",
                    headers=headers,
                    params={"q": query, "count": min(self.limit, 20)},
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.warning(f"GetXAPI '{query}': HTTP {resp.status_code}")
                    continue

                data = resp.json()
                tweets = data if isinstance(data, list) else data.get("data", data.get("tweets", data.get("results", [])))

                if isinstance(tweets, dict):
                    tweets = list(tweets.values())

                for tw in tweets[:self.limit]:
                    tw_id = str(tw.get("id", ""))
                    if not tw_id:
                        continue
                    text = tw.get("text", tw.get("full_text", tw.get("content", "")))
                    user = tw.get("user", tw.get("author", {}))
                    username = ""
                    if isinstance(user, dict):
                        username = user.get("screen_name", user.get("username", user.get("name", "")))
                    elif isinstance(user, str):
                        username = user

                    metrics = tw.get("public_metrics", tw.get("metrics", {}))
                    likes = (metrics.get("like_count", metrics.get("likes", 0))
                             or tw.get("favorite_count", tw.get("likeCount", 0)))
                    retweets = (metrics.get("retweet_count", metrics.get("retweets", 0))
                                or tw.get("retweet_count", tw.get("retweetCount", 0)))
                    replies = metrics.get("reply_count", metrics.get("replies", 0)) or tw.get("replyCount", 0)

                    # 尝试多种时间戳格式
                    created_at = 0
                    raw_time = tw.get("created_at", "")
                    if raw_time:
                        try:
                            import datetime
                            # X API 格式: "Wed Jun 01 00:00:00 +0000 2026"
                            dt = datetime.datetime.strptime(raw_time, "%a %b %d %H:%M:%S %z %Y")
                            created_at = int(dt.timestamp())
                        except ValueError:
                            try:
                                import datetime
                                dt = datetime.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                                created_at = int(dt.timestamp())
                            except:
                                created_at = int(time.time())

                    post = RawPost(
                        source="twitter",
                        source_id=f"getxapi_{tw_id}",
                        title=text[:200],
                        content=text[:2000],
                        url=tw.get("url", f"https://x.com/{username}/status/{tw_id}"),
                        image_url=((tw.get("media") or [{}])[0].get("url", "")) if isinstance(tw.get("media"), list) and tw["media"] else "",
                        author=str(username) if username else "unknown",
                        score=likes or 0,
                        num_comments=(replies or 0) + (retweets or 0),
                        created_utc=created_at,
                        tags=[query],
                        metadata={"source": "getxapi"},
                    )
                    all_posts.append(post)

                logger.info(f"GetXAPI '{query}': {len(tweets)} tweets")
                time.sleep(0.5)

            except Exception as e:
                logger.warning(f"GetXAPI '{query}' failed: {e}")
                continue

        return all_posts

    def _fetch_xapi_v2(self) -> list[RawPost]:
        """通过 X API v2 Bearer Token"""
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        all_posts = []

        for query in self.search_queries:
            try:
                resp = self._client.get(
                    f"{X_API_V2}/tweets/search/recent",
                    headers=headers,
                    params={
                        "query": query,
                        "max_results": min(self.limit, 10),
                        "tweet.fields": "created_at,public_metrics,author_id,text",
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.warning(f"X API '{query}': HTTP {resp.status_code}")
                    continue

                data = resp.json()
                tweets = data.get("data", [])

                users = {}
                for u in data.get("includes", {}).get("users", []):
                    users[u["id"]] = u.get("username", "unknown")

                for tw in tweets:
                    metrics = tw.get("public_metrics", {})
                    from datetime import datetime
                    created_utc = 0
                    if tw.get("created_at"):
                        try:
                            dt = datetime.fromisoformat(tw["created_at"].replace("Z", "+00:00"))
                            created_utc = int(dt.timestamp())
                        except:
                            pass

                    post = RawPost(
                        source="twitter",
                        source_id=f"xapi_{tw['id']}",
                        title="",
                        content=tw.get("text", "")[:2000],
                        url=f"https://x.com/{users.get(tw.get('author_id', ''), 'user')}/status/{tw['id']}",
                        author=users.get(tw.get("author_id", ""), "unknown"),
                        score=metrics.get("like_count", 0),
                        num_comments=metrics.get("reply_count", 0) + metrics.get("retweet_count", 0),
                        created_utc=created_utc,
                        tags=[query],
                        metadata={"source": "xapi_v2"},
                    )
                    all_posts.append(post)

                logger.info(f"X API '{query}': {len(tweets)} tweets")
                time.sleep(1)

            except Exception as e:
                logger.warning(f"X API '{query}' failed: {e}")

        return all_posts

    def _fetch_nitter(self) -> list[RawPost]:
        """通过 Nitter RSS（fallback，基本已失效）"""
        all_posts = []
        for query in self.search_queries:
            for instance in NITTER_INSTANCES:
                try:
                    url = f"{instance}/search/rss?q={query.replace(' ', '%20')}"
                    resp = httpx.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200 or len(resp.content) < 100:
                        continue

                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(resp.content)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall(".//atom:entry", ns) or root.findall("entry")

                    for entry in entries[:self.limit]:
                        title = entry.findtext("title", "")
                        link = entry.findtext("link", "")
                        entry_id = entry.findtext("id", "") or link
                        content = entry.findtext("content", "")[:1000]

                        post = RawPost(
                            source="twitter",
                            source_id=entry_id,
                            title=title[:200],
                            content=content,
                            url=link,
                            author="nitter",
                            score=0, num_comments=0,
                            tags=[query],
                            metadata={"source": "nitter", "instance": instance},
                        )
                        all_posts.append(post)

                    if all_posts:
                        logger.info(f"Nitter '{query}': {len(entries)} tweets")
                        break
                except Exception:
                    continue
                time.sleep(0.5)

        return all_posts

    def close(self):
        self._client.close()
