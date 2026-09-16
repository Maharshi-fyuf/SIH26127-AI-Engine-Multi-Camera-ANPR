import html
import json
from dataclasses import asdict, dataclass
from typing import Dict, List

from ingestion.multi_camera import CameraHealth


@dataclass
class DashboardSnapshot:
    camera_health: Dict[str, Dict]
    violation_counts: Dict[str, Dict[str, int]]
    review_queue: List[Dict]


class ControlRoomDashboard:
    """Read-only control-room view model with push-friendly serialization."""

    def __init__(self, db_manager):
        self.db = db_manager

    def snapshot(self, health: Dict[str, CameraHealth]) -> DashboardSnapshot:
        return DashboardSnapshot(
            camera_health={camera_id: asdict(status) for camera_id, status in health.items()},
            violation_counts=self.db.get_violation_counts_by_camera(),
            review_queue=self.db.get_review_queue(),
        )

    def snapshot_json(self, health: Dict[str, CameraHealth]) -> str:
        return json.dumps(asdict(self.snapshot(health)), sort_keys=True)

    def sse_event(self, health: Dict[str, CameraHealth], event_name: str = "dashboard") -> str:
        return f"event: {event_name}\ndata: {self.snapshot_json(health)}\n\n"

    def render_html(self, health: Dict[str, CameraHealth]) -> str:
        snapshot = self.snapshot(health)
        cards = []
        camera_ids = sorted(set(snapshot.camera_health) | set(snapshot.violation_counts))
        for camera_id in camera_ids:
            camera = snapshot.camera_health.get(
                camera_id,
                {
                    "status": "offline",
                    "simulated": False,
                    "frames_processed": 0,
                    "events_emitted": 0,
                },
            )
            counts = snapshot.violation_counts.get(camera_id, {})
            status = html.escape(camera["status"])
            label = "Simulated" if camera.get("simulated") else "Live"
            count_text = ", ".join(f"{html.escape(k)}: {v}" for k, v in sorted(counts.items())) or "No violations"
            cards.append(
                "<section class='tile'>"
                f"<h2>{html.escape(camera_id)}</h2>"
                f"<p class='status'>{status} &middot; {label}</p>"
                f"<p>{html.escape(count_text)}</p>"
                f"<p>{camera['frames_processed']} frames &middot; {camera['events_emitted']} events</p>"
                "</section>"
            )

        queue_rows = []
        for item in snapshot.review_queue:
            queue_rows.append(
                "<tr>"
                f"<td>{html.escape(item['camera_id'])}</td>"
                f"<td>{html.escape(item['track_id'])}</td>"
                f"<td>{html.escape(item['violation_type'])}</td>"
                f"<td>{item['aggregated_confidence']:.2f}</td>"
                "</tr>"
            )

        return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Traffic Control Room</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f4f7f9; color: #14202b; }
    header { padding: 24px; background: #102a43; color: white; }
    main { padding: 24px; display: grid; gap: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .tile { background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 16px; }
    h1, h2 { margin: 0 0 8px; }
    .status { color: #486581; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; background: white; }
    th, td { padding: 10px; border-bottom: 1px solid #d9e2ec; text-align: left; }
  </style>
</head>
<body>
  <header><h1>Traffic Control Room</h1></header>
  <main>
    <div class="grid">""" + "".join(cards) + """</div>
    <section>
      <h2>Review Queue</h2>
      <table>
        <thead><tr><th>Camera</th><th>Track</th><th>Violation</th><th>Confidence</th></tr></thead>
        <tbody>""" + "".join(queue_rows) + """</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
