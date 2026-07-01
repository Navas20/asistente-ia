import os
import json
import sqlite3
import logging
from datetime import datetime

log = logging.getLogger("artenisa.memory")

DB_PATH = os.getenv("DB_PATH", "data/conversations.db")


class MemoryEngine:

    def __init__(self):
        self._init_tables()

    def _get_conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_tables(self):
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operation_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT UNIQUE,
                    context_json TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT,
                    operation TEXT,
                    date TEXT,
                    summary TEXT,
                    findings_count INTEGER DEFAULT 0
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # Layer 2 — Operational Context
    def store_operational(self, conv_id, context: dict):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO operation_context (conversation_id, context_json, updated_at) VALUES (?, ?, ?)",
                (conv_id, json.dumps(context, ensure_ascii=False), datetime.utcnow().isoformat())
            )
            conn.commit()
        finally:
            conn.close()

    def get_operational(self, conv_id) -> dict:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT context_json FROM operation_context WHERE conversation_id = ?",
                (conv_id,)
            ).fetchone()
            if row:
                return json.loads(row["context_json"])
            return {}
        finally:
            conn.close()

    def merge_operational(self, conv_id, updates: dict):
        current = self.get_operational(conv_id)
        current.update(updates)
        self.store_operational(conv_id, current)

    # Layer 3 — Historical Operations
    def store_historical(self, target, operation, summary, findings_count=0):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO operation_history (target, operation, date, summary, findings_count) VALUES (?, ?, ?, ?, ?)",
                (target, operation, datetime.utcnow().isoformat(), summary, findings_count)
            )
            conn.commit()
        finally:
            conn.close()

    def get_history(self, target) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, target, operation, date, summary, findings_count FROM operation_history WHERE target = ? ORDER BY date DESC",
                (target,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # Layer 1 — Smart Summary
    def needs_summary(self, conv_id, threshold=50) -> bool:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ?",
                (conv_id,)
            ).fetchone()
            count = row["cnt"] if row else 0
            return count > 0 and count % threshold == 0
        finally:
            conn.close()

    def generate_summary(self, messages_text: str, llama_generate_fn) -> str:
        prompt = (
            "Resume la siguiente conversación de forma concisa en español, "
            "extrayendo los puntos clave, decisiones tomadas y hallazgos importantes:\n\n"
            f"{messages_text}"
        )
        return llama_generate_fn(prompt, temperature=0.3)
