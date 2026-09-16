"""Emergency vehicle recognition/priority intelligence. This is contextual routing, not violation immunity."""
from dataclasses import dataclass

@dataclass
class EmergencyVehicleFact:
    vehicle_type: str
    confidence: float
    priority: str
    requires_operator_confirmation: bool = True

EMERGENCY_LABELS={"ambulance":"ambulance","fire_truck":"fire_truck","fire engine":"fire_truck","police":"police","police_car":"police"}

def classify_emergency(label:str, confidence:float, threshold:float=.70)->EmergencyVehicleFact:
    kind=EMERGENCY_LABELS.get(label.lower().strip())
    if kind and confidence>=threshold:
        return EmergencyVehicleFact(kind,confidence,"HIGH",True)
    return EmergencyVehicleFact("none",confidence,"NORMAL",True)
