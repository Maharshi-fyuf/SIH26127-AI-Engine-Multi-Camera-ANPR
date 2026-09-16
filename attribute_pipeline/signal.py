import cv2
import numpy as np
from typing import Iterator
from ingestion.stream import FrameEvent
from detection.detector import BoundingBox
from attribute_pipeline.models import SignalStateFact

class SignalStateDetector:
    def __init__(self):
        """
        Signal State classification engine.
        Uses HSV color thresholding on a specified Region of Interest (ROI) 
        to determine traffic light state (RED/GREEN).
        """
        pass

    def extract_state(self, frame_event: FrameEvent, manual_bbox: BoundingBox) -> Iterator[SignalStateFact]:
        """
        Runs REAL pixel extraction and HSV thresholding on the given bounding box.
        The localization (bounding box) is supplied manually as an honest placeholder, 
        but the state classification logic processes the actual image pixels.
        """
        x1, y1, x2, y2 = manual_bbox.x1, manual_bbox.y1, manual_bbox.x2, manual_bbox.y2
        
        # Validate coordinates against image boundaries
        img = frame_event.image
        h, w = img.shape[:2]
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        
        if x2 <= x1 or y2 <= y1:
            yield SignalStateFact(
                bounding_box=manual_bbox,
                state="UNKNOWN",
                confidence=0.0,
                is_placeholder=False
            )
            return

        roi = img[y1:y2, x1:x2]
        
        # Convert ROI to HSV
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # Define HSV range for RED (Red wraps around 0/180)
        lower_red_1 = np.array([0, 70, 50])
        upper_red_1 = np.array([10, 255, 255])
        lower_red_2 = np.array([170, 70, 50])
        upper_red_2 = np.array([180, 255, 255])
        
        # Define HSV range for GREEN
        lower_green = np.array([40, 70, 50])
        upper_green = np.array([90, 255, 255])
        
        # Threshold the HSV image
        mask_red_1 = cv2.inRange(hsv_roi, lower_red_1, upper_red_1)
        mask_red_2 = cv2.inRange(hsv_roi, lower_red_2, upper_red_2)
        mask_red = cv2.bitwise_or(mask_red_1, mask_red_2)
        
        mask_green = cv2.inRange(hsv_roi, lower_green, upper_green)
        
        # Count non-zero pixels
        red_pixels = cv2.countNonZero(mask_red)
        green_pixels = cv2.countNonZero(mask_green)
        
        # Decide state based on pixel count
        state = "UNKNOWN"
        confidence = 0.5
        
        if red_pixels > green_pixels and red_pixels > 10:
            state = "RED"
            confidence = min(0.99, 0.5 + (red_pixels / (roi.shape[0]*roi.shape[1])))
        elif green_pixels > red_pixels and green_pixels > 10:
            state = "GREEN"
            confidence = min(0.99, 0.5 + (green_pixels / (roi.shape[0]*roi.shape[1])))

        yield SignalStateFact(
            bounding_box=manual_bbox,
            state=state,
            confidence=confidence,
            is_placeholder=False
        )
