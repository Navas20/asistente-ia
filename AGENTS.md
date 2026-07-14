## Session 2026-07-14

### Stable Baseline
- Commit `a65ec1b` is on `main`: Kali/Nmap integration plus Telegram Phase 2 UX.
- Nmap was previously verified end-to-end against `scanme.nmap.org`.

### Work Completed This Session
- Added a safe generic tool catalog for the current Phase 3 tools:
  - `nmap`, `whois`, `dig`, `nslookup`, `curl`, `ping`.
- Added `ToolsEngine.run_tool()` with semantic profiles/options, per-tool timeouts,
  target validation, per-user concurrency tracking, and unique task IDs.
- Kept `run_nmap()` as a compatibility wrapper around the generic executor.
- Added authenticated `POST /v5/tools/{tool}/run` and protected all tools routes
  with the configured bearer token.
- Added TaskQueue dispatch for `type="tool"`; nonzero tool exits now fail tasks,
  and cancelled tasks cannot be overwritten as completed.
- Hardened `kali_server.py` request bounds and capped both stdout and stderr.
- Reworked `docker/kali.Dockerfile` to install current and future binaries in one
  layer and run the API as the non-root `toolrunner` user.
- Added 18 unit tests covering Kali Server, ToolsEngine, tools router, TaskQueue,
  and Dockerfile security. All 18 passed before the Docker build attempt.

### Telegram Wizard Worktree State
- `backend/telegram_bot.py` contains an uncommitted wizard refactor for Recon,
  Web, Crack, Payloads, Red, OSINT, Tareas, Ayuda, and Objetivo.
- The file parses, but the refactor still has known blockers:
  - payload formatter/result shape mismatch;
  - selected payload type/language and crack dictionary are ignored;
  - ZIP/RAR/document flow has no document handler;
  - Red is Nmap, not WiFi; OSINT types collapse to domain;
  - photo/voice handlers are not registered;
  - Back tries to edit an inline message with `ReplyKeyboardMarkup`;
  - dynamic legacy Markdown can produce Telegram `BadRequest` errors.

### Docker Blocker
- `docker compose build artenisa-kali-tools` installed all declared packages and
  exported image manifest `sha256:49cb1265d5a2109cc5e1bdf43cc2aee0ee10159fcad5b10ad88cc650461b011a`.
- Docker then failed while unpacking a large layer with an input/output error.
- Windows drive `C:` reported `Free: 0`; this is the confirmed blocker.
- The new image could not be started or verified. Do not claim it is deployed.
- Free disk space before retrying Docker. The currently running containers may
  still reference the previous image and should be inspected after cleanup.

### Verification Commands
```powershell
python -m unittest discover -s tests -p "test_kali_server.py" -v
python -m unittest discover -s tests -p "test_tools_engine.py" -v
python -m unittest discover -s tests -p "test_task_queue_tools.py" -v
python -m unittest discover -s tests -p "test_tools_router.py" -v
python -m unittest discover -s tests -p "test_kali_dockerfile.py" -v
```

### Next Steps
1. Free disk space on `C:` and restart Docker Desktop if necessary.
2. Rebuild/recreate `artenisa-kali-tools` and verify `id`, `/health`, `/tools`,
   binary paths, and generic `whois`/`dig` execution.
3. Rebuild/recreate `artenisa-backend` and rerun Nmap compatibility tests.
4. Add offline regression tests for the Telegram wizard blockers, then fix them
   one flow at a time before considering the wizard refactor complete.
5. Integrate SQLMap only after the Phase 3 generic path is deployed and verified.
