"""
Phase 8 explicit persistence verification: for College, Department,
Staff-profile, Course, and Course-assignment — Create -> refetch (a fresh
GET, not the create response) -> still exists with the right values;
Update -> refetch -> values persisted; Delete -> refetch -> gone (404) or,
where a dependency-block rule legitimately prevents deletion, that the
block itself is real and enforced by the backend.

This is API-level verification (real HTTP requests through FastAPI's
TestClient, hitting the same router code paths the frontend calls) plus
DB-level verification (every "still exists" check is a brand new GET
request that re-queries the database — never asserting on the create/update
response alone). It is explicitly NOT browser-level verification: no real
browser or the dashboard UI was driven for this check, per the standing
instruction to never conflate the two.
"""


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_college_create_update_persist(client, admin_token):
    h = auth(admin_token)

    # Create
    resp = client.post("/api/faculties", json={"name": "College of Testing", "code": "COT", "description": "desc"}, headers=h)
    assert resp.status_code == 201
    faculty_id = resp.json()["faculty_id"]

    # Refetch (fresh GET) -> still exists with the right values
    got = client.get(f"/api/faculties/{faculty_id}", headers=h)
    assert got.status_code == 200
    assert got.json()["name"] == "College of Testing"
    assert got.json()["code"] == "COT"
    assert got.json()["status"] == "active"

    # Update
    upd = client.put(f"/api/faculties/{faculty_id}", json={"status": "inactive"}, headers=h)
    assert upd.status_code == 200

    # Refetch -> value persisted
    got2 = client.get(f"/api/faculties/{faculty_id}", headers=h)
    assert got2.json()["status"] == "inactive"

    # Delete (no dependents yet) -> refetch -> gone
    dele = client.delete(f"/api/faculties/{faculty_id}", headers=h)
    assert dele.status_code == 204
    got3 = client.get(f"/api/faculties/{faculty_id}", headers=h)
    assert got3.status_code == 404


def test_department_create_update_delete_persist(client, admin_token):
    h = auth(admin_token)
    fac = client.post("/api/faculties", json={"name": "College of Dept Testing"}, headers=h).json()

    create = client.post("/api/departments", json={"faculty_id": fac["faculty_id"], "name": "Testing Dept", "code": "TST"}, headers=h)
    assert create.status_code == 201
    dept_id = create.json()["department_id"]

    got = client.get(f"/api/departments/{dept_id}", headers=h)
    assert got.status_code == 200
    assert got.json()["name"] == "Testing Dept"
    assert got.json()["code"] == "TST"

    upd = client.put(f"/api/departments/{dept_id}", json={"description": "Now has a description"}, headers=h)
    assert upd.status_code == 200
    got2 = client.get(f"/api/departments/{dept_id}", headers=h)
    assert got2.json()["description"] == "Now has a description"

    dele = client.delete(f"/api/departments/{dept_id}", headers=h)
    assert dele.status_code == 204
    got3 = client.get(f"/api/departments/{dept_id}", headers=h)
    assert got3.status_code == 404


def test_staff_profile_update_persists(client, admin_token):
    h = auth(admin_token)
    fac = client.post("/api/faculties", json={"name": "College of Staff Testing"}, headers=h).json()
    dept = client.post("/api/departments", json={"faculty_id": fac["faculty_id"], "name": "Staff Test Dept"}, headers=h).json()

    doc = client.post("/api/users", json={
        "name": "Dr. Persist Check", "email": "persist.check@example.edu", "role": "doctor",
        "password": "pw12345", "faculty_id": fac["faculty_id"], "department_id": dept["department_id"],
    }, headers=h)
    assert doc.status_code == 201
    user_id = doc.json()["user_id"]

    upd = client.put(f"/api/users/{user_id}/staff-profile", json={
        "staff_id": "DR-9001", "academic_title": "Associate Professor",
        "specialization": "Distributed Systems", "phone": "555-0100", "status": "active",
    }, headers=h)
    assert upd.status_code == 200

    # Refetch through the staff listing endpoint (a fresh GET, not the PUT response)
    staff_list = client.get(f"/api/staff?department_id={dept['department_id']}&role=doctor", headers=h)
    assert staff_list.status_code == 200
    row = next(s for s in staff_list.json() if s["user_id"] == user_id)
    assert row["staff_id"] == "DR-9001"
    assert row["academic_title"] == "Associate Professor"
    assert row["specialization"] == "Distributed Systems"
    assert row["phone"] == "555-0100"

    # Reject an academic_title outside the closed 6-value set
    bad = client.put(f"/api/users/{user_id}/staff-profile", json={"academic_title": "Chairperson"}, headers=h)
    assert bad.status_code == 422


def test_course_create_update_delete_persist(client, admin_token):
    h = auth(admin_token)
    fac = client.post("/api/faculties", json={"name": "College of Course Testing"}, headers=h).json()
    dept = client.post("/api/departments", json={"faculty_id": fac["faculty_id"], "name": "Course Test Dept"}, headers=h).json()

    create = client.post("/api/courses", json={
        "department_id": dept["department_id"], "code": "CT101", "name": "Intro to Persistence",
        "credit_hours": 3, "level": "100", "semester": "Fall",
    }, headers=h)
    assert create.status_code == 201
    course_id = create.json()["course_id"]

    # Negative credit_hours rejected (positive-integer CheckConstraint mirrored in the schema validator)
    bad = client.post("/api/courses", json={
        "department_id": dept["department_id"], "code": "CT102", "name": "Bad Course", "credit_hours": -1,
    }, headers=h)
    assert bad.status_code == 422

    got = client.get(f"/api/courses?department_id={dept['department_id']}", headers=h)
    row = next(c for c in got.json() if c["course_id"] == course_id)
    assert row["credit_hours"] == 3
    assert row["level"] == "100"

    upd = client.put(f"/api/courses/{course_id}", json={"status": "inactive", "semester": "Spring"}, headers=h)
    assert upd.status_code == 200
    got2 = client.get(f"/api/courses?department_id={dept['department_id']}", headers=h)
    row2 = next(c for c in got2.json() if c["course_id"] == course_id)
    assert row2["status"] == "inactive"
    assert row2["semester"] == "Spring"

    dele = client.delete(f"/api/courses/{course_id}", headers=h)
    assert dele.status_code == 204
    got3 = client.get(f"/api/courses?department_id={dept['department_id']}", headers=h)
    assert all(c["course_id"] != course_id for c in got3.json())


def test_course_assignment_create_update_delete_persist(client, admin_token):
    h = auth(admin_token)
    fac = client.post("/api/faculties", json={"name": "College of Assignment Testing"}, headers=h).json()
    dept = client.post("/api/departments", json={"faculty_id": fac["faculty_id"], "name": "Assignment Test Dept"}, headers=h).json()
    course = client.post("/api/courses", json={
        "department_id": dept["department_id"], "code": "AS201", "name": "Assignment Persistence",
    }, headers=h).json()
    doc = client.post("/api/users", json={
        "name": "Dr. Assignment Check", "email": "assignment.check@example.edu", "role": "doctor",
        "password": "pw12345", "faculty_id": fac["faculty_id"], "department_id": dept["department_id"],
    }, headers=h).json()

    create = client.post(f"/api/courses/{course['course_id']}/assignments", json={
        "user_id": doc["user_id"], "section": "A1", "semester": "Fall", "academic_year": "2026/2027",
    }, headers=h)
    assert create.status_code == 201
    assignment_id = create.json()["assignment_id"]

    got = client.get(f"/api/courses/{course['course_id']}/assignments", headers=h)
    row = next(a for a in got.json() if a["assignment_id"] == assignment_id)
    assert row["section"] == "A1"
    assert row["academic_year"] == "2026/2027"

    upd = client.put(f"/api/courses/{course['course_id']}/assignments/{assignment_id}", json={"status": "inactive"}, headers=h)
    assert upd.status_code == 200
    got2 = client.get(f"/api/courses/{course['course_id']}/assignments", headers=h)
    row2 = next(a for a in got2.json() if a["assignment_id"] == assignment_id)
    assert row2["status"] == "inactive"

    dele = client.delete(f"/api/courses/{course['course_id']}/assignments/{assignment_id}", headers=h)
    assert dele.status_code == 204
    got3 = client.get(f"/api/courses/{course['course_id']}/assignments", headers=h)
    assert all(a["assignment_id"] != assignment_id for a in got3.json())


def test_course_assignment_cross_department_rejected_and_not_persisted(client, admin_token):
    """Business-rule 409 from Phase 5 (still enforced): a staff member
    outside the course's department can't be assigned, and nothing gets
    written when the request is rejected."""
    h = auth(admin_token)
    fac = client.post("/api/faculties", json={"name": "College X"}, headers=h).json()
    dept_a = client.post("/api/departments", json={"faculty_id": fac["faculty_id"], "name": "Dept A"}, headers=h).json()
    dept_b = client.post("/api/departments", json={"faculty_id": fac["faculty_id"], "name": "Dept B"}, headers=h).json()
    course = client.post("/api/courses", json={"department_id": dept_a["department_id"], "code": "X101", "name": "X Course"}, headers=h).json()
    doc_b = client.post("/api/users", json={
        "name": "Dr. In Dept B", "email": "dr.deptb@example.edu", "role": "doctor",
        "password": "pw12345", "faculty_id": fac["faculty_id"], "department_id": dept_b["department_id"],
    }, headers=h).json()

    resp = client.post(f"/api/courses/{course['course_id']}/assignments", json={"user_id": doc_b["user_id"]}, headers=h)
    assert resp.status_code == 409
    # The verbatim backend detail text the frontend is required to surface as-is.
    assert "different department" in resp.json()["detail"]

    got = client.get(f"/api/courses/{course['course_id']}/assignments", headers=h)
    assert got.json() == []
