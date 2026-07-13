"""
SECURITY LAYER - Auditoría
"""
import logging
from data_layer.repositories import AuditRepository

log = logging.getLogger("artenisa.security")


class AuditService:
    """Servicio de auditoría centralizado"""
    
    def __init__(self):
        self.repo = AuditRepository()
    
    def log_action(self, user_id: int, username: str, command: str, 
                   target: str = "", status: str = "ok", details: str = ""):
        """Registra una acción en el log de auditoría"""
        try:
            self.repo.log(user_id, username, command, target, status, details)
            log.info(f"Auditoría: {username} - {command} ({status})")
        except Exception as e:
            log.error(f"Error registrando auditoría: {e}")
    
    def get_recent_logs(self, limit: int = 20):
        """Obtiene los logs recientes"""
        return self.repo.get_recent(limit)


# Instancia global
audit_service = AuditService()
