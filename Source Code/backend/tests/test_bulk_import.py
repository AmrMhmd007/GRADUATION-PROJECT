"""
Phase 11 Priority 3 — dedicated tests for the existing bulk door/user
import endpoints (POST /api/doors/import, POST /api/users/import), which
had only incidental coverage per the Phase 9/10 audits. No import behavior
is changed here — these tests exercise the exact existing implementation
in app/routers/doors.py::import_doors and app/routers/users.py::import_users.
"""
import io

import openpyxl

from app import models


def _admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _xlsx_bytes(rows):
    """rows[0] is the header row; the rest are data rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Door import
# ---------------------------------------------------------------------------
def test_door_import_valid_rows_persist(client, db_session, admin_token):
    xlsx = _xlsx_bytes([
        ["Code", "Name", "Building", "Category"],
        ["IMP101", "Room IMP101", "Import Hall", "access_service"],
        ["IMP102", "Room IMP102", "Import Hall", "critical"],
    ])
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert set(body["created_codes"]) == {"IMP101", "IMP102"}

    # Fresh GET, not the import response.
    doors = client.get("/api/doors", headers=_admin(admin_token)).json()
    codes = {d["code"] for d in doors}
    assert {"IMP101", "IMP102"} <= codes
    imp102 = next(d for d in doors if d["code"] == "IMP102")
    assert imp102["category"] == "critical"

    # The building referenced by the import should also now exist.
    buildings = client.get("/api/buildings", headers=_admin(admin_token)).json()
    assert any(b["name"] == "Import Hall" for b in buildings)


def test_door_import_malformed_row_skipped_others_still_created(client, admin_token):
    xlsx = _xlsx_bytes([
        ["Code", "Name", "Building"],
        ["IMP201", "Room IMP201", "Import Hall 2"],
        ["", "Missing Code Room", "Import Hall 2"],  # malformed: no code
        ["IMP203", "", "Import Hall 2"],  # malformed: no name
    ])
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["created_codes"] == ["IMP201"]
    assert len(body["errors"]) == 2  # both malformed rows reported, not silently dropped

    doors = client.get("/api/doors", headers=_admin(admin_token)).json()
    assert any(d["code"] == "IMP201" for d in doors)
    assert not any(d["code"] == "IMP203" for d in doors)  # never created


def test_door_import_duplicate_code_skipped_not_duplicated(client, admin_token):
    client.post("/api/doors", json={"code": "IMPDUP1", "name": "Existing", "building": "B", "fail_mode": "secure"},
                headers=_admin(admin_token))
    xlsx = _xlsx_bytes([
        ["Code", "Name", "Building"],
        ["IMPDUP1", "Duplicate Attempt", "Import Hall 3"],
    ])
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["skipped"]) == 1
    assert "already exists" in body["skipped"][0]

    doors = client.get("/api/doors", headers=_admin(admin_token)).json()
    assert len([d for d in doors if d["code"] == "IMPDUP1"]) == 1  # not duplicated


def test_door_import_rejects_non_xlsx_file(client, admin_token):
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.csv", io.BytesIO(b"Code,Name,Building\nX,Y,Z"), "text/csv")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 400

    doors = client.get("/api/doors", headers=_admin(admin_token)).json()
    assert not any(d["code"] == "X" for d in doors)


def test_door_import_rejects_unparseable_file_content(client, admin_token):
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.xlsx", io.BytesIO(b"not actually an xlsx file"),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 400


def test_door_import_missing_required_columns_rejected(client, admin_token):
    xlsx = _xlsx_bytes([["Foo", "Bar"], ["1", "2"]])
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 400


def test_non_admin_cannot_import_doors(client, instructor_token):
    xlsx = _xlsx_bytes([["Code", "Name", "Building"], ["IMPX", "X", "Y"]])
    resp = client.post(
        "/api/doors/import",
        files={"file": ("doors.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# User import
# ---------------------------------------------------------------------------
def test_user_import_valid_rows_persist_with_generated_password(client, admin_token):
    xlsx = _xlsx_bytes([
        ["Name", "Email"],
        ["Import Doctor One", "import.doc1@example.edu"],
    ])
    resp = client.post(
        "/api/users/import",
        data={"role": "doctor"},
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["email"] == "import.doc1@example.edu"
    assert body["created"][0]["password"]  # a real generated password is returned, not blank

    users = client.get("/api/users", headers=_admin(admin_token)).json()
    row = next(u for u in users if u["email"] == "import.doc1@example.edu")
    assert row["role"] == "doctor"

    # The generated password actually works.
    login = client.post("/api/auth/login", json={"email": "import.doc1@example.edu", "password": body["created"][0]["password"]})
    assert login.status_code == 200


def test_user_import_duplicate_email_skipped(client, admin_token):
    xlsx = _xlsx_bytes([["Name", "Email"], ["Dup Import", "instructor@example.edu"]])  # already exists (conftest fixture)
    resp = client.post(
        "/api/users/import",
        data={"role": "instructor"},
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == []
    assert len(body["skipped"]) == 1
    assert "already exists" in body["skipped"][0]


def test_user_import_missing_name_row_errors_without_creating(client, admin_token):
    xlsx = _xlsx_bytes([["Name", "Email"], ["", "noname@example.edu"]])
    resp = client.post(
        "/api/users/import",
        data={"role": "doctor"},
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == []
    assert len(body["errors"]) == 1

    users = client.get("/api/users", headers=_admin(admin_token)).json()
    assert not any(u["email"] == "noname@example.edu" for u in users)


def test_user_import_invalid_role_rejected(client, admin_token):
    xlsx = _xlsx_bytes([["Name", "Email"], ["X", "x@example.edu"]])
    resp = client.post(
        "/api/users/import",
        data={"role": "admin"},  # bulk import is only for instructor/doctor
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 400


def test_user_import_creates_faculty_when_missing(client, db_session, admin_token):
    xlsx = _xlsx_bytes([["Name", "Email", "Faculty"], ["Import Doctor Two", "import.doc2@example.edu", "Brand New Faculty"]])
    resp = client.post(
        "/api/users/import",
        data={"role": "doctor"},
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_admin(admin_token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["created"]) == 1

    faculties = client.get("/api/faculties", headers=_admin(admin_token)).json()
    assert any(f["name"] == "Brand New Faculty" for f in faculties)
    users = client.get("/api/users", headers=_admin(admin_token)).json()
    row = next(u for u in users if u["email"] == "import.doc2@example.edu")
    assert row["faculty_name"] == "Brand New Faculty"


def test_scoped_admin_import_rejected_for_other_faculty(db_session, client, admin_token):
    """Mirrors the same-shaped scoped-admin gap that create_user closes —
    bulk import must apply the identical require_faculty_access check
    per row, not bypass it."""
    from app import security

    own_faculty = models.Faculty(name="Scoped Import Own Faculty")
    other_faculty = models.Faculty(name="Scoped Import Other Faculty")
    db_session.add_all([own_faculty, other_faculty])
    db_session.commit()
    db_session.refresh(own_faculty)
    db_session.refresh(other_faculty)

    scoped = models.User(name="Scoped Importer", email="scoped.importer@example.edu", role="admin",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(scoped)
    db_session.commit()
    db_session.refresh(scoped)
    db_session.add(models.AdminScope(user_id=scoped.user_id, faculty_id=own_faculty.faculty_id))
    db_session.commit()
    login = client.post("/api/auth/login", json={"email": scoped.email, "password": "pw123456"})
    scoped_token = login.json()["access_token"]

    xlsx = _xlsx_bytes([["Name", "Email", "Faculty"], ["Blocked Import", "blocked.import@example.edu", "Scoped Import Other Faculty"]])
    resp = client.post(
        "/api/users/import",
        data={"role": "doctor"},
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {scoped_token}"},
    )
    assert resp.status_code == 200  # the request itself succeeds; the offending row is reported, not silently allowed
    body = resp.json()
    assert body["created"] == []
    assert len(body["errors"]) == 1

    users = client.get("/api/users", headers=_admin(admin_token)).json()
    assert not any(u["email"] == "blocked.import@example.edu" for u in users)


def test_non_admin_cannot_import_users(client, instructor_token):
    xlsx = _xlsx_bytes([["Name", "Email"], ["X", "x2@example.edu"]])
    resp = client.post(
        "/api/users/import",
        data={"role": "doctor"},
        files={"file": ("users.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert resp.status_code == 403
