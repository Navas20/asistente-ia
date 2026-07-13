import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Finding, FindingSummary

DB_PATH = Path("data/artenisa.db")


def _get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _ensure_table(conn)
    return conn


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            severity TEXT DEFAULT 'info',
            cvss_vector TEXT,
            cvss_score REAL,
            host TEXT DEFAULT '',
            port INTEGER,
            service TEXT,
            tool TEXT DEFAULT '',
            phase TEXT DEFAULT '',
            evidence TEXT DEFAULT '',
            status TEXT DEFAULT 'raw',
            cve_ids TEXT DEFAULT '[]',
            tags TEXT DEFAULT '[]',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    for col in ("host", "severity", "status", "phase", "tool", "created_at"):
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_findings_{col} ON findings({col})")
    conn.commit()


class FindingsManager:
    def __init__(self):
        self._db = _get_db

    def _conn(self):
        return self._db()

    def save(self, finding: Finding) -> Finding:
        conn = self._conn()
        row = conn.execute("SELECT id FROM findings WHERE id=?", (finding.id,)).fetchone()
        finding.updated_at = datetime.now(timezone.utc).isoformat()
        data = finding.model_dump()
        data["cve_ids"] = json.dumps(data["cve_ids"])
        data["tags"] = json.dumps(data["tags"])
        if row:
            cols = ", ".join(f"{k}=?" for k in data)
            conn.execute(f"UPDATE findings SET {cols} WHERE id=?", list(data.values()) + [finding.id])
        else:
            cols = ", ".join(data.keys())
            vals = ", ".join("?" for _ in data)
            conn.execute(f"INSERT INTO findings ({cols}) VALUES ({vals})", list(data.values()))
        conn.commit()
        return finding

    def get(self, finding_id: str) -> Finding | None:
        row = self._conn().execute("SELECT * FROM findings WHERE id=?", (finding_id,)).fetchone()
        return self._row_to_finding(row) if row else None

    def list(self, host: str | None = None, severity: str | None = None,
             status: str | None = None, phase: str | None = None,
             tool: str | None = None, limit: int = 100, offset: int = 0) -> list[Finding]:
        query = "SELECT * FROM findings WHERE 1=1"
        params = []
        if host:
            query += " AND host=?"
            params.append(host)
        if severity:
            query += " AND severity=?"
            params.append(severity)
        if status:
            query += " AND status=?"
            params.append(status)
        if phase:
            query += " AND phase=?"
            params.append(phase)
        if tool:
            query += " AND tool=?"
            params.append(tool)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn().execute(query, params).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def summary(self) -> FindingSummary:
        rows = self._conn().execute(
            "SELECT severity, COUNT(*) as cnt FROM findings GROUP BY severity"
        ).fetchall()
        s = FindingSummary()
        for r in rows:
            sev = r["severity"]
            cnt = r["cnt"]
            s.total += cnt
            if sev == "critical":
                s.critical = cnt
            elif sev == "high":
                s.high = cnt
            elif sev == "medium":
                s.medium = cnt
            elif sev == "low":
                s.low = cnt
            elif sev == "info":
                s.info = cnt
        phase_rows = self._conn().execute(
            "SELECT phase, COUNT(*) as cnt FROM findings GROUP BY phase"
        ).fetchall()
        for r in phase_rows:
            s.by_phase[r["phase"]] = r["cnt"]
        return s

    def update_status(self, finding_id: str, status: str) -> bool:
        conn = self._conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "UPDATE findings SET status=?, updated_at=? WHERE id=?", (status, now, finding_id)
        )
        conn.commit()
        return cur.rowcount > 0

    def delete(self, finding_id: str) -> bool:
        conn = self._conn()
        cur = conn.execute("DELETE FROM findings WHERE id=?", (finding_id,))
        conn.commit()
        return cur.rowcount > 0

    def clear(self, host: str | None = None, phase: str | None = None):
        conn = self._conn()
        query = "DELETE FROM findings WHERE 1=1"
        params = []
        if host:
            query += " AND host=?"
            params.append(host)
        if phase:
            query += " AND phase=?"
            params.append(phase)
        conn.execute(query, params)
        conn.commit()

    def exists(self, title: str, host: str) -> bool:
        row = self._conn().execute(
            "SELECT id FROM findings WHERE title=? AND host=?", (title, host)
        ).fetchone()
        return row is not None

    def export(self, fmt: str = "json") -> str:
        findings = self.list(limit=9999)
        if fmt == "json":
            return json.dumps([f.model_dump() for f in findings], indent=2, ensure_ascii=False)
        elif fmt == "csv":
            lines = ["id,title,severity,host,port,tool,phase,status"]
            for f in findings:
                lines.append(f"{f.id},{f.title},{f.severity},{f.host},{f.port or ''},{f.tool},{f.phase},{f.status}")
            return "\n".join(lines)
        else:
            lines = [f"# Findings Report\n", f"Total: {len(findings)}\n"]
            for f in findings:
                lines.append(f"## {f.title}")
                lines.append(f"- **Severity**: {f.severity}")
                lines.append(f"- **Host**: {f.host}")
                lines.append(f"- **Tool**: {f.tool}")
                lines.append(f"- **Status**: {f.status}")
                if f.evidence:
                    lines.append(f"```\n{f.evidence}\n```")
                lines.append("")
            return "\n".join(lines)

    @staticmethod
    def _row_to_finding(row: sqlite3.Row) -> Finding:
        d = dict(row)
        d["cve_ids"] = json.loads(d.get("cve_ids", "[]"))
        d["tags"] = json.loads(d.get("tags", "[]"))
        return Finding(**d)
