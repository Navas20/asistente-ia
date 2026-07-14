from fastapi import APIRouter, HTTPException, Header

from tools_engine import tools_engine, validate_target, TOOL_SCAN_TYPES

router = APIRouter(prefix="/v5/tools", tags=["tools"])


@router.get("")
def list_tools():
    return {
        "tools": [
            {
                "name": "nmap",
                "description": "Escáner de puertos y servicios",
                "scan_types": list(TOOL_SCAN_TYPES.keys()),
                "default_timeout": 300,
                "features": ["port_scan", "service_detection", "os_detection", "nse_scripts"],
            },
        ]
    }


@router.get("/nmap/scan-types")
def get_nmap_scan_types():
    return {"scan_types": TOOL_SCAN_TYPES}


@router.post("/nmap/run")
def run_nmap(data: dict):
    target = data.get("target", "").strip()
    if not target:
        raise HTTPException(400, "target requerido")

    error = validate_target(target)
    if error:
        raise HTTPException(400, error)

    scan_type = data.get("scan_type", "normal")
    if scan_type not in TOOL_SCAN_TYPES:
        raise HTTPException(400, f"scan_type debe ser uno de: {list(TOOL_SCAN_TYPES.keys())}")

    extra_args = data.get("extra_args", None)
    timeout = data.get("timeout", None)

    result = tools_engine.run_nmap(
        target=target,
        scan_type=scan_type,
        extra_args=extra_args,
        timeout=timeout,
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
