from dataclasses import dataclass
from detection.detector import BoundingBox

@dataclass
class HelmetFact:
    bounding_box: BoundingBox
    has_helmet: bool
    confidence: float
    is_placeholder: bool = False

@dataclass
class SignalStateFact:
    bounding_box: BoundingBox
    state: str  # "RED", "GREEN", "AMBER", "UNKNOWN"
    confidence: float
    is_placeholder: bool = False
