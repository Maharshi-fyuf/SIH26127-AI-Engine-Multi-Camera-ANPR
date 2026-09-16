"""YUVATECH live-server API.
Run: uvicorn api.server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import os, json
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from config.settings import settings
from db.manager import DatabaseManager
from notifications.dispatcher import NotificationDispatcher
from security.auth import ApiKeyAuthorizer, Principal
from traffic_control.optimizer import ApproachState, SignalOptimizer

app=FastAPI(title="YUVATECH Traffic Intelligence API", version="2.0.0", docs_url="/docs")
db=DatabaseManager(settings.db_path)
auth=ApiKeyAuthorizer({
    settings.api_key:"operator",
    settings.admin_api_key:"admin",
    settings.reviewer_api_key:"reviewer",
    settings.investigator_api_key:"investigator",
    settings.auditor_api_key:"auditor",
})
notifier=NotificationDispatcher(settings.notification_enabled)

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
def health(): return {"status":"ok","environment":settings.environment,"notifications_enabled":settings.notification_enabled}

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
    require_role(x_api_key,"operator","admin","reviewer","investigator","auditor")
    row=db.get_violation(event_id)
    if not row: raise HTTPException(404,"Event not found")
    db.save_audit("api-user","vehicle_violation_view","ViolationEvent",event_id)
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
    return HTMLResponse('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>YUVATECH Control Room</title><style>body{font-family:Inter,system-ui;margin:0;background:#08111f;color:#eaf2ff}main{max-width:1200px;margin:auto;padding:32px}.hero{padding:28px;border:1px solid #24354f;border-radius:20px;background:#0e1a2c}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:18px}.card{padding:20px;border:1px solid #24354f;border-radius:16px;background:#0b1728}.muted{color:#93a7c2}code{color:#9bd0ff}</style></head><body><main><section class="hero"><h1>YUVATECH Control Room</h1><p class="muted">Multi-camera ANPR · trajectory intelligence · explainable enforcement</p></section><div class="grid"><div class="card"><b>API</b><p><code>/docs</code></p></div><div class="card"><b>Review</b><p>Authenticated human verification workflow</p></div><div class="card"><b>Timeline</b><p>Observed vehicle journey by plate</p></div><div class="card"><b>Notifications</b><p>Wawp + Gmail after verification</p></div><div class="card"><b>Adaptive Signals</b><p>Demand-weighted signal timing recommendations</p><p><code>POST /api/signals/optimize</code></p></div></div></main></body></html>''')
