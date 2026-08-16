def test_list_doors(client, admin_token):
    resp = client.get("/api/doors", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    doors = resp.json()
    assert len(doors) == 1
    assert doors[0]["code"] == "A101"


def test_get_single_door(client, admin_token):
    resp = client.get("/api/doors/1", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["door_id"] == 1


def test_get_missing_door_404(client, admin_token):
    resp = client.get("/api/doors/999", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_override_requires_admin(client, instructor_token):
    resp = client.post("/api/doors/1/override", json={"action": "unlock"},
                        headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_override_unlock_logs_event(client, admin_token):
    resp = client.post("/api/doors/1/override", json={"action": "unlock"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "unlock"
    assert body["mqtt_delivered"] is False  # MQTT disabled in tests

    logs = client.get("/api/doors/1/logs", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert len(logs) == 1
    assert logs[0]["method"] == "override"
    assert logs[0]["result"] == "queued_no_broker"

    door = client.get("/api/doors/1", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert door["locked"] is False


def test_override_invalid_action(client, admin_token):
    resp = client.post("/api/doors/1/override", json={"action": "explode"},
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 400
