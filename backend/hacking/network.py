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
    completed = []
    failures = []
    try:
        import dns.resolver
    except ImportError:
        return {"error": "dnspython no instalado. Ejecuta: pip install dnspython"}
    for rtype in record_types:
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=5)
            result[rtype] = [str(r) for r in answers]
            completed.append(rtype)
        except dns.resolver.NoAnswer:
            result[rtype] = []
            completed.append(rtype)
        except dns.resolver.NXDOMAIN:
            return {"error": f"Dominio {domain} no existe"}
        except Exception as e:
            log.debug(f"DNS {rtype} error: {e}")
            result[rtype] = []
            failures.append((rtype, str(e).strip() or type(e).__name__))
    if failures:
        result["failed_record_types"] = [rtype for rtype, _ in failures]
        result["completed_record_types"] = completed
        result["partial"] = bool(completed)
        result["warnings"] = [
            f"DNS {rtype}: {detail}" for rtype, detail in failures
        ]
        if not completed:
            result["error"] = f"Fallo de resolucion DNS: {failures[0][1]}"
    return result

def subdomain_scan(domain: str, wordlist: list = None) -> list | dict:
    if wordlist is None:
        wordlist = ["www", "mail", "admin", "blog", "ftp", "api", "dev", "test",
                     "webmail", "panel", "git", "jenkins", "ssh", "docs", "support",
                     "backup", "db", "mysql", "cpanel"]
    found = []
    completed = 0
    failures = []
    not_found_codes = {
        code
        for code in (
            getattr(socket, "EAI_NONAME", None),
            getattr(socket, "EAI_NODATA", None),
        )
        if code is not None
    }

    def _check(sub: str) -> tuple[str | None, str | None]:
        hostname = f"{sub}.{domain}"
        try:
            socket.getaddrinfo(hostname, 80, socket.AF_INET, socket.SOCK_STREAM)
            return hostname, None
        except socket.gaierror as e:
            if e.errno in not_found_codes:
                return None, None
            return None, f"{hostname}: {str(e).strip() or type(e).__name__}"
        except OSError as e:
            return None, f"{hostname}: {str(e).strip() or type(e).__name__}"
    with ThreadPoolExecutor(max_workers=20) as executor:
        futuros = {executor.submit(_check, s): s for s in wordlist}
        for fut in as_completed(futuros):
            r, failure = fut.result()
            if r:
                found.append(r)
            if failure:
                failures.append(failure)
            else:
                completed += 1
    found = sorted(found)
    if failures:
        result = {
            "target": domain,
            "found": found,
            "completed_lookups": completed,
            "failed_lookups": len(failures),
            "partial": bool(completed),
            "warnings": failures,
        }
        if not completed:
            result["error"] = (
                f"Fallo de resolucion de subdominios: {failures[0]}"
            )
        return result
    return found

def get_local_ip(_target: str | None = None) -> dict:
    """Obtiene IP local, subred y gateway de todas las interfaces activas."""
    interfaces = []
    default_gateway = None

    def _val(line):
        return line.split(":", 1)[-1].strip() if ": " in line else ""

    try:
        r = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=15)
        current = None
        for line in r.stdout.splitlines():
            raw = line
            line = line.strip()
            if not line:
                continue
            if "Adaptador de " in raw:
                if current and current.get("ip"):
                    interfaces.append(current)
                name = raw.split("Adaptador de ", 1)[-1].split(":")[0].strip()
                current = {"name": name, "ip": "", "netmask": "", "gateway": ""}
                continue
            if current is None:
                continue
            if "Direcci" in line and "IPv4" in line:
                current["ip"] = _val(line)
            elif "subred" in line.lower():
                current["netmask"] = _val(line)
            elif "Puerta de enlace" in line:
                gw = _val(line)
                if gw:
                    default_gateway = gw
                    current["gateway"] = gw
        if current and current.get("ip"):
            interfaces.append(current)

        interfaces = [i for i in interfaces if not i["ip"].startswith("127.") and i["ip"]]
    except Exception:
        pass

    if not interfaces:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            interfaces = [{"name": "default", "ip": local_ip, "netmask": "", "gateway": ""}]
        except Exception as e:
            return {"error": str(e), "interfaces": []}

    return {
        "interfaces": interfaces,
        "default_gateway": default_gateway,
    }

def _is_reachable_subnet(ip: str) -> bool:
    """Filtra subredes no escaneables: loopback, APIPA, multicast."""
    try:
        first = int(ip.split(".")[0])
        if first == 127 or first >= 224:
            return False
        if first == 169 and ip.split(".")[1] == "254":
            return False
        return True
    except (ValueError, IndexError):
        return False

def scan_local_network(timeout: float = 0.3) -> dict:
    """Escanea la red local con ping sweep y ARP para descubrir dispositivos."""
    local_info = get_local_ip()
    if "error" in local_info:
        return local_info

    devices = []
    arp_ips = set()

    try:
        arp = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
        for line in arp.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0].count(".") == 3:
                ip = parts[0]
                mac = parts[1]
                arp_ips.add(ip)
                first_octet = int(ip.split(".")[0])
                hostname = ""
                if first_octet not in (0, 127, 169, 224, 239, 255) and not ip.endswith(".255"):
                    try:
                        hostname = socket.gethostbyaddr(ip)[0]
                    except Exception:
                        pass
                devices.append({"ip": ip, "hostname": hostname, "mac": mac, "source": "arp"})
    except Exception:
        pass

    for iface in local_info.get("interfaces", []):
        ip = iface.get("ip", "")
        netmask = iface.get("netmask", "")
        if not ip or not netmask or not _is_reachable_subnet(ip):
            continue

        try:
            ip_parts = list(map(int, ip.split(".")))
            mask_parts = list(map(int, netmask.split(".")))
            network = [ip_parts[i] & mask_parts[i] for i in range(4)]
            broadcast = [network[i] | (~mask_parts[i] & 0xFF) for i in range(4)]
            if broadcast[3] < 2:
                continue
        except (ValueError, IndexError):
            continue

        max_hosts = min(broadcast[3] - 1, 254)
        hosts = [f"{network[0]}.{network[1]}.{network[2]}.{i}" for i in range(1, max_hosts + 1)
                 if f"{network[0]}.{network[1]}.{network[2]}.{i}" not in arp_ips]

        if not hosts:
            continue

        def _ping(host: str) -> str | None:
            try:
                r = subprocess.run(
                    ["ping", "-n", "1", "-w", str(max(100, int(timeout * 1000))), host],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    return host
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=50) as ex:
            futuros = {ex.submit(_ping, h): h for h in hosts}
            for fut in as_completed(futuros):
                r = fut.result()
                if r:
                    first_octet = int(r.split(".")[0])
                    hostname = ""
                    if first_octet not in (0, 127, 169, 224, 239, 255) and not r.endswith(".255"):
                        try:
                            hostname = socket.gethostbyaddr(r)[0]
                        except Exception:
                            pass
                    devices.append({"ip": r, "hostname": hostname, "interface": iface["name"]})

    return {
        "local": local_info,
        "devices": devices,
        "total": len(devices),
    }

def scan_wifi_networks(_target: str | None = None) -> dict:
    """Lista redes WiFi disponibles usando netsh (Windows)."""
    try:
        r = subprocess.run(
            ["netsh", "wlan", "show", "networks"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode != 0:
            return {"error": "No se pudo escanear WiFi. ¿Está habilitado el adaptador?", "raw": r.stderr.strip()}
        
        networks = []
        current = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID"):
                if current:
                    networks.append(current)
                current = {"ssid": "", "signal": "", "auth": "", "type": ""}
                if ": " in line:
                    current["ssid"] = line.split(": ", 1)[1].strip()
            elif "BSSID" in line and ": " in line:
                current["bssid"] = line.split(": ", 1)[1].strip()
            elif "Tipo de radio" in line and ": " in line:
                current["type"] = line.split(": ", 1)[1].strip()
            elif "Autenticaci" in line and ": " in line:
                current["auth"] = line.split(": ", 1)[1].strip()
            elif "Se" in line and "al" in line and ": " in line:
                current["signal"] = line.split(": ", 1)[1].strip()
        if current:
            networks.append(current)

        return {
            "networks": networks,
            "total": len(networks),
        }
    except FileNotFoundError:
        return {"error": "netsh no disponible (no es Windows o está bloqueado)"}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout escaneando redes WiFi"}
    except Exception as e:
        return {"error": str(e)}

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
