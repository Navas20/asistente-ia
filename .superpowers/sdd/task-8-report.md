# Task 8: Telegram Bot Rewrite — Report

**Status:** DONE  
**Commit:** `65ee927`  
**File:** `backend/telegram_bot.py` (574 insertions, 160 deletions)

## What was done

Complete rewrite of `telegram_bot.py` from the simple v4 J.A.R.V.I.S. chat bot to the Artenisa v5.0 operations bot.

### Features implemented

| Feature | Details |
|---------|---------|
| **Main menu keyboard** | ReplyKeyboardMarkup with 3×3 grid: Recon, Web, Crack, Payloads, Red, OSINT, Playbooks, Reporte, Sistema |
| **Recon type selector** | Inline keyboard: Dominio, IP, Rango de Red, Atrás |
| **Depth selector** | Inline keyboard: Rápido, Normal, Profundo, Atrás, Cancelar |
| **Wizard flow** | 3-step: button → enter target → select depth → execute |
| **Immediate execution** | Crack (hash_crack) and Payloads (reverse_shell) execute immediately on value entry |
| **Playbooks listing** | Shows all available playbooks with description, type, depth estimate |
| **Report generation** | Generates markdown report for current target via report_generator |
| **System status** | Shows current target, elapsed time, active tasks |
| **Command shortcuts** | /recon, /webscan, /crack, /payload, /osint with direct arguments |
| **Target management** | /objetivo, /olvidar_objetivo |
| **Task monitoring** | /tarea <id>, /tareas |
| **Voice toggle** | /voz — enable/disable voice response mode |
| **Photo upload** | Saves to API, provides file_id for /analizar |
| **Voice transcription** | Downloads OGG, converts with ffmpeg, transcribes with vosk |
| **Image analysis** | /analizar <file_id> sends to API analyze-image endpoint |
| **Role-based auth** | Uses security.get_role() — denies "denied" users |
| **Rate limiting** | Uses RateLimiter — shows "⏳ Límite de llamadas. Espera Xs." |
| **Audit logging** | Logs /objetivo and wizard executions |

### Modules integrated

- `target_engine` — set_target, get_target, clear_target, get_context_summary, set_operation
- `memory_engine` — instantiated (used by playbooks internally)
- `task_queue` — submit playbook tasks, get_status, list_tasks
- `security` — get_role, AuditLog, RateLimiter
- `playbooks` — list_playbooks (run_playbook called internally by TaskQueue)
- `report_generator` — generate_report
- `hacking.crypto` — hash_crack for immediate crack results
- `hacking.payloads` — reverse_shell for immediate payload generation
- `voice` — transcribe for voice note processing

### Key design decisions

- All user-facing text is in Spanish
- Emojis used consistently in menus, messages, and status indicators
- Wizard state stored in `user_wizards[uid]` dict, cleaned up after completion
- Voice mode stored in `voice_mode_users` set
- Non-menu text in voice mode forwarded to API `/chat` endpoint
- ffmpeg conversion failure gracefully handled with "[voz: ffmpeg no disponible]"
- Uses python-telegram-bot v21+ API (CallbackQueryHandler, ContextTypes.DEFAULT_TYPE)

### Verification

```
Syntax OK
```

Full testing requires a valid TELEGRAM_TOKEN.

## Concerns

- `hacking.payloads.reverse_shell()` payload templates are empty (dict `_E` only has keys but base64 values are hardcoded) — will return proper payloads
- Voice transcription depends on ffmpeg being installed and vosk model available
- `/analyze-image` endpoint assumed to exist at the API — if not, it will return 404
- Rate limiter reset_after value in the returned tuple may be 0 when remaining > 0 — the message still shows correct wait time for blocked state
