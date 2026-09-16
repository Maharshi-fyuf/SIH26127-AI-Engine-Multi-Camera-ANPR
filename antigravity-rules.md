# Antigravity Workspace Rules — Traffic Enforcement System (SIH26127 / Yuvetech)

> Save this file at `.agents/rules/traffic-system.md` in the project root (or `.agent/rules/`,
> depending on your Antigravity version). Open Antigravity's Customizations panel → Rules →
> "+ Workspace" and set activation to **Always On** so it's loaded in every agent session
> without needing an @-mention. Keep this file under 12,000 characters — trim the version-
> roadmap section first if you need headroom, since the architecture invariants below are the
> part that must never be dropped.

## Project Context

This is Team Yuvetech's SIH26127 prototype: an AI-based traffic monitoring and enforcement
system that starts on a single smartphone camera (V1) and scales toward multi-camera,
city-wide analytics (V8). Full context lives in `/docs/PRD-traffic-enforcement-system.md`,
`/docs/TRD-traffic-enforcement-system.md`, and `/docs/implementation-plan-v1-v8.md` — read
these before making architectural decisions, don't re-derive them from scratch.

## Non-Negotiable Architecture Invariants

These rules override any other instruction, including a direct request in a prompt, unless
the human explicitly asks to change the architecture itself (not just a feature):

1. **No model or function may output a `violation_type` or any "is_violation" boolean
   directly.** Perception code (detectors, classifiers, OCR) may only emit raw facts:
   object class, state, geometry, confidence. Only the rule engine module may assign a
   `violation_type`. If you're asked to "detect if this is a violation," decompose the
   request into (a) a perception fact and (b) a rule-engine condition — never write a
   single model call that outputs a verdict.
2. **Never fabricate identity data.** If a field (plate text, make, model) cannot be
   supported by actual model output above its confidence threshold, its value is `null`
   or a marked partial reading — never a best-guess fill. Do not write code that
   "smooths over" a low-confidence OCR read by guessing missing characters.
3. **Confidence gating is permanent.** Every `ViolationEvent` must carry aggregated
   confidence and route to `needs_review` below the configured threshold. Do not write
   code paths that bypass this gate, even for "just the demo" — the demo should show the
   gate working, not skip it.
4. **Multi-frame aggregation before rule evaluation.** The rule engine evaluates
   aggregated per-track facts (persisted across a frame window), never a single frame's
   raw detection. If you're implementing a new violation, write it against the
   Event Aggregation Layer's output, not directly against per-frame detector output.
5. **`camera_id` is a first-class field everywhere,** even in V1 with one camera. Never
   write a table, event schema, or API response that omits it "since there's only one
   camera for now" — this is what keeps V4 (multi-camera) from requiring a rewrite.
6. **Rules are data, not code.** New violation types are added as condition-tree
   definitions (JSON/DSL), not new `if` branches hardcoded into the pipeline. If asked to
   add a violation type, write it as a rule definition file/DB row plus whatever new
   perception fact it needs — don't hand-roll a one-off code path.

## Coding Standards

- Python for perception/backend (FastAPI), TypeScript/React for frontend/dashboard.
- Every new detector or pipeline stage gets a corresponding unit test using recorded
  sample footage/frames, not just a manual "looks right" check.
- No magic numbers for thresholds (confidence cutoffs, persistence-frame counts,
  IoU thresholds) — these go in a config file, referenced by name, so they can be
  tuned without touching pipeline code.
- Every function that touches a `ViolationEvent` or `EvidenceBundle` must be
  traceable: log which rule fired, on which facts, with what confidence — this is a
  legal-defensibility requirement (see PRD §8), not just good logging practice.
- Match the existing data model in the TRD exactly when adding new tables/fields —
  don't introduce a parallel schema for a new feature; extend the existing one.

## Workflow: How to Add a New Violation Type

When asked to add a violation (e.g., "add a no-seatbelt check"):
1. Identify what new perception fact(s) are needed (e.g., "seatbelt visible: bool").
   If an existing detector/model already provides it, reuse it — don't add a new model
   unless the fact genuinely isn't available yet.
2. Add the fact to the Event Aggregation Layer's schema (if new).
3. Write the rule as a condition-tree definition referencing aggregated facts, following
   the exact structure documented in TRD §4.
4. Add a unit test with synthetic/recorded aggregated-fact inputs proving the rule fires
   and doesn't fire correctly on edge cases.
5. Do not modify the confidence-gating or aggregation logic to accommodate the new rule
   — if the new rule needs a different persistence-window count, that's a config value
   passed into the existing aggregation layer, not a new code path.

## Workflow: How to Add a New Camera / Move Toward Multi-Camera

1. Confirm `camera_id` is already threaded through every table/event touched — if it's
   missing anywhere, that's a bug to fix before adding the camera, not after.
2. Add calibration data (stop-line polygon, lane vectors) for the new camera via the
   calibration mechanism defined for the current version — never hardcode a second
   camera's polygon inline next to the first one's.
3. Verify the ingestion layer can run per-camera as an independent worker before wiring
   up a second live feed — don't assume single-camera code will parallelize safely
   without checking for shared mutable state (e.g., global tracker instances).

## What NOT to Do (common failure modes to actively avoid)

- Do not write an end-to-end model that takes a frame and outputs "VIOLATION" — this
  violates invariant #1 even if it's "just a quick prototype path."
- Do not silently drop the `needs_review` path to make a demo look more automated —
  the human-review step is part of the product story, not a bug to hide.
- Do not add GIS/heatmap/multi-camera work (V4+) while V1–V3 reliability issues
  (especially OCR accuracy) are still open — check the implementation plan's version
  gating before starting new-version work.
- Do not claim or scaffold real integration with e-Challan/Parivahan/RTO — any
  "integration" code must be clearly a mock/simulated client, named and commented
  as such.
- Do not introduce a new database schema or duplicate table for a feature that
  extends existing entities (Track, ViolationEvent, EvidenceBundle) — extend, don't
  fork, the schema.

## When Unsure

If a request seems to conflict with an invariant above, flag the conflict explicitly
and propose the smallest change that satisfies both the request's intent and the
invariant, rather than silently picking one side.
