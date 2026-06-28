#!/bin/bash
# =========================================================
# JARVIS — Arranque 1-comando
# Inicia todo en orden: Ollama → Backend → Telegram → Watchdog
# =========================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/logs"

mkdir -p "$LOG_DIR" "$PID_DIR"

echo "========================================"
echo " Iniciando JARVIS..."
echo "========================================"

# 1. Exportar variables de entorno
if [ -f "$BACKEND_DIR/.env" ]; then
    export $(grep -v '^#' "$BACKEND_DIR/.env" | xargs)
    echo "[OK] Variables de entorno cargadas"
fi
if [ -f "$BACKEND_DIR/.env.telegram" ]; then
    export $(grep -v '^#' "$BACKEND_DIR/.env.telegram" | xargs)
    echo "[OK] Variables de Telegram cargadas"
fi

# 2. Ollama
echo "[1/4] Iniciando Ollama..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    echo $! > "$PID_DIR/ollama.pid"
    sleep 3
    for i in {1..12}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo "      Ollama listo"
            break
        fi
        sleep 2
    done
else
    echo "      Ollama ya corriendo"
fi

# 3. Backend
echo "[2/4] Iniciando Backend API..."
cd "$BACKEND_DIR"
nohup python3 main.py > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$PID_DIR/backend.pid"
sleep 2
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "      Backend listo en puerto 8000"
        break
    fi
    sleep 2
done

# 4. Telegram Bot
if [ -n "${TELEGRAM_TOKEN:-}" ]; then
    echo "[3/4] Iniciando Telegram Bot..."
    nohup python3 "$BACKEND_DIR/telegram_bot.py" > "$LOG_DIR/telegram.log" 2>&1 &
    echo $! > "$PID_DIR/telegram.pid"
    echo "      Telegram Bot iniciado"
else
    echo "[3/4] TELEGRAM_TOKEN no configurado — Bot omitido"
fi

# 5. Watchdog
echo "[4/4] Iniciando Watchdog..."
nohup bash "$ROOT_DIR/scripts/watchdog.sh" > "$LOG_DIR/watchdog.log" 2>&1 &
echo $! > "$PID_DIR/watchdog.pid"
echo "      Watchdog iniciado"

# 6. Backup inicial
bash "$ROOT_DIR/scripts/backup.sh" >> "$LOG_DIR/backup.log" 2>&1 || true

echo "========================================"
echo " JARVIS operativo:"
echo "   API:    http://localhost:8000"
echo "   Web UI: http://localhost:8000/web"
echo "   Logs:   $LOG_DIR"
echo "========================================"
