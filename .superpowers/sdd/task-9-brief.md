# Task 9: Backend Integration

## Files
Modify: `backend/main.py` — add v5 endpoints
Modify: `backend/requirements.txt` — add dnspython

## New endpoints to add to main.py (after existing endpoints)

### Target Engine
- `GET /v5/target` — returns `target_engine.get_target(0)` (user_id=0 for API)
- `POST /v5/target` — body: `{"target": "...", "target_type": "domain"}`, calls `target_engine.set_target(0, ...)`

### Playbooks
- `GET /v5/playbooks` — returns `list_playbooks()`
- `POST /v5/playbooks/{name}` — body: `{"target": "...", "depth": "rapido"}`, submits task via task_queue, returns `{"task_id": "...", "status": "queued"}`

### Tasks
- `GET /v5/tasks` — returns `{"tasks": task_queue.list_tasks()}`
- `GET /v5/tasks/{task_id}` — returns `task_queue.get_status(task_id)`
- `POST /v5/tasks/{task_id}/cancel` — returns `{"status": "cancelled"}`

### Reports
- `POST /v5/report` — body: `{"target": "...", "format": "md", "results": [], "playbook": "..."}`, returns `generate_report(...)`

### Hacking tools
- `POST /v5/hacking/{tool}` — body: `{"target": "..."}`, calls `getattr(hacking, tool)(target)`, returns result

### Audit
- `GET /v5/audit` — returns `{"entries": audit_log.get_recent(50)}`

### Memory
- `POST /v5/memory/operational` — body: `{"conversation_id": "...", "context": {...}}`, stores operational memory
- `GET /v5/memory/operational/{conv_id}` — returns operational memory
- `GET /v5/memory/history/{target}` — returns historical memory

## Dependencies to add
In `backend/main.py`, add near the top (after existing imports):
```python
from target_engine import TargetEngine
from memory_engine import MemoryEngine
from task_queue import TaskQueue
from security import AuditLog, RateLimiter
from playbooks import list_playbooks, run_playbook
from report_generator import generate_report
import hacking
```

Initialize instances after `init_db()`:
```python
_target_engine = TargetEngine()
_memory_engine = MemoryEngine()
_task_queue = TaskQueue()
_audit_log = AuditLog()
_rate_limiter = RateLimiter()
```

## requirements.txt
Change the existing line `# dnspython` to `dnspython>=2.6.0` (uncomment/ensure it's listed).

## Testing
```powershell
cd C:\Users\ASUS\asistente-ia
python -c "from backend.main import app; print('App loaded OK')"
```

## Commit
```bash
git add backend/main.py backend/requirements.txt
git commit -m "feat: v5.0 backend integration - new endpoints for target, playbooks, tasks, reports, hacking, audit, memory"
```

Write report to `C:\Users\ASUS\asistente-ia\.superpowers\sdd\task-9-report.md`.

Return: DONE/BLOCKED, commit hash, test summary, concerns
