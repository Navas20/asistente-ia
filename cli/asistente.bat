@echo off
setlocal

if "%API_URL%"=="" (
    set /p API_URL="URL del servidor (ej: http://192.168.1.100:8000): "
)
if "%AUTH_TOKEN%"=="" (
    set /p AUTH_TOKEN="Token de autenticacion: "
)

python "%~dp0asistente.py"
