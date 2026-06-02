"""调用 Sonnet 4.6 重写 Intelligence Router —— 分两路处理"""
import httpx, json, os

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
with open(env_path) as f:
    for line in f:
        if line.startswith("OPENROUTER_API_KEY="):
            key = line.strip().split("=", 1)[1]
            break

with open(os.path.join(os.path.dirname(__file__), "..", "router", "src", "router.js")) as f:
    code = f.read()

prompt = f"""Rewrite this Intelligence Router to process TWO separate pipelines instead of one.

Current router:
```javascript
{code}
```

Required changes:

1. **Dual pipeline**: Process posts in two separate batches:
   - Social pipeline: source IN ('reddit','tiktok','twitter') → consumer trend brief
   - E-commerce pipeline: source IN ('amazon','shein') → market competition brief (pricing, ratings, review sentiment)

2. **E-commerce brief should include**: 
   - Price range analysis (min, max, average per product category)
   - Rating distribution
   - Common review topics/themes (positive + negative)
   - Top competitor products

3. **Output format**:
```json
{{
  "week": "2026-W23",
  "social": {{ trends: [...], overall_summary: "...", top_product_recommendation: {{...}} }},
  "ecommerce": {{ 
    categories: [{{ search_term: "cooling sheets", product_count: 20, price_range: "$15-$110", avg_rating: 4.5, top_competitors: [...], review_insights: "..." }}],
    overall_assessment: "..."
  }}
}}
```

4. **Keep all existing features**: dry-run, budget tracking, SQLite logging, .env loading

5. **Cost control**: The e-commerce pipeline should use a shorter/more efficient prompt since the data is more structured. Social pipeline can use the existing detailed prompt.

Return the COMPLETE rewritten router.js file."""

r = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    json={
        "model": "anthropic/claude-sonnet-4.6",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 4000,
    },
    timeout=120,
)
data = r.json()
reply = data["choices"][0]["message"]["content"]
usage = data.get("usage", {})
cost = (usage.get("prompt_tokens", 0) * 3 + usage.get("completion_tokens", 0) * 15) / 1_000_000
print(f"COST={cost:.5f}")
print(f"PROMPT_TOKENS={usage.get('prompt_tokens',0)}")
print(f"COMPLETION_TOKENS={usage.get('completion_tokens',0)}")
print("---CODE---")
print(reply)
