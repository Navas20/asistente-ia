#!/bin/bash
# =========================================================
# JARVIS v4.0 — Setup completo para Oracle Cloud
# =========================================================
set -e

ROOT_DIR="/home/ubuntu/jarvis"
LOG_DIR="$ROOT_DIR/logs"

echo "========================================"
echo " JARVIS v4.0 — Instalación completa"
echo "========================================"

echo ""
echo "[1/8] Actualizando sistema..."
sudo apt update && sudo apt upgrade -y

echo ""
echo "[2/8] Instalando herramientas de pentesting..."
sudo apt install -y \
    python3-pip python3-venv \
    nmap curl wget netcat-openbsd dnsutils whois \
    sqlmap nikto gobuster dirb whatweb \
    sslscan enum4linux smbclient \
    ffmpeg espeak-ng \
    && sudo apt clean

echo ""
echo "[3/8] Instalando Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo ""
echo "[4/8] Dependencias Python..."
cd "$ROOT_DIR"
pip3 install --upgrade pip
pip3 install -r backend/requirements.txt

echo ""
echo "[5/8] Descargando WhiteRabbitNeo 2.5 7B..."
ollama pull whiterabbitneo:7b

echo ""
echo "[6/8] Creando modelo personalizado JARVIS..."
ollama create personal -f "$ROOT_DIR/modelfiles/personal.modelfile"

echo ""
echo "[7/8] Preparando directorios..."
mkdir -p "$ROOT_DIR/backend/data/uploads"
mkdir -p "$ROOT_DIR/backend/data/audio"
mkdir -p "$LOG_DIR"
mkdir -p "/home/ubuntu/backups/jarvis"

echo ""
echo "[8/8] Configurando permisos..."
chmod +x "$ROOT_DIR/scripts/"*.sh
chmod +x "$ROOT_DIR/scripts/"*.py 2>/dev/null || true

echo ""
echo "========================================"
echo " Instalación completada!"
echo ""
echo " PARA INICIAR:"
echo "   1. Configura los tokens:"
echo "      nano $ROOT_DIR/backend/.env"
echo "      nano $ROOT_DIR/backend/.env.telegram"
echo ""
echo "   2. Arranca todo con 1 comando:"
echo "      cd $ROOT_DIR && bash scripts/start.sh"
echo ""
echo "   3. Monitorear:"
echo "      tail -f $LOG_DIR/watchdog.log"
echo ""
echo "   4. Probar:"
echo "      cd $ROOT_DIR/tests && python3 test_api.py"
echo ""
echo "   5. Backup manual:"
echo "      bash scripts/backup.sh"
echo ""
echo " COMANDOS RÁPIDOS:"
echo "   Iniciar:   bash scripts/start.sh"
echo "   Detener:   bash scripts/stop.sh"
echo "   Logs:      tail -f $LOG_DIR/backend.log"
echo "   API:       curl http://localhost:8000"
echo "   Web UI:    http://<IP>:8000/web"
echo "========================================"
