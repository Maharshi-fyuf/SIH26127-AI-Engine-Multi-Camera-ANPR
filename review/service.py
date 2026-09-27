"""Human-review state machine. Only verified events may reach citizen notification."""
from __future__ import annotations
from dataclasses import dataclass

VALID = {"needs_review", "approved", "rejected", "escalated", "verified"}

@dataclass
class ReviewDecision:
    event_id: str
    old_status: str
    new_status: str
    reviewer: str
    note: str = ""

def validate_transition(old: str, new: str) -> bool:
    if old not in VALID or new not in VALID:
        return False
    if old == new:
        return True
    if old == "needs_review" and new in {"approved", "rejected", "escalated"}:
        return True
    if old == "escalated" and new in {"approved", "rejected"}:
        return True
    return old == "approved" and new == "verified"
