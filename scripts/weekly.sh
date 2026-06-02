# 需求驱动家纺生态系统 · 保姆级操作手册

## 系统架构总览

```
你每天/每周需要做的事：

  抓取数据  →  存入数据库  →  生成趋势简报  →  查看数据面板
  (scrapers)    (SQLite)      (LLM Router)    (HTML 看板)
```

## 目录结构

```
projects/home-textiles/
├── scrapers/                   ← 爬虫模块
│   ├── base.py                 ← 基础类（不要改）
│   ├── reddit.py               ← Reddit 爬虫（PullPush API）
│   ├── twitter.py              ← X/Twitter 爬虫（GetXAPI）
│   ├── tiktok_cli.py           ← TikTok 爬虫（OpenCLI + Chromium）
│   ├── pinterest.py            ← Pinterest 爬虫（等 Basic 审核）
│   └── runner.py               ← 统一入口
├── router/
│   └── src/router.js           ← Intelligence Router（LLM 分析）
├── db/
│   ├── schema.sql              ← 数据库结构
│   ├── database.py             ← Python 数据库操作
│   └── textiles.db             ← 数据文件
├── config/config.yaml          ← 配置文件（subreddit、关键词等）
├── reports/dashboard.html      ← 数据看板（浏览器打开）
├── scripts/                    ← 工具脚本
│   ├── verify_pipeline.py      ← 跑 Reddit → DB 验证
│   ├── test_getxapi.py         ← 测试 X/Twitter
│   ├── test_tiktok_cli.py      ← 测试 TikTok
│   ├── generate_dashboard.py   ← 生成 HTML 看板
│   └── write_env.py            ← 环境变量管理
├── .env                        ← API Key（不要提交到 git）
├── requirements.txt            ← Python 依赖
└── package.json                ← Node.js 依赖
```

---

## 第一步：环境准备（一次性）

### 1.1 激活虚拟环境

```bash
cd projects/home-textiles
source .venv/bin/activate
```

### 1.2 你的 API Key 清单

| Key | 在哪里获取 | 当前状态 |
|---|---|---|
| `OPENROUTER_API_KEY` | openrouter.ai → API Keys | ✅ 已配置 |
| `X_API_KEY` | getxapi.com → 注册 → API Keys | ✅ 已配置 |
| `PINTEREST_TOKEN` | developers.pinterest.com → 等 Basic 审核 | ⏳ 待审核 |
| TikTok | 无 API，走浏览器登录 | ✅ Chromium 已登录 |

### 1.3 检查依赖

```bash
pip install -r requirements.txt     # Python 依赖（已装好）
npm install                         # Node.js 依赖（已装好）
```

### 1.4 启动 Chromium（TikTok 需要）

```bash
# 检查 OpenCLI 是否连接
opencli doctor
# 正常应显示:
# [OK] Daemon: running
# [OK] Extension: connected
# [OK] Connectivity: connected
# Everything looks good!

# 如果 Chromium 关闭了，重新启动:
chromium --no-sandbox \
  --load-extension=~/.local/share/opencli-extension \
  --remote-debugging-port=9222 \
  --user-data-dir=~/.config/chromium-opencli \
  about:blank &
sleep 3
opencli doctor   # 确认连接
```

> **注意：** Chromium 窗口可以最小化，但不要关闭。如果关了，TikTok 抓取会失败。

---

## 第二步：日常使用流程

### 2.1 抓取所有数据

```bash
cd projects/home-textiles
source .venv/bin/activate

# 抓取所有已启用的平台（Reddit + X/Twitter + TikTok）
python -m scrapers.runner

# 也可以只抓指定平台
python -m scrapers.runner --sources reddit,twitter
python -m scrapers.runner --sources tiktok
```

**各平台行为：**

| 平台 | 单次抓取 | 耗时 | 注意事项 |
|---|---|---|---|
| Reddit | ~146 条 | ~30s | 5 个 subreddit，自动去重 |
| X/Twitter | ~50 条 | ~15s | 5 个关键词，每条 $0.001 |
| TikTok | ~89 条 | ~30s | 3 个 hashtag，需 Chromium 运行 |
| Pinterest | — | — | 等 Basic 审核通过 |

**TikTok 抓取流程详解：**

```
1. python -m scrapers.runner --sources tiktok
2. 脚本自动连接 OpenCLI → 你的已登录 Chromium
3. 依次访问 tiktok.com/tag/bedding
                     /tag/hometextiles
                     /tag/coolingsheets
4. 从 DOM 提取视频标题、作者、链接、hashtags
5. 写入 SQLite 数据库
```

### 2.2 生成趋势简报

```bash
# 先查看费用预估（不消耗预算）
node router/src/router.js --dry-run

# 正式运行（消耗 $0.08-0.10 预算）
node router/src/router.js
```

**Router 做了什么：**

```
1. 从 SQLite 读取本周所有帖子
2. 用 Sonnet 4.6 分类 → 去噪/相关/情感
3. 对相关帖子 → 聚类 → 趋势识别 → 需求评分
4. 生成 JSON Brief → 写入 trend_briefs 表
5. 记录 LLM 调用 → 追踪预算
```

### 2.3 生成数据看板

```bash
python scripts/generate_dashboard.py

# 然后浏览器打开
xdg-open reports/dashboard.html
```

**看板功能：**

| 标签 | 内容 |
|---|---|
| 📈 趋势简报 | LLM 生成的 4 个趋势 + 推荐产品 |
| 🔴 Reddit | 15 条热门帖，可点击跳转 |
| 🐦 X/Twitter | 15 条热门推文，可点击跳转 |
| 🎵 TikTok | 15 条热门视频，可点击跳转 |

每条帖子都是可点击的 → 点一下直接打开原始页面。

---

## 第三步：完整一周流程（参考）

假设是周一早上：

```bash
cd projects/home-textiles
source .venv/bin/activate

# 1. 确认 Chromium 运行
opencli doctor

# 2. 抓取数据（所有平台）
python -m scrapers.runner

# 3. 预览费用
node router/src/router.js --dry-run

# 4. 生成趋势简报
node router/src/router.js

# 5. 生成看板
python scripts/generate_dashboard.py

# 6. 打开看板查看结果
xdg-open reports/dashboard.html
```

**预计花费：$0.09-0.15 / 周**（你的 $5 够用 8-12 周）

---

## 第四步：配置修改

### 修改抓取的 subreddit / 关键词

编辑 `config/config.yaml`：

```yaml
sources:
  reddit:
    enabled: true
    subreddits:
      - HomeDecorating    # 家装
      - Sleep             # 睡眠
      - Bedding           # 床品
      - Mattress          # 床垫
      - InteriorDesign    # 室内设计
    limit: 50

  twitter:
    enabled: true
    search_queries:
      - "cooling sheets"
      - "bamboo bedding"
      - "linen sheets"
      - "weighted blanket"
    limit: 50

  tiktok:
    enabled: true
    hashtags:
      - bedding
      - hometextiles
      - sleeptok
      - bedroomdecor
    limit: 30
```

### 禁用某个数据源

```yaml
sources:
  tiktok:
    enabled: false   # 改成 false 就跳过了
```

---

## 第五步：常见问题

### Chromium / OpenCLI 问题

```
症状: opencli doctor 显示 "Extension: not connected"
解决:
  1. 开一个新终端
  2. 重跑: chromium --no-sandbox --load-extension=...
  3. 再跑: opencli doctor
```

### TikTok 登录过期

```
症状: TikTok 抓取返回 0 条
解决:
  1. 在 Chromium 窗口里打开 tiktok.com
  2. 检查是否还在登录状态
  3. 如果已登出，重新登录
```

### GetXAPI 余额不足

```
GetXAPI 注册送了 $0.1（≈100 次搜索）。
每周跑 5 次搜索 → 可用 20 周。
如果用完，充值 $10 = 10000 次搜索（≈3 年用量）。
```

### OpenRouter 预算用完

```
Router 内置 $5 封顶。
如果余额接近用完，router 会自动停止并报错。
充值后继续使用，花费记录在 llm_calls 表里。
```

---

## 第六步：一键脚本

把你日常用的组合包装成一个脚本：

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="write_file">
<｜｜DSML｜｜parameter name="content" string="true">#!/bin/bash
# 家纺情报·一键周报生成
# 用法: bash scripts/weekly.sh

set -e
cd "$(dirname "$0")/.."

echo "🏠 家纺情报系统 — 周报生成"
echo "========================"
date

# 激活环境
source .venv/bin/activate

# 1. 检查 OpenCLI
echo -e "\n🔍 检查 Chromium..."
opencli doctor 2>&1 | grep -q "Everything looks good"
if [ $? -ne 0 ]; then
    echo "⚠️  OpenCLI 未连接，TikTok 抓取将跳过"
    TIKTOK_SKIP=true
else
    TIKTOK_SKIP=false
fi

# 2. 抓取数据
echo -e "\n📡 抓取数据中..."
python -m scrapers.runner || echo "⚠️ 抓取部分失败"

# 3. 生成简报
echo -e "\n🤖 运行 Intelligence Router..."
node router/src/router.js --dry-run
echo ""
read -p "继续运行正式简报？(Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    node router/src/router.js
fi

# 4. 生成看板
echo -e "\n📊 生成数据看板..."
python scripts/generate_dashboard.py

# 5. 打开看板
echo -e "\n✅ 完成！打开看板..."
xdg-open reports/dashboard.html 2>/dev/null || \
    echo "请手动打开: reports/dashboard.html"

echo "========================"
echo "预算使用:"
source .venv/bin/activate
python3 -c "
import sqlite3
c = sqlite3.connect('db/textiles.db')
cost = c.execute('SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls').fetchone()[0]
print(f'  已使用: \${cost:.4f}')
print(f'  剩余:   \${5-cost:.4f}')
c.close()
"