import os, tempfile, json
from db.manager import DatabaseManager
from rule_engine.models import ViolationEvent
from review.service import validate_transition
from notifications.dispatcher import NotificationDispatcher
from plate.validator import normalize_indian_plate,is_valid_indian_plate
from monitoring.anomaly import score_camera

def test_plate_validation():
    assert normalize_indian_plate('gj-01 ab 1234') == 'GJ01AB1234'
    assert is_valid_indian_plate('GJ01AB1234')
    assert not is_valid_indian_plate('INVALID')

def test_review_state_machine():
    assert validate_transition('needs_review','approved')
    assert validate_transition('approved','verified')
    assert not validate_transition('needs_review','verified')

def test_notification_disabled():
    r=NotificationDispatcher(False).send('email',status='verified',human_verified=True,message='x',email='a@b.com')
    assert not r.success

def test_db_review_and_timeline():
    with tempfile.TemporaryDirectory() as d:
        db=DatabaseManager(os.path.join(d,'t.db'))
        db.save_camera('c1')
        db.save_track_stub('t1','c1')
        e=ViolationEvent('e1','t1','c1','RED_LIGHT_VIOLATION',.9,.9,'needs_review',1000)
        db.save_violation_event(e)
        assert db.review_event('e1','approved','reviewer')['status']=='approved'
        assert db.review_event('e1','verified','reviewer')['status']=='verified'
        db.save_plate_observation('GJ01AB1234','c1','t1',1000,.95,23.0,72.0)
        assert len(db.get_vehicle_timeline('GJ-01 AB1234'))==1

def test_anomaly():
    a=score_camera('c1',frames_processed=1000,events_emitted=0,last_frame_age_ms=12000,error='x')
    assert a.score==1.0
