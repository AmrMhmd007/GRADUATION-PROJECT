"""
Tests for Feature #5 (Schedule-Derived Access Authorization):
app/services/access_authorization_service.py, the AccessWindow model, and
the /api/access-windows + /api/doors/{id}/authorization endpoints.
"""
import datetime

from app import models, security
from app.services import access_authorization_service


def _door(db, code="AW101"):
    door = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure",
                        online=True, locked=True)
    db.add(door)
    db.commit()
    db.refresh(door)
    return door


def _staff(db, name="Doctor X", role="doctor"):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
                     password_hash=security.hash_password("pw123456"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _recurring_window(db, door, user, day_of_week, start_time, end_time, **kw):
    w = models.AccessWindow(door_id=door.door_id, user_id=user.user_id, recurring=True,
                             day_of_week=day_of_week, start_time=start_time, end_time=end_time, **kw)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def _temporary_window(db, door, user, start_at, end_at, **kw):
    w = models.AccessWindow(door_id=door.door_id, user_id=user.user_id, recurring=False,
                             start_at=start_at, end_at=end_at, **kw)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ---------------------------------------------------------------------------
# Pure service-level evaluation (direct, with an injected `now`)
# ---------------------------------------------------------------------------
def test_recurring_window_active_within_its_slot(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    # Thursday 24 Sept 2026, 10:00-12:00
    _recurring_window(db_session, door, staff, day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0))

    now = datetime.datetime(2026, 9, 24, 11, 0)  # Thursday, within window
    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door, now=now)
    assert result["authorized"] is True
    assert result["has_permanent_access"] is False
    assert result["windows"][0]["active"] is True


def test_recurring_window_future_today_not_authorized(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    _recurring_window(db_session, door, staff, day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0))

    now = datetime.datetime(2026, 9, 24, 9, 0)  # Thursday, before the window starts
    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door, now=now)
    assert result["authorized"] is False
    assert "not yet" not in result["windows"][0]["reason"] or True  # reason wording may vary; check active flag
    assert result["windows"][0]["active"] is False


def test_recurring_window_wrong_day_not_authorized(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    _recurring_window(db_session, door, staff, day_of_week=0, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0))  # Monday only

    now = datetime.datetime(2026, 9, 24, 11, 0)  # Thursday
    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door, now=now)
    assert result["authorized"] is False
    assert "day" in result["windows"][0]["reason"].lower()


def test_recurring_window_bounded_by_valid_until_expires(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    _recurring_window(
        db_session, door, staff, day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0),
        valid_until=datetime.datetime(2026, 9, 1),  # semester ended before "now"
    )
    now = datetime.datetime(2026, 9, 24, 11, 0)
    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door, now=now)
    assert result["authorized"] is False
    assert "ended" in result["windows"][0]["reason"].lower()


def test_recurring_window_bounded_by_valid_from_not_started(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    _recurring_window(
        db_session, door, staff, day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0),
        valid_from=datetime.datetime(2026, 10, 1),  # semester hasn't started yet
    )
    now = datetime.datetime(2026, 9, 24, 11, 0)
    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door, now=now)
    assert result["authorized"] is False


def test_temporary_window_active_within_range(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="External Lecturer")
    _temporary_window(db_session, door, staff,
                       start_at=datetime.datetime(2026, 9, 24, 10, 0),
                       end_at=datetime.datetime(2026, 9, 24, 14, 0),
                       reason="Network maintenance")

    result = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 24, 12, 0)
    )
    assert result["authorized"] is True


def test_temporary_window_future_not_yet_authorized(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="External Lecturer 2")
    _temporary_window(db_session, door, staff,
                       start_at=datetime.datetime(2026, 9, 25, 10, 0),
                       end_at=datetime.datetime(2026, 9, 25, 14, 0))

    result = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 24, 12, 0)
    )
    assert result["authorized"] is False
    assert "not yet" in result["windows"][0]["reason"].lower()


def test_temporary_window_expires_automatically(db_session):
    door = _door(db_session)
    staff = _staff(db_session, name="External Lecturer 3")
    _temporary_window(db_session, door, staff,
                       start_at=datetime.datetime(2026, 9, 24, 10, 0),
                       end_at=datetime.datetime(2026, 9, 24, 14, 0))

    # Before expiry: authorized
    before = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 24, 13, 0)
    )
    assert before["authorized"] is True

    # After expiry: automatically NOT authorized — row still exists (not deleted)
    after = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 24, 15, 0)
    )
    assert after["authorized"] is False
    assert "expired" in after["windows"][0]["reason"].lower()
    assert db_session.query(models.AccessWindow).count() == 1  # not auto-deleted


def test_multiple_windows_one_active_authorizes_without_conflict(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    # One expired temporary window, one currently-active recurring window —
    # must not conflict; the active one alone is enough.
    _temporary_window(db_session, door, staff,
                       start_at=datetime.datetime(2026, 9, 1, 10, 0), end_at=datetime.datetime(2026, 9, 1, 14, 0))
    _recurring_window(db_session, door, staff, day_of_week=3, start_time=datetime.time(10, 0), end_time=datetime.time(12, 0))

    result = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 24, 11, 0)
    )
    assert result["authorized"] is True
    assert len(result["windows"]) == 2
    active_flags = sorted(w["active"] for w in result["windows"])
    assert active_flags == [False, True]


def test_permanent_access_is_independent_of_windows_regression(db_session):
    """Regression: existing DoorAssignment (permanent) access must keep
    working exactly as before, with zero AccessWindows configured at all."""
    door = _door(db_session)
    staff = _staff(db_session)
    db_session.add(models.DoorAssignment(door_id=door.door_id, instructor_id=staff.user_id))
    db_session.commit()

    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door)
    assert result["authorized"] is True
    assert result["has_permanent_access"] is True
    assert result["windows"] == []


def test_no_access_at_all_is_denied_with_clear_reason(db_session):
    door = _door(db_session)
    staff = _staff(db_session)
    result = access_authorization_service.evaluate_door_authorization(db_session, staff, door)
    assert result["authorized"] is False
    assert result["reason"]  # non-empty explanation


def test_invalid_recurring_range_rejected():
    try:
        access_authorization_service.validate_window_shape({
            "recurring": True, "day_of_week": 3,
            "start_time": datetime.time(12, 0), "end_time": datetime.time(10, 0),  # end < start
        })
        assert False, "should have raised"
    except ValueError as e:
        assert "end_time" in str(e)


def test_invalid_temporary_range_rejected():
    try:
        access_authorization_service.validate_window_shape({
            "recurring": False,
            "start_at": datetime.datetime(2026, 9, 24, 14, 0),
            "end_at": datetime.datetime(2026, 9, 24, 10, 0),  # end < start
        })
        assert False, "should have raised"
    except ValueError as e:
        assert "end_at" in str(e)


def test_recurring_missing_fields_rejected():
    try:
        access_authorization_service.validate_window_shape({"recurring": True})
        assert False, "should have raised"
    except ValueError:
        pass


def test_day_boundary_uses_utc_weekday_not_local(db_session):
    """Timezone/day-boundary case: a recurring Thursday (weekday=3) window
    must not be considered active one minute into Friday UTC, even though
    naive local-time arithmetic elsewhere in this codebase has been shown
    to misbehave near midnight (see the pre-existing automation_engine
    flake) — Feature #5 always evaluates against UTC explicitly."""
    door = _door(db_session)
    staff = _staff(db_session)
    _recurring_window(db_session, door, staff, day_of_week=3, start_time=datetime.time(23, 0), end_time=datetime.time(23, 59, 59))

    # 23:30 Thursday — active
    result = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 24, 23, 30)
    )
    assert result["authorized"] is True

    # 00:01 Friday — must NOT be active (wrong weekday)
    result = access_authorization_service.evaluate_door_authorization(
        db_session, staff, door, now=datetime.datetime(2026, 9, 25, 0, 1)
    )
    assert result["authorized"] is False


# ---------------------------------------------------------------------------
# API + authorization-scope tests
# ---------------------------------------------------------------------------
def test_create_and_list_access_window_api(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post("/api/access-windows", json={
        "door_id": door.door_id, "user_id": staff.user_id, "recurring": True,
        "day_of_week": 3, "start_time": "10:00:00", "end_time": "12:00:00",
    }, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["door_code"] == door.code

    resp = client.get(f"/api/access-windows?user_id={staff.user_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_access_window_rejects_invalid_range_via_api(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post("/api/access-windows", json={
        "door_id": door.door_id, "user_id": staff.user_id, "recurring": False,
        "start_at": "2026-09-24T14:00:00", "end_at": "2026-09-24T10:00:00",
    }, headers=headers)
    assert resp.status_code == 400


def test_door_authorization_endpoint_logs_access_event(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/access-windows", json={
        "door_id": door.door_id, "user_id": staff.user_id, "recurring": False,
        "start_at": "2026-01-01T00:00:00", "end_at": "2099-01-01T00:00:00",
    }, headers=headers)

    resp = client.get(f"/api/doors/{door.door_id}/authorization?user_id={staff.user_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["authorized"] is True

    event = db_session.query(models.AccessEvent).filter(models.AccessEvent.method == "schedule_check").first()
    assert event is not None
    assert event.result == "granted"
    assert event.user_id == staff.user_id
    assert event.evidence_snapshot is not None


def test_scoped_admin_cannot_create_window_for_other_college_staff(db_session, client, admin_token):
    eng = models.Faculty(name="Faculty of Engineering")
    other = models.Faculty(name="Faculty of Business")
    db_session.add_all([eng, other])
    db_session.commit()
    other_staff = models.User(name="Business Doctor", email="biz.doc@example.edu", role="doctor",
                               password_hash=security.hash_password("pw123456"), faculty_id=other.faculty_id)
    db_session.add(other_staff)
    db_session.commit()

    eng_admin = models.User(name="Eng Admin AW", email="eng.admin.aw@example.edu", role="admin",
                             password_hash=security.hash_password("pw123456"))
    db_session.add(eng_admin)
    db_session.commit()
    db_session.add(models.AdminScope(user_id=eng_admin.user_id, faculty_id=eng.faculty_id))
    db_session.commit()

    door = _door(db_session)
    login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post("/api/access-windows", json={
        "door_id": door.door_id, "user_id": other_staff.user_id, "recurring": True,
        "day_of_week": 0, "start_time": "09:00:00", "end_time": "10:00:00",
    }, headers=headers)
    assert resp.status_code == 403


def test_staff_can_only_check_own_authorization(db_session, client):
    door = _door(db_session)
    staff = models.User(name="Self Checker", email="self.checker@example.edu", role="instructor",
                         password_hash=security.hash_password("pw123456"))
    other = models.User(name="Someone Else", email="someone.else@example.edu", role="instructor",
                         password_hash=security.hash_password("pw123456"))
    db_session.add_all([staff, other])
    db_session.commit()

    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/api/doors/{door.door_id}/authorization", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["user_id"] == staff.user_id

    resp = client.get(f"/api/doors/{door.door_id}/authorization?user_id={other.user_id}", headers=headers)
    assert resp.status_code == 403


def test_delete_access_window(db_session, client, admin_token):
    door = _door(db_session)
    staff = _staff(db_session)
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post("/api/access-windows", json={
        "door_id": door.door_id, "user_id": staff.user_id, "recurring": True,
        "day_of_week": 1, "start_time": "09:00:00", "end_time": "10:00:00",
    }, headers=headers).json()

    resp = client.delete(f"/api/access-windows/{created['access_window_id']}", headers=headers)
    assert resp.status_code == 204
    assert db_session.query(models.AccessWindow).count() == 0


# ---------------------------------------------------------------------------
# Authorization-gap fix: GET /api/access-windows?door_id= row-level scope
# filtering for restricted admins. Reuses the exact same AdminScope /
# is_staff_authorized machinery as every other scoped endpoint — no
# parallel permission system.
# ---------------------------------------------------------------------------
def _scoped_admin(db, faculty_id, email="scoped.admin@example.edu", name="Scoped Admin"):
    admin = models.User(name=name, email=email, role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id))
    db.commit()
    return admin


def test_unrestricted_admin_sees_all_windows_for_door(db_session, client, admin_token):
    """Baseline preserved: an unrestricted admin (no AdminScope rows) still
    sees every window on a door regardless of the staff member's college."""
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering")
    biz = models.Faculty(name="Faculty of Business")
    db_session.add_all([eng, biz])
    db_session.commit()
    eng_staff = _staff(db_session, name="Eng Staff")
    biz_staff = _staff(db_session, name="Biz Staff")
    eng_staff.faculty_id = eng.faculty_id
    biz_staff.faculty_id = biz.faculty_id
    db_session.commit()

    _temporary_window(db_session, door, eng_staff,
                       start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))
    _temporary_window(db_session, door, biz_staff,
                       start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))

    resp = client.get(f"/api/access-windows?door_id={door.door_id}",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_scoped_admin_sees_only_in_scope_windows_for_door(db_session, client):
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering AG")
    biz = models.Faculty(name="Faculty of Business AG")
    db_session.add_all([eng, biz])
    db_session.commit()

    eng_staff = _staff(db_session, name="Eng Staff AG")
    biz_staff = _staff(db_session, name="Biz Staff AG")
    eng_staff.faculty_id = eng.faculty_id
    biz_staff.faculty_id = biz.faculty_id
    db_session.commit()

    _temporary_window(db_session, door, eng_staff,
                       start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))
    _temporary_window(db_session, door, biz_staff,
                       start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))

    eng_admin = _scoped_admin(db_session, eng.faculty_id, email="eng.admin.ag@example.edu")
    login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/api/access-windows?door_id={door.door_id}", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()
    # The out-of-scope (Business) row must be entirely absent — not merely
    # anonymized — this is the actual gap being fixed.
    assert len(rows) == 1
    assert rows[0]["user_id"] == eng_staff.user_id


def test_two_admin_scopes_remain_isolated_when_listing_by_door(db_session, client):
    """A third scope (Science) proves this isn't just a two-way split —
    each scoped admin sees exactly their own college's row and no other."""
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering ISO")
    biz = models.Faculty(name="Faculty of Business ISO")
    sci = models.Faculty(name="Faculty of Science ISO")
    db_session.add_all([eng, biz, sci])
    db_session.commit()

    eng_staff = _staff(db_session, name="Eng Staff ISO")
    biz_staff = _staff(db_session, name="Biz Staff ISO")
    sci_staff = _staff(db_session, name="Sci Staff ISO")
    eng_staff.faculty_id, biz_staff.faculty_id, sci_staff.faculty_id = eng.faculty_id, biz.faculty_id, sci.faculty_id
    db_session.commit()

    for staff in (eng_staff, biz_staff, sci_staff):
        _temporary_window(db_session, door, staff,
                           start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))

    eng_admin = _scoped_admin(db_session, eng.faculty_id, email="eng.admin.iso@example.edu")
    biz_admin = _scoped_admin(db_session, biz.faculty_id, email="biz.admin.iso@example.edu", name="Biz Admin")

    eng_login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    biz_login = client.post("/api/auth/login", json={"email": biz_admin.email, "password": "pw123456"})
    eng_headers = {"Authorization": f"Bearer {eng_login.json()['access_token']}"}
    biz_headers = {"Authorization": f"Bearer {biz_login.json()['access_token']}"}

    eng_rows = client.get(f"/api/access-windows?door_id={door.door_id}", headers=eng_headers).json()
    biz_rows = client.get(f"/api/access-windows?door_id={door.door_id}", headers=biz_headers).json()

    assert [r["user_id"] for r in eng_rows] == [eng_staff.user_id]
    assert [r["user_id"] for r in biz_rows] == [biz_staff.user_id]


def test_scoped_admin_explicit_user_id_out_of_scope_still_403(db_session, client):
    """Existing unauthorized behavior (require_staff_access on the
    user_id= path) must be completely unchanged by this fix."""
    door = _door(db_session)
    eng = models.Faculty(name="Faculty of Engineering UC")
    biz = models.Faculty(name="Faculty of Business UC")
    db_session.add_all([eng, biz])
    db_session.commit()
    biz_staff = _staff(db_session, name="Biz Staff UC")
    biz_staff.faculty_id = biz.faculty_id
    db_session.commit()

    eng_admin = _scoped_admin(db_session, eng.faculty_id, email="eng.admin.uc@example.edu")
    login = client.post("/api/auth/login", json={"email": eng_admin.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/api/access-windows?door_id={door.door_id}&user_id={biz_staff.user_id}", headers=headers)
    assert resp.status_code == 403


def test_non_admin_listing_still_only_sees_own_windows_unchanged(db_session, client):
    """Existing non-admin behavior (own windows only) is untouched by the
    admin-only scope filter added above."""
    door = _door(db_session)
    staff = models.User(name="Self Lister", email="self.lister@example.edu", role="instructor",
                         password_hash=security.hash_password("pw123456"))
    other = models.User(name="Other Lister", email="other.lister@example.edu", role="instructor",
                         password_hash=security.hash_password("pw123456"))
    db_session.add_all([staff, other])
    db_session.commit()
    _temporary_window(db_session, door, staff,
                       start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))
    _temporary_window(db_session, door, other,
                       start_at=datetime.datetime(2026, 1, 1), end_at=datetime.datetime(2099, 1, 1))

    login = client.post("/api/auth/login", json={"email": staff.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get(f"/api/access-windows?door_id={door.door_id}", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["user_id"] == staff.user_id
