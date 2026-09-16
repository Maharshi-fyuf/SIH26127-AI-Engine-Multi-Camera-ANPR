"""Privacy helpers: blur bystander plates/faces before non-evidence retention."""
from __future__ import annotations
import cv2
from detection.detector import BoundingBox

def blur_regions(image, boxes, kernel=31):
    result=image.copy(); h,w=result.shape[:2]
    for box in boxes:
        x1=max(0,int(box.x1)); y1=max(0,int(box.y1)); x2=min(w,int(box.x2)); y2=min(h,int(box.y2))
        if x2<=x1 or y2<=y1: continue
        roi=result[y1:y2,x1:x2]
        if roi.size: result[y1:y2,x1:x2]=cv2.GaussianBlur(roi,(kernel|1,kernel|1),0)
    return result
