import json
import logging
import os
import time
import httpx
from typing import Any

log = logging.getLogger("artenisa.tools_engine")

KALI_BASE_URL = os.getenv("KALI_TOOLS_URL", "http://artenisa-kali-tools:9001")
DEFAULT_TIMEOUT = 300

TOOL_TIMEOUTS = {
    "nmap": 300,
    "whois": 10,
    "dig": 10,
    "nslookup": 5,
    "curl": 30,
    "ping": 15,
}

TOOL_SCAN_TYPES = {
    "quick": ["-T4", "-F"],
    "normal": ["-sV", "-sC"],
    "full": ["-sV", "-sC", "-A", "-p-"],
    "vuln": ["-sV", "--script", "vuln"],
}

BLOCKED_RANGES = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "255.255.255.255/32",
]


class ToolResult:
    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        parsed: dict | None = None,
        elapsed: float = 0.0,
        truncated: bool = False,
        error: str = "",
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.parsed = parsed
        self.elapsed = elapsed
        self.truncated = truncated
        self.error = error

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout[:500] if self.stdout else "",
            "stderr": self.stderr[:500] if self.stderr else "",
            "exit_code": self.exit_code,
            "parsed": self.parsed,
            "elapsed": self.elapsed,
            "truncated": self.truncated,
            "error": self.error,
        }


import ipaddress


def validate_target(target: str) -> str | None:
    """Valida target. Retorna mensaje de error si es inválido, None si es válido."""
    target = target.strip()

    import re
    domain_pattern = re.compile(
        r"^([a-zA-Z0-9]([-a-zA-Z0-9]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    )
    if domain_pattern.match(target):
        if target.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
            return f"Target '{target}' no permitido"
        return None

    try:
        ip = ipaddress.ip_address(target)
    except ValueError:
        try:
            ip = ipaddress.ip_network(target, strict=False)
            for blocked in BLOCKED_RANGES:
                if ip.overlaps(ipaddress.ip_network(blocked)):
                    return f"Rango '{target}' está en rango bloqueado: {blocked}"
            return None
        except ValueError:
            return f"Target '{target}' no es una IP o dominio válido"

    if ip.is_private:
        return f"IP privada '{target}' no permitida"
    if ip.is_loopback:
        return f"Loopback '{target}' no permitido"
    if ip.is_reserved:
        return f"IP reservada '{target}' no permitida"
    if ip.is_multicast:
        return f"Multicast '{target}' no permitido"

    for blocked in BLOCKED_RANGES:
        if ip in ipaddress.ip_network(blocked):
            return f"IP '{target}' está en rango bloqueado: {blocked}"

    return None


class ToolsEngine:
    def __init__(self, base_url: str = KALI_BASE_URL):
        self.base_url = base_url
        self._client = httpx.Client(
            base_url=base_url,
            timeout=30,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._active_tasks: dict[str, float] = {}
        self._concurrent_per_user: dict[int, int] = {}
        log.info("ToolsEngine initialized, Kali URL: %s", base_url)

    def _check_per_user_limit(self, user_id: int) -> str | None:
        now = time.time()
        self._concurrent_per_user[user_id] = sum(
            1 for t in self._active_tasks.values() if now - t < 300
        )
        if self._concurrent_per_user.get(user_id, 0) >= 3:
            return "Límite de 3 herramientas simultáneas por usuario alcanzado"
        return None

    def run_nmap(
        self,
        target: str,
        scan_type: str = "normal",
        extra_args: list[str] | None = None,
        timeout: int | None = None,
        user_id: int = 0,
    ) -> ToolResult:
        error = validate_target(target)
        if error:
            return ToolResult(success=False, error=error)

        limit_error = self._check_per_user_limit(user_id)
        if limit_error:
            return ToolResult(success=False, error=limit_error)

        args = TOOL_SCAN_TYPES.get(scan_type, TOOL_SCAN_TYPES["normal"])
        args = list(args)
        if extra_args:
            args.extend(extra_args)
        args.extend([target])

        actual_timeout = timeout or TOOL_TIMEOUTS.get("nmap", DEFAULT_TIMEOUT)

        payload = {
            "tool": "nmap",
            "args": args,
            "timeout": actual_timeout,
            "task_id": f"nmap_{user_id}_{int(time.time())}",
        }

        self._active_tasks[payload["task_id"]] = time.time()

        try:
            resp = self._client.post("/run", json=payload, timeout=actual_timeout + 5)
            resp.raise_for_status()
            data = resp.json()
            return ToolResult(
                success=data.get("success", False),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
                exit_code=data.get("exit_code", -1),
                parsed=data.get("parsed"),
                elapsed=data.get("elapsed", 0),
                truncated=data.get("truncated", False),
            )
        except httpx.ConnectError:
            return ToolResult(
                success=False,
                error=f"No se pudo conectar con Kali Tools Server en {self.base_url}. ¿El contenedor está corriendo?",
            )
        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                error=f"Timeout de conexión con Kali ({actual_timeout}s)",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Error HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            log.exception("Error in run_nmap")
            return ToolResult(success=False, error=str(e))
        finally:
            self._active_tasks.pop(payload["task_id"], None)

    def health(self) -> bool:
        try:
            resp = self._client.get("/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


tools_engine = ToolsEngine()
