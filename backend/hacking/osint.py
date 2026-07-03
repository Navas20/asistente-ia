import logging
import json
import urllib.request
import urllib.error
import ssl

log = logging.getLogger("artenisa.osint")

def _fetch_json(url: str, timeout: float = 10.0) -> dict | list:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        log.warning(f"HTTP {e.code} fetching {url}")
        return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        log.warning(f"URL error fetching {url}: {e.reason}")
        return {"error": f"Error de conexion: {e.reason}"}
    except json.JSONDecodeError as e:
        log.warning(f"JSON error from {url}: {e}")
        return {"error": "Respuesta JSON invalida"}
    except Exception as e:
        log.warning(f"Error fetching {url}: {e}")
        return {"error": str(e)}

def ip_geo(ip: str) -> dict:
    data = _fetch_json(f"http://ip-api.com/json/{ip}")
    if isinstance(data, dict) and data.get("status") == "success":
        return {
            "ip": data.get("query", ip),
            "pais": data.get("country", ""),
            "region": data.get("regionName", ""),
            "ciudad": data.get("city", ""),
            "zip": data.get("zip", ""),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "isp": data.get("isp", ""),
            "org": data.get("org", ""),
            "as": data.get("as", ""),
            "timezone": data.get("timezone", ""),
        }
    if isinstance(data, dict) and "error" in data:
        return data
    return {"error": "No se pudo obtener geolocalizacion"}

def email_osint(email: str) -> dict:
    if "@" not in email:
        return {"error": "Email invalido, debe contener @"}
    parts = email.split("@", 1)
    username = parts[0]
    domain = parts[1].lower()
    result = {
        "email": email,
        "username": username,
        "domain": domain,
        "mx_records": [],
        "hibp_reference": f"https://haveibeenpwned.com/account/{email}",
        "dominio_info": {},
    }
    try:
        import dns.resolver
        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=5)
            result["mx_records"] = [str(r.exchange) for r in answers]
        except Exception:
            result["mx_records"] = []
    except ImportError:
        result["mx_records"] = ["dnspython no instalado"]
    try:
        data = _fetch_json(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=8)
        if isinstance(data, list):
            unique = sorted(set(item["name_value"].strip() for item in data if "name_value" in item))
            result["dominio_info"]["subdominios_cert"] = unique[:50]
            result["dominio_info"]["total_certs"] = len(data)
    except (json.JSONDecodeError, urllib.error.URLError, urllib.error.HTTPError):
        pass
    return result

def cert_transparency(domain: str) -> list:
    data = _fetch_json(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=10)
    if isinstance(data, list):
        subdomains = set()
        for item in data:
            name = item.get("name_value", "")
            for n in name.split("\n"):
                n = n.strip().lower()
                if n and n.endswith(domain):
                    subdomains.add(n)
        return sorted(subdomains)
    if isinstance(data, dict) and "error" in data:
        return [f"Error: {data['error']}"]
    return []
