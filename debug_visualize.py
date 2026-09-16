"""
debug_visualize.py

Reads the first 30 seconds of test_footage/sample_traffic_full.mp4,
runs frames through ingestion → detection → tracking, draws annotated
bounding boxes on each frame (class name + confidence + track_id),
and writes the result to debug_output.mp4.

Prints a summary: total frames, avg detections/frame, distinct track_ids,
and real measured detection FPS. Saves motorcycle-specific frame crops.
"""

import cv2
import time
import os
import numpy as np
from collections import defaultdict

import torch  # Must be imported before paddle
from ingestion.stream import FrameEvent
from detection.detector import VehicleDetector, DetectionEvent
from detection.config import DetectionConfig
from tracking.tracker import ObjectTracker
from tracking.config import TrackingConfig

# ── Config ──────────────────────────────────────────────────────────────────
INPUT_PATH   = "test_footage/sample_traffic_full.mp4"
OUTPUT_PATH  = "debug_output.mp4"
MAX_SECONDS  = 30  # Read only the first 30 seconds

# Colour palette per track_id (cycles through)
PALETTE = [
    (255, 60,  60),   # red
    (60,  200, 60),   # green
    (60,  60,  255),  # blue
    (255, 200, 0),    # yellow
    (200, 0,   255),  # purple
    (0,   200, 255),  # cyan
    (255, 140, 0),    # orange
    (140, 255, 0),    # lime
]

def colour_for(track_id: int):
    return PALETTE[track_id % len(PALETTE)]

# ── Helpers ──────────────────────────────────────────────────────────────────
def frame_generator(cap, max_frames):
    """Yields FrameEvents from an OpenCV capture, up to max_frames."""
    frame_idx = 0
    while frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        yield FrameEvent(
            camera_id="cam_debug",
            frame_id=frame_idx,
            timestamp_ms=time.time() * 1000,
            image=frame
        )
        frame_idx += 1

def draw_label(img, text, x, y, colour, font_scale=0.45, thickness=1):
    """Draws a filled-background label box at (x, y)."""
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    # Draw filled rectangle
    cv2.rectangle(img, (x, y - th - baseline - 2), (x + tw + 4, y + baseline), colour, -1)
    # Draw text in white over the rectangle
    cv2.putText(img, text, (x + 2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

# ── Main ─────────────────────────────────────────────────────────────────────
def run():
    cap = cv2.VideoCapture(INPUT_PATH)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {INPUT_PATH}")

    fps      = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    max_frames = int(fps * MAX_SECONDS)

    print(f"Source : {INPUT_PATH}  ({width}x{height} @ {fps:.1f} fps)")
    print(f"Reading up to {MAX_SECONDS}s = {max_frames} frames")

    # Video writer — use mp4v codec (no ffmpeg needed)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(OUTPUT_PATH, fourcc, fps, (width, height))

    # Pipeline components
    detector = VehicleDetector(DetectionConfig())
    tracker  = ObjectTracker(TrackingConfig())

    # Collect raw frames so we can annotate them after tracking
    raw_frames = {}    # frame_id → ndarray
    det_events = {}    # frame_id → DetectionEvent

    # --- Pass 1: ingest + detect, cache frames and detections
    print("Pass 1: Running detection...")

    def cached_frame_gen():
        """Yields FrameEvents and caches the raw image."""
        frame_idx = 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # rewind
        while frame_idx < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            fe = FrameEvent(
                camera_id="cam_debug",
                frame_id=frame_idx,
                timestamp_ms=frame_idx / fps * 1000,
                image=frame
            )
            raw_frames[frame_idx] = frame.copy()
            yield fe
            frame_idx += 1

    # Materialise detection events, measuring real wall-clock time
    t_det_start = time.perf_counter()
    det_list = list(detector.process_stream(cached_frame_gen()))
    t_det_end = time.perf_counter()

    det_elapsed = t_det_end - t_det_start
    det_fps_real = len(det_list) / max(det_elapsed, 0.001)

    for de in det_list:
        det_events[de.frame_id] = de

    print(f"  Detected over {len(det_list)} frames in {det_elapsed:.1f}s")
    print(f"  Real detection throughput: {det_fps_real:.2f} fps  ({1000/det_fps_real:.1f} ms/frame)")

    # --- Pass 2: track (tracking must see events in order)
    print("Pass 2: Running tracker...")
    tracked_by_frame = {}  # frame_id → List[TrackedDetectionFact]

    for te in tracker.process_stream(iter(det_list)):
        tracked_by_frame[te.frame_id] = te.tracked_detections

    print(f"  Tracker produced output for {len(tracked_by_frame)} frames.")

    # --- Pass 3: annotate + write
    print("Pass 3: Annotating and writing debug_output.mp4...")
    os.makedirs("debug_frames", exist_ok=True)

    total_det_count  = 0
    all_track_ids    = set()
    moto_frames_saved = 0  # Count motorcycle-specific frames saved

    for fid in sorted(raw_frames.keys()):
        frame  = raw_frames[fid].copy()
        tracks = tracked_by_frame.get(fid, [])
        dets   = det_events.get(fid)

        total_det_count += len(dets.detections) if dets else 0

        # Draw stop-line reference at Y=250 (demo polygon reference)
        cv2.line(frame, (0, int(height * 0.52)), (width, int(height * 0.52)),
                 (0, 140, 255), 2)

        frame_has_moto = False

        if tracks:
            for tf in tracks:
                all_track_ids.add(tf.track_id)
                bb  = tf.raw_fact.bbox
                col = colour_for(tf.track_id)
                x1, y1, x2, y2 = int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2)

                # Bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)

                # Label: "ID:3 motorcycle 0.72"
                label = f"ID:{tf.track_id} {tf.raw_fact.class_name} {tf.raw_fact.confidence:.2f}"
                draw_label(frame, label, x1, y1, col)

                if tf.raw_fact.class_name == "motorcycle":
                    frame_has_moto = True

        # Save up to 5 motorcycle-rich frames for manual inspection
        if frame_has_moto and moto_frames_saved < 5:
            cv2.imwrite(f"debug_frames/moto_frame_{fid:04d}.jpg", frame)
            moto_frames_saved += 1

        # Frame counter overlay
        cv2.putText(frame, f"Frame {fid}", (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

        writer.write(frame)

    cap.release()
    writer.release()

    # --- Summary
    n_frames = len(raw_frames)
    avg_det  = total_det_count / max(n_frames, 1)
    size_mb  = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)

    print("\n=== Debug Visualisation Summary ===")
    print(f"  Model               : {detector.config.model_name}  conf={detector.config.min_confidence}")
    print(f"  Frames processed    : {n_frames}")
    print(f"  Avg detections/frame: {avg_det:.2f}")
    print(f"  Distinct track IDs  : {len(all_track_ids)}")
    print(f"  Output written to   : {OUTPUT_PATH}  ({size_mb:.2f} MB)")
    print(f"  Motorcycle frames   : {moto_frames_saved} saved to debug_frames/")
    print(f"\n=== Timing ===")
    print(f"  Detection pass      : {det_elapsed:.1f}s total")
    print(f"  Real detection FPS  : {det_fps_real:.2f} fps")
    print(f"  ms per frame        : {1000/det_fps_real:.1f} ms")
    if det_fps_real >= 25:
        print(f"  Live-stream demo    : VIABLE (>= 25 fps)")
    elif det_fps_real >= 10:
        print(f"  Live-stream demo    : BORDERLINE ({det_fps_real:.1f} fps) — consider pre-recorded")
    else:
        print(f"  Live-stream demo    : NOT VIABLE ({det_fps_real:.1f} fps) — use pre-recorded playback")

if __name__ == "__main__":
    run()
