"""
Tests for the mandatory hardening constraints added mid-way through the
software-groundwork phases: engine-level critical-load protection, the
enriched automation audit trail, real-vs-simulated data provenance, the
command-status lifecycle, and the stale-sensor-never-means-empty rule.
"""
import datetime
import json

from app import models
from app.hardware import interfaces
from app.services import automation_engine, energy_service, mqtt_service


def _zone(db, name="Hardening Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _sensor(db, zone_id, occupied, last_seen=None, sensor_type="PIR"):
    sensor = models.Sensor(
        zone_id=zone_id, sensor_type=sensor_type, status="online",
        occupancy_state=occupied, last_seen=last_seen or datetime.datetime.utcnow(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def _device(db, zone_id, name, type_, criticality, status=False, current_power=None):
    device = models.Device(
        zone_id=zone_id, name=name, type=type_, criticality=criticality,
        status=status, current_power=current_power,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _closed_schedule(db, zone_id, verification_minutes=5):
    now = datetime.datetime.now()
    db.add(models.ZoneSchedule(
        zone_id=zone_id, day_of_week=None,
        open_time=(now - datetime.timedelta(hours=2)).time(),
        close_time=(now - datetime.timedelta(minutes=2)).time(),
        grace_minutes=0, verification_minutes=verification_minutes,
    ))
    db.commit()


# ---------------------------------------------------------------------------
# Constraint #3: critical-load protection lives in the engine
# ---------------------------------------------------------------------------
def test_critical_device_blocked_with_explicit_reason(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    server = _device(db_session, zone.zone_id, "Critical Server", "SERVER", "CRITICAL", status=True)
    light = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)

    automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(server)
    db_session.refresh(light)
    assert server.status is True  # never touched
    assert light.status is False  # non-critical still acted on

    log = db_session.query(models.AutomationLog).filter(models.AutomationLog.zone_id == zone.zone_id).first()
    blocked = json.loads(log.blocked_actions)
    assert len(blocked) == 1
    assert blocked[0]["device_id"] == server.device_id
    assert blocked[0]["reason"] == "Critical load protection"


def test_shutdown_non_critical_returns_changed_and_blocked_separately(db_session):
    zone = _zone(db_session)
    server = _device(db_session, zone.zone_id, "Server", "SERVER", "CRITICAL", status=True)
    light = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)
    db_session.refresh(zone)

    changed, blocked = automation_engine.shutdown_non_critical(db_session, zone)

    assert any(c["device_id"] == light.device_id for c in changed)
    assert any(b["device_id"] == server.device_id and b["reason"] == "Critical load protection" for b in blocked)


# ---------------------------------------------------------------------------
# Constraint #7: full decision audit trail
# ---------------------------------------------------------------------------
def test_automation_log_carries_full_audit_context(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False, sensor_type="MMWAVE")
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True, current_power=40)

    automation_engine.process_zone_once(db_session, zone)

    log = db_session.query(models.AutomationLog).filter(models.AutomationLog.zone_id == zone.zone_id).first()
    assert log.trigger == "CONFIRMED_EMPTY"
    assert log.confidence == 1.0
    assert log.requested_action == "SHUTDOWN_NON_CRITICAL"
    assert log.matched_rule_name is not None  # at minimum the fallback rule's name
    evidence = json.loads(log.evidence_snapshot)
    assert evidence[0]["source"] == "sensor_mmwave"


# ---------------------------------------------------------------------------
# Constraint #6: command status lifecycle
# ---------------------------------------------------------------------------
def test_turn_device_off_persists_command_status(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, "Server rack fan", "OTHER", "NON_CRITICAL", status=True)

    status = automation_engine._turn_device_off(db_session, device)

    # Tests run with DISABLE_MQTT=true (see conftest.py) — no broker client
    # ever connects, so every command in this suite honestly reports
    # COMMAND_FAILED rather than pretending to have dispatched anything.
    assert status == interfaces.COMMAND_FAILED
    assert device.last_command_status == interfaces.COMMAND_FAILED
    assert device.last_command_at is not None


# ---------------------------------------------------------------------------
# Final hardening pass, Phase 7 — a real command failure during automatic
# shutdown must raise a REAL, persisted Alert, not just an internal status
# field nobody surfaces.
# ---------------------------------------------------------------------------
def test_shutdown_command_failure_raises_alert(db_session):
    zone = _zone(db_session)
    _device(db_session, zone.zone_id, "Server rack fan", "OTHER", "NON_CRITICAL", status=True)

    # DISABLE_MQTT=true in tests (see conftest.py) — no broker connects, so
    # this command honestly reports COMMAND_FAILED, which must raise a
    # device_failed alert for this zone.
    automation_engine.shutdown_non_critical(db_session, zone)
    db_session.commit()

    alert = db_session.query(models.Alert).filter(
        models.Alert.zone_id == zone.zone_id, models.Alert.type == "device_failed", models.Alert.severity == "CRITICAL"
    ).first()
    assert alert is not None


def test_shutdown_failure_alert_not_duplicated_per_call(db_session):
    zone = _zone(db_session)
    _device(db_session, zone.zone_id, "Fan 1", "OTHER", "NON_CRITICAL", status=True)
    _device(db_session, zone.zone_id, "Fan 2", "OTHER", "NON_CRITICAL", status=True)

    automation_engine.shutdown_non_critical(db_session, zone)
    db_session.commit()

    count = db_session.query(models.Alert).filter(
        models.Alert.zone_id == zone.zone_id, models.Alert.type == "device_failed", models.Alert.resolved.is_(False)
    ).count()
    assert count == 1


def test_mqtt_state_message_marks_state_confirmed(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, "Freestanding", "SERVER", "NON_CRITICAL", status=False)
    # SERVER devices are usually CRITICAL, but criticality doesn't block a
    # real hardware ack from being recorded — it only blocks automation
    # from issuing the OFF command in the first place.

    class FakeMsg:
        def __init__(self, topic, payload):
            self.topic = topic
            self.payload = payload.encode()

    topic = f"university/aiu/building/1/zone/{zone.zone_id}/device/{device.device_id}/state"
    mqtt_service._on_message(None, None, FakeMsg(topic, json.dumps({"on": True, "current_power": 12.5})))

    db_session.refresh(device)
    assert device.status is True
    assert device.current_power == 12.5
    assert device.power_source == "REAL"
    assert device.last_command_status == "STATE_CONFIRMED"


# ---------------------------------------------------------------------------
# Constraint #2: real vs simulated provenance survives storage
# ---------------------------------------------------------------------------
def test_manual_sensor_reading_is_marked_simulated(db_session, client, admin_token):
    zone = _zone(db_session)
    sensor = _sensor(db_session, zone.zone_id, occupied=None)

    resp = client.post(
        f"/api/sensors/{sensor.sensor_id}/reading", json={"occupied": True, "reading": "motion"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data_source"] == "SIMULATED"


def test_energy_simulation_marks_device_power_source_simulated(db_session):
    door = models.Door(
        code="HARD-1", name="Hardening Room", building="Main", category="access_service",
        ac_enabled=True, ac_on=True,
    )
    db_session.add(door)
    db_session.commit()
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, "AC", "AC", "NON_CRITICAL")
    device.door_ref_id = door.door_id
    db_session.commit()

    energy_service.simulate_power_and_check_alerts_once(db_session)

    db_session.refresh(device)
    assert device.power_source == "SIMULATED"


# ---------------------------------------------------------------------------
# Constraint #5: stale sensor data must never read as EMPTY
# ---------------------------------------------------------------------------
def test_stale_sensor_produces_unknown_not_empty(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False,
            last_seen=datetime.datetime.utcnow() - datetime.timedelta(minutes=20))

    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)

    assert verdict == "UNKNOWN"
    assert verdict != "EMPTY"
    assert confidence == 0.0
