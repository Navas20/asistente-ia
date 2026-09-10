"""
Configuración centralizada del proyecto
"""
import os
from pathlib import Path
from typing import List

# ─── Directorios ───
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_DIR = PROJECT_ROOT / "data_layer"

# ─── Base de Datos ───
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "conversations.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", str(DATA_DIR / "reports")))
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", str(DATA_DIR / "audio")))

# ─── Multi-Provider ───
ACTIVE_PROVIDER = os.getenv("ACTIVE_PROVIDER", "ollama")

# ─── Ollama (100% local) ───
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://artenisa-ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "artenisa")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "400"))

# ─── Groq ───
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "kimi-k2-instruct-0905")

# ─── Anthropic ───
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# ─── Seguridad ───
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "").split(",") if os.getenv("ALLOWED_USER_IDS") else []
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else []

# ─── Límites ───
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "8"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "1800"))
MAX_MEMORY_ITEMS = int(os.getenv("MAX_MEMORY_ITEMS", "6"))
MAX_MEMORY_CHARS = int(os.getenv("MAX_MEMORY_CHARS", "600"))
TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT", "60"))

# ─── Upload ───
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))  # 20MB
ALLOWED_EXTENSIONS = {
    ".wav", ".mp3", ".ogg", ".flac", ".m4a",
    ".png", ".jpg", ".jpeg", ".gif",
    ".pdf", ".txt", ".py", ".md", ".json"
}

# ─── Telegram (opcional) ───
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# ─── Rate Limiting ───
RATE_LIMIT_CALLS = int(os.getenv("RATE_LIMIT_CALLS", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ─── Logging ───
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Cargar .env si existe
def load_env():
    """Carga variables de entorno desde backend/.env"""
    env_path = BACKEND_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text("utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()

# Crear directorios necesarios
os.makedirs(DB_PATH.rsplit("/", 1)[0] if "/" in DB_PATH else ".", exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Generar AUTH_TOKEN si no existe
if not AUTH_TOKEN or len(AUTH_TOKEN) < 12:
    import logging
    import secrets
    AUTH_TOKEN = secrets.token_hex(32)
    logging.warning(f"⚠️  AUTH_TOKEN generado automáticamente: {AUTH_TOKEN}")
    logging.warning("   Configura uno fijo en backend/.env con AUTH_TOKEN=tu-token-seguro")
