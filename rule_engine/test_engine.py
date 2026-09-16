import unittest
import os
import json
from rule_engine.engine import RuleEngine

class TestRuleEngine(unittest.TestCase):
    def setUp(self):
        # Create a temporary rules file
        self.rules_path = "temp_rules.json"
        rules_data = {
            "rules": [
                {
                    "violation_type": "RED_LIGHT_VIOLATION",
                    "conditions": [
                        {"fact": "signal_state", "op": "==", "value": "RED"},
                        {"fact": "crossed_stop_line", "op": "==", "value": True},
                        {"fact": "persistence_frames", "op": ">=", "value": 5}
                    ]
                },
                {
                    "violation_type": "NO_HELMET_VIOLATION",
                    "conditions": [
                        {"fact": "vehicle_class", "op": "==", "value": "motorcycle"},
                        {"fact": "has_helmet", "op": "==", "value": False},
                        {"fact": "persistence_frames", "op": ">=", "value": 5}
                    ]
                }
            ]
        }
        with open(self.rules_path, "w") as f:
            json.dump(rules_data, f)
            
        self.engine = RuleEngine(rules_path=self.rules_path, confidence_threshold=0.75)

    def tearDown(self):
        if os.path.exists(self.rules_path):
            os.remove(self.rules_path)

    def test_red_light_violation_confirmed(self):
        facts = {
            "signal_state": "RED",
            "crossed_stop_line": True,
            "persistence_frames": 10
        }
        confidences = {
            "track": 0.9,
            "detection": 0.85,
            "signal": 0.8
        }
        
        events = self.engine.evaluate("track_1", "cam_1", facts, confidences)
        
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.violation_type, "RED_LIGHT_VIOLATION")
        self.assertEqual(event.status, "confirmed") # Avg conf is ~0.85 > 0.75
        self.assertGreater(event.aggregated_confidence, 0.75)

    def test_helmet_violation_needs_review(self):
        facts = {
            "vehicle_class": "motorcycle",
            "has_helmet": False,
            "persistence_frames": 5
        }
        # Low confidence forces needs_review
        confidences = {
            "track": 0.8,
            "detection": 0.6,
            "helmet": 0.5 
        }
        
        events = self.engine.evaluate("track_2", "cam_1", facts, confidences)
        
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.violation_type, "NO_HELMET_VIOLATION")
        self.assertEqual(event.status, "needs_review") # Avg conf is ~0.63 < 0.75

    def test_no_violation(self):
        # Meets some conditions but not all (persistence < 5)
        facts = {
            "signal_state": "RED",
            "crossed_stop_line": True,
            "persistence_frames": 2
        }
        
        events = self.engine.evaluate("track_3", "cam_1", facts, {})
        self.assertEqual(len(events), 0)

if __name__ == '__main__':
    unittest.main()
