#!/bin/bash
# =========================================================
# JARVIS — Parada ordenada
# =========================================================

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$ROOT_DIR/logs"

echo "========================================"
echo " Deteniendo JARVIS..."
echo "========================================"

stop_process() {
    local pid_file="$1"
    local name="$2"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            sleep 1
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            echo "[OK] $name detenido (PID $pid)"
        fi
        rm -f "$pid_file"
    fi
}

stop_process "$PID_DIR/watchdog.pid" "Watchdog"
stop_process "$PID_DIR/telegram.pid" "Telegram Bot"
stop_process "$PID_DIR/backend.pid" "Backend"

echo "========================================"
echo " JARVIS detenido"
echo "========================================"
