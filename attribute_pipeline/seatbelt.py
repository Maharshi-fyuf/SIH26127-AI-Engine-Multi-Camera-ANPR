from dataclasses import dataclass
from typing import Optional, Iterator
import numpy as np
from detection.detector import BoundingBox
from ingestion.stream import FrameEvent
from config.model_registry import resolve

@dataclass
class SeatbeltFact:
    vehicle_box: BoundingBox
    seatbelt_fastened: bool
    confidence: float
    is_placeholder: bool=False

class SeatbeltDetector:
    """Seatbelt classifier operating on the upper/driver region of a vehicle."""
    def __init__(self, model_path: Optional[str]=None, confidence: float=.55):
        if model_path is None:
            try:
                from config.settings import settings
                model_path=settings.seatbelt_model
            except Exception:
                model_path='models/seatbelt_detector.pt'
        auto=False
        try:
            from config.settings import settings
            auto=settings.auto_download_models
        except Exception:
            pass
        model_path=resolve("seatbelt", model_path, auto) if model_path else None
        self.model=None; self.confidence=confidence
        if model_path:
            try:
                from ultralytics import YOLO
                self.model=YOLO(model_path)
            except Exception:
                self.model=None

    @staticmethod
    def _crop_driver_region(image, box):
        h,w=image.shape[:2]
        x1=max(0,int(box.x1)); x2=min(w,int(box.x2)); y1=max(0,int(box.y1)); y2=min(h,int(box.y2))
        if x2<=x1 or y2<=y1: return None
        # Windshield/driver area is normally in the upper ~65% of the car ROI.
        return image[y1:y1+max(1,int((y2-y1)*0.65)),x1:x2]

    def detect(self, frame: FrameEvent, vehicle_box: BoundingBox) -> Iterator[SeatbeltFact]:
        if self.model is None: return
        crop=self._crop_driver_region(frame.image,vehicle_box)
        if crop is None or crop.size==0: return
        results=self.model.predict(crop,verbose=False)
        for result in results:
            probs=getattr(result,"probs",None)
            if probs is None: continue
            top=int(probs.top1); conf=float(probs.top1conf)
            name=str(result.names.get(top,"")).lower().replace("-","_").replace(" ","_")
            if conf < self.confidence: continue
            if name in {"seat_belt","seatbelt","fastened","with_seatbelt"}:
                yield SeatbeltFact(vehicle_box,True,conf,False); return
            if name in {"no_seatbelt","noseatbelt","unfastened","without_seatbelt","no_belt"}:
                yield SeatbeltFact(vehicle_box,False,conf,False); return
        return

    def placeholder_state(self, frame, vehicle_box, synthetic_fastened=True, synthetic_confidence=0.8):
        """TEST-ONLY compatibility helper."""
        return SeatbeltFact(vehicle_box, synthetic_fastened, synthetic_confidence, True)
