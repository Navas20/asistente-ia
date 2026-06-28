#!/bin/bash
# =========================================================
# JARVIS — Watchdog
# Vigila procesos y los reinicia si se detienen
# Ejecutar con: nohup ./watchdog.sh &
# =========================================================
set -e

BACKEND_DIR="${BACKEND_DIR:-/home/ubuntu/jarvis/backend}"
LOG_DIR="${LOG_DIR:-/home/ubuntu/jarvis/logs}"
CHECK_INTERVAL="${CHECK_INTERVAL:-15}"
BACKUP_INTERVAL="${BACKUP_INTERVAL:-3600}"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/watchdog.log"
}

is_running() {
    local pid_file="$1"
    local name="$2"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

start_backend() {
    log "[BACKEND] Iniciando..."
    cd "$BACKEND_DIR"
    nohup python3 main.py >> "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$LOG_DIR/backend.pid"
    log "[BACKEND] PID: $(cat $LOG_DIR/backend.pid)"
}

start_telegram() {
    if [ -z "${TELEGRAM_TOKEN:-}" ]; then
        return 0
    fi
    log "[TELEGRAM] Iniciando..."
    cd "$BACKEND_DIR"
    nohup python3 telegram_bot.py >> "$LOG_DIR/telegram.log" 2>&1 &
    echo $! > "$LOG_DIR/telegram.pid"
    log "[TELEGRAM] PID: $(cat $LOG_DIR/telegram.pid)"
}

check_ollama() {
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        log "[OLLAMA] Caído. Intentando reiniciar..."
        ollama serve > /dev/null 2>&1 &
        sleep 5
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            log "[OLLAMA] Reiniciado correctamente"
        else
            log "[OLLAMA] Error al reiniciar"
        fi
    fi
}

check_disk() {
    local usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$usage" -gt 90 ]; then
        log "[DISK] Alerta: $usage% usado"
    fi
}

run_backup() {
    cd "$BACKEND_DIR/.."
    bash scripts/backup.sh >> "$LOG_DIR/backup.log" 2>&1
}

# ─── Inicio ───

log "========================================"
log " JARVIS Watchdog iniciado"
log " Intervalo: ${CHECK_INTERVAL}s | Backup: cada ${BACKUP_INTERVAL}s"
log "========================================"

BACKUP_COUNTER=0

while true; do
    # Verificar Ollama
    check_ollama

    # Verificar Backend
    if ! is_running "$LOG_DIR/backend.pid" "BACKEND"; then
        log "[BACKEND] Caído. Reiniciando..."
        start_backend
        sleep 2
        # Esperar a que el backend esté listo antes del bot
        for i in {1..10}; do
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                log "[BACKEND] Listo"
                break
            fi
            sleep 2
        done
        start_telegram
    fi

    # Verificar Telegram Bot
    if [ -n "${TELEGRAM_TOKEN:-}" ]; then
        if ! is_running "$LOG_DIR/telegram.pid" "TELEGRAM"; then
            log "[TELEGRAM] Caído. Reiniciando..."
            start_telegram
        fi
    fi

    # Disco
    check_disk

    # Backup periódico
    BACKUP_COUNTER=$((BACKUP_COUNTER + CHECK_INTERVAL))
    if [ "$BACKUP_COUNTER" -ge "$BACKUP_INTERVAL" ]; then
        run_backup
        BACKUP_COUNTER=0
    fi

    sleep "$CHECK_INTERVAL"
done
