import cv2
import numpy as np
from detection.detector import BoundingBox

class StopLineDetector:
    def __init__(self, polygon_points: list):
        """
        Initializes the geometry detector.
        :param polygon_points: List of (x, y) tuples representing the stop line or intersection area.
        """
        self.polygon = np.array(polygon_points, np.int32)

    def has_crossed(self, bbox: BoundingBox) -> bool:
        """
        Checks if the bottom-center of the vehicle's bounding box is inside the polygon.
        """
        # Calculate bottom-center coordinate of the vehicle (where the wheels touch the road)
        bottom_center_x = (bbox.x1 + bbox.x2) / 2.0
        bottom_center_y = bbox.y2
        
        point = (float(bottom_center_x), float(bottom_center_y))
        
        # cv2.pointPolygonTest returns >0 if inside, 0 if on edge, <0 if outside
        dist = cv2.pointPolygonTest(self.polygon, point, measureDist=False)
        return dist >= 0
