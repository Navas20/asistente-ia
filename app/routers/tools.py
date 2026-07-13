"""
API Router - Tool execution endpoints
"""
from fastapi import APIRouter, Depends
import logging

from security.auth import verify_token
from security.audit import audit_service

log = logging.getLogger("artenisa.api.tools")

router = APIRouter()


@router.post("/tools/web-search")
async def web_search_endpoint(
    query: str,
    token: str = Depends(verify_token)
):
    """Ejecuta una búsqueda web"""
    
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=10)
        
        audit_service.log_action(0, "api", "tool/web-search", query, "ok")
        
        return {
            "query": query,
            "results": results,
            "count": len(results)
        }
    
    except Exception as e:
        audit_service.log_action(0, "api", "tool/web-search", query, "error", str(e))
        return {"error": str(e)}


@router.post("/tools/file-read")
async def file_read_endpoint(
    path: str,
    token: str = Depends(verify_token)
):
    """Lee un archivo"""
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        audit_service.log_action(0, "api", "tool/file-read", path, "ok")
        
        return {
            "path": path,
            "content": content[:5000],  # Limita a 5KB
            "size": len(content)
        }
    
    except Exception as e:
        audit_service.log_action(0, "api", "tool/file-read", path, "error", str(e))
        return {"error": str(e)}


@router.post("/tools/file-write")
async def file_write_endpoint(
    path: str,
    content: str,
    token: str = Depends(verify_token)
):
    """Escribe en un archivo"""
    
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        
        audit_service.log_action(0, "api", "tool/file-write", path, "ok")
        
        return {
            "path": path,
            "status": "written",
            "size": len(content)
        }
    
    except Exception as e:
        audit_service.log_action(0, "api", "tool/file-write", path, "error", str(e))
        return {"error": str(e)}
