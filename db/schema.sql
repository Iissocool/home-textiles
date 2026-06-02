-- 需求驱动家纺生态系统 · 数据库 Schema

-- 原始抓取数据
CREATE TABLE IF NOT EXISTS raw_posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,          -- reddit / pinterest / twitter / tiktok
    source_id   TEXT NOT NULL,          -- 平台的原始 ID
    title       TEXT,
    content     TEXT,
    url         TEXT,
    author      TEXT,
    score       INTEGER DEFAULT 0,
    num_comments INTEGER DEFAULT 0,
    created_utc INTEGER,
    fetched_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    tags        TEXT,                   -- JSON array of extracted tags
    metadata    TEXT,                   -- JSON extra fields
    image_url   TEXT DEFAULT '',        -- 文章/商品配图
    batch_id    TEXT DEFAULT '',        -- 搜索批次标记 (YYYYMMDD_HHMMSS_keyword)
    search_keyword TEXT DEFAULT '',     -- 搜索关键词
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_posts(source);
CREATE INDEX IF NOT EXISTS idx_raw_created ON raw_posts(created_utc);
CREATE INDEX IF NOT EXISTS idx_raw_fetched ON raw_posts(fetched_at);
CREATE INDEX IF NOT EXISTS idx_raw_tags ON raw_posts(tags);

-- 经 LLM 处理后的话题/趋势汇总
CREATE TABLE IF NOT EXISTS trend_briefs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    week        TEXT NOT NULL,           -- ISO week: 2026-W23
    created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    brief_json  TEXT NOT NULL,           -- 完整的 brief JSON
    raw_input_hash TEXT,                 -- 用于去重
    UNIQUE(week)
);

-- LLM 调用日志（成本追踪）
CREATE TABLE IF NOT EXISTS llm_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model       TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0.0,
    purpose     TEXT,
    created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- 帖子评论/评价（通用评论表，适用所有来源）
CREATE TABLE IF NOT EXISTS post_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL,
    source      TEXT NOT NULL,
    author      TEXT DEFAULT '',
    content     TEXT DEFAULT '',
    score       INTEGER DEFAULT 0,
    created_utc INTEGER DEFAULT 0,
    fetched_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    FOREIGN KEY (post_id) REFERENCES raw_posts(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON post_comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_source ON post_comments(source);
