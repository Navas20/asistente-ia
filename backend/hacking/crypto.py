import logging
import re
import base64
import hashlib
import itertools

log = logging.getLogger("artenisa.crypto")

HASH_PATTERNS = [
    (re.compile(r"^\$2[aby]\d{1,2}\$[A-Za-z0-9./]{53}$"), "bcrypt"),
    (re.compile(r"^\$5\$[A-Za-z0-9./]{43}$"), "SHA256-Crypt"),
    (re.compile(r"^\$6\$[A-Za-z0-9./]{86}$"), "SHA512-Crypt"),
    (re.compile(r"^\*[0-9A-F]{40}$", re.IGNORECASE), "MySQL5"),
    (re.compile(r"^[0-9a-f]{16}$", re.IGNORECASE), "MySQL3"),
    (re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE), "MD5"),
    (re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE), "SHA1"),
    (re.compile(r"^[0-9a-f]{56}$", re.IGNORECASE), "SHA224"),
    (re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE), "SHA256"),
    (re.compile(r"^[0-9a-f]{96}$", re.IGNORECASE), "SHA384"),
    (re.compile(r"^[0-9a-f]{128}$", re.IGNORECASE), "SHA512"),
    (re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE), "NTLM"),
]

COMMON_PASSWORDS = [
    "123456", "password", "12345678", "qwerty", "123456789",
    "12345", "1234", "111111", "1234567", "sunshine",
    "qwerty123", "admin", "letmein", "monkey", "dragon",
    "football", "iloveyou", "trustno1", "welcome", "master",
    "shadow", "passw0rd", "abc123", "hello", "charlie",
    "princess", "superman", "batman", "starwars", "696969",
]

def hash_id(hash_str: str) -> list:
    results = []
    for pattern, name in HASH_PATTERNS:
        if pattern.match(hash_str):
            results.append({"type": name, "length": len(hash_str)})
    if not results:
        return [{"type": "desconocido", "length": len(hash_str)}]
    return results

def hash_crack(hash_str: str, wordlist: list = None) -> dict:
    if wordlist is None:
        wordlist = COMMON_PASSWORDS
    identified = hash_id(hash_str)
    algo = identified[0]["type"] if identified else "desconocido"
    result = {"hash": hash_str, "identified": identified, "cracked": False, "plaintext": None, "algorithm": algo}
    for word in wordlist:
        if algo == "MD5" and hashlib.md5(word.encode()).hexdigest() == hash_str:
            result["cracked"] = True
            result["plaintext"] = word
            break
        if algo == "SHA1" and hashlib.sha1(word.encode()).hexdigest() == hash_str:
            result["cracked"] = True
            result["plaintext"] = word
            break
        if algo == "SHA224" and hashlib.sha224(word.encode()).hexdigest() == hash_str:
            result["cracked"] = True
            result["plaintext"] = word
            break
        if algo == "SHA256" and hashlib.sha256(word.encode()).hexdigest() == hash_str:
            result["cracked"] = True
            result["plaintext"] = word
            break
        if algo == "SHA384" and hashlib.sha384(word.encode()).hexdigest() == hash_str:
            result["cracked"] = True
            result["plaintext"] = word
            break
        if algo == "SHA512" and hashlib.sha512(word.encode()).hexdigest() == hash_str:
            result["cracked"] = True
            result["plaintext"] = word
            break
    return result

def encode_b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()

def decode_b64(text: str) -> str:
    try:
        return base64.b64decode(text).decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error decodificando: {e}"

def generate_wordlist(base: str = "", length: int = 4) -> list:
    if not base:
        base = "abcdefghijklmnopqrstuvwxyz0123456789"
    result = []
    for i in range(1, length + 1):
        for combo in itertools.product(base, repeat=i):
            result.append("".join(combo))
    return result
