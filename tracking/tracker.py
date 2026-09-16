import logging
from typing import Iterator, List
from dataclasses import dataclass
import numpy as np

from detection.detector import DetectionEvent, DetectionFact
from tracking.config import TrackingConfig

logger=logging.getLogger(__name__)

@dataclass
class TrackedDetectionFact:
    raw_fact: DetectionFact
    track_id: int
    age: int

@dataclass
class TrackedDetectionEvent:
    camera_id: str
    frame_id: int
    timestamp_ms: float
    tracked_detections: List[TrackedDetectionFact]

class _FallbackTrack:
    def __init__(self, track_id, fact):
        self.id=track_id; self.fact=fact; self.age=0; self.hits=1; self.missed=0

class ObjectTracker:
    """Norfair-first tracker with a deterministic centroid/IoU fallback for environments
    where the optional Norfair wheel is unavailable. Production deployments should install
    the pinned Norfair dependency from requirements.txt.
    """
    def __init__(self, config: TrackingConfig):
        self.config=config
        self._fallback=False
        try:
            from norfair import Detection, Tracker
            self._Detection=Detection
            dist_func=getattr(config,"distance_function","euclidean")
            self.tracker=Tracker(distance_function=dist_func,distance_threshold=config.max_distance_threshold,
                                 initialization_delay=config.initialization_delay,hit_counter_max=config.hit_counter_max)
        except ImportError:
            logger.warning("Norfair unavailable; using deterministic local tracker fallback")
            self._fallback=True; self._tracks={}; self._next_id=1

    @staticmethod
    def _centroid(f): return ((f.bbox.x1+f.bbox.x2)/2,(f.bbox.y1+f.bbox.y2)/2)
    @staticmethod
    def _iou(a,b):
        x1=max(a.x1,b.x1); y1=max(a.y1,b.y1); x2=min(a.x2,b.x2); y2=min(a.y2,b.y2)
        if x2<=x1 or y2<=y1:return 0.0
        inter=(x2-x1)*(y2-y1); aa=(a.x2-a.x1)*(a.y2-a.y1); ab=(b.x2-b.x1)*(b.y2-b.y1)
        return inter/max(1e-9,aa+ab-inter)

    def _fallback_process(self,event):
        used=set(); output=[]
        for fact in event.detections:
            best=None; best_score=float("inf")
            for tid,t in self._tracks.items():
                if tid in used: continue
                if getattr(self.config,"distance_function","euclidean") in ("iou","iou_opt"):
                    score=1-self._iou(fact.bbox,t.fact.bbox)
                    # Norfair accepts a large configured threshold for its IoU distance
                    # function; keep the fallback behavior compatible by requiring at
                    # least moderate overlap for the normal 30-point configuration.
                    match=score <= (0.70 if self.config.max_distance_threshold >= 1 else self.config.max_distance_threshold)
                else:
                    ax,ay=self._centroid(fact); bx,by=self._centroid(t.fact)
                    score=((ax-bx)**2+(ay-by)**2)**0.5; match=score<=self.config.max_distance_threshold
                if match and score<best_score: best=(tid,t); best_score=score
            if best:
                tid,t=best; t.fact=fact; t.age+=1; t.hits+=1; t.missed=0; used.add(tid)
            else:
                tid=self._next_id; self._next_id+=1; t=_FallbackTrack(tid,fact); self._tracks[tid]=t; used.add(tid)
            if t.hits>self.config.initialization_delay:
                output.append(TrackedDetectionFact(fact,tid,t.age))
        for tid,t in list(self._tracks.items()):
            if tid not in used:
                t.missed+=1
                if t.missed>self.config.hit_counter_max: del self._tracks[tid]
        return TrackedDetectionEvent(event.camera_id,event.frame_id,event.timestamp_ms,output)

    def process_stream(self,event_iterator:Iterator[DetectionEvent])->Iterator[TrackedDetectionEvent]:
        for event in event_iterator:
            if self._fallback:
                yield self._fallback_process(event); continue
            detections=[]; dist_func=getattr(self.config,"distance_function","euclidean")
            for fact in event.detections:
                if dist_func in ("iou","iou_opt"):
                    points=np.array([[fact.bbox.x1,fact.bbox.y1],[fact.bbox.x2,fact.bbox.y2]])
                else:
                    cx,cy=self._centroid(fact); points=np.array([[cx,cy]])
                detections.append(self._Detection(points=points,data=fact))
            tracked_objects=self.tracker.update(detections=detections)
            tracked_facts=[]
            for obj in tracked_objects:
                if obj.id is None or obj.last_detection is None or obj.last_detection not in detections: continue
                tracked_facts.append(TrackedDetectionFact(obj.last_detection.data,obj.id,obj.age))
            yield TrackedDetectionEvent(event.camera_id,event.frame_id,event.timestamp_ms,tracked_facts)
