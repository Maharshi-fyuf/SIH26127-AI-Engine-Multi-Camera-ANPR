import cv2
import time
import logging
from dataclasses import dataclass
from typing import Iterator
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class CameraConfig:
    camera_id: str
    source_url: str  # '0' for local webcam, 'rtmp://...', or path to video file
    target_fps: float = 15.0

@dataclass
class FrameEvent:
    camera_id: str
    frame_id: int
    timestamp_ms: float
    image: np.ndarray

class VideoStream:
    """
    Ingests a video stream from a file, IP camera, or local webcam.
    Yields frames at a configured target FPS, acting as a decoupled generator.
    """
    def __init__(self, config: CameraConfig):
        self.config = config
        
        # If the source is a single digit (e.g., '0'), it's a local camera index.
        src = int(self.config.source_url) if str(self.config.source_url).isdigit() else self.config.source_url
        self.cap = cv2.VideoCapture(src)
        
        if not self.cap.isOpened():
            raise ValueError(f"Failed to open video source: {self.config.source_url}")
            
        self.source_fps = self.cap.get(cv2.CAP_PROP_FPS)
        # Handle cases where source FPS cannot be determined (some live streams)
        if self.source_fps <= 0 or np.isnan(self.source_fps):
            logger.warning(f"Unable to determine source FPS for {self.config.source_url}. Defaulting to 30.0")
            self.source_fps = 30.0 
            
        self.target_interval_sec = 1.0 / self.config.target_fps

    def generate_frames(self) -> Iterator[FrameEvent]:
        """
        Yields downsampled frames. 
        Does not couple to detection logic.
        """
        frame_count = 0
        emitted_count = 0
        
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
                
            current_time_sec = frame_count / self.source_fps
            next_yield_time_sec = emitted_count / self.config.target_fps
            
            # Sub-sample frames to meet target FPS
            if current_time_sec >= next_yield_time_sec - 1e-9:
                # Use the stream's presentation timestamp if valid
                timestamp_ms = self.cap.get(cv2.CAP_PROP_POS_MSEC)
                if timestamp_ms < 0:
                    # Fallback to system time for live streams without proper PTS
                    timestamp_ms = time.time() * 1000.0
                    
                yield FrameEvent(
                    camera_id=self.config.camera_id,
                    frame_id=emitted_count,
                    timestamp_ms=timestamp_ms,
                    image=frame
                )
                
                emitted_count += 1
                
            frame_count += 1
            
    def close(self):
        """Release the capture device."""
        if self.cap.isOpened():
            self.cap.release()
