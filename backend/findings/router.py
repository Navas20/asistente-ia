from fastapi import APIRouter, HTTPException, Query

from .engine import FindingsManager
from .models import Finding
from .review import auto_review

router = APIRouter(prefix="/findings", tags=["findings"])
fm = FindingsManager()


@router.get("")
def list_findings(
    host: str | None = Query(None),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    phase: str | None = Query(None),
    tool: str | None = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
):
    return [
        f.model_dump() for f in fm.list(
            host=host, severity=severity, status=status,
            phase=phase, tool=tool, limit=limit, offset=offset
        )
    ]


@router.get("/summary")
def findings_summary():
    return fm.summary().model_dump()


@router.get("/{finding_id}")
def get_finding(finding_id: str):
    f = fm.get(finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    return f.model_dump()


@router.patch("/{finding_id}")
def update_finding(finding_id: str, data: dict):
    if "status" in data:
        fm.update_status(finding_id, data["status"])
    f = fm.get(finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    return f.model_dump()


@router.delete("/{finding_id}")
def delete_finding(finding_id: str):
    if not fm.delete(finding_id):
        raise HTTPException(404, "Finding not found")
    return {"ok": True}


@router.post("/verify/{finding_id}")
def verify_finding(finding_id: str):
    f = fm.get(finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    fm.update_status(finding_id, "verified")
    return {"ok": True, "status": "verified"}


@router.get("/export")
def export_findings(format: str = Query("json")):
    return {"data": fm.export(format)}


@router.delete("")
def clear_findings(host: str | None = Query(None), phase: str | None = Query(None)):
    fm.clear(host=host, phase=phase)
    return {"ok": True}


@router.post("/review")
def review_findings():
    result = auto_review()
    return result

