import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str = ""
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    cvss_vector: str | None = None
    cvss_score: float | None = None
    host: str = ""
    port: int | None = None
    service: str | None = None
    tool: str = ""
    phase: str = ""
    evidence: str = ""
    status: Literal["raw", "verified", "dismissed"] = "raw"
    cve_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FindingSummary(BaseModel):
    total: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    by_phase: dict[str, int] = Field(default_factory=dict)
