from dataclasses import dataclass
from typing import Optional

@dataclass
class ViolationEvent:
    event_id: str
    track_id: str
    camera_id: str
    violation_type: str
    rule_confidence: float
    aggregated_confidence: float
    status: str  # "confirmed" or "needs_review"
    timestamp_ms: float
    evidence_bundle_ref: Optional[str] = None
    # Plate identity is optional because a camera may not obtain a reliable read.
    # It is populated only from the scoped PlatePipeline result for this track.
    plate_text: Optional[str] = None
    plate_confidence: float = 0.0
    plate_is_full: bool = False
