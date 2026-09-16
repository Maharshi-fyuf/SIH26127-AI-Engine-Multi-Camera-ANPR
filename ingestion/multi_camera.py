import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional

from ingestion.stream import CameraConfig, FrameEvent, VideoStream

logger = logging.getLogger(__name__)

@dataclass
class CameraHealth:
    camera_id: str
    status: str = "starting"
    frames_processed: int = 0
    events_emitted: int = 0
    last_frame_ts: float = 0.0
    last_error: str = ""
    reconnect_count: int = 0
    consecutive_failures: int = 0
    simulated: bool = False

@dataclass
class CameraWorkerResult:
    camera_id: str
    frame: FrameEvent
    events: List[object] = field(default_factory=list)

FrameProcessor = Callable[[FrameEvent], List[object]]
StreamFactory = Callable[[CameraConfig], Iterator[FrameEvent]]

class CameraWorker:
    """Runs a camera feed with bounded exponential reconnect for live sources."""
    def __init__(self, config, processor, result_queue, stream_factory=None, simulated=False,
                 reconnect_enabled=True, max_retries=0, initial_backoff=1.0, max_backoff=30.0):
        self.config=config; self.processor=processor; self.result_queue=result_queue
        self.stream_factory=stream_factory or self._default_stream_factory
        self.health=CameraHealth(camera_id=config.camera_id, simulated=simulated)
        self._stop_event=threading.Event(); self._thread=None
        self.reconnect_enabled=reconnect_enabled
        self.max_retries=max_retries
        self.initial_backoff=max(0.1, initial_backoff)
        self.max_backoff=max(self.initial_backoff, max_backoff)

    @staticmethod
    def _is_live_source(source: str) -> bool:
        value=str(source).lower()
        return value.isdigit() or value.startswith(("rtsp://", "rtsps://", "rtmp://", "http://", "https://"))

    def _default_stream_factory(self, config):
        stream=VideoStream(config)
        try:
            yield from stream.generate_frames()
        finally:
            stream.close()

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._thread=threading.Thread(target=self.run,name=f"camera-{self.config.camera_id}",daemon=True)
        self._thread.start()

    def stop(self): self._stop_event.set()
    def join(self, timeout=None):
        if self._thread: self._thread.join(timeout)

    def run(self):
        retry_count=0
        self.health.status="connecting"
        while not self._stop_event.is_set():
            try:
                self.health.status="running" if retry_count == 0 else "reconnecting"
                saw_frame=False
                for frame in self.stream_factory(self.config):
                    if self._stop_event.is_set(): break
                    saw_frame=True
                    events=self.processor(frame)
                    self.health.frames_processed += 1
                    self.health.events_emitted += len(events)
                    self.health.last_frame_ts=time.time()*1000.0
                    self.health.last_error=""
                    self.health.consecutive_failures=0
                    self.result_queue.put(CameraWorkerResult(self.config.camera_id,frame,events))
                if self._stop_event.is_set():
                    self.health.status="stopped"; break
                # A live stream ending is treated as a disconnect; recorded files are completed normally.
                if not self._is_live_source(self.config.source_url) or not self.reconnect_enabled:
                    self.health.status="completed"; break
                retry_count += 1
                self.health.reconnect_count=retry_count
                self.health.consecutive_failures=retry_count
                self.health.status="reconnecting"
                if self.max_retries and retry_count > self.max_retries:
                    self.health.status="error"
                    self.health.last_error="maximum reconnect attempts exceeded"
                    break
                delay=min(self.max_backoff,self.initial_backoff*(2**(retry_count-1)))
                logger.warning("Camera %s disconnected after %s frames; retrying in %.1fs",self.config.camera_id,self.health.frames_processed,delay)
                self._stop_event.wait(delay)
            except Exception as exc:
                retry_count += 1
                self.health.reconnect_count=retry_count
                self.health.consecutive_failures=retry_count
                self.health.last_error=str(exc)
                logger.exception("Camera worker failure for %s",self.config.camera_id)
                if not self.reconnect_enabled or not self._is_live_source(self.config.source_url):
                    self.health.status="error"; break
                if self.max_retries and retry_count > self.max_retries:
                    self.health.status="error"; break
                delay=min(self.max_backoff,self.initial_backoff*(2**(retry_count-1)))
                self.health.status="reconnecting"
                self._stop_event.wait(delay)
        if self._stop_event.is_set(): self.health.status="stopped"

class MultiCameraRunner:
    def __init__(self,camera_configs,processor_factory,stream_factory=None,simulated_camera_ids=None,
                 reconnect_enabled=True,max_retries=0,initial_backoff=1.0,max_backoff=30.0):
        self.result_queue=queue.Queue(); simulated=set(simulated_camera_ids or [])
        self.workers={c.camera_id:CameraWorker(c,processor_factory(c.camera_id),self.result_queue,stream_factory,
            c.camera_id in simulated,reconnect_enabled,max_retries,initial_backoff,max_backoff) for c in camera_configs}
    def start(self):
        for w in self.workers.values(): w.start()
    def stop(self):
        for w in self.workers.values(): w.stop()
    def join(self,timeout=None):
        for w in self.workers.values(): w.join(timeout)
    def health_snapshot(self): return {k:v.health for k,v in self.workers.items()}
    def drain_results(self):
        results=[]
        while True:
            try: results.append(self.result_queue.get_nowait())
            except queue.Empty: break
        return results
