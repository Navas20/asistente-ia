"""
API Router - Task queue endpoints
"""
from fastapi import APIRouter, Depends, Query
import logging

from security.auth import verify_token
from security.audit import audit_service
from data_layer.repositories import TaskRepository

log = logging.getLogger("artenisa.api.tasks")

router = APIRouter()
task_repo = TaskRepository()


@router.get("/tasks")
async def list_tasks_endpoint(
    limit: int = Query(10, le=100),
    token: str = Depends(verify_token)
):
    """Lista las tareas"""
    
    tasks = task_repo.list_tasks(limit)
    
    audit_service.log_action(0, "api", "tasks/list", "", "ok")
    
    return {
        "tasks": tasks,
        "count": len(tasks)
    }


@router.get("/tasks/{task_id}")
async def get_task_endpoint(
    task_id: str,
    token: str = Depends(verify_token)
):
    """Obtiene el estado de una tarea"""
    
    task = task_repo.get_task(task_id)
    if not task:
        return {"error": "Tarea no encontrada"}
    
    audit_service.log_action(0, "api", "tasks/get", task_id, "ok")
    
    return task
