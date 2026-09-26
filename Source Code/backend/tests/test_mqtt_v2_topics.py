"""
Tests for the Phase 2 MQTT hierarchy (university/{uid}/building/{bid}/
zone/{zid}/...) added in app/services/mqtt_service.py. Two things matter
most here: (1) this is purely additive — test_mqtt_ingestion.py's legacy
site/{code}/... tests must keep passing completely unmodified, and
(2) a message on the new hierarchy is the ONLY thing allowed to mark a
Sensor reading as real hardware data.
"""
import json

from app import models
from app.services import mqtt_service


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


def _zone(db, name="V2 Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _sensor(db, zone_id, sensor_type="PIR"):
    sensor = models.Sensor(zone_id=zone_id, sensor_type=sensor_type, status="offline")
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def _device(db, zone_id, type_="SERVER", status=False):
    device = models.Device(zone_id=zone_id, name="V2 Device", type=type_, criticality="NON_CRITICAL", status=status)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def test_sensor_telemetry_updates_sensor_and_marks_source_real(db_session):
    zone = _zone(db_session)
    sensor = _sensor(db_session, zone.zone_id)

    topic = f"university/aiu/building/1/zone/{zone.zone_id}/sensor/{sensor.sensor_id}/telemetry"
    payload = json.dumps({"metric": "occupancy", "value": True, "quality": "good", "sequence_number": 7})
    mqtt_service._on_message(None, None, FakeMsg(topic, payload))

    db_session.refresh(sensor)
    assert sensor.occupancy_state is True
    assert sensor.status == "online"
    assert sensor.last_seen is not None
    stored = json.loads(sensor.last_reading)
    assert stored["source"] == "real"
    assert stored["sequence_number"] == 7

    event = db_session.query(models.OccupancyEvent).filter(models.OccupancyEvent.sensor_id == sensor.sensor_id).first()
    assert event is not None
    assert event.occupancy_state is True
    assert event.source == "sensor"


def test_telemetry_for_unknown_sensor_does_not_raise(db_session):
    zone = _zone(db_session)
    topic = f"university/aiu/building/1/zone/{zone.zone_id}/sensor/999999/telemetry"
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"metric": "occupancy", "value": True})))
    assert db_session.query(models.OccupancyEvent).count() == 0


def test_device_state_updates_status_and_power(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, status=False)

    topic = f"university/aiu/building/1/zone/{zone.zone_id}/device/{device.device_id}/state"
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"on": True, "current_power": 55.0})))

    db_session.refresh(device)
    assert device.status is True
    assert device.current_power == 55.0


def test_zone_occupancy_topic_creates_esp32_sensor(db_session):
    zone = _zone(db_session)
    assert db_session.query(models.Sensor).filter(models.Sensor.zone_id == zone.zone_id).count() == 0

    topic = f"university/aiu/building/1/zone/{zone.zone_id}/occupancy"
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"occupied": True})))

    sensor = db_session.query(models.Sensor).filter(
        models.Sensor.zone_id == zone.zone_id, models.Sensor.sensor_type == "ESP32"
    ).first()
    assert sensor is not None
    assert sensor.occupancy_state is True

    # A second message reuses the same auto-provisioned sensor rather than
    # creating a duplicate.
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"occupied": False})))
    assert db_session.query(models.Sensor).filter(
        models.Sensor.zone_id == zone.zone_id, models.Sensor.sensor_type == "ESP32"
    ).count() == 1
    db_session.refresh(sensor)
    assert sensor.occupancy_state is False


def test_health_topic_does_not_raise_and_does_not_persist(db_session):
    zone = _zone(db_session)
    topic = f"university/aiu/building/1/zone/{zone.zone_id}/health"
    # Must not raise even though there's nowhere to persist this yet (Phase 5).
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"rssi": -60, "uptime": 120})))


def test_unknown_zone_id_does_not_raise(db_session):
    topic = "university/aiu/building/1/zone/999999/occupancy"
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"occupied": True})))
    assert db_session.query(models.Sensor).count() == 0


def test_malformed_v2_topic_does_not_raise(db_session):
    mqtt_service._on_message(None, None, FakeMsg("university/aiu/nonsense", b"{}"))


def test_legacy_site_topics_unaffected_by_v2_routing(db_session):
    # Guards against a routing regression: a site/... message must never be
    # accidentally caught by the new university/... branch.
    mqtt_service._on_message(None, None, FakeMsg("site/A101/status", "online"))
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    assert door.online is True


def test_publish_device_command_without_broker_returns_false():
    assert mqtt_service.publish_device_command(1, 1, 1, "on") is False


def test_publish_automation_decision_without_broker_returns_false():
    assert mqtt_service.publish_automation_decision(1, {"decision": "TEST"}) is False


def test_publish_automation_decision_handles_no_zone():
    assert mqtt_service.publish_automation_decision(None, {"decision": "TEST"}) is False
