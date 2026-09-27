"""YUVATECH live-server API.
Run: uvicorn api.server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import os, json, time
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from config.settings import settings
from db.manager import DatabaseManager
from notifications.dispatcher import NotificationDispatcher
from security.auth import ApiKeyAuthorizer, Principal
from traffic_control.optimizer import ApproachState, SignalOptimizer
from api.dashboard import ControlRoomDashboard
from analytics.spatial import violation_heatmap
from tracking.reid import CameraLink, TrajectoryStitcher
from governance.retention import RetentionManager
from monitoring.anomaly import score_camera
from ingestion.stream import CameraConfig

app=FastAPI(title="YUVATECH Traffic Intelligence API", version="2.0.0", docs_url="/docs")
db=DatabaseManager(settings.db_path)
def _build_auth(cfg=settings):
    pairs = [
        (cfg.api_key, "operator", "operator-key"),
        (cfg.admin_api_key, "admin", "admin-key"),
        (cfg.reviewer_api_key, "reviewer", "reviewer-key"),
        (cfg.investigator_api_key, "investigator", "investigator-key"),
        (cfg.auditor_api_key, "auditor", "auditor-key"),
    ]
    seen = {}
    mapping = {}
    for key, role, subject in pairs:
        if not key:
            continue
        if key in seen:
            raise RuntimeError(f"Duplicate API key configured for roles {seen[key]} and {role}")
        seen[key] = role
        mapping[key] = (subject, role)
    return ApiKeyAuthorizer(mapping)

auth=_build_auth()
notifier=NotificationDispatcher(
    settings.notification_enabled,
    wawp=(settings.wawp_instance_id, settings.wawp_access_token, settings.wawp_session, settings.wawp_send_url),
    smtp=(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.notification_from),
)
pipeline_service = None
pipeline_start_error = None

def parse_camera_sources(raw: str):
    """Parse cam_id=source;cam_id=source deployment configuration."""
    configs = []
    for item in (raw or "").split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        camera_id, source = item.split("=", 1)
        camera_id, source = camera_id.strip(), source.strip()
        if camera_id and source:
            configs.append(CameraConfig(camera_id, source))
    return configs

@app.on_event("startup")
def start_live_pipeline():
    global pipeline_service, pipeline_start_error
    if not settings.auto_start_pipeline or not settings.camera_sources.strip():
        return
    try:
        from pipeline.live import LivePipelineService
        configs = parse_camera_sources(settings.camera_sources)
        if not configs:
            return
        pipeline_service = LivePipelineService(db, configs)
        pipeline_service.start()
    except Exception as exc:
        pipeline_start_error = str(exc)
        import logging
        logging.getLogger(__name__).exception("Live pipeline failed to start")

@app.on_event("shutdown")
def stop_live_pipeline():
    global pipeline_service
    if pipeline_service is not None:
        pipeline_service.stop()
        pipeline_service = None

class ReviewRequest(BaseModel):
    status: str = Field(pattern="^(approved|rejected|escalated|verified)$")
    note: str = Field(default="", max_length=2000)

class SignalApproachRequest(BaseModel):
    approach_id: str = Field(min_length=1, max_length=64)
    vehicle_count: int = Field(default=0, ge=0, le=100000)
    queue_length: int = Field(default=0, ge=0, le=100000)
    avg_speed_kph: float = Field(default=0.0, ge=0, le=300)
    emergency_vehicle: bool = False
    emergency_confidence: float = Field(default=0.0, ge=0, le=1)
    saturated: bool = False

class SignalOptimizationRequest(BaseModel):
    intersection_id: str = Field(min_length=1, max_length=64)
    cycle_seconds: int = Field(default=120, ge=30, le=300)
    approaches: list[SignalApproachRequest] = Field(min_length=1, max_length=16)

class NotificationRequest(BaseModel):
    channel: str = Field(pattern="^(whatsapp|email)$")
    phone: str | None = None
    email: str | None = None
    subject: str = "YUVATECH Verified Traffic Event"
    message: str = Field(min_length=1, max_length=5000)

def principal_from_key(key: str|None) -> Principal:
    p=auth.authenticate(key or "")
    if not p: raise HTTPException(401,"Unauthorized")
    return p

def require_role(key: str|None,*roles):
    p=principal_from_key(key)
    if not auth.allowed(p,*roles): raise HTTPException(403,"Insufficient role")
    return p

@app.get("/health")
def health():
    anomalies={}
    if pipeline_service is not None:
        for camera_id, health_item in pipeline_service.runner.health_snapshot().items():
            age = max(0.0, time.time()*1000.0-health_item.last_frame_ts) if health_item.last_frame_ts else float("inf")
            anomalies[camera_id] = score_camera(camera_id, frames_processed=health_item.frames_processed, events_emitted=health_item.events_emitted, last_frame_age_ms=age, error=health_item.last_error).__dict__
    return {
        "status":"ok", "environment":settings.environment,
        "notifications_enabled":settings.notification_enabled,
        "pipeline_configured":bool(settings.camera_sources.strip()),
        "pipeline_running":pipeline_service is not None,
        "pipeline_start_error":pipeline_start_error,
        "camera_anomalies":anomalies,
    }

@app.get("/api/pipeline/status")
def pipeline_status(x_api_key: str|None=Header(default=None)):
    require_role(x_api_key,"operator","admin","auditor")
    if pipeline_service is None:
        return {"running":False,"configured":bool(settings.camera_sources.strip()),"error":pipeline_start_error,"cameras":{}}
    return {"running":True,"configured":True,"error":None,"cameras":pipeline_service.status()}

@app.post("/api/pipeline/start")
def pipeline_start(x_api_key: str|None=Header(default=None)):
    global pipeline_service, pipeline_start_error
    p=require_role(x_api_key,"admin")
    if pipeline_service is not None:
        return {"running":True,"cameras":pipeline_service.status()}
    configs=parse_camera_sources(settings.camera_sources)
    if not configs:
        raise HTTPException(400,"Set YUVATECH_CAMERAS as cam_id=source;cam_id=source before starting the live pipeline")
    try:
        from pipeline.live import LivePipelineService
        pipeline_service=LivePipelineService(db, configs)
        pipeline_start_error=None
        result=pipeline_service.start()
        db.save_audit(p.subject,"start_live_pipeline","Pipeline","live",{"cameras":[c.camera_id for c in configs]})
        return {"running":True,"cameras":result}
    except Exception as exc:
        pipeline_start_error=str(exc)
        raise HTTPException(500,f"Live pipeline failed to start: {exc}")

@app.post("/api/pipeline/stop")
def pipeline_stop(x_api_key: str|None=Header(default=None)):
    global pipeline_service
    p=require_role(x_api_key,"admin")
    if pipeline_service is None:
        return {"running":False,"cameras":{}}
    result=pipeline_service.stop()
    pipeline_service=None
    db.save_audit(p.subject,"stop_live_pipeline","Pipeline","live")
    return {"running":False,"cameras":result}

@app.post("/api/signals/optimize")
def optimize_signal(request: SignalOptimizationRequest, x_api_key: str|None=Header(default=None)):
    p=require_role(x_api_key,"operator","admin","auditor")
    optimizer=SignalOptimizer(cycle_seconds=request.cycle_seconds)
    states=[ApproachState(**a.model_dump()) for a in request.approaches]
    try:
        plan=optimizer.optimize(request.intersection_id, states)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    db.save_audit(p.subject,"signal_timing_recommendation","Intersection",request.intersection_id,{"cycle_seconds":request.cycle_seconds,"emergency_priority":plan.emergency_priority_approach})
    return {"mode":"recommendation_only","warning":"No traffic controller is actuated by this endpoint.","plan":plan.to_dict()}

@app.get("/api/cameras")
def cameras(x_api_key: str|None=Header(default=None)):
    require_role(x_api_key,"operator","admin","auditor")
    return db.get_violation_counts_by_camera()

@app.put("/api/cameras/{camera_id}/calibration")
def calibration(camera_id: str, payload: dict, x_api_key: str|None=Header(default=None)):
    p=require_role(x_api_key,"admin")
    db.save_camera_calibration(camera_id,payload)
    db.save_audit(p.subject,"update_camera_calibration","Camera",camera_id)
    return {"camera_id":camera_id,"calibration":payload}

@app.get("/api/review")
def review_queue(x_api_key: str|None=Header(default=None)):
    require_role(x_api_key,"operator","admin","reviewer")
    return db.get_review_queue()

@app.get("/api/violations/{event_id}")
def violation(event_id:str,x_api_key:str|None=Header(default=None)):
    p=require_role(x_api_key,"operator","admin","reviewer","investigator","auditor")
    row=db.get_violation(event_id)
    if not row: raise HTTPException(404,"Event not found")
    db.save_audit(p.subject,"vehicle_violation_view","ViolationEvent",event_id)
    return {"event":row,"review_history":db.get_review_history(event_id)}

@app.post("/api/violations/{event_id}/review")
def review(event_id:str,request:ReviewRequest,x_api_key:str|None=Header(default=None)):
    p=require_role(x_api_key,"reviewer","admin")
    try: result=db.review_event(event_id,request.status,p.subject,request.note)
    except ValueError as exc: raise HTTPException(400,str(exc))
    db.save_audit(p.subject,"review_violation","ViolationEvent",event_id,{"status":request.status})
    return result

@app.post("/api/violations/{event_id}/notify")
def notify(event_id:str,request:NotificationRequest,x_api_key:str|None=Header(default=None)):
    p=require_role(x_api_key,"reviewer","admin")
    event=db.get_violation(event_id)
    if not event: raise HTTPException(404,"Event not found")
    result=notifier.send(request.channel,status=event["status"],human_verified=bool(event.get("verified_by")),message=request.message,phone=request.phone,email=request.email,subject=request.subject)
    db.save_notification_log(event_id,request.channel,request.phone or request.email or "", "sent" if result.success else "failed", result.error)
    db.save_audit(p.subject,"send_notification","ViolationEvent",event_id,{"channel":request.channel,"success":result.success})
    if not result.success: raise HTTPException(400,result.error)
    return {"success":True,"channel":request.channel}

@app.get("/api/vehicles/{plate}/timeline")
def timeline(plate:str,x_api_key:str|None=Header(default=None)):
    p=require_role(x_api_key,"operator","admin","investigator","auditor")
    data=db.get_vehicle_timeline(plate)
    db.save_audit(p.subject,"vehicle_timeline_query","VehicleObservation",plate,{"result_count":len(data)})
    return {"plate":plate,"observations":data}

@app.get("/evidence/{filename}")
def evidence(filename:str,x_api_key:str|None=Header(default=None)):
    require_role(x_api_key,"operator","admin","reviewer","investigator","auditor")
    root=Path(settings.evidence_dir).resolve(); target=(root/filename).resolve()
    if root not in target.parents or not target.is_file(): raise HTTPException(404,"Evidence not found")
    return FileResponse(target)

@app.get("/",response_class=HTMLResponse)
def home():
    dashboard = ControlRoomDashboard(db)
    health = pipeline_service.runner.health_snapshot() if pipeline_service is not None else {}
    return HTMLResponse(dashboard.render_html(health))

@app.get("/api/analytics/heatmap")
def analytics_heatmap(x_api_key:str|None=Header(default=None)):
    require_role(x_api_key,"operator","admin","investigator","auditor")
    return {"heatmap": {f"{lat:.4f},{lng:.4f}": count for (lat,lng), count in violation_heatmap(db.get_violation_locations()).items()}}

@app.post("/api/governance/retention/run")
def run_retention(x_api_key:str|None=Header(default=None)):
    p=require_role(x_api_key,"admin")
    root=Path(settings.evidence_dir)
    paths=[str(path) for path in root.glob("*") if path.is_file()] if root.exists() else []
    protected=db.get_protected_evidence_paths()
    decisions=RetentionManager().purge_non_violation_files(paths, protected)
    db.save_audit(p.subject,"run_retention","EvidenceDirectory",str(root),{"decisions":len(decisions)})
    return {"decisions":[d.__dict__ for d in decisions]}

class TrajectoryLinkRequest(BaseModel):
    from_camera_id: str
    to_camera_id: str
    min_travel_ms: float = Field(default=1000, ge=0)
    max_travel_ms: float = Field(default=300000, gt=0)

@app.post("/api/trajectories/stitch")
def stitch_trajectories(links:list[TrajectoryLinkRequest], x_api_key:str|None=Header(default=None)):
    p=require_role(x_api_key,"investigator","admin")
    camera_links=[CameraLink(**link.model_dump()) for link in links]
    stitcher=TrajectoryStitcher(camera_links)
    raw=db.get_recent_embeddings()
    from tracking.reid import VehicleEmbedding
    embeddings=[VehicleEmbedding(r["embedding_id"],r["camera_id"],r["track_id"],r["timestamp_ms"],r["vector"]) for r in raw]
    matches=stitcher.match(embeddings)
    for match in matches:
        db.save_trajectory_match(match)
    db.save_audit(p.subject,"trajectory_stitch","VehicleEmbedding","batch",{"matches":len(matches)})
    return {"matches":[{"from_embedding_id":m.from_embedding.embedding_id,"to_embedding_id":m.to_embedding.embedding_id,"similarity":m.similarity} for m in matches]}
