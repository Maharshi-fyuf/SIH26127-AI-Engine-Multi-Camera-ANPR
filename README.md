# AI-Based Intelligent Traffic Monitoring & Enforcement System (SIH26127)

**SIH26127, Team Yuvetech**

This repository contains the source code for an AI-powered traffic monitoring and enforcement system. It ingests video feeds, tracks vehicles in real-time, aggregates multi-frame events to reduce false positives, and uses a rule engine to confirm violations (e.g., stop-line crossing, missing helmets) before generating evidence packages and simulated alerts.

## Architecture Summary
The system relies on a strict decoupling between **perception** and **judgement**. The perception modules (YOLOv8, Norfair/ByteTrack, OCR) only emit objective `DetectionFact`s (e.g., "object ID 5 is a motorcycle at [x,y]"). An intermediate Event Aggregation layer tracks these facts across consecutive frames to filter out single-frame noise. Finally, a deterministic Rule Engine consumes these smoothed facts to declare a `ViolationEvent`. This prevents a single hallucinated frame from triggering a false alert and ensures the rule logic can be audited independently of the AI models.

## Current Build Status

This build is a hardened prototype with production-oriented interfaces. Core perception, tracking, aggregation, deterministic rule evaluation, evidence generation, multi-camera orchestration, trajectory/GIS primitives, watchlist intelligence, human-review state management, governance, notifications and a live FastAPI server are implemented.

Important implementation boundary: specialist ANPR/helmet/seatbelt models require validated model weights. The repository now exposes real YOLO-backed adapters and fails closed when those weights are absent; synthetic placeholder helpers remain only for deterministic automated tests. eChallan remains an integration boundary/specification until an authorized government API contract and credentials exist.

### Notification stack
- Wawp WhatsApp adapter using the supplied `wawp_sdk` contract; credentials are environment-only.
- Gmail SMTP/STARTTLS adapter.
- Notifications are disabled by default and citizen-facing notifications require an explicit `verified` human/authority review state.

### Live server
`python run_server.py` starts the FastAPI control/API layer. See `DEPLOYMENT.md` for production deployment, HTTPS, secrets, model weights and database guidance.

### Audit
See `docs/FINAL_IMPLEMENTATION_AUDIT.md` for implemented capabilities and remaining deployment-specific requirements.

## Setup Instructions

1. **Prerequisites:** Python 3.10+
2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/Mac:
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Running the Pipeline:**
   Check the provided testing and diagnostic scripts (e.g., `test_phase4_pipeline.py`, `debug_visualize.py`).

## Documentation
- [Product Requirements Document (PRD)](docs/PRD-traffic-enforcement-system.md)
- [Technical Requirements Document (TRD)](docs/TRD-traffic-enforcement-system.md)
- [Implementation Plan (V1-V8)](docs/implementation-plan-v1-v8.md)
- [Future Plans (V4-V8)](docs/future-plans.md)
- [Accuracy Audit Report Template](docs/accuracy-audit-report-template.md)
- [RTO/e-Challan Integration Spec](docs/RTO-eChallan-integration-spec.md)

## V9 — Adaptive Traffic Signal Optimization

YUVATECH includes a deterministic, simulation-safe signal optimizer that turns
camera-derived traffic state into an explainable **signal timing recommendation**.
It considers vehicle volume, queue length, observed speed and saturation, with
confidence-gated emergency-vehicle priority. The API is available at
`POST /api/signals/optimize` and requires an authenticated operator/admin/auditor.

The prototype is deliberately **recommendation-only**: it never actuates a real
traffic controller. Production signal control requires an authorized ITS/
controller interface, phase-conflict validation, yellow/all-red clearance,
pedestrian constraints, fail-safe rollback and field validation.

See `docs/ADAPTIVE_SIGNAL_CONTROL.md` and
`docs/YUVATECH_FLOWCHART_ADAPTIVE_SIGNAL.png`.
