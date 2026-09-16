# YUVATECH Production Candidate — Hardening Release

This release specifically resolves the recurring V9 audit findings.

## Fixed

- Specialist model bootstrap for plate, helmet and seatbelt inference.
- Plate localization → preprocessing → OCR → temporal voting pipeline.
- Tesseract fallback for offline/dev OCR when PaddleOCR is unavailable.
- Explicit operator/reviewer/investigator/auditor/admin API-key roles.
- RTSP/RTMP/webcam reconnect with exponential backoff and health state.
- SQLite WAL, busy timeout, foreign keys, and transient lock retries.
- Wawp official REST fallback enabled by default; SDK remains optional.
- Stale pytest cache and runtime `traffic.db` removed from release packaging.
- Dashboard provider label corrected to `Wawp`.
- Norfair-first tracking with deterministic fallback for dependency-light environments.
- Full local test suite now passes in the build environment except the vehicle-detector test, which requires the actual Ultralytics runtime/model package.

## Model provenance

See `models/MODEL_LICENSES.md`. The repository does not claim ownership of third-party specialist checkpoints.

## Important

The specialist weights are intentionally reproducibly bootstrapped rather than silently represented as YUVATECH-owned assets. Run:

```bash
python scripts/bootstrap_models.py --all
```

before live inference, or enable `YUVATECH_AUTO_DOWNLOAD_MODELS=true`.

The seatbelt checkpoint is AGPL-3.0. Replace it with a suitably licensed internally trained checkpoint if that license is not acceptable for the deployment.

## Verification

`pytest -q` in the packaging environment: **34 passed, 1 skipped**. The sole skip is `detection/test_detector.py`, because this isolated build environment does not have the `ultralytics` package installed. The release `requirements.txt` pins Ultralytics and the deployment image installs it.
