import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Incident

ALERT_LOG = Path("data/defense/alerts.log")


class AlertManager:
    def __init__(self):
        self._webhooks: list[str] = []
        self._telegram_callback = None

    def set_telegram_callback(self, cb):
        self._telegram_callback = cb

    def add_webhook(self, url: str):
        if url not in self._webhooks:
            self._webhooks.append(url)

    def send(self, incident: Incident, channel: str = "all"):
        msg = self._format_alert(incident)
        ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ALERT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")
        if channel in ("all", "telegram") and self._telegram_callback:
            try:
                self._telegram_callback(msg)
            except Exception:
                pass
        if channel in ("all", "webhook"):
            for url in self._webhooks:
                try:
                    import urllib.request
                    import urllib.parse
                    data = json.dumps({"text": msg}).encode()
                    urllib.request.urlopen(url, data=data, timeout=5)
                except Exception:
                    pass

    @staticmethod
    def _format_alert(incident: Incident) -> str:
        icon = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
        return (
            f"{icon.get(incident.severity, 'ℹ️')} {incident.attack_type.upper()}\n"
            f"Severity: {incident.severity.upper()}\n"
            f"Source: {incident.source_ip}\n"
            f"Target: {incident.target}\n"
            f"Time: {incident.timestamp}\n"
            f"Status: {incident.status}"
        )
