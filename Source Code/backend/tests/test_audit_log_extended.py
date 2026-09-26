"""
Phase 11 Priority 1 — extended AuditLog coverage. Confirms the
audit_service.log() calls newly added to Zone/Sensor/Device/AutomationRule
CRUD, Building mutations, System Settings mutations, and Password Reset
admin mutations actually produce real rows with the same
actor/action/resource/result semantics as every other audited action
(see test_audit_log.py for the original coverage this extends).

This does NOT claim every mutation in the system is audited — only the
ones explicitly listed for this pass. See PHASE_11 report for what
remains unaudited (e.g. zone-schedules, checkout sweep).
"""
from app import models


def _admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _rows(client, admin_token, resource_type=None):
    params = {"resource_type": resource_type} if resource_type else {}
    resp = client.get("/api/audit-logs", params=params, headers=_admin(admin_token))
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Zone CRUD
# ---------------------------------------------------------------------------
def test_zone_create_update_delete_logged(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Audit Zone"}, headers=_admin(admin_token)).json()
    client.put(f"/api/zones/{zone['zone_id']}", json={"name": "Audit Zone Renamed"}, headers=_admin(admin_token))
    client.delete(f"/api/zones/{zone['zone_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "zone")
    assert any(r["action"] == "create" and r["resource_id"] == zone["zone_id"] and r["result"] == "success" for r in rows)
    assert any(r["action"] == "update" and r["resource_id"] == zone["zone_id"] for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == zone["zone_id"] for r in rows)


# ---------------------------------------------------------------------------
# Sensor CRUD
# ---------------------------------------------------------------------------
def test_sensor_create_delete_logged(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Sensor Audit Zone"}, headers=_admin(admin_token)).json()
    sensor = client.post(f"/api/zones/{zone['zone_id']}/sensors", json={"sensor_type": "PIR"}, headers=_admin(admin_token)).json()
    client.delete(f"/api/sensors/{sensor['sensor_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "sensor")
    assert any(r["action"] == "create" and r["resource_id"] == sensor["sensor_id"] for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == sensor["sensor_id"] for r in rows)


# ---------------------------------------------------------------------------
# Device CRUD
# ---------------------------------------------------------------------------
def test_device_create_update_delete_logged(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Device Audit Zone"}, headers=_admin(admin_token)).json()
    device = client.post(f"/api/zones/{zone['zone_id']}/devices", json={"name": "Audit Light", "type": "LIGHT"}, headers=_admin(admin_token)).json()
    client.put(f"/api/devices/{device['device_id']}", json={"name": "Audit Light Renamed"}, headers=_admin(admin_token))
    client.delete(f"/api/devices/{device['device_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "device")
    assert any(r["action"] == "create" and r["resource_id"] == device["device_id"] for r in rows)
    assert any(r["action"] == "update" and r["resource_id"] == device["device_id"] for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == device["device_id"] for r in rows)


# ---------------------------------------------------------------------------
# AutomationRule CRUD
# ---------------------------------------------------------------------------
def test_automation_rule_create_update_delete_logged(client, admin_token):
    rule = client.post("/api/automation/rules", json={
        "name": "Audit Rule", "conditions": {"trigger": "CONFIRMED_EMPTY"}, "actions": {"action": "SHUTDOWN_NON_CRITICAL"},
    }, headers=_admin(admin_token)).json()
    client.put(f"/api/automation/rules/{rule['rule_id']}", json={"enabled": False}, headers=_admin(admin_token))
    client.delete(f"/api/automation/rules/{rule['rule_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "automation_rule")
    assert any(r["action"] == "create" and r["resource_id"] == rule["rule_id"] for r in rows)
    assert any(r["action"] == "update" and r["resource_id"] == rule["rule_id"] for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == rule["rule_id"] for r in rows)


# ---------------------------------------------------------------------------
# Building mutations
# ---------------------------------------------------------------------------
def test_building_create_delete_logged(client, admin_token):
    building = client.post("/api/buildings", json={"name": "Audit Hall"}, headers=_admin(admin_token)).json()
    client.delete(f"/api/buildings/{building['building_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "building")
    assert any(r["action"] == "create" and r["resource_id"] == building["building_id"] and r["resource_label"] == "Audit Hall" for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == building["building_id"] for r in rows)


def test_building_duplicate_return_does_not_double_log_create(client, admin_token):
    """create_building returns the EXISTING row (no new object) on a
    duplicate name — confirms no phantom second 'create' entry is logged
    for a no-op."""
    client.post("/api/buildings", json={"name": "Dup Audit Hall"}, headers=_admin(admin_token))
    client.post("/api/buildings", json={"name": "Dup Audit Hall"}, headers=_admin(admin_token))

    rows = _rows(client, admin_token, "building")
    creates = [r for r in rows if r["action"] == "create" and r["resource_label"] == "Dup Audit Hall"]
    assert len(creates) == 1


# ---------------------------------------------------------------------------
# System Settings mutations
# ---------------------------------------------------------------------------
def test_system_settings_update_logged(client, admin_token):
    client.put("/api/system/settings", json={"checkout_time": "21:15"}, headers=_admin(admin_token))

    rows = _rows(client, admin_token, "system_settings")
    assert any(r["action"] == "update" and "21:15" in (r["description"] or "") for r in rows)


# ---------------------------------------------------------------------------
# Password Reset admin mutations (approve/deny)
# ---------------------------------------------------------------------------
def test_password_reset_approve_logged(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "password_reset_request")
    assert any(r["action"] == "approve" and r["resource_id"] == req.request_id and r["result"] == "success" for r in rows)


def test_password_reset_deny_logged(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/deny", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "password_reset_request")
    assert any(r["action"] == "deny" and r["resource_id"] == req.request_id for r in rows)


def test_rejected_approve_does_not_log_a_success_entry(client, db_session, instructor_token, admin_token):
    """A 403-rejected (non-admin) approve attempt must not create a
    misleading 'success' audit row for an action that never happened."""
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    resp = client.post(f"/api/password-resets/{req.request_id}/approve",
                        headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403

    rows = _rows(client, admin_token, "password_reset_request")
    assert not any(r["resource_id"] == req.request_id and r["action"] == "approve" for r in rows)


# ---------------------------------------------------------------------------
# Zone schedule CRUD (Phase 12 — closes the "zone-schedules CRUD" gap
# documented as unaudited since Phase 11's completion report).
# ---------------------------------------------------------------------------
def test_zone_schedule_create_update_delete_logged(client, admin_token):
    zone = client.post("/api/zones", json={"name": "Sched Audit Zone"}, headers=_admin(admin_token)).json()
    sched = client.post("/api/zone-schedules", json={
        "zone_id": zone["zone_id"], "open_time": "08:00:00", "close_time": "18:00:00",
    }, headers=_admin(admin_token)).json()
    client.put(f"/api/zone-schedules/{sched['schedule_id']}", json={"grace_minutes": 15},
               headers=_admin(admin_token))
    client.delete(f"/api/zone-schedules/{sched['schedule_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "zone_schedule")
    assert any(r["action"] == "create" and r["resource_id"] == sched["schedule_id"] for r in rows)
    assert any(r["action"] == "update" and r["resource_id"] == sched["schedule_id"] for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == sched["schedule_id"] for r in rows)


# ---------------------------------------------------------------------------
# Scoped-admin cannot see audit logs at all — re-confirmed still holds after
# extending coverage (unrestricted-admin-only read policy unchanged).
# ---------------------------------------------------------------------------
def test_scoped_admin_still_cannot_view_extended_audit_entries(db_session, client, admin_token):
    from app import security

    faculty = models.Faculty(name="Extended Audit Scope College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    scoped = models.User(name="Extended Scoped Admin", email="ext.scoped.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(scoped)
    db_session.commit()
    db_session.refresh(scoped)
    db_session.add(models.AdminScope(user_id=scoped.user_id, faculty_id=faculty.faculty_id))
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": scoped.email, "password": "pw123456"})
    scoped_token = login.json()["access_token"]

    client.post("/api/zones", json={"name": "Should Be Invisible Zone"}, headers=_admin(admin_token))

    resp = client.get("/api/audit-logs", params={"resource_type": "zone"},
                       headers={"Authorization": f"Bearer {scoped_token}"})
    assert resp.status_code == 403
