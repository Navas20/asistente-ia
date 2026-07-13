import re
import time
from collections import defaultdict

from .models import Incident, LogSource

RATE_WINDOW = 60
RATE_LIMITS = {
    "brute_force_ssh": 5,
    "brute_force_http": 10,
    "port_scan": 10,
    "path_bruteforce": 20,
    "rate_limit": 100,
}


class AttackDetector:
    def __init__(self):
        self._counters: dict[str, dict] = defaultdict(lambda: defaultdict(list))

    def analyze(self, source: LogSource, line: str) -> Incident | None:
        if source.type == "auth":
            return self._check_auth(line)
        elif source.type == "nginx_access":
            return self._check_nginx(line)
        elif source.type == "syslog":
            return self._check_syslog(line)
        return self._check_custom(line)

    def _check_auth(self, line: str) -> Incident | None:
        m = re.search(r"Failed password.*from\s+(\S+)", line)
        if m:
            ip = m.group(1)
            return self._rate_check("brute_force_ssh", ip, line, "SSH brute force", "critical")
        m = re.search(r"Connection closed.*from\s+(\S+)", line)
        if m:
            ip = m.group(1)
            return self._rate_check("brute_force_ssh", ip, line, "SSH connection anomaly", "medium")
        return None

    def _check_nginx(self, line: str) -> Incident | None:
        m = re.match(r"(\S+).*?\"(?:GET|POST)\s+(\S+).*?\"\s+(\d+)", line)
        if not m:
            return None
        ip = m.group(1)
        path = m.group(2)
        status = int(m.group(3))

        if status in (401, 403):
            return self._rate_check("brute_force_http", ip, line, f"HTTP brute force to {path}", "high")
        if status == 404:
            return self._rate_check("path_bruteforce", ip, line, f"Path discovery: {path}", "low")

        low_path = path.lower()
        for pat, name in [
            (r"union.*select", "SQLi"),
            (r"or\s+1=1", "SQLi"),
            (r"--", "SQLi"),
            (r"<script", "XSS"),
            (r"onerror\s*=", "XSS"),
            (r"alert\s*\(", "XSS"),
            (r"\.\./", "Directory Traversal"),
            (r"%2e%2e", "Directory Traversal"),
            (r"\.\.\\", "Directory Traversal"),
        ]:
            if re.search(pat, low_path):
                sev = "critical" if name == "SQLi" else "high"
                return Incident(
                    attack_type=name.lower().replace(" ", "_"),
                    severity=sev,
                    source_ip=ip,
                    target=path,
                    log_snippet=line[:300],
                )
        suspicious_ua = ["sqlmap", "nikto", "nuclei", "gobuster", "dirbuster", "nmap"]
        ua_match = re.search(r'"([^"]*)"\s*"([^"]*)"', line)
        if ua_match:
            ua = ua_match.group(2).lower()
            for s in suspicious_ua:
                if s in ua:
                    return Incident(
                        attack_type="suspicious_ua",
                        severity="medium",
                        source_ip=ip,
                        target=path,
                        log_snippet=line[:300],
                    )
        return None

    def _check_syslog(self, line: str) -> Incident | None:
        return None

    def _check_custom(self, line: str) -> Incident | None:
        return None

    def _rate_check(self, atype: str, ip: str, line: str, title: str, sev: str) -> Incident | None:
        now = time.time()
        key = f"{atype}:{ip}"
        times = self._counters[key]
        times.append(now)
        cutoff = now - RATE_WINDOW
        self._counters[key] = [t for t in times if t > cutoff]
        count = len(self._counters[key])
        threshold = RATE_LIMITS.get(atype, 5)
        if count >= threshold:
            return Incident(
                attack_type=atype,
                severity=sev,
                source_ip=ip,
                target=title,
                count=count,
                log_snippet=line[:300],
            )
        return None
