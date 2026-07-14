import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tools_engine import (
    TOOL_SCAN_TYPES,
    TOOL_SPECS,
    list_tool_specs,
    tools_engine,
    validate_tool_target,
)


def require_tools_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("AUTH_TOKEN", "")
    if not authorization or not expected:
        raise HTTPException(401, "Token requerido")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != expected:
        raise HTTPException(401, "Token inválido")


class ToolRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1, max_length=2048)
    profile: str = "default"
    options: dict = Field(default_factory=dict)
    timeout: int | None = Field(default=None, ge=1, le=600)


class NmapRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1, max_length=512)
    scan_type: str = "normal"
    timeout: int | None = Field(default=None, ge=1, le=600)


router = APIRouter(
    prefix="/v5/tools",
    tags=["tools"],
    dependencies=[Depends(require_tools_token)],
)


@router.get("")
def list_tools():
    return {"tools": list_tool_specs()}


@router.get("/nmap/scan-types")
def get_nmap_scan_types():
    return {"scan_types": TOOL_SCAN_TYPES}


@router.post("/nmap/run")
def run_nmap(data: NmapRunRequest):
    target = data.target.strip()
    error = validate_tool_target("nmap", target)
    if error:
        raise HTTPException(400, error)

    scan_type = data.scan_type
    if scan_type not in TOOL_SCAN_TYPES:
        raise HTTPException(400, f"scan_type debe ser uno de: {list(TOOL_SCAN_TYPES.keys())}")

    result = tools_engine.run_nmap(
        target=target,
        scan_type=scan_type,
        timeout=data.timeout,
        user_id=0,
    )

    if result.error and not result.stdout:
        raise HTTPException(502, result.error)

    return {
        "status": "completed" if result.success else "failed",
        "tool": "nmap",
        "target": target,
        "scan_type": scan_type,
        "result": result.to_dict(),
    }


@router.post("/{tool}/run")
def run_tool(tool: str, data: ToolRunRequest):
    if tool not in TOOL_SPECS:
        raise HTTPException(404, f"Herramienta '{tool}' no soportada")

    target = data.target.strip()
    error = validate_tool_target(tool, target)
    if error:
        raise HTTPException(400, error)

    result = tools_engine.run_tool(
        tool=tool,
        target=target,
        profile=data.profile,
        options=data.options,
        timeout=data.timeout,
        user_id=0,
    )
    if result.error and not result.stdout:
        raise HTTPException(502, result.error)

    return {
        "status": "completed" if result.success else "failed",
        "tool": tool,
        "target": target,
        "profile": data.profile,
        "result": result.to_dict(),
    }
