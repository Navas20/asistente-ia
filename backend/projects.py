import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path("data/projects.json")


class ProjectManager:
    def __init__(self):
        self._projects: list[dict] = []
        self._active_id: str | None = None
        self._load()

    def _load(self):
        if DATA_FILE.exists():
            try:
                data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                self._projects = data.get("projects", [])
                self._active_id = data.get("active_id")
            except Exception:
                pass

    def _save(self):
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps({"projects": self._projects, "active_id": self._active_id}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create(self, name: str, target: str = "", description: str = "") -> dict:
        project = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "target": target,
            "description": description,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "findings_count": 0,
            "sessions_count": 0,
            "notes": "",
        }
        self._projects.append(project)
        self._save()
        return project

    def list(self) -> list[dict]:
        return list(self._projects)

    def get(self, project_id: str) -> dict | None:
        for p in self._projects:
            if p["id"] == project_id:
                return p
        return None

    def update(self, project_id: str, data: dict) -> dict | None:
        for p in self._projects:
            if p["id"] == project_id:
                for k, v in data.items():
                    if k in ("name", "target", "description", "status", "notes"):
                        p[k] = v
                p["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return p
        return None

    def delete(self, project_id: str) -> bool:
        for i, p in enumerate(self._projects):
            if p["id"] == project_id:
                self._projects.pop(i)
                if self._active_id == project_id:
                    self._active_id = None
                self._save()
                return True
        return False

    def set_active(self, project_id: str) -> dict | None:
        p = self.get(project_id)
        if p:
            self._active_id = project_id
            self._save()
            return p
        return None

    def get_active(self) -> dict | None:
        if self._active_id:
            return self.get(self._active_id)
        return None

    def clear_active(self):
        self._active_id = None
        self._save()

    def add_finding(self, project_id: str):
        for p in self._projects:
            if p["id"] == project_id:
                p["findings_count"] = p.get("findings_count", 0) + 1
                self._save()
                return
