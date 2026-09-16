from dataclasses import dataclass

@dataclass
class TrackingConfig:
    """
    Configuration for the object tracking module.
    Tracking thresholds are explicitly configured here,
    not left as silent library defaults (Architecture Invariant).
    """
    distance_function: str = "iou"
    
    # Maximum distance threshold to consider a match.
    # For IoU, distance is (1 - IoU), so 0.8 means minimum 20% overlap.
    max_distance_threshold: float = 0.8
    
    # How many consecutive frames a tracked object must be seen before it is considered stable/confirmed.
    # Set to 2 frames to avoid short phantom flickers.
    initialization_delay: int = 2
    
    # How many consecutive frames a tracked object can be missing before we discard it from memory entirely.
    # Set to 15 frames (about 1 second at 15fps) to bridge brief occlusions.
    hit_counter_max: int = 15
