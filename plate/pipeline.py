"""End-to-end plate localization -> preprocessing -> OCR -> temporal voting."""
from __future__ import annotations
from collections import defaultdict
import cv2
from ingestion.stream import FrameEvent
from detection.detector import BoundingBox
from plate.detector import PlateDetector
from plate.ocr import PlateOcr, TemporalPlateReader

class PlatePipeline:
    def __init__(self, detector=None, ocr=None, min_votes=3):
        self.detector=detector or PlateDetector()
        self.ocr=ocr or PlateOcr()
        self.readers=defaultdict(lambda: TemporalPlateReader(min_votes=min_votes))

    @staticmethod
    def _crop(frame,bbox):
        h,w=frame.shape[:2]
        x1=max(0,min(w-1,int(bbox.x1))); y1=max(0,min(h-1,int(bbox.y1)))
        x2=max(x1+1,min(w,int(bbox.x2))); y2=max(y1+1,min(h,int(bbox.y2)))
        crop=frame[y1:y2,x1:x2]
        if crop.size==0:return crop
        # Mild preprocessing preserves glyph edges while improving low-contrast plates.
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        gray=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(gray)
        return cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _overlap(a,b):
        ix1=max(a.x1,b.x1); iy1=max(a.y1,b.y1); ix2=min(a.x2,b.x2); iy2=min(a.y2,b.y2)
        if ix2<=ix1 or iy2<=iy1:return 0.0
        inter=(ix2-ix1)*(iy2-iy1); area=max(1,(b.x2-b.x1)*(b.y2-b.y1))
        return inter/area

    def process(self,event:FrameEvent,vehicle_box:BoundingBox|None=None,track_key:str|None=None):
        candidates=list(self.detector.detect(event))
        if vehicle_box is not None:
            candidates=[d for d in candidates if self._overlap(d.bounding_box,vehicle_box)>0.02] or candidates
        if not candidates:return None
        detection=max(candidates,key=lambda d:d.confidence)
        crop=self._crop(event.image,detection.bounding_box)
        fact=self.ocr.read_text(crop)
        if fact is None:return None
        key=track_key or f"{event.camera_id}:frame"
        voted=self.readers[key].add(fact)
        return {"detection":detection,"ocr":fact,"voted":voted,"crop":crop}
