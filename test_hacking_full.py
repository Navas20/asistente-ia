import sys; sys.path.insert(0, 'backend')
import json

PASS = 0
FAIL = 0

def test(name, fn, *args, **kw):
    global PASS, FAIL
    try:
        result = fn(*args, **kw)
        if result is not None:
            print(f"  [OK] {name}")
            PASS += 1
        else:
            print(f"  [FAIL] {name} - returned None")
            FAIL += 1
    except Exception as e:
        print(f"  [FAIL] {name} - {e}")
        FAIL += 1

def show(label, data):
    s = json.dumps(data, indent=2, default=str)
    if len(s) > 600:
        s = s[:600] + "..."
    print(f"       {label}: {s}")

print("=" * 60)
print("1. NETWORK")
print("=" * 60)
from hacking.network import (
    scan_ports, banner_grab, dns_enum, subdomain_scan, whois_lookup,
    get_local_ip, scan_local_network, scan_wifi_networks
)

test("get_local_ip", get_local_ip)
res = get_local_ip()
for i in res.get("interfaces", []):
    show(f"  {i['name']}", f"{i['ip']}/{i['netmask']}")

test("scan_wifi_networks", scan_wifi_networks)
res = scan_wifi_networks()
show("WiFi", [n.get("ssid") for n in res.get("networks", [])])

test("scan_local_network", scan_local_network)
res = scan_local_network()
devices = [d for d in res.get("devices", []) if d.get("ip").count(".") == 3 and not d["ip"].endswith(".255")]
show("Devices", [f"{d['ip']} ({d.get('hostname','?')})" for d in devices[:5]])

test("scan_ports (localhost 1-100)", scan_ports, "127.0.0.1", "1-100")
res = scan_ports("127.0.0.1", "1-100")
show("Open ports", [f"{p['port']}/{p['service']}" for p in res.get("open_ports", [])])

test("dns_enum", dns_enum, "example.com")
res = dns_enum("example.com")
show("DNS A", res.get("A", [])[:3])
show("DNS MX", res.get("MX", [])[:3])

test("subdomain_scan", subdomain_scan, "example.com")
res = subdomain_scan("example.com")
subdomains = res.get("found", []) if isinstance(res, dict) else res
show("Subdomains", subdomains[:5])

test("whois_lookup", whois_lookup, "example.com")
res = whois_lookup("example.com")
show("Whois", res[:200])

print()
print("=" * 60)
print("2. WEB")
print("=" * 60)
from hacking.web import detect_tech, check_sqli, check_xss, check_lfi, ssl_check, dir_bruteforce

test("detect_tech", detect_tech, "https://example.com")
res = detect_tech("https://example.com")
show("Tech", res.get("technologies", []))

test("ssl_check", ssl_check, "example.com", 443)
res = ssl_check("example.com", 443)
show("SSL", f"{res.get('subject','')} / {res.get('issuer','')}")

test("dir_bruteforce", dir_bruteforce, "https://example.com")
res = dir_bruteforce("https://example.com")
show("Dirs found", res.get("found", []))

print()
print("=" * 60)
print("3. CRYPTO")
print("=" * 60)
from hacking.crypto import hash_id, hash_crack, encode_b64, decode_b64, generate_wordlist

test("encode_b64", encode_b64, "hola_mundo")
res = encode_b64("hola_mundo")
show("b64", res)

test("decode_b64", decode_b64, "aG9sYV9tdW5kbw==")
res = decode_b64("aG9sYV9tdW5kbw==")
show("decoded", res)

test("hash_id (MD5)", hash_id, "5d41402abc4b2a76b9719d911017c592")
res = hash_id("5d41402abc4b2a76b9719d911017c592")
show("Hash type", res[:3])

test("hash_id (bcrypt)", hash_id, "$2b$12$LJ3m4ys3Lk0TSwHnOTsNcOoQvF.E.oQ9lN1k2q3Yq4r5s6t7u8v9")
res = hash_id("$2b$12$LJ3m4ys3Lk0TSwHnOTsNcOoQvF.E.oQ9lN1k2q3Yq4r5s6t7u8v9")
show("Hash type", res[:3])

test("hash_crack (MD5 simple)", hash_crack, "5d41402abc4b2a76b9719d911017c592")
res = hash_crack("5d41402abc4b2a76b9719d911017c592")
show("Crack result", res.get("result", ""))

print()
print("=" * 60)
print("4. PAYLOADS")
print("=" * 60)
from hacking.payloads import reverse_shell, webshell, encode_payload

test("reverse_shell", reverse_shell, "127.0.0.1", 4444, "bash")
res = reverse_shell("127.0.0.1", 4444, "bash")
show("Shell", res.get("decoded", "")[:100])

test("reverse_shell (powershell)", reverse_shell, "127.0.0.1", 4444, "powershell")
res = reverse_shell("127.0.0.1", 4444, "powershell")
show("PS Shell", res.get("decoded", "")[:100])

test("webshell", webshell, "php")
res = webshell("php")
show("Webshell", res.get("decoded", "")[:100])

test("encode_payload (hex)", encode_payload, "test", "hex")
res = encode_payload("test", "hex")
show("Hex", res.get("encoded", ""))

test("encode_payload (url)", encode_payload, "hola mundo", "url")
res = encode_payload("hola mundo", "url")
show("URL", res.get("encoded", ""))

print()
print("=" * 60)
print("5. OSINT")
print("=" * 60)
from hacking.osint import ip_geo, cert_transparency

test("ip_geo", ip_geo, "8.8.8.8")
res = ip_geo("8.8.8.8")
show("Geo", f"{res.get('country','')} / {res.get('isp','')}")

test("cert_transparency", cert_transparency, "example.com")
res = cert_transparency("example.com")
show("Subdomains", res[:5])

print()
print("=" * 60)
print(f"RESULT: {PASS} passed, {FAIL} failed")
print("=" * 60)
