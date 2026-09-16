# YUVATECH Live Deployment Guide

## 1. Environment

Copy `.env.example` to `.env` and replace every `CHANGE_ME_*` value with a strong random secret. Never commit `.env`.

Roles are intentionally separate:

- `operator` — live monitoring/camera views
- `reviewer` — violation review and verification
- `investigator` — vehicle timeline/history
- `auditor` — audit/report access
- `admin` — configuration and full administrative access

## 2. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Specialist models

The release includes a reproducible bootstrap script. On a connected server:

```bash
python scripts/bootstrap_models.py --all
```

This fetches the pinned public specialist checkpoints into `models/`. Review `models/MODEL_LICENSES.md` before production/commercial use. The seatbelt checkpoint is AGPL-3.0; replace it with an internally trained/appropriately licensed model if that license is unsuitable.

For automatic first-run fetching, set `YUVATECH_AUTO_DOWNLOAD_MODELS=true` and construct detectors through the application configuration. In an offline environment, weights must be copied into `models/` before starting inference.

## 4. Database

SQLite is hardened for the prototype/live-small deployment with WAL, 30-second busy timeout, foreign keys, and transient lock retries. For high-volume city deployment, migrate to PostgreSQL/PostGIS before adding many camera workers.

## 5. Camera reliability

RTSP/RTMP/webcam workers automatically reconnect after disconnects using exponential backoff. File sources terminate normally at EOF. Health status exposes reconnect count and the latest error.

## 6. Start server

```bash
python run_server.py
```

Production example:

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 2
```

Put HTTPS/TLS, firewall rules and a reverse proxy in front of the application.

## 7. Notifications

Wawp uses the official REST endpoint by default, so the private `wawp_sdk` package is optional. Configure `WAWP_INSTANCE_ID` and `WAWP_ACCESS_TOKEN`; keep notifications disabled until credentials and destinations are tested.

The safety flow is mandatory:

```text
AI event -> rule engine -> confidence -> evidence -> human review -> verified -> Wawp/Gmail
```

## 8. Verification

Run the lightweight suite:

```bash
pytest -q
```

For a full CV verification environment, ensure `ultralytics`, `norfair`, and `paddleocr` are installed from `requirements.txt`, the specialist models are present, and run the complete suite again. The repository does not silently skip those tests.
