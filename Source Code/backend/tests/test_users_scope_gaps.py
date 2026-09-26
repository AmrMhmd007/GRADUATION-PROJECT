"""
Regression tests for scope-check gaps closed in app/routers/users.py during
the final hardening pass: door-assignment CRUD and bulk staff import used to
enforce require_admin only, letting a scope-restricted admin act on staff
outside their own college/department. These mirror the existing pattern in
test_org_hierarchy.py.
"""
import io

from openpyxl import Workbook

from app import models, security


def _college(db, name):
    c = models.Faculty(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _staff(db, name, faculty_id=None):
    u = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="instructor",
                     password_hash=security.hash_password("pw123456"), faculty_id=faculty_id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _scoped_admin_token(client, db, name, faculty_id):
    admin = models.User(name=name, email=f"{name.lower().replace(' ', '.')}@example.edu", role="admin",
                         password_hash=security.hash_password("pw123456"))
    db.add(admin)
    db.commit()
    db.refresh(admin)
    db.add(models.AdminScope(user_id=admin.user_id, faculty_id=faculty_id))
    db.commit()
    resp = client.post("/api/auth/login", json={"email": admin.email, "password": "pw123456"})
    return admin, resp.json()["access_token"]


def _door(db, code="SG101"):
    d = models.Door(code=code, name=f"Room {code}", building="Building A", fail_mode="secure", online=True, locked=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def test_scoped_admin_cannot_add_door_assignment_for_other_college_staff(db_session, client, admin_token):
    eng = _college(db_session, "Engineering")
    business = _college(db_session, "Business")
    other_ta = _staff(db_session, "Business TA", faculty_id=business.faculty_id)
    door = _door(db_session)
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG", eng.faculty_id)

    headers = {"Authorization": f"Bearer {eng_admin_token}"}
    resp = client.post(f"/api/users/{other_ta.user_id}/doors", json={"door_id": door.door_id}, headers=headers)
    assert resp.status_code == 403


def test_scoped_admin_cannot_list_or_remove_door_assignment_for_other_college_staff(db_session, client, admin_token):
    eng = _college(db_session, "Engineering2")
    business = _college(db_session, "Business2")
    other_ta = _staff(db_session, "Business TA2", faculty_id=business.faculty_id)
    door = _door(db_session, code="SG102")
    unrestricted_headers = {"Authorization": f"Bearer {admin_token}"}
    add_resp = client.post(f"/api/users/{other_ta.user_id}/doors", json={"door_id": door.door_id}, headers=unrestricted_headers)
    assert add_resp.status_code == 201
    assignment_id = add_resp.json()["assignment_id"]

    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG2", eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    list_resp = client.get(f"/api/users/{other_ta.user_id}/doors", headers=headers)
    assert list_resp.status_code == 403

    remove_resp = client.delete(f"/api/users/{other_ta.user_id}/doors/{assignment_id}", headers=headers)
    assert remove_resp.status_code == 403


def test_scoped_admin_can_manage_door_assignment_for_own_college_staff(db_session, client, admin_token):
    eng = _college(db_session, "Engineering3")
    own_ta = _staff(db_session, "Eng TA", faculty_id=eng.faculty_id)
    door = _door(db_session, code="SG103")
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG3", eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    add_resp = client.post(f"/api/users/{own_ta.user_id}/doors", json={"door_id": door.door_id}, headers=headers)
    assert add_resp.status_code == 201


def test_scoped_admin_cannot_delete_other_college_staff(db_session, client, admin_token):
    eng = _college(db_session, "Engineering4")
    business = _college(db_session, "Business4")
    other_ta = _staff(db_session, "Business TA4", faculty_id=business.faculty_id)
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG4", eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    resp = client.delete(f"/api/users/{other_ta.user_id}", headers=headers)
    assert resp.status_code == 403


def test_scoped_admin_cannot_delete_admin_account(db_session, client, admin_token):
    eng = _college(db_session, "Engineering5")
    other_admin = models.User(name="Other Admin", email="other.admin@example.edu", role="admin",
                               password_hash=security.hash_password("pw123456"))
    db_session.add(other_admin)
    db_session.commit()
    db_session.refresh(other_admin)
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG5", eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    resp = client.delete(f"/api/users/{other_admin.user_id}", headers=headers)
    assert resp.status_code == 403


def _xlsx_bytes(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def test_scoped_admin_import_blocked_for_other_college(db_session, client, admin_token):
    eng = _college(db_session, "Engineering6")
    business = _college(db_session, "Business6")
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG6", eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    xlsx = _xlsx_bytes([("Name", "Faculty"), ("New TA", business.name)])
    resp = client.post(
        "/api/users/import",
        data={"role": "instructor"},
        files={"file": ("staff.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == []
    assert any("not authorized" in e for e in body["errors"])
    assert db_session.query(models.User).filter(models.User.email == "new.ta@aiu.is").first() is None


def test_scoped_admin_import_succeeds_for_own_college(db_session, client, admin_token):
    eng = _college(db_session, "Engineering7")
    _, eng_admin_token = _scoped_admin_token(client, db_session, "Eng Admin SG7", eng.faculty_id)
    headers = {"Authorization": f"Bearer {eng_admin_token}"}

    xlsx = _xlsx_bytes([("Name", "Faculty"), ("Own TA", eng.name)])
    resp = client.post(
        "/api/users/import",
        data={"role": "instructor"},
        files={"file": ("staff.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 1
