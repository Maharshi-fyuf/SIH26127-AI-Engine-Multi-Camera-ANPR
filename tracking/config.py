from dataclasses import dataclass

@dataclass
class TrackingConfig:
    distance_function: str = "iou"
    max_distance_threshold: float = 0.8
    initialization_delay: int = 2
    hit_counter_max: int = 15

    def __post_init__(self):
        if self.distance_function not in {"iou", "iou_opt", "euclidean"}:
            raise ValueError("distance_function must be 'iou'/'iou_opt' or 'euclidean'")
        if self.max_distance_threshold <= 0:
            raise ValueError("max_distance_threshold must be > 0")
        if self.distance_function in {"iou", "iou_opt"} and self.max_distance_threshold > 1:
            raise ValueError("IoU distance threshold must be <= 1; use distance_function='euclidean' for pixel distance")
        if self.initialization_delay < 0 or self.hit_counter_max < 1:
            raise ValueError("initialization_delay must be >= 0 and hit_counter_max must be >= 1")
