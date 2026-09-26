"""
Phase 9.1 Priority 4 — self-service account/profile mutations
(/api/users/me/*), which had no dedicated test file per the Phase 9 audit.
Every mutation is verified write -> commit -> fresh GET, and cross-user
isolation is checked directly (these endpoints take no user_id — they act
only on the authenticated caller — so the isolation test confirms that
structural guarantee actually holds in practice, not just in theory).
"""
import io

from app import models


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Update own name/email
# ---------------------------------------------------------------------------
def test_update_own_name_persists(client, db_session, instructor_token):
    resp = client.patch("/api/users/me/profile", json={"name": "New Name"}, headers=_headers(instructor_token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"

    # Fresh GET, not the PATCH response.
    me = client.get("/api/users/me", headers=_headers(instructor_token))
    assert me.json()["name"] == "New Name"

    row = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    assert row.name == "New Name"


def test_update_own_email_persists_and_requires_refresh(client, instructor_token):
    resp = client.patch("/api/users/me/profile", json={"email": "new.instructor@example.edu"}, headers=_headers(instructor_token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "new.instructor@example.edu"

    # The old token's subject (old email) no longer matches any user, so it
    # should now be rejected — this is the documented reason the frontend
    # must call /auth/refresh right after an email change.
    stale = client.get("/api/users/me", headers=_headers(instructor_token))
    assert stale.status_code == 401

    # Logging in with the NEW email (fresh credential check, not trusting
    # the PATCH response) confirms the change actually persisted.
    login = client.post("/api/auth/login", json={"email": "new.instructor@example.edu", "password": "instructor123"})
    assert login.status_code == 200
    old_login = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert old_login.status_code == 401


def test_update_own_email_conflict_rejected(client, instructor_token):
    """admin@example.edu already exists (conftest fixture) — instructor
    can't take that address."""
    resp = client.patch("/api/users/me/profile", json={"email": "admin@example.edu"}, headers=_headers(instructor_token))
    assert resp.status_code == 409

    me = client.get("/api/users/me", headers=_headers(instructor_token))
    assert me.json()["email"] == "instructor@example.edu"  # unchanged


def test_update_own_name_empty_rejected(client, instructor_token):
    resp = client.patch("/api/users/me/profile", json={"name": "   "}, headers=_headers(instructor_token))
    assert resp.status_code == 400

    me = client.get("/api/users/me", headers=_headers(instructor_token))
    assert me.json()["name"] == "Instructor"  # unchanged


def test_refresh_token_reflects_updated_identity(client, instructor_token):
    """Priority 4's 'refresh token behavior' check: after an email change +
    refresh, the NEW token must authenticate as the updated account, and the
    stale pre-change token must not."""
    client.patch("/api/users/me/profile", json={"email": "refreshed@example.edu"}, headers=_headers(instructor_token))

    login = client.post("/api/auth/login", json={"email": "refreshed@example.edu", "password": "instructor123"})
    new_token = login.json()["access_token"]

    me = client.get("/api/users/me", headers=_headers(new_token))
    assert me.status_code == 200
    assert me.json()["email"] == "refreshed@example.edu"

    refreshed = client.post("/api/auth/refresh", headers=_headers(new_token))
    assert refreshed.status_code == 200
    me2 = client.get("/api/users/me", headers=_headers(refreshed.json()["access_token"]))
    assert me2.json()["email"] == "refreshed@example.edu"


# ---------------------------------------------------------------------------
# Change own password
# ---------------------------------------------------------------------------
def test_change_own_password_persists(client, instructor_token):
    resp = client.patch("/api/users/me/password", json={
        "current_password": "instructor123", "new_password": "brandnewpassword1",
    }, headers=_headers(instructor_token))
    assert resp.status_code == 204

    # Fresh login (real credential re-check), not trusting the 204.
    old = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    new = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "brandnewpassword1"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_change_own_password_wrong_current_rejected(client, instructor_token):
    resp = client.patch("/api/users/me/password", json={
        "current_password": "not-the-real-password", "new_password": "brandnewpassword1",
    }, headers=_headers(instructor_token))
    assert resp.status_code == 400

    still_old = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert still_old.status_code == 200


def test_change_own_password_too_short_rejected(client, instructor_token):
    resp = client.patch("/api/users/me/password", json={
        "current_password": "instructor123", "new_password": "abc",
    }, headers=_headers(instructor_token))
    assert resp.status_code == 400

    still_old = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert still_old.status_code == 200


# ---------------------------------------------------------------------------
# Upload photo
# ---------------------------------------------------------------------------
def test_upload_photo_persists(client, db_session, instructor_token):
    fake_png = io.BytesIO(b"\x89PNG\r\n\x1a\nnotarealpngbutthatsfine")
    resp = client.post(
        "/api/users/me/photo",
        files={"file": ("avatar.png", fake_png, "image/png")},
        headers=_headers(instructor_token),
    )
    assert resp.status_code == 200
    assert resp.json()["photo_url"]
    assert resp.json()["photo_url"].startswith("/media/avatars/")

    me = client.get("/api/users/me", headers=_headers(instructor_token))
    assert me.json()["photo_url"] == resp.json()["photo_url"]

    row = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    assert row.photo_url == resp.json()["photo_url"]


def test_upload_photo_rejects_disallowed_extension(client, instructor_token):
    fake_exe = io.BytesIO(b"not an image")
    resp = client.post(
        "/api/users/me/photo",
        files={"file": ("malware.exe", fake_exe, "application/octet-stream")},
        headers=_headers(instructor_token),
    )
    assert resp.status_code == 400

    me = client.get("/api/users/me", headers=_headers(instructor_token))
    assert me.json()["photo_url"] is None


def test_upload_photo_rejects_oversized_file(client, instructor_token):
    too_big = io.BytesIO(b"0" * (5 * 1024 * 1024 + 1))
    resp = client.post(
        "/api/users/me/photo",
        files={"file": ("big.png", too_big, "image/png")},
        headers=_headers(instructor_token),
    )
    assert resp.status_code == 400

    me = client.get("/api/users/me", headers=_headers(instructor_token))
    assert me.json()["photo_url"] is None


def test_unauthenticated_cannot_use_any_self_endpoint(client):
    assert client.get("/api/users/me").status_code == 401
    assert client.patch("/api/users/me/profile", json={"name": "X"}).status_code == 401
    assert client.patch("/api/users/me/password", json={"current_password": "a", "new_password": "bbbbbb"}).status_code == 401
    assert client.post("/api/users/me/photo", files={"file": ("a.png", io.BytesIO(b"x"), "image/png")}).status_code == 401


# ---------------------------------------------------------------------------
# Cross-user isolation: a self-service endpoint acts ONLY on the caller.
# There is no user_id parameter on any /me/* route, so this test proves that
# guarantee holds in practice — one user's self-service calls never touch
# another user's row.
# ---------------------------------------------------------------------------
def test_self_endpoints_never_affect_another_users_account(client, db_session, admin_token, instructor_token):
    admin_before = db_session.query(models.User).filter(models.User.email == "admin@example.edu").first()
    admin_name_before = admin_before.name
    admin_hash_before = admin_before.password_hash
    admin_photo_before = admin_before.photo_url

    # Instructor updates their OWN profile/password/photo.
    client.patch("/api/users/me/profile", json={"name": "Instructor Renamed"}, headers=_headers(instructor_token))
    client.patch("/api/users/me/password", json={
        "current_password": "instructor123", "new_password": "instructorNewPw1",
    }, headers=_headers(instructor_token))
    client.post("/api/users/me/photo", files={"file": ("me.png", io.BytesIO(b"fakepngbytes"), "image/png")},
                headers=_headers(instructor_token))

    # Admin's row must be completely untouched by any of the instructor's
    # self-service calls.
    db_session.refresh(admin_before)
    assert admin_before.name == admin_name_before
    assert admin_before.password_hash == admin_hash_before
    assert admin_before.photo_url == admin_photo_before

    # And conversely, the admin's own /me still reflects the admin, not the
    # instructor's new values.
    me = client.get("/api/users/me", headers=_headers(admin_token))
    assert me.json()["name"] == admin_name_before
    assert me.json()["email"] == "admin@example.edu"
