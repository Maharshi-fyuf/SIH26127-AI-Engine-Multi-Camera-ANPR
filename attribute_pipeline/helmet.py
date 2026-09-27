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
        # Scope inference to the target vehicle. Running on the whole frame can
        # incorrectly assign another rider's helmet state to this track.
        image=frame_event.image
        h,w=image.shape[:2]
        vx1=max(0,min(w-1,int(vehicle_box.x1))); vy1=max(0,min(h-1,int(vehicle_box.y1)))
        vx2=max(vx1+1,min(w,int(vehicle_box.x2))); vy2=max(vy1+1,min(h,int(vehicle_box.y2)))
        crop=image[vy1:vy2,vx1:vx2]
        if crop.size==0: return
        results=self.model(crop, conf=self.confidence, verbose=False)
        best=None
        for result in results:
            if result.boxes is None: continue
            names=result.names
            for box in result.boxes:
                name=str(names.get(int(box.cls[0]), '')).lower().strip().replace(' ','_')
                c=float(box.conf[0])
                if name not in self.positive_names and name not in {'no_helmet','without_helmet'}: continue
                rx1,ry1,rx2,ry2=map(float,box.xyxy[0].tolist())
                candidate=HelmetFact(BoundingBox(rx1+vx1,ry1+vy1,rx2+vx1,ry2+vy1), name in self.positive_names, c, False)
                if best is None or c>best.confidence: best=candidate
        if best is not None: yield best

