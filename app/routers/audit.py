"""
API Router - Audit endpoints
"""
from fastapi import APIRouter, Depends, Query
import logging

from security.auth import verify_token
from security.audit import audit_service

log = logging.getLogger("artenisa.api.audit")

router = APIRouter()


@router.get("/audit/logs")
async def get_audit_logs_endpoint(
    limit: int = Query(20, le=100),
    token: str = Depends(verify_token)
):
    """Obtiene los logs de auditoría recientes"""
    
    logs = audit_service.get_recent_logs(limit)
    
    return {
        "logs": logs,
        "count": len(logs)
    }
