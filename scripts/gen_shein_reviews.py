"""调用 Sonnet 4.6 生成 SHEIN 评论提取代码"""
import httpx, json, os, sys

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
with open(env_path) as f:
    for line in f:
        if line.startswith("OPENROUTER_API_KEY="):
            key = line.strip().split("=", 1)[1]
            break

code_path = os.path.join(os.path.dirname(__file__), "..", "scrapers", "shein.py")
with open(code_path) as f:
    code = f.read()

prompt = f"""Add review extraction to this SHEIN OpenCLI scraper.

Current code:
```python
{code}
```

Requirements:
1. Add `fetch_reviews(self, product_url: str, limit: int = 5) -> list[dict]` method
2. SHEIN stores review data in JSON-LD schema.org markup inside <script type="application/ld+json"> on product pages. Parse it.
3. Reviews are in "review" array within the schema. Each has: author.name, reviewRating.ratingValue, name (title), reviewBody (text), datePublished
4. Alternative DOM fallback: if JSON-LD not found, look for review cards with class names containing "review" or "Review"
5. Add `fetch_reviews_for_all(self, posts: list, conn) -> int` same pattern as Amazon scraper
6. Save via insert_comment() from db.database
7. Return ONLY the two methods as Python code, no class wrapper, no explanation"""

r = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={
        "model": "anthropic/claude-sonnet-4.6",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2500,
    },
    timeout=60,
)
data = r.json()
reply = data["choices"][0]["message"]["content"]
usage = data.get("usage", {})
cost = (usage.get("prompt_tokens", 0) * 3 + usage.get("completion_tokens", 0) * 15) / 1_000_000
print(f"SONNET_COST={cost:.5f}")
print(f"SONNET_PROMPT={usage.get('prompt_tokens',0)}")
print(f"SONNET_COMPLETION={usage.get('completion_tokens',0)}")
print("---CODE---")
print(reply)
