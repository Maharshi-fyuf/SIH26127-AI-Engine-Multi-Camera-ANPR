# Future Plans and Roadmap (V4-V8)

This document now tracks the implemented V4-V8 demo capabilities for the SIH26127 Traffic Enforcement System. V2 review/health/triple-riding hooks and V3 seatbelt/calibration/migration helpers are also represented in code.

## V4 - Multi-Camera Support
1. Implemented per-camera workers in `ingestion/multi_camera.py`.
2. Scoped rule-engine deduplication by `camera_id:track_id`.
3. Added dashboard snapshots, review queue payloads, and SSE-formatted updates in `api/dashboard.py`.
4. Added a deterministic two-feed concurrency test in `test_v4_to_v8_plan.py`.

## V5 - Cross-Camera Vehicle Tracking
1. Added `tracking/reid.py` with a batchable color-histogram embedding fallback.
2. Added camera-pair travel-window constraints.
3. Added trajectory stitching with cosine similarity.

## V6 - GIS & Spatial Analytics
1. Added camera-location and trajectory-point models.
2. Added violation-density heatmap bucketing.
3. Added origin-destination reporting.

## V7 - Blacklist & Alerting Intelligence
1. Added blacklist persistence methods and `BlacklistMatcher`.
2. Added repeat-offender detection.
3. Added severity-aware alert routing.

## V8 - Production-Readiness Layer
1. Added an in-memory event bus abstraction for local demos.
2. Added retention enforcement for non-violation footage.
3. Added an accuracy/audit report renderer and template.
4. Added `docs/RTO-eChallan-integration-spec.md`.


## V9 — Adaptive Traffic Signal Optimization
1. Added a deterministic demand-weighted signal timing recommendation engine in `traffic_control/optimizer.py`.
2. Uses vehicle count, queue length, speed and saturation to calculate bounded green-time recommendations.
3. Added confidence-gated emergency vehicle priority recommendations.
4. Added authenticated `POST /api/signals/optimize` API with audit logging.
5. The prototype is recommendation-only; direct signal actuation requires authorized traffic-controller integration and safety interlocks.
*Exit criteria:* Given simulated camera-derived traffic states, produce a bounded, explainable signal plan and emergency-priority recommendation without changing a real controller.
