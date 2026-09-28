"""Live, end-to-end camera processing for YUVATECH.

The deployment entrypoint creates one processor per camera. Each frame flows through:
YOLO perception -> vehicle tracking -> scoped specialist models -> temporal aggregation
-> deterministic rule engine -> evidence/DB -> simulated alert.

No component other than the RuleEngine creates a violation type.
"""
from __future__ import annotations

import logging
from typing import Any

from aggregation.aggregator import EventAggregator
from alert.alert import SimulatedAlertGenerator
from attribute_pipeline.geometry import StopLineDetector
from attribute_pipeline.helmet import HelmetDetector
from attribute_pipeline.seatbelt import SeatbeltDetector
from attribute_pipeline.signal import SignalStateDetector
from attribute_pipeline.triple_riding import count_riders_on_vehicle
from config.settings import settings
from db.manager import DatabaseManager
from detection.config import DetectionConfig
from detection.detector import BoundingBox, VehicleDetector
from evidence.generator import EvidenceGenerator
from ingestion.stream import FrameEvent
from plate.pipeline import PlatePipeline
from rule_engine.engine import RuleEngine
from tracking.config import TrackingConfig
from tracking.tracker import ObjectTracker
from tracking.reid import ColorHistogramEmbedder
from event_bus.bus import InMemoryEventBus

logger = logging.getLogger(__name__)

VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
ALL_COCO_CLASSES = (0, 2, 3, 5, 7)  # person + vehicle classes


class LiveCameraProcessor:
    """Stateful processor for exactly one camera feed."""

    def __init__(self, camera_id: str, db: DatabaseManager, event_bus: InMemoryEventBus | None = None):
        self.camera_id = camera_id
        self.db = db
        self.event_bus = event_bus
        self.reid = ColorHistogramEmbedder()
        self.detector = VehicleDetector(
            DetectionConfig(model_name=getattr(settings, "vehicle_model", "yolov8s.pt"))
        )
        self.tracker = ObjectTracker(TrackingConfig())
        self.plate_pipeline = PlatePipeline()
        self.helmet_detector = HelmetDetector()
        self.seatbelt_detector = SeatbeltDetector()
        self.signal_detector = SignalStateDetector()
        self.aggregator = EventAggregator(debounce_frames=2)
        self.rule_engine = RuleEngine("rule_engine/rules.json", confidence_threshold=0.75)
        self.evidence_generator = EvidenceGenerator(settings.evidence_dir)
        self.alert_generator = SimulatedAlertGenerator()
        self._known_tracks: set[str] = set()
        self.calibration = db.get_camera_calibration(camera_id)
        self.stop_line = self._build_stop_line(self.calibration)

    @staticmethod
    def _build_stop_line(calibration: dict[str, Any]):
        points = calibration.get("stop_line_polygon")
        if not points or len(points) < 3:
            return None
        try:
            return StopLineDetector([(float(x), float(y)) for x, y in points])
        except (TypeError, ValueError):
            logger.warning("Invalid stop_line_polygon; red-light geometry disabled")
            return None

    @staticmethod
    def _bbox(value) -> BoundingBox | None:
        if not value or len(value) != 4:
            return None
        try:
            return BoundingBox(*[float(v) for v in value])
        except (TypeError, ValueError):
            return None

    def _signal_state(self, frame: FrameEvent):
        bbox = self._bbox(self.calibration.get("signal_bbox"))
        if bbox is None:
            return "UNKNOWN", 0.0
        fact = next(iter(self.signal_detector.extract_state(frame, bbox)), None)
        if fact is None:
            return "UNKNOWN", 0.0
        return fact.state, fact.confidence

    @staticmethod
    def _overlap(a: BoundingBox, b: BoundingBox) -> float:
        ix1=max(a.x1,b.x1); iy1=max(a.y1,b.y1); ix2=min(a.x2,b.x2); iy2=min(a.y2,b.y2)
        if ix2<=ix1 or iy2<=iy1: return 0.0
        inter=(ix2-ix1)*(iy2-iy1); area=max(1.0,(b.x2-b.x1)*(b.y2-b.y1))
        return inter/area

    def process(self, frame: FrameEvent) -> list[object]:
        detection_event = self.detector.process_frame(frame, classes=ALL_COCO_CLASSES)
        vehicle_event = type(detection_event)(
            camera_id=detection_event.camera_id,
            frame_id=detection_event.frame_id,
            timestamp_ms=detection_event.timestamp_ms,
            detections=[d for d in detection_event.detections if d.class_name in VEHICLE_CLASSES],
        )
        tracked_event = next(self.tracker.process_stream(iter([vehicle_event])))
        person_detections = [d for d in detection_event.detections if d.class_name == "person"]
        signal_state, signal_conf = self._signal_state(frame)
        emitted = []

        for tracked in tracked_event.tracked_detections:
            track_id = str(tracked.track_id)
            vehicle_box = tracked.raw_fact.bbox
            vehicle_class = tracked.raw_fact.class_name
            if track_id not in self._known_tracks:
                self.db.save_track_stub(track_id, self.camera_id)
                self._known_tracks.add(track_id)

            plate_result = self.plate_pipeline.process(
                frame, vehicle_box=vehicle_box, track_key=f"{self.camera_id}:{track_id}"
            )
            plate_text = None
            plate_conf = 0.0
            plate_full = False
            plate_bbox = None
            if plate_result:
                voted = plate_result.get("voted")
                raw = plate_result.get("ocr")
                selected = voted or raw
                if selected and selected.text:
                    plate_text = selected.text
                    plate_conf = float(selected.confidence)
                    plate_full = bool(selected.is_format_valid and voted is not None)
                    plate_bbox = plate_result["detection"].bounding_box
                    self.db.save_plate_observation(
                        plate_text, self.camera_id, track_id, frame.timestamp_ms, plate_conf
                    )

            # Persist a lightweight, deterministic Re-ID embedding tied to the actual track.
            try:
                self.db.save_vehicle_embedding(self.reid.extract(frame, vehicle_box, track_id))
            except Exception:
                logger.exception("Failed to persist Re-ID embedding for %s:%s", self.camera_id, track_id)

            helmet_fact = next(iter(self.helmet_detector.detect(frame, vehicle_box)), None)
            has_helmet = True if helmet_fact is None else helmet_fact.has_helmet
            helmet_conf = 0.0 if helmet_fact is None else helmet_fact.confidence

            seatbelt_fact = next(iter(self.seatbelt_detector.detect(frame, vehicle_box)), None)
            seatbelt_fastened = True if seatbelt_fact is None else seatbelt_fact.seatbelt_fastened
            seatbelt_conf = 0.0 if seatbelt_fact is None else seatbelt_fact.confidence

            rider_fact = count_riders_on_vehicle(vehicle_box, person_detections)
            crossed = self.stop_line.has_crossed(vehicle_box) if self.stop_line else False
            facts, confidences = self.aggregator.update_track(
                track_id=track_id,
                vehicle_class=vehicle_class,
                crossed_stop_line_now=crossed,
                signal_state_now=signal_state,
                has_helmet_now=has_helmet,
                rider_count_now=rider_fact.rider_count,
                seatbelt_fastened_now=seatbelt_fastened,
                plate_text_now=plate_text,
                plate_confidence_now=plate_conf,
                plate_is_full_now=plate_full,
                confidences_now={
                    "track": min(1.0, float(tracked.raw_fact.confidence)),
                    "detection": min(1.0, float(tracked.raw_fact.confidence)),
                    "signal": signal_conf,
                    "helmet": helmet_conf,
                    "person": rider_fact.confidence,
                    "seatbelt": seatbelt_conf,
                    "plate": plate_conf,
                },
            )
            violations = self.rule_engine.evaluate(
                track_id,
                self.camera_id,
                facts,
                confidences,
                timestamp_ms=frame.timestamp_ms,
            )

            for event in violations:
                bundle = self.evidence_generator.generate_bundle(
                    event,
                    frame,
                    vehicle_box,
                    facts,
                    plate_bbox=plate_bbox,
                    privacy_boxes=[d.bbox for d in person_detections if self._overlap(d.bbox, vehicle_box) <= 0.15],
                )
                event.evidence_bundle_ref = bundle.bundle_id
                self.db.save_violation_event(event)
                self.db.save_evidence_bundle(bundle)
                self.alert_generator.generate_and_log_alert(event, bundle)
                if self.event_bus is not None:
                    self.event_bus.publish("violations", {"event_id": event.event_id, "camera_id": event.camera_id, "track_id": event.track_id, "violation_type": event.violation_type, "plate_text": event.plate_text, "status": event.status})
                emitted.append(event)

        return emitted


class LivePipelineService:
    """Owns the multi-camera workers and exposes lifecycle/status operations."""

    def __init__(self, db: DatabaseManager, camera_configs):
        from ingestion.multi_camera import MultiCameraRunner

        self.db = db
        self.camera_configs = camera_configs
        self.event_bus = InMemoryEventBus()
        self.runner = MultiCameraRunner(
            camera_configs,
            processor_factory=lambda camera_id: LiveCameraProcessor(camera_id, self.db, self.event_bus).process,
            reconnect_enabled=settings.camera_reconnect_enabled,
            max_retries=settings.camera_reconnect_max_retries,
            initial_backoff=settings.camera_reconnect_initial_backoff,
            max_backoff=settings.camera_reconnect_max_backoff,
        )

    def start(self):
        self.runner.start()
        return self.status()

    def stop(self):
        self.runner.stop()
        self.runner.join(timeout=5.0)
        return self.status()

    def status(self):
        snapshot = self.runner.health_snapshot()
        for health in snapshot.values():
            try:
                self.db.save_camera_status(health)
            except Exception:
                logger.exception("Failed to persist camera health for %s", health.camera_id)
        return {
            camera_id: {
                "status": health.status,
                "frames_processed": health.frames_processed,
                "events_emitted": health.events_emitted,
                "last_frame_ts": health.last_frame_ts,
                "last_error": health.last_error,
                "reconnect_count": health.reconnect_count,
                "consecutive_failures": health.consecutive_failures,
            }
            for camera_id, health in snapshot.items()
        }
