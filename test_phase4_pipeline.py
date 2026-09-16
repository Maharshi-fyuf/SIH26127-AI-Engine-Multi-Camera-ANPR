import cv2
import numpy as np
import time
import os
import sqlite3
import json

from ingestion.stream import FrameEvent
from detection.detector import BoundingBox

from attribute_pipeline.helmet import HelmetDetector
from attribute_pipeline.signal import SignalStateDetector
from attribute_pipeline.geometry import StopLineDetector
from aggregation.aggregator import EventAggregator
from rule_engine.engine import RuleEngine

from evidence.generator import EvidenceGenerator
from db.manager import DatabaseManager
from alert.alert import SimulatedAlertGenerator

def run_pipeline():
    print("=== True End-to-End Traffic Rule Engine Pipeline (with Phase 4 Evidence & DB) ===")
    
    # Clean up old test db and images
    db_file = "test_traffic.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    # Setup Detectors
    signal_detector = SignalStateDetector()
    helmet_detector = HelmetDetector()
    
    # The Stop-Line Polygon (e.g. crossing a line at Y=250)
    intersection_polygon = [(0, 250), (640, 250), (640, 480), (0, 480)]
    stop_line_detector = StopLineDetector(intersection_polygon)
    
    # Setup Aggregator & Rule Engine
    aggregator = EventAggregator(debounce_frames=2)
    engine = RuleEngine(rules_path="rule_engine/rules.json", confidence_threshold=0.75)
    
    # Setup DB and Evidence Generator
    db_manager = DatabaseManager(db_path=db_file)
    db_manager.save_camera("cam_01")
    db_manager.save_track_stub("track_99", "cam_01")
    
    ev_generator = EvidenceGenerator(output_dir="evidence_output")
    alert_generator = SimulatedAlertGenerator()
    
    # Create 10 frames of a vehicle moving forward
    final_event_frame = None
    final_box = None
    
    for frame_idx in range(1, 11):
        # 1. Create Frame (Red traffic light always present)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.circle(img, (150, 150), 30, (0, 0, 255), -1) # RED Light
        
        # Draw a fake motorcycle (a blue rectangle) on the frame
        vehicle_y2_a = 100 + (frame_idx * 30)
        vehicle_y1_a = vehicle_y2_a - 50
        vehicle_box_a = BoundingBox(x1=300, y1=vehicle_y1_a, x2=400, y2=vehicle_y2_a)
        cv2.rectangle(img, (300, vehicle_y1_a), (400, vehicle_y2_a), (255, 0, 0), -1)
        
        event = FrameEvent(camera_id="cam_01", frame_id=frame_idx, timestamp_ms=time.time()*1000, image=img)
        
        # 2. Extract Signal State
        traffic_light_box = BoundingBox(x1=100, y1=100, x2=200, y2=200)
        signal_facts = list(signal_detector.extract_state(event, traffic_light_box))
        signal_fact = signal_facts[0]
        
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
        
        violations_a = engine.evaluate("track_99", "cam_01", agg_facts_a, agg_conf_a)
        
        for v in violations_a:
            print(f"[Frame {frame_idx}] => ALARM A! {v.violation_type} ({v.status})")
            
            # --- PHASE 4: EVIDENCE AND DATABASE ---
            # 1. Generate Evidence Bundle (Image crop)
            bundle = ev_generator.generate_bundle(v, event, vehicle_box_a, agg_facts_a)
            
            # Link bundle to violation
            v.evidence_bundle_ref = bundle.bundle_id
            
            # 2. Persist to SQLite
            db_manager.save_violation_event(v)
            db_manager.save_evidence_bundle(bundle)
            
            # 3. Generate Simulated Alert Output
            alert_generator.generate_and_log_alert(v, bundle)
            
    print("\n=== Validation ===")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    print("\n[DB Dump] ViolationEvent Table:")
    cursor.execute("SELECT event_id, track_id, camera_id, violation_type, status, evidence_bundle_ref FROM ViolationEvent")
    for row in cursor.fetchall():
        print(f"  {row}")
        
    print("\n[DB Dump] EvidenceBundle Table:")
    cursor.execute("SELECT bundle_id, event_id, image_paths, metadata_json FROM EvidenceBundle")
    for row in cursor.fetchall():
        print(f"  {row}")
        # Verify file exists and is readable by cv2
        paths = json.loads(row[2])
        for p in paths:
            img_read = cv2.imread(p)
            is_sane = img_read is not None and img_read.shape[0] > 0 and img_read.shape[1] > 0
            shape = img_read.shape if img_read is not None else None
            print(f"  -> File physically exists and readable via cv2? {is_sane} (shape={shape})")

if __name__ == "__main__":
    run_pipeline()
