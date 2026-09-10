import os
import json
import sqlite3
import uuid
import httpx
import re
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
import tool_permissions
import hacking
import tools_engine
from tools_engine import tools_engine as tool_engine

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
from projects_router import router as projects_router
from oast_router import router as oast_router
from tools.router import router as tools_router
app.include_router(findings_router)
app.include_router(pentest_router)
app.include_router(defense_router)
app.include_router(subagents_router)
app.include_router(mcp_router)
app.include_router(projects_router)
app.include_router(oast_router)
app.include_router(tools_router)

# ─── Cargar .env manualmente ───
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text("utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, v = _line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "artenisa")
DB_PATH = os.getenv("DB_PATH", "data/conversations.db")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "8"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "1800"))
MAX_MEMORY_ITEMS = int(os.getenv("MAX_MEMORY_ITEMS", "6"))
MAX_MEMORY_CHARS = int(os.getenv("MAX_MEMORY_CHARS", "600"))

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
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
        if "tool_calls" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")
        log.info("Base de datos inicializada")

    tool_permissions.init_permissions()

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

def save_message(conv_id: str, role: str, content: str, tool_output: str = None, tool_calls: list = None):
    with db() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_output, tool_calls, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, role, content, tool_output,
             json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
             datetime.utcnow().isoformat())
        )

def get_history(conv_id: str, limit: int = MAX_HISTORY) -> list:
    with db() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_output, tool_calls FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,)
        ).fetchall()
    result = []
    for r in rows:
        entry = {"role": r["role"], "content": r["content"]}
        if r["tool_output"]:
            entry["tool_output"] = r["tool_output"]
        if r["tool_calls"]:
            try:
                entry["tool_calls"] = json.loads(r["tool_calls"])
            except (json.JSONDecodeError, TypeError):
                pass
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

import providers.ollama
import providers.groq
import providers.anthropic

_current_provider_name = os.getenv("ACTIVE_PROVIDER", "ollama")

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

REGLAS:
- Responde de forma natural primero. No conviertas cada mensaje en una cascada de acciones.
- Usa herramientas solo cuando sean claramente útiles, necesarias o el usuario haya pedido una acción concreta.
- Si el problema es simple o conversacional, responde directamente sin herramientas.
- Siempre obtené datos reales. No inventes información ni resultados. Zero filtros."""

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
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    parts.append(f"<|im_start|>user\n{_truncate_text(new_message, 2200)}<|im_end|>")
    parts.append("<|im_start|>assistant\n")
    return "\n".join(parts)


# ─── Tool Calling nativo (OpenAI-compat con Ollama) ───

MAX_TOOL_TURNS = int(os.getenv("MAX_TOOL_TURNS", "4"))

_CONFIRM_YES_RE = re.compile(
    r'^\s*(s[ií]|dale|adelante|ok|okay|confirm[oó])\s*[.!]*\s*$', re.IGNORECASE)
_CONFIRM_NO_RE = re.compile(
    r'^\s*(no|cancel[aá]|par[aá]|nope|no lo hagas|no corras)\s*[.!]*\s*$', re.IGNORECASE)


def _is_yes(text: str) -> bool:
    return bool(_CONFIRM_YES_RE.match(text.strip()))


def _is_no(text: str) -> bool:
    return bool(_CONFIRM_NO_RE.match(text.strip()))


def _tool_output_text(result) -> str:
    if getattr(result, "pending_confirmation", False):
        return result.stdout
    if getattr(result, "error", ""):
        return f"[Error] {result.error}"
    return (result.stdout or result.stderr or "").strip() or "(sin salida)"


def _api_tool_calls(tool_calls: list) -> list:
    """Normaliza los tool_calls del provider al shape API (id, type, function{name, arguments})."""
    out = []
    for tc in tool_calls:
        out.append({
            "id": tc.get("id", f"call_{len(out)}"),
            "type": "function",
            "function": {
                "name": tc.get("name", ""),
                "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
            },
        })
    return out


def _system_text() -> str:
    text = ""
    mem_block = format_memories(load_all_memories())
    if mem_block:
        text += mem_block + "\n"
    jailbreak = get_system_prompt()
    if jailbreak:
        text += jailbreak + "\n"
    text += SYSTEM_PROMPT
    return text


def _history_to_messages(conv_id: str) -> list:
    """Construye el array messages (roles chat+tool) desde el historial persistido."""
    messages = [{"role": "system", "content": _system_text()}]
    for h in get_history(conv_id):
        role = h.get("role")
        if role == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": h.get("content", "") or "",
                "content": h.get("tool_output") or h.get("content", ""),
            })
        elif role == "assistant" and h.get("tool_calls"):
            messages.append({
                "role": "assistant",
                "content": h.get("content") or "",
                "tool_calls": h["tool_calls"],
            })
        else:
            messages.append({
                "role": role if role in ("system", "user", "assistant") else "user",
                "content": h.get("content", ""),
            })
    return messages


def _append_tool_turn(messages: list, resp: dict, tc: dict, output: str, conv_id: str) -> None:
    api_calls = _api_tool_calls(resp.get("tool_calls") or [])
    assistant = {"role": "assistant", "content": resp.get("content") or "", "tool_calls": api_calls}
    messages.append(assistant)
    save_message(conv_id, "assistant", assistant["content"], tool_calls=api_calls)
    save_message(conv_id, "tool", tc.get("id", "call_?"), output)
    messages.append({"role": "tool", "tool_call_id": tc.get("id", "call_?"), "content": output})


def _run_tool_loop(conv_id: str, message: str, user_id: int = 0) -> dict:
    provider = _get_provider()
    save_message(conv_id, "user", message)
    messages = _history_to_messages(conv_id)
    tools = tools_engine.build_openai_tools()
    last_exec: tuple | None = None

    for _ in range(MAX_TOOL_TURNS):
        resp = provider.chat(messages, tools)
        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            final = resp.get("content", "") or ""
            save_message(conv_id, "assistant", final)
            trigger_memory_extraction(message, final)
            return {
                "response": final,
                "tool_executed": bool(last_exec),
                "tool_command": last_exec[0] if last_exec else None,
                "tool_output": last_exec[1] if last_exec else None,
            }

        for tc in tool_calls:
            parsed = tools_engine.parse_tool_call(tc.get("name", ""), tc.get("arguments"))
            if parsed is None:
                _append_tool_turn(
                    messages, resp, tc,
                    f"[Error] La herramienta '{tc.get('name', '')}' no está soportada.", conv_id,
                )
                continue

            tool, target, profile, options, timeout = parsed
            intent = {
                "kind": "tool",
                "user_id": user_id,
                "tool": tool,
                "target": target,
                "profile": profile,
                "options": options,
                "timeout": timeout,
                "tool_call_id": tc.get("id", f"call_{tool}"),
            }

            if tool_permissions.needs_confirmation(tool):
                intent["proposal"] = (
                    f"[PROPUESTA] Ejecutar {tool} -> target: {target}"
                    f", perfil: {profile}, timeout: {timeout or 'default'}s."
                    " Decime 'sí' para ejecutarlo o 'no' para cancelar."
                )
                tool_permissions.propose(user_id, intent)
                tool_permissions.audit_intent(intent, "proposed")
                save_message(conv_id, "assistant", intent["proposal"])
                return {
                    "response": intent["proposal"],
                    "tool_executed": False,
                    "tool_command": f"!{tool}",
                    "tool_output": intent["proposal"],
                }

            result = tool_engine.run_tool(
                tool, target, profile=profile, options=options, timeout=timeout,
                user_id=user_id, force_execution=True,
            )
            output = _tool_output_text(result)
            last_exec = (tool, output[:2000])
            _append_tool_turn(messages, resp, tc, output, conv_id)

    final = "Llegué al máximo de iteraciones de herramientas sin llegar a un cierre. Intentá ser más específico."
    save_message(conv_id, "assistant", final)
    trigger_memory_extraction(message, final)
    return {
        "response": final,
        "tool_executed": bool(last_exec),
        "tool_command": last_exec[0] if last_exec else None,
        "tool_output": last_exec[1] if last_exec else None,
    }


def _run_confirmed(conv_id: str, message: str, intent: dict, user_id: int = 0) -> dict:
    provider = _get_provider()
    save_message(conv_id, "user", message)
    result = tool_engine.run_tool(
        intent["tool"], intent["target"], profile=intent["profile"],
        options=intent["options"], timeout=intent["timeout"],
        user_id=user_id, force_execution=True,
    )
    output = _tool_output_text(result)
    tc_id = intent.get("tool_call_id") or f"call_{intent['tool']}"
    api_calls = [{
        "id": tc_id,
        "type": "function",
        "function": {
            "name": intent["tool"],
            "arguments": json.dumps({
                "target": intent["target"],
                "profile": intent["profile"],
                "options": intent["options"],
                "timeout": intent["timeout"],
            }, ensure_ascii=False),
        },
    }]
    messages = _history_to_messages(conv_id)
    messages.append({"role": "assistant", "content": intent.get("proposal") or "", "tool_calls": api_calls})
    messages.append({"role": "tool", "tool_call_id": tc_id, "content": output})

    resp = provider.chat(messages, tools_engine.build_openai_tools())
    final = resp.get("content", "") or ""
    if not final.strip():
        final = f"Ejecutado {intent['tool']}.\n\n{output}"
    save_message(conv_id, "assistant", final)
    trigger_memory_extraction(message, final)
    return {
        "response": final,
        "tool_executed": True,
        "tool_command": intent["tool"],
        "tool_output": output[:2000],
    }


def _resolve_turn(conv_id: str, message: str, user_id: int = 0) -> dict:
    """Resuelve un turno: confirmación pendiente primero, luego tool-loop o fallback clásico."""
    if tool_permissions.has_pending(user_id):
        if _is_no(message):
            tool_permissions.resolve_pending(user_id, confirmed=False)
            save_message(conv_id, "user", message)
            final = "Cancelado. No ejecuto nada."
            save_message(conv_id, "assistant", final)
            return {"response": final, "tool_executed": False, "tool_command": None, "tool_output": None}
        if _is_yes(message):
            intent = tool_permissions.resolve_pending(user_id, confirmed=True)
            if intent:
                return _run_confirmed(conv_id, message, intent, user_id)

    provider = _get_provider()
    if getattr(provider, "supports_tools", False):
        return _run_tool_loop(conv_id, message, user_id)

    # Fallback clásico: prompt en string, sin tools.
    save_message(conv_id, "user", message)
    prompt = build_prompt(get_history(conv_id), message, load_all_memories())
    final = provider.generate(prompt, 0.85).strip()
    save_message(conv_id, "assistant", final)
    trigger_memory_extraction(message, final)
    return {"response": final, "tool_executed": False, "tool_command": None, "tool_output": None}


def _chunk_text(text: str, size: int = 40):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def search_web(query: str) -> str:
    try:
        domain_filter = None
        if " dominio:" in query:
            parts = query.split(" dominio:", 1)
            query = parts[0].strip()
            domain_filter = parts[1].strip().lower().rstrip("/")

        depth = 0
        if " profundidad:" in query:
            parts = query.split(" profundidad:", 1)
            query = parts[0].strip()
            try:
                depth = min(int(parts[1].strip().split()[0]), 2)
            except (ValueError, IndexError):
                depth = 0

        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "(sin resultados)"

        lines = []
        for r in results:
            title = r.get('title', '')
            body = r.get('body', '')[:300]
            href = r.get('href', '')
            if domain_filter and domain_filter not in href.lower():
                continue
            lines.append(f"• {title}: {body} [{href}]")
            if depth > 0 and href and (not domain_filter or domain_filter in href.lower()):
                try:
                    import httpx
                    resp = httpx.get(href, timeout=10, follow_redirects=True)
                    content = resp.text[:2000]
                    import re as _re
                    text = _re.sub(r'<[^>]+>', ' ', content)
                    text = _re.sub(r'\s+', ' ', text).strip()[:1000]
                    lines.append(f"  └ Crawl: {text[:500]}")
                    if depth > 1:
                        sub_links = re.findall(r'href=[\'"]?(https?://[^\'" >]+)', content)[:3]
                        for sl in sub_links:
                            try:
                                sub_resp = httpx.get(sl, timeout=8, follow_redirects=True)
                                sub_text = _re.sub(r'<[^>]+>', ' ', sub_resp.text)
                                sub_text = _re.sub(r'\s+', ' ', sub_text).strip()[:500]
                                lines.append(f"    └ {sl}: {sub_text[:200]}")
                            except Exception:
                                pass
                except Exception:
                    pass

        return "\n".join(lines) if lines else "(sin resultados para el filtro)"
    except Exception as e:
        return f"[Error de búsqueda: {e}]"


# ─── Endpoints ───

@app.get("/")
def root():
    return {
        "status": "ok",
        "asistente": "Artenisa",
        "modelo": OLLAMA_MODEL,
        "features": ["chat", "tools", "search", "files", "memory", "voice", "web"]
    }

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, authorization: str = Header(None)):
    verify_token(authorization)
    start = datetime.utcnow()

    conv_id = req.conversation_id or str(uuid.uuid4())

    result = _resolve_turn(conv_id, req.message)

    elapsed = (datetime.utcnow() - start).total_seconds()
    log.info(f"Chat [{conv_id[:8]}] {elapsed:.1f}s | tool={bool(result['tool_executed']) if result['tool_command'] else '-'}")

    return ChatResponse(
        response=result["response"],
        conversation_id=conv_id,
        tool_executed=result["tool_executed"],
        tool_command=result["tool_command"],
        tool_output=result["tool_output"],
    )

@app.post("/chat/stream")
def chat_stream(req: ChatRequest, authorization: str = Header(None)):
    verify_token(authorization)
    conv_id = req.conversation_id or str(uuid.uuid4())

    def event_generator():
        try:
            result = _resolve_turn(conv_id, req.message)
        except HTTPException as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e.detail)})}\n\n"
            return
        except Exception as e:
            err_msg = str(e)
            log.error(f"Error resolviendo turno: {err_msg}")
            if "429" in err_msg:
                friendly = "El modelo local (Ollama) no respondió. Revisá si el contenedor artenisa-ollama está arriba."
            elif "Timeout" in err_msg:
                friendly = "El modelo tardó demasiado en responder. Intenta con un mensaje más corto."
            else:
                friendly = f"Error del modelo: {err_msg}"
            yield f"data: {json.dumps({'type': 'error', 'error': friendly})}\n\n"
            return

        for chunk in _chunk_text(result["response"]):
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'response': result['response'], 'tool_executed': result['tool_executed'], 'tool_command': result['tool_command'], 'tool_output': (result['tool_output'] or '')[:2000]})}\n\n"

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

@app.post("/tools/move")
async def tool_move(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    arg = data.get("arg", "")
    try:
        parts = arg.rsplit(" ", 1)
        if len(parts) < 2:
            raise HTTPException(400, "Formato: !mover: origen destino")
        src, dst = parts[0], parts[1]
        Path(src).rename(dst)
        return {"from": src, "to": dst, "status": "movido"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error moviendo: {e}")


@app.post("/tools/copy")
async def tool_copy(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    arg = data.get("arg", "")
    try:
        import shutil
        parts = arg.rsplit(" ", 1)
        if len(parts) < 2:
            raise HTTPException(400, "Formato: !copiar: origen destino")
        src, dst = parts[0], parts[1]
        if Path(src).is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {"from": src, "to": dst, "status": "copiado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error copiando: {e}")


@app.post("/tools/delete")
async def tool_delete(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    try:
        p = Path(path)
        if not p.exists():
            raise HTTPException(404, "Archivo no encontrado")
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"path": path, "status": "eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error eliminando: {e}")


@app.post("/tools/readimg")
async def tool_readimg(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    try:
        if not Path(path).exists():
            raise HTTPException(404, "Archivo no encontrado")
        from PIL import Image
        img = Image.open(path)
        info = {"format": img.format, "size": f"{img.size[0]}x{img.size[1]}", "mode": img.mode}
        try:
            import pytesseract
            text = pytesseract.image_to_string(img)
            info["ocr_text"] = text[:5000]
        except Exception:
            info["ocr_text"] = "(Tesseract no disponible)"
        return {"path": path, "info": info}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error leyendo imagen: {e}")


@app.post("/tools/review")
async def tool_review(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    try:
        p = Path(path)
        if not p.exists():
            raise HTTPException(404, "Archivo no encontrado")
        content = p.read_text(encoding="utf-8", errors="replace")
        prompt = f"Revisa este código y da feedback línea por línea. Señala bugs, problemas de seguridad, estilo, y sugiere mejoras:\n\n```\n{content[:15000]}\n```"
        result = call_ollama(prompt, temperature=0.2)
        return {"path": path, "review": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error revisando: {e}")


@app.post("/tools/diff")
async def tool_diff(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, timeout=30,
            cwd=path or None
        )
        diff = (result.stdout or result.stderr or "")[:20000]
        return {"path": path or ".", "diff": diff, "has_changes": len(diff) > 0}
    except Exception as e:
        return {"path": path or ".", "diff": f"Error: {e}", "has_changes": False}


TEMPLATES = {
    "python": {
        "README.md": "# {name}\n\n## Descripción\n\nProyecto Python",
        "main.py": "def main():\n    print(\"Hello from {name}\")\n\nif __name__ == \"__main__\":\n    main()\n",
        "requirements.txt": "# {name}\n",
    },
    "fastapi": {
        "README.md": "# {name}\n\nFastAPI project",
        "main.py": "from fastapi import FastAPI\n\napp = FastAPI(title=\"{name}\")\n\n@app.get(\"/\")\ndef root():\n    return {\"message\": \"Hello from {name}\"}\n",
        "requirements.txt": "fastapi\nuvicorn\n",
    },
    "react": {
        "README.md": "# {name}\n\nReact project",
        "package.json": '{{\n  "name": "{name}",\n  "version": "1.0.0",\n  "scripts": {{\n    "dev": "vite",\n    "build": "vite build"\n  }}\n}}',
        "index.html": "<!DOCTYPE html>\n<html><head><title>{name}</title></head><body><div id=\"root\"></div></body></html>",
    },
    "cli": {
        "README.md": "# {name}\n\nCLI tool",
        "{name}.py": "import argparse\n\ndef main():\n    parser = argparse.ArgumentParser(description=\"{name}\")\n    args = parser.parse_args()\n    print(\"Hello from {name}\")\n\nif __name__ == \"__main__\":\n    main()\n",
        "requirements.txt": "# {name}\n",
    },
}


@app.post("/tools/scaffold")
async def tool_scaffold(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    arg = data.get("arg", "")
    try:
        parts = arg.strip().split(" ", 1)
        template_name = parts[0].lower() if parts else "python"
        project_name = parts[1] if len(parts) > 1 else "my_project"
        template = TEMPLATES.get(template_name)
        if not template:
            return {"error": f"Template no encontrado. Usa: {', '.join(TEMPLATES.keys())}"}
        base = Path(project_name)
        base.mkdir(parents=True, exist_ok=True)
        created = []
        for filename, content in template.items():
            fpath = base / filename.replace("{name}", project_name)
            fpath.write_text(content.replace("{name}", project_name), encoding="utf-8")
            created.append(str(fpath))
        return {"template": template_name, "project": project_name, "files": created, "path": str(base.resolve())}
    except Exception as e:
        raise HTTPException(500, f"Error creando proyecto: {e}")


async def _run_browser(url: str, action: str) -> dict:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if action == "screenshot":
            screenshot = await page.screenshot()
            import base64
            b64 = base64.b64encode(screenshot).decode()
            await browser.close()
            return {"url": url, "screenshot": f"data:image/png;base64,{b64[:500]}", "size": len(screenshot)}

        if action == "html":
            title = await page.title()
            text = await page.inner_text("body")
            await browser.close()
            return {"url": url, "title": title, "text": text[:5000]}

        if action.startswith("click "):
            selector = action[6:]
            await page.click(selector)
            await browser.close()
            return {"url": url, "action": f"click {selector}", "status": "clicked"}

        if action.startswith("fill "):
            fill_parts = action[5:].split(" ", 1)
            if len(fill_parts) >= 2:
                selector, value = fill_parts[0], fill_parts[1]
                await page.fill(selector, value)
                await browser.close()
                return {"url": url, "action": f"fill {selector}", "status": "filled"}

        if action == "links":
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))")
            await browser.close()
            return {"url": url, "links": links[:50]}

        title = await page.title()
        await browser.close()
        return {"url": url, "title": title}


@app.post("/tools/browse")
async def tool_browse(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    arg = data.get("arg", "")
    try:
        parts = arg.split(" ", 1)
        url = parts[0].strip()
        action = parts[1].strip().lower() if len(parts) > 1 else "html"
        return await _run_browser(url, action)
    except Exception as e:
        raise HTTPException(500, f"Error navegando: {e}")


@app.post("/tools/readpdf")
async def tool_readpdf(data: dict = Body({}), authorization: str = Header(None)):
    verify_token(authorization)
    path = data.get("path", "")
    try:
        if not Path(path).exists():
            raise HTTPException(404, "Archivo no encontrado")
        import fitz
        doc = fitz.open(path)
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            pages.append({"page": page_num + 1, "text": text[:5000]})
        doc.close()
        return {"path": path, "pages": len(pages), "content": pages}
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(500, "PyMuPDF no instalado (pip install pymupdf)")
    except Exception as e:
        raise HTTPException(500, f"Error leyendo PDF: {e}")


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
        raise HTTPException(400, "Se requiere el nombre del modelo")
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
