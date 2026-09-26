"""
Phase 9.1 Priority 1 — the complete password-reset lifecycle
(auth.py::forgot_password/forgot_password_status/reset_password +
password_resets.py::approve/deny), which had zero automated coverage per
the Phase 9 audit. Every mutation here is verified write -> commit ->
fresh check (a new request/query, never trusting the mutating response
alone), and every failure path is checked to leave state untouched.
"""
from app import models, security


def _admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# 1. POST /api/auth/forgot-password
# ---------------------------------------------------------------------------
def test_forgot_password_known_email_creates_pending_request(client, db_session):
    resp = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"})
    assert resp.status_code == 202
    body = resp.json()
    assert "request_token" in body and body["request_token"]

    row = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == body["request_token"]
    ).first()
    assert row is not None
    assert row.status == "pending"
    assert row.password_set is False


def test_forgot_password_unknown_email_does_not_create_a_row_but_looks_identical(client, db_session):
    """Same generic response for a non-existent email (so the endpoint can't
    be used to probe which addresses are registered), but nothing is
    persisted for it."""
    before = db_session.query(models.PasswordResetRequest).count()
    resp = client.post("/api/auth/forgot-password", json={"email": "nobody-at-all@example.edu"})
    assert resp.status_code == 202
    body = resp.json()
    assert "request_token" in body and body["request_token"]
    after = db_session.query(models.PasswordResetRequest).count()
    assert after == before  # no row created for an unknown email


def test_forgot_password_reuses_existing_pending_request(client, db_session):
    """A second submission while one request is still pending reuses the
    same token/row rather than creating a duplicate."""
    first = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()
    second = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()
    assert first["request_token"] == second["request_token"]

    count = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == first["request_token"]
    ).count()
    assert count == 1


# ---------------------------------------------------------------------------
# 2. GET /api/auth/forgot-password/status
# ---------------------------------------------------------------------------
def test_status_pending_for_real_request(client):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    resp = client.get(f"/api/auth/forgot-password/status?token={token}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_status_pending_for_unknown_token(client):
    """An invalid/never-issued token reports 'pending' forever — same as a
    real, unactioned one — so this endpoint can't leak whether a token was
    ever real."""
    resp = client.get("/api/auth/forgot-password/status?token=not-a-real-token-at-all")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_status_reflects_approval(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))

    resp = client.get(f"/api/auth/forgot-password/status?token={token}")
    assert resp.json()["status"] == "approved"


def test_status_reflects_denial(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/deny", headers=_admin_headers(admin_token))

    resp = client.get(f"/api/auth/forgot-password/status?token={token}")
    assert resp.json()["status"] == "denied"


# ---------------------------------------------------------------------------
# 3/9/11/12. POST /api/auth/reset-password — success, persistence, reuse
# ---------------------------------------------------------------------------
def test_reset_password_success_persists_new_password_and_marks_used(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))

    resp = client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "brandnewpw1"})
    assert resp.status_code == 204

    # Persistence check: fresh login with the NEW password (not trusting the
    # 204 response itself) — a real DB re-query via the login flow.
    login = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "brandnewpw1"})
    assert login.status_code == 200
    old_login = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert old_login.status_code == 401

    # Fresh query — password_set flipped, request now reports "used".
    db_session.refresh(req)
    assert req.password_set is True
    status_resp = client.get(f"/api/auth/forgot-password/status?token={token}")
    assert status_resp.json()["status"] == "used"


def test_reset_password_cannot_be_reused_after_success(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))
    client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "firstpassword1"})

    # Same (now-spent) token tried again with a different password.
    second = client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "secondpassword2"})
    assert second.status_code == 400

    # The password from the first, successful reset must still be the one
    # that works — the second (rejected) attempt must not have mutated it.
    login = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "firstpassword1"})
    assert login.status_code == 200


def test_reset_password_rejected_when_still_pending(client, db_session):
    """No approval yet — reset-password must refuse, and must not touch the
    account's password."""
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    resp = client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "shouldnotwork1"})
    assert resp.status_code == 400

    login_old = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert login_old.status_code == 200
    login_new = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "shouldnotwork1"})
    assert login_new.status_code == 401


def test_reset_password_rejected_when_denied(client, db_session, admin_token):
    """Priority 1 item #7: a denied request must not be usable — this is
    the 'expired/invalid reset request' case."""
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/deny", headers=_admin_headers(admin_token))

    resp = client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "shouldnotwork1"})
    assert resp.status_code == 400

    login_old = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert login_old.status_code == 200


def test_reset_password_rejected_for_invalid_token(client):
    """Priority 1 item #6: a token that was never issued at all."""
    resp = client.post("/api/auth/reset-password", json={"request_token": "totally-made-up-token", "new_password": "whatever12"})
    assert resp.status_code == 400


def test_reset_password_rejects_short_password_without_mutating_state(client, db_session, admin_token):
    """Priority 1 item #12: a failure path (validation failure this time,
    not an invalid token) must not mutate password state or spend the
    token."""
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))

    resp = client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "abc"})
    assert resp.status_code == 400

    db_session.refresh(req)
    assert req.password_set is False  # token not spent by the failed attempt

    login_old = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert login_old.status_code == 200

    # The token is still approved and unspent, so a valid follow-up attempt
    # must still succeed — confirms the short-password rejection didn't
    # corrupt the request's state.
    retry = client.post("/api/auth/reset-password", json={"request_token": token, "new_password": "longenough1"})
    assert retry.status_code == 204


# ---------------------------------------------------------------------------
# 4/5. Admin approve / deny
# ---------------------------------------------------------------------------
def test_admin_can_approve_pending_request(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()

    resp = client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))
    assert resp.status_code == 204

    db_session.refresh(req)
    assert req.status == "approved"
    assert req.resolved_at is not None
    assert req.resolved_by is not None


def test_admin_can_deny_pending_request(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()

    resp = client.post(f"/api/password-resets/{req.request_id}/deny", headers=_admin_headers(admin_token))
    assert resp.status_code == 204

    db_session.refresh(req)
    assert req.status == "denied"
    assert req.resolved_at is not None


def test_approve_already_resolved_request_rejected(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))

    second = client.post(f"/api/password-resets/{req.request_id}/approve", headers=_admin_headers(admin_token))
    assert second.status_code == 400


def test_deny_already_resolved_request_rejected(client, db_session, admin_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    client.post(f"/api/password-resets/{req.request_id}/deny", headers=_admin_headers(admin_token))

    second = client.post(f"/api/password-resets/{req.request_id}/deny", headers=_admin_headers(admin_token))
    assert second.status_code == 400


def test_approve_nonexistent_request_404(client, admin_token):
    resp = client.post("/api/password-resets/999999/approve", headers=_admin_headers(admin_token))
    assert resp.status_code == 404


def test_deny_nonexistent_request_404(client, admin_token):
    resp = client.post("/api/password-resets/999999/deny", headers=_admin_headers(admin_token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Unauthorized / non-admin approve/deny
# ---------------------------------------------------------------------------
def test_non_admin_cannot_approve(client, db_session, instructor_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()

    resp = client.post(f"/api/password-resets/{req.request_id}/approve",
                        headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403

    db_session.refresh(req)
    assert req.status == "pending"  # unauthorized attempt must not mutate state


def test_non_admin_cannot_deny(client, db_session, instructor_token):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()

    resp = client.post(f"/api/password-resets/{req.request_id}/deny",
                        headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403

    db_session.refresh(req)
    assert req.status == "pending"


def test_unauthenticated_cannot_approve_or_deny(client, db_session):
    token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()

    approve = client.post(f"/api/password-resets/{req.request_id}/approve")
    deny = client.post(f"/api/password-resets/{req.request_id}/deny")
    assert approve.status_code == 401
    assert deny.status_code == 401


def test_list_password_resets_requires_admin(client, instructor_token):
    resp = client.get("/api/password-resets", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_list_password_resets_only_shows_pending(client, db_session, admin_token):
    approved_token = client.post("/api/auth/forgot-password", json={"email": "instructor@example.edu"}).json()["request_token"]
    approved_req = db_session.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == approved_token
    ).first()
    client.post(f"/api/password-resets/{approved_req.request_id}/approve", headers=_admin_headers(admin_token))

    resp = client.get("/api/password-resets", headers=_admin_headers(admin_token))
    assert resp.status_code == 200
    ids = [r["request_id"] for r in resp.json()]
    assert approved_req.request_id not in ids  # already resolved, drops off the pending list


# ---------------------------------------------------------------------------
# 10. must_change_password behavior (change_my_password is the only place
# that clears it — nothing in the current codebase ever sets it True via an
# API path, so it's exercised here the same way existing tests set up other
# DB-only state directly, per the established pattern in this test suite).
# ---------------------------------------------------------------------------
def test_change_my_password_clears_must_change_password_flag(client, db_session):
    user = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    user.must_change_password = True
    db_session.commit()

    login = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    token = login.json()["access_token"]

    resp = client.patch(
        "/api/users/me/password",
        json={"current_password": "instructor123", "new_password": "newpassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    db_session.refresh(user)
    assert user.must_change_password is False


def test_change_my_password_wrong_current_password_does_not_mutate(client, db_session):
    user = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    original_hash = user.password_hash

    login = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    token = login.json()["access_token"]

    resp = client.patch(
        "/api/users/me/password",
        json={"current_password": "totally-wrong", "new_password": "newpassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400

    db_session.refresh(user)
    assert user.password_hash == original_hash
