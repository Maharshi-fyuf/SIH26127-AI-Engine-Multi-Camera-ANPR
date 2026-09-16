from __future__ import annotations
import hashlib
import json
import os
import cv2
import uuid
from pathlib import Path
from typing import Dict, Any, Iterable, Optional
from ingestion.stream import FrameEvent
from detection.detector import BoundingBox
from rule_engine.models import ViolationEvent
from evidence.models import EvidenceBundle

class EvidenceGenerator:
    """Creates reproducible evidence artifacts with a signed-by-hash manifest."""
    def __init__(self, output_dir: str = "evidence_output"):
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(path: str) -> str:
        h=hashlib.sha256()
        with open(path,'rb') as f:
            for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
        return h.hexdigest()

    def generate_bundle(self, event: ViolationEvent, frame: FrameEvent, bbox: BoundingBox,
                        aggregated_facts: Dict[str, Any], context_frames: Optional[Iterable[FrameEvent]]=None,
                        plate_bbox: Optional[BoundingBox]=None) -> EvidenceBundle:
        bundle_id=f"bndl_{uuid.uuid4().hex[:12]}"
        h,w=frame.image.shape[:2]
        def crop_save(image, box, suffix):
            x1=max(0,int(box.x1)-20); y1=max(0,int(box.y1)-20); x2=min(w,int(box.x2)+20); y2=min(h,int(box.y2)+20)
            crop=image[y1:y2,x1:x2]
            path=os.path.join(self.output_dir,f"{bundle_id}_{suffix}.jpg")
            if crop.size: cv2.imwrite(path,crop)
            return path
        paths=[crop_save(frame.image,bbox,'scene')]
        if plate_bbox: paths.append(crop_save(frame.image,plate_bbox,'plate'))
        for idx,ctx in enumerate(list(context_frames or [])[:6]):
            p=os.path.join(self.output_dir,f"{bundle_id}_context_{idx:02d}.jpg")
            cv2.imwrite(p,ctx.image); paths.append(p)
        metadata={
            **aggregated_facts,
            "event_id":event.event_id,"camera_id":event.camera_id,"track_id":event.track_id,
            "violation_type":event.violation_type,"timestamp_ms":event.timestamp_ms,
            "rule_confidence":event.rule_confidence,"aggregated_confidence":event.aggregated_confidence,
            "evidence_version":"2.0"
        }
        hashes={p:self._sha256(p) for p in paths if os.path.exists(p)}
        metadata["artifact_sha256"]=hashes
        # Stable bundle integrity digest over artifact hashes; avoids self-referential manifest hashing.
        integrity_input=json.dumps(hashes,sort_keys=True,separators=(",",":" )).encode()
        metadata["integrity_sha256"]=hashlib.sha256(integrity_input).hexdigest()
        metadata_path=os.path.join(self.output_dir,f"{bundle_id}_manifest.json")
        metadata["manifest_path"]=metadata_path
        with open(metadata_path,'w',encoding='utf-8') as f: json.dump(metadata,f,indent=2,sort_keys=True)
        return EvidenceBundle(bundle_id,event.event_id,paths,"",json.dumps(metadata),)
