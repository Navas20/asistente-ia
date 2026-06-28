@echo off
setlocal
set PYTHONIOENCODING=utf-8
set AUTH_TOKEN=test-token
set API_URL=http://localhost:8000
python "%~dp0asistente.py"
