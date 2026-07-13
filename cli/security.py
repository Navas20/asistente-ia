import os
import base64
import hashlib

HACX_DIR = os.path.expanduser("~/.artenisa")

def _get_machine_id() -> str:
    try:
        if sys.platform == "win32":
            import subprocess
            result = subprocess.run(
                ["wmic", "csproduct", "get", "UUID"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line and "UUID" not in line and len(line) > 10:
                    return line
        elif os.path.exists("/etc/machine-id"):
            return open("/etc/machine-id").read().strip()
        elif os.path.exists("/var/lib/dbus/machine-id"):
            return open("/var/lib/dbus/machine-id").read().strip()
    except Exception:
        pass
    return hashlib.sha256(os.path.expanduser("~").encode()).hexdigest()[:16]

def _derive_key() -> bytes:
    mid = _get_machine_id()
    return hashlib.pbkdf2_hmac("sha256", mid.encode(), b"artenisa-salt", 100000, 32)

def encrypt(text: str) -> str:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    key = base64.urlsafe_b64encode(_derive_key())
    f = Fernet(key)
    return f.encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(_derive_key())
    f = Fernet(key)
    return f.decrypt(token.encode()).decode()

def save_key(provider: str, api_key: str):
    os.makedirs(HACX_DIR, exist_ok=True)
    enc = encrypt(api_key)
    path = os.path.join(HACX_DIR, f"{provider}.key")
    with open(path, "w") as f:
        f.write(enc)

def load_key(provider: str) -> str:
    path = os.path.join(HACX_DIR, f"{provider}.key")
    if os.path.exists(path):
        with open(path) as f:
            return decrypt(f.read().strip())
    return ""

def list_saved_providers() -> list:
    if not os.path.exists(HACX_DIR):
        return []
    return sorted(f.replace(".key", "") for f in os.listdir(HACX_DIR) if f.endswith(".key"))

import sys
