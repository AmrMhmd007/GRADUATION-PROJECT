from app import models


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


# ---------------------------------------------------------------------------
# Stage F / F3 — object-level authorization (IDOR fix): GET /api/doors/{id}
# and GET /api/doors/{id}/logs previously accepted ANY authenticated
# instructor/doctor for ANY door, even though the list endpoint
# (GET /api/doors) already restricts them to their own DoorAssignment rows.
# ---------------------------------------------------------------------------
def test_instructor_cannot_get_unassigned_door_detail(client, instructor_token):
    # Door #1 (seeded by fresh_db) has no DoorAssignment for the instructor.
    resp = client.get("/api/doors/1", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_instructor_can_get_assigned_door_detail(client, instructor_token, db_session):
    db_session.add(models.DoorAssignment(door_id=1, instructor_id=2))
    db_session.commit()
    resp = client.get("/api/doors/1", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 200
    assert resp.json()["door_id"] == 1


def test_instructor_cannot_get_unassigned_door_logs(client, instructor_token):
    resp = client.get("/api/doors/1/logs", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_instructor_can_get_assigned_door_logs(client, instructor_token, db_session):
    db_session.add(models.DoorAssignment(door_id=1, instructor_id=2))
    db_session.commit()
    resp = client.get("/api/doors/1/logs", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 200


def test_admin_unaffected_by_door_visibility_check(client, admin_token):
    # Admin behavior (doors have no scope mapping) must remain unchanged.
    resp = client.get("/api/doors/1", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    resp2 = client.get("/api/doors/1/logs", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp2.status_code == 200


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


# Stage B — GET /api/doors/{door_id}/assignments: the reverse direction of
# the existing GET /api/users/{id}/doors, needed so a room/door's profile
# can show "who has permanent access to THIS door" without fetching every
# staff member's assignments and filtering client-side.
def test_list_assignments_for_door_empty(client, admin_token):
    resp = client.get("/api/doors/1/assignments", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_assignments_for_door_returns_real_rows(client, admin_token):
    add = client.post("/api/users/2/doors", json={"door_id": 1},
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert add.status_code == 201

    resp = client.get("/api/doors/1/assignments", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["door_id"] == 1
    assert rows[0]["instructor_id"] == 2
    assert rows[0]["instructor_name"] == "Instructor"

    # Persistence check: a fresh GET after the write still reflects it.
    resp2 = client.get("/api/doors/1/assignments", headers={"Authorization": f"Bearer {admin_token}"})
    assert len(resp2.json()) == 1


def test_list_assignments_for_door_requires_admin(client, instructor_token):
    resp = client.get("/api/doors/1/assignments", headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_list_assignments_for_door_404_missing_door(client, admin_token):
    resp = client.get("/api/doors/999/assignments", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_list_assignments_for_door_isolated_from_other_doors(client, admin_token):
    """Gap found during the Stage B hardening pass: no existing test proved
    GET /api/doors/{id}/assignments only returns rows for THAT door — the
    Access & Authorization panel shows this per-door, so a leak here would
    silently attribute another room's assignee to the wrong room."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    other_door = client.post("/api/doors", json={
        "code": "A102", "name": "Room A102", "building": "Building A",
        "fail_mode": "secure", "category": "critical",
    }, headers=headers)
    assert other_door.status_code == 201
    other_door_id = other_door.json()["door_id"]

    assert client.post("/api/users/2/doors", json={"door_id": 1}, headers=headers).status_code == 201

    door1_rows = client.get("/api/doors/1/assignments", headers=headers).json()
    door2_rows = client.get(f"/api/doors/{other_door_id}/assignments", headers=headers).json()
    assert len(door1_rows) == 1
    assert door2_rows == []


def test_access_authorization_panel_data_is_consistent_and_persists(client, admin_token, db_session):
    """Integration gap: the new Access & Authorization panel reads THREE
    endpoints together for one door (permanent assignments, access windows,
    live authorization check) and expects them to agree and survive a
    refetch — no prior test exercised all three against the same door in
    one flow the way the panel actually does."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Permanent assignment for the Instructor (user_id=2) on door 1.
    assert client.post("/api/users/2/doors", json={"door_id": 1}, headers=headers).status_code == 201

    # A scheduled window for the same door_id but a DIFFERENT user has no
    # bearing on the instructor's own permanent access (additive, not
    # conflicting) — covered generally in test_access_windows.py, but not
    # together with a real DoorAssignment on the very same door.
    window_resp = client.post("/api/access-windows", json={
        "door_id": 1, "user_id": 2, "recurring": False,
        "start_at": "2020-01-01T00:00:00", "end_at": "2020-01-02T00:00:00",  # already expired
    }, headers=headers)
    assert window_resp.status_code == 201

    # Live check: permanent access alone must still authorize even though
    # the window above has already expired (additive-OR, not overridden).
    check = client.get("/api/doors/1/authorization?user_id=2", headers=headers)
    assert check.status_code == 200
    body = check.json()
    assert body["authorized"] is True
    assert body["has_permanent_access"] is True
    assert body["windows"][0]["active"] is False  # expired window correctly shown as inactive, not hidden

    # Persistence: assignments + windows are still there, unchanged, on a
    # completely fresh GET (not just the same response object).
    assignments_again = client.get("/api/doors/1/assignments", headers=headers).json()
    windows_again = client.get("/api/access-windows?door_id=1", headers=headers).json()
    assert len(assignments_again) == 1
    assert len(windows_again) == 1

    # The check itself is durably recorded as a real AccessEvent, not just
    # returned in the HTTP response and forgotten.
    events = db_session.query(models.AccessEvent).filter(models.AccessEvent.method == "schedule_check").all()
    assert len(events) == 1
    assert events[0].result == "granted"
