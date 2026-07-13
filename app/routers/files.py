"""
API Router - File management endpoints
"""
from fastapi import APIRouter, Depends, UploadFile, File
import logging
import uuid
from pathlib import Path

from app.config import UPLOAD_DIR, MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS
from security.auth import verify_token
from security.audit import audit_service
from data_layer.repositories import FileRepository

log = logging.getLogger("artenisa.api.files")

router = APIRouter()
file_repo = FileRepository()


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    """Sube un archivo"""
    
    # Validaciones
    if file.size and file.size > MAX_UPLOAD_SIZE:
        return {"error": f"Archivo muy grande (max {MAX_UPLOAD_SIZE} bytes)"}
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return {"error": f"Extensión no permitida: {file_ext}"}
    
    # Generar nombre único
    file_id = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    
    # Guardar archivo
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    
    # Registrar en BD
    file_repo.register_file(file_id, str(save_path), file.filename, len(content))
    
    audit_service.log_action(0, "api", "file/upload", file.filename, "ok")
    
    return {
        "file_id": file_id,
        "filename": file.filename,
        "size": len(content),
        "url": f"/api/v1/files/download/{file_id}"
    }


@router.get("/files/download/{file_id}")
async def download_file(
    file_id: str,
    token: str = Depends(verify_token)
):
    """Descarga un archivo"""
    
    file_info = file_repo.get_file(file_id)
    if not file_info:
        return {"error": "Archivo no encontrado"}
    
    from fastapi.responses import FileResponse
    
    audit_service.log_action(0, "api", "file/download", file_id, "ok")
    
    return FileResponse(
        file_info["filename"],
        filename=file_info["original_name"]
    )
