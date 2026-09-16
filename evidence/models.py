from dataclasses import dataclass
from typing import List
@dataclass
class EvidenceBundle:
    bundle_id: str
    event_id: str
    image_paths: List[str]
    clip_path: str
    metadata_json: str
