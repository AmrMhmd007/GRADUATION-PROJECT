"""
Tests for Global Search (app/routers/search.py, app/services/search_service.py).

Mirrors the isolation-proof style already established in
test_command_center.py's _two_scope_fixture: two independent colleges/
operational scopes, each with their own door/staff/event/override, so scope
isolation is actually proven both directions rather than just "restricted
sees less".
"""
import datetime

from app import models, security
from app.services import emergency_override_service


def _door(db, code="SR101", name=None):
    d = models.Door(code=code, name=name or f"Room {code}", building="Building A",
                     fail_mode="secure", online=True, locked=True, category="access_service")
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _staff(db, name, role="doctor", faculty_id=None, department_id=None):
    u = models.User(
        name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
        password_hash=security.hash_password("pw123456"), faculty_id=faculty_id, department_id=department_id,
    )
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
    faculty_a = models.Faculty(name="Search Faculty Alpha")
    faculty_b = models.Faculty(name="Search Faculty Bravo")
    scope_a = models.OperationalScope(name="Search Scope Alpha", scope_type="HVAC")
    scope_b = models.OperationalScope(name="Search Scope Bravo", scope_type="ELECTRICAL")
    db.add_all([faculty_a, faculty_b, scope_a, scope_b])
    db.commit()

    dept_a = models.Department(faculty_id=faculty_a.faculty_id, name="Alpha Search Dept")
    dept_b = models.Department(faculty_id=faculty_b.faculty_id, name="Bravo Search Dept")
    db.add_all([dept_a, dept_b])
    db.commit()

    staff_a = _staff(db, "Zulfiqar Alpha Search", faculty_id=faculty_a.faculty_id, department_id=dept_a.department_id)
    staff_b = _staff(db, "Zulfiqar Bravo Search", faculty_id=faculty_b.faculty_id, department_id=dept_b.department_id)

    course_a = models.Course(department_id=dept_a.department_id, code="ALFA101", name="Zulfiqar Alpha Course")
    course_b = models.Course(department_id=dept_b.department_id, code="BRAV101", name="Zulfiqar Bravo Course")
    db.add_all([course_a, course_b])
    db.commit()

    door_a = _door(db, code="ZSA1", name="Zulfiqar Alpha Room")
    door_b = _door(db, code="ZSB1", name="Zulfiqar Bravo Room")

    admin_root = db.query(models.User).filter(models.User.role == "admin", models.User.email == "admin@example.edu").first()
    override_a = emergency_override_service.create_override(
        db, door=door_a, admin=admin_root, action="unlock", reason="Zulfiqar Alpha emergency",
        duration_minutes=10, operational_scope_id=scope_a.scope_id,
    )
    override_b = emergency_override_service.create_override(
        db, door=door_b, admin=admin_root, action="unlock", reason="Zulfiqar Bravo emergency",
        duration_minutes=10, operational_scope_id=scope_b.scope_id,
    )

    admin_a, token_a = _scoped_admin(db, client, "Scoped Search Admin A", faculty_id=faculty_a.faculty_id, operational_scope_id=scope_a.scope_id)
    admin_b, token_b = _scoped_admin(db, client, "Scoped Search Admin B", faculty_id=faculty_b.faculty_id, operational_scope_id=scope_b.scope_id)

    return {
        "faculty_a": faculty_a, "faculty_b": faculty_b, "dept_a": dept_a, "dept_b": dept_b,
        "staff_a": staff_a, "staff_b": staff_b, "course_a": course_a, "course_b": course_b,
        "door_a": door_a, "door_b": door_b, "override_a": override_a, "override_b": override_b,
        "token_a": token_a, "token_b": token_b,
    }


def _titles(body, type_=None):
    return {r["title"] for r in body["results"] if type_ is None or r["type"] == type_}


# ---------------------------------------------------------------------------
# Auth / validation
# ---------------------------------------------------------------------------
def test_search_requires_authentication(client):
    resp = client.get("/api/search", params={"q": "room"})
    assert resp.status_code == 401


def test_search_query_too_short_is_safe(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "a"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_too_short"] is True
    assert body["results"] == []


def test_search_empty_query_is_safe(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": ""}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["query_too_short"] is True


def test_search_nonexistent_query_returns_clean_empty_result(db_session, client, admin_token):
    _door(db_session, code="NX1", name="Nothing Matches This Room")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "zzz_definitely_not_a_real_thing_zzz"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_search_limit_is_bounded(db_session, client, admin_token):
    for i in range(15):
        _door(db_session, code=f"LIM{i}", name=f"Limit Test Room {i}")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "Limit Test", "limit": 5}, headers=headers)
    body = resp.json()
    doors = [r for r in body["results"] if r["type"] == "door"]
    assert len(doors) <= 5


def test_search_limit_out_of_range_rejected(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "room", "limit": 500}, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Unrestricted admin — full visibility, real results, correct navigation
# ---------------------------------------------------------------------------
def test_unrestricted_admin_finds_door_with_navigation_metadata(db_session, client, admin_token):
    door = _door(db_session, code="NAV1", name="Navigation Test Room")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "Navigation Test"}, headers=headers)
    body = resp.json()
    hit = next(r for r in body["results"] if r["type"] == "door")
    assert hit["id"] == door.door_id
    assert hit["nav_tab"] == "access"
    assert hit["nav_params"]["room"] == str(door.door_id)


def test_unrestricted_admin_finds_college_department_course_staff(db_session, client, admin_token):
    f = _two_scope_fixture(db_session, client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.get("/api/search", params={"q": "Search Faculty Alpha"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "college")
    assert hit["id"] == f["faculty_a"].faculty_id
    assert hit["nav_params"]["aa_college"] == str(f["faculty_a"].faculty_id)

    resp = client.get("/api/search", params={"q": "Alpha Search Dept"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "department")
    assert hit["id"] == f["dept_a"].department_id
    assert hit["nav_params"]["aa_college"] == str(f["faculty_a"].faculty_id)
    assert hit["nav_params"]["aa_department"] == str(f["dept_a"].department_id)

    resp = client.get("/api/search", params={"q": "Zulfiqar Alpha Course"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "course")
    assert hit["id"] == f["course_a"].course_id

    resp = client.get("/api/search", params={"q": "Zulfiqar Alpha Search"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "staff")
    assert hit["id"] == f["staff_a"].user_id
    assert hit["nav_params"]["aa_section"] == "doctors"


def test_unrestricted_admin_finds_building_and_zone(db_session, client, admin_token):
    building = models.Building(name="Search Verification Hall")
    zone = models.Zone(name="Search Verification Zone", occupancy_state="EMPTY")
    db_session.add_all([building, zone])
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "Search Verification Hall"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "building")
    assert hit["nav_params"]["building"] == "Search Verification Hall"

    resp = client.get("/api/search", params={"q": "Search Verification Zone"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "zone")
    assert hit["nav_action"] == "open_zone"
    assert hit["nav_action_id"] == zone.zone_id


def test_unrestricted_admin_finds_access_event_and_investigation(db_session, client, admin_token):
    door = _door(db_session, code="AE1", name="Access Event Test Room")
    event = models.AccessEvent(door_id=door.door_id, credential_id=None, method="card", result="denied")
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "Access Event Test"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "access_event")
    assert hit["id"] == event.event_id
    assert hit["nav_tab"] == "events"
    assert hit["nav_params"]["investigate"] == str(event.event_id)

    client.put(f"/api/access-events/{event.event_id}/investigation", json={"status": "open"}, headers=headers)
    resp2 = client.get("/api/search", params={"q": "Access Event Test"}, headers=headers)
    hit2 = next(r for r in resp2.json()["results"] if r["id"] == event.event_id)
    assert hit2["type"] == "investigation"


def test_unrestricted_admin_finds_emergency_override(db_session, client, admin_token):
    f = _two_scope_fixture(db_session, client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "Zulfiqar Alpha emergency"}, headers=headers)
    hit = next(r for r in resp.json()["results"] if r["type"] == "emergency_override")
    assert hit["id"] == f["override_a"].override_id


# ---------------------------------------------------------------------------
# Scoped admin isolation
# ---------------------------------------------------------------------------
def test_scoped_admin_a_never_sees_scope_b_college_or_department(db_session, client):
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}

    resp = client.get("/api/search", params={"q": "Search Faculty"}, headers=headers_a)
    titles = _titles(resp.json(), "college")
    assert f["faculty_a"].name in titles
    assert f["faculty_b"].name not in titles

    resp = client.get("/api/search", params={"q": "Search Dept"}, headers=headers_a)
    titles = _titles(resp.json(), "department")
    assert f["dept_a"].name in titles
    assert f["dept_b"].name not in titles


def test_scoped_admin_a_never_sees_scope_b_staff_or_course(db_session, client):
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}

    resp = client.get("/api/search", params={"q": "Zulfiqar"}, headers=headers_a)
    body = resp.json()
    staff_ids = {r["id"] for r in body["results"] if r["type"] == "staff"}
    course_ids = {r["id"] for r in body["results"] if r["type"] == "course"}
    assert f["staff_a"].user_id in staff_ids
    assert f["staff_b"].user_id not in staff_ids
    assert f["course_a"].course_id in course_ids
    assert f["course_b"].course_id not in course_ids


def test_scoped_admin_a_never_sees_scope_b_emergency_override(db_session, client):
    f = _two_scope_fixture(db_session, client)
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get("/api/search", params={"q": "Zulfiqar"}, headers=headers_a)
    override_ids = {r["id"] for r in resp.json()["results"] if r["type"] == "emergency_override"}
    assert f["override_a"].override_id in override_ids
    assert f["override_b"].override_id not in override_ids


def test_scoped_admin_b_isolation_holds_in_reverse(db_session, client):
    """Proves isolation both directions, not just 'restricted sees less' —
    same discipline as test_command_center.py's own isolation tests."""
    f = _two_scope_fixture(db_session, client)
    headers_b = {"Authorization": f"Bearer {f['token_b']}"}
    resp = client.get("/api/search", params={"q": "Zulfiqar"}, headers=headers_b)
    body = resp.json()
    staff_ids = {r["id"] for r in body["results"] if r["type"] == "staff"}
    assert f["staff_b"].user_id in staff_ids
    assert f["staff_a"].user_id not in staff_ids


def test_scoped_admin_gets_no_alerts_no_leak(db_session, client):
    f = _two_scope_fixture(db_session, client)
    db_session.add(models.Alert(door_id=f["door_a"].door_id, type="forced_open"))
    db_session.commit()
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}
    resp = client.get("/api/search", params={"q": "forced"}, headers=headers_a)
    assert resp.json()["results"] == []


def test_unrestricted_admin_still_sees_both_scopes(db_session, client, admin_token):
    f = _two_scope_fixture(db_session, client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/search", params={"q": "Zulfiqar"}, headers=headers)
    staff_ids = {r["id"] for r in resp.json()["results"] if r["type"] == "staff"}
    assert f["staff_a"].user_id in staff_ids
    assert f["staff_b"].user_id in staff_ids


# ---------------------------------------------------------------------------
# Doctor / instructor / TA visibility
# ---------------------------------------------------------------------------
def test_instructor_sees_academic_directory_unrestricted(db_session, client, instructor_token):
    """Matches GET /api/staff, /api/departments, /api/courses's own existing
    behavior — these are staff-directory endpoints with no scope filter for
    a non-admin viewer (see academic.py's `if user.role == "admin"` gates),
    so search must not invent a stricter rule that endpoint doesn't have."""
    f = _two_scope_fixture(db_session, client)
    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.get("/api/search", params={"q": "Zulfiqar"}, headers=headers)
    body = resp.json()
    staff_ids = {r["id"] for r in body["results"] if r["type"] == "staff"}
    assert f["staff_a"].user_id in staff_ids
    assert f["staff_b"].user_id in staff_ids


def test_instructor_only_sees_assigned_doors(db_session, client, instructor_token):
    door_assigned = _door(db_session, code="ASSIGN1", name="Search Assigned Room")
    door_unassigned = _door(db_session, code="ASSIGN2", name="Search Unassigned Room")
    instructor = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    db_session.add(models.DoorAssignment(door_id=door_assigned.door_id, instructor_id=instructor.user_id))
    db_session.commit()

    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.get("/api/search", params={"q": "Search"}, headers=headers)
    door_ids = {r["id"] for r in resp.json()["results"] if r["type"] == "door"}
    assert door_assigned.door_id in door_ids
    assert door_unassigned.door_id not in door_ids


def test_instructor_never_sees_emergency_overrides(db_session, client, instructor_token):
    f = _two_scope_fixture(db_session, client)
    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.get("/api/search", params={"q": "Zulfiqar"}, headers=headers)
    assert not any(r["type"] == "emergency_override" for r in resp.json()["results"])


def test_instructor_only_sees_own_access_events(db_session, client, instructor_token):
    door = _door(db_session, code="OWN1", name="Own Events Room")
    instructor = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    other = _staff(db_session, "Someone Else Owns", role="doctor")
    own_event = models.AccessEvent(door_id=door.door_id, credential_id=None, method="card",
                                    result="granted", user_id=instructor.user_id)
    other_event = models.AccessEvent(door_id=door.door_id, credential_id=None, method="card",
                                      result="granted", user_id=other.user_id)
    db_session.add_all([own_event, other_event])
    db_session.commit()

    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.get("/api/search", params={"q": "Own Events Room"}, headers=headers)
    event_ids = {r["id"] for r in resp.json()["results"] if r["type"] in ("access_event", "investigation")}
    assert own_event.event_id in event_ids
    assert other_event.event_id not in event_ids
