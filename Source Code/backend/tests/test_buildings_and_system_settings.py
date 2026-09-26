"""
Phase 9.1 Priority 2 — Buildings, System Settings, and Checkout Sweep, which
had zero automated coverage per the Phase 9 audit. Every mutation is
verified write -> commit -> fresh GET, never trusting the mutating
response alone.
"""
from app import models


def _admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------
def test_list_buildings_empty_by_default(client, admin_token):
    resp = client.get("/api/buildings", headers=_admin(admin_token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_building_persists(client, admin_token):
    resp = client.post("/api/buildings", json={"name": "Engineering Hall"}, headers=_admin(admin_token))
    assert resp.status_code == 201
    building_id = resp.json()["building_id"]

    # Fresh GET, not the create response.
    listed = client.get("/api/buildings", headers=_admin(admin_token))
    assert any(b["building_id"] == building_id and b["name"] == "Engineering Hall" for b in listed.json())


def test_create_building_empty_name_rejected(client, admin_token):
    resp = client.post("/api/buildings", json={"name": "   "}, headers=_admin(admin_token))
    assert resp.status_code == 400

    listed = client.get("/api/buildings", headers=_admin(admin_token))
    assert listed.json() == []


def test_create_building_duplicate_name_returns_existing_without_duplicating(client, admin_token):
    first = client.post("/api/buildings", json={"name": "Science Block"}, headers=_admin(admin_token))
    second = client.post("/api/buildings", json={"name": "Science Block"}, headers=_admin(admin_token))
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["building_id"] == second.json()["building_id"]

    listed = client.get("/api/buildings", headers=_admin(admin_token))
    assert len([b for b in listed.json() if b["name"] == "Science Block"]) == 1


def test_instructor_can_list_but_not_create_buildings(client, instructor_token):
    listed = client.get("/api/buildings", headers={"Authorization": f"Bearer {instructor_token}"})
    assert listed.status_code == 200

    created = client.post("/api/buildings", json={"name": "Should Fail"},
                           headers={"Authorization": f"Bearer {instructor_token}"})
    assert created.status_code == 403


def test_unauthenticated_cannot_list_or_create_buildings(client):
    assert client.get("/api/buildings").status_code == 401
    assert client.post("/api/buildings", json={"name": "X"}).status_code == 401


def test_delete_building_persists(client, admin_token):
    created = client.post("/api/buildings", json={"name": "Temp Hall"}, headers=_admin(admin_token)).json()
    resp = client.delete(f"/api/buildings/{created['building_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    listed = client.get("/api/buildings", headers=_admin(admin_token))
    assert all(b["building_id"] != created["building_id"] for b in listed.json())


def test_delete_nonexistent_building_404(client, admin_token):
    resp = client.delete("/api/buildings/999999", headers=_admin(admin_token))
    assert resp.status_code == 404


def test_instructor_cannot_delete_building(client, admin_token, instructor_token):
    created = client.post("/api/buildings", json={"name": "Protected Hall"}, headers=_admin(admin_token)).json()
    resp = client.delete(f"/api/buildings/{created['building_id']}",
                          headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403

    listed = client.get("/api/buildings", headers=_admin(admin_token))
    assert any(b["building_id"] == created["building_id"] for b in listed.json())


def test_delete_building_blocked_while_doors_reference_it(client, admin_token):
    """Door.building is a plain string, not a FK (see models.py) — so
    deletion must be blocked while any door still uses that name, rather
    than silently orphaning it."""
    building = client.post("/api/buildings", json={"name": "Occupied Hall"}, headers=_admin(admin_token)).json()
    door = client.post("/api/doors", json={
        "code": "OCC101", "name": "Room OCC101", "building": "Occupied Hall", "fail_mode": "secure",
    }, headers=_admin(admin_token))
    assert door.status_code == 201

    resp = client.delete(f"/api/buildings/{building['building_id']}", headers=_admin(admin_token))
    assert resp.status_code == 400
    assert "Occupied Hall" in resp.json()["detail"]

    # Still present after the blocked delete.
    listed = client.get("/api/buildings", headers=_admin(admin_token))
    assert any(b["building_id"] == building["building_id"] for b in listed.json())


# ---------------------------------------------------------------------------
# System settings (checkout time)
# ---------------------------------------------------------------------------
def test_get_system_settings_returns_default_when_unset(client, admin_token):
    from app.config import settings as app_settings
    resp = client.get("/api/system/settings", headers=_admin(admin_token))
    assert resp.status_code == 200
    assert resp.json()["checkout_time"] == app_settings.DEFAULT_CHECKOUT_TIME


def test_update_system_settings_persists(client, db_session, admin_token):
    resp = client.put("/api/system/settings", json={"checkout_time": "19:45"}, headers=_admin(admin_token))
    assert resp.status_code == 200
    assert resp.json()["checkout_time"] == "19:45"

    # Fresh GET, not the PUT response.
    got = client.get("/api/system/settings", headers=_admin(admin_token))
    assert got.json()["checkout_time"] == "19:45"

    # And directly at the DB layer.
    row = db_session.query(models.SystemSetting).filter(models.SystemSetting.key == "checkout_time").first()
    assert row.value == "19:45"


def test_update_system_settings_overwrites_previous_value(client, admin_token):
    client.put("/api/system/settings", json={"checkout_time": "18:00"}, headers=_admin(admin_token))
    client.put("/api/system/settings", json={"checkout_time": "20:30"}, headers=_admin(admin_token))
    got = client.get("/api/system/settings", headers=_admin(admin_token))
    assert got.json()["checkout_time"] == "20:30"


def test_update_system_settings_rejects_invalid_time_format(client, admin_token):
    resp = client.put("/api/system/settings", json={"checkout_time": "not-a-time"}, headers=_admin(admin_token))
    assert resp.status_code == 400

    # Unchanged — still the default.
    from app.config import settings as app_settings
    got = client.get("/api/system/settings", headers=_admin(admin_token))
    assert got.json()["checkout_time"] == app_settings.DEFAULT_CHECKOUT_TIME


def test_instructor_can_read_but_not_write_system_settings(client, instructor_token):
    got = client.get("/api/system/settings", headers={"Authorization": f"Bearer {instructor_token}"})
    assert got.status_code == 200

    put = client.put("/api/system/settings", json={"checkout_time": "17:00"},
                      headers={"Authorization": f"Bearer {instructor_token}"})
    assert put.status_code == 403


def test_unauthenticated_cannot_read_or_write_system_settings(client):
    assert client.get("/api/system/settings").status_code == 401
    assert client.put("/api/system/settings", json={"checkout_time": "17:00"}).status_code == 401


# ---------------------------------------------------------------------------
# Checkout sweep
# ---------------------------------------------------------------------------
def test_checkout_sweep_with_nothing_on_is_a_safe_no_op(client, admin_token):
    """No rooms at all (or none with anything running) — the sweep must
    complete successfully with an empty result, not error."""
    resp = client.post("/api/system/run-checkout-sweep", headers=_admin(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms_swept"] == 0
    assert body["door_codes"] == []
    assert "ran_at" in body


def test_checkout_sweep_turns_off_running_room_devices_and_persists(client, db_session, admin_token):
    door = client.post("/api/doors", json={
        "code": "SWEEP1", "name": "Room SWEEP1", "building": "Sweep Hall", "fail_mode": "secure",
        "category": "access_service", "ac_enabled": True, "light_enabled": True,
    }, headers=_admin(admin_token)).json()

    # Turn the AC and light on directly (mirrors what the real toggle
    # endpoints would do) so the sweep has something real to act on.
    door_row = db_session.query(models.Door).filter(models.Door.door_id == door["door_id"]).first()
    door_row.ac_on = True
    door_row.light_on = True
    db_session.commit()

    resp = client.post("/api/system/run-checkout-sweep", headers=_admin(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms_swept"] == 1
    assert "SWEEP1" in body["door_codes"]

    # Fresh query, not trusting the sweep response.
    db_session.refresh(door_row)
    assert door_row.ac_on is False
    assert door_row.light_on is False

    # A power reading should have been logged for the AC that was on.
    reading = db_session.query(models.PowerReading).filter(models.PowerReading.door_id == door["door_id"]).first()
    assert reading is not None


def test_checkout_sweep_ignores_main_doors_category(client, db_session, admin_token):
    """Only access_service (room) doors are swept — critical/main doors are
    deliberately excluded (see energy_service._rooms)."""
    door = client.post("/api/doors", json={
        "code": "MAIN1", "name": "Main Entrance", "building": "Main Hall", "fail_mode": "secure",
        "category": "critical",
    }, headers=_admin(admin_token)).json()
    door_row = db_session.query(models.Door).filter(models.Door.door_id == door["door_id"]).first()
    # Even if somehow flagged as "on", a critical door must never be touched.
    door_row.ac_on = True
    db_session.commit()

    resp = client.post("/api/system/run-checkout-sweep", headers=_admin(admin_token))
    assert resp.json()["rooms_swept"] == 0

    db_session.refresh(door_row)
    assert door_row.ac_on is True  # untouched


def test_instructor_cannot_run_checkout_sweep(client, instructor_token):
    resp = client.post("/api/system/run-checkout-sweep", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_unauthenticated_cannot_run_checkout_sweep(client):
    resp = client.post("/api/system/run-checkout-sweep")
    assert resp.status_code == 401
