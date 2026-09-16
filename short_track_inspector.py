"""
short_track_inspector.py

For a sample of short-lived motorcycle tracks (<= 10 frames), extracts:
  - The last frame where the track was seen
  - The 3 frames AFTER the track died

If the vehicle is still visibly in-frame in those post-death frames (and
just undetected), the track died prematurely. If the vehicle has left the
frame, the death was legitimate.

Saves annotated frames to debug_frames/short_track_inspect/ for manual review.
"""

import cv2
import os
import torch
from collections import defaultdict

from ingestion.stream import FrameEvent
from detection.detector import VehicleDetector
from detection.config import DetectionConfig
from tracking.tracker import ObjectTracker
from tracking.config import TrackingConfig

INPUT_PATH  = "test_footage/sample_traffic_full.mp4"
OUTPUT_DIR  = "debug_frames/short_track_inspect"
MAX_SECONDS = 30

PALETTE = [
    (255, 60, 60), (60, 200, 60), (60, 60, 255), (255, 200, 0),
    (200, 0, 255), (0, 200, 255), (255, 140, 0), (140, 255, 0),
]

def colour_for(tid): return PALETTE[tid % len(PALETTE)]

def draw_label(img, text, x, y, col, scale=0.45):
    (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    cv2.rectangle(img, (x, y - th - bl - 2), (x + tw + 4, y + bl), col, -1)
    cv2.putText(img, text, (x + 2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, scale,
                (255, 255, 255), 1, cv2.LINE_AA)

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cap = cv2.VideoCapture(INPUT_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    max_frames = int(fps * MAX_SECONDS)

    detector = VehicleDetector(DetectionConfig())
    tracker  = ObjectTracker(TrackingConfig())

    raw_frames = {}

    def frame_gen():
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        for fid in range(max_frames):
            ret, frame = cap.read()
            if not ret:
                break
            raw_frames[fid] = frame.copy()
            yield FrameEvent("cam_debug", fid, fid / fps * 1000, frame)

    det_list = list(detector.process_stream(frame_gen()))
    cap.release()

    # track_id -> sorted list of (frame_id, bbox, class) for motorcycle tracks
    moto_tracks = defaultdict(list)

    # frame_id -> all tracked detections (including non-motorcycle)
    tracked_by_frame = defaultdict(list)

    for te in tracker.process_stream(iter(det_list)):
        for tf in te.tracked_detections:
            tracked_by_frame[te.frame_id].append(tf)
            if tf.raw_fact.class_name == "motorcycle":
                moto_tracks[tf.track_id].append((te.frame_id, tf.raw_fact.bbox))

    # Find tracks with total_appearances <= 10
    short_tracks = [
        (tid, frames)
        for tid, frames in moto_tracks.items()
        if len(frames) <= 10
    ]

    print(f"Total motorcycle tracks: {len(moto_tracks)}")
    print(f"Short tracks (<= 10 frames): {len(short_tracks)}")

    # Pick 3 with >= 3 frames (enough to be real, short enough to be suspect)
    candidates = sorted(
        [(len(f), tid, f) for tid, f in short_tracks if len(f) >= 3],
        reverse=True
    )[:3]

    for total, tid, frames in candidates:
        frames_sorted = sorted(frames, key=lambda x: x[0])
        first_frame   = frames_sorted[0][0]
        last_frame    = frames_sorted[-1][0]

        print(f"\n--- Track ID {tid}: {total} frames, seen {first_frame}→{last_frame} ---")

        # Show: last 2 frames of life + 3 frames after death
        inspect_fids = [f for f, _ in frames_sorted[-2:]]
        post_death   = [last_frame + 1, last_frame + 2, last_frame + 3]
        post_death   = [f for f in post_death if f in raw_frames]

        all_fids_to_show = inspect_fids + post_death
        # tag them
        labels = {f: "ALIVE" for f in inspect_fids}
        labels.update({f: "POST-DEATH" for f in post_death})

        for fid in all_fids_to_show:
            frame  = raw_frames[fid].copy()
            tracks = tracked_by_frame.get(fid, [])

            # Draw all active tracks lightly
            for tf in tracks:
                bb  = tf.raw_fact.bbox
                x1, y1, x2, y2 = int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2)
                col = colour_for(tf.track_id)
                thick = 3 if tf.track_id == tid else 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, thick)
                draw_label(frame, f"ID:{tf.track_id} {tf.raw_fact.class_name}", x1, y1, col)

            phase = labels.get(fid, "POST-DEATH")
            colour = (0, 220, 0) if phase == "ALIVE" else (0, 0, 255)

            cv2.putText(frame,
                f"Frame {fid} | Track {tid} | {phase}",
                (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1)

            out_path = os.path.join(OUTPUT_DIR,
                f"track{tid}_{phase.lower().replace('-','_')}_f{fid:04d}.jpg")
            cv2.imwrite(out_path, frame)
            print(f"  Saved: {out_path}  [{phase}]")

    print(f"\nInspect {OUTPUT_DIR}/ to determine whether short tracks died because:")
    print("  - ALIVE frames show box on vehicle, POST-DEATH frames show empty space → LEGITIMATE")
    print("  - ALIVE frames show box on vehicle, POST-DEATH shows same vehicle still in frame → PREMATURE KILL")

if __name__ == "__main__":
    run()
