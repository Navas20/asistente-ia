"""
Esquemas y modelos Pydantic
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# ─── Chat ───
class Message(BaseModel):
    role: str  # "user" o "assistant"
    content: str

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    model: Optional[str] = None
    stream: bool = False

class ChatResponse(BaseModel):
    conversation_id: str
    role: str
    content: str
    timestamp: datetime

# ─── Memory ───
class MemoryItem(BaseModel):
    key: str
    value: str
    category: str
    updated_at: datetime

# ─── Target ───
class Target(BaseModel):
    id: str
    name: str
    target_type: str
    start_date: datetime
    current_operation: Optional[str] = None

# ─── Task ───
class TaskItem(BaseModel):
    id: str
    title: str
    status: str  # queued, running, completed, failed
    progress: float = 0.0
    created_at: datetime
    updated_at: datetime

# ─── Playbook ───
class PlaybookStep(BaseModel):
    tool: str
    params: Dict[str, Any]

class PlaybookRequest(BaseModel):
    name: str
    target: str

# ─── Report ───
class ReportRequest(BaseModel):
    target: str
    format: str  # md, html, json

# ─── File Upload ───
class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    uploaded_at: datetime

# ─── Audit ───
class AuditEntry(BaseModel):
    user_id: str
    username: str
    command: str
    target: Optional[str]
    timestamp: datetime
    status: str
    details: Optional[str]
