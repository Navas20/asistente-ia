# Artenisa

Asistente-copiloto de ingeniería con capacidades de hacking ético, playbooks automatizados, motor de memoria de 3 capas, cola de tareas async y bot de Telegram.

## Stack

- **Backend:** FastAPI + SQLite + OpenRouter (Gemma 4 26B)
- **CLI:** Rich + Prompt Toolkit
- **Bot:** python-telegram-bot (ReplyKeyboard + InlineKeyboard)
- **Plugins:** Sistema de plugins extensible con PluginBase

## Características

- Chat conversacional con streaming via OpenRouter
- Motor de memoria: capas reciente / operacional / histórica
- Contexto de objetivo persistente por sesión
- 5 playbooks estructurados de ciberseguridad ofensiva
- Herramientas de red, web, OSINT, crypto y generación de payloads
- Cola de tareas asíncrona con persistencia
- Generación de reportes (MD / HTML / JSON)
- Bot de Telegram con menú de 9 botones y asistentes guiados (wizards)
- Sistema de seguridad: auditoría, rate limiting, roles
- Plugins extensibles

## Requisitos

- Python 3.10+
- Windows 10/11 (sin WSL)
- Token de OpenRouter (gratuito)
- Token de Telegram Bot (opcional)

## Instalación rápida

```bash
pip install -r backend/requirements.txt
```

Crear `backend/.env`:

```
OPENROUTER_API_KEY=sk-or-v1-tu-key
OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free
AUTH_TOKEN=artenisa-secret-token-2026
TELEGRAM_TOKEN=tu-token-de-bot
ALLOWED_USER_IDS=123456789
```

## Uso

```bash
# Iniciar backend
cd backend && python main.py

# En otra terminal, iniciar CLI
cd cli && python main.py
```

## Estructura

```
backend/
├── main.py                 # API FastAPI (13 endpoints /v5/)
├── llama_backend.py        # Cliente OpenRouter
├── target_engine.py        # Contexto de objetivo
├── memory_engine.py        # Memoria 3 capas (SQLite)
├── playbooks.py            # 5 playbooks ofensivos
├── task_queue.py           # Cola async con persistencia
├── report_generator.py     # Reportes MD/HTML/JSON
├── security.py             # AuditLog, RateLimiter, roles
├── hacking/                # Herramientas: network, web, crypto, payloads, osint
├── plugins/                # PluginBase + PluginManager
└── telegram_bot.py         # Bot de Telegram
cli/
├── main.py                 # CLI con Rich + Prompt Toolkit
└── display.py              # UI de terminal
scripts/                    # Scripts de instalación y config
```

## Licencia

Uso privado — repositorio interno.
