@echo off
setlocal
set PYTHONIOENCODING=utf-8

if "%API_URL%"=="" (
    if exist "%~dp0..\backend\.env" (
        for /f "usebackq tokens=1* delims==" %%A in (`findstr /b /c:"API_URL=" "%~dp0..\backend\.env"`) do set "API_URL=%%~B"
    )
)

if "%AUTH_TOKEN%"=="" (
    if exist "%~dp0..\backend\.env" (
        for /f "usebackq tokens=1* delims==" %%A in (`findstr /b /c:"AUTH_TOKEN=" "%~dp0..\backend\.env"`) do set "AUTH_TOKEN=%%~B"
    )
)

if "%API_URL%"=="" set "API_URL=http://localhost:8000"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\ensure_backend.ps1" -SkipCli
python "%~dp0asistente.py"
