# YUVATECH SIH26127 — Final Production Candidate Hardening Manifest

This release closes the end-to-end deployment gaps identified in the V9 audit.

## Critical end-to-end fixes

- `run_server.py` provides the FastAPI control layer and `run_worker.py` provides the dedicated live camera processing service; Docker Compose runs them as separate services.
- Each configured camera runs through `MultiCameraRunner` and a stateful `LiveCameraProcessor`:
  `camera -> YOLO perception -> tracking -> scoped ANPR/attributes -> aggregation -> deterministic rules -> evidence -> DB -> simulated alert`.
- Recognized plate text, OCR confidence and full/partial status now travel from `PlatePipeline` into `ViolationEvent`, SQLite and evidence metadata.
- Helmet inference is cropped to the target vehicle before YOLO inference and coordinates are mapped back to the full frame.
- Plate inference is strictly scoped to the target vehicle; a miss **never** falls back to another vehicle's plate.
- SQLite schema/migrations include plate identity fields on `ViolationEvent`.
- Live pipeline lifecycle endpoints are available at `/api/pipeline/status`, `/api/pipeline/start`, and `/api/pipeline/stop`.
- Camera reconnect, exponential backoff and health reporting remain enabled for live sources.
- Docker Compose no longer masks image-bundled specialist weights with an empty host `models/` directory; a named volume is used instead.

## Other hardening retained

- Specialist model bootstrap for plate, helmet and seatbelt inference.
- Plate localization -> preprocessing -> OCR -> temporal voting.
- Tesseract fallback for offline/dev OCR when PaddleOCR is unavailable.
- Separate operator/reviewer/investigator/auditor/admin API-key roles with subject-aware audit logging and duplicate-key collision detection.
- SQLite WAL, busy timeout, foreign keys and transient lock retries.
- Wawp official REST fallback enabled by default; SDK remains optional.
- Norfair-first tracking with deterministic fallback for dependency-light environments.
- Privacy blurring is applied to bystander person regions before evidence export; retention, audit logging, API authentication and path-traversal protection are wired into the deployment path.
- Human verification remains required before citizen-facing notifications.

## Model provenance

See `models/MODEL_LICENSES.md`. Third-party specialist checkpoints are not represented as YUVATECH-owned assets. Use:

```bash
python scripts/bootstrap_models.py --all
```

or enable `YUVATECH_AUTO_DOWNLOAD_MODELS=true` on a connected deployment.

The seatbelt checkpoint is AGPL-3.0; replace it if that license is unsuitable for the intended deployment.

## Verification

Local validation in the packaging environment:

```text
43 passed, 1 skipped
```

The single skip is `detection/test_detector.py` because this isolated build environment does not have the `ultralytics` package installed. The release requirements pin Ultralytics and the Docker image installs the dependency.

Additional hardening tests specifically cover:

- scoped plate matching/no cross-vehicle fallback;
- vehicle-scoped helmet inference;
- plate persistence into violation records and simulated alerts;
- live processor wiring from camera frame to violation/evidence/DB;
- mandatory human-review state transitions;
- API-key collision detection and subject-aware audit records;
- bounded temporal state and reconnect backoff reset;
- bounded evidence paths and privacy redaction;
- signal-plan single-approach allocation and tracking configuration validation.
