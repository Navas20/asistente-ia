import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .models import Incident, LogSource, ResponseRule, ForensicPackage
from .monitor import LogMonitor
from .detector import AttackDetector
from .responder import AutoResponder
from .alerting import AlertManager
from .threat_intel import ThreatIntel
from .forensics import EvidenceCollector

router = APIRouter(prefix="/defense", tags=["defense"])

monitor = LogMonitor()
detector = AttackDetector()
responder = AutoResponder()
alerter = AlertManager()
intel = ThreatIntel()
forensics = EvidenceCollector()

INCIDENTS_FILE = Path("data/defense_incidents.json")
_monitoring = False


def _load_incidents() -> list[Incident]:
    if INCIDENTS_FILE.exists():
        try:
            data = json.loads(INCIDENTS_FILE.read_text(encoding="utf-8"))
            return [Incident(**d) for d in data]
        except Exception:
            pass
    return []


def _save_incidents(incidents: list[Incident]):
    INCIDENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [i.model_dump() for i in incidents]
    INCIDENTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _on_log_line(source: LogSource, line: str):
    global _monitoring
    if not _monitoring:
        return
    incident = detector.analyze(source, line)
    if incident:
        incidents = _load_incidents()
        incidents.append(incident)
        _save_incidents(incidents)
        if incident.severity in ("high", "critical"):
            responder.respond(incident)
        alerter.send(incident)


monitor.on_line(_on_log_line)


@router.get("/status")
def defense_status():
    blocks = responder.list_blocks()
    incidents = _load_incidents()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_count = sum(1 for i in incidents if i.timestamp.startswith(today))
    return {
        "monitoring": _monitoring,
        "active_blocks": len(blocks),
        "incidents_today": today_count,
        "total_incidents": len(incidents),
    }


@router.post("/start")
def start_monitoring():
    global _monitoring
    _monitoring = True
    return {"ok": True, "monitoring": True}


@router.post("/stop")
def stop_monitoring():
    global _monitoring
    _monitoring = False
    return {"ok": True, "monitoring": False}


@router.get("/incidents")
def list_incidents(
    severity: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50),
):
    incidents = _load_incidents()
    if severity:
        incidents = [i for i in incidents if i.severity == severity]
    if status:
        incidents = [i for i in incidents if i.status == status]
    return [i.model_dump() for i in incidents[-limit:]]


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    incidents = _load_incidents()
    for i in incidents:
        if i.id == incident_id:
            return i.model_dump()
    raise HTTPException(404, "Incident not found")


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: str, data: dict):
    incidents = _load_incidents()
    for i in incidents:
        if i.id == incident_id:
            if "status" in data:
                i.status = data["status"]
            _save_incidents(incidents)
            return i.model_dump()
    raise HTTPException(404, "Incident not found")


@router.post("/incidents/{incident_id}/block")
def block_incident(incident_id: str):
    incidents = _load_incidents()
    for i in incidents:
        if i.id == incident_id:
            msg = responder.block_ip(i.source_ip)
            i.status = "blocked"
            i.blocked_at = datetime.now(timezone.utc).isoformat()
            _save_incidents(incidents)
            return {"ok": True, "message": msg}
    raise HTTPException(404, "Incident not found")


@router.post("/incidents/{incident_id}/unblock")
def unblock_incident(incident_id: str):
    incidents = _load_incidents()
    for i in incidents:
        if i.id == incident_id:
            msg = responder.unblock_ip(i.source_ip)
            i.status = "resolved"
            _save_incidents(incidents)
            return {"ok": True, "message": msg}
    raise HTTPException(404, "Incident not found")


@router.post("/incidents/{incident_id}/investigate")
def investigate_incident(incident_id: str):
    incidents = _load_incidents()
    for i in incidents:
        if i.id == incident_id:
            ti = intel.lookup(i.source_ip)
            i.threat_intel = ti
            pkg = forensics.collect(i)
            i.status = "investigated"
            _save_incidents(incidents)
            return {
                "threat_intel": ti.model_dump() if ti else None,
                "forensics": pkg.model_dump(),
            }
    raise HTTPException(404, "Incident not found")


@router.post("/incidents/{incident_id}/report")
def generate_forensic_report(incident_id: str):
    incidents = _load_incidents()
    for i in incidents:
        if i.id == incident_id:
            pkg = forensics.collect(i)
            return pkg.model_dump()
    raise HTTPException(404, "Incident not found")


@router.get("/blocks")
def list_blocks():
    return {"blocks": responder.list_blocks()}


@router.delete("/blocks/{ip}")
def remove_block(ip: str):
    msg = responder.unblock_ip(ip)
    return {"ok": True, "message": msg}


@router.post("/intel/{ip}")
def lookup_intel(ip: str):
    ti = intel.lookup(ip)
    return ti.model_dump() if ti else {"ip": ip, "error": "No data"}


@router.get("/logs")
def list_log_sources():
    return {"sources": [s.model_dump() for s in monitor.list_sources()]}


@router.post("/logs/source")
def add_log_source(source: LogSource):
    monitor.add_source(source)
    return {"ok": True}


@router.delete("/logs/source/{source_id}")
def remove_log_source(source_id: str):
    monitor.remove_source(source_id)
    return {"ok": True}
