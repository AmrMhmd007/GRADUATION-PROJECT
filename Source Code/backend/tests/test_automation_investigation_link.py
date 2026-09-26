"""
Stage D / D8 — Failed automation -> Investigation linkage.

GET /api/automation/logs/{log_id}/related assembles the one REAL
relationship that exists between an AutomationLog decision and the rest of
the system: AutomationLog.zone_id -> Zone.door_id (only when an admin
explicitly linked that zone to a door) -> AccessEvent/Alert rows for that
door/zone. No new correlation is invented — a zone with no linked door
reports that honestly instead of guessing.
"""
import datetime
import json

from app import models, security


def _zone(db, name="Automation Zone", door_id=None):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN", door_id=door_id)
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _door(db, code="AUT101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _log(db, zone_id, decision="SHUTDOWN_SKIPPED_UNCERTAIN", created_at=None):
    log = models.AutomationLog(
        zone_id=zone_id, decision=decision, created_at=created_at or datetime.datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _event(db, door, at, result="granted"):
    e = models.AccessEvent(door_id=door.door_id, method="card", result=result, event_time=at)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def test_related_404_for_nonexistent_log(client, admin_token):
    resp = client.get("/api/automation/logs/999999/related", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_related_requires_admin(client, db_session):
    zone = _zone(db_session)
    log = _log(db_session, zone.zone_id)
    staff = models.User(name="Non Admin AUT", email="nonadmin.aut@example.edu", role="instructor",
                         password_hash=security.hash_password("pw123456"))
    db_session.add(staff)
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/automation/logs/{log.log_id}/related", headers=headers)
    assert resp.status_code == 403


def test_related_zone_with_no_door_reports_unavailable_honestly(client, admin_token, db_session):
    zone = _zone(db_session, name="Corridor With No Door")
    log = _log(db_session, zone.zone_id)
    resp = client.get(f"/api/automation/logs/{log.log_id}/related", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["door_available"] is False
    assert body["door_unavailable_reason"]
    assert body["related_access_events"] == []


def test_related_building_wide_log_reports_no_zone(client, admin_token, db_session):
    log = _log(db_session, zone_id=None)
    resp = client.get(f"/api/automation/logs/{log.log_id}/related", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone_id"] is None
    assert body["door_available"] is False


def test_related_zone_with_door_finds_nearby_access_events(client, admin_token, db_session):
    door = _door(db_session)
    zone = _zone(db_session, name="Linked Zone", door_id=door.door_id)
    log_time = datetime.datetime(2026, 9, 24, 18, 0)
    log = _log(db_session, zone.zone_id, created_at=log_time)
    # Inside the +/-30min window -> included.
    _event(db_session, door, at=log_time - datetime.timedelta(minutes=10))
    # Outside the window -> excluded.
    _event(db_session, door, at=log_time - datetime.timedelta(hours=5))

    resp = client.get(f"/api/automation/logs/{log.log_id}/related", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["door_available"] is True
    assert body["door_id"] == door.door_id
    assert len(body["related_access_events"]) == 1


def test_related_includes_zone_alerts(client, admin_token, db_session):
    zone = _zone(db_session, name="Zone With Alert")
    db_session.add(models.Alert(zone_id=zone.zone_id, type="device_failed", severity="CRITICAL"))
    db_session.commit()
    log = _log(db_session, zone.zone_id)

    resp = client.get(f"/api/automation/logs/{log.log_id}/related", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["alerts"]) == 1
    assert body["alerts"][0]["type"] == "device_failed"


# ---------------------------------------------------------------------------
# D14 #13 — no fake device health: the hardware-health endpoint must return
# exactly what's persisted (or nothing), never a synthesized "healthy" row.
# ---------------------------------------------------------------------------
def test_hardware_health_empty_when_no_node_has_ever_reported(client, admin_token):
    resp = client.get("/api/hardware-health", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_hardware_health_reports_real_persisted_status_only(client, admin_token, db_session):
    db_session.add(models.HardwareHealth(node_id="esp32-aut-1", status="DEGRADED", sensor_healthy=False,
                                          error_state="PIR read timeout"))
    db_session.commit()
    resp = client.get("/api/hardware-health", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "DEGRADED"
    assert body[0]["error_state"] == "PIR read timeout"
