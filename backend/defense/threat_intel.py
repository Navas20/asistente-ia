import json
import os
import urllib.request

from .models import ThreatIntelResult


class ThreatIntel:
    def __init__(self):
        self._abuse_key = os.getenv("ABUSEIPDB_API_KEY", "")
        self._shodan_key = os.getenv("SHODAN_API_KEY", "")
        self._vt_key = os.getenv("VIRUSTOTAL_API_KEY", "")

    def lookup(self, ip: str) -> ThreatIntelResult:
        result = ThreatIntelResult(ip=ip)
        geo = self._ip_api(ip)
        if geo:
            result.isp = geo.get("isp")
            result.country = geo.get("country")
            result.asn = geo.get("as")
        abuse = self._abuseipdb(ip)
        if abuse:
            result.abuse_reports = abuse.get("totalReports", 0)
            result.confidence = abuse.get("abuseConfidenceScore", 0)
        if self._shodan_key:
            shodan = self._shodan(ip)
            if shodan:
                result.open_ports = shodan.get("ports", [])
        return result

    def _ip_api(self, ip: str) -> dict | None:
        try:
            url = f"http://ip-api.com/json/{ip}?fields=status,country,isp,as,query"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read().decode())
                if data.get("status") == "success":
                    return data
        except Exception:
            pass
        return None

    def _abuseipdb(self, ip: str) -> dict | None:
        if not self._abuse_key:
            return None
        try:
            url = f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}&maxAgeInDays=90"
            req = urllib.request.Request(url, headers={"Key": self._abuse_key, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                return data.get("data")
        except Exception:
            pass
        return None

    def _shodan(self, ip: str) -> dict | None:
        if not self._shodan_key:
            return None
        try:
            url = f"https://api.shodan.io/shodan/host/{ip}?key={self._shodan_key}"
            with urllib.request.urlopen(url, timeout=5) as r:
                return json.loads(r.read().decode())
        except Exception:
            pass
        return None
