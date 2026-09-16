"""Production-capable plate localization adapter. A specialist YOLO weight is required for real inference."""
from __future__ import annotations
from typing import Iterator, Optional
from ingestion.stream import FrameEvent
from detection.detector import BoundingBox
from plate.models import PlateDetectionFact
from config.model_registry import resolve

class PlateDetector:
    def __init__(self, model_path: Optional[str] = None, confidence: float = .35):
        if model_path is None:
            try:
                from config.settings import settings
                model_path=settings.plate_model
            except Exception:
                model_path='models/plate_detector.pt'
        auto=False
        try:
            from config.settings import settings
            auto=settings.auto_download_models
        except Exception:
            pass
        model_path=resolve("plate", model_path, auto) if model_path else None
        self.model_path=model_path
        self.confidence=confidence
        self.model=None
        if model_path:
            try:
                from ultralytics import YOLO
                self.model=YOLO(model_path)
            except Exception:
                self.model=None

    @property
    def available(self): return self.model is not None

    def detect(self, frame_event: FrameEvent) -> Iterator[PlateDetectionFact]:
        if self.model is None:
            return
        results=self.model(frame_event.image, conf=self.confidence, verbose=False)
        for result in results:
            if result.boxes is None: continue
            for box in result.boxes:
                c=float(box.conf[0]); x1,y1,x2,y2=map(float,box.xyxy[0].tolist())
                yield PlateDetectionFact(BoundingBox(x1,y1,x2,y2),c,False)

    def _placeholder_plate_region(self, frame_event, manual_bbox, synthetic_confidence=0.75):
        """TEST-ONLY compatibility helper. Never call from production inference."""
        from plate.models import PlateDetectionFact
        yield PlateDetectionFact(manual_bbox, synthetic_confidence, True)
