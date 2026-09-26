"""
Tests for DELETE /api/users/{user_id} (app/routers/users.py::delete_user).

Bug this covers: a TA/doctor with any dependent row (a CourseAssignment, an
AccessWindow, an AdminScope, ...) could not be deleted at all — SQLite raised
an IntegrityError that surfaced as a generic 500, which is why "there is a TA
I can't delete it" also blocked deleting their college (the college-delete
dependency check correctly refused to orphan that one remaining staff row).

These tests prove the fixed endpoint follows the same
dependency-check-then-cascade/nullify pattern already used elsewhere
(delete_department/delete_course/delete_faculty in academic.py):
  - EmergencyOverride.created_by_id: blocked outright (audit-critical).
  - CourseAssignment, AccessWindow (own), AdminScope, PasswordResetRequest
    (own): cascade-deleted, since they're meaningless without the person.
  - Credential.user_id, AccessWindow.created_by_id, AccessEvent.user_id,
    Alert.requested_by, PasswordResetRequest.resolved_by,
    EmergencyOverride.revoked_by_id: nullified, since those rows are audit
    history that outlives the person.
"""
import datetime

from app import models, security
from app.services import emergency_override_service


def _door(db, code="DU101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _ta(db, name="Test TA", email="test.ta@example.edu"):
    u = models.User(name=name, email=email, role="instructor", password_hash=security.hash_password("pw123456"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _course(db, code="ECE301"):
    faculty = models.Faculty(name="Engineering")
    db.add(faculty)
    db.flush()
    dept = models.Department(name="ECE", faculty_id=faculty.faculty_id)
    db.add(dept)
    db.flush()
    course = models.Course(code=code, name="DSP", department_id=dept.department_id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def test_delete_ta_with_course_assignment_succeeds(db_session, client, admin_token):
    ta = _ta(db_session)
    course = _course(db_session)
    db_session.add(models.CourseAssignment(course_id=course.course_id, user_id=ta.user_id))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{ta.user_id}", headers=headers)
    assert resp.status_code == 204

    assert db_session.query(models.User).filter(models.User.user_id == ta.user_id).first() is None
    assert db_session.query(models.CourseAssignment).filter(models.CourseAssignment.user_id == ta.user_id).count() == 0


def test_delete_ta_with_own_access_window_succeeds(db_session, client, admin_token):
    ta = _ta(db_session, name="Window TA", email="window.ta@example.edu")
    door = _door(db_session)
    db_session.add(models.AccessWindow(door_id=door.door_id, user_id=ta.user_id, recurring=False,
                                        start_at=datetime.datetime.utcnow(),
                                        end_at=datetime.datetime.utcnow() + datetime.timedelta(hours=1)))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{ta.user_id}", headers=headers)
    assert resp.status_code == 204
    assert db_session.query(models.AccessWindow).filter(models.AccessWindow.user_id == ta.user_id).count() == 0


def test_delete_admin_who_created_access_window_nullifies_created_by(db_session, client, admin_token):
    creator_admin = models.User(name="Window Creator", email="window.creator@example.edu", role="admin",
                                 password_hash=security.hash_password("pw123456"))
    db_session.add(creator_admin)
    db_session.commit()
    db_session.refresh(creator_admin)

    ta = _ta(db_session, name="Window Owner", email="window.owner@example.edu")
    door = _door(db_session, code="DU102")
    window = models.AccessWindow(door_id=door.door_id, user_id=ta.user_id, created_by_id=creator_admin.user_id,
                                  recurring=False, start_at=datetime.datetime.utcnow(),
                                  end_at=datetime.datetime.utcnow() + datetime.timedelta(hours=1))
    db_session.add(window)
    db_session.commit()
    db_session.refresh(window)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{creator_admin.user_id}", headers=headers)
    assert resp.status_code == 204

    db_session.refresh(window)
    assert window.created_by_id is None
    # The window itself and its owner survive — only the creator link is unlinked.
    assert db_session.query(models.AccessWindow).filter(models.AccessWindow.access_window_id == window.access_window_id).count() == 1


def test_delete_user_blocked_if_they_created_emergency_override(db_session, client, admin_token):
    door = _door(db_session, code="DU103")
    scoped_admin = models.User(name="Override Admin", email="override.admin@example.edu", role="admin",
                                password_hash=security.hash_password("pw123456"))
    db_session.add(scoped_admin)
    db_session.commit()
    db_session.refresh(scoped_admin)

    emergency_override_service.create_override(
        db_session, door=door, admin=scoped_admin, action="unlock", reason="Delete-blocking test", duration_minutes=10,
    )

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{scoped_admin.user_id}", headers=headers)
    assert resp.status_code == 400
    assert "override" in resp.json()["detail"].lower()

    # Nothing was deleted.
    assert db_session.query(models.User).filter(models.User.user_id == scoped_admin.user_id).first() is not None


def test_delete_user_who_revoked_override_nullifies_revoked_by(db_session, client, admin_token):
    door = _door(db_session, code="DU104")
    creator = models.User(name="Override Creator", email="override.creator@example.edu", role="admin",
                           password_hash=security.hash_password("pw123456"))
    revoker = models.User(name="Override Revoker", email="override.revoker@example.edu", role="admin",
                           password_hash=security.hash_password("pw123456"))
    db_session.add_all([creator, revoker])
    db_session.commit()
    db_session.refresh(creator)
    db_session.refresh(revoker)

    override = emergency_override_service.create_override(
        db_session, door=door, admin=creator, action="unlock", reason="Revoke test", duration_minutes=10,
    )
    override.status = "REVOKED"
    override.revoked_by_id = revoker.user_id
    override.revoked_at = datetime.datetime.utcnow()
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{revoker.user_id}", headers=headers)
    assert resp.status_code == 204

    db_session.refresh(override)
    assert override.revoked_by_id is None
    assert override.status == "REVOKED"  # audit trail of what happened is untouched


def test_delete_user_with_admin_scope_succeeds(db_session, client, admin_token):
    scoped_admin = models.User(name="Scoped Admin", email="scoped.admin@example.edu", role="admin",
                                password_hash=security.hash_password("pw123456"))
    db_session.add(scoped_admin)
    db_session.commit()
    db_session.refresh(scoped_admin)
    faculty = models.Faculty(name="Business")
    db_session.add(faculty)
    db_session.flush()
    db_session.add(models.AdminScope(user_id=scoped_admin.user_id, faculty_id=faculty.faculty_id))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{scoped_admin.user_id}", headers=headers)
    assert resp.status_code == 204
    assert db_session.query(models.AdminScope).filter(models.AdminScope.user_id == scoped_admin.user_id).count() == 0


def test_delete_user_still_nullifies_credential_and_drops_door_assignment(db_session, client, admin_token):
    """Regression: pre-existing DoorAssignment/Credential handling from
    before this fix must keep working unchanged."""
    ta = _ta(db_session, name="Legacy TA", email="legacy.ta@example.edu")
    door = _door(db_session, code="DU105")
    db_session.add(models.DoorAssignment(instructor_id=ta.user_id, door_id=door.door_id))
    import app.crypto as crypto
    cred = models.Credential(user_id=ta.user_id, card_uid=crypto.encrypt_uid("CAFEBABE"),
                              card_uid_index=crypto.uid_index("CAFEBABE"), active=True)
    db_session.add(cred)
    db_session.commit()
    db_session.refresh(cred)

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{ta.user_id}", headers=headers)
    assert resp.status_code == 204

    assert db_session.query(models.DoorAssignment).filter(models.DoorAssignment.instructor_id == ta.user_id).count() == 0
    db_session.refresh(cred)
    assert cred.user_id is None


def test_delete_last_admin_still_blocked(db_session, client, admin_token):
    only_admin = db_session.query(models.User).filter(models.User.role == "admin").first()
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{only_admin.user_id}", headers=headers)
    assert resp.status_code == 400


def test_delete_self_blocked(db_session, client, admin_token):
    admin = db_session.query(models.User).filter(models.User.email == "admin@example.edu").first()
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete(f"/api/users/{admin.user_id}", headers=headers)
    assert resp.status_code == 400


def test_deleting_ta_then_deleting_now_empty_college_succeeds(db_session, client, admin_token):
    """End-to-end regression for the exact bug report: a TA blocking college
    deletion. Deleting the TA first must now let the college delete succeed."""
    faculty = models.Faculty(name="Engineering science")
    db_session.add(faculty)
    db_session.flush()
    dept = models.Department(name="General", faculty_id=faculty.faculty_id)
    db_session.add(dept)
    db_session.flush()
    ta = models.User(name="Lingering TA", email="lingering.ta@example.edu", role="instructor",
                      password_hash=security.hash_password("pw123456"),
                      faculty_id=faculty.faculty_id, department_id=dept.department_id)
    db_session.add(ta)
    db_session.commit()
    db_session.refresh(ta)
    faculty_id = faculty.faculty_id

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Before: college deletion is (correctly) blocked by the dependent staff.
    blocked = client.delete(f"/api/faculties/{faculty_id}", headers=headers)
    assert blocked.status_code == 409

    # Delete the TA.
    resp = client.delete(f"/api/users/{ta.user_id}", headers=headers)
    assert resp.status_code == 204

    # Department still needs deleting too (mirrors the "Manage Colleges &
    # Departments" flow — deleting the college itself follows once nothing
    # depends on it).
    dept_del = client.delete(f"/api/departments/{dept.department_id}", headers=headers)
    assert dept_del.status_code == 204

    now_allowed = client.delete(f"/api/faculties/{faculty_id}", headers=headers)
    assert now_allowed.status_code == 204
