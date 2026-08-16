def test_login_success(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.edu", "password": "x"})
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/doors")
    assert resp.status_code == 401


def test_refresh_token(client, admin_token):
    resp = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_lockout_after_repeated_failures(client):
    from app.config import settings

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        resp = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})
        assert resp.status_code == 401

    # One more attempt — even with the CORRECT password — should now be
    # throttled, since the account is locked out, not just the bad password.
    resp = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "admin123"})
    assert resp.status_code == 429
    assert "Too many failed attempts" in resp.json()["detail"]


def test_login_lockout_is_per_account(client):
    from app.config import settings

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})

    # A different account should be unaffected by admin's lockout.
    resp = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    assert resp.status_code == 200


def test_successful_login_resets_failure_count(client):
    from app.config import settings

    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})

    ok = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "admin123"})
    assert ok.status_code == 200

    # Failure count should have reset on success, so one more bad attempt
    # alone should not trigger a lockout.
    resp = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "wrong"})
    assert resp.status_code == 401
