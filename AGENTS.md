## Session 2026-06-28

### Done
- Fixed backend `main.py` to read `AUTH_TOKEN` from `.env` alongside env var
- Fixed CLI `asistente.py` to read `AUTH_TOKEN` from `backend/.env` automatically
- Replaced all `shell=True` with `shlex.split()` across backend/main.py, llama_backend.py, workflows.py, CLI
- Replaced bare `except:` with specific exceptions everywhere
- Added `OLLAMA_TIMEOUT` env var (default 60s)
- Added exponential backoff retry in llama_backend.py (2 attempts, sleep 2^n)
- Added file upload validation: `ALLOWED_EXTENSIONS` + `MAX_UPLOAD_SIZE` (20MB)
- Added CORS `ALLOWED_ORIGINS` env var (default localhost:5173,3000)
- Default token `"cambia-este-token-urgentemente"` replaced with `os.urandom(32).hex()`
- Installed Microsoft Visual C++ 2015-2022 Redistributable via `vc_redist.x64.exe`
- Pushed all fixes to `main`
- Committed files: backend/main.py, cli/asistente.py
- Commit hash: `64a8fe7`

### Blockers
- Ollama llama-server crashes with: `exit status 0xc0000135: hs was not found`
- VC++ Redistributable installed but old ollama process (PID 28872) can't be killed (no admin perms)
- Need user to manually **restart Ollama** (system tray → Quit, reopen) or **reboot PC**

### Next Steps
- After Ollama restarts, test full chain: `curl http://localhost:11434/api/generate -d "{\"model\":\"personal\",\"prompt\":\"Hola\",\"stream\":false}"`
- Start Artenisa backend: `cd backend && python main.py`
- Start Artenisa CLI: `cd cli && python asistente.py`
- If Ollama still fails, check if the model `personal` needs to be recreated
