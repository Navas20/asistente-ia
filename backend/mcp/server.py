import inspect
import json
import os
from pathlib import Path

import hacking
from findings.engine import FindingsManager
from findings.auto_extract import extract_findings

TOOLS_FILE = Path("data/mcp_tools.json")


def _describe_function(fn, name: str) -> dict:
    sig = inspect.signature(fn)
    params = []
    for pname, param in sig.parameters.items():
        typ = "string"
        if param.annotation is not inspect.Parameter.empty:
            if param.annotation is int:
                typ = "number"
            elif param.annotation is bool:
                typ = "boolean"
        params.append({
            "name": pname,
            "type": typ,
            "required": param.default is inspect.Parameter.empty,
        })
    return {
        "name": name,
        "description": (fn.__doc__ or f"Execute {name}").strip(),
        "parameters": params,
    }


def list_tools() -> list[dict]:
    tools = []
    for name in dir(hacking):
        if name.startswith("_"):
            continue
        fn = getattr(hacking, name)
        if callable(fn):
            tools.append(_describe_function(fn, name))
    tools.append({
        "name": "findings_list",
        "description": "List stored findings with optional filters",
        "parameters": [
            {"name": "host", "type": "string", "required": False},
            {"name": "severity", "type": "string", "required": False},
            {"name": "phase", "type": "string", "required": False},
        ],
    })
    tools.append({
        "name": "pentest_run",
        "description": "Run full pentest pipeline on a target",
        "parameters": [
            {"name": "target", "type": "string", "required": True},
        ],
    })
    return tools


def call_tool(name: str, arguments: dict) -> str:
    fn = getattr(hacking, name, None)
    if fn:
        try:
            result = fn(**arguments)
            if isinstance(result, str):
                return result
            return json.dumps(result, indent=2, ensure_ascii=False)
        except TypeError:
            try:
                target = arguments.get("target") or arguments.get("host") or arguments.get("url") or arguments.get("domain") or arguments.get("email") or arguments.get("ip") or ""
                result = fn(target)
                if isinstance(result, str):
                    return result
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception as e:
                return f"[ERROR] {e}"
        except Exception as e:
            return f"[ERROR] {e}"
    if name == "findings_list":
        fm = FindingsManager()
        findings = fm.list(
            host=arguments.get("host"),
            severity=arguments.get("severity"),
            phase=arguments.get("phase"),
        )
        return json.dumps([f.model_dump() for f in findings], indent=2, ensure_ascii=False)
    if name == "pentest_run":
        from pentest.engine import PentestEngine
        engine = PentestEngine()
        engine.run_pipeline(arguments.get("target", ""))
        return f"Pentest pipeline started on {arguments.get('target', '?')}"
    return f"[ERROR] Tool '{name}' not found"


class MCPServer:
    def __init__(self):
        self._ext_tools: dict[str, callable] = {}

    def register_tool(self, name: str, fn: callable, description: str = ""):
        self._ext_tools[name] = fn
        tools = self._load_ext()
        tools[name] = {"description": description}
        self._save_ext(tools)

    def _load_ext(self) -> dict:
        if TOOLS_FILE.exists():
            try:
                return json.loads(TOOLS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_ext(self, tools: dict):
        TOOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOOLS_FILE.write_text(json.dumps(tools, indent=2), encoding="utf-8")

    def handle_request(self, body: dict) -> dict:
        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id", 1)
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": list_tools()}}
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            result = call_tool(name, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result}]}}
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method '{method}' not found"}}
