import math

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]


def severity_from_score(score: float | None) -> str:
    if score is None:
        return "info"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score >= 1.0:
        return "low"
    return "info"


DEFAULT_VECTORS = {
    "critical": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    "high": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:L",
    "medium": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:L",
    "low": "CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N",
}


def cvss_score(vector: str) -> float:
    parts = {}
    for token in vector.replace("CVSS:3.1/", "").split("/"):
        if ":" in token:
            k, v = token.split(":", 1)
            parts[k] = v

    def _v(name: str) -> str:
        return parts.get(name, "X")

    av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}.get(_v("AV"), 1.0)
    ac = {"L": 0.77, "H": 0.44}.get(_v("AC"), 1.0)
    pr = {"N": 0.85, "L": 0.62, "H": 0.27}.get(_v("PR"), 1.0)
    ui = {"N": 0.85, "R": 0.62}.get(_v("UI"), 1.0)
    s = _v("S")
    c = {"H": 0.56, "L": 0.22}.get(_v("C"), 0.0)
    i = {"H": 0.56, "L": 0.22}.get(_v("I"), 0.0)
    a_val = {"H": 0.56, "L": 0.22}.get(_v("A"), 0.0)

    iss = 1.0 - (1.0 - c) * (1.0 - i) * (1.0 - a_val)
    impact = 6.42 * iss if s == "N" else 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
    exploitability = 8.22 * av * ac * pr * ui
    if impact <= 0:
        return 0.0
    if s == "N":
        return round(min(1.08 * (impact + exploitability), 10.0), 1)
    return round(min(impact + exploitability, 10.0), 1)
