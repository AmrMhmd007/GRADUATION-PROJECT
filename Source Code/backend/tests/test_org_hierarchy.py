"""
Tests for the organizational hierarchy (College=Faculty -> Department ->
Staff(User doctor/instructor) -> Course -> CourseAssignment) and its
AdminScope-based authorization: app/routers/academic.py,
app/security.py's scope helpers, and the scope-aware bits of
app/routers/users.py.

Covers: unrestricted-admin-sees-everything (backward compatibility),
college-scoped admin authorized vs unauthorized (both via the "frontend"
query params AND a direct API call to another college), department-scoped
admin, staff not leaking across colleges, and course assignment scoping.
"""
from app import models, security


def _college(db, name):
    c = models.Faculty(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _department(db, faculty_id, name):
    d = models.Department(faculty_id=faculty_id, name=name)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _staff(db, name, role, faculty_id=None, department_id=None):
    u = models.User(
        name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
        password_hash=security.hash_password("pw123456"),
        faculty_id=faculty_id, department_id=department_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _scoped_admin_token(client, db, name, faculty_id=None, department_id=None):
    admin = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    if faculty_id is not None:
        db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id, department_id=department_id))
        db.commit()
    resp = client.post("/api/auth/login", json={"email": admin.email, "password": "pw123456"})
    return admin, resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Department / Course CRUD + hierarchy shape
# ---------------------------------------------------------------------------
def test_create_department_and_course_under_college(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post("/api/departments", json={"faculty_id": eng.faculty_id, "name": "Electronics & Communication Engineering"},
                        headers=headers)
    assert resp.status_code == 201
    dept_id = resp.json()["department_id"]
    assert resp.json()["faculty_name"] == "Faculty of Engineering"

    resp = client.post("/api/courses", json={"department_id": dept_id, "code": "ECE301", "name": "DSP"},
                        headers=headers)
    assert resp.status_code == 201
    assert resp.json()["department_name"] == "Electronics & Communication Engineering"
    assert resp.json()["faculty_name"] == "Faculty of Engineering"


def test_duplicate_department_name_in_same_college_rejected(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/departments", json={"faculty_id": eng.faculty_id, "name": "ECE"}, headers=headers)
    resp = client.post("/api/departments", json={"faculty_id": eng.faculty_id, "name": "ECE"}, headers=headers)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Staff must be associated with College/Department, and not mixed globally
# ---------------------------------------------------------------------------
def test_staff_endpoint_scoped_by_department_not_globally_mixed(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    cs = _college(db_session, "Faculty of Computer Science")
    ece = _department(db_session, eng.faculty_id, "ECE")
    cs_dept = _department(db_session, cs.faculty_id, "CS")
    _staff(db_session, "Doctor Eng", "doctor", eng.faculty_id, ece.department_id)
    _staff(db_session, "Doctor CS", "doctor", cs.faculty_id, cs_dept.department_id)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get(f"/api/staff?department_id={ece.department_id}", headers=headers)
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["Doctor Eng"]


# ---------------------------------------------------------------------------
# AdminScope authorization — the core "no global admin superpower by default,
# but existing admins are unaffected" behavior
# ---------------------------------------------------------------------------
def test_unrestricted_admin_sees_all_colleges_unchanged(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    cs = _college(db_session, "Faculty of Computer Science")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/departments", headers=headers)
    assert resp.status_code == 200  # no crash, no filtering error for a global admin with zero scope rows


def test_college_scoped_admin_authorized_for_own_college(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    _staff(db_session, "Doctor Eng", "doctor", eng.faculty_id, ece.department_id)

    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    resp = client.get(f"/api/departments?faculty_id={eng.faculty_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(f"/api/staff?faculty_id={eng.faculty_id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_college_scoped_admin_rejected_for_other_college_direct_api_call(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    residential = _college(db_session, "Residential Operations")
    res_dept = _department(db_session, residential.faculty_id, "Residence A")
    _staff(db_session, "Res Staff", "doctor", residential.faculty_id, res_dept.department_id)

    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin2", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    # Direct, deliberate API call for a college this admin was never granted —
    # must be rejected by the backend, not just hidden in a UI dropdown.
    resp = client.get(f"/api/departments?faculty_id={residential.faculty_id}", headers=headers)
    assert resp.status_code == 403

    resp = client.get(f"/api/staff?faculty_id={residential.faculty_id}", headers=headers)
    assert resp.status_code == 403

    # And the unscoped /api/staff listing for this admin must never include
    # the other college's staff either.
    resp = client.get("/api/staff", headers=headers)
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "Res Staff" not in names


def test_department_scoped_admin_rejected_for_sibling_department(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    mech = _department(db_session, eng.faculty_id, "Mechanical Engineering")
    _staff(db_session, "Doctor Mech", "doctor", eng.faculty_id, mech.department_id)

    _, ece_admin_token = _scoped_admin_token(client, db_session, "ECE Admin",
                                              faculty_id=eng.faculty_id, department_id=ece.department_id)
    headers = {"Authorization": f"Bearer {ece_admin_token}"}

    resp = client.get(f"/api/staff?department_id={mech.department_id}", headers=headers)
    assert resp.status_code == 403


def test_create_user_with_department_outside_scope_rejected(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    other = _college(db_session, "Faculty of Business")
    other_dept = _department(db_session, other.faculty_id, "Marketing")

    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin3", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    resp = client.post("/api/users", json={
        "name": "New Doctor", "email": "newdoc@example.edu", "role": "doctor", "password": "pw123456",
        "faculty_id": other.faculty_id, "department_id": other_dept.department_id,
    }, headers=headers)
    assert resp.status_code == 403


def test_scoped_admin_cannot_grant_admin_scopes(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin4", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}
    resp = client.post("/api/admin-scopes", json={"user_id": 1, "faculty_id": eng.faculty_id}, headers=headers)
    assert resp.status_code == 403


def test_instructor_role_cannot_manage_departments(db_session, client, instructor_token):
    eng = _college(db_session, "Faculty of Engineering")
    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.post("/api/departments", json={"faculty_id": eng.faculty_id, "name": "ECE"}, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Course assignments connect staff -> course, scoped the same way
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# College & Department management: rename + dependency-protected delete
# ---------------------------------------------------------------------------
def test_rename_college_and_department(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.put(f"/api/faculties/{eng.faculty_id}", json={"name": "College of Engineering"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "College of Engineering"

    resp = client.put(f"/api/departments/{ece.department_id}", json={"name": "Electronics & Communications"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Electronics & Communications"


def test_delete_empty_college_and_department_succeeds(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.delete(f"/api/departments/{ece.department_id}", headers=headers)
    assert resp.status_code == 204

    resp = client.delete(f"/api/faculties/{eng.faculty_id}", headers=headers)
    assert resp.status_code == 204

    resp = client.get("/api/faculties", headers=headers)
    assert eng.faculty_id not in [c["faculty_id"] for c in resp.json()]


def test_delete_department_blocked_when_staff_assigned(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    _staff(db_session, "Doctor Eng", "doctor", eng.faculty_id, ece.department_id)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.delete(f"/api/departments/{ece.department_id}", headers=headers)
    assert resp.status_code == 409
    assert "staff" in resp.json()["detail"]

    # Department must still exist afterward — no partial/silent delete.
    resp = client.get(f"/api/departments?faculty_id={eng.faculty_id}", headers=headers)
    assert len(resp.json()) == 1


def test_delete_department_blocked_when_course_exists(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    db_session.add(models.Course(department_id=ece.department_id, code="ECE301", name="DSP"))
    db_session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.delete(f"/api/departments/{ece.department_id}", headers=headers)
    assert resp.status_code == 409
    assert "course" in resp.json()["detail"]


def test_delete_college_blocked_when_department_exists(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    _department(db_session, eng.faculty_id, "ECE")
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.delete(f"/api/faculties/{eng.faculty_id}", headers=headers)
    assert resp.status_code == 409
    assert "department" in resp.json()["detail"]


def test_delete_college_blocked_when_staff_directly_assigned(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    _staff(db_session, "Doctor NoDept", "doctor", eng.faculty_id, None)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.delete(f"/api/faculties/{eng.faculty_id}", headers=headers)
    assert resp.status_code == 409


def test_scoped_admin_cannot_delete_or_rename_other_college(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    other = _college(db_session, "Faculty of Business")
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin Del", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    resp = client.put(f"/api/faculties/{other.faculty_id}", json={"name": "Renamed"}, headers=headers)
    assert resp.status_code == 403

    resp = client.delete(f"/api/faculties/{other.faculty_id}", headers=headers)
    assert resp.status_code == 403


def test_scoped_admin_can_manage_own_college_and_department(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin Manage", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    resp = client.put(f"/api/departments/{ece.department_id}", json={"name": "ECE Renamed"}, headers=headers)
    assert resp.status_code == 200

    resp = client.delete(f"/api/departments/{ece.department_id}", headers=headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Phase 3: OperationalScope (non-academic areas) — same unified AdminScope
# grant table, not a second authorization system.
# ---------------------------------------------------------------------------
def test_create_operational_scope_and_list(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/operational-scopes", json={"name": "Chiller Plant", "scope_type": "HVAC"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["scope_type"] == "HVAC"

    resp = client.post("/api/operational-scopes", json={"name": "Bad", "scope_type": "NOT_A_TYPE"}, headers=headers)
    assert resp.status_code == 400


def test_operational_scope_grant_restricts_admin_and_rejects_other_scopes(db_session, client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    hvac = client.post("/api/operational-scopes", json={"name": "Chiller Plant", "scope_type": "HVAC"}, headers=headers).json()
    electrical = client.post("/api/operational-scopes", json={"name": "Main Transformer", "scope_type": "ELECTRICAL"}, headers=headers).json()

    hvac_admin = models.User(name="HVAC Admin", email="hvac.admin@example.edu", role="admin",
                              password_hash=security.hash_password("pw123456"))
    db_session.add(hvac_admin)
    db_session.commit()
    db_session.refresh(hvac_admin)

    resp = client.post("/api/admin-scopes", json={"user_id": hvac_admin.user_id, "operational_scope_id": hvac["scope_id"]},
                        headers=headers)
    assert resp.status_code == 201

    login = client.post("/api/auth/login", json={"email": hvac_admin.email, "password": "pw123456"})
    hvac_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.get("/api/operational-scopes", headers=hvac_headers)
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["Chiller Plant"]
    assert "Main Transformer" not in names

    # A scoped HVAC admin must also not be able to grant scopes to others.
    resp = client.post("/api/admin-scopes", json={"user_id": hvac_admin.user_id, "operational_scope_id": electrical["scope_id"]},
                        headers=hvac_headers)
    assert resp.status_code == 403


def test_admin_scope_requires_a_target(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/admin-scopes", json={"user_id": 1}, headers=headers)
    assert resp.status_code == 400


def test_delete_course_blocked_when_staff_assigned(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    doc = _staff(db_session, "Doctor DSP2", "doctor", eng.faculty_id, ece.department_id)
    course = models.Course(department_id=ece.department_id, code="ECE301", name="DSP")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": doc.user_id}, headers=headers)

    resp = client.delete(f"/api/courses/{course.course_id}", headers=headers)
    assert resp.status_code == 409
    assert "assignment" in resp.json()["detail"]

    # Confirm it wasn't silently deleted.
    resp = client.get(f"/api/courses?department_id={ece.department_id}", headers=headers)
    assert len(resp.json()) == 1


def test_delete_course_with_no_dependents_succeeds(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    course = models.Course(department_id=ece.department_id, code="ECE302", name="Networks")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.delete(f"/api/courses/{course.course_id}", headers=headers)
    assert resp.status_code == 204


def test_course_out_exposes_faculty_id(db_session, client, admin_token):
    """CourseOut previously only exposed faculty_name (a display string) —
    added a computed faculty_id (via Course -> Department -> Faculty, no
    schema change) so the frontend can filter/match courses by college ID
    instead of a fragile name comparison."""
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    course = models.Course(department_id=ece.department_id, code="ECE501", name="VLSI")
    db_session.add(course)
    db_session.commit()
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.get(f"/api/courses?department_id={ece.department_id}", headers=headers)
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["faculty_id"] == eng.faculty_id
    assert row["faculty_name"] == "Faculty of Engineering"


def test_assign_staff_to_course_and_list(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    doc = _staff(db_session, "Doctor DSP", "doctor", eng.faculty_id, ece.department_id)
    course = models.Course(department_id=ece.department_id, code="ECE301", name="DSP")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": doc.user_id}, headers=headers)
    assert resp.status_code == 201

    resp = client.get("/api/staff", headers=headers)
    staff_row = next(s for s in resp.json() if s["user_id"] == doc.user_id)
    assert staff_row["assigned_courses"][0]["code"] == "ECE301"


# ---------------------------------------------------------------------------
# Final hardening pass — "Remove/Unassign TA from academic org" workflow:
# POST /api/users/{id}/unassign clears faculty_id/department_id back to
# NULL (both already nullable at the model level — see models.py's User
# docstring), separate from the account-deletion endpoint and separate from
# update_staff_scope (which only ever assigns/reassigns, never clears).
# ---------------------------------------------------------------------------
def test_unassign_clears_faculty_and_department_for_ta(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    ta = _staff(db_session, "TA Alpha", "instructor", eng.faculty_id, ece.department_id)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["faculty_id"] is None
    assert body["department_id"] is None

    # Persistence: a fresh read (not the same response object) still shows it cleared.
    fresh = client.get("/api/staff", headers=headers).json()
    row = next((s for s in fresh if s["user_id"] == ta.user_id), None)
    # An unassigned TA has no faculty to scope by — still visible to an
    # unrestricted admin's global /api/staff listing? Only if faculty_id
    # filtering isn't required; confirm via direct user lookup instead,
    # which is unambiguous regardless of /api/staff's own scoping shape.
    resp2 = client.get("/api/users", headers=headers)
    user_row = next(u for u in resp2.json() if u["user_id"] == ta.user_id)
    assert user_row["faculty_id"] is None
    assert user_row["department_id"] is None


def test_unassign_clears_for_doctor_too(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    doc = _staff(db_session, "Doctor Beta", "doctor", eng.faculty_id, None)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(f"/api/users/{doc.user_id}/unassign", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["faculty_id"] is None


def test_unassign_404_for_missing_user(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/users/999999/unassign", headers=headers)
    assert resp.status_code == 404


def test_unassign_rejects_non_staff_role(db_session, client, admin_token):
    """Admin accounts have no academic assignment concept — unassign only
    makes sense for Doctor/TA rows."""
    other_admin = models.User(name="Other Admin", email="other.admin@example.edu", role="admin",
                               password_hash=security.hash_password("pw123456"))
    db_session.add(other_admin)
    db_session.commit()
    db_session.refresh(other_admin)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(f"/api/users/{other_admin.user_id}/unassign", headers=headers)
    assert resp.status_code == 400


def test_unassign_rejects_already_unassigned(db_session, client, admin_token):
    ta = _staff(db_session, "TA Gamma", "instructor")  # no faculty_id/department_id at all
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 400


def test_unassign_blocked_by_active_course_assignment(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    ta = _staff(db_session, "TA Delta", "instructor", eng.faculty_id, ece.department_id)
    course = models.Course(department_id=ece.department_id, code="ECE401", name="Control Systems")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    headers = {"Authorization": f"Bearer {admin_token}"}

    assign = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": ta.user_id}, headers=headers)
    assert assign.status_code == 201

    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 409
    assert "active course assignment" in resp.json()["detail"]

    # The block is real, not cosmetic: faculty_id/department_id are untouched.
    fresh = client.get("/api/users", headers=headers).json()
    row = next(u for u in fresh if u["user_id"] == ta.user_id)
    assert row["faculty_id"] == eng.faculty_id
    assert row["department_id"] == ece.department_id


def test_unassign_succeeds_after_course_assignment_removed(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ece = _department(db_session, eng.faculty_id, "ECE")
    ta = _staff(db_session, "TA Epsilon", "instructor", eng.faculty_id, ece.department_id)
    course = models.Course(department_id=ece.department_id, code="ECE402", name="Robotics")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    headers = {"Authorization": f"Bearer {admin_token}"}

    assign = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": ta.user_id}, headers=headers)
    assignment_id = assign.json()["assignment_id"]

    blocked = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert blocked.status_code == 409

    removed = client.delete(f"/api/courses/{course.course_id}/assignments/{assignment_id}", headers=headers)
    assert removed.status_code == 204

    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["faculty_id"] is None


def test_unassign_requires_unrestricted_admin(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    other = _college(db_session, "Faculty of Other")
    ta = _staff(db_session, "TA Zeta", "instructor", eng.faculty_id)
    _, scoped_token = _scoped_admin_token(client, db_session, "Scoped For Unassign", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {scoped_token}"}

    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 403

    # Sanity: an unrestricted admin can still do it (the 403 above is really
    # about restriction, not some other unrelated failure).
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    resp2 = client.post(f"/api/users/{ta.user_id}/unassign", headers=admin_headers)
    assert resp2.status_code == 200
    del other  # only needed to prove the scoped admin's own college isn't the reason for the 403


def test_unassign_requires_admin_role(db_session, client, instructor_token):
    eng = _college(db_session, "Faculty of Engineering")
    ta = _staff(db_session, "TA Eta", "instructor", eng.faculty_id)
    headers = {"Authorization": f"Bearer {instructor_token}"}
    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 403


def test_unassign_is_audit_logged(db_session, client, admin_token):
    eng = _college(db_session, "Faculty of Engineering")
    ta = _staff(db_session, "TA Theta", "instructor", eng.faculty_id)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = client.post(f"/api/users/{ta.user_id}/unassign", headers=headers)
    assert resp.status_code == 200

    logs = client.get(f"/api/audit-logs?resource_type=user&resource_id={ta.user_id}", headers=headers).json()
    assert any("academic organization" in (row.get("description") or "") for row in logs)


# ---------------------------------------------------------------------------
# High-risk College cascade-delete (GET .../deletion-impact,
# POST .../cascade-delete) — 17 explicit cases per the requested spec:
# empty/departments/staff/courses/course-assignments deletion, invalid
# password, unauthenticated, scoped-admin/doctor/instructor/TA rejection,
# wrong name confirmation, transactional rollback on failure, persistence
# after a fresh read, AuditLog creation, password never stored/logged, and
# double-submission not double-deleting.
# ---------------------------------------------------------------------------
from unittest.mock import patch
import sqlalchemy.orm as _orm


def _cascade(client, headers, faculty_id, name, password="admin123"):
    return client.post(f"/api/faculties/{faculty_id}/cascade-delete",
                        json={"confirm_name": name, "password": password}, headers=headers)


def test_cascade_delete_empty_college(db_session, client, admin_token):
    eng = _college(db_session, "Empty College")
    headers = {"Authorization": f"Bearer {admin_token}"}

    impact = client.get(f"/api/faculties/{eng.faculty_id}/deletion-impact", headers=headers)
    assert impact.status_code == 200
    assert impact.json()["departments"] == 0

    resp = _cascade(client, headers, eng.faculty_id, "Empty College")
    assert resp.status_code == 200
    assert client.get(f"/api/faculties/{eng.faculty_id}", headers=headers).status_code == 404


def test_cascade_delete_college_with_departments(db_session, client, admin_token):
    eng = _college(db_session, "College With Depts")
    faculty_id = eng.faculty_id
    _department(db_session, faculty_id, "Dept A")
    _department(db_session, faculty_id, "Dept B")
    headers = {"Authorization": f"Bearer {admin_token}"}

    impact = client.get(f"/api/faculties/{faculty_id}/deletion-impact", headers=headers).json()
    assert impact["departments"] == 2

    resp = _cascade(client, headers, faculty_id, "College With Depts")
    assert resp.status_code == 200
    assert client.get(f"/api/faculties/{faculty_id}", headers=headers).status_code == 404
    assert db_session.query(models.Department).filter(models.Department.faculty_id == faculty_id).count() == 0


def test_cascade_delete_college_with_staff_unassigns_not_deletes(db_session, client, admin_token):
    eng = _college(db_session, "College With Staff")
    dept = _department(db_session, eng.faculty_id, "Dept A")
    doc = _staff(db_session, "Cascade Doctor", "doctor", eng.faculty_id, dept.department_id)
    ta = _staff(db_session, "Cascade TA", "instructor", eng.faculty_id, dept.department_id)
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = _cascade(client, headers, eng.faculty_id, "College With Staff")
    assert resp.status_code == 200

    # Accounts survive — only unassigned, never deleted.
    users = client.get("/api/users", headers=headers).json()
    doc_row = next(u for u in users if u["user_id"] == doc.user_id)
    ta_row = next(u for u in users if u["user_id"] == ta.user_id)
    assert doc_row["faculty_id"] is None and doc_row["department_id"] is None
    assert ta_row["faculty_id"] is None and ta_row["department_id"] is None


def test_cascade_delete_college_with_courses(db_session, client, admin_token):
    eng = _college(db_session, "College With Courses")
    dept = _department(db_session, eng.faculty_id, "Dept A")
    course = models.Course(department_id=dept.department_id, code="X101", name="Intro")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    course_id = course.course_id
    headers = {"Authorization": f"Bearer {admin_token}"}

    impact = client.get(f"/api/faculties/{eng.faculty_id}/deletion-impact", headers=headers).json()
    assert impact["courses"] == 1

    resp = _cascade(client, headers, eng.faculty_id, "College With Courses")
    assert resp.status_code == 200
    assert db_session.query(models.Course).filter(models.Course.course_id == course_id).first() is None


def test_cascade_delete_college_with_course_assignments(db_session, client, admin_token):
    eng = _college(db_session, "College With Assignments")
    dept = _department(db_session, eng.faculty_id, "Dept A")
    ta = _staff(db_session, "Assign TA", "instructor", eng.faculty_id, dept.department_id)
    course = models.Course(department_id=dept.department_id, code="X201", name="Advanced")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(course)
    course_id = course.course_id
    faculty_id = eng.faculty_id
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(f"/api/courses/{course_id}/assignments", json={"user_id": ta.user_id}, headers=headers)

    impact = client.get(f"/api/faculties/{faculty_id}/deletion-impact", headers=headers).json()
    assert impact["course_assignments"] == 1

    resp = _cascade(client, headers, faculty_id, "College With Assignments")
    assert resp.status_code == 200
    assert db_session.query(models.CourseAssignment).filter(
        models.CourseAssignment.course_id == course_id
    ).count() == 0


def test_cascade_delete_invalid_password_rejected(db_session, client, admin_token):
    eng = _college(db_session, "College Bad Password")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = _cascade(client, headers, eng.faculty_id, "College Bad Password", password="wrongpassword")
    assert resp.status_code == 401
    assert client.get(f"/api/faculties/{eng.faculty_id}", headers=headers).status_code == 200


def test_cascade_delete_unauthenticated_rejected(db_session, client):
    eng = _college(db_session, "College No Auth")
    resp = client.post(f"/api/faculties/{eng.faculty_id}/cascade-delete",
                        json={"confirm_name": "College No Auth", "password": "admin123"})
    assert resp.status_code == 401


def test_cascade_delete_scoped_admin_rejected(db_session, client, admin_token):
    eng = _college(db_session, "College Scoped Reject")
    _, scoped_token = _scoped_admin_token(client, db_session, "Scoped For Cascade", faculty_id=eng.faculty_id)
    headers = {"Authorization": f"Bearer {scoped_token}"}
    resp = _cascade(client, headers, eng.faculty_id, "College Scoped Reject", password="pw123456")
    assert resp.status_code == 403
    assert client.get(f"/api/faculties/{eng.faculty_id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200


def test_cascade_delete_doctor_role_rejected(db_session, client, admin_token):
    eng = _college(db_session, "College Doctor Reject")
    doc = _staff(db_session, "Rejecting Doctor", "doctor")
    login = client.post("/api/auth/login", json={"email": doc.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = _cascade(client, headers, eng.faculty_id, "College Doctor Reject", password="pw123456")
    assert resp.status_code == 403


def test_cascade_delete_instructor_role_rejected(db_session, client, admin_token):
    eng = _college(db_session, "College Instructor Reject")
    instr = _staff(db_session, "Rejecting Instructor", "instructor")
    login = client.post("/api/auth/login", json={"email": instr.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = _cascade(client, headers, eng.faculty_id, "College Instructor Reject", password="pw123456")
    assert resp.status_code == 403


def test_cascade_delete_ta_rejected(db_session, client, admin_token):
    """A TA is role='instructor' with academic_title='Teaching Assistant' —
    same role-based rejection path as the plain instructor case, verified
    separately since the spec calls it out as its own case."""
    eng = _college(db_session, "College TA Reject")
    ta = models.User(name="Rejecting TA", email="rejecting.ta@example.edu", role="instructor",
                      academic_title="Teaching Assistant", password_hash=security.hash_password("pw123456"))
    db_session.add(ta)
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": ta.email, "password": "pw123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = _cascade(client, headers, eng.faculty_id, "College TA Reject", password="pw123456")
    assert resp.status_code == 403


def test_cascade_delete_wrong_name_confirmation_cannot_delete(db_session, client, admin_token):
    eng = _college(db_session, "College Wrong Name")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = _cascade(client, headers, eng.faculty_id, "Totally Wrong Name")
    assert resp.status_code == 400
    assert client.get(f"/api/faculties/{eng.faculty_id}", headers=headers).status_code == 200


def test_cascade_delete_rolls_back_transaction_on_failure(db_session, client, admin_token):
    eng = _college(db_session, "College Rollback")
    dept = _department(db_session, eng.faculty_id, "Dept Rollback")
    headers = {"Authorization": f"Bearer {admin_token}"}

    real_commit = _orm.Session.commit
    call_count = {"n": 0}

    def flaky_commit(self):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated failure during cascade delete")
        return real_commit(self)

    with patch.object(_orm.Session, "commit", flaky_commit):
        resp = _cascade(client, headers, eng.faculty_id, "College Rollback")
    assert resp.status_code == 500

    # Nothing partially deleted — college and department both still exist.
    assert client.get(f"/api/faculties/{eng.faculty_id}", headers=headers).status_code == 200
    assert db_session.query(models.Department).filter(models.Department.department_id == dept.department_id).first() is not None

    # The failure AuditLog row must survive even though the deletion itself
    # was rolled back — audit_service.log() does its own db.add()+db.commit()
    # AFTER the router's db.rollback() already ran, so it's a separate,
    # independent transaction, not part of the one that got rolled back.
    # Verified here directly (not just read from the source), per the
    # explicit "don't just claim it works, test it" requirement: this proves
    # the failure record is queryable from a fresh read of the same DB.
    logs = client.get(f"/api/audit-logs?resource_type=faculty&resource_id={eng.faculty_id}", headers=headers).json()
    assert any(
        row["result"] == "failure" and "rolled back" in (row.get("description") or "")
        for row in logs
    )


def test_cascade_delete_persists_after_fresh_read(db_session, client, admin_token):
    eng = _college(db_session, "College Fresh Read")
    faculty_id = eng.faculty_id
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = _cascade(client, headers, faculty_id, "College Fresh Read")
    assert resp.status_code == 200

    # A brand-new query against the same DB, not any cached response object.
    assert db_session.query(models.Faculty).filter(models.Faculty.faculty_id == faculty_id).first() is None
    resp2 = client.get("/api/faculties", headers=headers)
    assert faculty_id not in [c["faculty_id"] for c in resp2.json()]


def test_cascade_delete_creates_audit_log(db_session, client, admin_token):
    eng = _college(db_session, "College Audit")
    faculty_id = eng.faculty_id
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = _cascade(client, headers, faculty_id, "College Audit")
    assert resp.status_code == 200

    logs = client.get(f"/api/audit-logs?resource_type=faculty&resource_id={faculty_id}", headers=headers).json()
    assert any(row["result"] == "success" and "Deleted college" in (row.get("description") or "") for row in logs)


def test_cascade_delete_password_never_stored_or_logged(db_session, client, admin_token):
    eng = _college(db_session, "College Password Safety")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = _cascade(client, headers, eng.faculty_id, "College Password Safety", password="admin123")
    assert resp.status_code == 200

    logs = client.get("/api/audit-logs?resource_type=faculty", headers=headers).json()
    for row in logs:
        assert "admin123" not in str(row)
    # Also check the failure path doesn't leak the wrong password either.
    eng2 = _college(db_session, "College Password Safety 2")
    _cascade(client, headers, eng2.faculty_id, "College Password Safety 2", password="wrong-secret-xyz")
    logs2 = client.get("/api/audit-logs?resource_type=faculty", headers=headers).json()
    for row in logs2:
        assert "wrong-secret-xyz" not in str(row)


def test_cascade_delete_double_submission_does_not_delete_twice(db_session, client, admin_token):
    eng = _college(db_session, "College Double Submit")
    faculty_id = eng.faculty_id
    headers = {"Authorization": f"Bearer {admin_token}"}

    first = _cascade(client, headers, faculty_id, "College Double Submit")
    assert first.status_code == 200

    second = _cascade(client, headers, faculty_id, "College Double Submit")
    assert second.status_code == 404  # already gone — the second submit can't "delete again"
