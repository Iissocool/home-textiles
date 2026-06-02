"""诊断 TikTok 页面实际内容"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)

    page = context.new_page()
    page.goto("https://www.tiktok.com/tag/bedding", wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(5000)

    # 取标题和页面内容类型
    title = page.title()
    print(f"Title: {title}")

    # 检查是否有验证/登录/空白页面
    body_text = page.evaluate("() => document.body?.innerText?.substring(0, 1000) || ''")
    print(f"\nBody text:\n{body_text[:500]}")

    # 检查 script 标签
    scripts = page.evaluate("""() => {
        const scripts = document.querySelectorAll('script[id]');
        return Array.from(scripts).map(s => s.id);
    }""")
    print(f"\nScript IDs: {scripts}")

    # 检查是否有视频元素
    videos = page.evaluate("() => document.querySelectorAll('video, [data-e2e^=video], [class*=VideoContainer]').length")
    print(f"Video elements: {videos}")

    # 保存页面 HTML 前 5000 字符
    html = page.content()
    print(f"\nHTML length: {len(html)}")
    print(f"HTML preview:\n{html[:1000]}")

    page.screenshot(path="/tmp/tiktok_diag.png")
    print("\nScreenshot saved to /tmp/tiktok_diag.png")

    browser.close()
