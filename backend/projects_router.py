from fastapi import APIRouter, HTTPException

from projects import ProjectManager

router = APIRouter(prefix="/projects", tags=["projects"])
pm = ProjectManager()


@router.post("")
def create_project(data: dict):
    name = data.get("name", "Untitled")
    target = data.get("target", "")
    description = data.get("description", "")
    return pm.create(name, target, description)


@router.get("")
def list_projects():
    return pm.list()


@router.get("/active")
def get_active_project():
    p = pm.get_active()
    if not p:
        return {}
    return p


@router.get("/{project_id}")
def get_project(project_id: str):
    p = pm.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.patch("/{project_id}")
def update_project(project_id: str, data: dict):
    p = pm.update(project_id, data)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.delete("/{project_id}")
def delete_project(project_id: str):
    if not pm.delete(project_id):
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@router.post("/{project_id}/activate")
def activate_project(project_id: str):
    p = pm.set_active(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.post("/deactivate")
def deactivate_project():
    pm.clear_active()
    return {"ok": True}
