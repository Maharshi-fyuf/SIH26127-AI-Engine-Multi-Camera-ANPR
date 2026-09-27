from attribute_pipeline.models import HelmetFact
from attribute_pipeline.triple_riding import RiderCountFact
from detection.detector import BoundingBox
from plate.models import PlateDetectionFact

def fake_helmet(frame_event, bbox, has_helmet=False, confidence=0.75):
    return HelmetFact(bbox, has_helmet, confidence, True)

def fake_seatbelt(vehicle_box, fastened=True, confidence=0.8):
    from attribute_pipeline.seatbelt import SeatbeltFact
    return SeatbeltFact(vehicle_box, fastened, confidence, True)

def fake_plate(frame_event, bbox, confidence=0.75):
    return PlateDetectionFact(bbox, confidence, True)
