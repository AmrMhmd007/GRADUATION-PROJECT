from app import crypto


def test_list_credentials_requires_admin(client, instructor_token):
    resp = client.get("/api/credentials", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_list_credentials_admin(client, admin_token):
    resp = client.get("/api/credentials", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    # Never the plaintext UID over the API — only a masked tail.
    assert body[0]["card_uid_masked"] == "****BEEF"
    assert "card_uid" not in body[0]


def test_issue_credential(client, admin_token, db_session):
    resp = client.post("/api/credentials", json={"card_uid": "12345678"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert resp.json()["active"] is True
    assert resp.json()["card_uid_masked"] == "****5678"

    all_creds = client.get("/api/credentials", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert len(all_creds) == 2

    # Confirm it's actually encrypted at rest, not stored as plaintext.
    from app import models
    row = db_session.query(models.Credential).filter(
        models.Credential.card_uid_index == crypto.uid_index("12345678")
    ).first()
    assert row is not None
    assert row.card_uid != "12345678"
    assert crypto.decrypt_uid(row.card_uid) == "12345678"


def test_issue_duplicate_card_uid_rejected(client, admin_token):
    resp = client.post("/api/credentials", json={"card_uid": "DEADBEEF"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 409


def test_revoke_credential(client, admin_token):
    resp = client.delete("/api/credentials/1", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 204

    all_creds = client.get("/api/credentials", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert all_creds[0]["active"] is False  # revoked, not deleted


def test_revoke_missing_credential_404(client, admin_token):
    resp = client.delete("/api/credentials/999", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404
