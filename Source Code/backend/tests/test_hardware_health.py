"""
Tests for Phase 5 (hardware node health/heartbeat tracking):
app/services/hardware_health_service.py, the HardwareHealth model, the
Phase 2 MQTT .../health topic wiring, and the /api/hardware-health endpoint.

The one behavior that matters most here, called out explicitly in
HardwareHealth's own docstring: none of this ever feeds an occupancy
verdict. A node going OFFLINE/DEGRADED is a maintenance signal, not a
"the room is empty" signal — sense_zone_occupancy achieves the latter
completely independently via Sensor.last_seen staleness (see
test_hardening_constraints.py's own stale-sensor test).
"""
import datetime
import json

from app import models
from app.services import hardware_health_service, mqtt_service


def _zone(db, name="Health Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


# ---------------------------------------------------------------------------
# record_heartbeat / sweep_once
# ---------------------------------------------------------------------------
def test_first_heartbeat_creates_node_online(db_session):
    zone = _zone(db_session)
    node = hardware_health_service.record_heartbeat(
        db_session, node_id="esp32-abc123", zone_id=zone.zone_id,
        payload={"firmware_version": "1.0.3", "uptime_seconds": 500, "rssi": -55, "mqtt_connected": True},
    )
    assert node.status == "ONLINE"
    assert node.firmware_version == "1.0.3"
    assert node.rssi == -55
    assert node.last_seen is not None


def test_heartbeat_with_reported_problem_is_degraded(db_session):
    node = hardware_health_service.record_heartbeat(
        db_session, node_id="esp32-bad", payload={"sensor_healthy": False, "error_state": "PIR read timeout"},
    )
    assert node.status == "DEGRADED"
    assert node.error_state == "PIR read timeout"


def test_repeated_heartbeat_updates_same_node_not_duplicate(db_session):
    hardware_health_service.record_heartbeat(db_session, node_id="esp32-dup", payload={"rssi": -40})
    hardware_health_service.record_heartbeat(db_session, node_id="esp32-dup", payload={"rssi": -60})
    rows = db_session.query(models.HardwareHealth).filter(models.HardwareHealth.node_id == "esp32-dup").all()
    assert len(rows) == 1
    assert rows[0].rssi == -60


def test_sweep_marks_stale_node_offline(db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "HARDWARE_HEALTH_STALE_AFTER_SECONDS", 60)
    node = hardware_health_service.record_heartbeat(db_session, node_id="esp32-stale", payload={})
    node.last_seen = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    db_session.commit()

    offline = hardware_health_service.sweep_once(db_session)

    assert "esp32-stale" in offline
    db_session.refresh(node)
    assert node.status == "OFFLINE"


def test_sweep_leaves_fresh_node_alone(db_session):
    hardware_health_service.record_heartbeat(db_session, node_id="esp32-fresh", payload={})
    offline = hardware_health_service.sweep_once(db_session)
    assert "esp32-fresh" not in offline


# ---------------------------------------------------------------------------
# Final hardening pass, Phase 7 — degraded/offline hardware transitions must
# produce a REAL, persisted Alert (device_failed), not just a status field
# nobody's alerted on.
# ---------------------------------------------------------------------------
def test_degraded_transition_creates_alert(db_session):
    zone = _zone(db_session, name="Degraded Zone")
    hardware_health_service.record_heartbeat(
        db_session, node_id="esp32-degraded", zone_id=zone.zone_id,
        payload={"error_state": "sensor_fault"},
    )
    alert = db_session.query(models.Alert).filter(
        models.Alert.zone_id == zone.zone_id, models.Alert.type == "device_failed"
    ).first()
    assert alert is not None
    assert alert.severity == "WARNING"


def test_repeated_degraded_heartbeats_do_not_duplicate_alert(db_session):
    zone = _zone(db_session, name="Degraded Zone 2")
    for _ in range(3):
        hardware_health_service.record_heartbeat(
            db_session, node_id="esp32-degraded2", zone_id=zone.zone_id,
            payload={"error_state": "sensor_fault"},
        )
    count = db_session.query(models.Alert).filter(
        models.Alert.zone_id == zone.zone_id, models.Alert.type == "device_failed", models.Alert.resolved.is_(False)
    ).count()
    assert count == 1


def test_sweep_offline_transition_creates_critical_alert(db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "HARDWARE_HEALTH_STALE_AFTER_SECONDS", 60)
    zone = _zone(db_session, name="Offline Zone")
    node = hardware_health_service.record_heartbeat(db_session, node_id="esp32-offline", zone_id=zone.zone_id, payload={})
    node.last_seen = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    db_session.commit()

    hardware_health_service.sweep_once(db_session)

    alert = db_session.query(models.Alert).filter(
        models.Alert.zone_id == zone.zone_id, models.Alert.type == "device_failed", models.Alert.severity == "CRITICAL"
    ).first()
    assert alert is not None


# ---------------------------------------------------------------------------
# MQTT wiring
# ---------------------------------------------------------------------------
def test_health_topic_persists_via_mqtt(db_session):
    zone = _zone(db_session)
    topic = f"university/aiu/building/1/zone/{zone.zone_id}/health"
    payload = json.dumps({"node_id": "esp32-mqtt-1", "uptime_seconds": 300, "rssi": -50})

    mqtt_service._on_message(None, None, FakeMsg(topic, payload))

    node = db_session.query(models.HardwareHealth).filter(models.HardwareHealth.node_id == "esp32-mqtt-1").first()
    assert node is not None
    assert node.zone_id == zone.zone_id
    assert node.status == "ONLINE"


def test_health_topic_without_node_id_uses_synthetic_id_not_crash(db_session):
    zone = _zone(db_session)
    topic = f"university/aiu/building/1/zone/{zone.zone_id}/health"
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"rssi": -70})))

    node = db_session.query(models.HardwareHealth).filter(
        models.HardwareHealth.zone_id == zone.zone_id
    ).first()
    assert node is not None
    assert "unnamed-node" in node.node_id


# ---------------------------------------------------------------------------
# Fail-safe: health status never feeds occupancy
# ---------------------------------------------------------------------------
def test_offline_node_does_not_change_occupancy_verdict(db_session):
    from app.services import automation_engine

    zone = _zone(db_session)
    sensor = models.Sensor(
        zone_id=zone.zone_id, sensor_type="PIR", status="online",
        occupancy_state=True, last_seen=datetime.datetime.utcnow(),
    )
    db_session.add(sensor)
    db_session.commit()

    node = hardware_health_service.record_heartbeat(db_session, node_id="esp32-x", zone_id=zone.zone_id, payload={})
    node.status = "OFFLINE"
    db_session.commit()

    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)
    assert verdict == "OCCUPIED"  # the fresh sensor reading still governs — health status is irrelevant here


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_list_hardware_health_endpoint(db_session, client, admin_token):
    zone = _zone(db_session)
    hardware_health_service.record_heartbeat(db_session, node_id="esp32-api", zone_id=zone.zone_id, payload={})

    resp = client.get("/api/hardware-health", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert any(n["node_id"] == "esp32-api" for n in resp.json())
