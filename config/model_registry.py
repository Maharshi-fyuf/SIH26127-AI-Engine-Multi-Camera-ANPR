"""Specialist model registry and optional first-run bootstrap."""
from __future__ import annotations
from pathlib import Path

MODEL_SPECS={
    "plate": {"repo":"Babblu2821/alpr-plate-detector","file":"best.pt","license":"MIT"},
    "helmet": {"repo":"sharathhhhh/safetyHelmet-detection-yolov8","file":"best.pt","license":"Apache-2.0"},
    "seatbelt": {"repo":"RISEF/yolov11s-seatbelt","file":"weights/best.pt","license":"AGPL-3.0"},
}

def resolve(name: str, configured: str, auto_download: bool=False) -> str|None:
    path=Path(configured)
    if path.is_file(): return str(path)
    if not auto_download: return None
    spec=MODEL_SPECS[name]
    try:
        from huggingface_hub import hf_hub_download
        path.parent.mkdir(parents=True,exist_ok=True)
        cached=hf_hub_download(repo_id=spec["repo"],filename=spec["file"])
        path.write_bytes(Path(cached).read_bytes())
        return str(path)
    except Exception:
        return None
