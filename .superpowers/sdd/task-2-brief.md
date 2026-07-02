# Task 2: Hacking Tools Module

## Files to Create (all under `backend/hacking/`)
- `__init__.py`
- `network.py`
- `web.py`
- `crypto.py`
- `payloads.py`
- `osint.py`

## `__init__.py`
Re-export all public functions from submodules:
```python
from .network import scan_ports, banner_grab, dns_enum, subdomain_scan, whois_lookup
from .web import dir_bruteforce, detect_tech, check_sqli, check_xss, check_lfi, ssl_check
from .crypto import hash_id, hash_crack, decode_b64, encode_b64
from .payloads import reverse_shell, webshell, encode_payload
from .osint import ip_geo, email_osint, cert_transparency

__all__ = [ ... all function names ... ]
```

## `network.py`

Functions:
- `scan_ports(host: str, ports: str = "1-1024", timeout: float = 2.0, max_workers: int = 50) -> dict`
  - Multithreaded TCP connect scan
  - Returns `{target, total_scanned, open_count, open_ports: [{port, service, open, banner}]}`
  - Use `COMMON_PORTS` dict mapping port -> service name
  - Resolve hostname first
  - Parse ports string: "1-1024", "22,80,443", or single "80"

- `banner_grab(host: str, port: int, timeout: float = 3.0) -> str`
  - Connect, send "HEAD / HTTP/1.0\r\n\r\n", read up to 1024 bytes
  - For port 443, wrap with SSL context (check_hostname=False, verify_mode=CERT_NONE)

- `dns_enum(domain: str) -> dict`
  - Query A, AAAA, MX, NS, TXT, SOA, CNAME records using dnspython (`dns.resolver.resolve`)
  - Return dict with record type → list of strings

- `subdomain_scan(domain: str, wordlist: list = None) -> list`
  - Default wordlist: www, mail, admin, blog, ftp, api, dev, test, webmail, panel, git, jenkins, ssh, docs, support, backup, db, mysql, cpanel
  - Multithreaded resolution via `socket.getaddrinfo`
  - Return sorted list of found subdomains

- `whois_lookup(target: str) -> str`
  - `subprocess.run(["whois", target], timeout=15)`, capture_output
  - Return stdout[:2000] or stderr[:2000]
  - Return "whois no instalado" if FileNotFoundError

## `web.py`

Functions:
- `detect_tech(url: str) -> dict` — headers + body fingerprinting (Server, X-Powered-By, WordPress/jQuery/React/Laravel/Django patterns in body)
- `check_sqli(url: str, param: str) -> dict` — test error-based + time-based payloads, detect SQL errors in response
- `check_xss(url: str, param: str) -> dict` — inject script/img/svg payloads, check if reflected in response
- `check_lfi(url: str, param: str) -> dict` — ../../etc/passwd payloads, check for system file content
- `dir_bruteforce(url: str, wordlist: list = None) -> dict` — default 25 common dirs, multithreaded, return found with status codes
- `ssl_check(host: str, port: int = 443) -> dict` — cert info, cipher, version

All use `urllib.request` for HTTP calls. No external deps beyond stdlib + ssl.

## `crypto.py`

Functions:
- `hash_id(hash_str: str) -> list` — regex patterns for MD5, SHA1, SHA224/256/384/512, bcrypt, SHA256-Crypt, SHA512-Crypt, MySQL, etc.
- `hash_crack(hash_str: str, wordlist: list = None) -> dict` — try common passwords against md5/sha1/sha256/sha512, return `{hash, identified, cracked, plaintext, algorithm}`
- `encode_b64(text: str) -> str`
- `decode_b64(text: str) -> str`
- `generate_wordlist(base: str = "", length: int = 4) -> list`

## `payloads.py`

Functions:
- `reverse_shell(ip: str, port: int, shell_type: str = "bash") -> dict` — return `{type, payload, encoded_b64, listener}` for bash/python/php/powershell/nc
- `webshell(lang: str = "php") -> dict` — return `{language, payload, encoded_url, usage}` for php/asp/aspx/jsp/py
- `encode_payload(payload: str, method: str = "b64") -> dict` — b64/hex/url/unicode encoding

## `osint.py`

Functions:
- `ip_geo(ip: str) -> dict` — call ip-api.com/json/{ip}, parse JSON response
- `email_osint(email: str) -> dict` — extract domain, reference HaveIBeenPwned
- `cert_transparency(domain: str) -> list` — call crt.sh/?q={domain}&output=json, return sorted unique subdomains

## Global Constraints
- Must work on Windows 10/11 without WSL
- Python 3.10+ compatible only
- All user-facing text in Spanish
- No external paid services required
- Add `dnspython>=2.6.0` as dependency (for dns_enum)
- Every file must be importable without side effects at module level
