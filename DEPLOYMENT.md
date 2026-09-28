# YUVATECH SIH26127 — Live Deployment Guide

## 1. Environment

Copy `.env.example` to `.env` and replace every `CHANGE_ME_*` value with strong random secrets. Never commit `.env`.

Configure cameras using:

```text
YUVATECH_CAMERAS=cam_01=0;cam_02=rtsp://user:password@host:554/stream
```

Supported sources include webcam indexes, video files and RTSP/RTMP/HTTP streams.

The recommended deployment runs the FastAPI control layer and the perception worker as separate processes. Keep `YUVATECH_AUTO_START_PIPELINE=false` in the API process and run `python run_worker.py` for camera processing. For a single-process local demo, set `YUVATECH_AUTO_START_PIPELINE=true`.

Roles:

- `operator` — monitoring and camera views
- `reviewer` — violation review/verification
- `investigator` — vehicle timeline/history
- `auditor` — audit/report access
- `admin` — configuration and lifecycle control

## 2. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Specialist models

The release includes reproducible model bootstrap:

```bash
python scripts/bootstrap_models.py --all
```

Review `models/MODEL_LICENSES.md`. The seatbelt checkpoint is AGPL-3.0; replace it with an appropriately licensed checkpoint if required.

For a connected deployment you may instead set:

```text
YUVATECH_AUTO_DOWNLOAD_MODELS=true
```

Do not start real inference until the required specialist weights are available.

## 4. End-to-end processing path

When a camera is configured, the application runs:

```text
Camera source
   -> MultiCameraRunner
   -> YOLO vehicle/person perception
   -> per-camera object tracking
   -> vehicle-scoped plate localization + OCR
   -> vehicle-scoped helmet / seatbelt inference
   -> rider counting + signal/geometry facts
   -> temporal EventAggregator
   -> deterministic JSON RuleEngine
   -> confidence gate
   -> EvidenceGenerator
   -> SQLite ViolationEvent + plate identity
   -> simulated alert
```

The rule engine is the only component that creates `ViolationEvent.violation_type`.

## 5. Plate-to-event integrity

Plate reads are scoped to the active vehicle bounding box. If the plate detector finds a plate elsewhere in the frame, that plate is ignored for the current vehicle.

A reliable read is propagated as:

```text
PlatePipeline
  -> OcrFact
  -> EventAggregator
  -> ViolationEvent.plate_text / plate_confidence / plate_is_full
  -> EvidenceBundle metadata
  -> database / dashboard / simulated alert
```

No-plate cases remain explicitly unreadable; the system does not invent a plate.

## 6. Camera reliability

Live RTSP/RTMP/webcam sources automatically reconnect using exponential backoff. File sources finish normally at EOF. Camera health includes frame count, event count, last frame time, reconnect count and the latest error.

## 7. Start

### Local API

```bash
python run_server.py
```

### Local perception worker

```bash
python run_worker.py
```

The worker owns `MultiCameraRunner` and the end-to-end perception pipeline. Do not start multiple copies of the worker for the same camera set.

### Docker Compose

```bash
docker compose up --build -d
```

The Docker image bootstraps specialist models during the image build. The Compose file uses a named model volume so the image's `/app/models` contents are not accidentally hidden by an empty host directory.

The API may use normal process scaling because it no longer owns the camera workers in the recommended Compose deployment. Keep exactly one perception worker for each configured camera set; do not duplicate camera ingestion across workers.

## 8. Pipeline lifecycle API

Authenticated admin/operator access is required as documented by the API.

```text
GET  /api/pipeline/status
POST /api/pipeline/start
POST /api/pipeline/stop
```

Automatic in-process startup is controlled by `YUVATECH_AUTO_START_PIPELINE`; the dedicated worker always uses `YUVATECH_CAMERAS`.

## 9. Notifications

Wawp uses the official REST endpoint by default. Citizen-facing notifications remain blocked until the event has reached the `verified` human/authority state:

```text
AI perception -> rule engine -> confidence -> evidence -> human review -> verified -> Wawp/Gmail
```

Notifications are disabled by default.

## 10. Database

SQLite is hardened with WAL, a 30-second busy timeout, foreign keys, explicit connection closure and transient lock retries. PostgreSQL/PostGIS plus a distributed event bus remains the city-scale deployment path.

## 11. Verification

Run:

```bash
pytest -q
python -m compileall -q .
```

Current packaging-environment result: **43 passed, 1 skipped**. The single skip is the detector runtime test because the isolated build environment lacks the `ultralytics` package; the production requirements include it.
