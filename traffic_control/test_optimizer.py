import unittest
from .optimizer import ApproachState, SignalOptimizer


class SignalOptimizerTests(unittest.TestCase):
    def test_high_demand_gets_more_green(self):
        plan = SignalOptimizer(cycle_seconds=120).optimize("J1", [
            ApproachState("N", 100, 50, 8),
            ApproachState("E", 20, 5, 25),
        ])
        self.assertEqual(sum(p.green_seconds for p in plan.phases), 120)
        self.assertGreater(next(p.green_seconds for p in plan.phases if p.approach_id == "N"), next(p.green_seconds for p in plan.phases if p.approach_id == "E"))

    def test_emergency_priority_is_confidence_gated(self):
        low = SignalOptimizer(cycle_seconds=120).optimize("J1", [
            ApproachState("N", 10, 3, emergency_vehicle=True, emergency_confidence=.80),
            ApproachState("E", 40, 20),
        ])
        self.assertIsNone(low.emergency_priority_approach)
        high = SignalOptimizer(cycle_seconds=120).optimize("J1", [
            ApproachState("N", 10, 3, emergency_vehicle=True, emergency_confidence=.96),
            ApproachState("E", 40, 20),
        ])
        self.assertEqual(high.emergency_priority_approach, "N")
        self.assertTrue(next(p for p in high.phases if p.approach_id == "N").emergency_priority)

    def test_bounds_and_empty_input(self):
        with self.assertRaises(ValueError):
            SignalOptimizer(cycle_seconds=10, min_green=10).optimize("J1", [ApproachState("N", 1, 1), ApproachState("E", 1, 1)])
        with self.assertRaises(ValueError):
            SignalOptimizer().optimize("J1", [])


if __name__ == "__main__":
    unittest.main()
