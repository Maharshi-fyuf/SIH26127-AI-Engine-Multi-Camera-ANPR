import unittest
import cv2
import numpy as np
import os
import tempfile
from ingestion.stream import VideoStream, CameraConfig

class TestVideoStream(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the test video
        self.temp_dir = tempfile.TemporaryDirectory()
        self.video_path = os.path.join(self.temp_dir.name, "test_video.avi")
        
        # Synthetic video properties
        self.source_fps = 30
        self.duration_sec = 3
        self.total_frames = self.source_fps * self.duration_sec
        
        # Generate a 3-second 30fps dummy video
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(self.video_path, fourcc, self.source_fps, (640, 480))
        
        for i in range(self.total_frames):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (i % 255, 100, 100) # Changing color
            out.write(frame)
            
        out.release()
        
    def tearDown(self):
        self.temp_dir.cleanup()
        
    def test_downsampling_to_15fps(self):
        """Test that a 30fps video is correctly downsampled to 15fps and emits camera_id"""
        config = CameraConfig(
            camera_id="cam_test_01",
            source_url=self.video_path,
            target_fps=15.0
        )
        stream = VideoStream(config)
        
        frames = []
        for frame_event in stream.generate_frames():
            frames.append(frame_event)
            
            # Assert architecture invariant: camera_id is attached to every event emitted
            self.assertEqual(frame_event.camera_id, "cam_test_01")
            
            # Assert frame validity
            self.assertIsNotNone(frame_event.image)
            self.assertEqual(frame_event.image.shape, (480, 640, 3))
            
        stream.close()
        
        # Expected frames at 15fps for 3 seconds is 45
        self.assertEqual(len(frames), 45)
        # Ensure frame_ids are incrementing properly (0 to 44)
        self.assertEqual(frames[-1].frame_id, 44)

if __name__ == '__main__':
    unittest.main()
