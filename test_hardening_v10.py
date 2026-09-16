import os
import tempfile
import threading
import time

from security.auth import ApiKeyAuthorizer
from db.manager import DatabaseManager
from ingestion.multi_camera import CameraWorker
from ingestion.stream import CameraConfig, FrameEvent
from notifications.wawp import WawpNotifier


def test_all_roles_are_issuable():
    auth=ApiKeyAuthorizer({"op":"operator","rv":"reviewer","iv":"investigator","au":"auditor","ad":"admin"})
    assert auth.authenticate("rv").role=="reviewer"
    assert auth.authenticate("iv").role=="investigator"
    assert auth.authenticate("au").role=="auditor"
    assert auth.authenticate("ad").role=="admin"


def test_sqlite_wal_and_busy_timeout():
    with tempfile.TemporaryDirectory() as d:
        db=DatabaseManager(os.path.join(d,"traffic.db"))
        with db._get_connection() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower()=="wal"
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0]>=30000


def test_sqlite_concurrent_camera_writes():
    with tempfile.TemporaryDirectory() as d:
        db=DatabaseManager(os.path.join(d,"traffic.db"))
        errors=[]
        def worker(i):
            try:
                for j in range(20): db.save_camera(f"cam-{i}-{j}")
            except Exception as exc: errors.append(exc)
        threads=[threading.Thread(target=worker,args=(i,)) for i in range(5)]
        for t in threads:t.start()
        for t in threads:t.join()
        assert not errors


def test_wawp_normalizes_phone_and_has_official_default():
    n=WawpNotifier(instance_id="i",access_token="t")
    assert n.send_url=="https://api.wawp.net/v2/send/text"
    assert n._jid("+919898654707")=="919898654707@c.us"


def test_camera_reconnects_live_source():
    attempts=[]
    def factory(config):
        attempts.append(1)
        if len(attempts)==1:
            raise ConnectionError("simulated drop")
        yield FrameEvent(config.camera_id,1,1.0,__import__('numpy').zeros((2,2,3),dtype='uint8'))
    worker_ref={"worker":None}
    def processor(frame):
        worker_ref["worker"].stop()
        return []
    worker=CameraWorker(CameraConfig("cam","rtsp://example",15),processor,__import__('queue').Queue(),
                         stream_factory=factory,reconnect_enabled=True,max_retries=2,initial_backoff=0.01,max_backoff=0.02)
    worker_ref["worker"]=worker
    worker.start(); worker.join(1)
    assert len(attempts)>=2
    assert worker.health.frames_processed==1
