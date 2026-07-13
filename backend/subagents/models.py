import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class SubagentTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    target: str = ""
    task: str = ""
    model: str = ""
    provider: str = "openrouter"
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    progress: int = 0
    result: str = ""
    findings_count: int = 0
    error: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    parent_id: str = ""
