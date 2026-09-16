from dataclasses import dataclass
from typing import Iterable, List

from detection.detector import BoundingBox, DetectionFact


@dataclass
class RiderCountFact:
    vehicle_box: BoundingBox
    rider_count: int
    confidence: float


def count_riders_on_vehicle(vehicle_box: BoundingBox, person_detections: Iterable[DetectionFact]) -> RiderCountFact:
    riders: List[DetectionFact] = []
    for detection in person_detections:
        if detection.class_name != "person":
            continue
        center_x = (detection.bbox.x1 + detection.bbox.x2) / 2.0
        feet_y = detection.bbox.y2
        inside_x = vehicle_box.x1 <= center_x <= vehicle_box.x2
        near_vehicle = vehicle_box.y1 - 80 <= feet_y <= vehicle_box.y2 + 40
        if inside_x and near_vehicle:
            riders.append(detection)

    confidence = min([rider.confidence for rider in riders], default=0.0)
    return RiderCountFact(vehicle_box=vehicle_box, rider_count=len(riders), confidence=confidence)
