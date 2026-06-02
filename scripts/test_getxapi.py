"""测试 GetXAPI 搜索功能"""
import os, sys, json

# 从 .env 读取 API key
key = None
with open(os.path.join(os.path.dirname(__file__), "..", ".env")) as f:
    for line in f:
        if line.startswith("X_API_KEY="):
            key = line.strip().split("=", 1)[1]
            break

if not key:
    print("❌ X_API_KEY not found in .env")
    sys.exit(1)

import httpx

# --- Test 1: Advance Search ---
print("=" * 50)
print("Test 1: Advanced Search (cooling sheets)")
print("=" * 50)

r = httpx.get(
    "https://api.getxapi.com/twitter/tweet/advanced_search",
    params={"q": "cooling sheets bedding", "count": 5},
    headers={"Authorization": f"Bearer {key}"},
    timeout=15,
)

data = r.json()
print(f"Status: {r.status_code}")
if r.status_code == 200:
    tweets = data if isinstance(data, list) else data.get("data", data.get("tweets", data.get("results", [])))
    if isinstance(tweets, dict):
        tweets = list(tweets.values())
    print(f"✅ {len(tweets)} tweets")
    for t in tweets[:3]:
        text = t.get("text", t.get("full_text", ""))[:70]
        user = t.get("user", {})
        username = user.get("screen_name", "") if isinstance(user, dict) else ""
        print(f"  @{username}: {text}")
else:
    print(f"❌ {json.dumps(data, indent=2)[:300]}")

# --- Test 2: 家纺多关键词 ---
print("\n" + "=" * 50)
print("Test 2: 家纺关键词批量")
print("=" * 50)

queries = ["bamboo bedding", "linen sheets", "weighted blanket"]
for q in queries:
    r = httpx.get(
        "https://api.getxapi.com/twitter/tweet/advanced_search",
        params={"q": q, "count": 3},
        headers={"Authorization": f"Bearer {key}"},
        timeout=15,
    )
    if r.status_code == 200:
        data2 = r.json()
        tweets = data2 if isinstance(data2, list) else data2.get("data", data2.get("tweets", []))
        if isinstance(tweets, dict):
            tweets = list(tweets.values())
        print(f"  '{q}': {len(tweets)} tweets ✅")
    else:
        print(f"  '{q}': HTTP {r.status_code} ❌")

print("\n✅ 测试完成")
