@echo off
chcp 65001 >nul
title JARVIS Deploy
echo.
echo ========================================
echo        JARVIS v4.0 — Deploy
echo ========================================
echo.
echo 1) Desplegar en Oracle Cloud (SCP + SSH)
echo 2) Docker local
echo 3) Tests locales
echo 4) Salir
echo.
choice /c 1234 /n /m "Selecciona: "
if errorlevel 4 exit /b
if errorlevel 3 goto tests
if errorlevel 2 goto docker
if errorlevel 1 goto oracle

:oracle
set /p IP="IP de la instancia Oracle: "
set /p KEY="Ruta a clave SSH (.pem): "
echo Subiendo proyecto a %IP%...
scp -i "%KEY%" -r "%~dp0.." ubuntu@%IP%:/home/ubuntu/jarvis/
echo.
echo Ejecutando setup...
ssh -i "%KEY%" ubuntu@%IP% "cd /home/ubuntu/jarvis/scripts && chmod +x setup_oracle.sh && ./setup_oracle.sh"
echo.
echo [OK] Deploy completado. SSH a la instancia y configura los tokens.
goto end

:docker
copy /Y "%~dp0..\config.env" "%~dp0..\backend\.env" 2>nul
copy /Y "%~dp0..\config.telegram.env" "%~dp0..\backend\.env.telegram" 2>nul
echo Levantando contenedores...
cd /d "%~dp0.."
docker-compose up -d
echo.
echo [OK] JARVIS corriendo en http://localhost:8000
echo       Web UI: http://localhost:8000/web
goto end

:tests
echo.
echo ========================================
echo         JARVIS Test Runner
echo ========================================
set /p API_URL="API URL (default http://localhost:8000): "
if "%API_URL%"=="" set API_URL=http://localhost:8000
set /p AUTH_TOKEN="Auth Token: "
echo.
set API_URL=%API_URL%
set AUTH_TOKEN=%AUTH_TOKEN%
python "%~dp0..\tests\test_api.py"
if %ERRORLEVEL% equ 0 (
    echo [OK] Todos los tests pasaron
) else (
    echo [FAIL] Algunos tests fallaron
)
goto end

:end
echo.
pause
