"""
track_id_stability_check.py

Finds motorcycle tracks that are continuously visible across the most
consecutive frames, picks the best candidate, and writes 6 consecutive
annotated frames to debug_frames/stability_check/ for manual ID inspection.

This answers the question: does a single physical vehicle keep the same
track ID while it's continuously visible and unoccluded?
"""

import cv2
import os
import torch  # Must import before paddle
from collections import defaultdict

from ingestion.stream import FrameEvent
from detection.detector import VehicleDetector
from detection.config import DetectionConfig
from tracking.tracker import ObjectTracker
from tracking.config import TrackingConfig

INPUT_PATH   = "test_footage/sample_traffic_full.mp4"
OUTPUT_DIR   = "debug_frames/stability_check"
MAX_SECONDS  = 30
PALETTE = [
    (255, 60,  60), (60, 200, 60), (60, 60, 255), (255, 200, 0),
    (200, 0, 255),  (0, 200, 255), (255, 140, 0),  (140, 255, 0),
]

def colour_for(track_id):
    return PALETTE[track_id % len(PALETTE)]

def draw_label(img, text, x, y, colour):
    (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(img, (x, y - th - bl - 2), (x + tw + 4, y + bl), colour, -1)
    cv2.putText(img, text, (x + 2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255), 1, cv2.LINE_AA)

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cap = cv2.VideoCapture(INPUT_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    max_frames = int(fps * MAX_SECONDS)

    detector = VehicleDetector(DetectionConfig())
    tracker  = ObjectTracker(TrackingConfig())

    # --- Pass 1: detect + track, record per-track appearance list ---
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

    # track_id → sorted list of frame_ids where it appeared as 'motorcycle'
    moto_appearances = defaultdict(list)

    for te in tracker.process_stream(iter(det_list)):
        for tf in te.tracked_detections:
            if tf.raw_fact.class_name == "motorcycle":
                moto_appearances[tf.track_id].append(te.frame_id)

    cap.release()

    if not moto_appearances:
        print("No motorcycle tracks found.")
        return

    # --- Find the track with the longest run of CONSECUTIVE frames ---
    def longest_consecutive_run(frame_ids):
        """Returns (start_frame, length) of the longest consecutive sequence."""
        if not frame_ids:
            return 0, 0
        best_start, best_len = frame_ids[0], 1
        cur_start, cur_len  = frame_ids[0], 1
        for i in range(1, len(frame_ids)):
            if frame_ids[i] == frame_ids[i-1] + 1:
                cur_len += 1
                if cur_len > best_len:
                    best_len  = cur_len
                    best_start = cur_start
            else:
                cur_start = frame_ids[i]
                cur_len   = 1
        return best_start, best_len

    best_track_id  = None
    best_run_start = 0
    best_run_len   = 0

    print("Top 10 motorcycle tracks by longest consecutive run:")
    candidates = []
    for tid, fids in moto_appearances.items():
        start, length = longest_consecutive_run(sorted(fids))
        candidates.append((length, start, tid, len(fids)))

    candidates.sort(reverse=True)
    for i, (length, start, tid, total) in enumerate(candidates[:10]):
        print(f"  Track ID {tid:>4}: consecutive={length} frames  (start={start}, total_appearances={total})")
        if i == 0:
            best_track_id  = tid
            best_run_start = start
            best_run_len   = length

    # --- Extract 6 consecutive frames from the best run ---
    n_frames_to_save = min(6, best_run_len)
    target_frames    = list(range(best_run_start, best_run_start + n_frames_to_save))

    print(f"\nSelected Track ID {best_track_id} — extracting frames {target_frames}")

    # Re-run tracker just to get the bboxes for those frames
    # (we already have raw_frames cached)
    det_events = {de.frame_id: de for de in det_list}
    tracked_by_frame = {}
    for te in tracker.process_stream(iter(det_list)):
        tracked_by_frame[te.frame_id] = te.tracked_detections

    saved = []
    for fid in target_frames:
        frame  = raw_frames[fid].copy()
        tracks = tracked_by_frame.get(fid, [])

        # Draw ALL tracks (lighter) so we can see if IDs switch
        for tf in tracks:
            bb  = tf.raw_fact.bbox
            x1, y1, x2, y2 = int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2)
            is_target = (tf.track_id == best_track_id)
            col = colour_for(tf.track_id)
            thickness = 3 if is_target else 1
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, thickness)
            label = f"ID:{tf.track_id} {tf.raw_fact.class_name} {tf.raw_fact.confidence:.2f}"
            if is_target:
                # Larger label for the tracked vehicle
                draw_label(frame, f">>> ID:{tf.track_id} motorcycle <<<", x1, max(y1-2, 20), col)
            else:
                draw_label(frame, label, x1, y1, col)

        cv2.putText(frame, f"Frame {fid} | Checking ID:{best_track_id}", (6, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        out_path = os.path.join(OUTPUT_DIR, f"stability_track{best_track_id}_frame{fid:04d}.jpg")
        cv2.imwrite(out_path, frame)
        saved.append(out_path)
        print(f"  Saved: {out_path}")

    print(f"\nDone. {len(saved)} frames written to {OUTPUT_DIR}/")
    print("If ID:{} appears in all {} frames consistently, tracking is stable for this vehicle.".format(
        best_track_id, n_frames_to_save))

if __name__ == "__main__":
    run()
