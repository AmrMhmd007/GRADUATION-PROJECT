"""
Phase 9.1 Priority 3 — Zone/Sensor/Device CRUD endpoints, tested directly
(not just as setup fixtures for automation-engine tests, which is all the
existing suite exercised per the Phase 9 audit). Every mutation is verified
write -> commit -> fresh GET/query.
"""
from app import models


def _admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
def test_create_zone_persists(client, admin_token):
    resp = client.post("/api/zones", json={"name": "Lab 204", "zone_type": "LAB"}, headers=_admin(admin_token))
    assert resp.status_code == 201
    zone_id = resp.json()["zone_id"]

    got = client.get(f"/api/zones/{zone_id}", headers=_admin(admin_token))
    assert got.status_code == 200
    assert got.json()["name"] == "Lab 204"
    assert got.json()["zone_type"] == "LAB"
    assert got.json()["occupancy_state"] == "UNKNOWN"


def test_create_zone_invalid_zone_type_rejected(client, admin_token):
    resp = client.post("/api/zones", json={"name": "Bad Zone", "zone_type": "NOT_A_TYPE"}, headers=_admin(admin_token))
    assert resp.status_code == 400

    listed = client.get("/api/zones", headers=_admin(admin_token))
    assert all(z["name"] != "Bad Zone" for z in listed.json())


def test_create_zone_with_door_already_linked_rejected(client, admin_token):
    door = client.post("/api/doors", json={
        "code": "ZDOOR1", "name": "Room ZDOOR1", "building": "Zone Hall", "fail_mode": "secure",
    }, headers=_admin(admin_token)).json()
    first = client.post("/api/zones", json={"name": "Zone A", "door_id": door["door_id"]}, headers=_admin(admin_token))
    assert first.status_code == 201

    second = client.post("/api/zones", json={"name": "Zone B", "door_id": door["door_id"]}, headers=_admin(admin_token))
    assert second.status_code == 409


def test_create_zone_unknown_door_404(client, admin_token):
    resp = client.post("/api/zones", json={"name": "Zone C", "door_id": 999999}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_update_zone_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Corridor 1", "zone_type": "CORRIDOR"}, headers=_admin(admin_token)).json()
    upd = client.put(f"/api/zones/{zone['zone_id']}", json={"name": "Corridor 1 Renamed", "floor": "2"}, headers=_admin(admin_token))
    assert upd.status_code == 200

    got = client.get(f"/api/zones/{zone['zone_id']}", headers=_admin(admin_token))
    assert got.json()["name"] == "Corridor 1 Renamed"
    assert got.json()["floor"] == "2"


def test_update_zone_door_conflict_rejected(client, admin_token):
    door1 = client.post("/api/doors", json={"code": "ZDOOR2", "name": "R2", "building": "B", "fail_mode": "secure"}, headers=_admin(admin_token)).json()
    door2 = client.post("/api/doors", json={"code": "ZDOOR3", "name": "R3", "building": "B", "fail_mode": "secure"}, headers=_admin(admin_token)).json()
    client.post("/api/zones", json={"name": "Zone D", "door_id": door1["door_id"]}, headers=_admin(admin_token))
    zone_e = client.post("/api/zones", json={"name": "Zone E", "door_id": door2["door_id"]}, headers=_admin(admin_token)).json()

    resp = client.put(f"/api/zones/{zone_e['zone_id']}", json={"door_id": door1["door_id"]}, headers=_admin(admin_token))
    assert resp.status_code == 409

    # Zone E's own door_id must be untouched by the rejected update.
    got = client.get(f"/api/zones/{zone_e['zone_id']}", headers=_admin(admin_token))
    assert got.json()["door_id"] == door2["door_id"]


def test_update_nonexistent_zone_404(client, admin_token):
    resp = client.put("/api/zones/999999", json={"name": "X"}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_delete_zone_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Temp Zone"}, headers=_admin(admin_token)).json()
    resp = client.delete(f"/api/zones/{zone['zone_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    got = client.get(f"/api/zones/{zone['zone_id']}", headers=_admin(admin_token))
    assert got.status_code == 404


def test_delete_zone_cascades_sensors_and_devices(client, db_session, admin_token):
    """Zone.sensors/devices are cascade="all, delete-orphan" relationships
    (models.py) — deleting the zone must remove its sensors/devices too,
    rather than leaving them orphaned."""
    zone = client.post("/api/zones", json={"name": "Zone With Gear"}, headers=_admin(admin_token)).json()
    sensor = client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "PIR"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "Light 1", "type": "LIGHT"}, headers=_admin(admin_token)).json()

    resp = client.delete(f"/api/zones/{zone['zone_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    assert db_session.query(models.Sensor).filter(models.Sensor.sensor_id == sensor["sensor_id"]).first() is None
    assert db_session.query(models.Device).filter(models.Device.device_id == device["device_id"]).first() is None


def test_delete_nonexistent_zone_404(client, admin_token):
    resp = client.delete("/api/zones/999999", headers=_admin(admin_token))
    assert resp.status_code == 404


def test_instructor_cannot_mutate_zones(client, admin_token, instructor_token):
    headers = {"Authorization": f"Bearer {instructor_token}"}
    assert client.post("/api/zones", json={"name": "X"}, headers=headers).status_code == 403

    zone = client.post("/api/zones", json={"name": "Y"}, headers=_admin(admin_token)).json()
    assert client.put(f"/api/zones/{zone['zone_id']}", json={"name": "Z"}, headers=headers).status_code == 403
    assert client.delete(f"/api/zones/{zone['zone_id']}", headers=headers).status_code == 403

    # Untouched by the rejected attempts.
    got = client.get(f"/api/zones/{zone['zone_id']}", headers=_admin(admin_token))
    assert got.status_code == 200
    assert got.json()["name"] == "Y"


def test_unauthenticated_cannot_mutate_zones(client):
    assert client.post("/api/zones", json={"name": "X"}).status_code == 401


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------
def test_create_sensor_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Sensor Zone"}, headers=_admin(admin_token)).json()
    resp = client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "MMWAVE"}, headers=_admin(admin_token))
    assert resp.status_code == 201
    sensor_id = resp.json()["sensor_id"]
    assert resp.json()["status"] == "offline"

    got = client.get(f"/api/zones/{zone['zone_id']}/sensors", headers=_admin(admin_token))
    assert any(s["sensor_id"] == sensor_id and s["sensor_type"] == "MMWAVE" for s in got.json())


def test_create_sensor_invalid_type_rejected(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Sensor Zone 2"}, headers=_admin(admin_token)).json()
    resp = client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "NOT_REAL"}, headers=_admin(admin_token))
    assert resp.status_code == 400

    got = client.get(f"/api/zones/{zone['zone_id']}/sensors", headers=_admin(admin_token))
    assert got.json() == []


def test_create_sensor_unknown_zone_404(client, admin_token):
    resp = client.post("/api/zones/999999/sensors", json={"sensor_type": "PIR"}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_delete_sensor_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Sensor Zone 3"}, headers=_admin(admin_token)).json()
    sensor = client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "PIR"}, headers=_admin(admin_token)).json()

    resp = client.delete(f"/api/sensors/{sensor['sensor_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    got = client.get(f"/api/zones/{zone['zone_id']}/sensors", headers=_admin(admin_token))
    assert got.json() == []


def test_delete_nonexistent_sensor_404(client, admin_token):
    resp = client.delete("/api/sensors/999999", headers=_admin(admin_token))
    assert resp.status_code == 404


def test_instructor_cannot_create_or_delete_sensors(client, admin_token, instructor_token):
    zone = client.post("/api/zones", json={"name": "Sensor Zone 4"}, headers=_admin(admin_token)).json()
    headers = {"Authorization": f"Bearer {instructor_token}"}
    assert client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "PIR"}, headers=headers).status_code == 403

    sensor = client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "PIR"}, headers=_admin(admin_token)).json()
    assert client.delete(f"/api/sensors/{sensor['sensor_id']}", headers=headers).status_code == 403

    got = client.get(f"/api/zones/{zone['zone_id']}/sensors", headers=_admin(admin_token))
    assert len(got.json()) == 1  # unaffected by the rejected delete


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
def test_create_device_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone"}, headers=_admin(admin_token)).json()
    resp = client.post(f"/api/zones/{zone['zone_id']}/devices", json={
        "name": "Overhead Light", "type": "LIGHT", "criticality": "NON_CRITICAL", "rated_power": 40.0,
    }, headers=_admin(admin_token))
    assert resp.status_code == 201
    device_id = resp.json()["device_id"]

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    row = next(d for d in got.json() if d["device_id"] == device_id)
    assert row["name"] == "Overhead Light"
    assert row["rated_power"] == 40.0


def test_create_device_invalid_type_rejected(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 2"}, headers=_admin(admin_token)).json()
    resp = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "X", "type": "NOT_A_TYPE"}, headers=_admin(admin_token))
    assert resp.status_code == 400
    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    assert got.json() == []


def test_create_device_invalid_criticality_rejected(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 3"}, headers=_admin(admin_token)).json()
    resp = client.post(f"/api/zones/{zone['zone_id']}/devices", json={
        "name": "X", "type": "LIGHT", "criticality": "SORT_OF_IMPORTANT",
    }, headers=_admin(admin_token))
    assert resp.status_code == 400


def test_create_device_unknown_zone_404(client, admin_token):
    resp = client.post("/api/zones/999999/devices", json={"name": "X", "type": "LIGHT"}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_update_device_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 4"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "Fan", "type": "OTHER"}, headers=_admin(admin_token)).json()

    resp = client.put(f"/api/devices/{device['device_id']}", json={"name": "Ceiling Fan", "rated_power": 75.0}, headers=_admin(admin_token))
    assert resp.status_code == 200

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    row = next(d for d in got.json() if d["device_id"] == device["device_id"])
    assert row["name"] == "Ceiling Fan"
    assert row["rated_power"] == 75.0


def test_update_device_invalid_criticality_rejected(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 5"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "Heater", "type": "OTHER"}, headers=_admin(admin_token)).json()

    resp = client.put(f"/api/devices/{device['device_id']}", json={"criticality": "MAYBE"}, headers=_admin(admin_token))
    assert resp.status_code == 400

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    row = next(d for d in got.json() if d["device_id"] == device["device_id"])
    assert row["criticality"] == "NON_CRITICAL"  # untouched (schema default)


def test_update_nonexistent_device_404(client, admin_token):
    resp = client.put("/api/devices/999999", json={"name": "X"}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_set_device_status_persists_for_standalone_device(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 6"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={
        "name": "Lab Equipment 1", "type": "LAB_EQUIPMENT", "controllable": True,
    }, headers=_admin(admin_token)).json()

    resp = client.post(f"/api/devices/{device['device_id']}/status", json={"status": True}, headers=_admin(admin_token))
    assert resp.status_code == 200
    assert resp.json()["status"] is True

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    row = next(d for d in got.json() if d["device_id"] == device["device_id"])
    assert row["status"] is True


def test_set_device_status_rejected_when_not_controllable(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 7"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={
        "name": "Fixed Device", "type": "OTHER", "controllable": False,
    }, headers=_admin(admin_token)).json()

    resp = client.post(f"/api/devices/{device['device_id']}/status", json={"status": True}, headers=_admin(admin_token))
    assert resp.status_code == 400

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    row = next(d for d in got.json() if d["device_id"] == device["device_id"])
    assert row["status"] is False  # unchanged


def test_set_device_status_rejected_when_mirrors_door_or_plug(client, admin_token):
    """A device with door_ref_id/plug_ref_id must be controlled through the
    door/plug endpoints instead — this endpoint must refuse and not touch it."""
    door = client.post("/api/doors", json={
        "code": "DEVDOOR1", "name": "Room DEVDOOR1", "building": "B", "fail_mode": "secure",
    }, headers=_admin(admin_token)).json()
    zone = client.post("/api/zones", json={"name": "Device Zone 8"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={
        "name": "Mirrored AC", "type": "AC", "door_ref_id": door["door_id"],
    }, headers=_admin(admin_token)).json()

    resp = client.post(f"/api/devices/{device['device_id']}/status", json={"status": True}, headers=_admin(admin_token))
    assert resp.status_code == 400


def test_delete_device_persists(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 9"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "Temp Device", "type": "OTHER"}, headers=_admin(admin_token)).json()

    resp = client.delete(f"/api/devices/{device['device_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    assert got.json() == []


def test_delete_nonexistent_device_404(client, admin_token):
    resp = client.delete("/api/devices/999999", headers=_admin(admin_token))
    assert resp.status_code == 404


def test_instructor_cannot_mutate_devices(client, admin_token, instructor_token):
    zone = client.post("/api/zones", json={"name": "Device Zone 10"}, headers=_admin(admin_token)).json()
    headers = {"Authorization": f"Bearer {instructor_token}"}
    assert client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "X", "type": "LIGHT"}, headers=headers).status_code == 403

    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "Y", "type": "LIGHT"}, headers=_admin(admin_token)).json()
    assert client.put(f"/api/devices/{device['device_id']}", json={"name": "Z"}, headers=headers).status_code == 403
    assert client.post(f"/api/devices/{device['device_id']}/status", json={"status": True}, headers=headers).status_code == 403
    assert client.delete(f"/api/devices/{device['device_id']}", headers=headers).status_code == 403

    got = client.get(f"/api/zones/{zone['zone_id']}/devices", headers=_admin(admin_token))
    assert len(got.json()) == 1
    assert got.json()[0]["name"] == "Y"  # untouched by every rejected mutation
