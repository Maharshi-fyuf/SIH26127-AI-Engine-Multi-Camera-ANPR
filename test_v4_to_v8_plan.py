import os
import sqlite3
import tempfile
import time
import unittest

import numpy as np

from alert.intelligence import AlertRouter, BlacklistMatcher, repeat_offender_plates
from analytics.spatial import CameraLocation, build_trajectory, origin_destination_report, violation_heatmap
from api.dashboard import ControlRoomDashboard
from db.manager import DatabaseManager
from db.postgres_migration import MigrationCheck, migration_report
from event_bus.bus import InMemoryEventBus
from governance.audit import RuleMetrics, render_accuracy_audit_report
from governance.retention import RetentionManager
from ingestion.multi_camera import MultiCameraRunner
from ingestion.stream import CameraConfig, FrameEvent
from plate.intelligence import evaluate_plate_read
from plate.models import OcrFact
from rule_engine.engine import RuleEngine
from rule_engine.models import ViolationEvent
from attribute_pipeline.seatbelt import SeatbeltDetector
from attribute_pipeline.triple_riding import count_riders_on_vehicle
from detection.detector import BoundingBox, DetectionFact
from tracking.reid import CameraLink, TrajectoryStitcher, VehicleEmbedding


MATCHING_FACTS = {
    "vehicle_class": "motorcycle",
    "crossed_stop_line": True,
    "signal_state": "RED",
    "has_helmet": False,
    "persistence_frames": 5,
}
HIGH_CONFIDENCE = {"track": 0.95, "detection": 0.95, "signal": 0.95, "helmet": 0.95}


class TestV4ToV8Plan(unittest.TestCase):
    def make_db(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "traffic.db")
        return temp_dir, DatabaseManager(db_path)

    def test_rule_engine_deduplicates_per_camera_not_global_track_id(self):
        engine = RuleEngine("rule_engine/rules.json", confidence_threshold=0.75)

        cam_a = engine.evaluate("track_1", "cam_A", MATCHING_FACTS, HIGH_CONFIDENCE)
        cam_b = engine.evaluate("track_1", "cam_B", MATCHING_FACTS, HIGH_CONFIDENCE)
        cam_a_repeat = engine.evaluate("track_1", "cam_A", MATCHING_FACTS, HIGH_CONFIDENCE)

        self.assertEqual(len(cam_a), 2)
        self.assertEqual(len(cam_b), 2)
        self.assertEqual(len(cam_a_repeat), 0)
        self.assertEqual({event.camera_id for event in cam_b}, {"cam_B"})

    def test_database_and_dashboard_keep_camera_attribution_clean(self):
        temp_dir, db = self.make_db()
        self.addCleanup(temp_dir.cleanup)

        for camera_id in ("cam_A", "cam_B"):
            db.save_camera(camera_id)
            db.save_track_stub("track_1", camera_id)
            db.save_violation_event(
                ViolationEvent(
                    event_id=f"evt_{camera_id}",
                    track_id="track_1",
                    camera_id=camera_id,
                    violation_type="RED_LIGHT_VIOLATION",
                    rule_confidence=0.7,
                    aggregated_confidence=0.7,
                    status="needs_review",
                    timestamp_ms=time.time() * 1000.0,
                )
            )

        with sqlite3.connect(db.db_path) as conn:
            track_count = conn.execute("SELECT COUNT(*) FROM Track WHERE track_id = 'track_1'").fetchone()[0]

        self.assertEqual(track_count, 2)
        self.assertEqual(db.get_violation_counts_by_camera()["cam_A"]["RED_LIGHT_VIOLATION"], 1)
        self.assertEqual(db.get_violation_counts_by_camera()["cam_B"]["RED_LIGHT_VIOLATION"], 1)

        dashboard = ControlRoomDashboard(db)
        html = dashboard.render_html({})
        self.assertIn("cam_A", html)
        self.assertIn("cam_B", html)
        self.assertIn("needs_review", dashboard.snapshot_json({}))

    def test_v2_v3_rule_hooks_and_calibration_storage(self):
        temp_dir, db = self.make_db()
        self.addCleanup(temp_dir.cleanup)
        db.save_camera_calibration("cam_A", {"stop_line_polygon": [[0, 250], [640, 250]]})
        self.assertEqual(db.get_camera_calibration("cam_A")["stop_line_polygon"][0], [0, 250])

        vehicle_box = BoundingBox(100, 100, 220, 220)
        riders = [
            DetectionFact(BoundingBox(105, 40, 135, 210), 0, "person", 0.9),
            DetectionFact(BoundingBox(145, 45, 175, 215), 0, "person", 0.85),
            DetectionFact(BoundingBox(180, 50, 210, 218), 0, "person", 0.8),
        ]
        rider_fact = count_riders_on_vehicle(vehicle_box, riders)
        self.assertEqual(rider_fact.rider_count, 3)

        frame = FrameEvent("cam_A", 1, 1000.0, np.zeros((240, 320, 3), dtype=np.uint8))
        seatbelt_fact = SeatbeltDetector().placeholder_state(frame, vehicle_box, synthetic_fastened=False)
        self.assertFalse(seatbelt_fact.seatbelt_fastened)

        engine = RuleEngine("rule_engine/rules.json", confidence_threshold=0.75)
        triple = engine.evaluate(
            "track_triple",
            "cam_A",
            {
                "vehicle_class": "motorcycle",
                "rider_count": 3,
                "persistence_frames": 3,
                "crossed_stop_line": False,
                "signal_state": "GREEN",
                "has_helmet": True,
            },
            {"track": 0.9, "detection": 0.9, "person": 0.8},
        )
        seatbelt = engine.evaluate(
            "track_seatbelt",
            "cam_A",
            {
                "vehicle_class": "car",
                "seatbelt_fastened": False,
                "persistence_frames": 3,
                "crossed_stop_line": False,
                "signal_state": "GREEN",
                "has_helmet": True,
            },
            {"track": 0.9, "detection": 0.9, "seatbelt": 0.8},
        )
        self.assertEqual(triple[0].violation_type, "TRIPLE_RIDING_VIOLATION")
        self.assertEqual(seatbelt[0].violation_type, "NO_SEATBELT_VIOLATION")

        report = migration_report({"Track": MigrationCheck("Track", 2, 2)})
        self.assertIn("PASS: Track", report)

    def test_multi_camera_runner_processes_two_feeds_concurrently(self):
        def stream_factory(config):
            for frame_id in range(2):
                yield FrameEvent(
                    camera_id=config.camera_id,
                    frame_id=frame_id,
                    timestamp_ms=float(frame_id),
                    image=np.zeros((10, 10, 3), dtype=np.uint8),
                )

        def processor_factory(camera_id):
            def process(frame):
                return [f"{camera_id}:{frame.frame_id}"]
            return process

        runner = MultiCameraRunner(
            [
                CameraConfig("cam_A", "simulated_A"),
                CameraConfig("cam_B", "simulated_B"),
            ],
            processor_factory=processor_factory,
            stream_factory=stream_factory,
            simulated_camera_ids=["cam_B"],
        )
        runner.start()
        runner.join(timeout=2.0)
        results = runner.drain_results()

        self.assertEqual(len(results), 4)
        self.assertEqual(runner.health_snapshot()["cam_A"].frames_processed, 2)
        self.assertTrue(runner.health_snapshot()["cam_B"].simulated)
        self.assertEqual({result.camera_id for result in results}, {"cam_A", "cam_B"})

    def test_reid_stitching_uses_geometry_and_time_window(self):
        embeddings = [
            VehicleEmbedding("emb_a", "cam_A", "track_7", 1000.0, [1.0, 0.0, 0.0]),
            VehicleEmbedding("emb_b", "cam_B", "track_3", 2500.0, [0.98, 0.02, 0.0]),
            VehicleEmbedding("emb_c", "cam_B", "track_9", 9000.0, [1.0, 0.0, 0.0]),
        ]
        stitcher = TrajectoryStitcher([CameraLink("cam_A", "cam_B", 1000.0, 3000.0)], similarity_threshold=0.95)

        matches = stitcher.match(embeddings)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].from_embedding.embedding_id, "emb_a")
        self.assertEqual(matches[0].to_embedding.embedding_id, "emb_b")

    def test_spatial_analytics_blacklist_alerting_and_event_bus(self):
        locations = {
            "cam_A": CameraLocation("cam_A", 12.9716, 77.5946),
            "cam_B": CameraLocation("cam_B", 12.9726, 77.5956),
        }
        trajectory = build_trajectory(["cam_A", "cam_B"], locations, 1000.0)
        self.assertEqual(origin_destination_report([trajectory])[("cam_A", "cam_B")], 1)
        self.assertEqual(violation_heatmap([{"latitude": 12.97161, "longitude": 77.59461}])[(12.9716, 77.5946)], 1)

        matcher = BlacklistMatcher({"KA01AB1234": {"reason": "stolen", "severity": "critical"}}, min_confidence=0.92)
        self.assertIsNone(matcher.match("KA 01 AB 1234", 0.70))
        self.assertEqual(matcher.match("KA 01 AB 1234", 0.95).severity, "critical")
        decision = evaluate_plate_read(OcrFact("KA 01 AB 1234", 0.95, True), matcher)
        self.assertEqual(decision.blacklist_match.reason, "stolen")

        router = AlertRouter({"critical": "priority_webhook", "default": "console"})
        self.assertEqual(router.route_for("BLACKLIST_MATCH", "critical"), "priority_webhook")
        self.assertEqual(repeat_offender_plates([
            {"plate_text": "KA01AB1234", "timestamp_ms": 1000.0},
            {"plate_text": "KA01AB1234", "timestamp_ms": 2000.0},
        ], min_violations=2, window_ms=5000.0), ["KA01AB1234"])

        bus = InMemoryEventBus()
        bus.publish("violations", {"camera_id": "cam_A"})
        self.assertEqual(bus.drain("violations")[0].payload["camera_id"], "cam_A")

    def test_retention_and_audit_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_path = os.path.join(temp_dir, "old_frame.jpg")
            protected_path = os.path.join(temp_dir, "evidence.jpg")
            for path in (old_path, protected_path):
                with open(path, "w", encoding="utf-8") as file:
                    file.write("frame")
                os.utime(path, (time.time() - 10 * 24 * 60 * 60, time.time() - 10 * 24 * 60 * 60))

            decisions = RetentionManager(non_violation_retention_days=7).purge_non_violation_files(
                [old_path, protected_path],
                [protected_path],
            )

            self.assertFalse(os.path.exists(old_path))
            self.assertTrue(os.path.exists(protected_path))
            self.assertEqual([decision.action for decision in decisions], ["purge", "retain"])

        report = render_accuracy_audit_report([RuleMetrics("RED_LIGHT_VIOLATION", 9, 1, 2, 1)])
        self.assertIn("Digital Personal Data Protection Act, 2023", report)
        self.assertIn("| RED_LIGHT_VIOLATION | 0.90 | 0.82 | 0.10 | 1 |", report)


if __name__ == "__main__":
    unittest.main()
