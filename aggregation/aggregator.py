from typing import Dict, Any, Tuple
from dataclasses import dataclass
import time

@dataclass
class TrackState:
    crossed_stop_line: bool = False
    pending_crossing_frames: int = 0
    persistence_frames: int = 0
    signal_state: str = "UNKNOWN"
    has_helmet: bool = True
    rider_count: int = 1
    seatbelt_fastened: bool = True
    vehicle_class: str = "unknown"
    
    # Confidence aggregation
    track_conf: float = 0.0
    detection_conf: float = 0.0
    signal_conf: float = 0.0
    helmet_conf: float = 0.0
    plate_text: str | None = None
    plate_confidence: float = 0.0
    plate_is_full: bool = False
    last_seen_ms: float = 0.0


class EventAggregator:
    def __init__(self, debounce_frames: int = 2, state_ttl_seconds: float = 3600.0):
        """
        Manages the temporal state of vehicle tracks to bridge per-frame facts 
        into the aggregated dictionary required by the Rule Engine.
        :param debounce_frames: Number of consecutive crossing frames required before permanently latching.
        """
        self.track_history: Dict[str, TrackState] = {}
        self.debounce_frames = debounce_frames
        self.state_ttl_ms = max(60.0, state_ttl_seconds) * 1000.0

    def update_track(self, 
                     track_id: str, 
                     vehicle_class: str, 
                     crossed_stop_line_now: bool, 
                     signal_state_now: str, 
                     has_helmet_now: bool,
                     confidences_now: Dict[str, float],
                     rider_count_now: int = 1,
                     seatbelt_fastened_now: bool = True,
                     plate_text_now: str | None = None,
                     plate_confidence_now: float = 0.0,
                     plate_is_full_now: bool = False) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """
        Updates the track state with the current frame's facts and returns the aggregated dictionaries.
        """
        if track_id not in self.track_history:
            self.track_history[track_id] = TrackState()
            
        state = self.track_history[track_id]
        
        # 1. Update latched/static values
        state.vehicle_class = vehicle_class
        
        # Latch crossed_stop_line with debounce
        if not state.crossed_stop_line:
            if crossed_stop_line_now:
                state.pending_crossing_frames += 1
                if state.pending_crossing_frames >= self.debounce_frames:
                    state.crossed_stop_line = True
            else:
                state.pending_crossing_frames = 0
            
        # Update latest dynamic values
        state.signal_state = signal_state_now
        state.has_helmet = has_helmet_now
        state.rider_count = rider_count_now
        state.seatbelt_fastened = seatbelt_fastened_now
        
        # 2. Update persistence frames for every stable observation.
        # Rule-specific conditions decide what this persistence means. For example,
        # red-light rules additionally require crossed_stop_line=True, while helmet,
        # seatbelt and rider-count rules can use the same temporal stability window.
        state.persistence_frames += 1
            
        # 3. Update confidences (simple latest-value for V1, could be EMA/averages)
        state.track_conf = confidences_now.get("track", state.track_conf)
        state.detection_conf = confidences_now.get("detection", state.detection_conf)
        state.signal_conf = confidences_now.get("signal", state.signal_conf)
        state.helmet_conf = confidences_now.get("helmet", state.helmet_conf)
        if plate_text_now:
            state.plate_text = plate_text_now
            state.plate_confidence = plate_confidence_now
            state.plate_is_full = plate_is_full_now
        
        # 4. Export to dictionaries for Rule Engine
        aggregated_facts = {
            "vehicle_class": state.vehicle_class,
            "crossed_stop_line": state.crossed_stop_line,
            "signal_state": state.signal_state,
            "has_helmet": state.has_helmet,
            "rider_count": state.rider_count,
            "seatbelt_fastened": state.seatbelt_fastened,
            "persistence_frames": state.persistence_frames,
            "plate_text": state.plate_text,
            "plate_confidence": state.plate_confidence,
            "plate_is_full": state.plate_is_full
        }
        
        out_confidences = {
            "track": state.track_conf,
            "detection": state.detection_conf,
            "signal": state.signal_conf,
            "helmet": state.helmet_conf,
            "person": confidences_now.get("person", state.detection_conf),
            "seatbelt": confidences_now.get("seatbelt", state.detection_conf),
            "plate": state.plate_confidence
        }
        
        return aggregated_facts, out_confidences
