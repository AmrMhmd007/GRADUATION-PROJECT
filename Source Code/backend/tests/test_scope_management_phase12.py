"""
Phase 12 — backend support added for the new AdminScope/OperationalScope
management UI: GET /api/users/me now reports is_scope_restricted (so the
frontend knows whether to show the management panel at all), AdminScope
grant/revoke and OperationalScope create/delete are now audit-logged, and
two previously-missing dependent-blocking checks were added (deleting an
OperationalScope still referenced by an AdminScope grant; deleting a
Building still referenced by an OperationalScope) — mirroring the same
dependent-blocking pattern already used for Faculty/Department/Course.
"""
from app import models, security


def _admin(token):
    return {"Authorization": f"Bearer {token}"}


def _rows(client, admin_token, resource_type=None):
    params = {"resource_type": resource_type} if resource_type else {}
    return client.get("/api/audit-logs", params=params, headers=_admin(admin_token)).json()


# ---------------------------------------------------------------------------
# GET /api/users/me — is_scope_restricted
# ---------------------------------------------------------------------------
def test_unrestricted_admin_reports_unrestricted(client, admin_token):
    me = client.get("/api/users/me", headers=_admin(admin_token)).json()
    assert me["is_scope_restricted"] is False


def test_scoped_admin_reports_restricted(client, db_session, admin_token):
    faculty = models.Faculty(name="Scope Flag College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    scoped = models.User(name="Scope Flag Admin", email="scope.flag.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(scoped)
    db_session.commit()
    db_session.refresh(scoped)
    db_session.add(models.AdminScope(user_id=scoped.user_id, faculty_id=faculty.faculty_id))
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": scoped.email, "password": "pw123456"})
    scoped_token = login.json()["access_token"]

    me = client.get("/api/users/me", headers=_admin(scoped_token)).json()
    assert me["is_scope_restricted"] is True


def test_instructor_is_scope_restricted_is_none(client, instructor_token):
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {instructor_token}"}).json()
    assert me["is_scope_restricted"] is None


# ---------------------------------------------------------------------------
# AdminScope grant/revoke — audit logging
# ---------------------------------------------------------------------------
def test_grant_and_revoke_admin_scope_logged(client, db_session, admin_token):
    faculty = models.Faculty(name="Grant Audit College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    target = models.User(name="Grant Target Admin", email="grant.target.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    created = client.post("/api/admin-scopes", json={"user_id": target.user_id, "faculty_id": faculty.faculty_id},
                           headers=_admin(admin_token)).json()
    client.delete(f"/api/admin-scopes/{created['scope_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "admin_scope")
    assert any(r["action"] == "grant" and r["resource_id"] == created["scope_id"] for r in rows)
    assert any(r["action"] == "revoke" and r["resource_id"] == created["scope_id"] for r in rows)


# ---------------------------------------------------------------------------
# OperationalScope create/delete — audit logging
# ---------------------------------------------------------------------------
def test_create_and_delete_operational_scope_logged(client, admin_token):
    scope = client.post("/api/operational-scopes", json={"name": "Audit HVAC Zone", "scope_type": "HVAC"},
                         headers=_admin(admin_token)).json()
    client.delete(f"/api/operational-scopes/{scope['scope_id']}", headers=_admin(admin_token))

    rows = _rows(client, admin_token, "operational_scope")
    assert any(r["action"] == "create" and r["resource_id"] == scope["scope_id"] for r in rows)
    assert any(r["action"] == "delete" and r["resource_id"] == scope["scope_id"] for r in rows)


# ---------------------------------------------------------------------------
# Dependent-blocking: OperationalScope in use by an AdminScope grant
# ---------------------------------------------------------------------------
def test_cannot_delete_operational_scope_in_use_by_grant(client, db_session, admin_token):
    scope = client.post("/api/operational-scopes", json={"name": "In-Use HVAC", "scope_type": "HVAC"},
                         headers=_admin(admin_token)).json()
    target = models.User(name="In Use Admin", email="inuse.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)
    client.post("/api/admin-scopes", json={"user_id": target.user_id, "operational_scope_id": scope["scope_id"]},
                headers=_admin(admin_token))

    resp = client.delete(f"/api/operational-scopes/{scope['scope_id']}", headers=_admin(admin_token))
    assert resp.status_code == 409
    assert "still use it" in resp.json()["detail"]

    # Fresh read: still there, untouched.
    fresh = client.get("/api/operational-scopes", headers=_admin(admin_token)).json()
    assert any(s["scope_id"] == scope["scope_id"] for s in fresh)


def test_can_delete_operational_scope_after_grant_revoked(client, db_session, admin_token):
    scope = client.post("/api/operational-scopes", json={"name": "Freed HVAC", "scope_type": "HVAC"},
                         headers=_admin(admin_token)).json()
    target = models.User(name="Freed Admin", email="freed.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)
    grant = client.post("/api/admin-scopes", json={"user_id": target.user_id, "operational_scope_id": scope["scope_id"]},
                         headers=_admin(admin_token)).json()

    client.delete(f"/api/admin-scopes/{grant['scope_id']}", headers=_admin(admin_token))
    resp = client.delete(f"/api/operational-scopes/{scope['scope_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    fresh = client.get("/api/operational-scopes", headers=_admin(admin_token)).json()
    assert not any(s["scope_id"] == scope["scope_id"] for s in fresh)


# ---------------------------------------------------------------------------
# Dependent-blocking: Building in use by an OperationalScope
# ---------------------------------------------------------------------------
def test_cannot_delete_building_in_use_by_operational_scope(client, admin_token):
    building = client.post("/api/buildings", json={"name": "Scope-Linked Hall"}, headers=_admin(admin_token)).json()
    client.post("/api/operational-scopes", json={"name": "Hall HVAC", "scope_type": "HVAC",
                                                  "building_id": building["building_id"]},
                headers=_admin(admin_token))

    resp = client.delete(f"/api/buildings/{building['building_id']}", headers=_admin(admin_token))
    assert resp.status_code == 400
    assert "operational scope" in resp.json()["detail"]

    fresh = client.get("/api/buildings", headers=_admin(admin_token)).json()
    assert any(b["building_id"] == building["building_id"] for b in fresh)


def test_scoped_admin_cannot_manage_scopes_at_all(client, db_session, admin_token):
    faculty = models.Faculty(name="No Scope Mgmt College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    scoped = models.User(name="No Mgmt Admin", email="no.mgmt.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(scoped)
    db_session.commit()
    db_session.refresh(scoped)
    db_session.add(models.AdminScope(user_id=scoped.user_id, faculty_id=faculty.faculty_id))
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": scoped.email, "password": "pw123456"})
    scoped_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {scoped_token}"}

    assert client.get("/api/admin-scopes", headers=headers).status_code == 403
    assert client.post("/api/admin-scopes", json={"user_id": 1, "faculty_id": faculty.faculty_id}, headers=headers).status_code == 403
    assert client.post("/api/operational-scopes", json={"name": "X", "scope_type": "HVAC"}, headers=headers).status_code == 403
