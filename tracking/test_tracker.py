import unittest
from typing import Iterator

from detection.detector import DetectionEvent, DetectionFact, BoundingBox
from tracking.config import TrackingConfig
from tracking.tracker import ObjectTracker

class TestObjectTracker(unittest.TestCase):
    def test_tracker_assigns_consistent_ids(self):
        # We'll set initialization delay to 0 so it tracks immediately on frame 1 for this test
        config = TrackingConfig(
            max_distance_threshold=30.0,
            initialization_delay=0,
            hit_counter_max=5
        )
        tracker = ObjectTracker(config)
        
        # Synthetic sequence: 
        # Frame 1: Car A at (10, 10, 20, 20) -> centroid (15,15)
        # Frame 2: Car A slightly shifted at (12, 12, 22, 22) -> centroid (17,17) -> distance 2.8 < 30 (match)
        # Frame 3: Car A disappears. Car B appears at (100, 100, 110, 110) -> centroid (105,105) -> distance 124 > 30 (no match, new ID)
        
        def mock_stream() -> Iterator[DetectionEvent]:
            # Frame 1
            yield DetectionEvent(
                camera_id="cam_test_03", frame_id=1, timestamp_ms=100.0,
                detections=[DetectionFact(BoundingBox(10, 10, 20, 20), 2, "car", 0.9)]
            )
            # Frame 2
            yield DetectionEvent(
                camera_id="cam_test_03", frame_id=2, timestamp_ms=200.0,
                detections=[DetectionFact(BoundingBox(12, 12, 22, 22), 2, "car", 0.9)]
            )
            # Frame 3
            yield DetectionEvent(
                camera_id="cam_test_03", frame_id=3, timestamp_ms=300.0,
                detections=[DetectionFact(BoundingBox(100, 100, 110, 110), 2, "car", 0.9)]
            )
            
        events = list(tracker.process_stream(mock_stream()))
        
        print("\n[DEBUG] Tracked Objects Across Frames:")
        for e in events:
            for td in e.tracked_detections:
                print(f"  - Frame {e.frame_id}: track_id = {td.track_id}, class = {td.raw_fact.class_name}")
        
        # Ensure 3 frames were yielded back
        self.assertEqual(len(events), 3)
        
        # Frame 1 assertions
        self.assertEqual(events[0].camera_id, "cam_test_03")  # Architecture invariant
        self.assertEqual(len(events[0].tracked_detections), 1)
        track_id_1 = events[0].tracked_detections[0].track_id
        
        # Frame 2 assertions
        self.assertEqual(len(events[1].tracked_detections), 1)
        track_id_2 = events[1].tracked_detections[0].track_id
        
        # Assert same object gets same track_id across frames
        self.assertEqual(track_id_1, track_id_2)
        
        # Frame 3 assertions
        track_id_3 = events[2].tracked_detections[0].track_id
        
        # Assert disjoint object gets a DIFFERENT track_id
        self.assertNotEqual(track_id_1, track_id_3)
        
    def test_tracker_initialization_delay(self):
        config = TrackingConfig(max_distance_threshold=30.0, initialization_delay=2)
        tracker = ObjectTracker(config)
        
        def mock_stream():
            # Frame 1
            yield DetectionEvent(camera_id="cam_1", frame_id=1, timestamp_ms=0.0, detections=[
                DetectionFact(BoundingBox(10, 10, 20, 20), 0, "car", 0.9)
            ])
            # Frame 2
            yield DetectionEvent(camera_id="cam_1", frame_id=2, timestamp_ms=33.3, detections=[
                DetectionFact(BoundingBox(12, 12, 22, 22), 0, "car", 0.9)
            ])
            # Frame 3
            yield DetectionEvent(camera_id="cam_1", frame_id=3, timestamp_ms=66.6, detections=[
                DetectionFact(BoundingBox(14, 14, 24, 24), 0, "car", 0.9)
            ])
            
        events = list(tracker.process_stream(mock_stream()))
        self.assertEqual(len(events), 3)
        
        # Frame 1: age=0, hits=1. Needs hits > delay (2). Suppressed.
        self.assertEqual(len(events[0].tracked_detections), 0)
        # Frame 2: age=1, hits=2. Needs hits > 2. Suppressed.
        self.assertEqual(len(events[1].tracked_detections), 0)
        # Frame 3: age=2, hits=3. 3 > 2. EMITTED!
        self.assertEqual(len(events[2].tracked_detections), 1)
        self.assertIsNotNone(events[2].tracked_detections[0].track_id)
        
    def test_tracker_stationary_vehicle_is_not_ghosted(self):
        config = TrackingConfig(max_distance_threshold=30.0, initialization_delay=0)
        tracker = ObjectTracker(config)
        
        def mock_stream():
            # Frame 1
            yield DetectionEvent(camera_id="cam_1", frame_id=1, timestamp_ms=0.0, detections=[
                DetectionFact(BoundingBox(10, 10, 20, 20), 0, "car", 0.9)
            ])
            # Frame 2 (EXACT same bounding box - simulating stationary vehicle at red light)
            yield DetectionEvent(camera_id="cam_1", frame_id=2, timestamp_ms=33.3, detections=[
                DetectionFact(BoundingBox(10, 10, 20, 20), 0, "car", 0.9)
            ])
            
        events = list(tracker.process_stream(mock_stream()))
        self.assertEqual(len(events), 2)
        
        # Frame 1: emitted immediately (delay=0)
        self.assertEqual(len(events[0].tracked_detections), 1)
        track_id_1 = events[0].tracked_detections[0].track_id
        
        # Frame 2: Must NOT be suppressed as a ghost despite identical values
        self.assertEqual(len(events[1].tracked_detections), 1)
        track_id_2 = events[1].tracked_detections[0].track_id
        
        # Assert it's the exact same object
        self.assertEqual(track_id_1, track_id_2)

if __name__ == '__main__':
    unittest.main()
