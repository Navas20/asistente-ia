# Task 8: Telegram Bot Rewrite

## File
Modify: `backend/telegram_bot.py` — complete rewrite

## Keyboard Layouts

### Main menu (ReplyKeyboardMarkup)
```
[🔍 Recon] [🌐 Web] [🔑 Crack]
[💣 Payloads] [📡 Red] [🔎 OSINT]
[📚 Playbooks] [📄 Reporte] [⚙️ Sistema]
```

### Inline keyboards for wizards

**Recon type selection:**
```
[🌐 Dominio] [🖥️ IP]
[📡 Rango de Red] [🔙 Atrás]
```

**Depth selection:**
```
[⚡ Rápido] [🔎 Normal] [🧠 Profundo]
[🔙 Atrás]
```

**Cancel button:**
```
[❌ Cancelar]
```

## Imports needed
```python
from target_engine import TargetEngine
from memory_engine import MemoryEngine
from task_queue import TaskQueue
from security import AuditLog, RateLimiter, get_role
from playbooks import list_playbooks, run_playbook
from report_generator import generate_report
import hacking
import httpx  # for calling main API
```

## Global state
```python
target_engine = TargetEngine()
memory_engine = MemoryEngine()
task_queue = TaskQueue()
audit_log = AuditLog()
rate_limiter = RateLimiter()
user_wizards = {}   # user_id -> wizard state dict
user_depths = {}    # user_id -> depth preference
```

## Command handlers

### /start
- Check role via `get_role(uid)`, reject if "denied"
- Show main keyboard
- If target is set, show target context summary

### Handle text (non-command)
Match text to menu buttons:
- "🔍 Recon" → show recon type inline keyboard, set wizard state
- "🌐 Web" → ask for URL, set wizard
- "🔑 Crack" → ask for hash, set wizard
- "💣 Payloads" → ask for IP:port, set wizard
- "📡 Red" → ask for IP/range, set wizard
- "🔎 OSINT" → ask for domain/email, set wizard
- "📚 Playbooks" → list playbooks as text
- "📄 Reporte" → generate report for current target
- "⚙️ Sistema" → show status: target, task, elapsed

### Command handlers
- `/objetivo <target>` — set target
- `/olvidar_objetivo` — clear target
- `/voz` — toggle voice mode
- `/tarea <id>` — show task status
- `/tareas` — list all tasks
- `/analizar <file_id>` — OCR analyze image
- `/recon`, `/webscan`, `/crack`, `/payload`, `/osint` — text-based shortcuts

### CallbackQuery handler
Handle:
- `wizard:recon:dominio|ip|red` → set wizard type, ask for target
- `depth:rapido|normal|profundo` → set depth, execute wizard
- `menu:main` → return to main menu
- `action:cancel` → cancel wizard
- `action:confirm` → confirm and execute

### Wizard flow (for recon/web/osint/red)
1. User clicks button → wizard state set
2. User types target → stored in wizard
3. Depth selection shown as inline keyboard
4. User selects depth → execute wizard:
   - Set target in TargetEngine
   - Submit task to TaskQueue
   - Reply with task ID and status message

### Wizard for crack/payload
1. User clicks button → wizard asks for hash/IP
2. User enters value → execute immediately (no depth needed):
   - Crack: call `hacking.crypto.hash_crack`, show result
   - Payload: call `hacking.payloads.reverse_shell`, show shells

### Photo handler (`filters.PHOTO`)
- Download photo, upload to Artenisa API
- Reply with file_id and /analizar instructions

### Voice handler (`filters.VOICE`)
- Download voice note (OGG)
- Convert to WAV with ffmpeg (or mark as unavailable if ffmpeg missing)
- Transcribe with vosk if available
- Reply with transcription text

## All text in Spanish
All user-facing strings, menus, labels, error messages, status updates must be in Spanish.

## Error handling
- Rate limiting: check `rate_limiter.check(f"user:{uid}")`, reply "⏳ Límite de llamadas. Espera Xs."
- Role checking: `get_role(uid) == "denied"` → "❌ No autorizado"
- All API calls wrapped in try/except with user-friendly Spanish messages

## Commit
```bash
git add backend/telegram_bot.py
git commit -m "feat: telegram bot rewrite - keyboards, wizards, voice, images, playbooks"
```

Write report to `C:\Users\ASUS\asistente-ia\.superpowers\sdd\task-8-report.md`.

Return: DONE/BLOCKED, commit hash, test summary, concerns
