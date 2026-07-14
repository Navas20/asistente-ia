@echo off
cd /d "C:\Users\ASUS\Documents\Mis proyectos\asistente-ia"
set AUTH_TOKEN=artenisa-secret-token-2026
set API_URL=http://localhost:8765
set PORT=8765

REM Start backend in background
cd backend
start /b python -m uvicorn main:app --host 0.0.0.0 --port 8765 > ..\data\backend.log 2>&1
cd ..

REM Wait for backend
echo Starting backend...
:wait
timeout /t 2 /nobreak >nul
powershell -Command "try { $r = Invoke-RestMethod -Uri 'http://localhost:8765/health' -TimeoutSec 2 -ErrorAction Stop; if ($r.status -eq 'healthy') { exit 0 } } catch {}; exit 1" >nul 2>&1
if errorlevel 1 goto wait

echo Backend ready!

REM Open CLI
cd cli
python asistente.py
