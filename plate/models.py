from dataclasses import dataclass
from detection.detector import BoundingBox

@dataclass
class PlateDetectionFact:
    """Raw fact representing a localized license plate."""
    bounding_box: BoundingBox
    confidence: float
    is_placeholder: bool = False

@dataclass
class OcrFact:
    """Raw fact representing text extracted from a plate."""
    text: str
    confidence: float
    is_format_valid: bool
