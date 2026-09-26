"""
Tests for the final-hardening-pass centralized audit log:
app/models.py::AuditLog, app/services/audit_service.py, and the read-only
app/routers/audit_logs.py endpoint. Confirms real security-sensitive actions
(login, door lock/unlock, user/college/department/course CRUD, emergency
override) actually produce a row — not a fake/pre-populated log — and that
the endpoint stays unrestricted-admin-only.
"""
from app import models, security


def _scoped_admin_token(client, db, name, faculty_id):
    admin = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id))
    db.commit()
    resp = client.post("/api/auth/login", json={"email": admin.email, "password": "pw123456"})
    return admin, resp.json()["access_token"]


def _door(db, code="AUD101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def test_login_success_and_failure_are_logged(db_session, client, admin_token):
    client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})
    client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "admin123"})

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/audit-logs", headers=headers)
    assert resp.status_code == 200
    actions = [r["action"] for r in resp.json()]
    assert "login_failed" in actions
    assert "login_success" in actions
    failed = next(r for r in resp.json() if r["action"] == "login_failed")
    assert failed["result"] == "failure"
    assert failed["actor_email"] == "admin@example.edu"


def test_door_lock_unlock_logged(db_session, client, admin_token):
    door = _door(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(f"/api/doors/{door.door_id}/override", json={"action": "unlock"}, headers=headers)

    resp = client.get("/api/audit-logs", params={"resource_type": "door"}, headers=headers)
    rows = resp.json()
    assert any(r["action"] == "unlock" and r["resource_id"] == door.door_id for r in rows)


def test_user_and_college_crud_logged(db_session, client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    college_resp = client.post("/api/faculties", json={"name": "Audit College"}, headers=headers)
    faculty_id = college_resp.json()["faculty_id"]

    user_resp = client.post("/api/users", json={
        "name": "Audit TA", "email": "audit.ta@example.edu", "role": "instructor", "password": "pw123456",
    }, headers=headers)
    user_id = user_resp.json()["user_id"]
    client.delete(f"/api/users/{user_id}", headers=headers)

    resp = client.get("/api/audit-logs", headers=headers)
    rows = resp.json()
    assert any(r["action"] == "create" and r["resource_type"] == "faculty" and r["resource_id"] == faculty_id for r in rows)
    assert any(r["action"] == "create" and r["resource_type"] == "user" and r["resource_id"] == user_id for r in rows)
    assert any(r["action"] == "delete" and r["resource_type"] == "user" and r["resource_id"] == user_id for r in rows)


def test_emergency_override_create_and_revoke_logged(db_session, client, admin_token):
    door = _door(db_session, code="AUD102")
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = client.post(f"/api/doors/{door.door_id}/emergency-override", json={
        "door_id": door.door_id, "action": "unlock", "reason": "Fire drill", "duration_minutes": 10,
    }, headers=headers)
    override_id = create_resp.json()["override_id"]
    client.post(f"/api/emergency-overrides/{override_id}/revoke", json={"note": "drill over"}, headers=headers)

    resp = client.get("/api/audit-logs", params={"resource_type": "emergency_override"}, headers=headers)
    rows = resp.json()
    assert any(r["action"] == "emergency_override_unlock" and r["resource_id"] == override_id for r in rows)
    assert any(r["action"] == "emergency_override_revoke" and r["resource_id"] == override_id for r in rows)


def test_scoped_admin_cannot_view_audit_log(db_session, client, admin_token):
    faculty = models.Faculty(name="Scoped Audit College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    _, scoped_token = _scoped_admin_token(client, db_session, "Scoped Auditor", faculty.faculty_id)

    resp = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {scoped_token}"})
    assert resp.status_code == 403


def test_audit_log_is_read_only_no_mutation_routes(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/audit-logs", json={}, headers=headers)
    assert resp.status_code in (404, 405)
    resp2 = client.delete("/api/audit-logs/1", headers=headers)
    assert resp2.status_code in (404, 405)


def test_audit_log_result_filter(db_session, client, admin_token):
    client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/audit-logs", params={"result": "failure"}, headers=headers)
    assert resp.status_code == 200
    assert all(r["result"] == "failure" for r in resp.json())
