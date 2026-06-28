#!/bin/bash
# =========================================================
# JARVIS — Backup Automático
# Respalda: Base de datos, memoria, archivos, config
# =========================================================
set -e

BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/backups/jarvis}"
DATA_DIR="${DATA_DIR:-/home/ubuntu/jarvis/backend/data}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="$BACKUP_DIR/$TIMESTAMP"

mkdir -p "$BACKUP_PATH"

echo "========================================"
echo " JARVIS Backup — $TIMESTAMP"
echo "========================================"

# 1. Base de datos SQLite
if [ -f "$DATA_DIR/conversations.db" ]; then
    sqlite3 "$DATA_DIR/conversations.db" ".backup '$BACKUP_PATH/conversations.db'"
    echo "[OK] Base de datos respaldada"
else
    echo "[!] No se encontró la base de datos"
fi

# 2. Memoria (dump JSON legible)
if [ -f "$DATA_DIR/conversations.db" ]; then
    sqlite3 "$DATA_DIR/conversations.db" \
        "SELECT json_object('key', key, 'value', value, 'category', category, 'updated_at', updated_at) FROM memories;" \
        > "$BACKUP_PATH/memories.json" 2>/dev/null
    echo "[OK] Memoria exportada a JSON"
fi

# 3. Archivos subidos
if [ -d "$DATA_DIR/uploads" ] && [ "$(ls -A $DATA_DIR/uploads 2>/dev/null)" ]; then
    cp -r "$DATA_DIR/uploads" "$BACKUP_PATH/uploads"
    echo "[OK] Archivos subidos respaldados"
fi

# 4. Configuración
if [ -f "/home/ubuntu/jarvis/backend/.env" ]; then
    cp "/home/ubuntu/jarvis/backend/.env" "$BACKUP_PATH/.env"
    echo "[OK] Config respaldada"
fi

# 5. Comprimir
cd "$BACKUP_DIR"
tar -czf "$TIMESTAMP.tar.gz" "$TIMESTAMP" 2>/dev/null
rm -rf "$TIMESTAMP"
echo "[OK] Backup comprimido: $BACKUP_DIR/$TIMESTAMP.tar.gz"

# 6. Limpiar backups antiguos
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null
echo "[OK] Backups antiguos (>${RETENTION_DAYS}d) eliminados"

echo "========================================"
echo " Backup completado: $(du -sh $BACKUP_DIR/$TIMESTAMP.tar.gz | cut -f1)"
echo "========================================"
