# Product Requirements Document (PRD)
## AI-Based Intelligent Traffic Monitoring & Enforcement System
**Team:** Yuvetech · **Problem Statement:** SIH26127 (ANPR Traffic Analytics, BEL) · **Version:** 1.0

---

## 1. Problem Statement

Manual traffic enforcement in India is limited by the number of officers who can physically observe intersections, is inconsistent in application, and produces poor evidentiary records for contested cases. A camera-based system that can perceive traffic events, apply enforcement rules deterministically, and produce auditable evidence packages addresses this at low marginal cost per additional camera.

## 2. Goal

Build a system that turns a video feed (starting with a single smartphone camera for V1, scaling to fixed multi-camera city infrastructure by V8) into structured, defensible violation records — without ever having an AI model directly decide "this is illegal." Legality is always determined by an explicit, auditable rule engine operating on AI-perceived facts.

## 3. Non-Goals (explicitly out of scope, all versions unless stated)

- Real integration with e-Challan / Parivahan / RTO government databases (no real API access exists for a student team; always simulated)
- Real-time speed enforcement from a single monocular uncalibrated camera (unreliable without stereo/LiDAR or calibrated reference markers)
- Fully automated, human-review-free challan issuance (a confidence gate + human review step is a permanent product requirement, not a V1 limitation)
- Facial recognition of drivers/riders (privacy risk, not needed for any target violation)

## 4. Users / Personas

| Persona | Need |
|---|---|
| Traffic police officer (end user) | Wants a review queue of candidate violations with clear evidence, not raw video to scrub through |
| Traffic control room supervisor (V4+) | Wants aggregate views: violation hotspots, trends, camera health |
| SIH jury (evaluation-time user) | Wants to see a working, explainable pipeline and an honest account of what's real vs. simulated |
| City traffic planner (V6+, aspirational) | Wants OD analysis and heatmaps for infrastructure decisions |

## 5. Success Metrics

- **V1 demo:** live smartphone feed → at least 2 violation types detected end-to-end → evidence package generated → simulated alert shown, in front of a jury, without a crash
- **Precision target (V1):** ≥80% of auto-flagged violations should be genuine on manual review of demo footage (false positives are more damaging to credibility than missed detections in a demo)
- **Plate OCR:** correct full-plate read on ≥60% of readable, non-occluded plates in test footage; partial-plate fallback used the rest of the time (never a blank or fabricated read)

## 6. Guiding Product Principles (apply to every version)

1. **Perception ≠ judgment.** No model output is ever presented as "violation" without passing through the explicit rule engine.
2. **No hallucinated identity.** If a plate can't be fully read, report only what was actually observed (partial plate, vehicle type, color) — never guess make/model without a validated classifier.
3. **Confidence gating is permanent.** Low-confidence events always route to human review, at every version, forever. This is a product requirement, not a placeholder.
4. **Every version must demo standalone.** Each version (V1–V8) must be a coherent, demoable increment — never a broken intermediate state.

## 7. Version Roadmap — Scope Definition

### V1 — Single-Camera Core Pipeline (the MVP)
- One smartphone camera, live or recorded feed
- Vehicle detection + tracking
- 2–3 violations: no-helmet, red-light violation, wrong-side/lane violation
- ANPR with multi-frame OCR voting; partial-plate fallback
- Rule engine (deterministic) + confidence gate
- Evidence package (image/clip + metadata) stored locally
- Simulated challan/alert notification (UI only, clearly labeled simulated)

### V2 — Reliability & Coverage Hardening
- Add triple-riding violation
- Improve OCR accuracy: fine-tune on collected local plate data, add format-regex validation
- Add human-review queue UI (accept/reject candidate violations)
- Basic logging/metrics dashboard for pipeline health (detection rate, OCR success rate)

### V3 — Multi-Violation Expansion + Persistence
- Add seatbelt detection (car occupants)
- Move from local files to a proper database (Postgres) with camera_id-first schema (future-proofing for multi-camera)
- Add configurable per-camera calibration (stop-line polygon, lane vectors) via a simple admin UI instead of hardcoded values

### V4 — Multi-Camera Support
- Support 2+ simultaneous camera feeds (still phones or now fixed webcams)
- Central event log ingesting from multiple camera_ids
- Control-room dashboard: live feed status, violation counts per camera, review queue aggregated across cameras

### V5 — Cross-Camera Vehicle Tracking
- Vehicle re-identification (ReID embeddings) to match the same vehicle across non-overlapping camera views
- Basic trajectory stitching between camera pairs with known relative positions

### V6 — GIS & Spatial Analytics
- Plot camera locations and vehicle trajectories on a real map (GIS layer)
- Traffic heatmaps (violation density by location/time)
- Origin-Destination (OD) analysis from stitched trajectories

### V7 — Blacklist & Alerting Intelligence
- Blacklisted/stolen/wanted vehicle plate list with real-time match-on-read alerting
- Repeat-offender detection (same plate, multiple violations, escalation logic)
- Configurable alert routing (which alerts go to which control room / officer)

### V8 — Production-Readiness Layer
- Horizontal scalability plan for city-wide camera count (queueing/streaming infra, e.g. Kafka-style event bus)
- Data privacy/retention policy implementation (auto-purge of non-violation footage, bystander vehicle redaction)
- Formal accuracy/audit reporting suitable for presenting to an actual enforcement authority
- Documented path to real RTO/e-Challan integration (still not implemented, but a concrete integration spec)

## 8. Risks Called Out at the Product Level

- **Overclaiming risk:** every demo and every slide must describe the system as generating "structured violation reports for review," never as "issuing challans." This applies at every version.
- **OCR reliability is the critical path** for V1 through V3 — do not let team time be pulled into GIS/heatmap work (V6) before the plate pipeline is solid.
- **Scope creep across versions:** each version should ship as a working demoable unit before starting the next; do not begin V(n+1) work while V(n) has open reliability issues.
