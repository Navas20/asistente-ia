from fastapi import APIRouter, HTTPException, Query

from .manager import SubagentManager
from .models import SubagentTask

router = APIRouter(prefix="/subagents", tags=["subagents"])
manager = SubagentManager()


@router.post("/launch")
def launch_subagent(task: SubagentTask):
    t = manager.launch(
        name=task.name or "subagent",
        target=task.target,
        task=task.task,
        model=task.model,
        provider=task.provider or "openrouter",
        parent_id=task.parent_id,
    )
    return t.model_dump()


@router.get("")
def list_subagents(status: str | None = Query(None)):
    return [t.model_dump() for t in manager.list(status=status)]


@router.get("/{task_id}")
def get_subagent(task_id: str):
    t = manager.get(task_id)
    if not t:
        raise HTTPException(404, "Subagent task not found")
    return t


@router.post("/{task_id}/cancel")
def cancel_subagent(task_id: str):
    if not manager.cancel(task_id):
        raise HTTPException(400, "Task not running or not found")
    return {"ok": True}


@router.get("/running/count")
def running_count():
    return {"count": manager.running_count()}
