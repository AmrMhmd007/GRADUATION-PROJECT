"""
Tests for Feature #8 (Emergency Access / Override):
app/services/emergency_override_service.py + app/routers/emergency_overrides.py,
plus its integration points in mqtt_service.py (evidence) and
anomaly_detection_service.py (exclusion from false-positive anomalies).
"""
import datetime

from app import models, security
from app.services import access_authorization_service, anomaly_detection_service, emergency_override_service


def _door(db, code="EO101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _scoped_admin(db, name, operational_scope_id=None):
    admin = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    if operational_scope_id is not None:
        db.add(models.AdminScope(user_id=admin.user_id, operational_scope_id=operational_scope_id))
        db.commit()
    return admin


def _staff(db, name="Doctor EO", role="doctor"):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
                     password_hash=security.hash_password("pw123456"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _op_scope(db, name="HVAC Zone A", scope_type="HVAC"):
    s = models.OperationalScope(name=name, scope_type=scope_type)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Creation: authorization
# ---------------------------------------------------------------------------
def test_unrestricted_admin_can_create_override(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()

    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Fire drill", duration_minutes=15,
    )
    assert override.status == "ACTIVE"
    assert override.action == "unlock"
    db_session.refresh(door)
    assert door.locked is False


def test_scoped_admin_with_matching_scope_can_create_override(db_session):
    door = _door(db_session)
    scope = _op_scope(db_session)
    admin = _scoped_admin(db_session, "Scoped Admin EO1", operational_scope_id=scope.scope_id)

    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="HVAC emergency shutoff bypass",
        duration_minutes=10, operational_scope_id=scope.scope_id,
    )
    assert override.status == "ACTIVE"


def test_scoped_admin_without_scope_declaration_rejected(db_session):
    """A scope-restricted admin who doesn't declare an operational scope is
    rejected — Door itself has no scope link, so declaring one is how a
    restricted admin proves authority."""
    from fastapi import HTTPException
    door = _door(db_session)
    scope = _op_scope(db_session)
    admin = _scoped_admin(db_session, "Scoped Admin EO2", operational_scope_id=scope.scope_id)

    try:
        emergency_override_service.create_override(
            db_session, door=door, admin=admin, action="unlock", reason="No scope given", duration_minutes=10,
        )
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_override_outside_admin_scope_rejected(db_session):
    """An admin scoped to one operational area cannot override under a
    DIFFERENT operational area they weren't granted."""
    from fastapi import HTTPException
    door = _door(db_session)
    my_scope = _op_scope(db_session, name="HVAC Zone A")
    other_scope = _op_scope(db_session, name="Electrical Zone B", scope_type="ELECTRICAL")
    admin = _scoped_admin(db_session, "Scoped Admin EO3", operational_scope_id=my_scope.scope_id)

    try:
        emergency_override_service.create_override(
            db_session, door=door, admin=admin, action="unlock", reason="Wrong scope",
            duration_minutes=10, operational_scope_id=other_scope.scope_id,
        )
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


# ---------------------------------------------------------------------------
# Creation: validation
# ---------------------------------------------------------------------------
def test_missing_reason_rejected(db_session):
    from fastapi import HTTPException
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    try:
        emergency_override_service.create_override(
            db_session, door=door, admin=admin, action="unlock", reason="   ", duration_minutes=10,
        )
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


def test_invalid_duration_rejected(db_session):
    from fastapi import HTTPException
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    for bad_duration in (0, -5):
        try:
            emergency_override_service.create_override(
                db_session, door=door, admin=admin, action="unlock", reason="Test",
                duration_minutes=bad_duration,
            )
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 400


def test_duration_exceeding_max_rejected(db_session):
    """Never silently create permanent access: duration is capped."""
    from fastapi import HTTPException
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    try:
        emergency_override_service.create_override(
            db_session, door=door, admin=admin, action="unlock", reason="Too long",
            duration_minutes=100000,
        )
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


def test_invalid_action_rejected(db_session):
    from fastapi import HTTPException
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    try:
        emergency_override_service.create_override(
            db_session, door=door, admin=admin, action="explode", reason="bad action", duration_minutes=10,
        )
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


# ---------------------------------------------------------------------------
# Expiration / effective status
# ---------------------------------------------------------------------------
def test_expired_override_is_not_active(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Short-lived", duration_minutes=1,
    )
    future = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    assert emergency_override_service.effective_status(override, now=future) == "EXPIRED"
    assert emergency_override_service.active_override_for_door(db_session, door.door_id, now=future) is None


def test_expiry_sweep_reverts_door_and_marks_expired(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Will expire", duration_minutes=1,
    )
    db_session.refresh(door)
    assert door.locked is False

    future = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    expired_ids = emergency_override_service.expire_overrides_sweep(db_session, now=future)
    assert override.override_id in expired_ids

    db_session.refresh(override)
    db_session.refresh(door)
    assert override.status == "EXPIRED"
    assert door.locked is True  # reverted to the safe default

    # Audit trail: an "override expired" event was logged.
    events = db_session.query(models.AccessEvent).filter(models.AccessEvent.door_id == door.door_id).all()
    assert any("expired" in (json_or_empty(e.evidence_snapshot)) for e in events)


def json_or_empty(s):
    return s or ""


# ---------------------------------------------------------------------------
# Active override grants authorization only within its defined scope/time
# ---------------------------------------------------------------------------
def test_active_override_reflected_in_active_lookup_only_within_window(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Window test", duration_minutes=10,
    )
    now = datetime.datetime.utcnow()
    assert emergency_override_service.active_override_for_door(db_session, door.door_id, now=now) is not None
    later = now + datetime.timedelta(minutes=11)
    assert emergency_override_service.active_override_for_door(db_session, door.door_id, now=later) is None


def test_override_does_not_create_permanent_access(db_session):
    """No DoorAssignment or AccessWindow row is ever written by an
    emergency override — it must never masquerade as, or turn into, a
    normal permanent/scheduled grant."""
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    before_assignments = db_session.query(models.DoorAssignment).count()
    before_windows = db_session.query(models.AccessWindow).count()

    emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="No permanent grant", duration_minutes=10,
    )

    assert db_session.query(models.DoorAssignment).count() == before_assignments
    assert db_session.query(models.AccessWindow).count() == before_windows


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
def test_override_evidence_recorded_correctly(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Evidence check", duration_minutes=10,
    )

    import json
    event = (
        db_session.query(models.AccessEvent)
        .filter(models.AccessEvent.door_id == door.door_id, models.AccessEvent.method == "override")
        .order_by(models.AccessEvent.event_id.desc())
        .first()
    )
    evidence = json.loads(event.evidence_snapshot)
    assert evidence["authorization_source"] == access_authorization_service.EVIDENCE_SOURCE_ADMIN_OVERRIDE
    assert evidence["override_id"] == override.override_id
    assert evidence["actor_user_id"] == admin.user_id
    assert evidence["status"] == "ACTIVE"
    assert evidence["expires_at"] is not None
    assert event.user_id == admin.user_id


# ---------------------------------------------------------------------------
# Override events excluded from normal anomaly rules where appropriate
# ---------------------------------------------------------------------------
def test_override_creation_event_excluded_from_schedule_anomaly_rule(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Late night emergency", duration_minutes=10,
    )
    report = anomaly_detection_service.detect_anomalies_for_user(db_session, admin)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


def test_badge_swipe_during_active_override_not_flagged_outside_schedule(db_session):
    """A physical badge swipe that happens while an emergency override is
    active must not be flagged as an unexplained authorization gap — the
    override is a defensible, recorded explanation."""
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    staff = _staff(db_session, name="Swiper EO")

    emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Emergency evacuation", duration_minutes=30,
    )

    # Simulate what mqtt_service.py's /event handler would have recorded for
    # a badge swipe by `staff` (no permanent access, no window) while the
    # override was active.
    evaluation = access_authorization_service.evaluate_door_authorization(db_session, staff, door)
    evidence = access_authorization_service.build_authorization_evidence(
        evaluation, source=access_authorization_service.EVIDENCE_SOURCE_PHYSICAL_DOOR_NODE,
    )
    assert evidence["authorized"] is False  # no normal WHO/WHEN grant at all
    active = emergency_override_service.active_override_for_door(db_session, door.door_id)
    evidence["emergency_override_active"] = {
        "override_id": active.override_id, "action": active.action, "reason": active.reason,
        "created_by_id": active.created_by_id, "expires_at": active.expires_at,
    }
    import json
    db_session.add(models.AccessEvent(
        door_id=door.door_id, credential_id=None, method="card", result="granted",
        user_id=staff.user_id, evidence_snapshot=json.dumps(evidence, default=str),
    ))
    db_session.commit()

    report = anomaly_detection_service.detect_anomalies_for_user(db_session, staff)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------
def test_revoke_marks_revoked_and_relocks_door(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="To be revoked", duration_minutes=30,
    )
    db_session.refresh(door)
    assert door.locked is False

    revoked = emergency_override_service.revoke_override(db_session, override=override, admin=admin, note="Resolved")
    assert revoked.status == "REVOKED"
    assert revoked.revoked_by_id == admin.user_id
    db_session.refresh(door)
    assert door.locked is True


def test_cannot_revoke_already_expired_override(db_session):
    from fastapi import HTTPException
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Will expire", duration_minutes=1,
    )
    future = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    emergency_override_service.expire_overrides_sweep(db_session, now=future)
    db_session.refresh(override)

    try:
        emergency_override_service.revoke_override(db_session, override=override, admin=admin)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 409


# ---------------------------------------------------------------------------
# Multiple simultaneous overrides / conflict handling
# ---------------------------------------------------------------------------
def test_conflicting_override_on_same_door_rejected(db_session):
    from fastapi import HTTPException
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="First", duration_minutes=30,
    )
    try:
        emergency_override_service.create_override(
            db_session, door=door, admin=admin, action="lock", reason="Second (conflict)", duration_minutes=10,
        )
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 409


def test_new_override_allowed_after_previous_one_revoked(db_session):
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    first = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="First", duration_minutes=30,
    )
    emergency_override_service.revoke_override(db_session, override=first, admin=admin)

    second = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Second, after revoke", duration_minutes=10,
    )
    assert second.status == "ACTIVE"


def test_simultaneous_overrides_on_different_doors_both_active(db_session):
    door_a = _door(db_session, code="EO201")
    door_b = _door(db_session, code="EO202")
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()

    o1 = emergency_override_service.create_override(
        db_session, door=door_a, admin=admin, action="unlock", reason="Door A emergency", duration_minutes=10,
    )
    o2 = emergency_override_service.create_override(
        db_session, door=door_b, admin=admin, action="unlock", reason="Door B emergency", duration_minutes=10,
    )
    assert emergency_override_service.active_override_for_door(db_session, door_a.door_id).override_id == o1.override_id
    assert emergency_override_service.active_override_for_door(db_session, door_b.door_id).override_id == o2.override_id


# ---------------------------------------------------------------------------
# Timezone / day-boundary behavior
# ---------------------------------------------------------------------------
def test_override_expiry_computed_in_utc_across_midnight(db_session):
    """expires_at must be a plain UTC-consistent addition, unaffected by
    local wall-clock day boundaries (the same class of bug the pre-existing
    midnight-wrap flake in test_automation_engine.py stems from — this
    feature deliberately avoids naive local time entirely, same as
    Feature #5's AccessWindow)."""
    door = _door(db_session)
    admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    override = emergency_override_service.create_override(
        db_session, door=door, admin=admin, action="unlock", reason="Cross-midnight", duration_minutes=60 * 3,
    )
    # Regardless of what local wall-clock time it is when this test runs,
    # expires_at must be exactly created_at + duration, in UTC.
    delta = override.expires_at - override.created_at
    assert delta == datetime.timedelta(minutes=180)

    just_before = override.expires_at - datetime.timedelta(seconds=1)
    just_after = override.expires_at + datetime.timedelta(seconds=1)
    assert emergency_override_service.effective_status(override, now=just_before) == "ACTIVE"
    assert emergency_override_service.effective_status(override, now=just_after) == "EXPIRED"


# ---------------------------------------------------------------------------
# Regression: normal authorization untouched
# ---------------------------------------------------------------------------
def test_normal_door_assignment_authorization_unaffected_by_emergency_override_feature(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="Regression Doc EO")
    db_session.add(models.DoorAssignment(door_id=door.door_id, instructor_id=staff.user_id))
    db_session.commit()

    evaluation = access_authorization_service.evaluate_door_authorization(db_session, staff, door)
    assert evaluation["authorized"] is True
    assert evaluation["has_permanent_access"] is True


def test_normal_access_window_authorization_unaffected_by_emergency_override_feature(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="Regression Doc EO2")
    db_session.add(models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=True,
        day_of_week=datetime.datetime.utcnow().weekday(),
        start_time=datetime.time(0, 0), end_time=datetime.time(23, 59),
    ))
    db_session.commit()

    evaluation = access_authorization_service.evaluate_door_authorization(db_session, staff, door)
    assert evaluation["authorized"] is True


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
def test_api_create_and_get_active_override(db_session, client, admin_token):
    door = _door(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(f"/api/doors/{door.door_id}/emergency-override", json={
        "door_id": door.door_id, "action": "unlock", "reason": "API test", "duration_minutes": 20,
    }, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["effective_status"] == "ACTIVE"
    assert body["seconds_remaining"] > 0

    resp2 = client.get(f"/api/doors/{door.door_id}/emergency-override", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["override_id"] == body["override_id"]


def test_api_non_admin_cannot_create_override(db_session, client, instructor_token):
    door = _door(db_session)
    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.post(f"/api/doors/{door.door_id}/emergency-override", json={
        "door_id": door.door_id, "action": "unlock", "reason": "Should fail", "duration_minutes": 10,
    }, headers=headers)
    assert resp.status_code == 403


def test_api_revoke_endpoint(db_session, client, admin_token):
    door = _door(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = client.post(f"/api/doors/{door.door_id}/emergency-override", json={
        "door_id": door.door_id, "action": "unlock", "reason": "To revoke via API", "duration_minutes": 10,
    }, headers=headers)
    override_id = create_resp.json()["override_id"]

    revoke_resp = client.post(f"/api/emergency-overrides/{override_id}/revoke",
                               json={"note": "Resolved via API"}, headers=headers)
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["status"] == "REVOKED"
