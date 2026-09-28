import json
import logging
import uuid
import time
from typing import List, Dict, Any
from rule_engine.models import ViolationEvent

logger = logging.getLogger(__name__)

class RuleEngine:
    def __init__(self, rules_path: str, confidence_threshold: float = 0.75):
        self.rules_path = rules_path
        self.confidence_threshold = confidence_threshold
        self.rules = self._load_rules()
        self.emitted_violations: Dict[str, set] = {}
        self._last_seen_ms: Dict[str, float] = {}
        self.state_ttl_ms = 60 * 60 * 1000.0

    def _load_rules(self) -> List[Dict[str, Any]]:
        with open(self.rules_path, 'r') as f:
            data = json.load(f)
            return data.get("rules", [])

    def _evaluate_condition(self, condition: Dict[str, Any], facts: Dict[str, Any]) -> bool:
        fact_key = condition["fact"]
        if fact_key not in facts:
            return False
            
        fact_value = facts[fact_key]
        expected_value = condition["value"]
        op = condition["op"]

        if op == "==":
            return fact_value == expected_value
        elif op == "!=":
            return fact_value != expected_value
        elif op == ">":
            return fact_value > expected_value
        elif op == "<":
            return fact_value < expected_value
        elif op == ">=":
            return fact_value >= expected_value
        elif op == "<=":
            return fact_value <= expected_value
        else:
            logger.warning(f"Unknown operator: {op}")
            return False

    def evaluate(self, track_id: str, camera_id: str, aggregated_facts: Dict[str, Any], confidences: Dict[str, float], *, timestamp_ms: float | None = None) -> List[ViolationEvent]:
        """
        Evaluates the aggregated facts against the declarative rules.
        """
        now_ms = timestamp_ms if timestamp_ms is not None else time.time() * 1000.0
        cutoff = now_ms - self.state_ttl_ms
        for key, seen_ms in list(self._last_seen_ms.items()):
            if seen_ms < cutoff:
                self._last_seen_ms.pop(key, None)
                self.emitted_violations.pop(key, None)
        violations = []
        scoped_track_key = f"{camera_id}:{track_id}"
        self._last_seen_ms[scoped_track_key] = now_ms
        if scoped_track_key not in self.emitted_violations:
            self.emitted_violations[scoped_track_key] = set()
        
        for rule in self.rules:
            violation_type = rule["violation_type"]
            # Deduplication: Don't emit the same violation twice for the same track
            if violation_type in self.emitted_violations[scoped_track_key]:
                continue
                
            rule_matched = True
            for condition in rule.get("conditions", []):
                if not self._evaluate_condition(condition, aggregated_facts):
                    rule_matched = False
                    break
                    
            if rule_matched:
                # Calculate aggregated confidence specific to this rule
                relevant_keys = rule.get("relevant_confidence_keys", [])
                if relevant_keys and confidences:
                    filtered_confidences = [v for k, v in confidences.items() if k in relevant_keys]
                    aggregated_confidence = sum(filtered_confidences) / max(len(filtered_confidences), 1)
                elif confidences:
                    # Fallback if rule doesn't declare relevant keys
                    aggregated_confidence = sum(confidences.values()) / len(confidences)
                else:
                    aggregated_confidence = 0.0

                rule_confidence = aggregated_confidence
                
                # Every machine-detected violation enters human review. Confidence
                # is preserved as evidence metadata, never as an automatic legal verdict.
                status = "needs_review"
                
                event = ViolationEvent(
                    event_id=str(uuid.uuid4()),
                    track_id=track_id,
                    camera_id=camera_id,
                    violation_type=rule["violation_type"],
                    rule_confidence=rule_confidence,
                    aggregated_confidence=aggregated_confidence,
                    status=status,
                    timestamp_ms=now_ms,
                    plate_text=aggregated_facts.get("plate_text"),
                    plate_confidence=float(aggregated_facts.get("plate_confidence", 0.0) or 0.0),
                    plate_is_full=bool(aggregated_facts.get("plate_is_full", False))
                )
                violations.append(event)
                
                # Mark as emitted so we don't duplicate it for this track on future frames.
                self.emitted_violations[scoped_track_key].add(violation_type)
                
        return violations
