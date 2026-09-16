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
