import json
from rule_engine.models import ViolationEvent
from evidence.models import EvidenceBundle

class SimulatedAlertGenerator:
    def generate_and_log_alert(self, event: ViolationEvent, bundle: EvidenceBundle):
        """
        Simulates generating an alert/challan for a confirmed violation event.
        Must prominently feature a "SIMULATED" label per TRD restrictions.
        """
        metadata = json.loads(bundle.metadata_json)
        vehicle_class = metadata.get("vehicle_class", "unknown")
        
        print("\n" + "="*60)
        print("                 SIMULATED TRAFFIC ALERT")
        print("           (DO NOT USE FOR OFFICIAL ENFORCEMENT)")
        print("="*60)
        print(f" Violation Type   : {event.violation_type} [{event.status.upper()}]")
        print(f" Timestamp (ms)   : {event.timestamp_ms}")
        print(f" Camera ID        : {event.camera_id}")
        print(f" Confidence       : {(event.aggregated_confidence * 100):.1f}%")
        print("-" * 60)
        print(" [ VEHICLE INFORMATION ]")
        print(" Plate Number     : NOT READABLE - FALLBACK TRIGGERED")
        print(f" Vehicle Class    : {vehicle_class.upper()}")
        print("-" * 60)
        print(" [ EVIDENCE ARTIFACTS ]")
        print(f" Bundle Reference : {bundle.bundle_id}")
        for path in bundle.image_paths:
            print(f" Attached Image   : {path}")
        print("="*60 + "\n")
