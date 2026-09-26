"""
Stage C — Investigation & Evidence: focused regression tests.

Covers exactly the gaps genuinely introduced by investigation_service.py /
routers/investigations.py — not a re-test of anomaly_detection_service or
emergency_override_service themselves (those already have their own test
files and are only being reused/read here, not modified).
"""
import datetime
import json

from app import models, security


def _door(db, code="INV101", building="Building A"):
    door = models.Door(code=code, name=f"Room {code}", building=building, fail_mode="secure",
                        online=True, locked=True)
    db.add(door)
    db.commit()
    db.refresh(door)
    return door


def _staff(db, name="Staff", role="doctor", faculty_id=None):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
                     password_hash=security.hash_password("pw123456"), faculty_id=faculty_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _event(db, door, user=None, result="granted", method="schedule_check", evidence=None, event_time=None):
    e = models.AccessEvent(
        door_id=door.door_id, credential_id=None, user_id=user.user_id if user else None,
        method=method, result=result,
        event_time=event_time or datetime.datetime.utcnow(),
        evidence_snapshot=json.dumps(evidence, default=str) if evidence is not None else None,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _scoped_admin(db, faculty_id, email="scoped.inv@example.edu"):
    admin = models.User(name="Scoped Inv Admin", email=email, role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id))
    db.commit()
    return admin


def _login(client, email, password="pw123456"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# 1. Authorized (unrestricted) admin can investigate an event.
def test_unrestricted_admin_can_view_event_detail(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    event = _event(db_session, door, user=staff)

    resp = client.get(f"/api/access-events/{event.event_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_id"] == event.event_id
    assert body["user_id"] == staff.user_id
    assert body["physical_door_state"]["available"] is True


# 2. Unauthorized role (a different, non-admin staff member) cannot access
# someone else's investigation data — but CAN view their own.
def test_non_admin_can_view_own_event_but_not_others(db_session, client):
    door = _door(db_session)
    staff = _staff(db_session, name="Self Staff", role="instructor")
    other = _staff(db_session, name="Other Staff", role="instructor")
    own_event = _event(db_session, door, user=staff)
    other_event = _event(db_session, door, user=other)

    headers = _login(client, staff.email)
    own_resp = client.get(f"/api/access-events/{own_event.event_id}", headers=headers)
    assert own_resp.status_code == 200

    other_resp = client.get(f"/api/access-events/{other_event.event_id}", headers=headers)
    assert other_resp.status_code == 403


# 3. Scoped admin cannot access another scope's investigation data (and
# isolation holds both ways).
def test_scoped_admin_cannot_view_out_of_scope_event(db_session, client):
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering INV")
    biz = models.Faculty(name="Faculty of Business INV")
    db_session.add_all([eng, biz])
    db_session.commit()
    eng_staff = _staff(db_session, name="Eng Staff INV", faculty_id=eng.faculty_id)
    biz_staff = _staff(db_session, name="Biz Staff INV", faculty_id=biz.faculty_id)
    eng_event = _event(db_session, door, user=eng_staff)
    biz_event = _event(db_session, door, user=biz_staff)

    eng_admin = _scoped_admin(db_session, eng.faculty_id, email="eng.inv@example.edu")
    headers = _login(client, eng_admin.email)

    assert client.get(f"/api/access-events/{eng_event.event_id}", headers=headers).status_code == 200
    assert client.get(f"/api/access-events/{biz_event.event_id}", headers=headers).status_code == 403


# 4. Access event details persist after refresh (a fresh GET, not a cached
# response, reflects an investigation-status change).
def test_event_detail_persists_after_refresh(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    event = _event(db_session, door, user=staff)
    headers = {"Authorization": f"Bearer {admin_token}"}

    put_resp = client.put(f"/api/access-events/{event.event_id}/investigation",
                           json={"status": "under_review", "note": "Looking into this"}, headers=headers)
    assert put_resp.status_code == 200

    get_resp = client.get(f"/api/access-events/{event.event_id}", headers=headers)
    assert get_resp.status_code == 200
    inv = get_resp.json()["investigation"]
    assert inv["status"] == "under_review"
    assert inv["note"] == "Looking into this"

    # A second, completely independent fetch confirms it wasn't a one-off.
    get_resp2 = client.get(f"/api/access-events/{event.event_id}", headers=headers)
    assert get_resp2.json()["investigation"]["status"] == "under_review"


# 5. Evidence snapshot is preferred over current-state data.
def test_evidence_snapshot_preferred_over_current_state(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    # No AccessWindow/DoorAssignment exists at all right now — a live
    # evaluation would say "denied, no access". The recorded snapshot says
    # the opposite, and that recorded snapshot must win.
    snapshot = {
        "authorization_source": "schedule_derived", "authorized": True,
        "reason": "Recorded: within a since-deleted temporary window",
        "has_permanent_access": False, "matched_window": None, "temporary": True,
    }
    event = _event(db_session, door, user=staff, evidence=snapshot)

    resp = client.get(f"/api/access-events/{event.event_id}", headers={"Authorization": f"Bearer {admin_token}"})
    body = resp.json()
    assert body["evidence_basis"] == "recorded_snapshot"
    assert body["authorization"]["authorized"] is True
    assert body["authorization"]["reason"] == "Recorded: within a since-deleted temporary window"


# 6. Missing snapshot is clearly handled (never silently recomputed/guessed).
def test_missing_evidence_snapshot_is_explicit(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    event = _event(db_session, door, user=staff, evidence=None)

    resp = client.get(f"/api/access-events/{event.event_id}", headers={"Authorization": f"Bearer {admin_token}"})
    body = resp.json()
    assert body["evidence_available"] is False
    assert body["evidence_basis"] == "unavailable"
    assert body["evidence"] is None
    assert body["authorization"] is None


# 7. Anomaly evidence in the investigation view matches the deterministic
# rule's own output (not a separate/invented computation).
def test_related_anomalies_match_deterministic_rule(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    # Three denied attempts within the burst window at the same door — the
    # exact shape _rule_repeated_denied_attempts requires.
    events = [_event(db_session, door, user=staff, result="denied", method="card",
                      event_time=base + datetime.timedelta(minutes=i)) for i in range(3)]
    last_event = events[-1]

    resp = client.get(f"/api/access-events/{last_event.event_id}", headers={"Authorization": f"Bearer {admin_token}"})
    body = resp.json()
    rules = [a["rule"] for a in body["related_anomalies"]]
    assert "REPEATED_DENIED_ATTEMPTS" in rules
    matching = next(a for a in body["related_anomalies"] if a["rule"] == "REPEATED_DENIED_ATTEMPTS")
    assert matching["evidence"]["event_count"] == 3


# 8. Related records are real — an emergency override that genuinely
# overlaps the event's timestamp is linked; one that doesn't, isn't.
def test_related_override_is_real_and_time_bounded(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    now = datetime.datetime.utcnow()
    override = models.EmergencyOverride(
        door_id=door.door_id, action="unlock", reason="Fire drill",
        created_by_id=1, created_at=now, expires_at=now + datetime.timedelta(minutes=10), status="ACTIVE",
    )
    db_session.add(override)
    db_session.commit()

    inside_event = _event(db_session, door, user=staff, event_time=now + datetime.timedelta(minutes=2))
    outside_event = _event(db_session, door, user=staff, event_time=now + datetime.timedelta(hours=2))

    headers = {"Authorization": f"Bearer {admin_token}"}
    inside_resp = client.get(f"/api/access-events/{inside_event.event_id}", headers=headers).json()
    outside_resp = client.get(f"/api/access-events/{outside_event.event_id}", headers=headers).json()

    assert inside_resp["related_override"] is not None
    assert inside_resp["related_override"]["override_id"] == override.override_id
    assert outside_resp["related_override"] is None


# 9. Investigation mutation is audited.
def test_investigation_status_change_is_audited(db_session, client, admin_token):
    door = _door(db_session)
    event = _event(db_session, door)
    headers = {"Authorization": f"Bearer {admin_token}"}

    before = db_session.query(models.AuditLog).filter(models.AuditLog.resource_type == "event_investigation").count()
    resp = client.put(f"/api/access-events/{event.event_id}/investigation", json={"status": "resolved"}, headers=headers)
    assert resp.status_code == 200
    after = db_session.query(models.AuditLog).filter(models.AuditLog.resource_type == "event_investigation").count()
    assert after == before + 1


# 10. Read-only investigation (GET detail, GET timeline) does not create
# audit noise.
def test_readonly_investigation_view_creates_no_audit_entries(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    event = _event(db_session, door, user=staff)
    headers = {"Authorization": f"Bearer {admin_token}"}

    before = db_session.query(models.AuditLog).count()
    assert client.get(f"/api/access-events/{event.event_id}", headers=headers).status_code == 200
    assert client.get(f"/api/access-events/{event.event_id}/timeline", headers=headers).status_code == 200
    assert client.get("/api/access-events", headers=headers).status_code == 200
    after = db_session.query(models.AuditLog).count()
    assert after == before


# Bonus: list endpoint's scope filtering + building/result filters, since
# C7 explicitly requires real backend filtering (not client-side over an
# incomplete page).
def test_list_access_events_filters_and_scope_isolation(db_session, client):
    door_a = _door(db_session, code="INV-A", building="Building A")
    door_b = _door(db_session, code="INV-B", building="Building B")
    eng = models.Faculty(name="Faculty of Engineering INVLIST")
    biz = models.Faculty(name="Faculty of Business INVLIST")
    db_session.add_all([eng, biz])
    db_session.commit()
    eng_staff = _staff(db_session, name="Eng List Staff", faculty_id=eng.faculty_id)
    biz_staff = _staff(db_session, name="Biz List Staff", faculty_id=biz.faculty_id)
    _event(db_session, door_a, user=eng_staff, result="denied")
    _event(db_session, door_b, user=biz_staff, result="granted")

    eng_admin = _scoped_admin(db_session, eng.faculty_id, email="eng.list.inv@example.edu")
    headers = _login(client, eng_admin.email)

    resp = client.get("/api/access-events", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["user_id"] == eng_staff.user_id

    filtered = client.get("/api/access-events?result=denied", headers=headers)
    assert len(filtered.json()) == 1
    filtered_out = client.get("/api/access-events?result=granted", headers=headers)
    assert len(filtered_out.json()) == 0
