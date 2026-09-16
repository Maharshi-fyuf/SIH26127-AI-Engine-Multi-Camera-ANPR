import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass
class CameraLocation:
    camera_id: str
    latitude: float
    longitude: float


@dataclass
class TrajectoryPoint:
    camera_id: str
    timestamp_ms: float
    latitude: float
    longitude: float


def haversine_meters(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000.0 * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def build_trajectory(camera_ids: Iterable[str], locations: Dict[str, CameraLocation], start_ts_ms: float) -> List[TrajectoryPoint]:
    points: List[TrajectoryPoint] = []
    for index, camera_id in enumerate(camera_ids):
        location = locations[camera_id]
        points.append(TrajectoryPoint(camera_id, start_ts_ms + index * 1000.0, location.latitude, location.longitude))
    return points


def violation_heatmap(events: Iterable[Dict], precision: int = 4) -> Dict[Tuple[float, float], int]:
    buckets: Dict[Tuple[float, float], int] = {}
    for event in events:
        if event.get("latitude") is None or event.get("longitude") is None:
            continue
        key = (round(float(event["latitude"]), precision), round(float(event["longitude"]), precision))
        buckets[key] = buckets.get(key, 0) + 1
    return buckets


def origin_destination_report(trajectories: Iterable[List[TrajectoryPoint]]) -> Dict[Tuple[str, str], int]:
    report: Dict[Tuple[str, str], int] = {}
    for trajectory in trajectories:
        if len(trajectory) < 2:
            continue
        key = (trajectory[0].camera_id, trajectory[-1].camera_id)
        report[key] = report.get(key, 0) + 1
    return report
