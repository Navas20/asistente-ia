"""
API Router - Agent endpoints (Hacking Agent)
"""
from fastapi import APIRouter, Depends, Body
import logging

from app.models import Message
from security.auth import verify_token
from security.audit import audit_service
from agents import hacking_agent

log = logging.getLogger("artenisa.api.agent")

router = APIRouter()


@router.post("/agent/activate")
async def activate_agent(token: str = Depends(verify_token)):
    """Activa el agente de hacking (modo operativo)"""
    
    result = hacking_agent.activate()
    
    audit_service.log_action(0, "api", "agent/activate", "hacking_agent", "ok")
    
    return {
        "status": "activated" if hacking_agent.active else "error",
        "message": result
    }


@router.post("/agent/deactivate")
async def deactivate_agent(token: str = Depends(verify_token)):
    """Desactiva el agente de hacking (modo seguro)"""
    
    result = hacking_agent.deactivate()
    
    audit_service.log_action(0, "api", "agent/deactivate", "hacking_agent", "ok")
    
    return {
        "status": "deactivated" if not hacking_agent.active else "error",
        "message": result
    }


@router.post("/agent/start")
async def start_operation(
    target: str = Body(..., embed=True),
    token: str = Depends(verify_token)
):
    """Inicia una operación contra un target"""
    
    result = hacking_agent.start_operation(target)
    
    audit_service.log_action(0, "api", "agent/start", target, "ok")
    
    return {
        "status": "started",
        "target": target,
        "message": result
    }


@router.get("/agent/status")
async def get_agent_status(token: str = Depends(verify_token)):
    """Obtiene el estado del agente"""
    
    result = hacking_agent.get_status()
    
    audit_service.log_action(0, "api", "agent/status", "", "ok")
    
    return {
        "active": hacking_agent.active,
        "target": hacking_agent.current_target,
        "message": result
    }


@router.get("/agent/summary")
async def get_agent_summary(token: str = Depends(verify_token)):
    """Obtiene el resumen de la operación"""
    
    result = hacking_agent.get_summary()
    
    audit_service.log_action(0, "api", "agent/summary", "", "ok")
    
    return {
        "summary": result,
        "target": hacking_agent.current_target,
        "session_data": hacking_agent.session_data
    }


@router.post("/agent/attack")
async def execute_attack(
    attack_type: str = Body(...),
    params: dict = Body(...),
    token: str = Depends(verify_token)
):
    """Ejecuta un ataque específico"""
    
    result = hacking_agent.execute_attack(attack_type, params)
    
    audit_service.log_action(0, "api", "agent/attack", attack_type, "ok", str(params))
    
    return {
        "status": "executed",
        "attack_type": attack_type,
        "result": result
    }


@router.post("/agent/save")
async def save_progress(token: str = Depends(verify_token)):
    """Guarda el progreso de la operación"""
    
    result = hacking_agent.save_progress()
    
    audit_service.log_action(0, "api", "agent/save", "", "ok")
    
    return {
        "status": "saved",
        "message": result
    }


@router.post("/agent/end")
async def end_operation(token: str = Depends(verify_token)):
    """Finaliza la operación actual"""
    
    result = hacking_agent.end_operation()
    
    audit_service.log_action(0, "api", "agent/end", "", "ok")
    
    return {
        "status": "ended",
        "message": result
    }


@router.get("/agent/prompt")
async def get_prompt(token: str = Depends(verify_token)):
    """Obtiene el prompt maestro completo"""
    
    prompt = hacking_agent.load_prompt()
    
    audit_service.log_action(0, "api", "agent/prompt", "", "ok")
    
    return {
        "prompt": prompt,
        "length": len(prompt)
    }
