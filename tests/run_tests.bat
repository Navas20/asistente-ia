@echo off
echo.
echo === JARVIS Test Runner ===
echo.
set /p API_URL="API URL (default http://localhost:8000): "
if "%API_URL%"=="" set API_URL=http://localhost:8000
set /p AUTH_TOKEN="Auth Token: "
if "%AUTH_TOKEN%"=="" set AUTH_TOKEN=test-token
echo.
set API_URL=%API_URL%
set AUTH_TOKEN=%AUTH_TOKEN%
python "%~dp0test_api.py"
if %ERRORLEVEL% equ 0 (
    echo.
    echo [OK] Todos los tests pasaron
) else (
    echo.
    echo [FAIL] Algunos tests fallaron
)
pause
