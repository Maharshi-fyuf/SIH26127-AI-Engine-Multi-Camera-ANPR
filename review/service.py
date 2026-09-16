"""Human-review state machine. Only verified events may reach citizen notification."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

VALID = {"needs_review", "approved", "rejected", "escalated", "verified"}

@dataclass
class ReviewDecision:
    event_id: str
    old_status: str
    new_status: str
    reviewer: str
    note: str = ""

def validate_transition(old: str, new: str) -> bool:
    if old not in VALID or new not in VALID: return False
    if old == new: return True
    return old == "needs_review" and new in {"approved", "rejected", "escalated"} or old == "approved" and new == "verified"
