"""
Unit tests for the MQTT message handler itself. There is no broker in this
environment, so these call _on_message() directly with a fake message
object rather than exercising the network path — see the Phase 3 README
for how to test this against a real broker.
"""
from app.services import mqtt_service
from app import models


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


def test_status_message_updates_door(db_session):
    mqtt_service._on_message(None, None, FakeMsg("site/A101/status", "online"))
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    assert door.online is True
    assert door.last_seen is not None


def test_event_message_resolves_known_credential(db_session):
    mqtt_service._on_message(
        None, None,
        FakeMsg("site/A101/event", '{"door_id":"A101","card_uid":"DEADBEEF","method":"card","result":"granted"}'),
    )
    event = db_session.query(models.AccessEvent).first()
    assert event is not None
    assert event.result == "granted"
    assert event.credential_id is not None  # matched DEADBEEF from the seeded fixture

    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    assert door.locked is False  # granted access should reflect as unlocked


def test_event_message_unknown_card_still_logs(db_session):
    mqtt_service._on_message(
        None, None,
        FakeMsg("site/A101/event", '{"door_id":"A101","card_uid":"NOTREAL","method":"card","result":"denied"}'),
    )
    event = db_session.query(models.AccessEvent).first()
    assert event.credential_id is None
    assert event.result == "denied"


def test_alert_message_creates_alert(db_session):
    mqtt_service._on_message(None, None, FakeMsg("site/A101/alert", '{"door_id":"A101","type":"tamper"}'))
    alert = db_session.query(models.Alert).first()
    assert alert is not None
    assert alert.type == "tamper"
    assert alert.resolved is False


def test_unknown_door_code_does_not_raise(db_session):
    # Should log a warning and return quietly, not throw — a malformed or
    # spoofed topic must never crash the ingestion thread.
    mqtt_service._on_message(None, None, FakeMsg("site/GHOST/status", "online"))
    assert db_session.query(models.Door).filter(models.Door.code == "GHOST").first() is None
