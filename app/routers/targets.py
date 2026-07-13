"""
API Router - Target management endpoints
"""
from fastapi import APIRouter, Depends
import logging

from security.auth import verify_token
from security.audit import audit_service

log = logging.getLogger("artenisa.api.targets")

router = APIRouter()


@router.post("/targets")
async def create_target_endpoint(
    name: str,
    target_type: str,
    token: str = Depends(verify_token)
):
    """Crea un target nuevo"""
    
    target_id = f"tgt_{name.lower().replace(' ', '_')}"
    
    audit_service.log_action(0, "api", "target/create", name, "ok")
    
    return {
        "target_id": target_id,
        "name": name,
        "type": target_type,
        "status": "created"
    }


@router.get("/targets/{target_id}")
async def get_target_endpoint(
    target_id: str,
    token: str = Depends(verify_token)
):
    """Obtiene información de un target"""
    
    audit_service.log_action(0, "api", "target/get", target_id, "ok")
    
    return {
        "target_id": target_id,
        "name": target_id.replace("tgt_", ""),
        "status": "active"
    }
