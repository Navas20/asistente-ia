"""
FastAPI Entry Point - Punto de entrada de la aplicación
"""
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ALLOWED_ORIGINS, LOG_LEVEL
from app.routers import chat, files, tools, playbooks, memory, targets, tasks, audit, agent

# ─── Logging ───
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
log = logging.getLogger("artenisa")

# ─── FastAPI App ───
app = FastAPI(
    title="Artenisa API",
    description="Asistente-copiloto de ingeniería con capacidades de hacking ético",
    version="4.0.0"
)

# ─── CORS Middleware ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ─── Routers ───
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(files.router, prefix="/api/v1", tags=["files"])
app.include_router(tools.router, prefix="/api/v1", tags=["tools"])
app.include_router(playbooks.router, prefix="/api/v1", tags=["playbooks"])
app.include_router(memory.router, prefix="/api/v1", tags=["memory"])
app.include_router(targets.router, prefix="/api/v1", tags=["targets"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(audit.router, prefix="/api/v1", tags=["audit"])
app.include_router(agent.router, prefix="/api/v1", tags=["agent"])

# ─── Health Check ───
@app.get("/health")
def health():
    return {"status": "ok", "version": "4.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("ENV", "production") == "development"
    )
