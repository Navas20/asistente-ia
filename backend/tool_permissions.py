import logging
import os
import sqlite3
import threading

log = logging.getLogger("artenisa.tool_permissions")

DB_PATH = os.getenv("DB_PATH", "data/conversations.db")

_PENDING: dict = {}
_PENDING_LOCK = threading.Lock()
_READY = False

_AUDIT = None
_AUDIT_LOCK = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_ready() -> None:
    global _READY
    if not _READY:
        init_permissions()
        _READY = True


def init_permissions() -> None:
    """Crea las tablas y siembra las herramientas de TOOL_SPECS que falten.

    Todo corre directo salvo que el usuario indique lo contrario
    (requires_confirmation=0 por defecto)."""
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_permissions (
                tool_name TEXT PRIMARY KEY,
                requires_confirmation BOOLEAN DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        # Import lazy para evitar ciclo: tool_permissions -> tools_engine.
        from tools_engine import TOOL_SPECS

        for name in TOOL_SPECS:
            conn.execute(
                "INSERT OR IGNORE INTO tool_permissions (tool_name, requires_confirmation) VALUES (?, 0)",
                (name,),
            )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('agent_mode', 'build')"
        )
        conn.commit()
    except Exception:
        log.exception("Error inicializando permisos de herramientas")
        raise
    finally:
        conn.close()


def get_permission(tool_name: str) -> bool:
    _ensure_ready()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT requires_confirmation FROM tool_permissions WHERE tool_name = ?",
            (tool_name,),
        ).fetchone()
        return bool(row["requires_confirmation"]) if row else False
    finally:
        conn.close()


def set_permission(tool_name: str, requires_confirmation: bool) -> None:
    _ensure_ready()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO tool_permissions (tool_name, requires_confirmation) VALUES (?, ?) "
            "ON CONFLICT(tool_name) DO UPDATE SET requires_confirmation = excluded.requires_confirmation",
            (tool_name, int(bool(requires_confirmation))),
        )
        conn.commit()
    finally:
        conn.close()


def list_permissions() -> list[dict]:
    _ensure_ready()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT tool_name, requires_confirmation FROM tool_permissions ORDER BY tool_name"
        ).fetchall()
        return [
            {"tool_name": r["tool_name"], "requires_confirmation": bool(r["requires_confirmation"])}
            for r in rows
        ]
    finally:
        conn.close()


def get_agent_mode() -> str:
    _ensure_ready()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'agent_mode'").fetchone()
        return row["value"] if row else "build"
    finally:
        conn.close()


def set_agent_mode(mode: str) -> str:
    _ensure_ready()
    mode = mode if mode in ("plan", "build") else "build"
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('agent_mode', ?)",
            (mode,),
        )
        conn.commit()
    finally:
        conn.close()
    return mode


def needs_confirmation(tool_name: str) -> bool:
    """Regla global: en modo plan TODO pide confirmación; si no, se respeta
    la config individual de la herramienta."""
    return get_agent_mode() == "plan" or get_permission(tool_name)


def _audit() -> object:
    global _AUDIT
    if _AUDIT is None:
        with _AUDIT_LOCK:
            if _AUDIT is None:
                from security import AuditLog

                _AUDIT = AuditLog()
    return _AUDIT


def audit_intent(intent: dict, status: str, details: str = "") -> None:
    """Registra en el AuditLog qué se propuso y si se confirmó o rechazó."""
    try:
        _audit().log(
            intent.get("user_id", 0),
            "",
            intent.get("tool") or intent.get("command", ""),
            intent.get("target", ""),
            status=status,
            details=details or intent.get("proposal", ""),
        )
    except Exception:
        log.warning("No se pudo auditar la acción: %s", status)


# ── Confirmaciones pendientes (en memoria, keyed por owner) ──


def propose(owner, intent: dict) -> None:
    with _PENDING_LOCK:
        _PENDING[owner] = intent
    audit_intent(intent, "proposed")


def get_pending(owner):
    with _PENDING_LOCK:
        return _PENDING.get(owner)


def has_pending(owner) -> bool:
    with _PENDING_LOCK:
        return owner in _PENDING


def resolve_pending(owner, confirmed: bool):
    with _PENDING_LOCK:
        intent = _PENDING.pop(owner, None)
    if intent is None:
        return None
    audit_intent(intent, "confirmed" if confirmed else "rejected")
    return intent