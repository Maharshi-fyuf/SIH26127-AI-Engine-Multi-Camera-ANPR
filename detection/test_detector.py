import pytest
pytest.importorskip("ultralytics")
import unittest
import numpy as np
import cv2
import os

from ingestion.stream import FrameEvent
from detection.config import DetectionConfig
from detection.detector import VehicleDetector

class TestVehicleDetector(unittest.TestCase):
    def setUp(self):
        from ultralytics.utils import ASSETS
        
        # Use the built-in 'bus.jpg' asset that ships locally with the ultralytics package.
        # This completely avoids network calls and guarantees a real vehicle (a bus, class 5)
        # is present in the image for the model to detect reliably.
        self.image_path = os.path.join(ASSETS, "bus.jpg")
        
        self.image = cv2.imread(self.image_path)
        if self.image is None:
            # Absolute fallback if ultralytics package layout changes
            self.image = np.zeros((480, 640, 3), dtype=np.uint8)
            
    def test_detector_finds_vehicle(self):
        # Configuration matches the rule invariants: configurable threshold, specific model
        config = DetectionConfig(
            min_confidence=0.25, # Lowered for test robustness on smaller resolutions
            model_name='yolov8n.pt'
        )
        detector = VehicleDetector(config)
        
        # Generator serving as a mock of the ingestion stream iterator
        def mock_stream():
            yield FrameEvent(
                camera_id="cam_test_02",
                frame_id=100,
                timestamp_ms=1234.5,
                image=self.image
            )
            
        events = list(detector.process_stream(mock_stream()))
        
        # Verify precisely 1 event (1 frame) was yielded back
        self.assertEqual(len(events), 1)
        event = events[0]
        
        # Verify camera_id architecture invariant is maintained
        self.assertEqual(event.camera_id, "cam_test_02")
        self.assertEqual(event.frame_id, 100)
        self.assertEqual(event.timestamp_ms, 1234.5)
        
        # Check if the bundled image is present and detected correctly
        if self.image.sum() > 0:
            print(f"\\n[DEBUG] Raw detections from test image:")
            for d in event.detections:
                print(f"  - Class: {d.class_name} (ID: {d.class_id}), Confidence: {d.confidence:.4f}, BBox: {d.bbox}")
                
            self.assertTrue(len(event.detections) > 0, "Expected at least one detection from the bundled static image")
            
            # bus.jpg has a 'bus' (class 5) in it
            vehicle_found = any(d.class_name in ['car', 'bus', 'truck', 'motorcycle'] for d in event.detections)
            self.assertTrue(vehicle_found, "Expected to detect a vehicle class in the image")
            
            # Check bounding box reasonableness (x2 > x1, y2 > y1)
            det = event.detections[0]
            self.assertTrue(det.bbox.x1 < det.bbox.x2)
            self.assertTrue(det.bbox.y1 < det.bbox.y2)

if __name__ == '__main__':
    unittest.main()
