from fastapi import APIRouter, Query

from oast import OASTManager

router = APIRouter(prefix="/oast", tags=["oast"])
om = OASTManager()


@router.get("/payload")
def generate_oast_payload(payload_type: str = Query("ssrf")):
    return {"payload": om.generate_payload(payload_type), "type": payload_type}


@router.get("/poll")
def poll_interactions():
    return {"interactions": om.poll()}


@router.get("/check/{payload_id}")
def check_interactions(payload_id: str):
    return {"interactions": om.check(payload_id), "count": len(om.check(payload_id))}
