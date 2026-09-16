# Technical Requirements Document (TRD)
## AI-Based Intelligent Traffic Monitoring & Enforcement System
**Team:** Yuvetech · **Problem Statement:** SIH26127 · **Version:** 1.0

---

## 1. Architecture Overview (V1 baseline, extended in later versions)

```
[Smartphone Camera]
        │  (RTMP/local capture, downsampled to ~15fps)
        ▼
[Video Ingestion] — OpenCV/FFmpeg frame extraction
        ▼
[Vehicle Detection] — YOLOv8 (pretrained, COCO classes)
        ▼
[Multi-Object Tracking] — ByteTrack (persistent track_id)
        ▼
   ┌────┴─────────────────┐
   ▼                       ▼
[Plate Pipeline]      [Attribute/State Pipeline]
 - Plate detector       - Helmet detector (fine-tuned YOLO)
   (fine-tuned YOLO)    - Signal-state detector (fine-tuned
 - PaddleOCR per crop      localization + HSV state classify)
 - Multi-frame vote     - Trajectory vs. stop-line/lane
   across track            geometry (rule-based polygons,
 - Format-regex             precomputed per camera placement)
   validation
   └────┬─────────────────┘
        ▼
[Event Aggregation Layer] — persistence-window voting,
  per-track confidence scoring (custom logic, not ML)
        ▼
[Traffic Rule Engine] — deterministic rules (JSON/DSL rule
  definitions evaluated against aggregated facts)
        ▼
[Confidence Gate] — routes to auto-processed vs. human-review
        ▼
[Evidence Package Generator] — image/clip + metadata bundle
        ▼
[Database] — Postgres/SQLite, camera_id-first schema
        ▼
[Challan/Alert Simulation] — mock notification, clearly
  labeled simulated in UI
```

## 2. Technology Stack by Module

| Module | Technology | Training Strategy |
|---|---|---|
| Vehicle detection | YOLOv8/v11 (n/s variant) | Pretrained, no fine-tuning |
| Plate detection (localization) | YOLOv8 custom head | Fine-tuned on Indian plate dataset |
| Plate OCR | PaddleOCR (or fine-tuned CRNN) | Fine-tuned on Indian plate crops |
| Tracking | ByteTrack | Algorithmic, no training |
| Signal state | YOLO fine-tuned localization + HSV color classify in ROI | Fine-tune localization only |
| Helmet detection | YOLO fine-tuned | Fine-tuned on public helmet datasets |
| Re-ID (V5+) | Lightweight OSNet embeddings | Pretrained |
| Stop-line/lane geometry | Manually calibrated polygons per camera | Rules, not ML |
| Rule engine | Python rule DSL (JSON-defined conditions) | N/A — hand-authored logic |
| Backend API | FastAPI | N/A |
| Database | SQLite (V1–V2) → Postgres (V3+) | N/A |
| Frontend / review UI | React + TypeScript | N/A |
| Event bus (V8) | Kafka or Redis Streams | N/A |
| GIS layer (V6+) | PostGIS + Leaflet/Mapbox | N/A |

## 3. Core Data Model (schema stable from V1, extended, never broken, across versions)

```
Camera
  camera_id (PK)
  location_lat, location_lng
  calibration_json      -- stop-line polygon, lane vectors
  active

Track
  track_id (PK)
  camera_id (FK)
  vehicle_class
  color
  first_seen_ts, last_seen_ts
  track_confidence

PlateRead
  plate_read_id (PK)
  track_id (FK)
  plate_text_partial_or_full
  ocr_confidence
  is_full_read (bool)
  frame_ref

ViolationEvent
  event_id (PK)
  track_id (FK)
  camera_id (FK)
  violation_type
  rule_confidence
  aggregated_confidence
  status               -- candidate | confirmed | rejected | needs_review
  timestamp
  evidence_bundle_ref

EvidenceBundle
  bundle_id (PK)
  event_id (FK)
  image_paths[]
  clip_path
  metadata_json

Alert (simulated)
  alert_id (PK)
  event_id (FK)
  channel               -- sms_sim | whatsapp_sim | dashboard
  delivered_sim (bool)
```

`camera_id` is present on every relevant table from V1 onward specifically so V4 (multi-camera) requires no schema migration — only new rows.

## 4. Rule Engine Specification

- Rules are declarative, expressed as condition trees over aggregated per-track facts (not raw per-frame detections).
- Example (red-light violation):
  ```json
  {
    "violation_type": "RED_LIGHT_VIOLATION",
    "conditions": [
      {"fact": "signal_state", "op": "==", "value": "RED"},
      {"fact": "crossed_stop_line", "op": "==", "value": true},
      {"fact": "persistence_frames", "op": ">=", "value": 5}
    ]
  }
  ```
- Rules must be hot-reloadable from a config file/DB table — never hardcoded in pipeline code — so V2+ violation additions don't require redeploying the perception pipeline.

## 5. Confidence & Aggregation Requirements

- Every `ViolationEvent` carries at least: detection confidence, OCR confidence (if applicable), track stability score, rule-persistence count.
- A configurable threshold (start at 0.75 combined score for V1) determines `confirmed` vs. `needs_review` status. This threshold is a config value, not a code constant.
- OCR: majority-vote across all frames of a track's lifetime; if no reading reaches a minimum per-character confidence, mark `is_full_read = false` and store whatever partial characters passed threshold.

## 6. Non-Functional Requirements

| Requirement | V1 target | V8 target |
|---|---|---|
| Processing latency (frame → event) | Best-effort, offline-acceptable for demo | Near-real-time (<2s) per camera |
| Concurrent camera feeds | 1 | City-scale (100s), via event bus |
| Data retention | Local disk, indefinite (prototype) | Policy-driven auto-purge for non-violation footage |
| Availability | Demo-time only | 24/7 with camera health monitoring |
| Privacy | No bystander plate storage beyond track lifetime | Formal redaction/retention policy enforced in code |

## 7. Version-by-Version Technical Deltas

- **V1:** everything above at prototype scale, single camera, local storage.
- **V2:** add review-queue API/UI; add pipeline health metrics endpoint; OCR fine-tuning pass on locally collected data.
- **V3:** migrate SQLite → Postgres; add per-camera calibration admin UI; add seatbelt module.
- **V4:** ingestion service becomes multi-camera aware (one ingestion worker per camera_id, shared event log); add control-room dashboard.
- **V5:** add Re-ID service; trajectory stitching between camera pairs with known geometry offsets.
- **V6:** add PostGIS-backed spatial layer; heatmap and OD analysis batch jobs.
- **V7:** add blacklist table + real-time match service; repeat-offender escalation logic in rule engine.
- **V8:** introduce event bus (Kafka/Redis Streams) between ingestion and processing for horizontal scale; formal retention/privacy policy enforcement; integration spec document for real RTO/e-Challan APIs (not implemented).

## 8. Explicit Engineering Guardrails (see also the Antigravity rulebook)

- No model or module may output a `violation_type` directly — only the rule engine may set that field.
- No component may fabricate data for a field it cannot support with actual model output (e.g., make/model without a validated classifier is `null`, not a guess).
- Every new violation type added in V2+ must be expressed as a rule-engine condition set, not new perception-model classes for "is_violation."
