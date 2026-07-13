import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .models import Incident, ResponseRule

BLOCK_FILE = Path("data/defense_blocks.txt")


class AutoResponder:
    def __init__(self):
        self._blocks: dict[str, float] = {}
        self._load_blocks()

    def _load_blocks(self):
        if BLOCK_FILE.exists():
            now = time.time()
            lines = BLOCK_FILE.read_text(encoding="utf-8").splitlines()
            for line in lines:
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    ip, expires = parts[0], float(parts[1])
                    if expires > now:
                        self._blocks[ip] = expires

    def _save_blocks(self):
        BLOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{ip}|{exp}" for ip, exp in self._blocks.items()]
        BLOCK_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def block_ip(self, ip: str, duration: int = 3600) -> str:
        expires = time.time() + duration
        self._blocks[ip] = expires
        self._save_blocks()
        if sys.platform == "win32":
            cmd = f'netsh advfirewall firewall add rule name="Artenisa_Block_{ip}" dir=in action=block remoteip={ip}'
        else:
            cmd = f"iptables -A INPUT -s {ip} -j DROP"
        try:
            subprocess.run(shlex.split(cmd), capture_output=True, timeout=10)
            return f"Blocked {ip} for {duration}s"
        except Exception as e:
            return f"Failed to block {ip}: {e}"

    def unblock_ip(self, ip: str) -> str:
        self._blocks.pop(ip, None)
        self._save_blocks()
        if sys.platform == "win32":
            cmd = f'netsh advfirewall firewall delete rule name="Artenisa_Block_{ip}"'
        else:
            cmd = f"iptables -D INPUT -s {ip} -j DROP"
        try:
            subprocess.run(shlex.split(cmd), capture_output=True, timeout=10)
            return f"Unblocked {ip}"
        except Exception as e:
            return f"Failed to unblock {ip}: {e}"

    def list_blocks(self) -> list[dict]:
        now = time.time()
        result = []
        expired = []
        for ip, exp in self._blocks.items():
            remaining = int(exp - now)
            if remaining <= 0:
                expired.append(ip)
            else:
                result.append({"ip": ip, "expires_in": remaining})
        for ip in expired:
            del self._blocks[ip]
        if expired:
            self._save_blocks()
        return result

    def is_blocked(self, ip: str) -> bool:
        exp = self._blocks.get(ip)
        if exp and exp > time.time():
            return True
        if exp:
            del self._blocks[ip]
            self._save_blocks()
        return False

    def respond(self, incident: Incident, rule: ResponseRule | None = None) -> str:
        if rule is None:
            rule = ResponseRule(incident_type=incident.attack_type, action="notify", auto=False)
        if rule.action == "block_ip":
            msg = self.block_ip(incident.source_ip, rule.duration)
            incident.status = "blocked"
            incident.blocked_at = datetime.now(timezone.utc).isoformat()
            return msg
        elif rule.action == "notify":
            return f"Alert: {incident.attack_type} from {incident.source_ip}"
        return f"No action taken for {incident.attack_type}"
