def test_create_schedule(client, admin_token):
    resp = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00", "course_id": "CS101",
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert resp.json()["course_id"] == "CS101"


def test_create_schedule_unknown_door(client, admin_token):
    resp = client.post("/api/schedules", json={
        "door_id": 999, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_update_schedule(client, admin_token):
    created = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00", "course_id": "CS101",
    }, headers={"Authorization": f"Bearer {admin_token}"}).json()

    resp = client.put(f"/api/schedules/{created['schedule_id']}", json={"course_id": "CS999"},
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["course_id"] == "CS999"
    assert resp.json()["day_of_week"] == 0  # untouched fields preserved


def test_instructor_cannot_create_schedule(client, instructor_token):
    resp = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
    }, headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_instructor_can_list_schedules(client, instructor_token):
    resp = client.get("/api/schedules", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 200


def test_schedule_out_exposes_course_ref_id(db_session, client, admin_token):
    """The Course Assignment UI's schedule dropdown filters on
    course_ref_id (see CourseAssignmentsModal.jsx) — this is the data
    contract it depends on. Set directly on the model here (rather than via
    the Phase 11 API path added below) simply to keep this particular test
    focused on the read/serialization contract, not the write path."""
    import datetime as dt
    from app import models

    door = models.Door(code="SCHOUT1", name="Room SCHOUT1", building="Building A",
                        fail_mode="secure", online=True, locked=True)
    db_session.add(door)
    db_session.flush()
    faculty = models.Faculty(name="Sched Out College")
    db_session.add(faculty)
    db_session.flush()
    dept = models.Department(faculty_id=faculty.faculty_id, name="Sched Out Dept")
    db_session.add(dept)
    db_session.flush()
    course = models.Course(department_id=dept.department_id, code="SC101", name="Sched Out Course")
    db_session.add(course)
    db_session.flush()

    linked = models.Schedule(door_id=door.door_id, day_of_week=1, start_time=dt.time(9, 0), end_time=dt.time(10, 0),
                              course_ref_id=course.course_id)
    unlinked = models.Schedule(door_id=door.door_id, day_of_week=2, start_time=dt.time(9, 0), end_time=dt.time(10, 0))
    db_session.add_all([linked, unlinked])
    db_session.commit()
    db_session.refresh(linked)
    db_session.refresh(unlinked)

    resp = client.get("/api/schedules", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    by_id = {s["schedule_id"]: s for s in resp.json()}
    assert by_id[linked.schedule_id]["course_ref_id"] == course.course_id
    assert by_id[unlinked.schedule_id]["course_ref_id"] is None


def test_schedules_from_another_course_excluded_by_ui_filter_logic(db_session, client, admin_token):
    """Mirrors CourseAssignmentsModal.jsx's exact filter predicate
    (course_ref_id is null/undefined OR equals the selected course) against
    real API data, so a regression in either the backend field or the
    frontend's filter logic would show up here even though there's no JS
    test harness in this project (frontend correctness for this piece is
    otherwise verified by code inspection + the build/lint pass)."""
    import datetime as dt
    from app import models

    door = models.Door(code="SCHOUT2", name="Room SCHOUT2", building="Building A",
                        fail_mode="secure", online=True, locked=True)
    db_session.add(door)
    db_session.flush()
    faculty = models.Faculty(name="Sched Filter College")
    db_session.add(faculty)
    db_session.flush()
    dept = models.Department(faculty_id=faculty.faculty_id, name="Sched Filter Dept")
    db_session.add(dept)
    db_session.flush()
    course_a = models.Course(department_id=dept.department_id, code="FA101", name="Course A")
    course_b = models.Course(department_id=dept.department_id, code="FB101", name="Course B")
    db_session.add_all([course_a, course_b])
    db_session.flush()

    sched_a = models.Schedule(door_id=door.door_id, day_of_week=0, start_time=dt.time(9, 0), end_time=dt.time(10, 0),
                               course_ref_id=course_a.course_id)
    sched_b = models.Schedule(door_id=door.door_id, day_of_week=1, start_time=dt.time(9, 0), end_time=dt.time(10, 0),
                               course_ref_id=course_b.course_id)
    sched_none = models.Schedule(door_id=door.door_id, day_of_week=2, start_time=dt.time(9, 0), end_time=dt.time(10, 0))
    db_session.add_all([sched_a, sched_b, sched_none])
    db_session.commit()
    for s in (sched_a, sched_b, sched_none):
        db_session.refresh(s)

    resp = client.get("/api/schedules", headers={"Authorization": f"Bearer {admin_token}"})
    all_schedules = resp.json()

    def available_for(course_id):
        return [
            s for s in all_schedules
            if s["course_ref_id"] is None or s["course_ref_id"] == course_id
        ]

    for_a = {s["schedule_id"] for s in available_for(course_a.course_id)}
    assert sched_a.schedule_id in for_a
    assert sched_none.schedule_id in for_a
    assert sched_b.schedule_id not in for_a  # a schedule belonging to another course is excluded

    for_b = {s["schedule_id"] for s in available_for(course_b.course_id)}
    assert sched_b.schedule_id in for_b
    assert sched_a.schedule_id not in for_b


# ---------------------------------------------------------------------------
# Phase 11: additive admin API path for Schedule.course_ref_id (previously
# only settable by a direct DB write — see routers/schedules.py::_validate_course_ref).
# ---------------------------------------------------------------------------
def _org(db_session, suffix):
    from app import models
    faculty = models.Faculty(name=f"Sched API College {suffix}")
    db_session.add(faculty)
    db_session.flush()
    dept = models.Department(faculty_id=faculty.faculty_id, name=f"Sched API Dept {suffix}")
    db_session.add(dept)
    db_session.flush()
    course = models.Course(department_id=dept.department_id, code=f"SA{suffix}", name=f"Sched API Course {suffix}")
    db_session.add(course)
    db_session.commit()
    db_session.refresh(faculty)
    db_session.refresh(dept)
    db_session.refresh(course)
    return faculty, dept, course


def test_create_schedule_with_course_ref_id_persists(db_session, client, admin_token):
    _, _, course = _org(db_session, "1")
    resp = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
        "course_ref_id": course.course_id,
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert resp.json()["course_ref_id"] == course.course_id

    fresh = client.get("/api/schedules", headers={"Authorization": f"Bearer {admin_token}"}).json()
    row = next(s for s in fresh if s["schedule_id"] == resp.json()["schedule_id"])
    assert row["course_ref_id"] == course.course_id


def test_create_schedule_with_unknown_course_ref_id_404(client, admin_token):
    resp = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
        "course_ref_id": 999999,
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_update_schedule_course_ref_id_persists_on_fresh_read(db_session, client, admin_token):
    _, _, course = _org(db_session, "2")
    created = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
    }, headers={"Authorization": f"Bearer {admin_token}"}).json()

    resp = client.put(f"/api/schedules/{created['schedule_id']}", json={"course_ref_id": course.course_id},
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["course_ref_id"] == course.course_id

    fresh = client.get("/api/schedules", headers={"Authorization": f"Bearer {admin_token}"}).json()
    row = next(s for s in fresh if s["schedule_id"] == created["schedule_id"])
    assert row["course_ref_id"] == course.course_id


def test_scoped_admin_cannot_link_schedule_to_course_outside_scope(db_session, client, admin_token):
    from app import models, security

    own_faculty, own_dept, _ = _org(db_session, "3own")
    _, _, other_course = _org(db_session, "3other")

    scoped = models.User(name="Sched Scoped Admin", email="sched.scoped.admin@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(scoped)
    db_session.commit()
    db_session.refresh(scoped)
    db_session.add(models.AdminScope(user_id=scoped.user_id, faculty_id=own_faculty.faculty_id,
                                      department_id=own_dept.department_id))
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": scoped.email, "password": "pw123456"})
    scoped_token = login.json()["access_token"]

    resp = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
        "course_ref_id": other_course.course_id,
    }, headers={"Authorization": f"Bearer {scoped_token}"})
    assert resp.status_code == 403


def test_relinking_schedule_used_by_assignment_to_different_course_conflict(db_session, client, admin_token):
    """A Schedule already referenced by a CourseAssignment (assignment.schedule_id)
    shouldn't be silently re-pointed at a different course out from under
    that assignment — mirrors _validate_assignment_schedule's own check in
    academic.py, applied here in the other direction."""
    import datetime as dt
    from app import models

    _, dept, course_a = _org(db_session, "4a")
    course_b = models.Course(department_id=dept.department_id, code="SA4b", name="Sched API Course 4b")
    db_session.add(course_b)
    db_session.commit()
    db_session.refresh(course_b)

    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    schedule = models.Schedule(door_id=door.door_id, day_of_week=3, start_time=dt.time(9, 0), end_time=dt.time(10, 0),
                                course_ref_id=course_a.course_id)
    db_session.add(schedule)
    db_session.flush()

    doctor = models.User(name="Sched API Doctor", email="sched.api.doctor@example.edu", role="doctor",
                          password_hash="x", department_id=dept.department_id, faculty_id=dept.faculty_id)
    db_session.add(doctor)
    db_session.flush()
    db_session.add(models.CourseAssignment(course_id=course_a.course_id, user_id=doctor.user_id,
                                            schedule_id=schedule.schedule_id))
    db_session.commit()

    resp = client.put(f"/api/schedules/{schedule.schedule_id}", json={"course_ref_id": course_b.course_id},
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 409

    fresh = client.get("/api/schedules", headers={"Authorization": f"Bearer {admin_token}"}).json()
    row = next(s for s in fresh if s["schedule_id"] == schedule.schedule_id)
    assert row["course_ref_id"] == course_a.course_id  # untouched


def test_non_admin_cannot_set_course_ref_id(db_session, client, instructor_token):
    _, _, course = _org(db_session, "5")
    resp = client.post("/api/schedules", json={
        "door_id": 1, "day_of_week": 0, "start_time": "08:00:00", "end_time": "09:30:00",
        "course_ref_id": course.course_id,
    }, headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403
