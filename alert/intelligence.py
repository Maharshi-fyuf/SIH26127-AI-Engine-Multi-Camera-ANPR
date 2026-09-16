import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass
class BlacklistMatch:
    plate_text: str
    reason: str
    severity: str
    confidence: float


class BlacklistMatcher:
    def __init__(self, entries: Dict[str, Dict], min_confidence: float = 0.92):
        self.entries = {self._normalize_plate(k): v for k, v in entries.items()}
        self.min_confidence = min_confidence

    def _normalize_plate(self, plate_text: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", plate_text.upper())

    def match(self, plate_text: str, confidence: float) -> Optional[BlacklistMatch]:
        normalized = self._normalize_plate(plate_text)
        if normalized not in self.entries:
            return None
        entry = self.entries[normalized]
        required_confidence = max(self.min_confidence, float(entry.get("min_confidence", self.min_confidence)))
        if confidence < required_confidence:
            return None
        return BlacklistMatch(
            plate_text=normalized,
            reason=entry.get("reason", "BLACKLIST_MATCH"),
            severity=entry.get("severity", "high"),
            confidence=confidence,
        )


class AlertRouter:
    def __init__(self, routing: Dict[str, str]):
        self.routing = routing

    def route_for(self, violation_type: str, severity: str = "routine") -> str:
        return self.routing.get(f"{violation_type}:{severity}") or self.routing.get(severity) or self.routing.get("default", "console")


def repeat_offender_plates(plate_events: Iterable[Dict], min_violations: int, window_ms: float) -> List[str]:
    by_plate: Dict[str, List[float]] = {}
    for event in plate_events:
        plate = event.get("plate_text")
        timestamp = event.get("timestamp_ms")
        if plate is None or timestamp is None:
            continue
        normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
        by_plate.setdefault(normalized, []).append(float(timestamp))

    offenders: List[str] = []
    for plate, timestamps in by_plate.items():
        ordered = sorted(timestamps)
        for start_index, start_ts in enumerate(ordered):
            end_ts = start_ts + window_ms
            count = sum(1 for ts in ordered[start_index:] if ts <= end_ts)
            if count >= min_violations:
                offenders.append(plate)
                break
    return offenders
