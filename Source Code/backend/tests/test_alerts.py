from app import models


def test_alerts_empty_initially(client, admin_token):
    resp = client.get("/api/alerts", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_resolve_alert(client, admin_token, db_session):
    alert = models.Alert(door_id=1, type="tamper")
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    alert_id = alert.alert_id

    resp = client.get("/api/alerts", headers={"Authorization": f"Bearer {admin_token}"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["resolved"] is False

    resolve = client.put(f"/api/alerts/{alert_id}/resolve", headers={"Authorization": f"Bearer {admin_token}"})
    assert resolve.status_code == 200
    assert resolve.json()["resolved"] is True

    unresolved = client.get("/api/alerts?resolved=false", headers={"Authorization": f"Bearer {admin_token}"})
    assert unresolved.json() == []


def test_resolve_alert_requires_admin(client, instructor_token):
    resp = client.put("/api/alerts/1/resolve", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403
