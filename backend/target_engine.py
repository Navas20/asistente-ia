import os
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("artenisa.target")

TARGET_FILE = Path(__file__).parent / "data" / "target_state.json"


class TargetEngine:

    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        if TARGET_FILE.exists():
            try:
                self._data = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, FileNotFoundError):
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        TARGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        TARGET_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def set_target(self, user_id: int, target: str, target_type: str = "domain"):
        key = str(user_id)
        self._data[key] = {
            "target": target,
            "target_type": target_type,
            "set_at": datetime.utcnow().isoformat(),
            "operation": self._data.get(key, {}).get("operation", ""),
        }
        self._save()

    def get_target(self, user_id: int) -> dict:
        entry = self._data.get(str(user_id))
        if not entry:
            return {}
        elapsed = 0
        if "set_at" in entry:
            set_at = datetime.fromisoformat(entry["set_at"])
            elapsed = int((datetime.utcnow() - set_at).total_seconds() / 60)
        return {
            "target": entry["target"],
            "target_type": entry["target_type"],
            "set_at": entry["set_at"],
            "operation": entry.get("operation", ""),
            "elapsed_minutes": elapsed,
        }

    def clear_target(self, user_id: int):
        self._data.pop(str(user_id), None)
        self._save()

    def set_operation(self, user_id: int, operation: str):
        key = str(user_id)
        if key not in self._data:
            self._data[key] = {}
        self._data[key]["operation"] = operation
        self._save()

    def get_context_summary(self, user_id: int) -> str:
        entry = self._data.get(str(user_id))
        if not entry or "target" not in entry:
            return ""
        target = entry["target"]
        operation = entry.get("operation", "")
        elapsed = 0
        if "set_at" in entry:
            set_at = datetime.fromisoformat(entry["set_at"])
            elapsed = int((datetime.utcnow() - set_at).total_seconds() / 60)
        parts = [f"🎯 Objetivo: {target}"]
        if operation:
            parts.append(f"📁 {operation[:20]}")
        parts.append(f"⏱️ {elapsed} min")
        return " | ".join(parts)
