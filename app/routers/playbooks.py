"""
API Router - Playbook endpoints
"""
from fastapi import APIRouter, Depends
import logging

from security.auth import verify_token
from security.audit import audit_service

log = logging.getLogger("artenisa.api.playbooks")

router = APIRouter()


@router.get("/playbooks")
async def list_playbooks_endpoint(
    token: str = Depends(verify_token)
):
    """Lista todos los playbooks disponibles"""
    
    playbooks = [
        {
            "name": "network_discovery",
            "description": "Descubrimiento de red y escaneo de puertos",
            "tools": ["scan_ports", "banner_grab", "dns_enum"]
        },
        {
            "name": "web_audit",
            "description": "Auditoría de seguridad web",
            "tools": ["dir_bruteforce", "check_sqli", "check_xss"]
        },
        {
            "name": "osint",
            "description": "Inteligencia de fuentes abiertas",
            "tools": ["ip_geo", "email_osint", "cert_transparency"]
        }
    ]
    
    audit_service.log_action(0, "api", "playbooks/list", "", "ok")
    
    return {
        "playbooks": playbooks,
        "count": len(playbooks)
    }


@router.post("/playbooks/run")
async def run_playbook_endpoint(
    name: str,
    target: str,
    depth: str = "rapido",
    token: str = Depends(verify_token)
):
    """Ejecuta un playbook"""
    
    try:
        # TODO: Implementar lógica de ejecución
        result = {
            "playbook": name,
            "target": target,
            "depth": depth,
            "status": "queued",
            "task_id": "TASK_001"
        }
        
        audit_service.log_action(0, "api", "playbook/run", target, "ok", f"Playbook: {name}")
        
        return result
    
    except Exception as e:
        audit_service.log_action(0, "api", "playbook/run", target, "error", str(e))
        return {"error": str(e)}
