"""
需求驱动家纺生态系统 · TikTok 爬虫

使用 Playwright 无头浏览器抓取 TikTok hashtag 页面数据

TikTok 没有公开 reader API，必须通过浏览器渲染获取数据。
Playwright 方案比 Scrapling 更可靠，因为直接运行真实浏览器。
"""
import time
import re
import json
from typing import Optional
from urllib.parse import quote

from loguru import logger

from .base import BaseScraper, RawPost


class TikTokScraper(BaseScraper):
    """TikTok 爬虫 — 使用 Playwright 无头浏览器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.source_name = "tiktok"
        self.hashtags = config.get("hashtags", [])
        self.limit = min(config.get("limit", 30), 50)
        self._browser = None
        self._context = None

    def _ensure_browser(self):
        """延迟初始化浏览器"""
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()

            # 更完整的隐身参数
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-setuid-sandbox",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            self._context = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                # 使用 Windows 平台伪装
                device_scale_factor=1,
                has_touch=False,
                is_mobile=False,
            )

            # 注入反检测脚本
            self._context.add_init_script("""
                // 隐藏 webdriver 标志
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                // 覆盖 chrome 对象
                window.chrome = { runtime: {} };
                // 覆盖权限查询
                const originalQuery = navigator.permissions.query;
                navigator.permissions.query = (params) => (
                    params.name === 'notifications' ?
                    Promise.resolve({state: 'denied'}) :
                    originalQuery(params)
                );
            """)

    def fetch(self) -> list[RawPost]:
        self._ensure_browser()
        all_posts = []

        for tag in self.hashtags:
            posts = self._scrape_hashtag(tag)
            all_posts.extend(posts)
            time.sleep(1)

        seen = set()
        unique = []
        for p in all_posts:
            if p.source_id not in seen:
                seen.add(p.source_id)
                unique.append(p)

        logger.info(f"TikTok: {len(unique)} unique videos from {len(self.hashtags)} hashtags")
        return unique

    def _scrape_hashtag(self, tag: str) -> list[RawPost]:
        """抓取单个 hashtag 的视频列表"""
        page = self._context.new_page()
        posts = []

        try:
            url = f"https://www.tiktok.com/tag/{tag}"
            logger.info(f"TikTok: loading {url}...")

            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            # 等待页面渲染
            page.wait_for_timeout(5000)

            # 尝试提取 SIGI_STATE（TikTok 的初始数据）
            sigi_state = page.evaluate("() => window.__SIGI_STATE__")
            if not sigi_state:
                # 尝试从 script 标签提取
                sigi_raw = page.evaluate(
                    """() => {
                        const el = document.getElementById('__SIGI_STATE__');
                        return el ? el.textContent : null;
                    }"""
                )
                if sigi_raw:
                    sigi_state = json.loads(sigi_raw)

            if sigi_state:
                posts = self._parse_sigi_state(sigi_state, tag)
                if posts:
                    logger.info(f"TikTok #{tag}: {len(posts)} videos via SIGI_STATE")
                    return posts

            # 备选方案：直接从 DOM 提取视频卡片
            posts = self._parse_dom(page, tag)
            if posts:
                logger.info(f"TikTok #{tag}: {len(posts)} videos via DOM")
                return posts

            # 最后方案：截取页面 API 响应
            posts = self._intercept_api(page, tag)
            if posts:
                logger.info(f"TikTok #{tag}: {len(posts)} videos via API intercept")
                return posts

            logger.warning(f"TikTok #{tag}: no data found")

        except Exception as e:
            logger.warning(f"TikTok #{tag} failed: {e}")

        finally:
            page.close()

        return posts

    def _parse_sigi_state(self, state: dict, tag: str) -> list[RawPost]:
        """从 SIGI_STATE 解析视频数据"""
        posts = []

        # ItemModule 包含视频详情
        items = state.get("ItemModule", {}) or {}
        if isinstance(items, dict):
            for vid_id, vid in items.items():
                if not isinstance(vid, dict):
                    continue
                author = vid.get("author", {})
                stats = vid.get("stats", {}) or {}
                post = RawPost(
                    source="tiktok",
                    source_id=f"tiktok_{vid_id}",
                    title=vid.get("desc", "")[:200],
                    content=vid.get("desc", "")[:1000],
                    url=f"https://www.tiktok.com/@{author.get('uniqueId','')}/video/{vid_id}",
                    author=author.get("uniqueId", ""),
                    score=stats.get("diggCount", stats.get("likeCount", 0)),
                    num_comments=stats.get("commentCount", stats.get("commentCount", 0)),
                    created_utc=vid.get("createTime", 0),
                    tags=[tag],
                    metadata={
                        "hashtag": tag,
                        "music": vid.get("music", {}).get("title", ""),
                        "play_count": stats.get("playCount", 0),
                        "share_count": stats.get("shareCount", 0),
                        "duration": vid.get("video", {}).get("duration", 0),
                    },
                )
                posts.append(post)

        return posts

    def _parse_dom(self, page, tag: str) -> list[RawPost]:
        """从 DOM 提取视频卡片"""
        try:
            cards = page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('[class*="DivItemContainer"]').forEach(el => {
                    const link = el.querySelector('a');
                    const desc = el.querySelector('[class*="Desc"]');
                    if (link) {
                        items.push({
                            url: link.href,
                            text: desc ? desc.textContent : ''
                        });
                    }
                });
                return items;
            }""")

            posts = []
            for card in cards[:self.limit]:
                vid_id = card.get("url", "").split("/video/")[-1] if "/video/" in card.get("url", "") else ""
                if not vid_id:
                    continue
                post = RawPost(
                    source="tiktok",
                    source_id=f"tiktok_{vid_id}",
                    title=card.get("text", "")[:200],
                    content="",
                    url=card.get("url", ""),
                    author="",
                    score=0,
                    tags=[tag],
                    metadata={"hashtag": tag, "source": "dom"},
                )
                posts.append(post)
            return posts
        except Exception:
            return []

    def _intercept_api(self, page, tag: str) -> list[RawPost]:
        """通过拦截 XHR 请求获取 API 数据"""
        posts = []
        try:
            responses = page.evaluate("""() => {
                const entries = performance.getEntriesByType('resource');
                return entries
                    .filter(e => e.name.includes('/api/'))
                    .map(e => e.name);
            }""")
            logger.debug(f"API endpoints found: {len(responses)}")
        except Exception:
            pass
        return posts

    def close(self):
        if self._browser:
            self._browser.close()
        if hasattr(self, "_pw") and self._pw:
            self._pw.stop()
