"""Lightweight operational anomaly scoring without pretending to be ML."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class CameraAnomaly:
    camera_id: str
    score: float
    reasons: list[str]

def score_camera(camera_id: str, *, frames_processed: int, events_emitted: int,
                  last_frame_age_ms: float, error: str | None = None) -> CameraAnomaly:
    reasons=[]; score=0.0
    if error: score += .5; reasons.append("camera_error")
    if frames_processed > 100 and events_emitted == 0: score += .2; reasons.append("no_events")
    if last_frame_age_ms > 10000: score += .4; reasons.append("stale_frames")
    return CameraAnomaly(camera_id, min(1.0, score), reasons)
