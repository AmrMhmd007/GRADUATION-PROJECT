"""
Tests for the final-hardening-pass Phase 7 fix to app/routers/alerts.py: a
scope-restricted admin used to see and resolve EVERY alert system-wide
(list_alerts/resolve_alert only checked require_admin, no scope filter at
all) — a real gap, since alerts are exactly the kind of security-sensitive
data scoping is supposed to protect. Alerts are door/zone-anchored and
neither has a safe scope mapping (same documented limitation as Command
Center's doors/alerts), so the fix is the same "no guessing" pattern: a
scope-restricted admin gets an empty list and cannot resolve anything, never
a fabricated subset. An unrestricted admin is unaffected.
"""
from app import models, security


def _door(db, code="ALSC101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


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


def test_unrestricted_admin_still_sees_all_alerts(db_session, client, admin_token):
    door = _door(db_session)
    db_session.add(models.Alert(door_id=door.door_id, type="forced_open"))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/alerts", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_scoped_admin_sees_no_alerts(db_session, client, admin_token):
    door = _door(db_session, code="ALSC102")
    db_session.add(models.Alert(door_id=door.door_id, type="forced_open"))
    db_session.commit()

    faculty = models.Faculty(name="Alert Scope College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    _, scoped_token = _scoped_admin_token(client, db_session, "Alert Scoped Admin", faculty.faculty_id)

    resp = client.get("/api/alerts", headers={"Authorization": f"Bearer {scoped_token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_scoped_admin_cannot_resolve_any_alert(db_session, client, admin_token):
    door = _door(db_session, code="ALSC103")
    alert = models.Alert(door_id=door.door_id, type="forced_open")
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    faculty = models.Faculty(name="Alert Scope College 2")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    _, scoped_token = _scoped_admin_token(client, db_session, "Alert Resolver Blocked", faculty.faculty_id)

    resp = client.put(f"/api/alerts/{alert.alert_id}/resolve", headers={"Authorization": f"Bearer {scoped_token}"})
    assert resp.status_code == 403

    db_session.refresh(alert)
    assert alert.resolved is False


def test_unrestricted_admin_can_still_resolve(db_session, client, admin_token):
    door = _door(db_session, code="ALSC104")
    alert = models.Alert(door_id=door.door_id, type="forced_open")
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(f"/api/alerts/{alert.alert_id}/resolve", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True
