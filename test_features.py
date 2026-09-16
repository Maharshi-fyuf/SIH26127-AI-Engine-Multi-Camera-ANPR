from attribute_pipeline.emergency import classify_emergency
from governance.privacy import blur_regions
from detection.detector import BoundingBox
import numpy as np

def test_emergency_requires_confidence():
    assert classify_emergency('ambulance',.9).priority=='HIGH'
    assert classify_emergency('ambulance',.4).priority=='NORMAL'

def test_privacy_blur():
    img=np.ones((50,50,3),dtype=np.uint8)*255
    out=blur_regions(img,[BoundingBox(10,10,30,30)])
    assert out.shape==img.shape
