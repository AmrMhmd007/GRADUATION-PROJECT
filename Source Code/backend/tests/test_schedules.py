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
