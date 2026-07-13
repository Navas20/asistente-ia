"""
DATA LAYER - Repositorios y acceso a datos
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.config import DB_PATH, UPLOAD_DIR, REPORTS_DIR, AUDIO_DIR


class DatabaseConnection:
    """Gestor de conexiones SQLite con WAL mode"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
    
    def get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn
    
    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class ConversationRepository:
    """Repositorio de conversaciones"""
    
    def __init__(self):
        self.db = DatabaseConnection()
        self._init_table()
    
    def _init_table(self):
        conn = self.db.get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                tool_output TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()
    
    def add_message(self, conv_id: str, role: str, content: str, tool_output: Optional[str] = None):
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_output, timestamp) VALUES (?, ?, ?, ?, ?)",
            (conv_id, role, content, tool_output, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    
    def get_messages(self, conv_id: str, limit: int = 20) -> List[Dict]:
        conn = self.db.get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conv_id, limit)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]


class MemoryRepository:
    """Repositorio de memoria (3 capas)"""
    
    def __init__(self):
        self.db = DatabaseConnection()
        self._init_tables()
    
    def _init_tables(self):
        conn = self.db.get_conn()
        
        # Layer 2: Operational Context
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operation_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT UNIQUE,
                context_json TEXT,
                updated_at TEXT
            )
        """)
        
        # Layer 3: Historical Operations
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
    
    def store_operational(self, conv_id: str, context: Dict):
        conn = self.db.get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO operation_context (conversation_id, context_json, updated_at) VALUES (?, ?, ?)",
            (conv_id, json.dumps(context, ensure_ascii=False), datetime.utcnow().isoformat())
        )
        conn.commit()
    
    def get_operational(self, conv_id: str) -> Dict:
        conn = self.db.get_conn()
        row = conn.execute(
            "SELECT context_json FROM operation_context WHERE conversation_id = ?",
            (conv_id,)
        ).fetchone()
        return json.loads(row["context_json"]) if row else {}
    
    def store_historical(self, target: str, operation: str, summary: str, findings_count: int = 0):
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO operation_history (target, operation, date, summary, findings_count) VALUES (?, ?, ?, ?, ?)",
            (target, operation, datetime.utcnow().isoformat(), summary, findings_count)
        )
        conn.commit()
    
    def get_history(self, target: str) -> List[Dict]:
        conn = self.db.get_conn()
        rows = conn.execute(
            "SELECT * FROM operation_history WHERE target = ? ORDER BY date DESC",
            (target,)
        ).fetchall()
        return [dict(row) for row in rows]


class FileRepository:
    """Repositorio de archivos"""
    
    def __init__(self):
        self.db = DatabaseConnection()
        self.upload_dir = UPLOAD_DIR
        self._init_table()
    
    def _init_table(self):
        conn = self.db.get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT,
                original_name TEXT,
                size INTEGER,
                uploaded_at TEXT
            )
        """)
        conn.commit()
    
    def register_file(self, file_id: str, filename: str, original_name: str, size: int):
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO files (id, filename, original_name, size, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (file_id, filename, original_name, size, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    
    def get_file(self, file_id: str) -> Optional[Dict]:
        conn = self.db.get_conn()
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return dict(row) if row else None


class AuditRepository:
    """Repositorio de auditoría"""
    
    def __init__(self):
        self.db = DatabaseConnection()
        self._init_table()
    
    def _init_table(self):
        conn = self.db.get_conn()
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
    
    def log(self, user_id: int, username: str, command: str, target: str = "", 
            status: str = "ok", details: str = ""):
        conn = self.db.get_conn()
        conn.execute(
            "INSERT INTO audit_log (user_id, username, command, target, timestamp, status, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, command, target, datetime.now(timezone.utc).isoformat(), status, details)
        )
        conn.commit()
    
    def get_recent(self, limit: int = 20) -> List[Dict]:
        conn = self.db.get_conn()
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


class TaskRepository:
    """Repositorio de tareas (JSON-based)"""
    
    def __init__(self):
        self.tasks_file = Path(UPLOAD_DIR).parent / "tasks.json"
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        if self.tasks_file.exists():
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._tasks = data.get("tasks", {})
                self._queue = data.get("queue", [])
        else:
            self._tasks = {}
            self._queue = []
    
    def _save(self):
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump({"tasks": self._tasks, "queue": self._queue}, f, indent=2, ensure_ascii=False)
    
    def add_task(self, task_id: str, task_data: Dict):
        with self._lock:
            self._tasks[task_id] = task_data
            self._queue.append(task_id)
            self._save()
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        with self._lock:
            return self._tasks.get(task_id)
    
    def update_task(self, task_id: str, updates: Dict):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(updates)
                self._save()
    
    def list_tasks(self, limit: int = 10) -> List[Dict]:
        with self._lock:
            sorted_tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.get("created_at", ""),
                reverse=True
            )
            return sorted_tasks[:limit]
