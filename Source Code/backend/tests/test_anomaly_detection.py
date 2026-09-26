"""
Tests for Feature #7 (Access Anomaly / Unusual Access Indicator):
app/services/anomaly_detection_service.py and the
/api/staff/{id}/anomalies + /api/doors/{id}/anomalies endpoints.
"""
import datetime
import json

from app import models, security
from app.services import access_authorization_service
from app.services import anomaly_detection_service as anomalies


def _door(db, code="AN101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _staff(db, name="Doctor Anom", role="doctor", faculty_id=None, department_id=None):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
                     password_hash=security.hash_password("pw123456"), faculty_id=faculty_id, department_id=department_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _event(db, door, *, user=None, credential_id=None, method="card", result="granted", at=None, evidence=None):
    e = models.AccessEvent(
        door_id=door.door_id, credential_id=credential_id, method=method, result=result,
        event_time=at or datetime.datetime(2026, 9, 24, 12, 0),
        user_id=user.user_id if user else None,
        evidence_snapshot=json.dumps(evidence, default=str) if evidence is not None else None,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


NOW = datetime.datetime(2026, 9, 24, 18, 0)


# ---------------------------------------------------------------------------
# Normal behavior — no indicators
# ---------------------------------------------------------------------------
def test_normal_history_produces_no_indicators(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    db_session.add(models.DoorAssignment(door_id=door.door_id, instructor_id=staff.user_id))
    db_session.commit()
    # A few ordinary daytime granted visits to their own assigned door.
    for hour in (9, 10, 14):
        _event(db_session, door, user=staff, method="card", result="granted",
               at=datetime.datetime(2026, 9, 21, hour, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert report["indicators"] == []
    assert report["summary"] == {"UNUSUAL": 0, "ANOMALOUS": 0, "ELEVATED_RISK_INDICATOR": 0}


# ---------------------------------------------------------------------------
# Repeated denied attempts
# ---------------------------------------------------------------------------
def test_repeated_denied_attempts_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for i in range(3):
        _event(db_session, door, user=staff, method="card", result="denied", at=base + datetime.timedelta(minutes=i * 2))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    rules = [i["rule"] for i in report["indicators"]]
    assert "REPEATED_DENIED_ATTEMPTS" in rules
    indicator = next(i for i in report["indicators"] if i["rule"] == "REPEATED_DENIED_ATTEMPTS")
    assert indicator["severity"] == "ELEVATED_RISK_INDICATOR"
    assert indicator["evidence"]["event_count"] == 3


def test_denied_attempts_below_threshold_not_flagged(db_session):
    """False-positive boundary: 2 denials (threshold is 3) must not trigger."""
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for i in range(2):
        _event(db_session, door, user=staff, method="card", result="denied", at=base + datetime.timedelta(minutes=i))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "REPEATED_DENIED_ATTEMPTS" not in [i["rule"] for i in report["indicators"]]


def test_denied_attempts_spread_outside_window_not_clustered(db_session):
    """False-positive boundary: 3 denials 20 minutes apart (window is 15
    minutes) must NOT be treated as one burst."""
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for i in range(3):
        _event(db_session, door, user=staff, method="card", result="denied", at=base + datetime.timedelta(minutes=i * 20))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "REPEATED_DENIED_ATTEMPTS" not in [i["rule"] for i in report["indicators"]]


# ---------------------------------------------------------------------------
# Rapid repeated attempts (short window, any result)
# ---------------------------------------------------------------------------
def test_rapid_repeated_attempts_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for i in range(5):
        _event(db_session, door, user=staff, method="card",
               result="granted" if i % 2 == 0 else "denied", at=base + datetime.timedelta(minutes=i))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "REPEATED_ATTEMPTS_SHORT_WINDOW" in [i["rule"] for i in report["indicators"]]


# ---------------------------------------------------------------------------
# Unusual access time
# ---------------------------------------------------------------------------
def test_unusual_access_time_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    _event(db_session, door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 24, 3, 0))  # 3 AM UTC

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    indicator = next(i for i in report["indicators"] if i["rule"] == "UNUSUAL_ACCESS_TIME")
    assert indicator["severity"] == "UNUSUAL"


def test_daytime_access_not_flagged_as_unusual_time(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    _event(db_session, door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 24, 14, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "UNUSUAL_ACCESS_TIME" not in [i["rule"] for i in report["indicators"]]


# ---------------------------------------------------------------------------
# Unusual door for user
# ---------------------------------------------------------------------------
def test_unusual_door_flagged_once_then_learned(db_session):
    door = _door(db_session)
    other_door = _door(db_session, code="AN102")
    staff = _staff(db_session)
    db_session.add(models.DoorAssignment(door_id=door.door_id, instructor_id=staff.user_id))
    db_session.commit()

    # Two granted visits to a door they have no assignment or window for.
    _event(db_session, other_door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 20, 10, 0))
    _event(db_session, other_door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 21, 10, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    unusual_door = [i for i in report["indicators"] if i["rule"] == "UNUSUAL_DOOR_FOR_USER"]
    assert len(unusual_door) == 1  # only flagged the first time, not the second


# ---------------------------------------------------------------------------
# Access outside authorized schedule
# ---------------------------------------------------------------------------
def test_granted_access_with_no_authorization_record_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    # No DoorAssignment, no AccessWindow — but a "granted" event exists anyway.
    _event(db_session, door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 24, 11, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" in [i["rule"] for i in report["indicators"]]


def test_granted_access_within_active_window_not_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    db_session.add(models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=True,
        day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0),
    ))
    db_session.commit()
    _event(db_session, door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 24, 11, 0))  # Thursday, within the window

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


def test_override_method_excluded_from_schedule_rule(db_session):
    """An admin override is already its own audited action — must not be
    flagged as an anomaly by this rule."""
    door = _door(db_session)
    staff = _staff(db_session)
    _event(db_session, door, user=staff, method="override", result="granted",
           at=datetime.datetime(2026, 9, 24, 11, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


# ---------------------------------------------------------------------------
# Access after temporary expiration
# ---------------------------------------------------------------------------
def test_access_after_temporary_window_expiration_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="External Lecturer Anom")
    db_session.add(models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=False,
        start_at=datetime.datetime(2026, 9, 24, 10, 0), end_at=datetime.datetime(2026, 9, 24, 14, 0),
        reason="Network maintenance",
    ))
    db_session.commit()
    # Attempt 2 hours after the window ended, with nothing else authorizing it.
    _event(db_session, door, user=staff, method="card", result="denied",
           at=datetime.datetime(2026, 9, 24, 16, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    indicator = next(i for i in report["indicators"] if i["rule"] == "ACCESS_AFTER_TEMPORARY_EXPIRATION")
    assert indicator["evidence"]["access_window_id"] is not None


def test_access_within_temporary_window_not_flagged_as_after_expiration(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="External Lecturer Anom2")
    db_session.add(models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=False,
        start_at=datetime.datetime(2026, 9, 24, 10, 0), end_at=datetime.datetime(2026, 9, 24, 14, 0),
    ))
    db_session.commit()
    _event(db_session, door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 24, 12, 0))  # still within the window

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_AFTER_TEMPORARY_EXPIRATION" not in [i["rule"] for i in report["indicators"]]


def test_access_long_after_expiration_beyond_followup_not_flagged(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="External Lecturer Anom3")
    db_session.add(models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=False,
        start_at=datetime.datetime(2026, 9, 1, 10, 0), end_at=datetime.datetime(2026, 9, 1, 14, 0),
    ))
    db_session.commit()
    # Three weeks later — well beyond the 24h follow-up horizon.
    _event(db_session, door, user=staff, method="card", result="denied", at=datetime.datetime(2026, 9, 22, 10, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_AFTER_TEMPORARY_EXPIRATION" not in [i["rule"] for i in report["indicators"]]


# ---------------------------------------------------------------------------
# Time window / lookback
# ---------------------------------------------------------------------------
def test_events_outside_lookback_window_ignored(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    old_events_time = base - datetime.timedelta(days=60)
    for i in range(3):
        _event(db_session, door, user=staff, method="card", result="denied", at=old_events_time + datetime.timedelta(minutes=i))

    report = anomalies.detect_anomalies_for_user(db_session, staff, since_days=30, now=NOW)
    assert report["indicators"] == []
    assert report["event_count_considered"] == 0


# ---------------------------------------------------------------------------
# Door-centric view
# ---------------------------------------------------------------------------
def test_door_anomaly_report_groups_by_staff(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for i in range(3):
        _event(db_session, door, user=staff, method="card", result="denied", at=base + datetime.timedelta(minutes=i * 2))

    report = anomalies.detect_anomalies_for_door(db_session, door, now=NOW)
    assert report["door_id"] == door.door_id
    assert len(report["staff"]) == 1
    assert report["staff"][0]["user_id"] == staff.user_id


# ---------------------------------------------------------------------------
# API + scope isolation
# ---------------------------------------------------------------------------
def test_staff_can_view_own_anomaly_report_via_api(db_session, client):
    door = _door(db_session)
    staff = _staff(db_session, name="Self Report Doc", role="doctor")
    _event(db_session, door, user=staff, method="card", result="granted", at=datetime.datetime(2026, 9, 24, 11, 0))

    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/staff/{staff.user_id}/anomalies", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["user_id"] == staff.user_id


def test_staff_cannot_view_someone_elses_anomaly_report(db_session, client):
    staff = _staff(db_session, name="Viewer Doc")
    other = _staff(db_session, name="Victim Doc")

    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/staff/{other.user_id}/anomalies", headers=headers)
    assert resp.status_code == 403


def test_scoped_admin_cannot_view_anomalies_for_other_college_staff(db_session, client, admin_token):
    eng = models.Faculty(name="Faculty of Engineering AN")
    other = models.Faculty(name="Faculty of Business AN")
    db_session.add_all([eng, other])
    db_session.commit()
    other_staff = _staff(db_session, name="Business Doc AN", faculty_id=other.faculty_id)

    eng_admin = models.User(name="Eng Admin AN", email="eng.admin.an@example.edu", role="admin",
                             password_hash=security.hash_password("pw123456"))
    db_session.add(eng_admin)
    db_session.commit()
    db_session.add(models.AdminScope(user_id=eng_admin.user_id, faculty_id=eng.faculty_id))
    db_session.commit()

    login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/staff/{other_staff.user_id}/anomalies", headers=headers)
    assert resp.status_code == 403


def test_door_anomalies_endpoint_admin_only(db_session, client):
    door = _door(db_session)
    staff = _staff(db_session, name="Non Admin Viewer")
    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=headers)
    assert resp.status_code == 403


def test_door_anomalies_endpoint_works_for_admin(db_session, client, admin_token):
    door = _door(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["door_id"] == door.door_id


# ---------------------------------------------------------------------------
# Stage D / D0 hardening: GET /api/doors/{id}/anomalies must drop staff rows
# a scoped admin isn't authorized to see (same pattern as the access-windows
# fix), while an unrestricted admin's view is unaffected.
# ---------------------------------------------------------------------------
def _scoped_admin(db, faculty_id, name="Scoped Admin AN"):
    admin = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id))
    db.commit()
    db.refresh(admin)
    return admin


def test_unrestricted_admin_sees_all_staff_rows_for_door_anomalies(db_session, client, admin_token):
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering AN2")
    biz = models.Faculty(name="Faculty of Business AN2")
    db_session.add_all([eng, biz])
    db_session.commit()
    eng_staff = _staff(db_session, name="Eng Doc AN2", faculty_id=eng.faculty_id)
    biz_staff = _staff(db_session, name="Biz Doc AN2", faculty_id=biz.faculty_id)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for staff in (eng_staff, biz_staff):
        for i in range(3):
            _event(db_session, door, user=staff, method="card", result="denied",
                   at=base + datetime.timedelta(minutes=i * 2))

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=headers)
    assert resp.status_code == 200
    seen_ids = {row["user_id"] for row in resp.json()["staff"]}
    assert eng_staff.user_id in seen_ids
    assert biz_staff.user_id in seen_ids


def test_scoped_admin_only_sees_in_scope_staff_for_door_anomalies(db_session, client):
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering AN3")
    biz = models.Faculty(name="Faculty of Business AN3")
    db_session.add_all([eng, biz])
    db_session.commit()
    eng_staff = _staff(db_session, name="Eng Doc AN3", faculty_id=eng.faculty_id)
    biz_staff = _staff(db_session, name="Biz Doc AN3", faculty_id=biz.faculty_id)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for staff in (eng_staff, biz_staff):
        for i in range(3):
            _event(db_session, door, user=staff, method="card", result="denied",
                   at=base + datetime.timedelta(minutes=i * 2))

    eng_admin = _scoped_admin(db_session, eng.faculty_id, name="Eng Admin AN3")
    login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    seen_ids = {row["user_id"] for row in body["staff"]}
    assert eng_staff.user_id in seen_ids
    assert biz_staff.user_id not in seen_ids
    # Summary counts must be recomputed from the filtered rows, not the
    # original unfiltered report — otherwise the totals would silently leak
    # that out-of-scope activity exists even though the row itself is gone.
    assert body["summary"]["ELEVATED_RISK_INDICATOR"] == 1


def test_two_admin_scopes_remain_isolated_for_door_anomalies(db_session, client):
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering AN4")
    biz = models.Faculty(name="Faculty of Business AN4")
    db_session.add_all([eng, biz])
    db_session.commit()
    eng_staff = _staff(db_session, name="Eng Doc AN4", faculty_id=eng.faculty_id)
    biz_staff = _staff(db_session, name="Biz Doc AN4", faculty_id=biz.faculty_id)
    base = datetime.datetime(2026, 9, 24, 10, 0)
    for staff in (eng_staff, biz_staff):
        for i in range(3):
            _event(db_session, door, user=staff, method="card", result="denied",
                   at=base + datetime.timedelta(minutes=i * 2))

    eng_admin = _scoped_admin(db_session, eng.faculty_id, name="Eng Admin AN4")
    biz_admin = _scoped_admin(db_session, biz.faculty_id, name="Biz Admin AN4")

    eng_login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    eng_headers = {"Authorization": f"Bearer {eng_login.json()['access_token']}"}
    eng_resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=eng_headers)
    assert {row["user_id"] for row in eng_resp.json()["staff"]} == {eng_staff.user_id}

    biz_login = client.post("/api/auth/login", json={"email": biz_admin.email, "password": "pw123456"})
    biz_headers = {"Authorization": f"Bearer {biz_login.json()['access_token']}"}
    biz_resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=biz_headers)
    assert {row["user_id"] for row in biz_resp.json()["staff"]} == {biz_staff.user_id}


def test_door_anomalies_non_admin_behavior_unchanged(db_session, client):
    door = _door(db_session)
    staff = _staff(db_session, name="Non Admin Viewer AN5")
    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = client.get(f"/api/doors/{door.door_id}/anomalies", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Anomaly Evidence Hardening — historical events must key off their own
# recorded evidence_snapshot, not today's AccessWindow rows.
# ---------------------------------------------------------------------------
def _recorded_authorized_evidence(db, user, door, at):
    """Builds the same evidence shape mqtt_service.py / log_authorization_check
    would have frozen onto the event at the time it happened."""
    evaluation = access_authorization_service.evaluate_door_authorization(db, user, door, now=at)
    return access_authorization_service.build_authorization_evidence(
        evaluation, source=access_authorization_service.EVIDENCE_SOURCE_PHYSICAL_DOOR_NODE,
    )


def test_evidence_survives_window_deletion(db_session):
    """(a) Access was authorized; the AccessWindow is later deleted. The
    historical event must NOT become anomalous merely because the window no
    longer exists — its frozen evidence says it was authorized at the time."""
    door = _door(db_session)
    staff = _staff(db_session, name="Evidence Survivor A")
    event_time = datetime.datetime(2026, 9, 24, 11, 0)  # Thursday, 10-12 window
    window = models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=True,
        day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0),
    )
    db_session.add(window)
    db_session.commit()

    evidence = _recorded_authorized_evidence(db_session, staff, door, event_time)
    assert evidence["authorized"] is True
    _event(db_session, door, user=staff, method="card", result="granted", at=event_time, evidence=evidence)

    # The window is deleted entirely — a live re-evaluation would now find
    # nothing authorizing this access.
    db_session.delete(window)
    db_session.commit()

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


def test_evidence_survives_window_modification(db_session):
    """(b) Access was authorized; the window is later modified (its hours
    changed so it would no longer cover the original event). Historical
    interpretation must remain based on the original recorded evidence, not
    the window's new shape."""
    door = _door(db_session)
    staff = _staff(db_session, name="Evidence Survivor B")
    event_time = datetime.datetime(2026, 9, 24, 11, 0)  # Thursday, 10-12 window
    window = models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=True,
        day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0),
    )
    db_session.add(window)
    db_session.commit()

    evidence = _recorded_authorized_evidence(db_session, staff, door, event_time)
    assert evidence["authorized"] is True
    _event(db_session, door, user=staff, method="card", result="granted", at=event_time, evidence=evidence)

    # Window is edited afterward to a completely different time range that
    # would NOT have covered the original event.
    window.start_time = datetime.time(15, 0)
    window.end_time = datetime.time(17, 0)
    db_session.commit()

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


def test_legitimate_access_within_temporary_window_stays_legitimate_after_expiry(db_session):
    """(c) A legitimate access event occurred inside a temporary window that
    has SINCE expired (relative to the report's "now"). The event must
    remain legitimate — not retroactively flagged by either the schedule
    rule or the post-expiration rule."""
    door = _door(db_session)
    staff = _staff(db_session, name="Evidence Survivor C")
    window = models.AccessWindow(
        door_id=door.door_id, user_id=staff.user_id, recurring=False,
        start_at=datetime.datetime(2026, 9, 1, 10, 0), end_at=datetime.datetime(2026, 9, 1, 14, 0),
        reason="One-off maintenance visit",
    )
    db_session.add(window)
    db_session.commit()

    event_time = datetime.datetime(2026, 9, 1, 12, 0)  # inside the window
    evidence = _recorded_authorized_evidence(db_session, staff, door, event_time)
    assert evidence["authorized"] is True
    _event(db_session, door, user=staff, method="card", result="granted", at=event_time, evidence=evidence)

    # Report is evaluated well after the window's own end_at.
    report = anomalies.detect_anomalies_for_user(db_session, staff, since_days=60,
                                                  now=datetime.datetime(2026, 9, 24, 18, 0))
    rules = [i["rule"] for i in report["indicators"]]
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in rules
    assert "ACCESS_AFTER_TEMPORARY_EXPIRATION" not in rules


def test_override_event_correctly_classified_and_audited(db_session):
    """(d) An admin override/emergency event must stay excluded from the
    WHO/WHEN authorization rules (it's already its own audited action — see
    _ENTRY_METHODS), and its evidence must be properly attributable to the
    acting admin rather than read as an ordinary authorization decision."""
    door = _door(db_session)
    staff = _staff(db_session, name="Evidence Survivor D")
    admin = models.User(name="Override Admin AN", email="override.admin.an@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db_session.add(admin)
    db_session.commit()

    evidence = access_authorization_service.build_override_evidence(action="unlock", actor=admin)
    assert evidence["authorization_source"] == access_authorization_service.EVIDENCE_SOURCE_ADMIN_OVERRIDE
    assert evidence["authorized"] is None
    event = _event(db_session, door, user=admin, method="override", result="sent",
                   at=datetime.datetime(2026, 9, 24, 3, 0), evidence=evidence)

    # Correctly audited: the evidence names the real actor.
    stored = json.loads(event.evidence_snapshot)
    assert stored["actor_user_id"] == admin.user_id

    # Correctly classified: an override is not a WHO/WHEN decision, so it
    # must not trip the schedule-authorization rule even though it happened
    # at an unusual hour and no window covers the admin at this door.
    report = anomalies.detect_anomalies_for_user(db_session, admin, now=NOW)
    assert "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE" not in [i["rule"] for i in report["indicators"]]


def test_legacy_event_without_snapshot_falls_back_safely(db_session):
    """(e) An old event with no evidence_snapshot at all (pre-hardening)
    must still be analyzed safely via the current-state fallback path, and
    the resulting indicator must be clearly tagged as fallback-based rather
    than silently indistinguishable from a recorded-evidence indicator."""
    door = _door(db_session)
    staff = _staff(db_session, name="Legacy Event Staff")
    # No AccessWindow, no DoorAssignment, no evidence_snapshot at all.
    _event(db_session, door, user=staff, method="card", result="granted",
           at=datetime.datetime(2026, 9, 24, 11, 0))

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    indicator = next(i for i in report["indicators"] if i["rule"] == "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE")
    assert indicator["evidence"]["evidence_basis"] == anomalies.BASIS_FALLBACK


def test_recorded_evidence_basis_tagged_when_snapshot_present(db_session):
    """Companion check: when a usable snapshot IS present but still denotes
    an unauthorized access, the indicator must be tagged as recorded rather
    than fallback."""
    door = _door(db_session)
    staff = _staff(db_session, name="Recorded Denial Staff")
    event_time = datetime.datetime(2026, 9, 24, 11, 0)
    evidence = _recorded_authorized_evidence(db_session, staff, door, event_time)
    assert evidence["authorized"] is False  # no window/assignment exists for this user at all
    _event(db_session, door, user=staff, method="card", result="granted", at=event_time, evidence=evidence)

    report = anomalies.detect_anomalies_for_user(db_session, staff, now=NOW)
    indicator = next(i for i in report["indicators"] if i["rule"] == "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE")
    assert indicator["evidence"]["evidence_basis"] == anomalies.BASIS_RECORDED
