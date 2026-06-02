/**
 * 需求驱动家纺 · LLM 市场分析引擎
 *
 * 4 步 prompt 链：
 *   Step 1 — 社媒需求分析（Reddit/Twitter/TikTok）
 *   Step 2 — 电商供给分析（Amazon/SHEIN）
 *   Step 3 — 交叉机会分析（Step1 + Step2 → gap）
 *   Step 4 — JSON 结构化摘要（存 DB 方便聚合）
 *
 * 用法: node router/src/analysis.js --batch <batch_id>
 * 输出: HTML + DB (llm_analyses 表) + LLM 调用日志
 */
import { createRequire } from "module";
const require = createRequire(import.meta.url);

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");
const DB_PATH = path.join(PROJECT_ROOT, "db", "textiles.db");
const REPORTS_DIR = path.join(PROJECT_ROOT, "reports");

// 加载 .env
const envPath = path.join(PROJECT_ROOT, ".env");
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, "utf-8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx > 0) {
      const key = trimmed.slice(0, eqIdx).trim();
      const val = trimmed.slice(eqIdx + 1).trim();
      if (!process.env[key]) process.env[key] = val;
    }
  }
}

const Database = require("better-sqlite3");
import OpenAI from "openai";

const MODEL = process.env.ROUTER_MODEL || "anthropic/claude-sonnet-4.6";
const MAX_BUDGET = 5.0;

const SOCIAL_SOURCES = ["reddit", "tiktok", "twitter"];
const ECOM_SOURCES = ["amazon", "shein"];

const openai = new OpenAI({
  baseURL: process.env.OPENROUTER_BASE || "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY || "",
  defaultHeaders: {
    "HTTP-Referer": "https://github.com/xin/home-textiles",
    "X-Title": "Home Textiles Analysis Engine",
  },
});

// 角色设定
const SYSTEM_PROMPT = `You are Black Pearl, an expert e-commerce data analyst specializing in identifying product opportunities for independent, private domain traffic channels. Your task is to cross-reference social media demand against existing e-commerce supply.
Respond ONLY with valid JSON. No markdown, no explanations outside JSON.`;

// ============================================================
// 工具函数
// ============================================================

function calcCost(promptTokens, completionTokens) {
  // Sonnet 4.6: $3/M prompt, $15/M completion
  const promptPrice = 3 / 1_000_000;
  const completionPrice = 15 / 1_000_000;
  return promptTokens * promptPrice + completionTokens * completionPrice;
}

function logCall(db, model, pt, ct, cost, purpose) {
  db.prepare(
    `INSERT INTO llm_calls (model, prompt_tokens, completion_tokens, cost_usd, purpose, created_at)
     VALUES (?, ?, ?, ?, ?, unixepoch())`
  ).run(model, pt, ct, cost, purpose);
}

function getTotalCost(db) {
  const row = db.prepare("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls").get();
  return row.total;
}

async function llmCall(system, userMsg, maxTokens = 2000) {
  const completion = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      { role: "system", content: system },
      { role: "user", content: userMsg },
    ],
    temperature: 0.1,
    max_tokens: maxTokens,
  });
  const usage = completion.usage;
  const cost = calcCost(usage.prompt_tokens, usage.completion_tokens);
  const text = completion.choices[0].message.content;
  return { text, cost, usage };
}

function parseJSON(text) {
  try {
    return JSON.parse(text.replace(/```json\n?|```/g, "").trim());
  } catch {
    return { raw: text };
  }
}

// ============================================================
// 数据查询
// ============================================================

function queryBatchData(db, batchId) {
  // 每个 source 取 score 前 20
  const data = {};

  for (const src of [...SOCIAL_SOURCES, ...ECOM_SOURCES]) {
    const posts = db
      .prepare(
        `SELECT id, source, title, content, score, num_comments, author, tags, metadata, image_url
         FROM raw_posts
         WHERE batch_id=? AND source=?
         ORDER BY score DESC
         LIMIT 20`
      )
      .all(batchId, src);

    // 为每个帖子加载评论
    for (const p of posts) {
      p.comments = db
        .prepare(
          `SELECT author, content, score
           FROM post_comments
           WHERE post_id=?
           ORDER BY score DESC
           LIMIT 5`
        )
        .all(p.id);

      // 整理元数据
      let meta = {};
      try { meta = JSON.parse(p.metadata || "{}"); } catch {}
      p.price = meta.price || 0;
      p.rating = meta.rating || 0;
      p.reviews = meta.reviews || 0;
      p.search_term = meta.search_term || "";
    }

    data[src] = posts;
  }

  return data;
}

// ============================================================
// Prompt 构造
// ============================================================

function buildSocialPrompt(data) {
  let text = "## 社媒数据 (消费者需求信号)\n\n";
  for (const src of SOCIAL_SOURCES) {
    const posts = data[src] || [];
    if (posts.length === 0) continue;
    text += `### ${src} (${posts.length} 条)\n`;
    for (const p of posts) {
      text += `- [${p.score}♥ ${p.num_comments}💬] ${p.title || "(无标题)"}`;
      if (p.content) text += ` | ${p.content.substring(0, 200)}`;
      if (p.comments.length > 0) {
        text += `\n  评论: ${p.comments.map(c => c.content?.substring(0, 100)).filter(Boolean).join(" | ")}`;
      }
      text += "\n";
    }
  }
  return text;
}

function buildEcomPrompt(data) {
  let text = "## 电商数据 (市场供给信号)\n\n";
  for (const src of ECOM_SOURCES) {
    const posts = data[src] || [];
    if (posts.length === 0) continue;
    text += `### ${src} (${posts.length} 条)\n`;
    for (const p of posts) {
      text += `- $${p.price} ★${p.rating} (${p.reviews.toLocaleString()} reviews) — ${p.title?.substring(0, 150)}`;
      if (p.comments.length > 0) {
        text += `\n  评论: ${p.comments.map(c => c.content?.substring(0, 100)).filter(Boolean).join(" | ")}`;
      }
      text += "\n";
    }
  }
  return text;
}

// ============================================================
// 4 步 prompt 链
// ============================================================

async function step1_DemandAnalysis(db, data) {
  console.log("[Analysis] Step 1: Demand Analysis (social)...");
  const socialText = buildSocialPrompt(data);
  const prompt = `Analyze these social media posts about home textiles. Identify:

1. **emerging_trends** (array): Top 3-5 rising trends, each with a name, strength (high/medium/low), and evidence from posts
2. **pain_points** (array): Common consumer frustrations mentioned (e.g., "sheets wrinkle", "too hot", "cheap fabric")
3. **aesthetic_descriptors** (array): Recurring style keywords (e.g., "minimalist", "linen texture", "earth tones")
4. **sentiment** (string): Overall consumer sentiment (excited / curious / frustrated / mixed)
5. **demand_signal** (string): Key takeaway — what should a seller pay attention to?

${socialText}

Respond with a JSON object with keys: emerging_trends, pain_points, aesthetic_descriptors, sentiment, demand_signal.`;

  const result = await llmCall(SYSTEM_PROMPT, prompt, 3000);
  logCall(db, MODEL, result.usage.prompt_tokens, result.usage.completion_tokens, result.cost, "analysis-step1-demand");
  const parsed = parseJSON(result.text);
  console.log(`  → ${parsed.emerging_trends?.length || 0} trends, $${result.cost.toFixed(5)}`);
  return { json: parsed, cost: result.cost };
}

async function step2_SupplyAnalysis(db, data) {
  console.log("[Analysis] Step 2: Supply Analysis (ecom)...");
  const ecomText = buildEcomPrompt(data);
  const prompt = `Analyze these e-commerce product listings for home textiles. Identify:

1. **market_landscape** (object): For each category found, note price range, avg rating, and density (crowded/competitive/fragmented)
2. **product_gaps** (array): Features or price points that seem underserved
3. **negative_review_themes** (array): Common complaints across top products
4. **pricing_sweet_spot** (object): { min, max, recommended } price range based on data

${ecomText}

Respond with a JSON object with keys: market_landscape, product_gaps, negative_review_themes, pricing_sweet_spot.`;

  const result = await llmCall(SYSTEM_PROMPT, prompt, 3000);
  logCall(db, MODEL, result.usage.prompt_tokens, result.usage.completion_tokens, result.cost, "analysis-step2-supply");
  const parsed = parseJSON(result.text);
  console.log(`  → ${parsed.product_gaps?.length || 0} gaps, $${result.cost.toFixed(5)}`);
  return { json: parsed, cost: result.cost };
}

async function step3_CrossReference(db, demand, supply) {
  console.log("[Analysis] Step 3: Cross-reference...");
  const prompt = `You have two analysis outputs. Cross-reference them to identify product opportunities.

## Demand Analysis (Social)
${JSON.stringify(demand, null, 2)}

## Supply Analysis (E-commerce)
${JSON.stringify(supply, null, 2)}

Identify:

1. **gap_opportunities** (array): Each gap should have:
   - trend (string): The trend or demand signal
   - current_offerings (string): What exists on market now
   - gap (string): What's missing or underserved
   - action (string): Concrete product recommendation
   - confidence (string): high/medium/low

2. **top_recommendation** (object): The single best product opportunity with:
   - product_name, category, target_price, key_features (array),_usps (array), risk_factors (array)

3. **summary** (string): One-sentence actionable takeaway for the seller

Respond with a JSON object with keys: gap_opportunities, top_recommendation, summary.`;

  const result = await llmCall(SYSTEM_PROMPT, prompt, 3000);
  logCall(db, MODEL, result.usage.prompt_tokens, result.usage.completion_tokens, result.cost, "analysis-step3-crossref");
  const parsed = parseJSON(result.text);
  console.log(`  → ${parsed.gap_opportunities?.length || 0} opportunities, $${result.cost.toFixed(5)}`);
  return { json: parsed, cost: result.cost };
}

async function step4_StructuredSummary(db, cross) {
  console.log("[Analysis] Step 4: Structured summary...");
  const prompt = `Extract a minimal structured summary from this gap analysis.

${JSON.stringify(cross, null, 2)}

Output ONLY a JSON object with these exact keys:
{
  "top_trends": ["...", "...", "..."],
  "gap_opportunities": [
    {"product": "...", "price_point": 39.99, "confidence": "high"}
  ],
  "risk_factors": ["...", "..."],
  "action_priority": "high/medium/low",
  "summary_note": "one-liner"
}`;

  const result = await llmCall(SYSTEM_PROMPT, prompt, 1500);
  logCall(db, MODEL, result.usage.prompt_tokens, result.usage.completion_tokens, result.cost, "analysis-step4-summary");
  const parsed = parseJSON(result.text);
  console.log(`  → Summary, $${result.cost.toFixed(5)}`);
  return { json: parsed, cost: result.cost };
}

// ============================================================
// HTML 报告生成
// ============================================================

function generateHTML(batchId, step1, step2, step3, step4, totalCost, data) {
  // 统计各 source 数据量
  const counts = {};
  let totalItems = 0;
  for (const src of [...SOCIAL_SOURCES, ...ECOM_SOURCES]) {
    const n = (data[src] || []).length;
    counts[src] = n;
    totalItems += n;
  }

  const now = new Date().toISOString().slice(0, 16).replace("T", " ");
  const d = step1.json;
  const s = step2.json;
  const c = step3.json;
  const m = step4.json;

  // 渲染趋势列表
  const trendItems = (d.emerging_trends || []).map(t =>
    `<div class="gap"><span class="tag ${t.strength || 'medium'}">${(t.strength || 'medium').toUpperCase()}</span> <strong>${escapeHTML(t.name || '')}</strong><br><span class="ev">${escapeHTML(t.evidence || '')}</span></div>`
  ).join("\n");

  const painItems = (d.pain_points || []).map(p =>
    `<li>${escapeHTML(p)}</li>`
  ).join("\n");

  const gapItems = (c.gap_opportunities || []).map(g =>
    `<div class="gap">
      <div class="gap-title"><span class="conf ${g.confidence || 'medium'}">${(g.confidence || 'medium').toUpperCase()}</span> ${escapeHTML(g.trend || '')}</div>
      <div class="gap-detail"><strong>现状：</strong>${escapeHTML(g.current_offerings || '')}</div>
      <div class="gap-detail"><strong>缺口：</strong>${escapeHTML(g.gap || '')}</div>
      <div class="gap-detail"><strong>建议：</strong>${escapeHTML(g.action || '')}</div>
    </div>`
  ).join("\n");

  const rec = c.top_recommendation || {};
  const recHTML = rec.product_name ? `
    <div class="rec">
      <div class="rec-name">🏆 ${escapeHTML(rec.product_name)}</div>
      <div class="rec-detail">类别：${escapeHTML(rec.category || '—')} · 目标价：$${rec.target_price || '—'}</div>
      ${rec.key_features ? `<div class="rec-section"><strong>核心卖点</strong><ul>${rec.key_features.map(f => `<li>${escapeHTML(f)}</li>`).join('')}</ul></div>` : ''}
      ${rec.usps ? `<div class="rec-section"><strong>差异优势</strong><ul>${rec.usps.map(u => `<li>${escapeHTML(u)}</li>`).join('')}</ul></div>` : ''}
      ${rec.risk_factors ? `<div class="rec-section risk"><strong>风险</strong><ul>${rec.risk_factors.map(r => `<li>${escapeHTML(r)}</li>`).join('')}</ul></div>` : ''}
    </div>` : '';

  const marketHTML = s.market_landscape ? Object.entries(s.market_landscape).map(([cat, info]) => {
    const prMin = info?.price_range?.min ?? info?.min;
    const prMax = info?.price_range?.max ?? info?.max;
    const pr = (prMin && prMax) ? `$${prMin}-${prMax}` : (info?.price_range ?? '—');
    return `<div class="gap"><strong>${escapeHTML(cat)}</strong><br><span class="ev">价格 ${pr} · 评分 ${info.avg_rating || info?.price_range?.avg_rating || '—'} · 密度: ${info.density || '—'}</span></div>`;
  }).join("\n") : '';

  const negReviews = (s.negative_review_themes || []).map(r =>
    `<li>${escapeHTML(r)}</li>`
  ).join("\n");

  const riskItems = (m.risk_factors || []).map(r =>
    `<li>${escapeHTML(r)}</li>`
  ).join("\n");

  const topTrends = (m.top_trends || []).map(t =>
    `<span class="tag medium">${escapeHTML(t)}</span>`
  ).join(" ");

  const gapOpps = (m.gap_opportunities || []).map(g =>
    `<div class="gap"><span class="conf ${g.confidence || 'medium'}">${(g.confidence || 'medium').toUpperCase()}</span> ${escapeHTML(g.product || '')} @ $${g.price_point || '—'}</div>`
  ).join("\n");

  const sourceBar = [...SOCIAL_SOURCES, ...ECOM_SOURCES]
    .filter(src => counts[src] > 0)
    .map(src => {
      const emoji = { reddit: "🔴", twitter: "🐦", tiktok: "🎵", amazon: "📦", shein: "👗" }[src] || "📌";
      const label = { reddit: "Reddit", twitter: "X", tiktok: "TikTok", amazon: "Amazon", shein: "SHEIN" }[src] || src;
      return `<span class="src-badge">${emoji} ${label} ${counts[src]}条</span>`;
    }).join(" ");

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Black Pearl · 市场分析</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#020617;color:#e2e8f0;font-family:Inter,sans-serif;padding:20px;max-width:800px;margin:auto}
h1{font-size:22px;margin-bottom:2px;text-align:center}
.hdr{text-align:center;font-size:11px;color:#64748b;margin-bottom:6px}
.sub{text-align:center;font-size:10px;color:#334155;margin-bottom:20px}
.section{border:1px solid #1e293b;border-radius:10px;padding:16px;margin-bottom:14px;background:#0f172a}
.section h2{font-size:14px;margin-bottom:10px;display:flex;align-items:center;gap:6px}
.gap{border:1px solid #1e293b;border-radius:6px;padding:10px;margin-bottom:6px;background:#0a0f1a}
.gap-title{font-size:13px;font-weight:600;margin-bottom:4px}
.gap-detail{font-size:11px;color:#94a3b8;margin-top:2px}
.ev{font-size:11px;color:#94a3b8}
.tag{font-size:9px;padding:1px 6px;border-radius:3px;font-weight:600;margin-right:4px}
.tag.high{background:rgba(52,211,153,.15);color:#34d399}
.tag.medium{background:rgba(251,191,36,.15);color:#fbbf24}
.tag.low{background:rgba(100,116,139,.15);color:#94a3b8}
.conf{font-size:9px;padding:1px 6px;border-radius:3px;font-weight:600;margin-right:4px}
.conf.high{background:rgba(52,211,153,.15);color:#34d399}
.conf.medium{background:rgba(251,191,36,.15);color:#fbbf24}
.conf.low{background:rgba(239,68,68,.15);color:#f87171}
.rec{border:1px solid #3b82f6;border-radius:8px;padding:14px;background:rgba(59,130,246,.08)}
.rec-name{font-size:15px;font-weight:700;color:#60a5fa;margin-bottom:4px}
.rec-detail{font-size:11px;color:#94a3b8;margin-bottom:8px}
.rec-section{margin-top:8px}
.rec-section strong{font-size:11px;color:#94a3b8}
.rec-section ul{margin-top:4px;padding-left:16px;font-size:11px;color:#e2e8f0}
.risk{color:#f87171}
ul{padding-left:16px;font-size:12px;color:#94a3b8;margin-top:4px}
li{margin-bottom:3px}
.src-bar{display:flex;gap:4px;flex-wrap:wrap;justify-content:center;margin-bottom:14px}
.src-badge{font-size:10px;padding:3px 8px;border-radius:4px;background:#1e293b;color:#94a3b8}
.ftr{text-align:center;font-size:9px;color:#334155;margin-top:24px}
</style>
</head>
<body>
<h1>🕶️ Black Pearl · 市场分析报告</h1>
<div class="hdr">Batch: ${escapeHTML(batchId)}</div>
<div class="sub">${now} · 数据源 ${sourceBar} · 共 ${totalItems} 条</div>

<div class="src-bar">${sourceBar}</div>

<div class="section">
<h2>🔥 趋势信号 (Demand)</h2>
<div>${trendItems || '<p style="color:#64748b;font-size:12px">暂无数据</p>'}</div>
${painItems ? `<div style="margin-top:10px"><strong style="font-size:12px;color:#94a3b8">用户痛点</strong><ul>${painItems}</ul></div>` : ''}
${d.aesthetic_descriptors ? `<div style="margin-top:8px"><strong style="font-size:12px;color:#94a3b8">审美关键词</strong><br><span style="font-size:11px;color:#64748b">${d.aesthetic_descriptors.map(escapeHTML).join(' · ')}</span></div>` : ''}
<div style="margin-top:8px;font-size:11px;color:#64748b;font-style:italic">${escapeHTML(d.demand_signal || '')}</div>
</div>

<div class="section">
<h2>📊 市场现状 (Supply)</h2>
${marketHTML || '<p style="color:#64748b;font-size:12px">暂无数据</p>'}
${s.pricing_sweet_spot ? `<div style="margin-top:8px;font-size:12px"><strong>推荐定价区间：</strong>$${s.pricing_sweet_spot.min || '—'} ~ $${s.pricing_sweet_spot.max || '—'} · 推荐 $${
  typeof s.pricing_sweet_spot.recommended === 'number' ? s.pricing_sweet_spot.recommended : (s.pricing_sweet_spot.recommended || '—')
}</div>` : ''}
${negReviews ? `<div style="margin-top:8px"><strong style="font-size:12px;color:#94a3b8">差评主题</strong><ul>${negReviews}</ul></div>` : ''}
</div>

<div class="section">
<h2>💎 机会缺口 (Cross-Reference)</h2>
${gapItems || '<p style="color:#64748b;font-size:12px">暂无数据</p>'}
${recHTML ? `<div style="margin-top:12px">${recHTML}</div>` : ''}
<div style="margin-top:10px;font-size:12px;color:#64748b;font-style:italic;border-top:1px solid #1e293b;padding-top:8px">${escapeHTML(c.summary || '')}</div>
</div>

<div class="section">
<h2>📋 结构化摘要</h2>
<div style="margin-bottom:6px"><strong style="font-size:12px;color:#94a3b8">趋势</strong><br>${topTrends}</div>
<div style="margin-bottom:6px"><strong style="font-size:12px;color:#94a3b8">机会</strong><br>${gapOpps || '<span style="font-size:11px;color:#64748b">无</span>'}</div>
${riskItems ? `<div><strong style="font-size:12px;color:#94a3b8">风险</strong><ul>${riskItems}</ul></div>` : ''}
<div style="margin-top:6px;font-size:11px;color:#64748b">优先级: <span class="tag ${m.action_priority || 'medium'}">${(m.action_priority || 'medium').toUpperCase()}</span> · ${escapeHTML(m.summary_note || '')}</div>
</div>

<div class="ftr">分析成本: $${totalCost.toFixed(5)} · ${totalItems} 条数据 · ${SOCIAL_SOURCES.filter(s => counts[s] > 0).length} 社媒 + ${ECOM_SOURCES.filter(s => counts[s] > 0).length} 电商<br><a href="batch_${encodeURIComponent(batchId)}.html" style="color:#3b82f6;text-decoration:none">← 返回数据看板</a></div>
</body>
</html>`;

  return html;
}

function escapeHTML(s) {
  if (typeof s !== "string") return String(s || "");
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ============================================================
// Main
// ============================================================

async function main() {
  const batchIdx = process.argv.indexOf("--batch");
  if (batchIdx === -1) {
    console.error("❌ 用法: node router/src/analysis.js --batch <batch_id>");
    process.exit(1);
  }
  const batchId = process.argv[batchIdx + 1];
  if (!batchId) {
    console.error("❌ 缺少 batch_id");
    process.exit(1);
  }

  console.log(`\n🕶️  Black Pearl · 市场分析引擎`);
  console.log(`   Batch: ${batchId}`);
  console.log(`   Model: ${MODEL}\n`);

  if (!process.env.OPENROUTER_API_KEY) {
    console.error("❌ OPENROUTER_API_KEY not set");
    process.exit(1);
  }

  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");

  // 预算检查
  const spent = getTotalCost(db);
  const remaining = MAX_BUDGET - spent;
  console.log(`   Budget: $${spent.toFixed(4)} used, $${remaining.toFixed(4)} remaining`);

  if (remaining <= 0) {
    console.error("❌ Budget exhausted!");
    db.close();
    process.exit(1);
  }

  // 1. 读取批次数据
  console.log("\n📡 读取数据...");
  const data = queryBatchData(db, batchId);
  let totalItems = 0;
  for (const src of [...SOCIAL_SOURCES, ...ECOM_SOURCES]) {
    const n = (data[src] || []).length;
    totalItems += n;
    console.log(`   ${src}: ${n} 条`);
  }

  if (totalItems === 0) {
    console.error("❌ 该批次无数据");
    db.close();
    process.exit(1);
  }

  // 2. 执行 4 步分析
  let totalCost = 0;

  const r1 = await step1_DemandAnalysis(db, data);
  totalCost += r1.cost;

  const r2 = await step2_SupplyAnalysis(db, data);
  totalCost += r2.cost;

  const r3 = await step3_CrossReference(db, r1.json, r2.json);
  totalCost += r3.cost;

  const r4 = await step4_StructuredSummary(db, r3.json);
  totalCost += r4.cost;

  console.log(`\n💰 总成本: $${totalCost.toFixed(5)}`);

  // 3. 保存到 DB
  console.log("\n💾 保存到 DB...");
  db.prepare(
    `INSERT OR REPLACE INTO llm_analyses
     (batch_id, created_at, model, social_json, ecom_json, cross_json, summary_json, cost_usd)
     VALUES (?, unixepoch(), ?, ?, ?, ?, ?, ?)`
  ).run(
    batchId,
    MODEL,
    JSON.stringify(r1.json),
    JSON.stringify(r2.json),
    JSON.stringify(r3.json),
    JSON.stringify(r4.json),
    totalCost
  );

  // 4. 生成 HTML 报告
  console.log("📄 生成 HTML 报告...");
  const html = generateHTML(batchId, r1, r2, r3, r4, totalCost, data);
  const outPath = path.join(REPORTS_DIR, `analysis_${batchId}.html`);
  fs.writeFileSync(outPath, html, "utf-8");
  console.log(`   → file://${outPath}`);

  db.close();
  console.log("\n✅ 分析完成\n");
}

main().catch((err) => {
  console.error("❌", err);
  process.exit(1);
});
