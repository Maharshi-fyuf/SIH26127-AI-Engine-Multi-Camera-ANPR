"""Dedicated live-perception worker for container deployments."""
from __future__ import annotations
import os
import time
from config.settings import settings
from db.manager import DatabaseManager
from ingestion.stream import CameraConfig
from pipeline.live import LivePipelineService

def parse_camera_sources(raw: str):
    configs=[]
    for item in (raw or "").split(";"):
        item=item.strip()
        if not item or "=" not in item: continue
        camera_id, source=item.split("=",1)
        if camera_id.strip() and source.strip(): configs.append(CameraConfig(camera_id.strip(),source.strip()))
    return configs

if __name__ == "__main__":
    configs=parse_camera_sources(settings.camera_sources)
    if not configs:
        raise SystemExit("YUVATECH_CAMERAS must contain cam_id=source;cam_id=source")
    service=LivePipelineService(DatabaseManager(settings.db_path), configs)
    service.start()
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        service.stop()
