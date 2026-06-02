"""写入 API Keys 到 .env（从环境变量读取，不硬编码）"""
import os

content = """# OpenRouter ($5 budget)
OPENROUTER_API_KEY={openrouter}
# Pinterest
PINTEREST_TOKEN={pinterest}
# X/Twitter - GetXAPI
X_API_KEY={xapi}
# X API v2 Bearer Token (备选)
X_BEARER_TOKEN={xbearer}
"""

path = os.path.join(os.path.dirname(__file__), "..", ".env")
content = content.format(
    openrouter=os.environ.get("OPENROUTER_API_KEY", ""),
    pinterest=os.environ.get("PINTEREST_TOKEN", ""),
    xapi=os.environ.get("X_API_KEY", ""),
    xbearer=os.environ.get("X_BEARER_TOKEN", ""),
)
with open(path, "w") as f:
    f.write(content)
print(f"Written to {path}")
