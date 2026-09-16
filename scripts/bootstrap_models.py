"""Download the specialist models used by YUVATECH.

Models are fetched only when explicitly requested. This avoids silently pulling
large third-party binaries during normal development while making a clean live
installation reproducible.
"""
from __future__ import annotations
import argparse
from pathlib import Path

MODELS={
    "plate": {"repo":"Babblu2821/alpr-plate-detector","file":"best.pt","out":"plate_detector.pt","license":"MIT"},
    "helmet": {"repo":"sharathhhhh/safetyHelmet-detection-yolov8","file":"best.pt","out":"helmet_detector.pt","license":"Apache-2.0"},
    "seatbelt": {"repo":"RISEF/yolov11s-seatbelt","file":"weights/best.pt","out":"seatbelt_detector.pt","license":"AGPL-3.0"},
}

def download(names, dest):
    from huggingface_hub import hf_hub_download
    dest=Path(dest); dest.mkdir(parents=True,exist_ok=True)
    for name in names:
        spec=MODELS[name]
        target=dest/spec["out"]
        if target.exists() and target.stat().st_size>0:
            print(f"[skip] {name}: {target}"); continue
        cached=hf_hub_download(repo_id=spec["repo"],filename=spec["file"])
        target.write_bytes(Path(cached).read_bytes())
        print(f"[ok] {name}: {target} ({spec['license']})")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",action="append",choices=list(MODELS),dest="models")
    parser.add_argument("--all",action="store_true")
    parser.add_argument("--dest",default="models")
    args=parser.parse_args()
    names=list(MODELS) if args.all or not args.models else args.models
    download(names,args.dest)
