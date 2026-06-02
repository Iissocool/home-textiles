"""
需求驱动家纺生态系统 · TikTok 爬虫 (OpenCLI 版)

原理：通过 OpenCLI 浏览器桥 → 用已登录的 Chromium 提取 TikTok 数据

前置条件：
  1. Chromium 已启动并加载 OpenCLI 扩展
  2. TikTok 已登录（一次性操作）
  3. opencli doctor 显示 "Everything looks good!"

用法：
  from scrapers.tiktok_cli import TikTokCLIScraper
  scraper = TikTokCLIScraper(config)
  posts = scraper.fetch()
"""
import subprocess, json, time, re
from typing import Optional
from urllib.parse import quote

from loguru import logger

from .base import BaseScraper, RawPost


class TikTokCLIScraper(BaseScraper):
    """TikTok 爬虫 — 通过 OpenCLI 浏览器桥"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "tiktok"
        self.hashtags = config.get("hashtags", [])
        self.limit = min(config.get("limit", 30), 50)
        self.session = config.get("opencli_session", self._detect_session())

    def _detect_session(self) -> Optional[str]:
        """自动检测 OpenCLI session"""
        try:
            r = subprocess.run(
                ["opencli", "profile", "list"],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.split("\n"):
                # 格式: "  h8r935qh — connected v1.0.17"
                m = re.search(r"(\w+)\s*[—–-]\s*connected", line)
                if m:
                    return m.group(1)
        except Exception as e:
            logger.warning(f"OpenCLI session detection failed: {e}")
        return None

    def _opencli(self, *args: str) -> dict:
        """执行 OpenCLI 命令并解析 JSON 输出"""
        cmd = ["opencli", "browser", self.session] + list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                logger.warning(f"OpenCLI error: {r.stderr[:200]}")
                return {}
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            return {"_raw": r.stdout}
        except Exception as e:
            logger.warning(f"OpenCLI failed: {e}")
            return {}

    def _extract_videos(self, hashtag: str) -> list[dict]:
        """提取 hashtag 页面的视频数据"""
        url = f"https://www.tiktok.com/tag/{hashtag}"
        nav = self._opencli("open", url)
        page_id = nav.get("page", "")
        if not page_id:
            logger.warning(f"TikTok: failed to navigate to #{hashtag}")
            return []
        # 切换到新标签
        self._opencli("tab", "select", page_id)
        time.sleep(4)

        # 通过 JS 提取视频数据
        result = self._opencli(
            "eval",
            "Array.from(document.querySelectorAll('a')).filter(a=>a.href.includes('/video/')).map(a=>({url:a.href,title:(a.querySelector('img')?.alt||'').substring(0,500),author:a.href.match(/@([^/]+)/)?.[1]||'',videoId:a.href.match(/video\\/(\\d+)/)?.[1]||'',imgSrc:a.querySelector('img')?.src||''}))"
        )

        if isinstance(result, str):
            return json.loads(result)
        if isinstance(result, dict):
            return result.get("_raw", [])
        if isinstance(result, list):
            return result
        return []

    def fetch(self) -> list[RawPost]:
        if not self.session:
            logger.error("TikTok: No OpenCLI session. Run 'opencli doctor' first.")
            return []

        all_posts = []
        for tag in self.hashtags:
            videos = self._extract_videos(tag)
            for v in videos:
                title = v.get("title", "")
                author = v.get("author", "")
                vid_id = v.get("videoId", "")
                url = v.get("url", "")

                # 提取描述（@ 符号前的部分为主内容）
                desc = title
                # 提取 hashtags
                tags = re.findall(r"#(\w+)", title)

                post = RawPost(
                    source="tiktok",
                    source_id=f"tiktok_{vid_id}",
                    title=desc[:200],
                    content=desc[:1000],
                    url=url,
                    author=author,
                    image_url=v.get("imgSrc", ""),
                    score=0,
                    num_comments=0,
                    tags=list(set(tags + [tag])),
                    metadata={
                        "hashtag": tag,
                        "method": "opencli",
                    },
                )
                all_posts.append(post)

            logger.info(f"TikTok #{tag}: {len(videos)} videos via OpenCLI")
            time.sleep(1)

        seen = set()
        unique = []
        for p in all_posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"TikTok total: {len(unique)} unique videos")
        return unique

    def close(self):
        pass
