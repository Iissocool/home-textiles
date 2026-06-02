"""Dashboard v6 — 支持 --batch 参数生成批次看板"""
import sqlite3, json, datetime, sys
from pathlib import Path
from html import escape

DB = Path(__file__).resolve().parent.parent / "db" / "textiles.db"
OUT_DIR = Path(__file__).resolve().parent.parent / "reports"
OUT_DIR.mkdir(exist_ok=True)

# 解析 --batch 参数
batch_filter = None
if "--batch" in sys.argv:
    batch_filter = sys.argv[sys.argv.index("--batch") + 1]
    OUT = OUT_DIR / f"batch_{batch_filter}.html"
else:
    OUT = OUT_DIR / "dashboard.html"

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

sources = conn.execute("SELECT source, COUNT(*) as cnt FROM raw_posts GROUP BY source").fetchall()
total = sum(r["cnt"] for r in sources)
cost = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls").fetchone()[0]

rows = []
if batch_filter:
    src_rows = conn.execute(
        "SELECT id,source,title,url,score,num_comments,author,tags,metadata,image_url FROM raw_posts WHERE batch_id=? ORDER BY score DESC LIMIT 150",
        (batch_filter,)
    ).fetchall()
    rows.extend(src_rows)
else:
    for src in ["amazon", "reddit", "tiktok", "twitter", "shein"]:
        src_rows = conn.execute(
            "SELECT id,source,title,url,score,num_comments,author,tags,metadata,image_url FROM raw_posts WHERE source=? ORDER BY score DESC LIMIT 30",
            (src,)
        ).fetchall()
        rows.extend(src_rows)

# 预渲染卡片 HTML
cards_html = []
for p in rows:
    meta = json.loads(p["metadata"]) if p["metadata"] else {}
    tags = json.loads(p["tags"]) if p["tags"] else []
    search_term = meta.get("search_term", "")
    price = meta.get("price", 0)
    rating = meta.get("rating", 0)
    reviews = meta.get("reviews", 0)
    title = escape((p["title"] or "")[:200])
    author = escape((p["author"] or "")[:15])
    url = escape(p["url"] or "#")
    img = escape(p["image_url"] or "")
    src = p["source"]

    meta_html = f'<span class="b b-{src}">{src}</span>'
    if price: meta_html += f' <span class="pr">${price:.2f}</span>'
    if rating: meta_html += f' <span class="rt">&#11088;{rating}</span>'
    if reviews: meta_html += f' <span>&#128172;{reviews:,}</span>'
    if p["score"]: meta_html += f' <span>&#10084;&#65039;{p["score"]}</span>'
    meta_html += f' <span>&#128100;{author}</span>'

    img_html = f'<img src="{img}" loading="lazy" class="thumb" onerror="this.hidden=true">' if img else ''
    tag_html = f' <span class="t">#{escape(search_term)}</span>' if search_term else ''

    cards_html.append(f'''<div class="c" data-src="{src}" data-price="{price}" data-rating="{rating}" data-reviews="{reviews}" data-score="{p["score"]}" data-term="{escape(search_term)}">
  <div class="ci">{img_html}<div class="ct"><a href="{url}" target="_blank" class="tl">{title}</a><div class="cm">{meta_html}{tag_html}</div></div></div>
</div>''')

# 来源统计
stats_html = f'<div class="s"><div class="sl">总计</div><div class="sv">{total}</div></div>'
for r in sources:
    stats_html += f'<div class="s"><div class="sl">{r["source"]}</div><div class="sv">{r["cnt"]}</div></div>'
stats_html += f'<div class="s"><div class="sl">花费</div><div class="sv" style="color:#34d399">${cost:.4f}</div></div>'

all_cards = "\n".join(cards_html)
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Home Textiles · Dashboard</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#020617;color:#e2e8f0;font-family:Inter,sans-serif;padding:16px}}
h1{{text-align:center;font-size:20px;margin-bottom:2px}}
.hdr{{text-align:center;font-size:10px;color:#64748b;margin-bottom:14px}}
.bar{{display:flex;gap:4px;margin-bottom:12px;flex-wrap:wrap}}
.btn{{font-size:10px;padding:5px 12px;border:1px solid #1e293b;border-radius:6px;cursor:pointer;background:#0f172a;color:#64748b;font-family:inherit}}
.btn.act{{background:#1e293b;color:#f1f5f9;border-color:#334155}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-bottom:12px}}
.s{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:8px 10px}}
.sl{{font-size:8px;color:#64748b;text-transform:uppercase}}
.sv{{font-size:20px;font-weight:700}}
.ctrl{{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;align-items:center}}
.ctrl select,.ctrl input{{background:#0f172a;border:1px solid #1e293b;border-radius:6px;color:#e2e8f0;font-size:11px;padding:4px 8px;font-family:inherit}}
.ctrl input{{flex:1;min-width:120px}}
.c{{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:8px 10px;margin-bottom:4px}}
.ci{{display:flex;align-items:flex-start;gap:8px}}
.thumb{{width:64px;height:64px;object-fit:cover;border-radius:6px;flex-shrink:0}}
.ct{{flex:1;min-width:0}}
.tl{{font-size:12px;font-weight:500;color:#e2e8f0;text-decoration:none;display:block;line-height:1.4}}
.tl:hover{{color:#60a5fa}}
.cm{{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px;font-size:10px;align-items:center}}
.b{{font-size:8px;padding:1px 5px;border-radius:3px;font-weight:600}}
.b-reddit{{background:rgba(255,69,0,.15);color:#ff8a60}}
.b-twitter{{background:rgba(29,155,240,.15);color:#60b0f4}}
.b-tiktok{{background:rgba(255,0,80,.15);color:#ff6080}}
.b-amazon{{background:rgba(255,153,0,.15);color:#ffb84d}}
.b-shein{{background:rgba(6,182,212,.15);color:#67e0f0}}
.pr{{color:#34d399;font-weight:600}}
.rt{{color:#fbbf24}}
.t{{font-size:9px;color:#475569}}
#cnt{{font-size:10px;color:#64748b;margin-left:auto}}
.ftr{{text-align:center;font-size:9px;color:#334155;margin-top:20px}}
.hide{{display:none}}
</style>
</head>
<body>
<h1>🏠 家纺情报面板</h1>
<div class="hdr">{now} · 点击标题打开原文</div>
<div class="stats">{stats_html}</div>
<div class="bar">
  <button class="btn act" data-f="all">📊 全部</button>
  <button class="btn" data-f="reddit">🔴 Reddit</button>
  <button class="btn" data-f="twitter">🐦 X</button>
  <button class="btn" data-f="tiktok">🎵 TikTok</button>
  <button class="btn" data-f="amazon">📦 Amazon</button>
  <button class="btn" data-f="shein">👗 SHEIN</button>
</div>
<div class="ctrl">
  <select id="sort">
    <option value="score">热度</option>
    <option value="price_h">价格高→低</option>
    <option value="price_l">价格低→高</option>
    <option value="rating">评分</option>
    <option value="reviews">评论数</option>
  </select>
  <input id="search" placeholder="搜索...">
  <span id="cnt">0</span>
</div>
<div id="list">{all_cards}</div>
<div class="ftr">{"" if not batch_filter else f"Batch: {batch_filter} · "}每源 top 30 · 共 {len(cards_html)} 条 · 刷新页面重新排序</div>
<script>
function q(s){{return document.querySelector(s)}}
function qa(s){{return document.querySelectorAll(s)}}

// Filter buttons
qa(".btn").forEach(b => b.onclick = function(){{
  qa(".btn").forEach(x => x.classList.remove("act"));
  this.classList.add("act");
  filter();
}});

q("#sort").onchange = filter;
q("#search").oninput = filter;

function filter(){{
  let f = q(".btn.act").dataset.f;
  let s = q("#sort").value;
  let t = q("#search").value.toLowerCase();
  let cards = qa("#list .c");
  let visible = 0;

  cards.forEach(c => {{
    let src = c.dataset.src;
    let title = c.querySelector(".tl").textContent.toLowerCase();
    let show = (f === "all" || src === f) && (!t || title.includes(t));
    c.classList.toggle("hide", !show);
    if(show) visible++;
  }});

  // Sort visible cards
  let parent = q("#list");
  let sorted = Array.from(cards).filter(c => !c.classList.contains("hide"));
  switch(s){{
    case"price_h": sorted.sort((a,b) => (parseFloat(b.dataset.price)||0) - (parseFloat(a.dataset.price)||0)); break;
    case"price_l": sorted.sort((a,b) => (parseFloat(a.dataset.price)||0) - (parseFloat(b.dataset.price)||0)); break;
    case"rating": sorted.sort((a,b) => (parseFloat(b.dataset.rating)||0) - (parseFloat(a.dataset.rating)||0)); break;
    case"reviews": sorted.sort((a,b) => (parseFloat(b.dataset.reviews)||0) - (parseFloat(a.dataset.reviews)||0)); break;
    default: sorted.sort((a,b) => (parseFloat(b.dataset.score)||0) - (parseFloat(a.dataset.score)||0));
  }}
  sorted.forEach(c => parent.appendChild(c));
  q("#cnt").textContent = visible + " / " + cards.length;
}}
filter();
</script>
</body>
</html>"""

OUT.write_text(HTML, encoding="utf-8")
print(f"Done: {OUT}")
print(f"  Cards: {len(cards_html)}")
print(f"  Size: {OUT.stat().st_size // 1024}KB")
