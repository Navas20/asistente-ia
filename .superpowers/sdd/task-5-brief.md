# Task 5: Security Controls

## File
Create: `backend/security.py`

## Classes

### AuditLog
- `__init__`: Create `audit_log` table in SQLite at `DB_PATH` env var (default `data/conversations.db`):
  ```sql
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
  ```
- `log(user_id, username, command, target="", status="ok", details="")` — INSERT row
- `get_recent(limit=20) -> list` — SELECT * ORDER BY id DESC LIMIT ?

Each method opens/closes its own connection.

### RateLimiter
- `__init__`: Initialize `_buckets: dict` and `_lock: threading.Lock()`
- `check(key: str, max_calls: int = 10, window: int = 60) -> tuple`:
  - Returns `(allowed: bool, remaining: int, reset_after: int)`
  - Sliding window: keep timestamps within last `window` seconds
  - If blocked_until > now, return false
  - If len(calls) >= max_calls, set blocked_until = now + 30, return false
  - Else append now, clean old calls, return true with remaining

### Role system (module-level functions)
- `ALLOWED_USER_IDS = [...]` parsed from `ALLOWED_USER_IDS` or `ALLOWED_USER_ID` env var
- `ADMIN_IDS = [...]` parsed from `ADMIN_IDS` env var
- `get_role(user_id: int) -> str` — returns "admin" if in ADMIN_IDS, "operator" if in ALLOWED_USER_IDS, "denied" otherwise. If no IDs configured (value is 0 or empty), return "admin"
- `require_role(min_role: str = "operator")` — decorator that checks role, returns `{"error": "No autorizado"}` if denied, `{"error": "Se requiere rol admin"}` if insufficient

## Global Constraints
- Windows compatible
- Python 3.10+
- Spanish user-facing text
- Importable without side effects
- Only stdlib + sqlite3
