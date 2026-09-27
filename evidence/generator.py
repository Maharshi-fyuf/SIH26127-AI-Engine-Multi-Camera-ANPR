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
from governance.privacy import blur_regions

class EvidenceGenerator:
    """Creates evidence artifacts with hash-based integrity metadata.

    The SHA-256 manifest is an integrity checksum, not a legal digital signature.
    """
    def __init__(self, output_dir: str = "evidence_output"):
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(path: str) -> str:
        h=hashlib.sha256()
        with open(path,'rb') as f:
            for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _overlap(a: BoundingBox, b: BoundingBox) -> float:
        ix1=max(a.x1,b.x1); iy1=max(a.y1,b.y1); ix2=min(a.x2,b.x2); iy2=min(a.y2,b.y2)
        if ix2<=ix1 or iy2<=iy1: return 0.0
        inter=(ix2-ix1)*(iy2-iy1); area=max(1.0,(b.x2-b.x1)*(b.y2-b.y1))
        return inter/area

    def generate_bundle(self, event: ViolationEvent, frame: FrameEvent, bbox: BoundingBox,
                        aggregated_facts: Dict[str, Any], context_frames: Optional[Iterable[FrameEvent]]=None,
                        plate_bbox: Optional[BoundingBox]=None,
                        privacy_boxes: Optional[Iterable[BoundingBox]]=None) -> EvidenceBundle:
        bundle_id=f"bndl_{uuid.uuid4().hex[:12]}"
        h,w=frame.image.shape[:2]
        privacy_boxes=list(privacy_boxes or [])
        def crop_save(image, box, suffix):
            ih,iw=image.shape[:2]
            x1=max(0,int(box.x1)-20); y1=max(0,int(box.y1)-20); x2=min(iw,int(box.x2)+20); y2=min(ih,int(box.y2)+20)
            crop=image[y1:y2,x1:x2]
            if crop.size == 0: return None
            local_boxes=[]
            scale_x = iw / max(1,w); scale_y = ih / max(1,h)
            for pbox in privacy_boxes:
                pb=BoundingBox(pbox.x1*scale_x,pbox.y1*scale_y,pbox.x2*scale_x,pbox.y2*scale_y)
                if self._overlap(pb, BoundingBox(x1,y1,x2,y2)) > 0.0:
                    local_boxes.append(BoundingBox(pb.x1-x1,pb.y1-y1,pb.x2-x1,pb.y2-y1))
            if local_boxes:
                crop=blur_regions(crop, local_boxes)
            path=os.path.join(self.output_dir,f"{bundle_id}_{suffix}.jpg")
            ok=cv2.imwrite(path,crop)
            return path if ok and os.path.isfile(path) else None
        paths=[]
        scene=crop_save(frame.image,bbox,'scene')
        if scene: paths.append(scene)
        if plate_bbox:
            plate=crop_save(frame.image,plate_bbox,'plate')
            if plate: paths.append(plate)
        for idx,ctx in enumerate(list(context_frames or [])[:6]):
            image=ctx.image.copy()
            if privacy_boxes:
                image=blur_regions(image, privacy_boxes)
            p=os.path.join(self.output_dir,f"{bundle_id}_context_{idx:02d}.jpg")
            if cv2.imwrite(p,image): paths.append(p)
        metadata={
            **aggregated_facts,
            "event_id":event.event_id,"camera_id":event.camera_id,"track_id":event.track_id,
            "violation_type":event.violation_type,"timestamp_ms":event.timestamp_ms,
            "rule_confidence":event.rule_confidence,"aggregated_confidence":event.aggregated_confidence,
            "plate_text":event.plate_text, "plate_confidence":event.plate_confidence,
            "plate_is_full":event.plate_is_full,
            "privacy_redaction_applied": bool(privacy_boxes),
            "evidence_version":"3.0"
        }
        hashes={p:self._sha256(p) for p in paths}
        metadata["artifact_sha256"]=hashes
        integrity_input=json.dumps(hashes,sort_keys=True,separators=(",",":" )).encode()
        metadata["integrity_sha256"]=hashlib.sha256(integrity_input).hexdigest()
        metadata_path=os.path.join(self.output_dir,f"{bundle_id}_manifest.json")
        metadata["manifest_path"]=metadata_path
        with open(metadata_path,'w',encoding='utf-8') as f: json.dump(metadata,f,indent=2,sort_keys=True)
        return EvidenceBundle(bundle_id,event.event_id,paths,"",json.dumps(metadata),)
