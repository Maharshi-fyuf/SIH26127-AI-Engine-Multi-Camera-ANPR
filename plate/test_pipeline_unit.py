from plate.pipeline import PlatePipeline
from detection.detector import BoundingBox

def test_overlap():
    a=BoundingBox(10,10,50,50); b=BoundingBox(20,20,40,40)
    assert PlatePipeline._overlap(a,b)==1.0

def test_overlap_zero():
    assert PlatePipeline._overlap(BoundingBox(0,0,10,10),BoundingBox(20,20,30,30))==0.0
