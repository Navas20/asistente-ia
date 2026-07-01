# DEPRECATED — Use playbooks.py instead
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime

try:
    from playbooks import list_playbooks, run_playbook
except ImportError:
    from backend.playbooks import list_playbooks, run_playbook

TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT", "120"))


def tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(cmd, timeout: int = None) -> dict:
    if isinstance(cmd, str):
        try:
            cmd = shlex.split(cmd, posix=False)
        except:
            cmd = cmd.split()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout or TOOL_TIMEOUT
        )
        output = (result.stdout or result.stderr or "(sin salida)")[:5000]
        return {
            "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
            "success": result.returncode == 0,
            "output": output,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd) if isinstance(cmd, list) else cmd, "success": False, "output": "[Timeout]"}
    except Exception as e:
        return {"command": " ".join(cmd) if isinstance(cmd, list) else cmd, "success": False, "output": f"[Error: {e}]"}


def try_run(tool: str, args: list, fallback_msg: str = None) -> dict:
    if tool_exists(tool):
        return run([tool] + args)
    return {
        "command": f"{tool} {' '.join(args)}",
        "success": False,
        "output": fallback_msg or f"[{tool} no instalado]"
    }


WORKFLOWS = {}


def ejecutar_workflow(nombre: str, params: dict) -> dict:
    target = params.get("target", params.get("service", params.get("hash", "")))
    if not target:
        return {"error": "Se requiere un objetivo para este workflow"}
    return run_playbook(nombre, target)


def listar_workflows() -> dict:
    pbs = list_playbooks()
    return {
        name: {
            "name": pb["name"],
            "description": pb["description"],
            "params": [{"name": "target", "label": f"Objetivo ({pb['target_type']})", "type": "text"}],
        }
        for name, pb in pbs.items()
    }
