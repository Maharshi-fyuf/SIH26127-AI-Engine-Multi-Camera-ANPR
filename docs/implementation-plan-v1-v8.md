Implementation Plan — V1 through V8 (Revised)
AI-Based Intelligent Traffic Monitoring & Enforcement System (SIH26127, Team Yuvetech)

This plan sequences work so that each version is independently demoable before the next begins. Do not start V(n+1) tasks while V(n) has open reliability issues — this is a hard rule, not a suggestion (see PRD §8, TRD §8).

What changed from v1: every version now has a Risks & Mitigations subsection, a fallback/descope note, and exit criteria written as things you can actually check pass/fail instead of vague adjectives. Added a Day 0 setup checklist, dataset pointers, a priority-tier note for time-crunch triage, and tightened the "reliability issue" definition so the hard rule has teeth.

Day 0 — Before V1 Starts (do this first, don't skip it)
Repo set up with a branching convention (main stays demoable at all times; work happens on v1-dev, merge to main only at each version's exit criteria). Tag main at every version boundary (v1-complete, v2-complete, …) — this is your rollback point if a later version destabilizes things.
Confirm actual demo hardware (phone model, laptop/GPU or lack thereof) before picking model sizes — this decides whether you're running YOLOv8n/s or m/l.
Do a site visit (or get real footage) of the actual intended demo location/angle as early as possible — V1 task 14-15 assume you have this, and getting it late is the single most common cause of last-minute scrambling on projects like this.
Check licensing on any public dataset before training on it — some Indian plate datasets are academic-use-only; note this in your README so it isn't a surprise during judging.
Decide now who owns which vertical slice (perception models vs. rule engine/backend vs. dashboard/UI vs. docs/demo narrative) so V1's tasks can run in parallel across your six people instead of serially.
Guiding Principle: What Counts as an "Open Reliability Issue" (blocks moving to V(n+1))

To make the hard rule enforceable rather than a vibe: a version is not exit-ready if any of these are true —

A rehearsal run crashes, hangs, or requires a manual restart.
Any violation type included in that version's demo shows a fabricated or wrong result in rehearsal (a missed detection is acceptable and expected; a confidently wrong one is not — route it to needs_review instead).
The exit criteria for that version haven't been checked against real (not synthetic) footage at least once.

If you're tempted to start V(n+1) because "it's basically fine" — it isn't exit-ready. Descope instead (see each version's Fallback note).

V1 — Single-Camera Core Pipeline

Goal: live smartphone feed → 2–3 violation types → evidence package → simulated alert, end-to-end.

Set up video ingestion (OpenCV frame extraction from phone stream or recorded clips). Target a sustained 10–15 FPS minimum for stable tracking at road speeds — confirm your phone-streaming path (IP Webcam / DroidCam / RTMP) actually hits this before building on top of it.
Integrate pretrained YOLOv8 for vehicle detection; validate on sample footage. Pick model size (n/s vs. m/l) based on your confirmed demo hardware from Day 0, not the biggest one that fits on a dev machine.
Integrate ByteTrack for multi-object tracking; verify track_id stability, specifically across brief occlusions (one vehicle passing behind another) since that's the most common real-world break case.
Build plate pipeline: fine-tune a plate detector on a public Indian plate dataset (e.g. Kaggle's "Indian License Plates" sets, Roboflow Universe's Indian-plate projects, or IDD for broader scene context); integrate PaddleOCR; implement multi-frame majority-vote + format-regex validation. Treat the regex as a soft plausibility check, not a hard reject — real plates include BH-series, VIP/defense/diplomatic formats, and worn/non-standard plates that won't match a clean pattern.
Build helmet detector (fine-tune YOLO on a public helmet dataset — Kaggle "Helmet Detection" or Roboflow Universe helmet-detection projects are reasonable starting points).
Build signal-state detection (fine-tune localization; HSV-based state classification in ROI). Flag explicitly: this is calibrated to one camera position and is expected to be fragile — that's what V3's calibration UI exists to fix, not a V1 problem to solve.
Manually calibrate stop-line polygon and lane vectors for the demo camera position.
Implement event aggregation layer (persistence-window voting per track).
Implement rule engine with 2–3 rule definitions (helmet, red-light, wrong-side).
Implement confidence gate + needs_review status. Start with a conservative (high) threshold — it's much better to under-flag in rehearsal and tune down than to show judges a wrong verdict.
Implement evidence bundle generation (image crop + short clip + metadata JSON). Include camera_id, rule_id, model version/hash, and confidence score in the metadata — you'll want this for the audit trail story in V8, and it costs nothing to add now.
Build minimal local storage (SQLite) with the camera_id-first schema from day one; index on timestamp too, since most queries will be time-windowed.
Build a simple UI/CLI to display generated events and simulated alerts (clearly labeled simulated).
End-to-end test with real recorded footage from the actual demo location.
Rehearse the live demo at the actual intended camera angle/lighting.

Risks & Mitigations:

OCR fails on real plates (dirt, glare, oblique angle, non-standard fonts) → multi-frame voting + confidence gate + human review fallback are already in scope; don't cut them under time pressure.
Phone stream drops mid-demo (wifi/hotspot flakiness) → always have a pre-recorded fallback clip tested and ready to switch to live, and rehearse the switch itself.
Small local fine-tuning set overfits → combine public datasets with whatever local footage you can gather; heavy augmentation (rotation, blur, brightness) helps more than more epochs on a tiny set.

Fallback / Descope: if a third violation type isn't reliable by rehearsal, cut it rather than show a flaky one — exit criteria only requires ≥2 correctly triggered types.

Exit criteria: live or recorded demo runs start-to-finish without manual intervention on real (not cherry-picked) footage from the actual demo location; ≥2 violation types correctly triggered across at least 3 rehearsal runs; zero fabricated plate/vehicle data shown; no crash or hang across a full rehearsal run.

V2 — Reliability & Coverage Hardening
Collect local plate/helmet footage from the demo environment; fine-tune OCR and helmet models on this data.
Add triple-riding rule (reuses existing person/vehicle detection, no new model). Watch for bicycle-vs-motorcycle confusion in the underlying detector — a rule this cheap is only as good as that distinction.
Build human-review queue UI (accept/reject/edit candidate violations). Treat corrections as a data source: route accepted/edited labels back into the fine-tuning set for the next iteration — this gives you a genuine active-learning story to tell judges, not just a QA tool.
Add pipeline health metrics (detection rate, OCR success rate, per-camera uptime) as a simple dashboard or logged endpoint.
Regression-test V1 violation types against the new fine-tuned models before adding anything new.

Risks & Mitigations:

Collecting local footage is logistically time-critical — this needs the demo-location camera access from Day 0, not a scramble the week of the deadline. Schedule it first, not last, in this version.
Fine-tuning on new data silently regresses an existing violation type — this is exactly what task 5's regression test exists to catch; don't skip it because "it's probably fine."

Fallback / Descope: if local footage collection slips, ship V2 with public-data-only fine-tuning and log the gap honestly in progress.md — a documented known-limitation is fine; a silently-skipped regression test is not.

Exit criteria: OCR and helmet accuracy on a held-out local-footage test set measurably improve over the V1 baseline, with the before/after numbers logged (not just "looks better"); review queue is functional and at least one corrected label has been fed back into a retrain.

V3 — Multi-Violation Expansion + Persistence
Add seatbelt detection module (new detector, fine-tuned).
Migrate storage from SQLite to Postgres; write a migration script and a rollback/backup step, verify no data loss on a full round-trip before deleting the SQLite copy.
Build per-camera calibration admin UI (replace hardcoded polygon values with a config screen).
Add automated tests for rule engine logic (unit tests per rule definition) — include adversarial cases, e.g. a partially occluded plate should downgrade confidence and route to review, not crash or silently pass.

Risks & Mitigations:

SQLite→Postgres type drift (timestamps, JSON columns) is a common silent-corruption source — diff row counts and spot-check a sample of migrated records, don't just check the migration script exits without error.

Fallback / Descope: the calibration UI is the highest-value item here for reducing V4 demo risk (no more hand-editing polygon coordinates per camera) — if time is short, prioritize it over seatbelt detection, which is a nice-to-have violation type, not a structural dependency for later versions.

Exit criteria: three+ violation types running concurrently on the Postgres backend with no data loss verified against the SQLite source; calibration doable without a code change or restart.

V4 — Multi-Camera Support
Refactor ingestion into a per-camera worker process/service.
Extend event log to aggregate across multiple camera_ids cleanly (verify no camera_id leakage/mixing bugs — write a specific test for this, it's an easy silent bug).
Build control-room dashboard: live feed status tiles, violation counts per camera, aggregated review queue. Prefer a push mechanism (WebSocket/SSE) over polling for the live-feel judges will actually notice.
Load-test with 2–3 simultaneous feeds (phones or fixed webcams).

Risks & Mitigations:

Only one physical demo camera is actually available — a very common hackathon constraint. If so, simulate a second feed from looped pre-recorded footage and label it clearly as simulated in the UI, consistent with the no-fabrication rule — the pipeline logic is still real, only the input source is substituted.

Fallback / Descope: if load-testing 3 feeds destabilizes things close to the deadline, 2 verified-stable feeds beat 3 flaky ones for a live demo.

Exit criteria: 2+ cameras running simultaneously with zero cross-camera_id attribution errors observed across a full rehearsal; dashboard updates within a second or two of an event, not on a stale poll.

V5 — Cross-Camera Vehicle Tracking
Integrate a lightweight Re-ID embedding model (e.g., OSNet) for tracked vehicle crops. Run embedding extraction async/batched, not inline in the real-time detection loop — it's compute-heavy enough to stall everything else if blocking.
Define known relative geometry/offsets between camera pairs used in the demo.
Implement trajectory stitching: match Re-ID embeddings across cameras within a plausible time window.
Validate stitching accuracy manually against ground-truth footage of the same vehicle passing both cameras.

Risks & Mitigations:

Re-ID accuracy is very sensitive to lighting/angle differences between cameras — for the demo specifically (not as a production claim), choose two camera positions with similar lighting and viewing angle to make stitching actually reliable on stage. Say so plainly in your presentation — judges generally respond better to "we know this is the fragile part and here's why" than to an unqualified claim.

Fallback / Descope: this version has the worst effort-to-demo-reliability ratio in the whole plan. If time is genuinely tight, a strong V4 plus a clearly-labeled "here's how V5 would work" slide is a safer bet than a live cross-camera demo that might not stitch correctly on stage.

Exit criteria: demonstrable single-vehicle trajectory reconstructed across 2 cameras, validated against ground truth at least twice with a consistent match.

V6 — GIS & Spatial Analytics
Add PostGIS extension; store camera locations and stitched trajectories spatially.
Integrate a map layer (Leaflet/Mapbox) into the dashboard for trajectory visualization.
Build a batch job for violation-density heatmaps (by location/time bucket).
Build a basic OD (origin-destination) analysis report from stitched trajectory data.

Risks & Mitigations:

A real demo will generate very little trajectory volume — a heatmap over 5 real data points looks sparse and unconvincing regardless of how correct the code is. If you want a heatmap that reads well on stage, it's fine to overlay a clearly-labeled "simulated at city scale" dataset for illustration purposes distinct from and visually differentiated from the real pipeline output — never blend the two without a label.

Fallback / Descope: this is the most purely presentational version in the plan; if time runs out here, a static map mockup with a caption explaining the intended pipeline is a reasonable substitute for working PostGIS + Leaflet integration.

Exit criteria: map view showing at least one real (not simulated) trajectory, plus a heatmap that is clearly labeled if it includes simulated-scale data.

V7 — Blacklist & Alerting Intelligence
Build blacklist table (plate list) and real-time match-on-read logic in the plate pipeline. Require a higher OCR-confidence threshold specifically for blacklist matches than for ordinary violations — a false positive here (misreading an innocent plate as a blacklisted one) is a worse failure mode than a missed one.
Implement repeat-offender detection (same plate, N violations in window → escalation flag).
Build configurable alert routing (map violation type/severity to notification channel). For demo purposes, a webhook into Slack/Discord/email is enough — don't build a full notification service for this.

Risks & Mitigations:

Partial/misread plates colliding with a blacklist entry — the elevated confidence threshold in task 1 is the primary mitigation; don't skip it under time pressure since it's cheap to add.

Fallback / Descope: repeat-offender detection (task 2) can be simplified to an in-memory/simple-query check rather than a dedicated service if time is short — the escalation-path demo is what matters, not its production architecture.

Exit criteria: a blacklist match triggers a distinct, higher-priority alert path in the demo, observably different from a routine violation alert (different channel, different visual treatment, or both).

V8 — Production-Readiness Layer
Introduce an event bus (Kafka or Redis Streams) between ingestion and downstream processing. Treat this as largely aspirational for a hackathon — a working minimal version (even just Redis pub/sub) plus a clear diagram of the intended architecture at scale is more credible than an overbuilt one that's untested.
Implement data retention/privacy policy in code (auto-purge non-violation footage after N days; redact bystander plates not tied to any ViolationEvent).
Write a formal accuracy/audit report format suitable for presentation to an actual enforcement authority. Structure it around per-rule precision/recall, false-positive rate, and human-review override rate — those are the numbers an actual evaluator (BEL, in this case) will want to see, more than a narrative description.
Write (not implement) a concrete integration specification for real RTO/e-Challan APIs (India's national e-Challan platform), documenting exactly what would be needed for production connection.

Note on privacy/retention framing: ground task 2 in India's Digital Personal Data Protection (DPDP) Act, 2023, explicitly in your written policy — naming the actual legal framework you're designing against reads as far more credible to judges than a generic "we care about privacy" statement.

Fallback / Descope: this version is explicitly a maturity/documentation milestone as much as a code one — if you're out of build time, the audit report format and privacy policy document alone (task 2's policy written down, even if partially enforced in code, plus task 3) cover most of the credibility this version is meant to buy.

Exit criteria: documented, presentable case for production readiness — this version is a maturity/documentation milestone as much as a code milestone.

Priority Tiers for Time-Crunch Triage

If the deadline arrives before V8 does (likely, for most teams), the safest stopping points in order are:

End of V2 — reliable single-camera pipeline + human review queue + logged accuracy improvement. This alone is a credible, honest demo.
End of V4 — multi-camera with a clean control-room dashboard. Strong visual upgrade over V2, moderate risk.
End of V7 — blacklist/alerting intelligence layer. Good "smart system" narrative, low-to-moderate additional risk since it builds on already-stable V3/V4 infrastructure.

V5 and V6 are the most compute- and data-fragile versions relative to the demo value they add — treat them as stretch goals, not sequential requirements, if time is tight. V8 can legitimately be a slide/document, not code, without weakening the pitch — it's framed as a documentation milestone in the plan for exactly this reason.

Cross-Cutting Rules for Every Version
No version ships with an AI model directly outputting a violation verdict — always through the rule engine (see TRD §8).
No version fabricates vehicle identity data (make/model, full plate) beyond what perception models can actually support. Any simulated data used for presentation purposes (V4 second camera, V6 heatmap scale) must be visually and explicitly labeled as simulated, and must never be blended indistinguishably with real pipeline output.
Every version must be demoable standalone; don't leave a version in a partially-broken state while starting the next — see "What Counts as an Open Reliability Issue" above for a concrete check.
Confidence gating and human review remain permanent, not phased out at higher versions.
Tag main at every version boundary (v1-complete … v8-complete) so there's always a known-good rollback point.
Keep spec.md / progress.md / demo.md updated at each version boundary, including any known-limitation or descope decisions — an honestly documented gap reads better to judges than a silent one they discover during Q&A.