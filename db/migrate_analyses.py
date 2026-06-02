"""迁移：添加 llm_analyses 表"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "textiles.db"
db = sqlite3.connect(str(DB))
db.executescript("""
CREATE TABLE IF NOT EXISTS llm_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    TEXT NOT NULL,
    created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    model       TEXT DEFAULT '',
    social_json TEXT,
    ecom_json   TEXT,
    cross_json  TEXT,
    summary_json TEXT,
    cost_usd    REAL DEFAULT 0.0,
    UNIQUE(batch_id)
);
""")
db.commit()
# 验证
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
db.close()
print("Tables:", tables)
print("OK" if "llm_analyses" in tables else "FAIL")
