import logging
from typing import Iterator, List
from dataclasses import dataclass

from ingestion.stream import FrameEvent
from detection.config import DetectionConfig

logger = logging.getLogger(__name__)

@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

@dataclass
class DetectionFact:
    """Raw perception fact. Emits NO judgement about violations."""
    bbox: BoundingBox
    class_id: int
    class_name: str
    confidence: float

@dataclass
class DetectionEvent:
    camera_id: str
    frame_id: int
    timestamp_ms: float
    detections: List[DetectionFact]

class VehicleDetector:
    def __init__(self, config: DetectionConfig):
        self.config = config
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Ultralytics is required to run VehicleDetector. Install requirements.txt.") from exc
        self.model = YOLO(self.config.model_name)
        
    def process_frame(self, frame_event: FrameEvent, classes=None) -> DetectionEvent:
        """Run one YOLO inference and return objective detections only.

        ``classes`` may widen the query for auxiliary facts such as persons.
        The tracker should receive only vehicle classes.
        """
        target_classes = tuple(classes) if classes is not None else self.config.target_classes
        results = self.model(
            frame_event.image,
            classes=list(target_classes),
            conf=self.config.min_confidence,
            iou=self.config.iou_threshold,
            verbose=False
        )
        facts = []
        if len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                for box in result.boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    coords = box.xyxy[0].tolist()
                    facts.append(DetectionFact(
                        bbox=BoundingBox(coords[0], coords[1], coords[2], coords[3]),
                        class_id=cls_id,
                        class_name=self.model.names.get(cls_id, str(cls_id)),
                        confidence=conf
                    ))
        return DetectionEvent(frame_event.camera_id, frame_event.frame_id, frame_event.timestamp_ms, facts)

    def process_stream(self, frame_iterator: Iterator[FrameEvent]) -> Iterator[DetectionEvent]:
        """Consumes raw FrameEvents and yields objective perception facts."""
        for frame_event in frame_iterator:
            yield self.process_frame(frame_event)
