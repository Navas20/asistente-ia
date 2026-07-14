## Session 2026-07-14

### Done
- Instalado Graphify, generado grafo del proyecto (988 nodos, 79 comunidades)
- Docker Desktop activado, contenedores `artenisa-backend` (puerto 8000) y `artenisa-telegram-bot` funcionando
- Agregado DNS explícito (8.8.8.8, 1.1.1.1) a docker-compose.yml
- `ALLOWED_USER_IDS` unificado a plural, Ollama removido del Dockerfile
- Chat IA desde Telegram funciona con OpenRouter (`google/gemma-4-26b-a4b-it:free`)
- Herramientas de hacking verificadas funcionales desde el backend
- Playwright instalado en Dockerfile (Chromium descargado)
- Integrado `screenshot()` como herramienta de hacking + paso en playbook `web_audit`
- Modificado `/tarea` en Telegram para mostrar screenshot y resumen al completarse
- Corregido Markdown malformado en respuestas del LLM (fallback a texto plano)

### Files Modified This Session
- `backend/hacking/web.py` — Nueva función `screenshot(url)` con Playwright
- `backend/hacking/__init__.py` — Exportada `screenshot`
- `backend/playbooks.py` — Paso `screenshot` agregado a `web_audit`
- `backend/telegram_bot.py` — `/tarea` muestra resultados + foto
- `docker-compose.yml` — DNS, variables de entorno
- `Dockerfile` — Playwright + Chromium
- `.env` — Token, modelo, `ALLOWED_USER_IDS`

### Next Steps
- Probar web_audit desde Telegram: "🌐 Web" → URL → profundidad → `/tarea <id>`
- Verificar screenshot se recibe como foto en el chat
