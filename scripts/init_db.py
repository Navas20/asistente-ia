#!/usr/bin/env python3
"""
Script de inicialización - Crea tablas y estructura base
"""
import sys
import os
from pathlib import Path

# Agregar raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import DB_PATH, UPLOAD_DIR, REPORTS_DIR, AUDIO_DIR
from data_layer.repositories import (
    ConversationRepository, MemoryRepository, FileRepository,
    AuditRepository, TaskRepository, DatabaseConnection
)


def init_database():
    """Inicializa todas las tablas y directorios"""
    
    print("🔧 Inicializando Artenisa v4.1...")
    print()
    
    # 1. Crear directorios
    print("📁 Creando directorios...")
    for d in [UPLOAD_DIR, REPORTS_DIR, AUDIO_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {d}")
    print()
    
    # 2. Inicializar repositorios (crean tablas automáticamente)
    print("📊 Inicializando tablas de BD...")
    
    try:
        conv_repo = ConversationRepository()
        print("  ✓ messages")
        
        mem_repo = MemoryRepository()
        print("  ✓ operation_context")
        print("  ✓ operation_history")
        
        file_repo = FileRepository()
        print("  ✓ files")
        
        audit_repo = AuditRepository()
        print("  ✓ audit_log")
        
        task_repo = TaskRepository()
        print("  ✓ tasks.json")
    
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    print()
    print("✅ Inicialización completada!")
    print()
    print(f"📌 BD: {DB_PATH}")
    print(f"📁 Uploads: {UPLOAD_DIR}")
    print(f"📁 Reports: {REPORTS_DIR}")
    print(f"📁 Audio: {AUDIO_DIR}")
    print()
    print("🚀 Para iniciar el servidor:")
    print("   python -m app.main")
    print("   o")
    print("   uvicorn app.main:app --reload")
    print()
    
    return True


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
