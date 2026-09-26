"""
Tests for Phase 6's Command Center summary endpoint
(app/routers/command_center.py) — verifies it aggregates REAL data from
existing tables/services rather than inventing anything, and that it stays
admin-only.
"""
import datetime

from app import models, security
from app.services import emergency_override_service


def _door(db, code="CC101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def test_summary_admin_only(client, instructor_token):
    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    assert resp.status_code == 403


def test_summary_reflects_real_door_and_event_data(db_session, client, admin_token):
    door = _door(db_session)
    db_session.add(models.AccessEvent(door_id=door.door_id, credential_id=None, method="card", result="granted"))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["door_status"]["total"] >= 1
    assert any(e["door_id"] == door.door_id for e in body["recent_events"])


def test_summary_event_rows_carry_real_investigation_status(db_session, client, admin_token):
    # Stage E-hardening: Command Center's recent-events feed now surfaces the
    # same EventInvestigation status the dedicated Access Events page shows —
    # None when nobody has ever opened an investigation on it, the real
    # persisted status once one exists.
    door = _door(db_session)
    event = models.AccessEvent(door_id=door.door_id, credential_id=None, method="card", result="denied")
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    row = next(e for e in resp.json()["recent_events"] if e["event_id"] == event.event_id)
    assert row["investigation_status"] is None

    client.put(f"/api/access-events/{event.event_id}/investigation", json={"status": "under_review"}, headers=headers)
    resp2 = client.get("/api/command-center/summary", headers=headers)
    row2 = next(e for e in resp2.json()["recent_events"] if e["event_id"] == event.event_id)
    assert row2["investigation_status"] == "under_review"


def test_summary_includes_active_emergency_override(db_session, client, admin_token):
    door = _door(db_session, code="CC102")
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="CC test", duration_minutes=10,
    )

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    assert resp.status_code == 200
    overrides = resp.json()["active_overrides"]
    assert any(o["door_id"] == door.door_id for o in overrides)


def test_summary_excludes_expired_override(db_session, client, admin_token):
    door = _door(db_session, code="CC103")
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Will expire", duration_minutes=1,
    )
    future = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    emergency_override_service.expire_overrides_sweep(db_session, now=future)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    overrides = resp.json()["active_overrides"]
    assert not any(o["override_id"] == override.override_id for o in overrides)


def test_summary_includes_unresolved_alerts(db_session, client, admin_token):
    door = _door(db_session, code="CC104")
    db_session.add(models.Alert(door_id=door.door_id, type="forced_open"))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    alerts = resp.json()["alerts"]
    assert alerts["available"] is True
    assert any(a["door_id"] == door.door_id for a in alerts["items"])


def test_unrestricted_admin_sees_full_door_status_and_alerts(db_session, client, admin_token):
    _door(db_session, code="CC105")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    body = resp.json()
    assert body["scope"]["restricted"] is False
    assert body["door_status"]["available"] is True
    assert body["alerts"]["available"] is True


# ---------------------------------------------------------------------------
# Security hardening — Command Center scope isolation.
#
# Two distinct colleges/operational scopes are set up so isolation is
# actually proven (not just "restricted admin sees nothing"): Faculty A /
# Scope A has its own staff, events, and override; Faculty B / Scope B has
# a completely separate set. A's scoped admin must see A's data and NEVER
# B's, and vice versa.
# ---------------------------------------------------------------------------
def _staff(db, name, faculty_id=None, department_id=None):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="doctor",
                     password_hash=security.hash_password("pw123456"), faculty_id=faculty_id, department_id=department_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _scoped_admin(db, client, name, faculty_id=None, operational_scope_id=None):
    admin = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    if faculty_id is not None:
        db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id))
    if operational_scope_id is not None:
        db.add(models.AdminScope(user_id=admin.user_id, operational_scope_id=operational_scope_id))
    db.commit()
    resp = client.post("/api/auth/login", json={"email": admin.email, "password": "pw123456"})
    return admin, resp.json()["access_token"]


def _two_scope_fixture(db, client):
    """Builds two fully independent colleges/operational scopes with their
    own door, staff, access event, and emergency override each, plus a
    scoped admin for each side. Returns a dict of everything a test might
    need."""
    faculty_a = models.Faculty(name="Faculty A — CC Isolation")
    faculty_b = models.Faculty(name="Faculty B — CC Isolation")
    scope_a = models.OperationalScope(name="Scope A — CC Isolation", scope_type="HVAC")
    scope_b = models.OperationalScope(name="Scope B — CC Isolation", scope_type="ELECTRICAL")
    db.add_all([faculty_a, faculty_b, scope_a, scope_b])
    db.commit()

    staff_a = _staff(db, "Staff A CC", faculty_id=faculty_a.faculty_id)
    staff_b = _staff(db, "Staff B CC", faculty_id=faculty_b.faculty_id)

    door_a = _door(db, code="CCA1")
    door_b = _door(db, code="CCB1")

    event_a = models.AccessEvent(door_id=door_a.door_id, credential_id=None, method="card", result="granted", user_id=staff_a.user_id)
    event_b = models.AccessEvent(door_id=door_b.door_id, credential_id=None, method="card", result="granted", user_id=staff_b.user_id)
    db.add_all([event_a, event_b])
    db.commit()

    admin_root = db.query(models.User).filter(models.User.role == "admin", models.User.email == "admin@example.edu").first()
    override_a = emergency_override_service.create_override(
        db, door=door_a, admin=admin_root, action="unlock", reason="Scope A emergency",
        duration_minutes=10, operational_scope_id=scope_a.scope_id,
    )
    override_b = emergency_override_service.create_override(
        db, door=door_b, admin=admin_root, action="unlock", reason="Scope B emergency",
        duration_minutes=10, operational_scope_id=scope_b.scope_id,
    )

    admin_a, token_a = _scoped_admin(db, client, "Scoped Admin A CC", faculty_id=faculty_a.faculty_id, operational_scope_id=scope_a.scope_id)
    admin_b, token_b = _scoped_admin(db, client, "Scoped Admin B CC", faculty_id=faculty_b.faculty_id, operational_scope_id=scope_b.scope_id)

    return {
        "faculty_a": faculty_a, "faculty_b": faculty_b, "scope_a": scope_a, "scope_b": scope_b,
        "staff_a": staff_a, "staff_b": staff_b, "door_a": door_a, "door_b": door_b,
        "event_a": event_a, "event_b": event_b, "override_a": override_a, "override_b": override_b,
        "token_a": token_a, "token_b": token_b,
    }


def test_scoped_admin_sees_only_own_scope_events(db_session, client):
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get("/api/command-center/summary", headers=headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"]["restricted"] is True
    event_door_ids = {e["door_id"] for e in body["recent_events"]}
    assert f["door_a"].door_id in event_door_ids
    assert f["door_b"].door_id not in event_door_ids


def test_scoped_admin_b_sees_only_own_scope_events(db_session, client):
    """Proves isolation both directions, not just 'restricted sees less'."""
    f = _two_scope_fixture(db_session, client)
    headers_b = {"Authorization": f"Bearer {f['token_b']}"}
    resp = client.get("/api/command-center/summary", headers=headers_b)
    body = resp.json()
    event_door_ids = {e["door_id"] for e in body["recent_events"]}
    assert f["door_b"].door_id in event_door_ids
    assert f["door_a"].door_id not in event_door_ids


def test_scoped_admin_cannot_see_another_scopes_emergency_override(db_session, client):
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get("/api/command-center/summary", headers=headers_a)
    body = resp.json()
    override_ids = {o["override_id"] for o in body["active_overrides"]}
    assert f["override_a"].override_id in override_ids
    assert f["override_b"].override_id not in override_ids


def test_scoped_admin_cannot_see_another_colleges_anomaly_indicators(db_session, client):
    """Gives staff_b enough denied attempts to actually trigger an anomaly
    indicator, then proves scope A's admin never receives it."""
    f = _two_scope_fixture(db_session, client)
    base = datetime.datetime.utcnow()
    for i in range(3):
        db_session.add(models.AccessEvent(
            door_id=f["door_b"].door_id, credential_id=None, method="card", result="denied",
            user_id=f["staff_b"].user_id, event_time=base - datetime.timedelta(minutes=i * 2),
        ))
    db_session.commit()

    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get("/api/command-center/summary", headers=headers_a)
    body = resp.json()
    assert not any(ind["user_id"] == f["staff_b"].user_id for ind in body["anomaly_indicators"])

    # Confirm the anomaly is real (so this test isn't vacuously true) by
    # checking it DOES show up for scope B's own admin.
    headers_b = {"Authorization": f"Bearer {f['token_b']}"}
    resp_b = client.get("/api/command-center/summary", headers=headers_b)
    body_b = resp_b.json()
    assert any(ind["user_id"] == f["staff_b"].user_id for ind in body_b["anomaly_indicators"])


def test_scoped_admin_doors_and_alerts_marked_unavailable_not_guessed(db_session, client):
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get("/api/command-center/summary", headers=headers_a)
    body = resp.json()
    assert body["door_status"]["available"] is False
    assert body["alerts"]["available"] is False


def test_scoped_admin_cannot_revoke_another_scopes_override_via_drilldown(db_session, client):
    """Even if a scoped admin somehow learned another scope's override id
    (e.g. guessed it), the underlying endpoint — not just the Command
    Center list — still rejects it. Proves the isolation isn't just a
    frontend-rendering trick."""
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.post(f"/api/emergency-overrides/{f['override_b'].override_id}/revoke",
                        json={"note": "attempted cross-scope revoke"}, headers=headers_a)
    assert resp.status_code == 403


def test_scoped_admin_cannot_view_another_colleges_staff_anomaly_report_via_drilldown(db_session, client):
    """Same drill-down-can't-bypass-authorization proof for the staff
    anomaly detail endpoint a Command Center row would link toward."""
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get(f"/api/staff/{f['staff_b'].user_id}/anomalies", headers=headers_a)
    assert resp.status_code == 403


def test_unrestricted_admin_still_sees_everything_across_both_scopes(db_session, client, admin_token):
    f = _two_scope_fixture(db_session, client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/command-center/summary", headers=headers)
    body = resp.json()
    assert body["scope"]["restricted"] is False
    event_door_ids = {e["door_id"] for e in body["recent_events"]}
    assert f["door_a"].door_id in event_door_ids
    assert f["door_b"].door_id in event_door_ids
    override_ids = {o["override_id"] for o in body["active_overrides"]}
    assert f["override_a"].override_id in override_ids
    assert f["override_b"].override_id in override_ids
