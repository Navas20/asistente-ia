#!/usr/bin/env python3
"""
Exporta o importa toda la memoria de JARVIS.
Útil para migrar de servidor o hacer backups manuales.

Uso:
  python export_import.py export output.json
  python export_import.py import input.json
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "data/conversations.db")

def export_data(output_path: str):
    """Exporta toda la base de datos a un JSON."""
    if not os.path.exists(DB_PATH):
        print(f"Error: Base de datos no encontrada: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    data = {
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "memories": [],
        "conversations": {},
        "messages_count": 0
    }

    # Memorias
    rows = conn.execute("SELECT * FROM memories").fetchall()
    for r in rows:
        data["memories"].append({
            "key": r["key"],
            "value": r["value"],
            "category": r["category"],
            "updated_at": r["updated_at"]
        })

    # Conversaciones
    conv_ids = conn.execute("SELECT DISTINCT conversation_id FROM messages").fetchall()
    for conv in conv_ids:
        cid = conv["conversation_id"]
        msgs = conn.execute(
            "SELECT role, content, tool_output, timestamp FROM messages WHERE conversation_id = ? ORDER BY id",
            (cid,)
        ).fetchall()
        data["conversations"][cid] = [
            {"role": m["role"], "content": m["content"],
             "tool_output": m["tool_output"], "timestamp": m["timestamp"]}
            for m in msgs
        ]
        data["messages_count"] += len(data["conversations"][cid])

    conn.close()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Exportado: {output_path}")
    print(f"  Memorias: {len(data['memories'])}")
    print(f"  Conversaciones: {len(data['conversations'])}")
    print(f"  Mensajes: {data['messages_count']}")

def import_data(input_path: str):
    """Importa datos desde un JSON exportado."""
    if not os.path.exists(input_path):
        print(f"Error: Archivo no encontrado: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    # Importar memorias
    imported_memories = 0
    for m in data.get("memories", []):
        conn.execute(
            "INSERT OR REPLACE INTO memories (key, value, category, updated_at) VALUES (?, ?, ?, ?)",
            (m["key"], m["value"], m.get("category", "user"), m.get("updated_at", datetime.utcnow().isoformat()))
        )
        imported_memories += 1

    # Importar conversaciones
    imported_msgs = 0
    for conv_id, msgs in data.get("conversations", {}).items():
        for m in msgs:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, tool_output, timestamp) VALUES (?, ?, ?, ?, ?)",
                (conv_id, m["role"], m["content"], m.get("tool_output"), m.get("timestamp", datetime.utcnow().isoformat()))
            )
            imported_msgs += 1

    conn.commit()
    conn.close()

    print(f"Importado: {input_path}")
    print(f"  Memorias: {imported_memories}")
    print(f"  Mensajes: {imported_msgs}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python export_import.py export|import <archivo.json>")
        sys.exit(1)

    action = sys.argv[1]
    path = sys.argv[2]

    if action == "export":
        export_data(path)
    elif action == "import":
        import_data(path)
    else:
        print(f"Acción desconocida: {action}")
        print("Usa: export o import")
        sys.exit(1)
