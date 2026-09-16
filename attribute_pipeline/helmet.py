"""YOLO-backed helmet detector. No synthetic facts are emitted in production mode."""
from __future__ import annotations
from typing import Iterator, Optional
from ingestion.stream import FrameEvent
from detection.detector import BoundingBox
from attribute_pipeline.models import HelmetFact
from config.model_registry import resolve

class HelmetDetector:
    def __init__(self, model_path: Optional[str]=None, confidence: float=.35, positive_names=('helmet','with_helmet')):
        if model_path is None:
            try:
                from config.settings import settings
                model_path=settings.helmet_model
            except Exception:
                model_path='models/helmet_detector.pt'
        auto=False
        try:
            from config.settings import settings
            auto=settings.auto_download_models
        except Exception:
            pass
        model_path=resolve("helmet", model_path, auto) if model_path else None
        self.model_path=model_path; self.confidence=confidence; self.positive_names=set(positive_names); self.model=None
        if model_path:
            try:
                from ultralytics import YOLO
                self.model=YOLO(model_path)
            except Exception:
                self.model=None

    def detect(self, frame_event: FrameEvent, vehicle_box: BoundingBox) -> Iterator[HelmetFact]:
        if self.model is None: return
        results=self.model(frame_event.image, conf=self.confidence, verbose=False)
        best=None
        for result in results:
            if result.boxes is None: continue
            names=result.names
            for box in result.boxes:
                name=str(names.get(int(box.cls[0]), '')).lower(); c=float(box.conf[0])
                if name not in self.positive_names and name not in {'no_helmet','without_helmet'}: continue
                x1,y1,x2,y2=map(float,box.xyxy[0].tolist())
                candidate=HelmetFact(BoundingBox(x1,y1,x2,y2), name in self.positive_names, c, False)
                if best is None or c>best.confidence: best=candidate
        if best is not None: yield best

    def _placeholder_helmet_state(self, frame_event, manual_bbox, synthetic_has_helmet=False, synthetic_confidence=0.75):
        """TEST-ONLY compatibility helper for deterministic pipeline tests."""
        yield HelmetFact(manual_bbox, synthetic_has_helmet, synthetic_confidence, True)
