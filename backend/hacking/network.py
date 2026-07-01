import logging
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger("artenisa.network")

COMMON_PORTS = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 111: "rpcbind", 135: "msrpc",
    139: "netbios-ssn", 143: "imap", 443: "https", 445: "microsoft-ds",
    993: "imaps", 995: "pop3s", 1433: "mssql", 1521: "oracle",
    2049: "nfs", 3306: "mysql", 3389: "rdp", 5432: "postgresql",
    5900: "vnc", 5985: "winrm-http", 5986: "winrm-https",
    6379: "redis", 8080: "http-proxy", 8443: "https-alt",
    27017: "mongodb",
}

def _parse_ports(ports: str) -> list:
    ports = ports.strip()
    if not ports:
        return []
    if "," in ports:
        result = []
        for part in ports.split(","):
            result.extend(_parse_ports(part.strip()))
        return sorted(set(result))
    if "-" in ports:
        a, b = ports.split("-", 1)
        return list(range(int(a.strip()), int(b.strip()) + 1))
    return [int(ports)]

def _scan_port(host: str, port: int, timeout: float) -> dict:
    result = {"port": port, "service": COMMON_PORTS.get(port, ""), "open": False, "banner": ""}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        code = sock.connect_ex((host, port))
        if code == 0:
            result["open"] = True
            try:
                if port == 443:
                    import ssl
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    with context.wrap_socket(sock, server_hostname=host) as ssock:
                        ssock.settimeout(timeout)
                        ssock.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
                        result["banner"] = ssock.recv(1024).decode("utf-8", errors="replace").strip()[:200]
                else:
                    sock.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
                    result["banner"] = sock.recv(1024).decode("utf-8", errors="replace").strip()[:200]
            except (socket.timeout, ConnectionError, OSError):
                pass
            finally:
                sock.close()
        else:
            sock.close()
    except (socket.timeout, socket.gaierror, ConnectionError, OSError) as e:
        log.debug(f"Error scanning {host}:{port}: {e}")
    return result

def scan_ports(host: str, ports: str = "1-1024", timeout: float = 2.0, max_workers: int = 50) -> dict:
    port_list = _parse_ports(ports)
    try:
        target = socket.gethostbyname(host)
    except socket.gaierror:
        return {"target": host, "error": "No se pudo resolver el hostname", "open_ports": []}
    open_ports = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {executor.submit(_scan_port, target, p, timeout): p for p in port_list}
        for fut in as_completed(futuros):
            r = fut.result()
            if r["open"]:
                open_ports.append(r)
    open_ports.sort(key=lambda x: x["port"])
    return {
        "target": host,
        "ip": target,
        "total_scanned": len(port_list),
        "open_count": len(open_ports),
        "open_ports": open_ports,
    }

def banner_grab(host: str, port: int, timeout: float = 3.0) -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        if port == 443:
            import ssl
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                ssock.settimeout(timeout)
                ssock.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
                return ssock.recv(1024).decode("utf-8", errors="replace").strip()
        else:
            sock.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
            return sock.recv(1024).decode("utf-8", errors="replace").strip()
    except (socket.timeout, socket.gaierror, ConnectionError, OSError) as e:
        return f"Error: {e}"
    finally:
        try:
            sock.close()
        except NameError:
            pass

def dns_enum(domain: str) -> dict:
    record_types = ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"]
    result = {}
    try:
        import dns.resolver
    except ImportError:
        return {"error": "dnspython no instalado. Ejecuta: pip install dnspython"}
    for rtype in record_types:
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=5)
            result[rtype] = [str(r) for r in answers]
        except dns.resolver.NoAnswer:
            result[rtype] = []
        except dns.resolver.NXDOMAIN:
            return {"error": f"Dominio {domain} no existe"}
        except Exception as e:
            log.debug(f"DNS {rtype} error: {e}")
            result[rtype] = []
    return result

def subdomain_scan(domain: str, wordlist: list = None) -> list:
    if wordlist is None:
        wordlist = ["www", "mail", "admin", "blog", "ftp", "api", "dev", "test",
                     "webmail", "panel", "git", "jenkins", "ssh", "docs", "support",
                     "backup", "db", "mysql", "cpanel"]
    found = []
    def _check(sub: str) -> str | None:
        try:
            socket.getaddrinfo(f"{sub}.{domain}", 80, socket.AF_INET, socket.SOCK_STREAM)
            return f"{sub}.{domain}"
        except (socket.gaierror, OSError):
            return None
    with ThreadPoolExecutor(max_workers=20) as executor:
        futuros = {executor.submit(_check, s): s for s in wordlist}
        for fut in as_completed(futuros):
            r = fut.result()
            if r:
                found.append(r)
    return sorted(found)

def whois_lookup(target: str) -> str:
    try:
        r = subprocess.run(["whois", target], capture_output=True, text=True, timeout=15)
        return (r.stdout or r.stderr)[:2000]
    except FileNotFoundError:
        return "whois no instalado"
    except subprocess.TimeoutExpired:
        return "Timeout en la consulta whois"
    except Exception as e:
        return f"Error: {e}"
