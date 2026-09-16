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

    def evaluate(self, track_id: str, camera_id: str, aggregated_facts: Dict[str, Any], confidences: Dict[str, float]) -> List[ViolationEvent]:
        """
        Evaluates the aggregated facts against the declarative rules.
        """
        violations = []
        scoped_track_key = f"{camera_id}:{track_id}"
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
                
                status = "confirmed" if aggregated_confidence >= self.confidence_threshold else "needs_review"
                
                event = ViolationEvent(
                    event_id=str(uuid.uuid4()),
                    track_id=track_id,
                    camera_id=camera_id,
                    violation_type=rule["violation_type"],
                    rule_confidence=rule_confidence,
                    aggregated_confidence=aggregated_confidence,
                    status=status,
                    timestamp_ms=time.time() * 1000.0
                )
                violations.append(event)
                
                # Mark as emitted so we don't duplicate it for this track on future frames
                if status in ("confirmed", "needs_review"):
                    self.emitted_violations[scoped_track_key].add(violation_type)
                
        return violations
