from dataclasses import dataclass
from typing import Optional

from alert.intelligence import BlacklistMatch, BlacklistMatcher
from plate.models import OcrFact


@dataclass
class PlateReadDecision:
    plate_text: str
    ocr_confidence: float
    is_format_valid: bool
    blacklist_match: Optional[BlacklistMatch] = None


def evaluate_plate_read(ocr_fact: OcrFact, blacklist_matcher: Optional[BlacklistMatcher] = None) -> PlateReadDecision:
    match = None
    if blacklist_matcher is not None and ocr_fact.is_format_valid:
        match = blacklist_matcher.match(ocr_fact.text, ocr_fact.confidence)
    return PlateReadDecision(
        plate_text=ocr_fact.text,
        ocr_confidence=ocr_fact.confidence,
        is_format_valid=ocr_fact.is_format_valid,
        blacklist_match=match,
    )
