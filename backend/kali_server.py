import asyncio
import json
import logging
import subprocess
import shlex
import signal
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kali_server")

app = FastAPI(title="Kali Tools Server")

MAX_STDOUT = 1_000_000


class RunRequest(BaseModel):
    tool: str
    args: list[str] = []
    timeout: int = 300
    task_id: str = ""


class RunResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    task_id: str = ""
    elapsed: float = 0.0
    truncated: bool = False
    parsed: dict | None = None


ALLOWED_TOOLS = {
    "nmap": "/usr/bin/nmap",
    "whois": "/usr/bin/whois",
    "dig": "/usr/bin/dig",
    "nslookup": "/usr/bin/nslookup",
    "curl": "/usr/bin/curl",
    "ping": "/usr/bin/ping",
}

HEALTH_FILE = Path("/tmp/kali_healthy")


@app.on_event("startup")
async def startup():
    HEALTH_FILE.write_text("ready")
    log.info("Kali Tools Server started on port 9001")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/tools")
def list_tools():
    available = {}
    for name, path in ALLOWED_TOOLS.items():
        available[name] = {"path": path, "exists": Path(path).exists()}
    return {"tools": available}


@app.post("/run", response_model=RunResponse)
def run_tool(req: RunRequest):
    binary = ALLOWED_TOOLS.get(req.tool)
    if not binary:
        raise HTTPException(404, f"Tool '{req.tool}' not found")

    if not Path(binary).exists():
        raise HTTPException(500, f"Binary '{binary}' not installed")

    import time
    start = time.time()
    cmd = [binary] + req.args

    log.info("Running: %s (timeout=%ds, task=%s)", " ".join(shlex.quote(str(a)) for a in cmd), req.timeout, req.task_id)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=req.timeout,
        )
        elapsed = time.time() - start
        truncated = False
        stdout = proc.stdout
        stderr = proc.stderr

        if len(stdout) > MAX_STDOUT:
            stdout = stdout[:MAX_STDOUT]
            truncated = True

        parsed = None
        if req.tool == "nmap" and proc.returncode == 0:
            parsed = _parse_nmap_xml(stdout)

        return RunResponse(
            success=proc.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            task_id=req.task_id,
            elapsed=round(elapsed, 2),
            truncated=truncated,
            parsed=parsed,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        log.warning("Timeout after %ds for tool=%s task=%s", req.timeout, req.tool, req.task_id)
        return RunResponse(
            success=False,
            stdout="",
            stderr=f"Timeout after {req.timeout}s",
            exit_code=-1,
            task_id=req.task_id,
            elapsed=round(elapsed, 2),
        )
    except FileNotFoundError:
        raise HTTPException(500, f"Binary '{binary}' not found at path")
    except Exception as e:
        elapsed = time.time() - start
        log.exception("Error running tool=%s", req.tool)
        return RunResponse(
            success=False,
            stdout="",
            stderr=str(e),
            exit_code=-2,
            task_id=req.task_id,
            elapsed=round(elapsed, 2),
        )


def _parse_nmap_xml(stdout: str) -> dict | None:
    """Extrae info básica de output nmap usando marcadores XML."""
    import re

    hosts = []
    host_pattern = re.compile(
        r"<host>.*?<address addr=\"([^\"]+)\".*?>(?:.*?<hostname name=\"([^\"]+)\")?",
        re.DOTALL,
    )
    port_pattern = re.compile(
        r"<port protocol=\"([^\"]+)\" portid=\"([^\"]+)\">"
        r"\s*<state state=\"([^\"]+)\""
        r"(?:.*?<service name=\"([^\"]*)\".*?)?(?:product=\"([^\"]*)\".*?)?(?:version=\"([^\"]*)\".*?)?",
    )

    for m in host_pattern.finditer(stdout):
        ip = m.group(1)
        hostname = m.group(2) or ""
        hosts.append({"ip": ip, "hostname": hostname, "ports": []})

    if not hosts:
        return None

    for m in port_pattern.finditer(stdout):
        protocol = m.group(1)
        port = m.group(2)
        state = m.group(3)
        service = m.group(4) or ""
        product = m.group(5) or ""
        version = m.group(6) or ""
        svc_full = f"{product} {version}".strip()
        if hosts:
            hosts[-1]["ports"].append({
                "port": int(port),
                "protocol": protocol,
                "state": state,
                "service": service,
                "version": svc_full,
            })

    up = len(hosts)
    total_ports = sum(len(h["ports"]) for h in hosts)

    return {
        "type": "nmap",
        "hosts": hosts,
        "summary": {"hosts_up": up, "total_ports_found": total_ports},
    }
