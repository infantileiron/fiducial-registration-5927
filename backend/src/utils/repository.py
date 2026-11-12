import json, sqlite3, threading
from contextlib import contextmanager
from dataclasses import asdict
from fastapi import HTTPException
from src.config.settings import DATABASE_URL
TABLES = ("datasets", "dataset_versions", "frames", "studies", "runs", "reviews", "reports", "users", "audit")
PLACEHOLDER = "?" if DATABASE_URL.startswith("sqlite:///") else "%s"
# 仅保护单进程内的并发（如 inline 模式下同时提交更新与快照）；
# 多 worker / PostgreSQL 场景由数据库事务本身保证原子性与一致性。
_LOCK = threading.RLock()
def connect():
    if DATABASE_URL.startswith("sqlite:///"):
        return sqlite3.connect(DATABASE_URL.removeprefix("sqlite:///"), timeout=30), PLACEHOLDER
    import psycopg
    return psycopg.connect(DATABASE_URL), PLACEHOLDER
def init_db():
    conn,_ = connect()
    try:
        if not DATABASE_URL.startswith("sqlite:///"):
            conn.execute("SELECT pg_advisory_xact_lock(2405)")
        for table in TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        conn.commit()
    finally: conn.close()
@contextmanager
def transaction():
    """整批更新在同一事务内完成：外部读到的永远是完整的旧版或完整的新版。"""
    conn, q = connect()
    try:
        with _LOCK:
            yield conn, q
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
def all_rows(table, conn=None):
    assert table in TABLES
    own = conn is None
    if own: conn, q = connect()
    else: q = PLACEHOLDER
    try:
        return [json.loads(row[0]) for row in conn.execute(f"SELECT payload FROM {table} ORDER BY id").fetchall()]
    finally:
        if own: conn.close()
def get(table, id, conn=None, for_update=False):
    assert table in TABLES
    own = conn is None
    if own: conn, q = connect()
    else: q = PLACEHOLDER
    try:
        suffix = " FOR UPDATE" if for_update and not DATABASE_URL.startswith("sqlite:///") else ""
        row = conn.execute(f"SELECT payload FROM {table} WHERE id={q}{suffix}", (id,)).fetchone()
        if row is None: raise HTTPException(404, "记录不存在")
        return json.loads(row[0])
    finally:
        if own: conn.close()
def put(table, item, insert_only=False, conn=None):
    assert table in TABLES
    if not isinstance(item, dict): item = asdict(item)
    own = conn is None
    if own: conn, q = connect()
    else: q = PLACEHOLDER
    clause = "DO NOTHING" if insert_only else "DO UPDATE SET payload=excluded.payload"
    sql = f"INSERT INTO {table} (id,payload) VALUES ({q},{q}) ON CONFLICT(id) {clause}"
    payload = json.dumps(item, ensure_ascii=False, allow_nan=False)
    try:
        if own:
            with _LOCK:
                conn.execute(sql, (item["id"], payload))
                conn.commit()
        else:
            conn.execute(sql, (item["id"], payload))
        return item
    finally:
        if own: conn.close()