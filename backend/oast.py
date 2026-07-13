import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
import urllib.request

OAST_FILE = Path("data/oast_interactions.json")
OAST_URL = "https://oast.fun"
USE_LOCAL = False


class OASTManager:
    def __init__(self):
        self._interactions: list[dict] = []
        self._load()

    def _load(self):
        if OAST_FILE.exists():
            try:
                self._interactions = json.loads(OAST_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        OAST_FILE.parent.mkdir(parents=True, exist_ok=True)
        OAST_FILE.write_text(json.dumps(self._interactions, indent=2), encoding="utf-8")

    def generate_payload(self, payload_type: str = "ssrf") -> str:
        uid = uuid.uuid4().hex[:8]
        domain = "oast.fun"
        if payload_type == "ssrf":
            return f"http://{uid}.{domain}/artenisa/{uid}"
        elif payload_type == "dns":
            return f"{uid}.{domain}"
        elif payload_type == "xss":
            return f"<img src=http://{uid}.{domain}/xss/{uid}>"
        return f"http://{uid}.{domain}/{payload_type}/{uid}"

    def poll(self) -> list[dict]:
        if USE_LOCAL:
            return self._interactions
        try:
            url = f"https://{OAST_URL}/interactions"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read().decode())
                new = data if isinstance(data, list) else data.get("interactions", [])
                for item in new:
                    if item not in self._interactions:
                        self._interactions.append(item)
                self._save()
        except Exception:
            pass
        return self._interactions

    def check(self, payload_id: str) -> list[dict]:
        return [i for i in self._interactions if payload_id in str(i)]
