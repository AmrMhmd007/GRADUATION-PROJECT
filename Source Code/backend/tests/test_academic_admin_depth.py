"""
Tests for the final-hardening-pass Academic Administration depth: additive
fields on Faculty(College)/Department/User(staff)/Course/CourseAssignment,
their validation, and the new cross-department/cross-college assignment
business rules. See app/models.py and app/routers/{faculties,academic,users}.py
for the implementation this exercises.
"""
import datetime

from app import models, security


def _faculty(db, name="Engineering", code=None):
    f = models.Faculty(name=name, code=code)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _department(db, faculty_id, name="ECE"):
    d = models.Department(faculty_id=faculty_id, name=name)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _course(db, department_id, code="ECE301", name="DSP"):
    c = models.Course(department_id=department_id, code=code, name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _staff(db, name, role="doctor", faculty_id=None, department_id=None):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role=role,
                     password_hash=security.hash_password("pw123456"),
                     faculty_id=faculty_id, department_id=department_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# College (Faculty)
# ---------------------------------------------------------------------------
def test_create_college_with_code_and_description(db_session, client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/faculties", json={"name": "Faculty of Engineering", "code": "ENG", "description": "Engineering programs"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "ENG"
    assert body["status"] == "active"
    assert body["departments_count"] == 0


def test_duplicate_college_code_rejected(db_session, client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/faculties", json={"name": "College A", "code": "DUP"}, headers=headers)
    resp = client.post("/api/faculties", json={"name": "College B", "code": "DUP"}, headers=headers)
    assert resp.status_code == 409


def test_college_rollup_counts_reflect_real_data(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng2")
    dept = _department(db_session, eng.faculty_id)
    _staff(db_session, "Doc1", role="doctor", faculty_id=eng.faculty_id, department_id=dept.department_id)
    _staff(db_session, "TA1", role="instructor", faculty_id=eng.faculty_id, department_id=dept.department_id)
    _course(db_session, dept.department_id)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/faculties", headers=headers)
    body = next(f for f in resp.json() if f["faculty_id"] == eng.faculty_id)
    assert body["departments_count"] == 1
    assert body["doctors_count"] == 1
    assert body["tas_count"] == 1
    assert body["courses_count"] == 1


def test_update_college_status_to_inactive(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng3")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(f"/api/faculties/{eng.faculty_id}", json={"status": "inactive"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


def test_invalid_college_status_rejected(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng4")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(f"/api/faculties/{eng.faculty_id}", json={"status": "deleted"}, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------
def test_create_department_with_code_and_counts(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng5")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/departments", json={"faculty_id": eng.faculty_id, "name": "ECE", "code": "ECE", "description": "Electronics"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "ECE"
    assert body["doctors_count"] == 0


def test_update_department_status(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng6")
    dept = _department(db_session, eng.faculty_id)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(f"/api/departments/{dept.department_id}", json={"status": "inactive", "description": "Being phased out"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
def test_create_course_with_credit_hours_and_semester(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng7")
    dept = _department(db_session, eng.faculty_id)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/courses", json={
        "department_id": dept.department_id, "code": "ECE301", "name": "DSP",
        "credit_hours": 3, "level": "3", "semester": "Fall",
    }, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["credit_hours"] == 3
    assert body["semester"] == "Fall"


def test_negative_credit_hours_rejected(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng8")
    dept = _department(db_session, eng.faculty_id)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/courses", json={
        "department_id": dept.department_id, "code": "ECE302", "name": "Bad Course", "credit_hours": 0,
    }, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Staff profile fields (academic_title validation, staff_id uniqueness)
# ---------------------------------------------------------------------------
def test_create_staff_with_valid_academic_title(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng9")
    dept = _department(db_session, eng.faculty_id)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/users", json={
        "name": "Dr Ahmed", "email": "ahmed@example.edu", "role": "doctor", "password": "pw123456",
        "faculty_id": eng.faculty_id, "department_id": dept.department_id,
        "staff_id": "EMP-001", "academic_title": "Assistant Professor", "specialization": "Signal Processing",
        "phone": "555-1234",
    }, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["academic_title"] == "Assistant Professor"
    assert body["staff_id"] == "EMP-001"


def test_invalid_academic_title_rejected(db_session, client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/users", json={
        "name": "Bad Title", "email": "bad.title@example.edu", "role": "doctor", "password": "pw123456",
        "academic_title": "Wizard",
    }, headers=headers)
    assert resp.status_code == 422


def test_duplicate_staff_id_rejected(db_session, client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/users", json={
        "name": "First", "email": "first.staff@example.edu", "role": "doctor", "password": "pw123456",
        "staff_id": "EMP-DUP",
    }, headers=headers)
    resp = client.post("/api/users", json={
        "name": "Second", "email": "second.staff@example.edu", "role": "doctor", "password": "pw123456",
        "staff_id": "EMP-DUP",
    }, headers=headers)
    assert resp.status_code == 409


def test_update_staff_profile_and_deactivate(db_session, client, admin_token):
    doc = _staff(db_session, "Dr Sara", role="doctor")
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(f"/api/users/{doc.user_id}/staff-profile", json={
        "academic_title": "Professor", "specialization": "Networks", "status": "inactive",
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["academic_title"] == "Professor"
    assert body["status"] == "inactive"


# ---------------------------------------------------------------------------
# Course assignments — section/semester/term + cross-department/college rules
# ---------------------------------------------------------------------------
def test_assign_doctor_with_section_and_term(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng10")
    dept = _department(db_session, eng.faculty_id)
    course = _course(db_session, dept.department_id)
    doc = _staff(db_session, "Dr Term", role="doctor", faculty_id=eng.faculty_id, department_id=dept.department_id)
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course.course_id}/assignments", json={
        "user_id": doc.user_id, "section": "1", "semester": "Fall", "academic_year": "2026/2027",
    }, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["section"] == "1"
    assert body["academic_year"] == "2026/2027"


def test_cross_department_assignment_rejected(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng11")
    dept_a = _department(db_session, eng.faculty_id, "ECE")
    dept_b = _department(db_session, eng.faculty_id, "Mechanical")
    course = _course(db_session, dept_a.department_id, code="ECE401")
    mech_doctor = _staff(db_session, "Dr Mech", role="doctor", faculty_id=eng.faculty_id, department_id=dept_b.department_id)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": mech_doctor.user_id}, headers=headers)
    assert resp.status_code == 409


def test_cross_college_assignment_rejected_for_unassigned_department_staff(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng12")
    business = _faculty(db_session, "Business12")
    dept = _department(db_session, eng.faculty_id)
    course = _course(db_session, dept.department_id, code="ECE501")
    # Staff has a faculty but no department yet — should still be blocked
    # from a course in a different college.
    business_doctor = _staff(db_session, "Dr Biz", role="doctor", faculty_id=business.faculty_id)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": business_doctor.user_id}, headers=headers)
    assert resp.status_code == 409


def test_same_department_assignment_succeeds(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng13")
    dept = _department(db_session, eng.faculty_id)
    course = _course(db_session, dept.department_id, code="ECE601")
    doc = _staff(db_session, "Dr Same", role="doctor", faculty_id=eng.faculty_id, department_id=dept.department_id)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": doc.user_id}, headers=headers)
    assert resp.status_code == 201


def test_assignment_schedule_must_belong_to_same_course(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng14")
    dept = _department(db_session, eng.faculty_id)
    course_a = _course(db_session, dept.department_id, code="A101")
    course_b = _course(db_session, dept.department_id, code="B101")
    doc = _staff(db_session, "Dr Sched", role="doctor", faculty_id=eng.faculty_id, department_id=dept.department_id)
    door = models.Door(code="ASG101", name="Room ASG101", building="Building A", fail_mode="secure", online=True, locked=True)
    db_session.add(door)
    db_session.flush()
    schedule = models.Schedule(door_id=door.door_id, day_of_week=0, start_time=datetime.time(9, 0), end_time=datetime.time(10, 0), course_ref_id=course_b.course_id)
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course_a.course_id}/assignments", json={
        "user_id": doc.user_id, "schedule_id": schedule.schedule_id,
    }, headers=headers)
    assert resp.status_code == 409


def test_assignment_room_resolved_from_schedule(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng15")
    dept = _department(db_session, eng.faculty_id)
    course = _course(db_session, dept.department_id, code="C101")
    doc = _staff(db_session, "Dr Room", role="doctor", faculty_id=eng.faculty_id, department_id=dept.department_id)
    door = models.Door(code="ASG102", name="Room ASG102", building="Building A", fail_mode="secure", online=True, locked=True)
    db_session.add(door)
    db_session.flush()
    schedule = models.Schedule(door_id=door.door_id, day_of_week=0, start_time=datetime.time(9, 0), end_time=datetime.time(10, 0), course_ref_id=course.course_id)
    db_session.add(schedule)
    db_session.commit()
    db_session.refresh(schedule)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(f"/api/courses/{course.course_id}/assignments", json={
        "user_id": doc.user_id, "schedule_id": schedule.schedule_id,
    }, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["room_code"] == "ASG102"


def test_update_assignment_status_and_term(db_session, client, admin_token):
    eng = _faculty(db_session, "Eng16")
    dept = _department(db_session, eng.faculty_id)
    course = _course(db_session, dept.department_id, code="D101")
    doc = _staff(db_session, "Dr Update", role="doctor", faculty_id=eng.faculty_id, department_id=dept.department_id)
    headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(f"/api/courses/{course.course_id}/assignments", json={"user_id": doc.user_id}, headers=headers)
    assignment_id = create.json()["assignment_id"]

    resp = client.put(f"/api/courses/{course.course_id}/assignments/{assignment_id}", json={
        "status": "inactive", "semester": "Spring",
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "inactive"
    assert body["semester"] == "Spring"
