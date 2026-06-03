"""
跨境产品 · X (Twitter) 爬虫 (OpenCLI 版)

数据源优先级：
  1. OpenCLI + 已登录 Chromium（通过浏览器搜索 X.com）
  2. GetXAPI（fallback，需 X_API_KEY）
  3. X API v2（fallback，需 X_BEARER_TOKEN）
"""
import os, time, re, json
from typing import Optional

import httpx
from loguru import logger

from .base import BaseScraper, RawPost

GETXAPI_BASE = "https://api.getxapi.com"
X_API_V2 = "https://api.twitter.com/2"


class TwitterScraper(BaseScraper):
    """X/Twitter 爬虫 — 优先 OpenCLI + 已登录 Chromium"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "twitter"
        self.search_queries = config.get("search_queries", [])
        self.limit = min(config.get("limit", 30), 50)
        self.getxapi_key = os.environ.get("X_API_KEY", "")
        self.bearer_token = os.environ.get("X_BEARER_TOKEN", "")
        self._client = httpx.Client(timeout=20)
        # OpenCLI session
        self.session = config.get("opencli_session", self._detect_session())

    def _detect_session(self) -> Optional[str]:
        try:
            r = __import__("subprocess").run(
                ["opencli", "profile", "list"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.split("\n"):
                m = __import__("re").search(r"(\w+)\s*[—–-]\s*connected", line)
                if m:
                    return m.group(1)
        except Exception as e:
            logger.warning(f"OpenCLI session detection failed: {e}")
        return None

    def _opencli(self, *args: str):
        """执行 OpenCLI 命令"""
        import subprocess, json
        if not self.session:
            return {}
        cmd = ["opencli", "browser", self.session] + list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return {}
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            return {}
        except Exception as e:
            logger.warning(f"OpenCLI error: {e}")
            return {}

    def fetch(self) -> list[RawPost]:
        posts = []

        # 策略 1: OpenCLI + 已登录 Chromium
        if self.session:
            posts = self._fetch_opencli()
        # 策略 2: GetXAPI（fallback）
        if not posts and self.getxapi_key:
            posts = self._fetch_getxapi()
        # 策略 3: X API v2 Bearer Token（fallback）
        if not posts and self.bearer_token:
            posts = self._fetch_xapi_v2()

        seen = set()
        unique = []
        for p in posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"X/Twitter: {len(unique)} unique tweets")
        return unique

    def _fetch_opencli(self) -> list[RawPost]:
        """通过 OpenCLI + Chrome 搜索 X.com"""
        all_posts = []

        for query in self.search_queries:
            try:
                # 搜索 X
                search_url = f"https://x.com/search?q={query.replace(' ', '%20')}&src=typed_query&f=top"
                nav = self._opencli("open", search_url)
                page_id = nav.get("page", "")
                if not page_id:
                    logger.warning(f"X OpenCLI: 无法打开搜索页")
                    continue
                self._opencli("tab", "select", page_id)
                time.sleep(5)

                # 滚动加载更多（多次滚动触发懒加载）
                for s in range(3):
                    self._opencli("scroll", "down")
                    time.sleep(2)

                # 从页面提取推文
                raw = self._opencli("eval", """
(() => {
  // X.com 推文容器
  var articles = document.querySelectorAll('article[data-testid="tweet"]');
  var out = [];
  for(var i = 0; i < Math.min(articles.length, 50); i++) {
    var art = articles[i];
    // 推文文本
    var textEl = art.querySelector('[data-testid="tweetText"]');
    var text = textEl ? textEl.textContent.trim() : '';
    // 用户名
    var userEl = art.querySelector('[data-testid="User-Name"] a');
    var username = userEl ? userEl.textContent.trim() : '';
    // 链接
    var linkEl = art.querySelector('a[href*="/status/"]');
    var link = linkEl ? linkEl.href : '';
    var tweetId = link ? link.split('/status/')[1]?.split('?')[0] || '' : '';
    // 互动数据
    var likes = 0;
    var replies = 0;
    var retweets = 0;
    var likeBtn = art.querySelector('[data-testid="like"]');
    if(likeBtn) {
      var likeLabel = likeBtn.getAttribute('aria-label') || '';
      var m = likeLabel.match(/([\\d,]+)/);
      if(m) likes = parseInt(m[1].replace(/,/g,'')) || 0;
    }
    var replyBtn = art.querySelector('[data-testid="reply"]');
    if(replyBtn) {
      var replyLabel = replyBtn.getAttribute('aria-label') || '';
      var m = replyLabel.match(/([\\d,]+)/);
      if(m) replies = parseInt(m[1].replace(/,/g,'')) || 0;
    }
    var retweetBtn = art.querySelector('[data-testid="retweet"]');
    if(retweetBtn) {
      var retweetLabel = retweetBtn.getAttribute('aria-label') || '';
      var m = retweetLabel.match(/([\\d,]+)/);
      if(m) retweets = parseInt(m[1].replace(/,/g,'')) || 0;
    }
    // 图片
    var imgs = art.querySelectorAll('img[alt="Image"]');
    var imgUrl = imgs.length > 0 ? imgs[0].src : '';
    if(imgUrl && imgUrl.includes('twimg.com')) {
      // Twitter 图片，保留
    } else {
      imgUrl = '';
    }

    if(text || tweetId) {
      out.push({
        id: tweetId || 'x_' + i + '_' + Date.now(),
        text: text.substring(0,2000),
        username: username,
        url: link || ('https://x.com/i/web/status/' + tweetId),
        likes: likes,
        replies: replies,
        retweets: retweets,
        img: imgUrl
      });
    }
  }
  return JSON.stringify(out);
})()
""")
                if not raw:
                    logger.info(f"X OpenCLI '{query}': 未找到推文")
                    continue

                tweets = raw if isinstance(raw, list) else []
                if isinstance(raw, dict) and "raw" in raw:
                    try:
                        tweets = json.loads(raw["raw"])
                    except:
                        tweets = []

                for tw in tweets:
                    post = RawPost(
                        source="twitter",
                        source_id=f"xcli_{tw.get('id','')}",
                        title=tw.get("text", "")[:200],
                        content=tw.get("text", "")[:2000],
                        url=tw.get("url", ""),
                        image_url=tw.get("img", ""),
                        author=tw.get("username", "unknown")[:15],
                        score=tw.get("likes", 0),
                        num_comments=tw.get("replies", 0) + tw.get("retweets", 0),
                        tags=[query],
                        metadata={"source": "opencli"},
                    )
                    all_posts.append(post)

                logger.info(f"X OpenCLI '{query}': {len(tweets)} tweets")

            except Exception as e:
                logger.warning(f"X OpenCLI '{query}' failed: {e}")
                continue

        return all_posts

    def _fetch_getxapi(self) -> list[RawPost]:
        """通过 GetXAPI 搜索（原实现）"""
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

                    created_at = 0
                    raw_time = tw.get("created_at", "")
                    if raw_time:
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %z %Y")
                            created_at = int(dt.timestamp())
                        except ValueError:
                            try:
                                from datetime import datetime
                                dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
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
        """通过 X API v2（原实现）"""
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
                    created_utc = 0
                    if tw.get("created_at"):
                        try:
                            from datetime import datetime
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

    def close(self):
        self._client.close()
