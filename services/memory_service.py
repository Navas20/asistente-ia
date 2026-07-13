"""
SERVICES LAYER - Servicio de Memoria (3 capas)
"""
import logging
from typing import Dict, List, Optional

from data_layer.repositories import MemoryRepository, ConversationRepository
from app.config import MAX_MEMORY_ITEMS, MAX_MEMORY_CHARS

log = logging.getLogger("artenisa.memory")


class MemoryService:
    """Servicio de memoria con 3 capas: reciente, operacional, histórica"""
    
    def __init__(self):
        self.memory_repo = MemoryRepository()
        self.conv_repo = ConversationRepository()
    
    # ─── Layer 1: Recent (Conversación actual) ───
    def get_recent_context(self, conv_id: str, limit: int = 10) -> str:
        """Obtiene contexto reciente de la conversación"""
        messages = self.conv_repo.get_messages(conv_id, limit)
        context = "\n".join([
            f"{m['role'].upper()}: {m['content'][:200]}" 
            for m in messages
        ])
        return context[:MAX_MEMORY_CHARS]
    
    # ─── Layer 2: Operational (Contexto de sesión) ───
    def store_operational_context(self, conv_id: str, context: Dict):
        """Almacena contexto operacional (objetivo, progreso, etc)"""
        self.memory_repo.store_operational(conv_id, context)
        log.info(f"Contexto operacional guardado para {conv_id}")
    
    def get_operational_context(self, conv_id: str) -> Dict:
        """Obtiene contexto operacional"""
        return self.memory_repo.get_operational(conv_id)
    
    def merge_operational_context(self, conv_id: str, updates: Dict):
        """Actualiza el contexto operacional"""
        current = self.get_operational_context(conv_id)
        current.update(updates)
        self.store_operational_context(conv_id, current)
    
    # ─── Layer 3: Historical (Registro de operaciones) ───
    def store_historical(self, target: str, operation: str, summary: str, findings: int = 0):
        """Almacena operación histórica"""
        self.memory_repo.store_historical(target, operation, summary, findings)
        log.info(f"Operación histórica registrada: {target} - {operation}")
    
    def get_history(self, target: str) -> List[Dict]:
        """Obtiene historial de operaciones por target"""
        return self.memory_repo.get_history(target)
    
    # ─── Consolidated Context ───
    def get_full_context(self, conv_id: str, target: Optional[str] = None) -> Dict:
        """Obtiene contexto consolidado (3 capas)"""
        return {
            "recent": self.get_recent_context(conv_id),
            "operational": self.get_operational_context(conv_id),
            "historical": self.get_history(target) if target else []
        }


# Instancia global
memory_service = MemoryService()
