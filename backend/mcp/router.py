from fastapi import APIRouter, HTTPException, Request

from .server import MCPServer, list_tools

router = APIRouter(prefix="/mcp", tags=["mcp"])
server = MCPServer()


@router.post("/jsonrpc")
async def mcp_jsonrpc(request: Request):
    body = await request.json()
    return server.handle_request(body)


@router.get("/tools")
def mcp_tools():
    return {"tools": list_tools()}


@router.post("/register")
def register_tool(name: str, description: str = ""):
    def stub(**kwargs):
        return f"External tool stub: {name}"
    server.register_tool(name, stub, description)
    return {"ok": True, "name": name}
