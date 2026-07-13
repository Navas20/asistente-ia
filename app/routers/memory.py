"""
API Router - Memory endpoints
"""
from fastapi import APIRouter, Depends
import logging

from security.auth import verify_token
from security.audit import audit_service
from services import memory_service

log = logging.getLogger("artenisa.api.memory")

router = APIRouter()


@router.get("/memory/{conversation_id}")
async def get_memory_endpoint(
    conversation_id: str,
    token: str = Depends(verify_token)
):
    """Obtiene el contexto completo de memoria"""
    
    context = memory_service.get_full_context(conversation_id)
    
    audit_service.log_action(0, "api", "memory/get", conversation_id, "ok")
    
    return {
        "conversation_id": conversation_id,
        "context": context
    }


@router.post("/memory/{conversation_id}")
async def store_memory_endpoint(
    conversation_id: str,
    context: dict,
    token: str = Depends(verify_token)
):
    """Almacena contexto operacional"""
    
    memory_service.store_operational_context(conversation_id, context)
    
    audit_service.log_action(0, "api", "memory/store", conversation_id, "ok")
    
    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "message": "Contexto almacenado"
    }


@router.get("/memory/history/{target}")
async def get_history_endpoint(
    target: str,
    token: str = Depends(verify_token)
):
    """Obtiene el historial de operaciones por target"""
    
    history = memory_service.get_history(target)
    
    audit_service.log_action(0, "api", "memory/history", target, "ok")
    
    return {
        "target": target,
        "history": history,
        "count": len(history)
    }
