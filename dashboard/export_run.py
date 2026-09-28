"""Turn a real YUVATECH pipeline run into the dashboard's data.json and evidence images.

Usage (from the project root, after a run):
    python dashboard/export_run.py --db <path to sqlite db> --evidence-root <evidence dir>

Reads the ViolationEvent, EvidenceBundle and CameraStatus tables only; never writes to the DB.
Standard library only.
"""
import argparse, json, shutil, sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent


def mask_plate(text):
    if not text:
        return None
    t = str(text)
    return t if len(t) <= 4 else t[:2] + "*" * (len(t) - 4) + t[-2:]


def find_image(paths, root):
    for p in paths:
        cand = [Path(p), root / p, root / Path(p).name]
        cand += list(root.rglob(Path(p).name)) if root.is_dir() else []
        for c in cand:
            if c.is_file():
                return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SQLite database written by the pipeline")
    ap.add_argument("--evidence-root", default=".", help="Folder that holds the evidence images")
    ap.add_argument("--out", default=str(HERE), help="Dashboard folder (default: this folder)")
    ap.add_argument("--show-plates", action="store_true", help="Export full plate text (default: masked)")
    a = ap.parse_args()

    out, root = Path(a.out), Path(a.evidence_root)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    rows = db.execute(
        "SELECT event_id, track_id, camera_id, violation_type, aggregated_confidence, status, timestamp,"
        " plate_text, evidence_bundle_ref FROM ViolationEvent ORDER BY timestamp").fetchall()
    if not rows:
        raise SystemExit("No violation events in this database, nothing to export.")
    t0 = rows[0]["timestamp"]

    events, missing = [], 0
    for r in rows:
        b = db.execute("SELECT image_paths FROM EvidenceBundle WHERE event_id=?", (r["event_id"],)).fetchone()
        paths = json.loads(b["image_paths"] or "[]") if b else []
        img = find_image(paths, root)
        ev = None
        if img:
            ev = f"evidence/{r['event_id']}{img.suffix}"
            shutil.copyfile(img, out / ev)
        else:
            missing += 1
        events.append({
            "t": round((r["timestamp"] - t0) / 1000.0, 1),
            "camera": r["camera_id"], "track": str(r["track_id"]), "type": r["violation_type"],
            "plate": (r["plate_text"] if a.show_plates else mask_plate(r["plate_text"])),
            "conf": round(float(r["aggregated_confidence"] or 0), 2),
            "status": r["status"], "evidence": ev})

    cams = {}
    for c in db.execute("SELECT camera_id, frames_processed FROM CameraStatus"):
        cams[c["camera_id"]] = int(c["frames_processed"] or 0)
    for e in events:
        cams.setdefault(e["camera"], 0)

    meta = {"title": "YUVATECH traffic control room",
            "subtitle": "Multi-camera ANPR engine for Smart India Hackathon 2026, problem statement 26127"}
    try:
        meta.update({k: v for k, v in json.load(open(out / "data.json"))["meta"].items() if k in meta})
    except Exception:
        pass
    meta["is_sample"] = False

    data = {"meta": meta,
            "cameras": [{"id": k, "frames_total": v} for k, v in sorted(cams.items())],
            "events": events}
    (out / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Exported {len(events)} events, {len(cams)} cameras, {len(events) - missing} evidence images.")
    if missing:
        print(f"Warning: {missing} events had no readable evidence image (check --evidence-root).")
    if not a.show_plates:
        print("Plate text is masked. Evidence images can still show plates; review them before making the site public.")


if __name__ == "__main__":
    main()
