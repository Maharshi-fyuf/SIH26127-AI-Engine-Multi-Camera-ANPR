from __future__ import annotations
import logging
import re
from collections import Counter
from typing import Optional
import numpy as np
from plate.models import OcrFact
from plate.validator import normalize_indian_plate, is_valid_indian_plate, repair_indian_plate
logging.getLogger("ppocr").setLevel(logging.ERROR)

class PlateOcr:
    def __init__(self):
        self.ocr=None
        self.backend="paddleocr"
        try:
            from paddleocr import PaddleOCR
            self.ocr=PaddleOCR(use_angle_cls=False,lang='en',show_log=False)
        except ImportError:
            self.backend="tesseract"
            try:
                import pytesseract
                self._tesseract=pytesseract
            except ImportError as exc:
                raise RuntimeError("Install PaddleOCR (preferred) or pytesseract+tesseract-ocr for plate OCR.") from exc
    def read_text(self,cropped_image: np.ndarray) -> Optional[OcrFact]:
        if cropped_image is None or cropped_image.size==0: return None
        if self.ocr is not None:
            results=self.ocr.ocr(cropped_image,cls=False)
            if not results or not results[0]: return None
            parts=[]; confs=[]
            for line in results[0]:
                text=line[1][0]; conf=float(line[1][1]); parts.append(text); confs.append(conf)
            text=repair_indian_plate(''.join(parts))
            return OcrFact(text,min(confs) if confs else 0.0,is_valid_indian_plate(text))
        # Lightweight offline fallback for environments where PaddleOCR is unavailable.
        import cv2
        import pytesseract
        gray=cv2.cvtColor(cropped_image,cv2.COLOR_BGR2GRAY)
        gray=cv2.resize(gray,None,fx=3.0,fy=3.0,interpolation=cv2.INTER_CUBIC)
        best=None
        for psm in (8,13,7):
            _,th=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
            raw=pytesseract.image_to_string(th,config=f'--psm {psm} -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789').strip()
            if not raw: continue
            text=repair_indian_plate(raw)
            valid=is_valid_indian_plate(text)
            data=pytesseract.image_to_data(th,config=f'--psm {psm} -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',output_type=pytesseract.Output.DICT)
            vals=[]
            for c in data.get('conf',[]):
                try:
                    v=float(c)/100.0
                    if v>0: vals.append(v)
                except ValueError: pass
            conf=sum(vals)/len(vals) if vals else 0.0
            candidate=OcrFact(text,conf,valid)
            if best is None or (candidate.is_format_valid, candidate.confidence)>(best.is_format_valid,best.confidence): best=candidate
            if valid: return candidate
        return best


class TemporalPlateReader:
    """Multi-frame voting; only emits a full identity when consistency is sufficient."""
    def __init__(self,min_votes:int=3,min_confidence:float=.55): self.min_votes=min_votes; self.min_confidence=min_confidence; self._reads=[]
    def add(self,fact:Optional[OcrFact]):
        if fact and fact.text and fact.confidence>=self.min_confidence: self._reads.append(fact)
        if len(self._reads)<self.min_votes: return None
        groups={}
        for f in self._reads:
            groups.setdefault(f.text,[]).append(f)
        text,items=max(groups.items(),key=lambda kv:(len(kv[1]),sum(x.confidence for x in kv[1])))
        consistency=len(items)/len(self._reads)
        conf=sum(x.confidence for x in items)/len(items)*consistency
        return OcrFact(text,conf,is_valid_indian_plate(text))
