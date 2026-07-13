import re
from .models import Finding
from .cvss import cvss_score, DEFAULT_VECTORS


def extract_findings(tool: str, output: str, host: str = "", phase: str = "") -> list[Finding]:
    extractors = {
        "scan_ports": _extract_ports,
        "dns_enum": _extract_dns,
        "subdomain_scan": _extract_subdomains,
        "whois_lookup": _extract_whois,
        "cert_transparency": _extract_cert,
        "ip_geo": _extract_geo,
        "email_osint": _extract_email,
        "detect_tech": _extract_tech,
        "dir_bruteforce": _extract_dirs,
        "ssl_check": _extract_ssl,
        "check_sqli": _extract_sqli,
        "check_xss": _extract_xss,
        "check_lfi": _extract_lfi,
        "reverse_shell": _extract_payload,
        "hash_crack": _extract_crack,
    }
    extractor = extractors.get(tool)
    if extractor:
        return extractor(output, host, phase, tool)
    return []


def _make_finding(title: str, severity: str, host: str, phase: str, tool: str,
                  evidence: str = "", port: int | None = None,
                  service: str | None = None, description: str = "") -> Finding:
    vec = DEFAULT_VECTORS.get(severity)
    score = cvss_score(vec) if vec else None
    return Finding(
        title=title,
        description=description or title,
        severity=severity,
        cvss_vector=vec,
        cvss_score=score,
        host=host,
        port=port,
        service=service,
        tool=tool,
        phase=phase,
        evidence=evidence[:500],
        status="raw",
    )


def _extract_ports(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        m = re.match(r".*?(?:Puerto|Port)\s*(\d+).*?(?:abierto|open).*?(?:en|on)\s*(\S+)?", line, re.I)
        if m:
            port = int(m.group(1))
            svc = m.group(2) or ""
            findings.append(_make_finding(
                f"Open port {port}/{svc} on {host}",
                "info", host, phase, tool,
                evidence=line.strip(), port=port, service=svc
            ))
    if not findings:
        for line in output.splitlines():
            m = re.match(r"\s*(\d+)/(tcp|udp)\s+(\S+)", line)
            if m:
                port, proto, state = int(m.group(1)), m.group(2), m.group(3)
                if "open" in state:
                    findings.append(_make_finding(
                        f"Open port {port}/{proto} on {host}",
                        "info", host, phase, tool,
                        evidence=line.strip(), port=port, service=proto
                    ))
    return findings


def _extract_dns(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        m = re.search(r"(A|AAAA|MX|NS|TXT|SOA|CNAME)\s+[=:]\s*(.+)", line, re.I)
        if m:
            findings.append(_make_finding(
                f"DNS {m.group(1).upper()} record: {m.group(2).strip()}",
                "info", host, phase, tool, evidence=line.strip()
            ))
    return findings


def _extract_subdomains(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        m = re.search(r"([\w.-]+\.(?:com|org|net|io|app|dev|xyz|tech|online))\s*", line, re.I)
        if m and host in m.group(1):
            findings.append(_make_finding(
                f"Subdomain found: {m.group(1)}",
                "info", host, phase, tool, evidence=line.strip()
            ))
    return findings


def _extract_whois(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    return [_make_finding(f"WHOIS data for {host}", "info", host, phase, tool, evidence=output[:300])]


def _extract_cert(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    return [_make_finding(f"Certificate for {host}", "info", host, phase, tool, evidence=output[:300])]


def _extract_geo(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    return [_make_finding(f"Geo location for {host}", "info", host, phase, tool, evidence=output[:300])]


def _extract_email(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    return [_make_finding(f"Email intel for {host}", "info", host, phase, tool, evidence=output[:300])]


def _extract_tech(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        m = re.search(r"(detect(?:ed|ó)|encontr(?:ado|ó)|found)\s*[:\s]+(.+)", line, re.I)
        if m:
            findings.append(_make_finding(
                f"Technology detected: {m.group(2).strip()}",
                "info", host, phase, tool, evidence=line.strip()
            ))
    return findings


def _extract_dirs(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        m = re.search(r"(/\S+)\s+.*?(\d{3})", line)
        if m:
            path, code = m.group(1), int(m.group(2))
            sev = "low" if code == 200 else "info"
            findings.append(_make_finding(
                f"Directory found: {path} ({code})",
                sev, host, phase, tool, evidence=line.strip()
            ))
    return findings


def _extract_ssl(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    issues = []
    for line in output.splitlines():
        low = line.lower()
        for kw in ["expir", "invalid", "self-signed", "untrusted", "weak", "error"]:
            if kw in low:
                issues.append(line.strip())
    if issues:
        findings.append(_make_finding(
            f"SSL issue on {host}",
            "medium", host, phase, tool,
            evidence="\n".join(issues[:5])
        ))
    if not findings:
        findings.append(_make_finding(
            f"SSL certificate for {host}",
            "info", host, phase, tool, evidence=output[:300]
        ))
    return findings


def _extract_sqli(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for kw in ["vulnerable", "SQL", "error", "syntax", "mysql", "unclosed"]:
        if kw.lower() in output.lower():
            findings.append(_make_finding(
                f"SQL Injection detected in {host}",
                "critical", host, phase, tool, evidence=output[:500]
            ))
            break
    return findings


def _extract_xss(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for kw in ["vulnerable", "xss", "alert", "reflected", "script"]:
        if kw.lower() in output.lower():
            findings.append(_make_finding(
                f"XSS detected in {host}",
                "high", host, phase, tool, evidence=output[:500]
            ))
            break
    return findings


def _extract_lfi(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for kw in ["vulnerable", "lfi", "path", "traversal", "root:", "etc/passwd"]:
        if kw.lower() in output.lower():
            findings.append(_make_finding(
                f"LFI detected in {host}",
                "high", host, phase, tool, evidence=output[:500]
            ))
            break
    return findings


def _extract_payload(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    return [_make_finding(
        f"Payload generated for {host}",
        "info", host, phase, tool, evidence=output[:300]
    )]


def _extract_crack(output: str, host: str, phase: str, tool: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        m = re.search(r"(hash|cracked|found|match)[\s:]+(\S+)", line, re.I)
        if m:
            findings.append(_make_finding(
                f"Hash cracked: {m.group(2)[:50]}",
                "medium", host, phase, tool, evidence=line.strip()
            ))
    return findings
