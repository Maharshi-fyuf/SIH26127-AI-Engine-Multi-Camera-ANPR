# YUVATECH SIH26127 — V11 Final Audit Remediation

This release addresses the 23 findings from the independent V10 code/architecture audit.

## Critical correctness / architecture

1. **Live deployment path** — `run_worker.py` owns `MultiCameraRunner` and `LiveCameraProcessor`; Docker Compose separates API and perception worker.
2. **Plate identity propagation** — `PlatePipeline` → `EventAggregator` → `ViolationEvent` → SQLite/evidence/alert metadata.
3. **Helmet scoping** — YOLO inference is performed on the target vehicle crop and coordinates are mapped back to the frame.
4. **Plate cross-vehicle fallback** — no scoped plate match now means no plate result; another vehicle's plate is never used.
5. **Review status** — all machine-created violations enter `needs_review`; confidence is evidence metadata, not an automatic legal verdict.
6. **Escalation workflow** — `escalated` can return to `approved` or `rejected`, after which approved events can become `verified`.
7. **Audit identity** — API keys map to explicit subject IDs and the violation-detail endpoint records the authenticated principal.
8. **Duplicate API keys** — startup fails fast if two configured role keys are identical.

## Reliability / data integrity

9. **Reconnect backoff reset** — successful frame bursts reset consecutive retry backoff; total reconnect count remains monotonic.
10. **Bounded in-memory state** — aggregator, rule-engine deduplication, plate readers and OCR temporal voting are bounded/TTL-pruned.
11. **Re-ID track linkage** — embeddings carry the real camera track ID and the live pipeline persists them; an authenticated trajectory-stitch endpoint invokes `TrajectoryStitcher`.
12. **Evidence paths** — artifacts are only recorded when `cv2.imwrite` succeeds and the file exists.
13. **Privacy redaction** — bystander person regions are blurred before scene/context evidence export; the metadata records whether redaction was applied.
14. **Signal timing** — a single emergency approach receives the full cycle rather than silently losing leftover green time.
15. **SQLite lifecycle** — every DB operation uses an explicit connection context that closes connections after commit/rollback.
16. **Video capture lifecycle** — failed `VideoCapture` opens are released before raising.

## Hygiene / semantics

17. **Rule-engine tautology** — unconditional dedup registration replaces the redundant status condition.
18. **Accuracy metrics** — `false_discovery_rate` is distinct from true `false_positive_rate`; FPR is reported as `N/A` when true negatives are unavailable.
19. **Synthetic detector helpers** — removed from production detector classes and moved to `tests/fixtures.py`.
20. **Centralized notification settings** — Wawp and SMTP settings are passed explicitly from `config.settings`.
21. **Tracking thresholds** — IoU and Euclidean threshold configurations are validated; the old magic-number fallback is removed.
22. **Triple-riding geometry** — pixel margins scale with vehicle bounding-box height.
23. **SQL inserts** — review, audit, notification and vehicle-observation inserts use explicit column lists.

## Additional wiring

- Control-room dashboard is served through the dashboard view model.
- Camera anomaly scoring is exposed in `/health`.
- Violation heatmap is exposed through `/api/analytics/heatmap`.
- Retention cleanup is exposed as an authenticated admin operation at `/api/governance/retention/run`.
- The event bus receives machine-detected violation events.
- Re-ID embeddings are persisted per camera/track.
- `desktop.ini`, `tracker_code.txt`, runtime databases, bytecode and pytest caches are excluded from the release package.

## Verification

`python -m compileall -q .` passes.

`pytest -q`:

- **43 passed**
- **1 skipped** — the vehicle-detector test is skipped only because the isolated packaging environment does not have `ultralytics` installed; the production requirements include it.

The release does not claim that third-party specialist model checkpoints are YUVATECH-owned. Their provenance and licenses remain documented in `models/MODEL_LICENSES.md`.
