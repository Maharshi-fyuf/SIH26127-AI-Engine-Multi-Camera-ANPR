import os
import time
from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class RetentionDecision:
    path: str
    action: str
    reason: str


class RetentionManager:
    """
    Enforces the V8 privacy posture: non-violation footage can be purged, while
    evidence tied to a ViolationEvent is retained for audit review.
    """

    def __init__(self, non_violation_retention_days: int = 7):
        self.non_violation_retention_days = non_violation_retention_days

    def purge_non_violation_files(self, paths: Iterable[str], protected_paths: Iterable[str]) -> List[RetentionDecision]:
        protected = {os.path.abspath(path) for path in protected_paths}
        cutoff = time.time() - self.non_violation_retention_days * 24 * 60 * 60
        decisions: List[RetentionDecision] = []
        for path in paths:
            abs_path = os.path.abspath(path)
            if abs_path in protected:
                decisions.append(RetentionDecision(path, "retain", "linked_to_violation_event"))
                continue
            if not os.path.exists(abs_path):
                decisions.append(RetentionDecision(path, "skip", "missing"))
                continue
            if os.path.getmtime(abs_path) <= cutoff:
                os.remove(abs_path)
                decisions.append(RetentionDecision(path, "purge", "expired_non_violation_footage"))
            else:
                decisions.append(RetentionDecision(path, "retain", "inside_retention_window"))
        return decisions
