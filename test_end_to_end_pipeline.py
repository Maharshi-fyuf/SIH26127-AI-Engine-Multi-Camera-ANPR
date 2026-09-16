import cv2
import numpy as np
import time

from ingestion.stream import FrameEvent
from detection.detector import BoundingBox

from attribute_pipeline.helmet import HelmetDetector
from attribute_pipeline.signal import SignalStateDetector
from attribute_pipeline.geometry import StopLineDetector
from aggregation.aggregator import EventAggregator
from rule_engine.engine import RuleEngine

def run_pipeline():
    print("=== True End-to-End Traffic Rule Engine Pipeline ===")
    
    # Setup Detectors
    signal_detector = SignalStateDetector()
    helmet_detector = HelmetDetector()
    
    # The Stop-Line Polygon (e.g. crossing a line at Y=250)
    # Define a rectangle area for the intersection
    intersection_polygon = [(0, 250), (640, 250), (640, 480), (0, 480)]
    stop_line_detector = StopLineDetector(intersection_polygon)
    
    # Setup Aggregator & Rule Engine
    aggregator = EventAggregator()
    engine = RuleEngine(rules_path="rule_engine/rules.json", confidence_threshold=0.75)
    
    # Create 10 frames of two vehicles moving forward
    for frame_idx in range(1, 11):
        # 1. Create Frame (Red traffic light always present)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.circle(img, (150, 150), 30, (0, 0, 255), -1) # RED Light
        
        event = FrameEvent(camera_id="cam_01", frame_id=frame_idx, timestamp_ms=time.time()*1000, image=img)
        
        # 2. Extract Signal State
        traffic_light_box = BoundingBox(x1=100, y1=100, x2=200, y2=200)
        signal_facts = list(signal_detector.extract_state(event, traffic_light_box))
        signal_fact = signal_facts[0]
        
        print(f"\n[Frame {frame_idx}]")
        
        # --- TRACK A: CROSSES STOP LINE ---
        vehicle_y2_a = 100 + (frame_idx * 30)
        vehicle_box_a = BoundingBox(x1=300, y1=vehicle_y2_a - 50, x2=400, y2=vehicle_y2_a)
        has_crossed_a = stop_line_detector.has_crossed(vehicle_box_a)
        
        helmet_facts_a = list(helmet_detector._placeholder_helmet_state(event, vehicle_box_a, synthetic_has_helmet=False, synthetic_confidence=0.85))
        
        agg_facts_a, agg_conf_a = aggregator.update_track(
            track_id="track_99",
            vehicle_class="motorcycle",
            crossed_stop_line_now=has_crossed_a,
            signal_state_now=signal_fact.state,
            has_helmet_now=helmet_facts_a[0].has_helmet,
            confidences_now={"track": 0.90, "detection": 0.88, "signal": signal_fact.confidence, "helmet": helmet_facts_a[0].confidence}
        )
        
        print(f"  Track A (Crossing)    | Y={vehicle_y2_a} | Crossed={has_crossed_a} | Persistence={agg_facts_a['persistence_frames']}")
        violations_a = engine.evaluate("track_99", "cam_01", agg_facts_a, agg_conf_a)
        for v in violations_a:
            print(f"   => ALARM A! {v.violation_type} ({v.status})")
            
        # --- TRACK B: DOES NOT CROSS STOP LINE ---
        vehicle_y2_b = 50 + (frame_idx * 15)  # Moves slower, never crosses Y=250
        vehicle_box_b = BoundingBox(x1=100, y1=vehicle_y2_b - 50, x2=200, y2=vehicle_y2_b)
        has_crossed_b = stop_line_detector.has_crossed(vehicle_box_b)
        
        helmet_facts_b = list(helmet_detector._placeholder_helmet_state(event, vehicle_box_b, synthetic_has_helmet=True, synthetic_confidence=0.95))
        
        agg_facts_b, agg_conf_b = aggregator.update_track(
            track_id="track_88",
            vehicle_class="motorcycle",
            crossed_stop_line_now=has_crossed_b,
            signal_state_now=signal_fact.state,
            has_helmet_now=helmet_facts_b[0].has_helmet,
            confidences_now={"track": 0.92, "detection": 0.90, "signal": signal_fact.confidence, "helmet": helmet_facts_b[0].confidence}
        )
        
        print(f"  Track B (Not Crossing)| Y={vehicle_y2_b} | Crossed={has_crossed_b} | Persistence={agg_facts_b['persistence_frames']}")
        violations_b = engine.evaluate("track_88", "cam_01", agg_facts_b, agg_conf_b)
        for v in violations_b:
            print(f"   => ALARM B! {v.violation_type} ({v.status})")

        # --- TRACK C: SPURIOUS CROSSING ---
        # Stays entirely outside polygon, but jitters into it for exactly Frame 4
        has_crossed_c = True if frame_idx == 4 else False
        
        helmet_facts_c = list(helmet_detector._placeholder_helmet_state(event, vehicle_box_b, synthetic_has_helmet=True, synthetic_confidence=0.95))
        
        agg_facts_c, agg_conf_c = aggregator.update_track(
            track_id="track_77",
            vehicle_class="motorcycle",
            crossed_stop_line_now=has_crossed_c,
            signal_state_now=signal_fact.state,
            has_helmet_now=helmet_facts_c[0].has_helmet,
            confidences_now={"track": 0.92, "detection": 0.90, "signal": signal_fact.confidence, "helmet": helmet_facts_c[0].confidence}
        )
        
        print(f"  Track C (Spurious)    | Crossed(Now)={has_crossed_c} | Latched={agg_facts_c['crossed_stop_line']} | Persistence={agg_facts_c['persistence_frames']}")
        violations_c = engine.evaluate("track_77", "cam_01", agg_facts_c, agg_conf_c)
        for v in violations_c:
            print(f"   => ALARM C! {v.violation_type} ({v.status})")

if __name__ == '__main__':
    run_pipeline()
