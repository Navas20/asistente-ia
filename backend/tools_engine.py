import json
import ipaddress
import logging
import os
import socket
import time
import uuid
import httpx
from typing import Any
from urllib.parse import urlparse

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

TOOL_SPECS = {
    "nmap": {
        "description": "Escáner de puertos y servicios",
        "default_timeout": 300,
        "max_timeout": 600,
        "target_kind": "host",
        "profiles": list(TOOL_SCAN_TYPES),
    },
    "whois": {
        "description": "Consulta de registro WHOIS",
        "default_timeout": 10,
        "max_timeout": 30,
        "target_kind": "host",
        "profiles": ["default"],
    },
    "dig": {
        "description": "Consulta de registros DNS",
        "default_timeout": 10,
        "max_timeout": 30,
        "target_kind": "host",
        "profiles": ["default"],
    },
    "nslookup": {
        "description": "Resolución DNS",
        "default_timeout": 5,
        "max_timeout": 30,
        "target_kind": "host",
        "profiles": ["default"],
    },
    "curl": {
        "description": "Solicitud HTTP/HTTPS controlada",
        "default_timeout": 30,
        "max_timeout": 60,
        "target_kind": "url",
        "profiles": ["default"],
    },
    "ping": {
        "description": "Comprobación ICMP de disponibilidad",
        "default_timeout": 15,
        "max_timeout": 30,
        "target_kind": "host",
        "profiles": ["default"],
    },
    "nikto": {
        "description": "Escáner de vulnerabilidades web Nikto",
        "default_timeout": 300,
        "max_timeout": 600,
        "target_kind": "url",
        "profiles": ["default"],
    },
    "msfvenom": {
        "description": "Generador de payloads Metasploit",
        "default_timeout": 30,
        "max_timeout": 60,
        "target_kind": "none",
        "profiles": ["default"],
    },
    "airodump-ng": {
        "description": "Captura de paquetes WiFi",
        "default_timeout": 60,
        "max_timeout": 120,
        "target_kind": "none",
        "profiles": ["default"],
    },
    "aircrack-ng": {
        "description": "Cracking de claves WPA/WPA2",
        "default_timeout": 300,
        "max_timeout": 600,
        "target_kind": "none",
        "profiles": ["default"],
    },
    "theharvester": {
        "description": "Recolección de información OSINT",
        "default_timeout": 60,
        "max_timeout": 120,
        "target_kind": "host",
        "profiles": ["default"],
    },
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
        pending_confirmation: bool = False,
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.parsed = parsed
        self.elapsed = elapsed
        self.truncated = truncated
        self.error = error
        self.pending_confirmation = pending_confirmation

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "parsed": self.parsed,
            "elapsed": self.elapsed,
            "truncated": self.truncated,
            "error": self.error,
            "pending_confirmation": self.pending_confirmation,
        }


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
            if ip.version == 6:
                if ip.prefixlen != 128:
                    return (
                        f"Rango IPv6 '{target}' no soportado: "
                        "usa una sola dirección /128"
                    )
                address = ip.network_address
                if not address.is_global or address.is_multicast:
                    return f"Rango IPv6 no global '{target}' no permitido"
                return None
            for blocked in BLOCKED_RANGES:
                blocked_network = ipaddress.ip_network(blocked)
                if (
                    ip.version == blocked_network.version
                    and ip.overlaps(blocked_network)
                ):
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


def validate_url_target(target: str) -> str | None:
    parsed = urlparse(target.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "URL inválida: usa http:// o https://"

    try:
        literal_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return None

    if (
        literal_ip.is_private
        or literal_ip.is_loopback
        or literal_ip.is_reserved
        or literal_ip.is_multicast
        or literal_ip.is_link_local
    ):
        return f"Host privado o reservado '{parsed.hostname}' no permitido"
    return None


def validate_tool_target(tool: str, target: str) -> str | None:
    spec = TOOL_SPECS.get(tool)
    if not spec:
        return f"Herramienta '{tool}' no soportada"
    if spec["target_kind"] == "url":
        return validate_url_target(target)
    return validate_target(target)


def _build_tool_args(
    tool: str,
    target: str,
    profile: str,
    options: dict[str, Any],
    timeout: int,
) -> list[str]:
    if tool == "nmap":
        args = list(TOOL_SCAN_TYPES[profile])
        extra_args = options.get("extra_args", [])
        if not isinstance(extra_args, list) or any(not isinstance(arg, str) for arg in extra_args):
            raise ValueError("extra_args debe ser una lista de strings")
        args.extend(extra_args)
        return args + [target]
    if tool == "ping":
        return ["-c", "4", "-W", "3", target]
    if tool == "curl":
        return [
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            str(timeout),
            target,
        ]
    if tool == "nikto":
        return ["-h", target, "-o", "/dev/stdout"]
    return [target]


def list_tool_specs() -> list[dict[str, Any]]:
    return [
        {"name": name, **spec}
        for name, spec in TOOL_SPECS.items()
    ]


def _synth_parameters(spec: dict) -> dict:
    hint = {
        "host": "Dominio o IP pública a analizar",
        "url": "URL completa con http:// o https://",
        "none": "",
    }
    properties: dict = {}
    required: list = []
    if spec.get("target_kind") != "none":
        properties["target"] = {
            "type": "string",
            "description": hint.get(spec["target_kind"], "Objetivo a analizar"),
        }
        required.append("target")
    profiles = spec.get("profiles") or ["default"]
    properties["profile"] = {
        "type": "string",
        "enum": profiles,
        "description": "Perfil de intensidad de la ejecución",
        "default": "normal" if "normal" in profiles else profiles[0],
    }
    if spec.get("max_timeout"):
        properties["timeout"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": spec["max_timeout"],
            "description": "Timeout de la ejecución en segundos",
        }
    properties["options"] = {
        "type": "object",
        "description": "Opciones extra (ej: extra_args: lista de argumentos adicionales)",
        "additionalProperties": True,
    }
    return {"type": "object", "properties": properties, "required": required}


def build_openai_tools(tools: list[str] | None = None) -> list[dict]:
    """Convierte TOOL_SPECS al array 'tools' que espera la API OpenAI-compat de Ollama.

    Si una tool del catálogo define 'parameters' (JSON Schema completo), se usa tal cual;
    si no, el schema se sintetiza desde target_kind/profiles/timeout."""
    names = set(tools) if tools else set(TOOL_SPECS)
    out = []
    for name, spec in TOOL_SPECS.items():
        if name not in names:
            continue
        parameters = spec.get("parameters") or _synth_parameters(spec)
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec.get("description", name),
                "parameters": parameters,
            },
        })
    return out


def parse_tool_call(name: str, arguments: dict | None):
    """Mapea un tool_call emitido por el modelo a la firma de run_tool.

    Devuelve (tool, target, profile, options, timeout) o None si la tool es desconocida.
    La validación fuerte (target, perfil, timeout) la hace run_tool."""
    spec = TOOL_SPECS.get(name)
    if not spec:
        return None
    args = arguments or {}
    target = str(args.get("target", "") or "").strip()
    profile = str(args.get("profile", "") or (spec["profiles"][0] if spec["profiles"] else "default"))
    options = args.get("options") or {}
    if not isinstance(options, dict):
        options = {}
    timeout = args.get("timeout")
    timeout = int(timeout) if timeout else None
    return name, target, profile, options, timeout


class ToolsEngine:
    def __init__(self, base_url: str = KALI_BASE_URL):
        self.base_url = base_url
        self._client = httpx.Client(
            base_url=base_url,
            timeout=30,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._active_tasks: dict[str, tuple[int, float]] = {}
        self._concurrent_per_user: dict[int, int] = {}
        log.info("ToolsEngine initialized, Kali URL: %s", base_url)

    def _check_per_user_limit(self, user_id: int) -> str | None:
        now = time.time()
        self._active_tasks = {
            task_id: (owner, started)
            for task_id, (owner, started) in self._active_tasks.items()
            if now - started < 600
        }
        self._concurrent_per_user[user_id] = sum(
            1 for owner, _ in self._active_tasks.values() if owner == user_id
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
        return self.run_tool(
            "nmap",
            target,
            profile=scan_type,
            options={"extra_args": extra_args or []},
            timeout=timeout,
            user_id=user_id,
        )

    def run_tool(
        self,
        tool: str,
        target: str,
        profile: str = "default",
        options: dict[str, Any] | None = None,
        timeout: int | None = None,
        user_id: int = 0,
        force_execution: bool = False,
    ) -> ToolResult:
        spec = TOOL_SPECS.get(tool)
        if not spec:
            return ToolResult(success=False, error=f"Herramienta '{tool}' no soportada")

        error = validate_tool_target(tool, target)
        if error:
            return ToolResult(success=False, error=error)

        if profile == "default" and tool == "nmap":
            profile = "normal"
        if profile not in spec["profiles"]:
            return ToolResult(success=False, error=f"Perfil '{profile}' no soportado para {tool}")

        actual_timeout = timeout or spec["default_timeout"]
        if actual_timeout < 1 or actual_timeout > spec["max_timeout"]:
            return ToolResult(
                success=False,
                error=f"Timeout inválido para {tool}: máximo {spec['max_timeout']}s",
            )

        limit_error = self._check_per_user_limit(user_id)
        if limit_error:
            return ToolResult(success=False, error=limit_error)

        if not force_execution:
            # Middleware de permisos: modo plan o confirmación individual
            from tool_permissions import audit_intent, needs_confirmation, propose

            if needs_confirmation(tool):
                proposal = (
                    f"[PROPUESTA] Ejecutar {tool} -> target: {target}"
                    f", perfil: {profile}, timeout: {actual_timeout}s."
                    " Decime 'sí' para ejecutarlo o 'no' para cancelar."
                )
                intent = {
                    "kind": "tool",
                    "user_id": user_id,
                    "tool": tool,
                    "target": target,
                    "profile": profile,
                    "options": options,
                    "timeout": actual_timeout,
                    "proposal": proposal,
                }
                propose(user_id, intent)
                audit_intent(intent, "proposed")
                return ToolResult(
                    success=True,
                    stdout=proposal,
                    pending_confirmation=True,
                )

        try:
            args = _build_tool_args(tool, target, profile, options or {}, actual_timeout)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        task_id = f"{tool}_{user_id}_{uuid.uuid4().hex[:12]}"
        payload = {
            "tool": tool,
            "args": args,
            "timeout": actual_timeout,
            "task_id": task_id,
        }
        self._active_tasks[task_id] = (user_id, time.time())

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
            log.exception("Error running tool %s", tool)
            return ToolResult(success=False, error=str(e))
        finally:
            self._active_tasks.pop(task_id, None)

    def health(self) -> bool:
        try:
            resp = self._client.get("/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


tools_engine = ToolsEngine()
