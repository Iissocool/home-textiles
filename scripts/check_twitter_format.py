"""检查 GetXAPI 返回格式"""
import os, httpx, json

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
key = None
with open(env_path) as f:
    for line in f:
        if "X_API_KEY" in line and "=" in line:
            key = line.strip().split("=", 1)[1]
            break

r = httpx.get("https://api.getxapi.com/twitter/tweet/advanced_search",
    params={"q": "cooling sheets bedding", "count": 2},
    headers={"Authorization": f"Bearer {key}"},
    timeout=15)
data = r.json()
tweets = data if isinstance(data, list) else data.get("data", data.get("tweets", data.get("results", [])))
if isinstance(tweets, dict):
    tweets = list(tweets.values())

for tw in tweets[:2]:
    print("Keys:", list(tw.keys()))
    print("Text:", (tw.get("text", "") or "")[:60])
    for k, v in tw.items():
        if isinstance(v, (int, float)):
            print(f"  {k}: {v}")
        elif isinstance(v, dict):
            nums = {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float))}
            if nums:
                print(f"  {k} numeric: {nums}")
    print()
