/**
 * 需求驱动家纺生态系统 · Intelligence Router (双通道)
 *
 * Social Pipeline: Reddit, TikTok, Twitter → 消费者趋势简报
 * Ecom Pipeline:  Amazon, SHEIN           → 市场竞争简报
 */
import { createRequire } from "module";
const require = createRequire(import.meta.url);

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");
const DB_PATH = path.join(PROJECT_ROOT, "db", "textiles.db");

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

// ============================================================
// 配置
// ============================================================
const MODEL = process.env.ROUTER_MODEL || "anthropic/claude-sonnet-4.6";
const MAX_BUDGET = 5.0;

const SOCIAL_SOURCES = ["reddit", "tiktok", "twitter"];
const ECOM_SOURCES = ["amazon", "shein"];

const openai = new OpenAI({
  baseURL: process.env.OPENROUTER_BASE || "https://openrouter.ai/api/v1",
  apiKey: process.env.OPENROUTER_API_KEY || "",
  defaultHeaders: {
    "HTTP-Referer": "https://github.com/xin/home-textiles",
    "X-Title": "Home Textiles Intelligence Router",
  },
});

// ============================================================
// 数据库操作
// ============================================================
function getDB() {
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  return db;
}

function getUnprocessedPosts(db, weekStart, weekEnd) {
  const rows = db
    .prepare(
      `SELECT id, source, title, content, score, num_comments, tags, metadata
       FROM raw_posts
       WHERE fetched_at >= ? AND fetched_at < ?
       ORDER BY score DESC
       LIMIT 200`
    )
    .all(weekStart, weekEnd);

  return rows.map((r) => ({
    id: r.id,
    source: r.source,
    title: r.title?.substring(0, 300),
    content: r.content?.substring(0, 500),
    score: r.score,
    comments: r.num_comments,
    tags: (() => { try { return JSON.parse(r.tags || "[]"); } catch { return []; } })(),
    metadata: (() => { try { return JSON.parse(r.metadata || "{}"); } catch { return {}; } })(),
  }));
}

function getPostsBySource(db, weekStart, weekEnd, sources) {
  const placeholders = sources.map(() => "?").join(",");
  const rows = db
    .prepare(
      `SELECT id, source, title, content, score, num_comments, tags, metadata
       FROM raw_posts
       WHERE fetched_at >= ? AND fetched_at < ?
         AND source IN (${placeholders})
       ORDER BY score DESC
       LIMIT 200`
    )
    .all(weekStart, weekEnd, ...sources);

  return rows.map((r) => ({
    id: r.id,
    source: r.source,
    title: r.title?.substring(0, 300),
    content: r.content?.substring(0, 500),
    score: r.score,
    comments: r.num_comments,
    tags: (() => { try { return JSON.parse(r.tags || "[]"); } catch { return []; } })(),
    metadata: (() => { try { return JSON.parse(r.metadata || "{}"); } catch { return {}; } })(),
  }));
}

function getTotalCost(db) {
  const row = db.prepare("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM llm_calls").get();
  return row.total;
}

function logCall(db, model, promptTokens, completionTokens, costUsd, purpose) {
  db.prepare(
    `INSERT INTO llm_calls (model, prompt_tokens, completion_tokens, cost_usd, purpose, created_at)
     VALUES (?, ?, ?, ?, ?, unixepoch())`
  ).run(model, promptTokens, completionTokens, costUsd, purpose);
}

function saveBrief(db, weekStr, briefJson, inputHash) {
  db.prepare(
    `INSERT OR REPLACE INTO trend_briefs (week, created_at, brief_json, raw_input_hash)
     VALUES (?, unixepoch(), ?, ?)`
  ).run(weekStr, briefJson, inputHash);
}

// ============================================================
// LLM Pipeline
// ============================================================

/**
 * Step 1: 去噪 + 初步分类
 * 用便宜的 prompt 快速过滤掉无关内容
 */
async function filterAndClassify(posts) {
  const MAX_POSTS = 80; // 控制 token 消耗
  const sample = posts.slice(0, MAX_POSTS);
  if (sample.length === 0) return { relevant: [], summary: "No data" };

  const prompt = `You are a home textiles trend analyst. Analyze these social media posts about bedding, sheets, and home decor.

For each post, determine:
1. Is it relevant to home textiles/products? (true/false)
2. What product category does it mention? (cooling sheets, linen, bamboo, weighted blanket, duvet, pillow, mattress, decor, other)
3. What is the sentiment? (positive/negative/neutral/curious)

Only respond with JSON array:
[
  {"id":N, "relevant":true/false, "category":"...", "sentiment":"..."}
]

Posts:
${JSON.stringify(sample, null, 2)}`;

  const completion = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      { role: "system", content: "You are a precise data analyst. Respond only with valid JSON." },
      { role: "user", content: prompt },
    ],
    temperature: 0.1,
    max_tokens: 3000,
  });

  const usage = completion.usage;
  const cost = calcCost(usage.prompt_tokens, usage.completion_tokens);

  let classified = [];
  try {
    const text = completion.choices[0].message.content;
    const cleaned = text.replace(/```json\n?|\n?```/g, "").trim();
    classified = JSON.parse(cleaned);
  } catch (e) {
    console.warn("[Router] Failed to parse classification:", e.message);
    return { relevant: [], summary: "Parse error", cost };
  }

  const relevant = sample.filter((_, i) => classified[i]?.relevant === true);
  console.log(
    `[Router] Classified ${sample.length} posts → ${relevant.length} relevant, cost $${cost.toFixed(5)}`
  );

  return { relevant, classified, cost };
}

/**
 * Step 2: 生成趋势简报
 */
async function generateBrief(posts) {
  if (posts.length === 0) {
    return { brief: { trends: [], summary: "No relevant posts this week" }, cost: 0 };
  }

  const postText = posts
    .map(
      (p, i) =>
        `${i + 1}. [${p.source}] "${p.title}" (score:${p.score}, comments:${p.comments})\n   ${p.content || ""}`
    )
    .join("\n\n");

  const prompt = `You are a home textiles market intelligence analyst. Based on the following social media posts from this week, produce a concise "Product Demand Brief".

Identify:
1. TOP TRENDS: What specific home textile products are people talking about? (e.g. "cooling bamboo sheets", "heavy-weight linen duvet")
2. DEMAND SIGNAL: How strong is the demand? (score 1-10 based on volume, engagement, sentiment)
3. KEYWORDS: What specific terms/phrases repeatedly appear?
4. SENTIMENT: What do people love or complain about?
5. ACTIONABLE INSIGHT: If you were to launch ONE product based on this data, what would it be and why?

Respond ONLY with JSON:
{
  "week": "${getISOWeek()}",
  "generated_at": "${new Date().toISOString()}",
  "trends": [
    {
      "product": "string",
      "demand_score": 0-10,
      "sentiment": "positive|mixed|negative",
      "keywords": ["..."],
      "evidence_count": 0,
      "summary": "2-3 sentence insight"
    }
  ],
  "overall_summary": "2-3 sentence week overview",
  "top_product_recommendation": {"product": "...", "reason": "..."}
}

Raw Data:
${postText}`;

  const completion = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      {
        role: "system",
        content:
          "You are a market intelligence analyst specializing in home textiles. Always respond with valid JSON only.",
      },
      { role: "user", content: prompt },
    ],
    temperature: 0.3,
    max_tokens: 2000,
  });

  const usage = completion.usage;
  const cost = calcCost(usage.prompt_tokens, usage.completion_tokens);

  let brief;
  try {
    const text = completion.choices[0].message.content;
    const cleaned = text.replace(/```json\n?|```/g, "").trim();
    brief = JSON.parse(cleaned);
  } catch (e) {
    console.warn("[Router] Brief parse error:", e.message);
    brief = { trends: [], error: e.message };
  }

  console.log(`[Router] Brief generated: ${brief.trends?.length || 0} trends, cost $${cost.toFixed(5)}`);
  return { brief, cost };
}

// ============================================================
// E-COMMERCE PIPELINE
// ============================================================

async function ecomAnalyze(posts) {
  if (posts.length === 0) return { analysis: { categories: [], overall_assessment: "No data" }, cost: 0 };

  const compact = posts.slice(0, 100).map(p => ({
    id: p.id, src: p.source,
    title: (p.title || "").substring(0, 120),
    price: p.metadata?.price ?? null,
    rating: p.metadata?.rating ?? null,
    reviews: p.metadata?.reviews ?? null,
    tags: (p.tags || []).slice(0, 3),
  }));

  const prompt = `You are an e-commerce analyst for home textiles. Analyze these Amazon/SHEIN product listings and produce a Market Competition Brief.

Output JSON:
{
  "categories": [
    {
      "search_term": "string",
      "product_count": 0,
      "platforms": ["amazon", "shein"],
      "price_range": {"min": 0, "max": 0, "avg": 0},
      "avg_rating": 0,
      "total_reviews": 0,
      "top_products": [{"name":"...","price":0,"rating":0,"reviews":0}],
      "review_insights": "1-2 sentences about what buyers say"
    }
  ],
  "overall_assessment": "2-3 sentence market overview"
}

Data:
${JSON.stringify(compact)}`;

  const completion = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      { role: "system", content: "You are an e-commerce analyst. Respond only with valid JSON." },
      { role: "user", content: prompt },
    ],
    temperature: 0.2,
    max_tokens: 2500,
  });

  const usage = completion.usage;
  const cost = calcCost(usage.prompt_tokens, usage.completion_tokens);
  let analysis;
  try {
    const text = completion.choices[0].message.content;
    analysis = JSON.parse(text.replace(/```json\n?|```/g, "").trim());
  } catch (e) {
    console.warn("[Ecom] Parse error:", e.message);
    analysis = { categories: [], overall_assessment: "Parse error" };
  }
  console.log(`[Ecom] Analyzed ${posts.length} products in ${analysis.categories?.length || 0} categories, cost $${cost.toFixed(5)}`);
  return { analysis, cost };
}

// ============================================================
// 工具函数
// ============================================================

function calcCost(promptTokens, completionTokens) {
  // Sonnet 4.6: $3/M prompt, $15/M completion
  const promptPrice = 3 / 1_000_000;
  const completionPrice = 15 / 1_000_000;
  return promptTokens * promptPrice + completionTokens * completionPrice;
}

function getISOWeek() {
  const now = new Date();
  const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, "0")}`;
}

function weekTimestamp() {
  const now = new Date();
  const dayOfWeek = now.getDay();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((dayOfWeek + 6) % 7));
  monday.setHours(0, 0, 0, 0);
  const nextMonday = new Date(monday);
  nextMonday.setDate(monday.getDate() + 7);
  return {
    start: Math.floor(monday.getTime() / 1000),
    end: Math.floor(nextMonday.getTime() / 1000),
  };
}

// ============================================================
// Main
// ============================================================

async function main() {
  const dryRun = process.argv.includes("--dry-run");
  console.log(`\n🤖 Home Textiles Intelligence Router`);
  console.log(`   Model: ${MODEL}`);
  console.log(`   DB:    ${DB_PATH}`);
  console.log(`   Dry run: ${dryRun}\n`);

  // Dry-run 模式跳过 API key 检查
  if (!dryRun) {
    if (!process.env.OPENROUTER_API_KEY) {
      console.error("❌ OPENROUTER_API_KEY not set. Add to .env file:");
      console.error(`   echo 'OPENROUTER_API_KEY=sk-or-v1-...' > ${envPath}`);
      process.exit(1);
    }
  }

  const db = getDB();

  // 预算检查
  const spent = getTotalCost(db);
  const remaining = MAX_BUDGET - spent;
  console.log(`   Budget: $${spent.toFixed(4)} used, $${remaining.toFixed(4)} remaining\n`);

  if (!dryRun && remaining <= 0) {
    console.error("❌ Budget exhausted! Replenish OpenRouter credits.");
    db.close();
    process.exit(1);
  }

  // 读取本周数据（双通道）
  const { start, end } = weekTimestamp();
  const socialPosts = getPostsBySource(db, start, end, SOCIAL_SOURCES);
  const ecomPosts = getPostsBySource(db, start, end, ECOM_SOURCES);
  console.log(`📊 Social posts: ${socialPosts.length} | E-commerce: ${ecomPosts.length}`);

  if (dryRun) {
    console.log("\n[Dry Run — Social]");
    socialPosts.slice(0, 5).forEach((p, i) => {
      console.log(`  ${i+1}. [${p.source}] ${(p.title||"").substring(0, 60)} (score:${p.score})`);
    });
    console.log(`\n[Dry Run — E-commerce]`);
    ecomPosts.slice(0, 5).forEach((p, i) => {
      console.log(`  ${i+1}. [${p.source}] ${(p.title||"").substring(0, 40)} $${p.metadata?.price||"?"} ⭐${p.metadata?.rating||"?"}`);
    });
    console.log(`\n[Dry Run] Total: ${socialPosts.length} social + ${ecomPosts.length} ecommerce (would cost ~$${((socialPosts.length + ecomPosts.length) * 0.004).toFixed(4)})`);
    db.close();
    return;
  }

  const weekStr = getISOWeek();
  let totalCost = 0;

  // === Social Pipeline ===
  console.log("\n🔍 Social Pipeline: filtering & classifying...");
  const { relevant, cost: filterCost } = await filterAndClassify(socialPosts);
  totalCost += filterCost;
  logCall(db, MODEL, 0, 0, filterCost, "social_filter");

  if (totalCost >= remaining) {
    console.error("❌ Budget exceeded during social filtering!");
    db.close();
    process.exit(1);
  }

  console.log("\n📋 Social Pipeline: generating trend brief...");
  const { brief: socialBrief, cost: socialBriefCost } = await generateBrief(relevant);
  totalCost += socialBriefCost;
  logCall(db, MODEL, 0, 0, socialBriefCost, "social_brief");

  if (totalCost >= remaining) {
    console.error("❌ Budget exceeded during social brief!");
    db.close();
    process.exit(1);
  }

  // === E-commerce Pipeline ===
  console.log("\n🛒 E-commerce Pipeline: analyzing products...");
  const { analysis: ecomAnalysis, cost: ecomCost } = await ecomAnalyze(ecomPosts);
  totalCost += ecomCost;
  logCall(db, MODEL, 0, 0, ecomCost, "ecom_analysis");

  // Combine
  const combined = {
    week: weekStr,
    generated_at: new Date().toISOString(),
    social: socialBrief,
    ecommerce: ecomAnalysis,
  };

  saveBrief(db, weekStr, JSON.stringify(combined, null, 2), `week_${weekStr}`);
  saveBudgetSnapshot(db, spent + totalCost);

  // Print summary
  console.log("\n" + "=".repeat(60));
  console.log("📈 SOCIAL TREND BRIEF");
  console.log("=".repeat(60));
  console.log(JSON.stringify(combined.social, null, 2));
  console.log("\n" + "=".repeat(60));
  console.log("🛒 E-COMMERCE BRIEF");
  console.log("=".repeat(60));
  console.log(JSON.stringify(combined.ecommerce, null, 2));
  console.log("=".repeat(60));
  console.log(`💵 This run: $${totalCost.toFixed(5)}`);
  console.log(`💰 Total spent: $${(spent + totalCost).toFixed(4)} / $${MAX_BUDGET}`);
  console.log(`📅 Week: ${weekStr}`);
  console.log("✅ Done!");

  db.close();
}

function saveBudgetSnapshot(db, spent) {
  db.prepare("INSERT INTO config_snapshots (key, value, created_at) VALUES (?, ?, unixepoch())")
    ?.run("budget_spent", String(spent));
}

// 如果 config_snapshots 表不存在，忽略
function ensureSnapshotTable(db) {
  db.exec(`CREATE TABLE IF NOT EXISTS config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT,
    value TEXT,
    created_at INTEGER
  )`);
}

// 手动启动以确保 snapshot 表存在
const _db = getDB();
ensureSnapshotTable(_db);
_db.close();

main().catch((err) => {
  console.error("[Router Fatal]", err);
  process.exit(1);
});
