import sqlite3
import json
import uuid
import time
import random
from contextlib import contextmanager
from rule_engine.models import ViolationEvent
from evidence.models import EvidenceBundle

class _RetryCursor(sqlite3.Cursor):
    """Cursor that retries transient SQLite writer contention."""
    def _run(self, method, *args, **kwargs):
        last = None
        for attempt in range(6):
            try:
                return method(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                last = exc
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                time.sleep(min(0.8, 0.05 * (2 ** attempt)) + random.random() * 0.02)
        raise last

    def execute(self, *args, **kwargs):
        return self._run(super().execute, *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._run(super().executemany, *args, **kwargs)

class _RetryConnection(sqlite3.Connection):
    def cursor(self, factory=_RetryCursor):
        return super().cursor(factory)

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level="DEFERRED", factory=_RetryConnection)
        # WAL permits readers while a writer is active; busy_timeout + retry cursor
        # absorb short multi-camera contention instead of surfacing "database is locked".
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Camera table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Camera (
                    camera_id TEXT PRIMARY KEY,
                    location_lat REAL,
                    location_lng REAL,
                    calibration_json TEXT,
                    active BOOLEAN
                )
            ''')

            self._migrate_track_table_if_needed(cursor)
            
            # Track table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Track (
                    track_id TEXT,
                    camera_id TEXT,
                    vehicle_class TEXT,
                    color TEXT,
                    first_seen_ts REAL,
                    last_seen_ts REAL,
                    track_confidence REAL,
                    PRIMARY KEY (camera_id, track_id),
                    FOREIGN KEY (camera_id) REFERENCES Camera (camera_id)
                )
            ''')
            self._copy_legacy_tracks_if_present(cursor)

            # PlateRead intentionally does not declare a single-column Track FK: Track
            # uses the composite primary key (camera_id, track_id), so a track_id alone
            # is not globally unique. Referential integrity is enforced by application
            # writes using both camera_id and track_id.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS PlateRead (
                    plate_read_id TEXT PRIMARY KEY,
                    track_id TEXT,
                    plate_text_partial_or_full TEXT,
                    ocr_confidence REAL,
                    is_full_read BOOLEAN,
                    frame_ref TEXT
                )
            ''')

            # ViolationEvent table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ViolationEvent (
                    event_id TEXT PRIMARY KEY,
                    track_id TEXT,
                    camera_id TEXT,
                    violation_type TEXT,
                    rule_confidence REAL,
                    aggregated_confidence REAL,
                    status TEXT,
                    timestamp REAL,
                    evidence_bundle_ref TEXT,
                    FOREIGN KEY (camera_id) REFERENCES Camera (camera_id)
                )
            ''')

            # EvidenceBundle table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS EvidenceBundle (
                    bundle_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    image_paths TEXT,
                    clip_path TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY (event_id) REFERENCES ViolationEvent (event_id)
                )
            ''')
            
            # Alert table (simulated)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Alert (
                    alert_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    channel TEXT,
                    delivered_sim BOOLEAN,
                    FOREIGN KEY (event_id) REFERENCES ViolationEvent (event_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS CameraStatus (
                    camera_id TEXT PRIMARY KEY,
                    status TEXT,
                    frames_processed INTEGER,
                    events_emitted INTEGER,
                    last_frame_ts REAL,
                    last_error TEXT,
                    simulated BOOLEAN,
                    FOREIGN KEY (camera_id) REFERENCES Camera (camera_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS BlacklistPlate (
                    plate_text TEXT PRIMARY KEY,
                    reason TEXT,
                    severity TEXT,
                    min_confidence REAL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS AlertRouting (
                    route_key TEXT PRIMARY KEY,
                    channel TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS VehicleEmbedding (
                    embedding_id TEXT PRIMARY KEY,
                    camera_id TEXT,
                    track_id TEXT,
                    timestamp REAL,
                    vector_json TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS TrajectoryStitch (
                    stitch_id TEXT PRIMARY KEY,
                    from_embedding_id TEXT,
                    to_embedding_id TEXT,
                    similarity REAL,
                    created_ts REAL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ReviewDecision (
                    decision_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    note TEXT,
                    created_ts REAL NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES ViolationEvent (event_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS AuditLog (
                    audit_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    metadata_json TEXT,
                    created_ts REAL NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS NotificationLog (
                    notification_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    channel TEXT NOT NULL,
                    destination TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_ts REAL NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS VehicleObservation (
                    observation_id TEXT PRIMARY KEY,
                    plate_text TEXT,
                    camera_id TEXT NOT NULL,
                    track_id TEXT,
                    timestamp_ms REAL NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT 'camera'
                )
            ''')
            self._ensure_columns(cursor, "ViolationEvent", {
                "reviewed_by": "TEXT", "reviewed_ts": "REAL", "review_note": "TEXT",
                "verified_by": "TEXT", "verified_ts": "REAL"
            })
            self._ensure_columns(cursor, "EvidenceBundle", {"integrity_hash": "TEXT", "manifest_path": "TEXT"})

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_violation_camera_ts ON ViolationEvent (camera_id, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_violation_status ON ViolationEvent (status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_plate_track ON PlateRead (track_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_vehicle_observation_plate_ts ON VehicleObservation (plate_text, timestamp_ms)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_review_event ON ReviewDecision (event_id, created_ts)')
            
            conn.commit()

    def _ensure_columns(self, cursor, table: str, columns: dict):
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        for name, sql_type in columns.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")

    def _migrate_track_table_if_needed(self, cursor):
        cursor.execute("PRAGMA table_info(Track)")
        columns = cursor.fetchall()
        if not columns:
            return
        pk_columns = [column[1] for column in columns if column[5] > 0]
        if pk_columns != ["track_id"]:
            return

        backup_name = "Track_legacy_pre_v4"
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (backup_name,))
        if cursor.fetchone() is not None:
            backup_name = f"Track_legacy_pre_v4_{uuid.uuid4().hex[:8]}"
        self._legacy_track_table = backup_name
        cursor.execute(f"ALTER TABLE Track RENAME TO {backup_name}")

    def _copy_legacy_tracks_if_present(self, cursor):
        backup_name = getattr(self, "_legacy_track_table", "Track_legacy_pre_v4")
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (backup_name,))
        if cursor.fetchone() is None:
            return
        cursor.execute(f'''
            INSERT OR IGNORE INTO Track (
                camera_id, track_id, vehicle_class, color, first_seen_ts, last_seen_ts, track_confidence
            )
            SELECT camera_id, track_id, vehicle_class, color, first_seen_ts, last_seen_ts, track_confidence
            FROM {backup_name}
        ''')

    def save_camera(self, camera_id: str, active: bool = True):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO Camera (camera_id, active) VALUES (?, ?)",
                (camera_id, active)
            )
            conn.commit()

    def save_camera_calibration(self, camera_id: str, calibration: dict):
        self.save_camera(camera_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE Camera SET calibration_json = ? WHERE camera_id = ?",
                (json.dumps(calibration), camera_id)
            )
            conn.commit()

    def get_camera_calibration(self, camera_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT calibration_json FROM Camera WHERE camera_id = ?", (camera_id,))
            row = cursor.fetchone()
            if row is None or not row[0]:
                return {}
            return json.loads(row[0])

    def save_track_stub(self, track_id: str, camera_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO Track (camera_id, track_id, first_seen_ts, last_seen_ts) VALUES (?, ?, ?, ?)",
                (camera_id, track_id, time.time() * 1000.0, time.time() * 1000.0)
            )
            conn.commit()

    def save_violation_event(self, event: ViolationEvent):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ViolationEvent (
                    event_id, track_id, camera_id, violation_type, 
                    rule_confidence, aggregated_confidence, status, 
                    timestamp, evidence_bundle_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.event_id, event.track_id, event.camera_id, event.violation_type,
                event.rule_confidence, event.aggregated_confidence, event.status,
                event.timestamp_ms, event.evidence_bundle_ref
            ))
            conn.commit()

    def save_camera_status(self, health):
        self.save_camera(health.camera_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO CameraStatus (
                    camera_id, status, frames_processed, events_emitted, last_frame_ts, last_error, simulated
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                health.camera_id, health.status, health.frames_processed, health.events_emitted,
                health.last_frame_ts, health.last_error, health.simulated
            ))
            conn.commit()

    def get_violation_counts_by_camera(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT camera_id, violation_type, COUNT(*)
                FROM ViolationEvent
                GROUP BY camera_id, violation_type
            ''')
            counts = {}
            for camera_id, violation_type, count in cursor.fetchall():
                counts.setdefault(camera_id, {})[violation_type] = count
            return counts

    def get_review_queue(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT event_id, track_id, camera_id, violation_type, aggregated_confidence, timestamp, status
                FROM ViolationEvent
                WHERE status = 'needs_review'
                ORDER BY timestamp DESC
            ''')
            return [
                {
                    "event_id": row[0],
                    "track_id": row[1],
                    "camera_id": row[2],
                    "violation_type": row[3],
                    "aggregated_confidence": row[4],
                    "timestamp": row[5],
                    "status": row[6],
                }
                for row in cursor.fetchall()
            ]

    def save_blacklist_plate(self, plate_text: str, reason: str, severity: str = "high", min_confidence: float = 0.92):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO BlacklistPlate (plate_text, reason, severity, min_confidence)
                VALUES (?, ?, ?, ?)
            ''', (plate_text, reason, severity, min_confidence))
            conn.commit()

    def get_blacklist_entries(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT plate_text, reason, severity, min_confidence FROM BlacklistPlate')
            return {
                row[0]: {"reason": row[1], "severity": row[2], "min_confidence": row[3]}
                for row in cursor.fetchall()
            }

    def save_alert_route(self, route_key: str, channel: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO AlertRouting (route_key, channel) VALUES (?, ?)',
                (route_key, channel)
            )
            conn.commit()

    def get_alert_routes(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT route_key, channel FROM AlertRouting')
            return {route_key: channel for route_key, channel in cursor.fetchall()}

    def save_vehicle_embedding(self, embedding):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO VehicleEmbedding (
                    embedding_id, camera_id, track_id, timestamp, vector_json
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                embedding.embedding_id, embedding.camera_id, embedding.track_id,
                embedding.timestamp_ms, json.dumps(embedding.vector)
            ))
            conn.commit()

    def save_trajectory_match(self, match):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO TrajectoryStitch (
                    stitch_id, from_embedding_id, to_embedding_id, similarity, created_ts
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                f"stitch_{uuid.uuid4().hex[:10]}",
                match.from_embedding.embedding_id,
                match.to_embedding.embedding_id,
                match.similarity,
                time.time() * 1000.0,
            ))
            conn.commit()

    def save_evidence_bundle(self, bundle: EvidenceBundle):
        metadata = json.loads(bundle.metadata_json or "{}")
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO EvidenceBundle (
                    bundle_id, event_id, image_paths, clip_path, metadata_json, integrity_hash, manifest_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                bundle.bundle_id, bundle.event_id,
                json.dumps(bundle.image_paths), bundle.clip_path,
                bundle.metadata_json, metadata.get("integrity_sha256"), metadata.get("manifest_path")
            ))
            conn.commit()

    def get_violation(self, event_id: str):
        with self._get_connection() as conn:
            row = conn.execute("SELECT event_id, track_id, camera_id, violation_type, rule_confidence, aggregated_confidence, status, timestamp, evidence_bundle_ref, reviewed_by, reviewed_ts, review_note, verified_by, verified_ts FROM ViolationEvent WHERE event_id = ?", (event_id,)).fetchone()
            if not row: return None
            keys = ["event_id","track_id","camera_id","violation_type","rule_confidence","aggregated_confidence","status","timestamp","evidence_bundle_ref","reviewed_by","reviewed_ts","review_note","verified_by","verified_ts"]
            return dict(zip(keys,row))

    def review_event(self, event_id: str, new_status: str, reviewer: str, note: str = ""):
        from review.service import validate_transition
        current = self.get_violation(event_id)
        if not current: raise ValueError("Violation event not found")
        if not validate_transition(current["status"], new_status):
            raise ValueError(f"Invalid review transition: {current['status']} -> {new_status}")
        now=time.time()*1000.0
        with self._get_connection() as conn:
            conn.execute("UPDATE ViolationEvent SET status=?, reviewed_by=?, reviewed_ts=?, review_note=?, verified_by=?, verified_ts=? WHERE event_id=?", (new_status, reviewer, now, note, reviewer if new_status=="verified" else None, now if new_status=="verified" else None, event_id))
            conn.execute("INSERT INTO ReviewDecision VALUES (?,?,?,?,?,?,?)", (f"rev_{uuid.uuid4().hex[:12]}",event_id,reviewer,current["status"],new_status,note,now))
            conn.commit()
        return self.get_violation(event_id)

    def save_audit(self, subject: str, action: str, resource_type: str = "", resource_id: str = "", metadata: dict | None = None):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO AuditLog VALUES (?,?,?,?,?,?,?)", (f"aud_{uuid.uuid4().hex[:12]}",subject,action,resource_type,resource_id,json.dumps(metadata or {}),time.time()*1000.0))
            conn.commit()

    def save_notification_log(self, event_id: str, channel: str, destination: str, status: str, error: str = ""):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO NotificationLog VALUES (?,?,?,?,?,?,?)", (f"not_{uuid.uuid4().hex[:12]}",event_id,channel,destination,status,error,time.time()*1000.0))
            conn.commit()

    def save_plate_observation(self, plate_text: str | None, camera_id: str, track_id: str | None, timestamp_ms: float, confidence: float, latitude: float | None = None, longitude: float | None = None, source: str = "camera"):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO VehicleObservation VALUES (?,?,?,?,?,?,?,?,?)", (f"obs_{uuid.uuid4().hex[:12]}",plate_text,camera_id,track_id,timestamp_ms,latitude,longitude,confidence,source))
            conn.commit()

    def get_vehicle_timeline(self, plate_text: str, limit: int = 200):
        clean = ''.join(c for c in plate_text.upper() if c.isalnum())
        with self._get_connection() as conn:
            rows=conn.execute("SELECT observation_id,plate_text,camera_id,track_id,timestamp_ms,latitude,longitude,confidence,source FROM VehicleObservation WHERE REPLACE(REPLACE(UPPER(plate_text),' ',''),'-','')=? ORDER BY timestamp_ms ASC LIMIT ?", (clean,limit)).fetchall()
        keys=["observation_id","plate_text","camera_id","track_id","timestamp_ms","latitude","longitude","confidence","source"]
        return [dict(zip(keys,r)) for r in rows]

    def get_review_history(self, event_id: str):
        with self._get_connection() as conn:
            rows=conn.execute("SELECT decision_id,event_id,reviewer,old_status,new_status,note,created_ts FROM ReviewDecision WHERE event_id=? ORDER BY created_ts ASC",(event_id,)).fetchall()
        keys=["decision_id","event_id","reviewer","old_status","new_status","note","created_ts"]
        return [dict(zip(keys,r)) for r in rows]
