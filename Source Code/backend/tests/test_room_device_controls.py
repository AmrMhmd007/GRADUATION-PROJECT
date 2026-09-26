"""
Phase 11 Priority 4 — dedicated tests for the Smart Building room-device
control endpoints (AC / light / plugs) on doors.py, which previously had
no dedicated coverage (only incidental exercise via other suites).

Documented, intentional policy under test (security.require_room_control):
admin can always control a room's AC/light/plugs; a doctor can only if
assigned to that specific door via DoorAssignment; an instructor never can.
This test file does NOT change that policy — it only verifies it holds,
per the explicit Phase 11 instruction not to alter this design.
"""
from app import models, security


def _admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _make_room(client, admin_token, code="ROOM1", ac=True, light=True):
    resp = client.post(
        "/api/doors",
        json={
            "code": code, "name": f"Room {code}", "building": "Test Hall", "fail_mode": "secure",
            "category": "access_service", "ac_enabled": ac, "light_enabled": light,
            "plug_labels": ["Plug A"],
        },
        headers=_admin(admin_token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_doctor(db_session, email="room.doctor@example.edu"):
    doctor = models.User(name="Room Doctor", email=email, role="doctor",
                          password_hash=security.hash_password("pw123456"))
    db_session.add(doctor)
    db_session.commit()
    db_session.refresh(doctor)
    return doctor


def _login(client, email, password="pw123456"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _assign_door(db_session, door_id, instructor_id):
    db_session.add(models.DoorAssignment(door_id=door_id, instructor_id=instructor_id))
    db_session.commit()


# ---------------------------------------------------------------------------
# AC toggle
# ---------------------------------------------------------------------------
def test_admin_can_toggle_ac_and_it_persists(client, admin_token):
    room = _make_room(client, admin_token, code="ACROOM1")
    resp = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": True}, headers=_admin(admin_token))
    assert resp.status_code == 200
    assert resp.json()["ac_on"] is True

    fresh = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    assert fresh["ac_on"] is True

    resp2 = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": False}, headers=_admin(admin_token))
    assert resp2.status_code == 200
    fresh2 = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    assert fresh2["ac_on"] is False


def test_ac_toggle_rejected_when_not_enabled_on_this_room(client, admin_token):
    room = _make_room(client, admin_token, code="ACROOM2", ac=False)
    resp = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": True}, headers=_admin(admin_token))
    assert resp.status_code == 400
    assert "AC" in resp.json()["detail"]


def test_ac_toggle_404_for_nonexistent_door(client, admin_token):
    resp = client.post("/api/doors/999999/ac", json={"on": True}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_assigned_doctor_can_toggle_ac(client, db_session, admin_token):
    room = _make_room(client, admin_token, code="ACROOM3")
    doctor = _make_doctor(db_session, email="ac.assigned.doctor@example.edu")
    _assign_door(db_session, room["door_id"], doctor.user_id)
    doctor_token = _login(client, doctor.email)

    resp = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": True},
                        headers={"Authorization": f"Bearer {doctor_token}"})
    assert resp.status_code == 200
    assert resp.json()["ac_on"] is True


def test_unassigned_doctor_cannot_toggle_ac(client, db_session, admin_token):
    room = _make_room(client, admin_token, code="ACROOM4")
    doctor = _make_doctor(db_session, email="ac.unassigned.doctor@example.edu")
    doctor_token = _login(client, doctor.email)

    resp = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": True},
                        headers={"Authorization": f"Bearer {doctor_token}"})
    assert resp.status_code == 403

    fresh = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    assert fresh["ac_on"] is False  # untouched


def test_instructor_cannot_toggle_ac_even_if_assigned(client, db_session, admin_token, instructor_token):
    """Instructors were explicitly excluded from room-device control by
    design (only doctors and admin) — confirm this still holds even when
    a DoorAssignment row exists for the instructor."""
    room = _make_room(client, admin_token, code="ACROOM5")
    instructor = db_session.query(models.User).filter(models.User.email == "instructor@example.edu").first()
    _assign_door(db_session, room["door_id"], instructor.user_id)

    resp = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": True},
                        headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_unauthenticated_cannot_toggle_ac(client, admin_token):
    room = _make_room(client, admin_token, code="ACROOM6")
    resp = client.post(f"/api/doors/{room['door_id']}/ac", json={"on": True})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Light toggle
# ---------------------------------------------------------------------------
def test_admin_can_toggle_light_and_it_persists(client, admin_token):
    room = _make_room(client, admin_token, code="LIGHTROOM1")
    resp = client.post(f"/api/doors/{room['door_id']}/light", json={"on": True}, headers=_admin(admin_token))
    assert resp.status_code == 200
    fresh = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    assert fresh["light_on"] is True


def test_light_toggle_rejected_when_not_enabled_on_this_room(client, admin_token):
    room = _make_room(client, admin_token, code="LIGHTROOM2", light=False)
    resp = client.post(f"/api/doors/{room['door_id']}/light", json={"on": True}, headers=_admin(admin_token))
    assert resp.status_code == 400


def test_unassigned_doctor_cannot_toggle_light(client, db_session, admin_token):
    room = _make_room(client, admin_token, code="LIGHTROOM3")
    doctor = _make_doctor(db_session, email="light.unassigned.doctor@example.edu")
    doctor_token = _login(client, doctor.email)

    resp = client.post(f"/api/doors/{room['door_id']}/light", json={"on": True},
                        headers={"Authorization": f"Bearer {doctor_token}"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Plugs: add / toggle / delete
# ---------------------------------------------------------------------------
def test_admin_can_add_and_toggle_plug_and_it_persists(client, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM1")
    plug = client.post(f"/api/doors/{room['door_id']}/plugs", json={"label": "Fridge Plug"},
                        headers=_admin(admin_token)).json()

    resp = client.post(f"/api/doors/{room['door_id']}/plugs/{plug['plug_id']}", json={"on": True},
                        headers=_admin(admin_token))
    assert resp.status_code == 200
    assert resp.json()["on"] is True

    fresh_doors = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    fresh_plug = next(p for p in fresh_doors["plugs"] if p["plug_id"] == plug["plug_id"])
    assert fresh_plug["on"] is True


def test_add_plug_rejected_for_non_room_door(client, admin_token):
    resp = client.post("/api/doors", json={"code": "CRIT1", "name": "Critical Door", "building": "Test Hall",
                                            "fail_mode": "secure", "category": "critical"},
                        headers=_admin(admin_token))
    door = resp.json()
    plug_resp = client.post(f"/api/doors/{door['door_id']}/plugs", json={"label": "X"}, headers=_admin(admin_token))
    assert plug_resp.status_code == 400


def test_toggle_nonexistent_plug_404(client, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM2")
    resp = client.post(f"/api/doors/{room['door_id']}/plugs/999999", json={"on": True}, headers=_admin(admin_token))
    assert resp.status_code == 404


def test_toggle_plug_belonging_to_different_door_404(client, admin_token):
    room1 = _make_room(client, admin_token, code="PLUGROOM3")
    room2 = _make_room(client, admin_token, code="PLUGROOM4")
    plug = client.post(f"/api/doors/{room1['door_id']}/plugs", json={"label": "Room1 Plug"},
                        headers=_admin(admin_token)).json()

    resp = client.post(f"/api/doors/{room2['door_id']}/plugs/{plug['plug_id']}", json={"on": True},
                        headers=_admin(admin_token))
    assert resp.status_code == 404


def test_unassigned_doctor_cannot_toggle_plug(client, db_session, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM5")
    plug = client.post(f"/api/doors/{room['door_id']}/plugs", json={"label": "X"}, headers=_admin(admin_token)).json()
    doctor = _make_doctor(db_session, email="plug.unassigned.doctor@example.edu")
    doctor_token = _login(client, doctor.email)

    resp = client.post(f"/api/doors/{room['door_id']}/plugs/{plug['plug_id']}", json={"on": True},
                        headers={"Authorization": f"Bearer {doctor_token}"})
    assert resp.status_code == 403


def test_non_admin_cannot_add_plug(client, instructor_token, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM6")
    resp = client.post(f"/api/doors/{room['door_id']}/plugs", json={"label": "X"},
                        headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403


def test_admin_can_delete_plug_and_it_persists(client, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM7")
    plug = client.post(f"/api/doors/{room['door_id']}/plugs", json={"label": "Deletable"},
                        headers=_admin(admin_token)).json()

    resp = client.delete(f"/api/doors/{room['door_id']}/plugs/{plug['plug_id']}", headers=_admin(admin_token))
    assert resp.status_code == 204

    fresh_doors = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    assert not any(p["plug_id"] == plug["plug_id"] for p in fresh_doors["plugs"])


def test_non_admin_cannot_delete_plug(client, instructor_token, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM8")
    plug = client.post(f"/api/doors/{room['door_id']}/plugs", json={"label": "X"}, headers=_admin(admin_token)).json()

    resp = client.delete(f"/api/doors/{room['door_id']}/plugs/{plug['plug_id']}",
                          headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 403

    fresh_doors = client.get(f"/api/doors/{room['door_id']}", headers=_admin(admin_token)).json()
    assert any(p["plug_id"] == plug["plug_id"] for p in fresh_doors["plugs"])  # untouched


def test_delete_nonexistent_plug_404(client, admin_token):
    room = _make_room(client, admin_token, code="PLUGROOM9")
    resp = client.delete(f"/api/doors/{room['door_id']}/plugs/999999", headers=_admin(admin_token))
    assert resp.status_code == 404
