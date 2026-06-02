"""
验证 X/Twitter API v2 是否工作
用法:  source .venv/bin/activate && python scripts/test_x_api.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 确保 token 已加载
from dotenv import load_dotenv
load_dotenv()

import httpx

token = os.environ.get("X_BEARER_TOKEN", "")
if not token:
    print("❌ X_BEARER_TOKEN not found in .env")
    sys.exit(1)

# URL 解码（如果 token 是 URL 编码的）
from urllib.parse import unquote
token = unquote(token)

print(f"Token loaded: {token[:20]}...{token[-10:]}")
print()

# 测试 1: 搜索推文
print("=" * 50)
print("Test 1: tweet search (冷却 sheets)")
print("=" * 50)

r = httpx.get(
    "https://api.twitter.com/2/tweets/search/recent",
    params={
        "query": "cooling sheets",
        "max_results": 5,
        "tweet.fields": "created_at,public_metrics,author_id",
    },
    headers={"Authorization": f"Bearer {token}"},
    timeout=15,
)

data = r.json()
print(f"Status: {r.status_code}")
if r.status_code == 200:
    tweets = data.get("data", [])
    print(f"✅ 成功! {len(tweets)} tweets")
    for t in tweets:
        m = t.get("public_metrics", {})
        print(f'  [{t["id"]}] {t["text"][:60]}')
        print(f'    ❤️{m.get("like_count",0)} 🔁{m.get("retweet_count",0)}')
    meta = data.get("meta", {})
    print(f"\nResult count: {meta.get('result_count', 0)}")
else:
    print(f"❌ 失败: {r.status_code}")
    print(json.dumps(data, indent=2)[:500])

print()

# 测试 2: 搜索家纺关键词
print("=" * 50)
print("Test 2: 家纺关键词搜索")
print("=" * 50)

queries = ["bamboo bedding", "linen sheets", "weighted blanket"]
for q in queries:
    r = httpx.get(
        "https://api.twitter.com/2/tweets/search/recent",
        params={"query": q, "max_results": 3, "tweet.fields": "public_metrics"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code == 200:
        count = len(r.json().get("data", []))
        print(f"  '{q}': {count} tweets ✅")
    else:
        print(f"  '{q}': HTTP {r.status_code} ❌")

print()
print("=" * 50)
print("测试完成")
print("=" * 50)
