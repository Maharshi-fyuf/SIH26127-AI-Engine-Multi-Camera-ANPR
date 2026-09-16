from dataclasses import dataclass

@dataclass
class DetectionConfig:
    """
    Configuration for the vehicle detection module.
    Confidence and IoU thresholds are explicitly configured here,
    not hardcoded in the logic pipeline (Architecture Invariant).
    """
    min_confidence: float = 0.25
    iou_threshold: float = 0.45
    model_name: str = 'yolov8s.pt'
    # COCO classes for vehicles: 2=car, 3=motorcycle, 5=bus, 7=truck
    target_classes: tuple = (2, 3, 5, 7)
