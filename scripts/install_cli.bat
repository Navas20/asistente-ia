@echo off
REM Instala el CLI de Artenisa (CMD version)

echo Instalando CLI de Artenisa...
echo.

REM Detectar ruta del proyecto
set "PROJECT_ROOT=%~dp0.."
set "CLI_SCRIPT=%PROJECT_ROOT%\cli\asistente.py"

echo Proyecto: %PROJECT_ROOT%
echo CLI: %CLI_SCRIPT%
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en PATH
    exit /b 1
)

REM Crear batch wrapper
set "WRAPPER=%USERPROFILE%\artenisa.bat"

echo @echo off > "%WRAPPER%"
echo python "%CLI_SCRIPT%" %%* >> "%WRAPPER%"

echo Wrapper creado en: %WRAPPER%
echo.

REM Agregar al PATH si no existe
echo %PATH% | find /i "%USERPROFILE%" >nul
if errorlevel 1 (
    echo ADVERTENCIA: %USERPROFILE% no esta en PATH
    echo Agrega esta ruta manualmente a las variables de entorno
)

echo.
echo Instalacion completada!
echo.
echo Proximos pasos:
echo   1. Abre una nueva ventana de CMD
echo   2. Ejecuta: artenisa
echo.
pause
