import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ThreatIntelResult(BaseModel):
    ip: str = ""
    isp: str | None = None
    country: str | None = None
    asn: str | None = None
    abuse_reports: int = 0
    confidence: int = 0
    open_ports: list[int] = Field(default_factory=list)
    known_malware: bool = False
    previous_incidents: int = 0


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    attack_type: str = ""
    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"
    source_ip: str = ""
    target: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    count: int = 1
    log_snippet: str = ""
    evidence_files: list[str] = Field(default_factory=list)
    status: Literal["detected", "blocked", "investigated", "resolved"] = "detected"
    blocked_at: str | None = None
    threat_intel: ThreatIntelResult | None = None


class LogSource(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    path: str = ""
    type: Literal["nginx_access", "nginx_error", "auth", "syslog", "custom"] = "custom"
    enabled: bool = True


class ResponseRule(BaseModel):
    incident_type: str = ""
    action: Literal["block_ip", "block_ip_windows", "rate_limit", "notify", "capture"] = "notify"
    auto: bool = False
    duration: int = 3600


class ForensicPackage(BaseModel):
    incident_id: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_manifest: list[dict] = Field(default_factory=list)
    timeline: list[dict] = Field(default_factory=list)
    chain_of_custody: str = ""
    report_path: str = ""
