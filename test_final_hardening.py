import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from attribute_pipeline.helmet import HelmetDetector
from db.manager import DatabaseManager
from detection.detector import BoundingBox, DetectionEvent, DetectionFact
from ingestion.stream import FrameEvent
from plate.models import OcrFact, PlateDetectionFact
from plate.pipeline import PlatePipeline
from rule_engine.models import ViolationEvent
from alert.alert import SimulatedAlertGenerator


class FakePlateDetector:
    def __init__(self, detections):
        self.detections = detections

    def detect(self, event):
        yield from self.detections


class FakePlateOcr:
    def read_text(self, crop):
        return OcrFact("GJ01AB1234", 0.95, True)


class TestFinalHardening(unittest.TestCase):
    def test_plate_pipeline_never_uses_other_vehicle_plate(self):
        frame = FrameEvent("cam", 1, 1000.0, np.zeros((100, 100, 3), dtype=np.uint8))
        other_vehicle_plate = PlateDetectionFact(BoundingBox(70, 70, 90, 90), 0.99)
        pipeline = PlatePipeline(FakePlateDetector([other_vehicle_plate]), FakePlateOcr(), min_votes=1)

        result = pipeline.process(frame, BoundingBox(10, 10, 40, 40), "cam:track-1")
        self.assertIsNone(result)

    def test_plate_pipeline_keeps_scoped_vehicle_plate(self):
        frame = FrameEvent("cam", 1, 1000.0, np.zeros((100, 100, 3), dtype=np.uint8))
        plate = PlateDetectionFact(BoundingBox(20, 25, 38, 32), 0.91)
        pipeline = PlatePipeline(FakePlateDetector([plate]), FakePlateOcr(), min_votes=1)

        result = pipeline.process(frame, BoundingBox(10, 10, 50, 50), "cam:track-1")
        self.assertIsNotNone(result)
        self.assertEqual(result["voted"].text, "GJ01AB1234")

    def test_helmet_detector_inference_is_scoped_to_vehicle_crop(self):
        calls = []

        class FakeBox:
            cls = [SimpleNamespace(__int__=lambda self: 0)]
            conf = [SimpleNamespace(__float__=lambda self: 0.9)]
            xyxy = [SimpleNamespace(tolist=lambda self: [2, 3, 10, 12])]

        # The production detector uses int(box.cls[0]) / float(box.conf[0]),
        # so provide scalar-like values with the expected conversions.
        class Scalar:
            def __init__(self, value): self.value = value
            def __int__(self): return int(self.value)
            def __float__(self): return float(self.value)

        class Box:
            cls = [Scalar(0)]
            conf = [Scalar(0.9)]
            xyxy = [SimpleNamespace(tolist=lambda: [2, 3, 10, 12])]

        class Model:
            names = {0: "helmet"}
            def __call__(self, image, **kwargs):
                calls.append(image.shape)
                return [SimpleNamespace(boxes=[Box()], names=self.names)]

        detector = object.__new__(HelmetDetector)
        detector.model = Model()
        detector.confidence = 0.35
        detector.positive_names = {"helmet", "with_helmet"}

        frame = FrameEvent("cam", 1, 1000.0, np.zeros((100, 120, 3), dtype=np.uint8))
        facts = list(detector.detect(frame, BoundingBox(20, 30, 60, 80)))
        self.assertEqual(calls, [(50, 40, 3)])
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0].bounding_box.x1, facts[0].bounding_box.y1), (22, 33))

    def test_violation_event_persists_plate_identity(self):
        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(f"{td}/traffic.db")
            db.save_camera("cam")
            db.save_track_stub("track-1", "cam")
            event = ViolationEvent(
                "evt-1", "track-1", "cam", "NO_SEATBELT_VIOLATION", 0.9, 0.9,
                "confirmed", 1000.0, plate_text="GJ01AB1234", plate_confidence=0.95, plate_is_full=True
            )
            db.save_violation_event(event)
            stored = db.get_violation("evt-1")
            self.assertEqual(stored["plate_text"], "GJ01AB1234")
            self.assertAlmostEqual(stored["plate_confidence"], 0.95)
            self.assertTrue(stored["plate_is_full"])

    def test_simulated_alert_prints_recognized_plate(self):
        event = ViolationEvent(
            "evt-1", "track-1", "cam", "NO_SEATBELT_VIOLATION", 0.9, 0.9,
            "confirmed", 1000.0, plate_text="GJ01AB1234", plate_confidence=0.95, plate_is_full=True
        )
        bundle = SimpleNamespace(bundle_id="b1", metadata_json=json.dumps({"vehicle_class": "car"}), image_paths=[])
        output = io.StringIO()
        with redirect_stdout(output):
            SimulatedAlertGenerator().generate_and_log_alert(event, bundle)
        self.assertIn("GJ01AB1234", output.getvalue())
        self.assertNotIn("NOT READABLE - FALLBACK TRIGGERED", output.getvalue())


if __name__ == "__main__":
    unittest.main()

class TestLivePipelineWiring(unittest.TestCase):
    def test_live_processor_creates_violation_from_camera_frame(self):
        from evidence.generator import EvidenceGenerator
        from pipeline import live

        with tempfile.TemporaryDirectory() as td:
            db = DatabaseManager(f"{td}/traffic.db")
            db.save_camera("cam_live")

            class FakeVehicleDetector:
                def __init__(self, config): pass
                def process_frame(self, frame, classes=None):
                    fact = DetectionFact(BoundingBox(20, 20, 80, 80), 2, "car", 0.95)
                    return DetectionEvent(frame.camera_id, frame.frame_id, frame.timestamp_ms, [fact])

            class FakePlatePipeline:
                def __init__(self): pass
                def process(self, frame, vehicle_box=None, track_key=None):
                    detection = PlateDetectionFact(BoundingBox(40, 60, 70, 70), 0.95)
                    ocr = OcrFact("GJ01AB1234", 0.95, True)
                    return {"detection": detection, "ocr": ocr, "voted": ocr, "crop": np.zeros((10, 20, 3), dtype=np.uint8)}

            class FakeSeatbelt:
                def __init__(self): pass
                def detect(self, frame, vehicle_box):
                    from attribute_pipeline.seatbelt import SeatbeltFact
                    yield SeatbeltFact(vehicle_box, False, 0.95, False)

            class FakeHelmet:
                def __init__(self): pass
                def detect(self, frame, vehicle_box):
                    return iter(())

            with patch.object(live, "VehicleDetector", FakeVehicleDetector), \
                 patch.object(live, "PlatePipeline", FakePlatePipeline), \
                 patch.object(live, "SeatbeltDetector", FakeSeatbelt), \
                 patch.object(live, "HelmetDetector", FakeHelmet):
                processor = live.LiveCameraProcessor("cam_live", db)
                processor.evidence_generator = EvidenceGenerator(td)
                frame = FrameEvent("cam_live", 1, 1000.0, np.zeros((100, 100, 3), dtype=np.uint8))

                events = []
                for idx in range(1, 6):
                    frame = FrameEvent("cam_live", idx, float(idx) * 1000.0, frame.image)
                    events.extend(processor.process(frame))

                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].violation_type, "NO_SEATBELT_VIOLATION")
                self.assertEqual(events[0].plate_text, "GJ01AB1234")
                stored = db.get_violation(events[0].event_id)
                self.assertEqual(stored["plate_text"], "GJ01AB1234")
                self.assertTrue(stored["evidence_bundle_ref"])


if __name__ == "__main__":
    unittest.main()


def test_auth_duplicate_keys_fail():
    import pytest
    from types import SimpleNamespace
    from api.server import _build_auth
    cfg = SimpleNamespace(api_key="same", admin_api_key="same", reviewer_api_key="", investigator_api_key="", auditor_api_key="")
    with pytest.raises(RuntimeError):
        _build_auth(cfg)

def test_review_escalated_can_return_to_decision():
    from review.service import validate_transition
    assert validate_transition("escalated", "approved")
    assert validate_transition("escalated", "rejected")

def test_rule_engine_always_requires_review():
    from rule_engine.engine import RuleEngine
    import tempfile, json, os
    fd,path=tempfile.mkstemp(suffix=".json"); os.close(fd)
    try:
        with open(path,"w") as f: json.dump({"rules":[{"violation_type":"X","conditions":[{"fact":"ok","op":"==","value":True}]}]},f)
        event=RuleEngine(path).evaluate("1","cam",{"ok":True},{"detection":1.0})[0]
        assert event.status == "needs_review"
    finally: os.remove(path)
