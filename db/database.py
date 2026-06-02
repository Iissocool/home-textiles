"""
需求驱动家纺生态系统 · 数据库初始化与操作
"""
import sqlite3
import json
import time
from pathlib import Path
from loguru import logger


DB_DIR = Path(__file__).resolve().parent


def get_db_path(db_name: str = "textiles.db") -> Path:
    return DB_DIR / db_name


def init_db(db_path: str | Path | None = None):
    """初始化数据库，执行 schema.sql"""
    if db_path is None:
        db_path = get_db_path()
    schema_file = DB_DIR / "schema.sql"
    if not schema_file.exists():
        logger.error(f"Schema file not found: {schema_file}")
        return False
    schema = schema_file.read_text()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema)
    conn.commit()
    conn.close()
    logger.info(f"Database initialized: {db_path}")
    return True


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def insert_raw_post(conn: sqlite3.Connection, post: dict) -> bool:
    """插入一条原始帖子，已存在则忽略"""
    try:
        conn.execute(
            """INSERT OR IGNORE INTO raw_posts
               (source, source_id, title, content, url, author,
                score, num_comments, created_utc, fetched_at, tags, metadata, image_url,
                batch_id, search_keyword)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch(), ?, ?, ?, ?, ?)""",
            (
                post["source"],
                post["source_id"],
                post.get("title", ""),
                post.get("content", ""),
                post.get("url", ""),
                post.get("author", ""),
                post.get("score", 0),
                post.get("num_comments", 0),
                post.get("created_utc", int(time.time())),
                json.dumps(post.get("tags", [])),
                json.dumps(post.get("metadata", {})),
                post.get("image_url", ""),
                post.get("batch_id", ""),
                post.get("search_keyword", ""),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Insert failed: {e}")
        return False


def insert_brief(conn: sqlite3.Connection, week: str, brief_json: str, raw_hash: str = "") -> bool:
    """写入每周趋势简报"""
    try:
        conn.execute(
            """INSERT OR REPLACE INTO trend_briefs
               (week, created_at, brief_json, raw_input_hash)
               VALUES (?, unixepoch(), ?, ?)""",
            (week, brief_json, raw_hash),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Insert brief failed: {e}")
        return False


def log_llm_call(conn: sqlite3.Connection, model: str, prompt_tokens: int,
                 completion_tokens: int, cost_usd: float, purpose: str = ""):
    """记录 LLM 调用"""
    try:
        conn.execute(
            """INSERT INTO llm_calls
               (model, prompt_tokens, completion_tokens, cost_usd, purpose, created_at)
               VALUES (?, ?, ?, ?, ?, unixepoch())""",
            (model, prompt_tokens, completion_tokens, cost_usd, purpose),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Log LLM call failed: {e}")


def total_cost(conn: sqlite3.Connection) -> float:
    """查询 OpenRouter 总花费"""
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls").fetchone()
    return row[0]


def insert_comment(conn: sqlite3.Connection, comment: dict) -> bool:
    """插入一条评论"""
    try:
        conn.execute(
            """INSERT INTO post_comments
               (post_id, source, author, content, score, created_utc, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, unixepoch())""",
            (
                comment["post_id"],
                comment["source"],
                comment.get("author", ""),
                comment.get("content", ""),
                comment.get("score", 0),
                comment.get("created_utc", 0),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Insert comment failed: {e}")
        return False


def get_comments(conn: sqlite3.Connection, post_id: int, limit: int = 20) -> list[dict]:
    """获取某条帖子的评论"""
    rows = conn.execute(
        "SELECT * FROM post_comments WHERE post_id=? ORDER BY score DESC LIMIT ?",
        (post_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
