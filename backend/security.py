import os
import sqlite3
import threading
import time
import logging
from functools import wraps
from datetime import datetime

log = logging.getLogger("artenisa.security")

DB_PATH = os.getenv("DB_PATH", "data/conversations.db")


def _parse_int_list(value):
    if not value or value.strip() == "0":
        return []
    parts = [p.strip() for p in value.split(",") if p.strip()]
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            log.warning("Invalid ID in env var: %s", p)
    return result


ALLOWED_USER_IDS = _parse_int_list(os.getenv("ALLOWED_USER_IDS") or os.getenv("ALLOWED_USER_ID") or "")
ADMIN_IDS = _parse_int_list(os.getenv("ADMIN_IDS") or "")


def get_role(user_id: int) -> str:
    if not ALLOWED_USER_IDS and not ADMIN_IDS:
        return "admin"
    if user_id in ADMIN_IDS:
        return "admin"
    if user_id in ALLOWED_USER_IDS:
        return "operator"
    return "denied"


def require_role(min_role: str = "operator"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_id = kwargs.get("user_id", args[0] if args else None)
            if user_id is None:
                return {"error": "No autorizado"}
            role = get_role(user_id)
            if role == "denied":
                return {"error": "No autorizado"}
            if min_role == "admin" and role != "admin":
                return {"error": "Se requiere rol admin"}
            return func(*args, **kwargs)
        return wrapper
    return decorator


class AuditLog:

    def __init__(self):
        self._init_table()

    def _get_conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_table(self):
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    command TEXT,
                    target TEXT,
                    timestamp TEXT,
                    status TEXT,
                    details TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def log(self, user_id, username, command, target="", status="ok", details=""):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO audit_log (user_id, username, command, target, timestamp, status, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, command, target, datetime.utcnow().isoformat(), status, details),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent(self, limit=20):
        conn = self._get_conn()
        try:
            cur = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            conn.close()


class RateLimiter:

    def __init__(self):
        self._buckets = {}
        self._lock = threading.Lock()

    def check(self, key: str, max_calls: int = 10, window: int = 60):
        now = time.time()
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = {"calls": [], "blocked_until": 0}
            bucket = self._buckets[key]

            if bucket["blocked_until"] > now:
                reset_after = int(bucket["blocked_until"] - now)
                return (False, 0, reset_after)

            cutoff = now - window
            bucket["calls"] = [t for t in bucket["calls"] if t > cutoff]

            if len(bucket["calls"]) >= max_calls:
                bucket["blocked_until"] = now + 30
                return (False, 0, 30)

            bucket["calls"].append(now)
            remaining = max_calls - len(bucket["calls"])
            oldest = bucket["calls"][0]
            reset_after = max(0, int(window - (now - oldest)))
            return (True, remaining, reset_after)
