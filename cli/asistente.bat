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

if "%API_URL%"=="" (
    set /p API_URL="URL del servidor (ej: http://192.168.1.100:8000): "
)
if "%AUTH_TOKEN%"=="" (
    set /p AUTH_TOKEN="Token de autenticacion: "
)

python "%~dp0asistente.py"
