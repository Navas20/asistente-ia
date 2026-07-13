from .engine import FindingsManager

CRITICAL_KEYWORDS = [
    "sql injection", "sqli", "union select",
    "xss", "cross-site", "alert(",
    "lfi", "path traversal", "etc/passwd",
    "rce", "remote code", "command injection",
]

HIGH_CONFIDENCE_KEYWORDS = [
    "open port", "dns record", "whois",
    "technology detected", "subdomain found",
]


def auto_review() -> dict:
    fm = FindingsManager()
    findings = fm.list(status="raw", limit=200)
    reviewed = {"verified": [], "dismissed": [], "total": 0}
    for f in findings:
        low = (f.title + " " + f.evidence).lower()
        is_critical = any(kw in low for kw in CRITICAL_KEYWORDS)
        is_high_conf = any(kw in low for kw in HIGH_CONFIDENCE_KEYWORDS)
        if is_critical:
            fm.update_status(f.id, "verified")
            reviewed["verified"].append(f.id)
        elif is_high_conf:
            fm.update_status(f.id, "verified")
            reviewed["verified"].append(f.id)
        elif f.severity == "info":
            fm.update_status(f.id, "verified")
            reviewed["verified"].append(f.id)
        else:
            fm.update_status(f.id, "dismissed")
            reviewed["dismissed"].append(f.id)
        reviewed["total"] += 1
    return reviewed
