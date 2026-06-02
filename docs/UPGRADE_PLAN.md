# Phase 1.5 — 数据精细化改造方案

## 目标
1. 电商平台（Amazon/SHEIN）抓取买家评论
2. 社媒平台（Reddit/TikTok/X）抓取用户评论
3. LLM 简报分两路：社媒趋势 + 电商分析
4. 看板显示评论内容

---

## 改造清单

### 1. 数据库 — 新增评论表

```sql
-- 帖子评论/评价
CREATE TABLE IF NOT EXISTS post_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER NOT NULL,         -- 关联 raw_posts.id
    source      TEXT NOT NULL,
    author      TEXT DEFAULT '',
    content     TEXT DEFAULT '',
    score       INTEGER DEFAULT 0,        -- Reddit upvotes / 点赞
    created_utc INTEGER DEFAULT 0,
    fetched_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    FOREIGN KEY (post_id) REFERENCES raw_posts(id)
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON post_comments(post_id);
```

### 2. Reddit — 加评论抓取

PullPush 有 Comment API：
```
GET https://api.pullpush.io/reddit/search/comment/
  ?subreddit=HomeDecorating
  &link_id=t3_xxxxx
  &size=20
```

**实现：** RedditScraper 加 `fetch_comments(post_id, reddit_post_id)` 方法，抓每条帖子的 top 评论。

### 3. TikTok — 加评论 + 播放数据

TikTok 页面已加载评论，通过 OpenCLI 提取：
```javascript
// 提取视频评论
document.querySelectorAll('[class*=Comment]')
```

同时补充播放量、点赞数（目前只有 0）。

### 4. X/Twitter — GetXAPI 有回复端点

GetXAPI 提供 `tweet/replies` 端点（$0.001/次），可以获取每条推文的回复。

### 5. Amazon — 抓商品详情页评论

流程：
```
搜索页 → 提取商品链接 → 逐个打开商品页 → 提取评论
```

Amazon 商品页评论在：
```css
[data-hook=review] .review-text
```

注意：每个商品页会显著增加耗时（~5-10秒/个）。建议只抓 Top 3 评论。

### 6. SHEIN — 商品页评论

SHEIN 商品页也有评论，同样通过 JSON-LD 或 DOM 提取。

### 7. LLM Router — 分流处理

当前：所有来源一起送 → 趋势简报

改为两路：

```
Pipeline A: 社媒情报
  输入: Reddit + TikTok + X 的帖子 + 评论
  输出: 消费者趋势简报（需求、情感、关键词）

Pipeline B: 电商情报
  输入: Amazon + SHEIN 的竞品数据 + 评论
  输出: 市场竞争简报（定价、评分、买家痛点）
```

Router 代码结构：
```javascript
// 读取数据时按 source 分组
const socialPosts = db.prepare("...WHERE source IN ('reddit','tiktok','twitter')").all();
const ecomPosts = db.prepare("...WHERE source IN ('amazon','shein')").all();

// 两路独立 prompt
const socialBrief = await generateSocialBrief(socialPosts);
const ecomBrief = await generateEcomBrief(ecomPosts);

// 合并输出
saveBrief(db, weekStr, JSON.stringify({social: socialBrief, ecom: ecomBrief}));
```

### 8. 看板 — 显示评论

每条帖子卡片下加 "查看评论" 按钮，点击展开显示评论列表。

---

## 实施顺序

```
Step 1: 数据库加评论表
Step 2: Reddit 加评论
Step 3: Amazon 加评论（最影响决策价值）
Step 4: SHEIN 加评论
Step 5: Router 分流改造
Step 6: 看板显示评论
Step 7: TikTok/X 评论（优先级最低）
```

## 预计耗时

| 步骤 | 预估 |
|---|---|
| Step 1-2 | 30min |
| Step 3 | 45min |
| Step 4 | 30min |
| Step 5 | 30min |
| Step 6 | 20min |
| Step 7 | 30min |
| **合计** | **~3h** |
