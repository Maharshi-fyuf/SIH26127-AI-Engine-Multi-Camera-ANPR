# RTO / e-Challan Integration Specification

## Purpose
This document defines the production integration boundary between the traffic enforcement system and a real RTO/e-Challan service. The demo build must continue to label all outbound challans as simulated until an authorized government API contract, credentials, and legal operating approval are in place.

## Required Inputs
- `event_id`, `camera_id`, `timestamp`, `location`, `violation_type`, confidence, and human-review status.
- Evidence bundle references for cropped images, clips, and metadata.
- Plate read with OCR confidence and validation status.
- Officer or reviewer identity for any manually approved enforcement action.

## API Contract Needed From Authority
- Authentication method, token lifetime, and key-rotation process.
- Accepted violation codes and evidence formats.
- Plate-owner lookup policy and allowed data fields.
- Idempotency key behavior for duplicate submissions.
- Error and appeal status callbacks.

## Submission Flow
1. Confirm the event through the rule engine and confidence gate.
2. Route low-confidence or sensitive matches to human review.
3. Package evidence with immutable metadata and model version identifiers.
4. Submit only confirmed events using `event_id` as the idempotency key.
5. Store the authority response reference and callback status.

## Privacy And Retention
Retention and redaction controls are designed around India's Digital Personal Data Protection Act, 2023. Non-violation footage should be auto-purged after the configured retention window. Bystander plates and identities not tied to a confirmed `ViolationEvent` should be redacted or discarded.
