"""
Master UX pass — GET /api/audit-logs gained resource_id/q/since/until/offset
filters (all additive/optional) so a real Audit Log viewer can filter and
paginate against genuine backend query parameters instead of faking it
client-side. No existing parameter's behavior changed.
"""
import datetime

from app import models


def _admin(token):
    return {"Authorization": f"Bearer {token}"}


def test_filter_by_resource_id(client, admin_token):
    b1 = client.post("/api/buildings", json={"name": "Filter Hall One"}, headers=_admin(admin_token)).json()
    b2 = client.post("/api/buildings", json={"name": "Filter Hall Two"}, headers=_admin(admin_token)).json()

    resp = client.get("/api/audit-logs", params={"resource_type": "building", "resource_id": b1["building_id"]},
                       headers=_admin(admin_token))
    assert resp.status_code == 200
    rows = resp.json()
    assert all(r["resource_id"] == b1["building_id"] for r in rows)
    assert any(r["action"] == "create" for r in rows)
    assert not any(r["resource_id"] == b2["building_id"] for r in rows)


def test_search_q_matches_resource_label(client, admin_token):
    client.post("/api/buildings", json={"name": "Very Unique Search Target Hall"}, headers=_admin(admin_token))
    client.post("/api/buildings", json={"name": "Unrelated Hall"}, headers=_admin(admin_token))

    resp = client.get("/api/audit-logs", params={"q": "Unique Search Target"}, headers=_admin(admin_token))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert all("Unique Search Target" in (r["resource_label"] or "") for r in rows)


def test_since_until_bounds_filter_by_date(client, admin_token):
    """`AuditLog.timestamp` is always written with `datetime.datetime.utcnow()`
    (see services/audit_service.py) — the same UTC-only convention every
    other timestamp in this codebase uses. `since`/`until` are therefore UTC
    calendar-day bounds, not the local date of whatever machine runs this
    test — using `datetime.date.today()` (LOCAL date) here was the bug: near
    a UTC day boundary, local "today" and the UTC date the row was actually
    stamped with can be different calendar days, making this test flaky by
    time of day rather than by anything wrong with the endpoint. Anchoring on
    `datetime.datetime.utcnow().date()` matches the real contract and is
    deterministic regardless of the local timezone/clock the suite runs on."""
    client.post("/api/buildings", json={"name": "Date Bounded Hall"}, headers=_admin(admin_token))
    today = datetime.datetime.utcnow().date()

    in_range = client.get("/api/audit-logs", params={
        "q": "Date Bounded Hall", "since": today.isoformat(), "until": today.isoformat(),
    }, headers=_admin(admin_token))
    assert in_range.status_code == 200
    assert len(in_range.json()) >= 1

    yesterday = today - datetime.timedelta(days=1)
    out_of_range = client.get("/api/audit-logs", params={
        "q": "Date Bounded Hall", "since": (yesterday - datetime.timedelta(days=5)).isoformat(),
        "until": yesterday.isoformat(),
    }, headers=_admin(admin_token))
    assert out_of_range.status_code == 200
    assert out_of_range.json() == []


def test_since_until_bounds_are_utc_not_local_clock_dependent(db_session, client, admin_token):
    """Deterministic version of the above, independent of wall-clock time:
    plants an AuditLog row with an explicit, fixed UTC timestamp and proves
    since/until bound it by that UTC calendar date — this can't flake no
    matter what time of day (or what local timezone) the suite runs in."""
    fixed_utc = datetime.datetime(2030, 6, 15, 23, 45, 0)  # 15 June 2030, UTC
    row = models.AuditLog(
        timestamp=fixed_utc, action="create", resource_type="building",
        resource_label="Fixed UTC Timestamp Hall", result="success",
    )
    db_session.add(row)
    db_session.commit()

    same_utc_day = client.get("/api/audit-logs", params={
        "q": "Fixed UTC Timestamp Hall",
        "since": "2030-06-15", "until": "2030-06-15",
    }, headers=_admin(admin_token))
    assert same_utc_day.status_code == 200
    assert len(same_utc_day.json()) == 1

    next_utc_day_only = client.get("/api/audit-logs", params={
        "q": "Fixed UTC Timestamp Hall",
        "since": "2030-06-16", "until": "2030-06-16",
    }, headers=_admin(admin_token))
    assert next_utc_day_only.status_code == 200
    assert next_utc_day_only.json() == []


def test_offset_paginates_without_duplicates_or_gaps(client, admin_token):
    for i in range(5):
        client.post("/api/buildings", json={"name": f"Page Hall {i}"}, headers=_admin(admin_token))

    page1 = client.get("/api/audit-logs", params={"q": "Page Hall", "limit": 2, "offset": 0},
                        headers=_admin(admin_token)).json()
    page2 = client.get("/api/audit-logs", params={"q": "Page Hall", "limit": 2, "offset": 2},
                        headers=_admin(admin_token)).json()
    assert len(page1) == 2
    assert len(page2) == 2
    ids1 = {r["log_id"] for r in page1}
    ids2 = {r["log_id"] for r in page2}
    assert ids1.isdisjoint(ids2)


def test_scoped_admin_still_403s_with_new_filters(client, db_session, admin_token):
    from app import security

    faculty = models.Faculty(name="Filter Scope College")
    db_session.add(faculty)
    db_session.commit()
    db_session.refresh(faculty)
    scoped = models.User(name="Filter Scoped Admin", email="filter.scoped.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(scoped)
    db_session.commit()
    db_session.refresh(scoped)
    db_session.add(models.AdminScope(user_id=scoped.user_id, faculty_id=faculty.faculty_id))
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": scoped.email, "password": "pw123456"})
    scoped_token = login.json()["access_token"]

    resp = client.get("/api/audit-logs", params={"q": "anything"}, headers=_admin(scoped_token))
    assert resp.status_code == 403
