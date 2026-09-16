import math
import uuid
from dataclasses import dataclass
from typing import Iterable, List

import cv2

from detection.detector import BoundingBox
from ingestion.stream import FrameEvent


@dataclass
class VehicleEmbedding:
    embedding_id: str
    camera_id: str
    track_id: str
    timestamp_ms: float
    vector: List[float]


@dataclass
class CameraLink:
    from_camera_id: str
    to_camera_id: str
    min_travel_ms: float
    max_travel_ms: float


@dataclass
class TrajectoryMatch:
    from_embedding: VehicleEmbedding
    to_embedding: VehicleEmbedding
    similarity: float


class ColorHistogramEmbedder:
    """
    Lightweight deterministic Re-ID fallback.

    It is not a replacement for OSNet, but it gives the demo an async/batchable
    embedding interface that can later be swapped for a learned model.
    """

    def extract(self, frame: FrameEvent, bbox: BoundingBox) -> VehicleEmbedding:
        h, w = frame.image.shape[:2]
        x1, y1 = max(0, int(bbox.x1)), max(0, int(bbox.y1))
        x2, y2 = min(w, int(bbox.x2)), min(h, int(bbox.y2))
        crop = frame.image[y1:y2, x1:x2]
        if crop.size == 0:
            vector = [0.0] * 24
        else:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 3, 1], [0, 180, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            vector = [float(v) for v in hist]
        return VehicleEmbedding(
            embedding_id=f"emb_{uuid.uuid4().hex[:10]}",
            camera_id=frame.camera_id,
            track_id="",
            timestamp_ms=frame.timestamp_ms,
            vector=vector,
        )


class TrajectoryStitcher:
    def __init__(self, links: Iterable[CameraLink], similarity_threshold: float = 0.85):
        self.links = {(link.from_camera_id, link.to_camera_id): link for link in links}
        self.similarity_threshold = similarity_threshold

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / (left_norm * right_norm)

    def match(self, embeddings: Iterable[VehicleEmbedding]) -> List[TrajectoryMatch]:
        ordered = sorted(embeddings, key=lambda emb: emb.timestamp_ms)
        matches: List[TrajectoryMatch] = []
        for earlier in ordered:
            for later in ordered:
                if earlier.camera_id == later.camera_id or later.timestamp_ms <= earlier.timestamp_ms:
                    continue
                link = self.links.get((earlier.camera_id, later.camera_id))
                if link is None:
                    continue
                travel_ms = later.timestamp_ms - earlier.timestamp_ms
                if not (link.min_travel_ms <= travel_ms <= link.max_travel_ms):
                    continue
                similarity = self._cosine_similarity(earlier.vector, later.vector)
                if similarity >= self.similarity_threshold:
                    matches.append(TrajectoryMatch(earlier, later, similarity))
        return matches
