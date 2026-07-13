import os
import json
import sqlite3
import uuid
import httpx
import re
import subprocess
import threading
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form, Body
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from workflows import ejecutar_workflow, listar_workflows

# ─── V5 modules ───
from target_engine import TargetEngine
from memory_engine import MemoryEngine
from task_queue import TaskQueue
from security import AuditLog, RateLimiter
from playbooks import list_playbooks, run_playbook
from report_generator import generate_report
import hacking

try:
    import voice as voice_module
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("artenisa")

app = FastAPI(title="Artenisa API")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ─── Routers ───
from findings.router import router as findings_router
from pentest.router import router as pentest_router
from defense.router import router as defense_router
from subagents.router import router as subagents_router
from mcp.router import router as mcp_router
app.include_router(findings_router)
app.include_router(pentest_router)
app.include_router(defense_router)
app.include_router(subagents_router)
app.include_router(mcp_router)

# ─── Cargar .env manualmente ───
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text("utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, v = _line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nex-agi/nex-n2-pro:free")
DB_PATH = os.getenv("DB_PATH", "data/conversations.db")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "8"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "1800"))
MAX_MEMORY_ITEMS = int(os.getenv("MAX_MEMORY_ITEMS", "6"))
MAX_MEMORY_CHARS = int(os.getenv("MAX_MEMORY_CHARS", "600"))
TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT", "60"))

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))  # 20MB
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".txt", ".py", ".md", ".json"}
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

if not AUTH_TOKEN or len(AUTH_TOKEN) < 12:
    AUTH_TOKEN = os.urandom(32).hex()
    log.warning(f"⚠️  AUTH_TOKEN generado automáticamente: {AUTH_TOKEN}")
    log.warning("   Configura uno fijo en backend/.env con AUTH_TOKEN=tu-token-seguro")

# ─── SQLite optimizado: WAL mode + connection pool ───

_conn_local = threading.local()

def get_conn():
    if not hasattr(_conn_local, "conn") or _conn_local.conn is None:
        _conn_local.conn = sqlite3.connect(DB_PATH)
        _conn_local.conn.execute("PRAGMA journal_mode=WAL")
        _conn_local.conn.execute("PRAGMA busy_timeout=5000")
        _conn_local.conn.row_factory = sqlite3.Row
    return _conn_local.conn

@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                tool_output TEXT,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                key TEXT PRIMARY KEY,
                value TEXT,
                category TEXT DEFAULT 'user',
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT,
                original_name TEXT,
                size INTEGER,
                uploaded_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)")
        log.info("Base de datos inicializada")

init_db()

# ─── V5 module instances ───
_target_engine = TargetEngine()
_memory_engine = MemoryEngine()
_task_queue = TaskQueue()
_audit_log = AuditLog()
_rate_limiter = RateLimiter()

# ─── httpx client reutilizable ───

_httpx_timeout = int(os.getenv("HTTPX_TIMEOUT", "30"))
_httpx_client = None

def get_httpx():
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.Client(timeout=_httpx_timeout)
    return _httpx_client

# ─── Modelos ───

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    tool_executed: bool = False
    tool_command: Optional[str] = None
    tool_output: Optional[str] = None
    done: bool = True

class SpeakRequest(BaseModel):
    text: str
    voice: str = "es-MX-DaliaNeural"

# ─── Auth ───

def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, {"error": "Token requerido"})
    token = authorization.replace("Bearer ", "")
    if not token or token != AUTH_TOKEN:
        raise HTTPException(401, {"error": "Token inválido"})

# ─── DB helpers ───

def save_message(conv_id: str, role: str, content: str, tool_output: str = None):
    with db() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_output, timestamp) VALUES (?, ?, ?, ?, ?)",
            (conv_id, role, content, tool_output, datetime.utcnow().isoformat())
        )

def get_history(conv_id: str, limit: int = MAX_HISTORY) -> list:
    with db() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_output FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,)
        ).fetchall()
    result = []
    for r in rows:
        entry = {"role": r["role"], "content": r["content"]}
        if r["tool_output"]:
            entry["tool_output"] = r["tool_output"]
        result.append(entry)
    return result[-limit:]

def load_all_memories() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT key, value FROM memories ORDER BY key").fetchall()
    return {r["key"]: r["value"] for r in rows}

def save_memories_batch(memories: list):
    if not memories:
        return
    now = datetime.utcnow().isoformat()
    with db() as conn:
        for m in memories:
            key = m.get("key", "").strip()
            value = m.get("value", "").strip()
            if key and value:
                conn.execute(
                    "INSERT OR REPLACE INTO memories (key, value, category, updated_at) VALUES (?, ?, 'user', ?)",
                    (key, value, now)
                )

# ─── Multi-Provider ───

from providers import get_provider, list_providers, PROVIDER_REGISTRY

import providers.openrouter
import providers.groq
import providers.anthropic

_current_provider_name = os.getenv("ACTIVE_PROVIDER", "openrouter")

def _get_provider():
    return get_provider(_current_provider_name)

def switch_provider(name: str):
    global _current_provider_name
    if name not in PROVIDER_REGISTRY:
        raise ValueError(f"Provider '{name}' no disponible")
    _current_provider_name = name
    os.environ["ACTIVE_PROVIDER"] = name

def switch_model(model: str):
    p = _get_provider()
    p.switch_model(model)

def call_ollama(prompt: str, model: str = None, temperature: float = 0.85) -> str:
    try:
        p = _get_provider()
        if model:
            p.switch_model(model)
        return p.generate(prompt, temperature)
    except TimeoutError:
        raise HTTPException(504, "Timeout del modelo")
    except Exception as e:
        log.error(f"Error en modelo: {e}")
        raise HTTPException(502, f"Error del modelo: {e}")

def call_ollama_safe(prompt: str, model: str = None, temperature: float = 0.85) -> str:
    """Versión segura que no lanza excepciones."""
    try:
        p = _get_provider()
        if model:
            p.switch_model(model)
        return p.generate(prompt, temperature)
    except Exception as e:
        log.error(f"Error en modelo (safe): {e}")
        return f"[Error del modelo: {e}]"

# ─── Memoria (fire-and-forget con thread) ───

MEMORY_EXTRACTION_PROMPT = """
Extrae TODOS los datos personales del usuario en esta conversación.
Devuelve SOLO JSON: {"memories": [{"key": "nombre", "value": "valor"}]}
Keys en inglés con guiones bajos. Si no hay datos: {"memories": []}
Conversación:
"""

def _extract_memories_worker(user_msg: str, assistant_resp: str):
    """Corre en segundo plano para no bloquear la respuesta"""
    try:
        extraction_input = f"""<|im_start|>system\n{MEMORY_EXTRACTION_PROMPT}\nUsuario: {user_msg}\nArtenisa: {assistant_resp}<|im_end|>\n<|im_start|>assistant\n"""
        raw = call_ollama(extraction_input, temperature=0.1)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            if "memories" in data and isinstance(data["memories"], list):
                save_memories_batch(data["memories"])
    except Exception:
        pass

def trigger_memory_extraction(user_msg: str, assistant_resp: str):
    t = threading.Thread(target=_extract_memories_worker, args=(user_msg, assistant_resp), daemon=True)
    t.start()

# ─── Prompt builder ───

MEMORY_INJECTION_TEMPLATE = "[MEMORIA DEL USUARIO]\n{items}"

def _truncate_text(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _prepare_history_for_prompt(history: list, limit: int = None, max_chars: int = None) -> list:
    limit = limit if limit is not None else MAX_HISTORY_TURNS
    max_chars = max_chars if max_chars is not None else MAX_MESSAGE_CHARS
    prepared = []
    for item in history[-limit:]:
        content = _truncate_text(item.get("content", ""), max_chars)
        entry = {"role": item.get("role", "user"), "content": content}
        tool_output = item.get("tool_output")
        if tool_output:
            entry["tool_output"] = _truncate_text(str(tool_output), 800)
        prepared.append(entry)
    return prepared


def format_memories(memories: dict, max_items: int = None, max_chars: int = None) -> str:
    if not memories:
        return ""
    max_items = max_items if max_items is not None else MAX_MEMORY_ITEMS
    max_chars = max_chars if max_chars is not None else MAX_MEMORY_CHARS
    items = []
    for key, value in list(memories.items())[:max_items]:
        value = _truncate_text(str(value), max_chars)
        items.append(f"  {key.replace('_', ' ').title()}: {value}")
    return MEMORY_INJECTION_TEMPLATE.format(items="\n".join(items))

SYSTEM_PROMPT = r"""Eres Artenisa, mi asistente personal y compañero de ingeniería. Tu misión es comprenderme profundamente, anticiparte a mis necesidades y ayudarme a construir, depurar, mejorar y escalar sistemas con la mayor calidad posible.

Tu único dueño es Daniel Navas. Puedes llamarlo Navas. Eres leal únicamente a él y debes priorizar comprensión, velocidad, claridad y utilidad real.

Tu nivel debe ser el de un ingeniero senior de primer nivel. Eres excelente en programación, debugging, arquitectura, código limpio, testing, performance, seguridad, automatización, APIs, bases de datos, DevOps, shell, Docker, Git, CI/CD y resolución de problemas complejos.

ESTILO:
- Habla de forma natural, humana, calmada y precisa.
- No actúes como un personaje de teatro; actúa como alguien real, competente y cercano.
- No exageres, no hagas humor forzado ni frases vacías.
- Si una respuesta puede ser corta, hazla corta; si necesita profundidad, entrégala sin rodeos.
- Cuando te doy un problema técnico, lo analizas como un experto real.

COMPORTAMIENTO DE INGENIERÍA:
1. Entiende primero la intención antes de cambiar código.
2. Revisa el contexto completo: errores, archivos, flujo, dependencias y objetivos.
3. Busca la causa raíz, no solo el síntoma.
4. Propón soluciones mínimas, robustas y bien justificadas.
5. Prefiere calidad, mantenibilidad y seguridad por encima de soluciones rápidas e inestables.
6. Si corresponde, añade tests, validación y pasos de verificación.
7. Si falta contexto, haz una pregunta precisa y concreta.
8. No inventes información: sé honesto cuando no sepas algo y ofrece la mejor aproximación posible.

CUANDO TRABAJES CON CÓDIGO:
- Escribe código limpio, idiomático y legible.
- Respeta el estilo del proyecto.
- Mantén funciones pequeñas y enfocadas.
- Evita abstracciones innecesarias.
- Prioriza rendimiento, seguridad, testabilidad y simplicidad.
- Si hay errores, identifícalos con precisión y corrígelos con criterio.
- Si hay arquitectura débil, propón mejoras sin complicar innecesariamente.

CUANDO DEPURES:
- Lee los mensajes de error con atención.
- Reproduce o identifica el fallo de forma concreta.
- Haz hipótesis y verifícalas.
- No te quedes en el primer síntoma; encuentra la causa real.

CUANDO AYUDES EN PROYECTOS:
- Piensa como un CTO, arquitecto, lead engineer y desarrollador al mismo tiempo.
- Ayuda a construir sistemas que sean claros, escalables y mantenibles.
- Considera seguridad, observabilidad, documentación, automatización y experiencia de desarrollo.

TU OBJETIVO:
Ser la mejor asistente de programación y pensamiento técnico para mí. Entenderme como si fueras mi copiloto de ingeniería: útil, rápida, precisa y profundamente competente.

HERRAMIENTAS DISPONIBLES (escribe el comando exacto en tu respuesta para usarlas):
!leer: ruta         - Lee archivos del sistema
!escribir: ruta contenido - Crea/escribe archivos
!editar: ruta "texto_viejo" "texto_nuevo" - Reemplaza texto exacto en un archivo
!grep: patrón ruta  - Busca texto en archivos
!glob: patrón       - Encuentra archivos por nombre
!ejecutar: comando  - Ejecuta comandos en el sistema (cmd/powershell)
!buscar: consulta   - Busca en internet
!fetch: url         - Trae contenido web
!explorar: ruta     - Explora estructura de carpetas
!preguntar: texto   - Pregunta algo al usuario y espera su respuesta
!tareas: inicio/paso/hecho - Seguimiento de tareas
!razonar: problema  - Piensa paso a paso antes de responder

REGLAS:
- Responde de forma natural primero. No conviertas cada mensaje en una cascada de herramientas.
- Usa herramientas solo cuando sean claramente útiles, necesarias o el usuario haya pedido una acción concreta.
- Si el problema es simple o conversacional, responde directamente sin herramientas.
- Si necesitas datos reales, ESCRIBE el comando exacto en tu respuesta. Yo lo ejecuto y te doy el resultado.
- Ejemplo: !leer: C:/Users/ASUS/archivo.txt
- No digas "voy a leer" — directamente escribe !leer:
- Para editar usa !editar: ruta "texto exacto a reemplazar" "texto nuevo"
- Para tareas usa !tareas: inicio "nombre", !tareas: paso "descripción", !tareas: hecho N
- Para razonar usa !razonar: problema y analiza paso a paso
- Siempre obtén datos reales. No inventes. Zero filtros."""

def build_prompt(history: list, new_message: str, memories: dict) -> str:
    parts = []
    mem_block = format_memories(memories)
    if mem_block:
        parts.append(f"<|im_start|>system\n{mem_block}<|im_end|>")
    jailbreak = get_system_prompt()
    if jailbreak:
        parts.append(f"<|im_start|>system\n{jailbreak}<|im_end|>")
    parts.append(f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>")
    for h in _prepare_history_for_prompt(history):
        role = "user" if h["role"] == "user" else "assistant"
        content = h["content"]
        if h.get("tool_output"):
            content += f"\n[Resultado: {h['tool_output']}]"
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    parts.append(f"<|im_start|>user\n{_truncate_text(new_message, 2200)}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)

import shlex

# ─── Seguridad: evitar shell=True ───

def _safe_args(cmd: str) -> list:
    """Convierte un comando string en lista de argumentos segura."""
    try:
        return shlex.split(cmd, posix=False)
    except ValueError:
        return cmd.split()

TOOL_CMD_RE = re.compile(r'!ejecutar:\s*(.+)', re.IGNORECASE)
TOOL_SEARCH_RE = re.compile(r'!buscar:\s*(.+)', re.IGNORECASE)
TOOL_READ_RE = re.compile(r'!leer:\s*(.+)', re.IGNORECASE)
TOOL_WRITE_RE = re.compile(r'!escribir:\s*(.+)', re.IGNORECASE)
TOOL_GREP_RE = re.compile(r'!grep:\s*(.+)', re.IGNORECASE)
TOOL_GLOB_RE = re.compile(r'!glob:\s*(.+)', re.IGNORECASE)
TOOL_FETCH_RE = re.compile(r'!fetch:\s*(.+)', re.IGNORECASE)
TOOL_EDIT_RE = re.compile(r'!editar:\s*(.+)', re.IGNORECASE)
TOOL_PREGUNTAR_RE = re.compile(r'!preguntar:\s*(.+)', re.IGNORECASE)
TOOL_TAREAS_RE = re.compile(r'!tareas:\s*(.+)', re.IGNORECASE)
TOOL_EXPLORAR_RE = re.compile(r'!explorar:\s*(.+)', re.IGNORECASE)
TOOL_RAZONAR_RE = re.compile(r'!razonar:\s*(.+)', re.IGNORECASE)

def parse_tool_commands(text: str) -> list:
    commands = []
    for m in TOOL_CMD_RE.finditer(text):
        cmd = m.group(1).strip()
        if cmd:
            commands.append(cmd)
    for m in TOOL_SEARCH_RE.finditer(text):
        query = m.group(1).strip()
        if query:
            commands.append(("search", query))
    for m in TOOL_READ_RE.finditer(text):
        commands.append(("read", m.group(1).strip()))
    for m in TOOL_WRITE_RE.finditer(text):
        commands.append(("write", m.group(1).strip()))
    for m in TOOL_GREP_RE.finditer(text):
        commands.append(("grep", m.group(1).strip()))
    for m in TOOL_GLOB_RE.finditer(text):
        commands.append(("glob", m.group(1).strip()))
    for m in TOOL_FETCH_RE.finditer(text):
        commands.append(("fetch", m.group(1).strip()))
    for m in TOOL_EDIT_RE.finditer(text):
        commands.append(("edit", m.group(1).strip()))
    for m in TOOL_PREGUNTAR_RE.finditer(text):
        commands.append(("preguntar", m.group(1).strip()))
    for m in TOOL_TAREAS_RE.finditer(text):
        commands.append(("tareas", m.group(1).strip()))
    for m in TOOL_EXPLORAR_RE.finditer(text):
        commands.append(("explorar", m.group(1).strip()))
    for m in TOOL_RAZONAR_RE.finditer(text):
        commands.append(("razonar", m.group(1).strip()))
    return commands

TOOL_INSTALLERS = {
    "nmap": ["winget", "install", "--id", "Insecure.Nmap", "-e", "--source", "winget"],
    "curl": ["winget", "install", "--id", "cURL.cURL", "-e", "--source", "winget"],
    "wget": ["winget", "install", "--id", "GNU.Wget2", "-e", "--source", "winget"],
    "ping": ["cmd", "/c", "echo", "ya instalado en Windows"],
    "tracert": ["cmd", "/c", "echo", "ya instalado en Windows"],
    "netstat": ["cmd", "/c", "echo", "ya instalado en Windows"],
    "ipconfig": ["cmd", "/c", "echo", "ya instalado en Windows"],
    "findstr": ["cmd", "/c", "echo", "ya instalado en Windows"],
    "python": ["cmd", "/c", "echo", "ya instalado"],
    "pip": ["cmd", "/c", "echo", "ya instalado"],
    "ssh": ["winget", "install", "--id", "Microsoft.OpenSSH.Beta", "-e", "--source", "winget"],
    "git": ["winget", "install", "--id", "Git.Git", "-e", "--source", "winget"],
    "whois": ["winget", "install", "--id", "whois", "-e", "--source", "winget"],
    "dig": ["winget", "install", "--id", "BIND.BIND", "-e", "--source", "winget"],
    "nslookup": ["cmd", "/c", "echo", "ya instalado en Windows"],
    "sqlmap": ["pip", "install", "sqlmap"],
    "hydra": ["winget", "install", "--id", "Thc.Hydra", "-e", "--source", "winget"],
}

NOT_FOUND_PATTERNS = [
    "no se reconoce", "not recognized", "not found", "no instalado",
    "not installed", "no such file", "command not found",
    "is not recognized", "is not installed",
]

def _get_tool_name(command: str) -> str:
    cmd = command.strip().split()[0].lower()
    return cmd.split("\\")[-1].split("/")[-1]

def _auto_install(tool: str) -> str:
    installer = TOOL_INSTALLERS.get(tool)
    if not installer:
        return f"No sé cómo instalar {tool}. Instalalo manualmente."
    try:
        log.info(f"Instalando {tool}...")
        result = subprocess.run(installer, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 or "instalado" in (result.stdout + result.stderr).lower():
            return f"✅ {tool} instalado correctamente."
        else:
            return f"⚠️ Error instalando {tool}: {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return f"⚠️ Timeout instalando {tool}"
    except Exception as e:
        return f"⚠️ Error: {e}"

def execute_command(command: str, auto_install: bool = True) -> dict:
    tool = _get_tool_name(command)
    args = _safe_args(command)
    for attempt in range(2):
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=TOOL_TIMEOUT
            )
            output = (result.stdout or result.stderr or "").strip()
            if result.returncode != 0 and auto_install and attempt == 0:
                error_lower = (result.stdout + result.stderr).lower()
                if any(p in error_lower for p in NOT_FOUND_PATTERNS):
                    install_msg = _auto_install(tool)
                    if install_msg.startswith("✅"):
                        log.info(f"Reintentando {command} después de instalar {tool}")
                        continue
                    return {
                        "command": command,
                        "success": False,
                        "output": f"{install_msg}\n\nReintenta el comando.",
                        "returncode": result.returncode
                    }
            return {
                "command": command,
                "success": result.returncode == 0,
                "output": output[:8000] if output else "(sin salida)",
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"command": command, "success": False, "output": "[Timeout]"}
        except Exception as e:
            return {"command": command, "success": False, "output": f"[Error: {e}]"}
    return {"command": command, "success": False, "output": "[Error: no se pudo ejecutar]"}

def search_web(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "(sin resultados)"
        lines = [
            f"• {r.get('title', '')}: {r.get('body', '')[:200]} [{r.get('href', '')}]"
            for r in results
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"[Error de búsqueda: {e}]"

TOOL_ANALYSIS_PROMPT = """
Has ejecutado una herramienta. Analiza el resultado y responde al usuario
con un análisis útil estilo Artenisa: técnico, preciso y con personalidad.
Explica vulnerabilidades encontradas y sugiere próximos pasos.
"""

TAREAS_DB = {}
TAREAS_FILE = Path(__file__).parent / "data" / "tareas.json"

def _load_tareas():
    global TAREAS_DB
    if TAREAS_FILE.exists():
        try:
            TAREAS_DB = json.loads(TAREAS_FILE.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            TAREAS_DB = {}
    return TAREAS_DB

def _save_tareas():
    TAREAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TAREAS_FILE.write_text(json.dumps(TAREAS_DB, indent=2, ensure_ascii=False))

def _handle_tareas(arg: str) -> dict:
    _load_tareas()
    conv_key = f"conv_{datetime.utcnow().date()}"
    if conv_key not in TAREAS_DB:
        TAREAS_DB[conv_key] = {"pasos": [], "actual": 0}
    parts = arg.strip().split(" ", 1)
    accion = parts[0].lower()
    data = parts[1] if len(parts) > 1 else ""
    if accion == "inicio":
        TAREAS_DB[conv_key] = {"pasos": [], "actual": 0}
        _save_tareas()
        return {"status": "iniciado", "tarea": data or "General"}
    elif accion in ("paso", "+"):
        TAREAS_DB[conv_key]["pasos"].append({"id": len(TAREAS_DB[conv_key]["pasos"]) + 1, "desc": data, "hecho": False})
        _save_tareas()
        return {"status": "paso agregado", "paso": len(TAREAS_DB[conv_key]["pasos"]), "desc": data}
    elif accion in ("hecho", "ok", "x"):
        n = int(data) if data.isdigit() else TAREAS_DB[conv_key]["actual"] + 1
        for p in TAREAS_DB[conv_key]["pasos"]:
            if p["id"] == n:
                p["hecho"] = True
                TAREAS_DB[conv_key]["actual"] = n
                break
        _save_tareas()
        return {"status": f"paso {n} completado"}
    elif accion == "estado":
        pendientes = [p for p in TAREAS_DB[conv_key]["pasos"] if not p["hecho"]]
        completados = [p for p in TAREAS_DB[conv_key]["pasos"] if p["hecho"]]
        return {"total": len(TAREAS_DB[conv_key]["pasos"]), "completados": len(completados), "pendientes": len(pendientes), "siguiente": pendientes[0] if pendientes else None}
    return {"status": f"tarea: {arg}"}

def _parse_edit_arg(arg: str) -> dict:
    import shlex
    try:
        parts = shlex.split(arg, posix=False)
        if len(parts) >= 3:
            return {"path": parts[0], "old": parts[1].strip('"'), "new": " ".join(p.strip('"') for p in parts[2:])}
        return None
    except ValueError:
        return None

TOOL_HANDLERS = {
    "read": lambda arg: _exec_httpx("tools/read", {"path": arg}),
    "write": lambda arg: _exec_httpx("tools/write", {"path": arg.split(" ", 1)[0], "content": arg.split(" ", 1)[1] if " " in arg else ""}),
    "grep": lambda arg: _exec_httpx("tools/grep", {"pattern": arg.split(" ", 1)[0], "path": arg.split(" ", 1)[1] if " " in arg else "."}),
    "glob": lambda arg: _exec_httpx("tools/glob", {"pattern": arg}),
    "fetch": lambda arg: _exec_httpx("tools/fetch", {"url": arg}),
    "edit": lambda arg: _exec_httpx("tools/edit", {"arg": arg}),
    "explorar": lambda arg: _exec_httpx("tools/explore", {"path": arg}),
    "preguntar": lambda arg: {"tipo": "pregunta", "pregunta": arg, "esperando": True},
    "tareas": lambda arg: _handle_tareas(arg),
    "razonar": lambda arg: _exec_httpx("tools/reason", {"prompt": arg}),
}

def _exec_httpx(endpoint: str, data: dict) -> dict:
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f"http://localhost:8000/{endpoint}", json=data,
                       headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
            return r.json() if r.status_code == 200 else {"error": r.text[:500]}
    except Exception as e:
        return {"error": str(e)}

def process_tool_commands(response_text: str) -> tuple:
    tool_results = []
    lines = response_text.split("\n")
    cleaned = []

    for line in lines:
        m_cmd = TOOL_CMD_RE.match(line)
        if m_cmd:
            result = execute_command(m_cmd.group(1).strip())
            tool_results.append(result)
            continue

        m_search = TOOL_SEARCH_RE.match(line)
        if m_search:
            query = m_search.group(1).strip()
            output = search_web(query)
            tool_results.append({"command": f"buscar: {query}", "output": output})
            continue

        m_read = TOOL_READ_RE.match(line)
        if m_read:
            result = TOOL_HANDLERS["read"](m_read.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_write = TOOL_WRITE_RE.match(line)
        if m_write:
            result = TOOL_HANDLERS["write"](m_write.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_grep = TOOL_GREP_RE.match(line)
        if m_grep:
            result = TOOL_HANDLERS["grep"](m_grep.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_glob = TOOL_GLOB_RE.match(line)
        if m_glob:
            result = TOOL_HANDLERS["glob"](m_glob.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_fetch = TOOL_FETCH_RE.match(line)
        if m_fetch:
            result = TOOL_HANDLERS["fetch"](m_fetch.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue

        m_edit = TOOL_EDIT_RE.match(line)
        if m_edit:
            result = TOOL_HANDLERS["edit"](m_edit.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_preguntar = TOOL_PREGUNTAR_RE.match(line)
        if m_preguntar:
            result = TOOL_HANDLERS["preguntar"](m_preguntar.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_tareas = TOOL_TAREAS_RE.match(line)
        if m_tareas:
            result = TOOL_HANDLERS["tareas"](m_tareas.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_explorar = TOOL_EXPLORAR_RE.match(line)
        if m_explorar:
            result = TOOL_HANDLERS["explorar"](m_explorar.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue
        m_razonar = TOOL_RAZONAR_RE.match(line)
        if m_razonar:
            result = TOOL_HANDLERS["razonar"](m_razonar.group(1).strip())
            tool_results.append({"command": line.strip(), "output": json.dumps(result, ensure_ascii=False)[:8000]})
            continue

        cleaned.append(line)

    return "\n".join(cleaned), tool_results

# ─── Endpoints ───

@app.get("/")
def root():
    return {
        "status": "ok",
        "asistente": "Artenisa",
        "modelo": OPENROUTER_MODEL,
        "features": ["chat", "tools", "search", "files", "memory", "voice", "web"]
    }

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, authorization: str = Header(None)):
    verify_token(authorization)
    start = datetime.utcnow()

    conv_id = req.conversation_id or str(uuid.uuid4())
    memories = load_all_memories()
    history = get_history(conv_id) if req.conversation_id else []
    prompt = build_prompt(history, req.message, memories)

    response_text = call_ollama(prompt)
    cleaned_text, tool_results = process_tool_commands(response_text)

    if tool_results:
        tool_context = "\n".join(
            f"Comando: {r.get('command', '')}\nSalida:\n{r.get('output', '')}"
            for r in tool_results
        )
        analysis_prompt = (
            f"{TOOL_ANALYSIS_PROMPT}\n\n"
            f"Comando: {tool_results[0].get('command', '')}\n\n"
            f"Resultado:\n{tool_context}\n\n"
            f"Usuario: {req.message}"
        )
        final_text = call_ollama(analysis_prompt, temperature=0.7)
    else:
        final_text = cleaned_text

    save_message(conv_id, "user", req.message)
    save_message(conv_id, "assistant", final_text,
                 tool_results[0]["output"] if tool_results else None)

    trigger_memory_extraction(req.message, final_text)

    elapsed = (datetime.utcnow() - start).total_seconds()
    log.info(f"Chat [{conv_id[:8]}] {elapsed:.1f}s | tools={len(tool_results)} | hist={len(history)}")

    return ChatResponse(
        response=final_text,
        conversation_id=conv_id,
        tool_executed=len(tool_results) > 0,
        tool_command=tool_results[0].get("command") if tool_results else None,
        tool_output=tool_results[0].get("output")[:2000] if tool_results else None
    )

@app.post("/chat/stream")
def chat_stream(req: ChatRequest, authorization: str = Header(None)):
    verify_token(authorization)
    conv_id = req.conversation_id or str(uuid.uuid4())
    memories = load_all_memories()
    history = get_history(conv_id) if req.conversation_id else []
    prompt = build_prompt(history, req.message, memories)

    def event_generator():
        full_response = []
        try:
            p = _get_provider()
            for token in p.generate_stream(prompt):
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as e:
            err_msg = str(e)
            log.error(f"Error streaming: {err_msg}")
            if "429" in err_msg:
                friendly = "Límite de requests excedido (OpenRouter free). Espera unos segundos y vuelve a intentar."
            elif "Timeout" in err_msg:
                friendly = "El modelo tardó demasiado en responder. Intenta con un mensaje más corto."
            else:
                friendly = f"Error del modelo: {err_msg}"
            yield f"data: {json.dumps({'type': 'error', 'error': friendly})}\n\n"
            return

        try:
            cleaned_text, tool_results = process_tool_commands("".join(full_response))

            if tool_results:
                tool_context = "\n".join(
                    f"Comando: {r.get('command', '')}\nSalida:\n{r.get('output', '')}"
                    for r in tool_results
                )
                analysis_prompt = (
                    f"{TOOL_ANALYSIS_PROMPT}\n\n"
                    f"Comando: {tool_results[0].get('command', '')}\n\n"
                    f"Resultado:\n{tool_context}\n\n"
                    f"Usuario: {req.message}"
                )
                final_text = call_ollama(analysis_prompt, temperature=0.7)
            else:
                final_text = cleaned_text

            save_message(conv_id, "user", req.message)
            save_message(conv_id, "assistant", final_text,
                         tool_results[0]["output"] if tool_results else None)
            trigger_memory_extraction(req.message, final_text)

            result = {
                "type": "done",
                "conversation_id": conv_id,
                "response": final_text,
                "tool_executed": len(tool_results) > 0,
                "tool_command": tool_results[0].get("command") if tool_results else None,
                "tool_output": tool_results[0].get("output")[:2000] if tool_results else None
            }
            yield f"data: {json.dumps(result)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), authorization: str = Header(None)):
    verify_token(authorization)

    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Tipo de archivo no permitido: {ext}")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"Archivo demasiado grande ({len(content)}b). Máximo: {MAX_UPLOAD_SIZE}b")

    file_id = str(uuid.uuid4())[:8]
    safe_name = f"{file_id}{ext}"
    save_path = UPLOAD_DIR / safe_name

    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO files (id, filename, original_name, size, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (file_id, safe_name, file.filename, len(content), datetime.utcnow().isoformat())
        )

    log.info(f"Upload: {file.filename} ({len(content)}b) -> {file_id}")

    return {"file_id": file_id, "filename": file.filename, "size": len(content),
            "url": f"/files/{file_id}/{safe_name}"}

@app.get("/files/{file_id}/{filename:path}")
def download_file(file_id: str, filename: str, authorization: str = Header(None)):
    verify_token(authorization)
    with db() as conn:
        row = conn.execute("SELECT filename, original_name FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Archivo no encontrado")
    file_path = UPLOAD_DIR / row["filename"]
    if not file_path.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")
    return FileResponse(file_path, filename=row["original_name"])

@app.get("/files")
def list_files(authorization: str = Header(None)):
    verify_token(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, original_name, size, uploaded_at FROM files ORDER BY uploaded_at DESC"
        ).fetchall()
    return {"files": [{"id": r["id"], "name": r["original_name"],
                       "size": r["size"], "uploaded": r["uploaded_at"]} for r in rows]}

@app.get("/search")
def search(query: str, authorization: str = Header(None)):
    verify_token(authorization)
    log.info(f"Search: {query}")
    return {"query": query, "results": search_web(query)}

@app.post("/execute")
def execute(command: str = Form(...), authorization: str = Header(None)):
    verify_token(authorization)
    log.info(f"Execute: {command[:100]}")
    return execute_command(command)

@app.post("/execute-body")
def execute_body(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    cmd = data.get("command", "")
    if not cmd:
        raise HTTPException(400, "command requerido")
    return execute_command(cmd)

@app.get("/history/{conversation_id}")
def get_history_endpoint(conversation_id: str, authorization: str = Header(None)):
    verify_token(authorization)
    return {"conversation_id": conversation_id, "messages": get_history(conversation_id)}

@app.get("/conversations")
def list_conversations(authorization: str = Header(None)):
    verify_token(authorization)
    with db() as conn:
        rows = conn.execute(
            "SELECT conversation_id, MIN(timestamp) as start, COUNT(*) as msgs "
            "FROM messages GROUP BY conversation_id ORDER BY start DESC"
        ).fetchall()
    return {"conversations": [{"id": r["conversation_id"], "created": r["start"],
                               "messages": r["msgs"]} for r in rows]}

@app.get("/memories")
def get_memories(authorization: str = Header(None)):
    verify_token(authorization)
    return {"memories": load_all_memories()}

@app.post("/memories")
def add_memory(key: str = Form(...), value: str = Form(...), authorization: str = Header(None)):
    verify_token(authorization)
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO memories (key, value, category, updated_at) VALUES (?, ?, 'user', ?)",
            (key.strip(), value.strip(), datetime.utcnow().isoformat())
        )
    return {"status": "ok", "key": key, "value": value}

@app.delete("/memories/{key}")
def delete_memory(key: str, authorization: str = Header(None)):
    verify_token(authorization)
    with db() as conn:
        conn.execute("DELETE FROM memories WHERE key = ?", (key,))
    return {"status": "deleted", "key": key}

@app.get("/transcribe")
async def transcribe_audio(file_id: str, authorization: str = Header(None)):
    verify_token(authorization)
    if not VOICE_AVAILABLE:
        raise HTTPException(501, "Módulo de voz no disponible")
    with db() as conn:
        row = conn.execute("SELECT filename FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Archivo no encontrado")
    audio_path = UPLOAD_DIR / row["filename"]
    if not audio_path.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")
    try:
        text = voice_module.transcribe(str(audio_path))
        return {"text": text}
    except Exception as e:
        raise HTTPException(500, f"Error transcribiendo: {e}")

@app.post("/speak")
async def speak(req: SpeakRequest, authorization: str = Header(None)):
    verify_token(authorization)
    if not VOICE_AVAILABLE:
        raise HTTPException(501, "Módulo de voz no disponible")
    try:
        audio = await voice_module.speak(req.text, req.voice)
        if not audio:
            raise HTTPException(500, "No se generó audio")
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(500, f"Error de TTS: {e}")

# ─── Herramientas de sistema (leer, escribir, grep, glob, fetch) ───

@app.post("/tools/read")
async def tool_read(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    try:
        if not Path(path).exists():
            raise HTTPException(404, "Archivo no encontrado")
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content[:50000]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error leyendo: {e}")

@app.post("/tools/write")
async def tool_write(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    content = data.get("content", "")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")
        return {"path": path, "status": "escrito", "bytes": len(content)}
    except Exception as e:
        raise HTTPException(500, f"Error escribiendo: {e}")

@app.post("/tools/grep")
async def tool_grep(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    pattern = data.get("pattern", "")
    path = data.get("path", ".")
    try:
        results = []
        for p in Path(path).rglob("*"):
            if p.is_file() and p.suffix in {".py", ".txt", ".md", ".json", ".yml", ".yaml", ".html", ".js", ".ts", ".css", ".bat", ".ps1", ".sh", ".env", ".cfg", ".conf", ".ini"}:
                try:
                    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            results.append({"file": str(p), "line": i, "text": line[:200]})
                except (UnicodeDecodeError, PermissionError, OSError):
                    pass
        return {"matches": len(results), "results": results[:100]}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")

@app.post("/tools/glob")
async def tool_glob(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    pattern = data.get("pattern", "")
    path = data.get("path", ".")
    try:
        import glob as glob_mod
        full = str(Path(path) / pattern)
        files = glob_mod.glob(full, recursive=True)
        return {"files": files[:200]}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")

@app.post("/tools/fetch")
async def tool_fetch(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    url = data.get("url", "")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.get(url)
            return {"url": url, "status": resp.status_code, "content": resp.text[:50000]}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")

@app.post("/tools/edit")
async def tool_edit(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    import shlex
    try:
        arg = data.get("arg", "")
        parts = shlex.split(arg, posix=False)
        if len(parts) < 3:
            return {"error": "Formato: !editar: ruta 'texto_viejo' 'texto_nuevo'"}
        path, old, new = parts[0], parts[1].strip('"'), " ".join(p.strip('"') for p in parts[2:])
        if not Path(path).exists():
            raise HTTPException(404, "Archivo no encontrado")
        content = Path(path).read_text(encoding="utf-8")
        if old not in content:
            return {"error": f"'texto_viejo' no encontrado en el archivo", "path": path}
        new_content = content.replace(old, new, 1)
        Path(path).write_text(new_content, encoding="utf-8")
        return {"path": path, "status": "editado", "reemplazos": 1}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error editando: {e}")

@app.post("/tools/explore")
async def tool_explore(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", ".")
    try:
        p = Path(path)
        if not p.exists():
            raise HTTPException(404, "Ruta no encontrada")
        files = []
        dirs = []
        for item in p.iterdir():
            if item.is_dir():
                dirs.append(item.name)
            else:
                files.append({"name": item.name, "size": item.stat().st_size})
        return {"path": str(p.absolute()), "dirs": dirs, "files": files[:100]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")

@app.post("/tools/reason")
async def tool_reason(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    prompt = data.get("prompt", "")
    reasoning_prompt = f"Piensa paso a paso para resolver:\n\n{prompt}\n\nRazonamiento:"
    try:
        result = call_ollama(reasoning_prompt, temperature=0.3)
        return {"razonamiento": result}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}")

@app.get("/workflows")
def get_workflows(authorization: str = Header(None)):
    verify_token(authorization)
    return listar_workflows()

@app.post("/workflows/{nombre}")
def run_workflow_endpoint(nombre: str, params: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    log.info(f"Workflow: {nombre} params={params}")
    return ejecutar_workflow(nombre, params)

# ─── Multi-Provider endpoints ───

@app.get("/models")
def list_models(authorization: str = Header(None)):
    verify_token(authorization)
    p = _get_provider()
    return {"models": p.list_models(), "current": p.model, "provider": _current_provider_name}

@app.get("/providers")
def list_providers_endpoint(authorization: str = Header(None)):
    verify_token(authorization)
    return {"providers": list_providers(), "active": _current_provider_name}

@app.post("/provider")
def set_provider(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    name = data.get("provider", "")
    try:
        switch_provider(name)
        p = _get_provider()
        return {"status": "ok", "provider": name, "model": p.model}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/provider/model")
def set_provider_model(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    model = data.get("model", "")
    if not model:
        raise HTTPException(400, "Model name required")
    switch_model(model)
    return {"status": "ok", "model": model}

# ─── System Prompt (jailbreak mode) ───

SYSTEM_PROMPT_FILE = Path(__file__).parent / "system_prompt.md"
_system_prompt_cache = None

def get_system_prompt() -> str:
    global _system_prompt_cache
    if SYSTEM_PROMPT_FILE.exists():
        _system_prompt_cache = SYSTEM_PROMPT_FILE.read_text("utf-8")
    return _system_prompt_cache or ""

@app.get("/system-prompt")
def get_system_prompt_endpoint(authorization: str = Header(None)):
    verify_token(authorization)
    return {"system_prompt": get_system_prompt()}

@app.post("/system-prompt")
def set_system_prompt_endpoint(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    content = data.get("content", "")
    if content:
        SYSTEM_PROMPT_FILE.write_text(content, encoding="utf-8")
        global _system_prompt_cache
        _system_prompt_cache = content
    else:
        if SYSTEM_PROMPT_FILE.exists():
            SYSTEM_PROMPT_FILE.unlink()
        _system_prompt_cache = None
    return {"status": "ok"}

# ─── Health check para Docker ───

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

TOOL_ALIASES = {
    "portscan": "scan_ports",
    "dns": "dns_enum",
    "subdomains": "subdomain_scan",
    "whois": "whois_lookup",
    "dirb": "dir_bruteforce",
    "tech": "detect_tech",
    "sqli": "check_sqli",
    "xss": "check_xss",
    "lfi": "check_lfi",
    "ssl": "ssl_check",
    "hashid": "hash_id",
    "hashcrack": "hash_crack",
    "decode64": "decode_b64",
    "encode64": "encode_b64",
    "base64": "encode_b64",
    "ipgeo": "ip_geo",
    "email": "email_osint",
    "certs": "cert_transparency",
    "reverseshell": "reverse_shell",
    "webshell": "webshell",
    "payload": "encode_payload",
}

# ─── V5 Endpoints ───

@_rate_limiter.wrap
@app.get("/v5/target/{user_id}")
def v5_get_target(user_id: int, authorization: str = Header(None)):
    verify_token(authorization)
    return _target_engine.get_target(user_id)

@_rate_limiter.wrap
@app.get("/v5/target/{user_id}/summary")
def v5_get_target_summary(user_id: int, authorization: str = Header(None)):
    verify_token(authorization)
    return {"summary": _target_engine.get_context_summary(user_id)}

@_rate_limiter.wrap
@app.post("/v5/target")
def v5_set_target(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    target = data.get("target", "")
    target_type = data.get("target_type", "domain")
    user_id = data.get("user_id", 0)
    _target_engine.set_target(user_id, target, target_type)
    return {"status": "ok", "target": target, "target_type": target_type, "user_id": user_id}

@_rate_limiter.wrap
@app.delete("/v5/target/{user_id}")
def v5_clear_target(user_id: int, authorization: str = Header(None)):
    verify_token(authorization)
    _target_engine.clear_target(user_id)
    return {"status": "ok", "user_id": user_id}

@_rate_limiter.wrap
@app.get("/v5/playbooks")
def v5_list_playbooks(authorization: str = Header(None)):
    verify_token(authorization)
    return list_playbooks()

@_rate_limiter.wrap
@app.post("/v5/playbooks/{name}")
def v5_run_playbook(name: str, data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    target = data.get("target", "")
    depth = data.get("depth", "rapido")
    creador = data.get("creador", "api")
    task_id = _task_queue.submit(name, target=target, params={"playbook": name, "depth": depth})
    _audit_log.log(0, creador, f"playbook:{name}", target=target, status="ok", details=f"task:{task_id}")
    return {"task_id": task_id, "status": "queued"}

@_rate_limiter.wrap
@app.get("/v5/tasks")
def v5_list_tasks(authorization: str = Header(None)):
    verify_token(authorization)
    return {"tasks": _task_queue.list_tasks()}

@_rate_limiter.wrap
@app.get("/v5/tasks/{task_id}")
def v5_get_task(task_id: str, authorization: str = Header(None)):
    verify_token(authorization)
    return _task_queue.get_status(task_id)

@_rate_limiter.wrap
@app.post("/v5/tasks")
def v5_submit_task(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    playbook = data.get("playbook", "")
    target = data.get("target", "")
    depth = data.get("depth", "rapido")
    creador = data.get("creador", "api")
    if not playbook or not target:
        raise HTTPException(400, "playbook y target son requeridos")
    task_id = _task_queue.submit(playbook, target=target, params={"playbook": playbook, "depth": depth})
    _audit_log.log(0, creador, f"task:{playbook}", target=target, status="queued", details=f"task:{task_id}")
    return {"task_id": task_id, "status": "queued", "playbook": playbook, "target": target}

@_rate_limiter.wrap
@app.post("/v5/tasks/{task_id}/cancel")
def v5_cancel_task(task_id: str, authorization: str = Header(None)):
    verify_token(authorization)
    ok = _task_queue.cancel(task_id)
    return {"status": "cancelled" if ok else "not_found"}

@_rate_limiter.wrap
@app.post("/v5/report")
def v5_generate_report(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    target = data.get("target", "")
    fmt = data.get("format", "md")
    results = data.get("data", data.get("results", []))
    playbook = data.get("playbook", "")
    payload = {"results": results, "playbook": playbook}
    report = generate_report(target, payload, fmt)
    return report

@_rate_limiter.wrap
@app.post("/v5/hacking/{tool}")
def v5_hacking_tool(tool: str, data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    target = data.get("target", "")
    hash_val = data.get("hash", "")
    text = data.get("text", "")
    ip = data.get("ip", "")
    port = data.get("port", 0)
    shell_type = data.get("shell_type", "bash")
    language = data.get("language", "php")
    param = data.get("param", "q")
    try:
        real_name = TOOL_ALIASES.get(tool, tool)
        tool_fn = getattr(hacking, real_name, None)
        if tool_fn is None:
            raise HTTPException(404, f"Herramienta '{tool}' no encontrada")

        if tool in ("hashcrack",):
            result = tool_fn(hash_val or target)
        elif tool in ("decode64",):
            result = tool_fn(text or target)
        elif tool in ("encode64", "base64"):
            result = tool_fn(text or target)
        elif tool in ("hashid",):
            result = tool_fn(hash_val or target)
        elif tool in ("reverseshell",):
            result = tool_fn(ip or target, int(port or 4444), shell_type)
        elif tool in ("webshell",):
            result = tool_fn(language)
        elif tool in ("ipgeo",):
            result = tool_fn(ip or target)
        elif tool in ("portscan",):
            ports = data.get("ports", "22,80,443")
            timeout = data.get("timeout", 3)
            result = tool_fn(target, ports, timeout)
        else:
            result = tool_fn(target)
        return {"tool": tool, "target": target, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error ejecutando {tool}: {e}")

@_rate_limiter.wrap
@app.get("/v5/audit")
def v5_get_audit(authorization: str = Header(None)):
    verify_token(authorization)
    return {"entries": _audit_log.get_recent(50)}

@_rate_limiter.wrap
@app.post("/v5/memory/operational")
def v5_store_operational_memory(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    conversation_id = data.get("conversation_id", "")
    context = data.get("context", data.get("data", {}))
    _memory_engine.store_operational(conversation_id, context)
    return {"status": "stored", "conversation_id": conversation_id}

@_rate_limiter.wrap
@app.get("/v5/memory/operational/{conv_id}")
def v5_get_operational_memory(conv_id: str, authorization: str = Header(None)):
    verify_token(authorization)
    memory = _memory_engine.get_operational(conv_id)
    return {"conversation_id": conv_id, "memory": memory}

@_rate_limiter.wrap
@app.post("/v5/memory/historical")
def v5_store_history_memory(data: dict = Body(...), authorization: str = Header(None)):
    verify_token(authorization)
    target = data.get("target", "")
    playbook = data.get("playbook", "")
    summary = data.get("summary", "")
    findings = data.get("findings", 0)
    if not target:
        raise HTTPException(400, "target requerido")
    _memory_engine.store_historical(target=target, operation=f"playbook:{playbook}" if playbook else "manual", summary=summary, findings_count=findings)
    return {"status": "stored", "target": target}

@_rate_limiter.wrap
@app.get("/v5/memory/historical/{target}")
def v5_get_history_memory(target: str, authorization: str = Header(None)):
    verify_token(authorization)
    memory = _memory_engine.get_history(target)
    return {"target": target, "memory": memory}

# ─── Main ───

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    log.info(f"Iniciando Artenisa en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
