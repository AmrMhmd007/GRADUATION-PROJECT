"""Face door access, face enrollment, occupancy counts, device fault monitoring,
room health/timeline/map, and RBAC for the cyber-physical upgrade."""
import datetime
import json

import pytest

from app import models, security
from app.config import settings
from app.services import (device_monitor_service, face_service, occupancy_service, room_intel_service)

NODE = {"X-Node-Key": "node-secret"}
NOW = datetime.datetime.utcnow()


@pytest.fixture(autouse=True)
def _node_key(monkeypatch):
    monkeypatch.setattr(settings, "FACE_NODE_API_KEY", "node-secret")


def vec(seed, n=16):
    import math
    return [math.sin(seed * (i + 1)) for i in range(n)]


def mk_user(db, name, role="doctor", status="active"):
    u = models.User(name=name, email=f"{name.lower()}@example.edu", role=role, status=status,
                    password_hash=security.hash_password("pw123456"))
    db.add(u); db.commit(); db.refresh(u)
    return u


def token(client, name):
    r = client.post("/api/auth/login", json={"email": f"{name.lower()}@example.edu", "password": "pw123456"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def mk_room(db, code="R1", capacity=50):
    d = models.Door(code=code, name=f"Room {code}", building="B", fail_mode="secure", online=True, locked=True)
    db.add(d); db.flush()
    z = models.Zone(name=f"Room {code}", zone_type="CLASSROOM", door_id=d.door_id, floor="1", capacity=capacity)
    db.add(z); db.commit(); db.refresh(d); db.refresh(z)
    return d, z


def enroll(db, user, seed, **kw):
    return face_service.enroll(db, user, embedding=vec(seed), quality=kw.get("quality", 0.9),
                               liveness_passed=kw.get("liveness", True), model_version="t", source="SIMULATED",
                               actor=user), db.commit()


def assign(db, door, user):
    db.add(models.DoorAssignment(door_id=door.door_id, instructor_id=user.user_id)); db.commit()


def verify(client, door, seed, **kw):
    body = {"door_code": door.code, "embedding": vec(seed), "quality": 0.9, "liveness_passed": True, **kw}
    return client.post("/api/face/node/verify", json=body, headers=NODE).json()


# ------------------------------------------------------------------ face access
def test_grant_requires_face_and_authorization(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Alice"); enroll(db_session, u, 1); assign(db_session, door, u)
    r = verify(client, door, 1)
    assert r["decision"] == "GRANT" and r["event_id"]
    e = db_session.get(models.AccessEvent, r["event_id"])
    ev = json.loads(e.evidence_snapshot)
    assert e.method == "face" and e.result == "granted" and ev["face"]["identity_resolved"] is True
    assert "template" not in json.dumps(ev)
    # granting does NOT claim physical unlock until the node confirms
    db_session.expire_all()
    assert db_session.get(models.Door, door.door_id).locked is True
    ack = client.post("/api/face/node/ack", json={"door_code": door.code, "event_id": e.event_id, "unlocked": True}, headers=NODE)
    assert ack.status_code == 200
    db_session.expire_all()
    assert db_session.get(models.Door, door.door_id).locked is False


def test_deny_wrong_room_no_schedule(client, db_session):
    d1, _ = mk_room(db_session, "R1"); d2, _ = mk_room(db_session, "R2")
    u = mk_user(db_session, "Bob"); enroll(db_session, u, 2); assign(db_session, d1, u)
    r = verify(client, d2, 2)
    assert r["decision"] == "DENY" and "not authorized" in r["reason"]


def test_deny_outside_window_even_with_enrolled_face(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Carl"); enroll(db_session, u, 3)
    past = NOW - datetime.timedelta(days=2)
    db_session.add(models.AccessWindow(door_id=door.door_id, user_id=u.user_id, recurring=False,
                                       start_at=past, end_at=past + datetime.timedelta(hours=2))); db_session.commit()
    assert verify(client, door, 3)["decision"] == "DENY"


def test_grant_within_active_window(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Dina"); enroll(db_session, u, 4)
    db_session.add(models.AccessWindow(door_id=door.door_id, user_id=u.user_id, recurring=False,
                                       start_at=NOW - datetime.timedelta(hours=1), end_at=NOW + datetime.timedelta(hours=1)))
    db_session.commit()
    assert verify(client, door, 4)["decision"] == "GRANT"


def test_unknown_face_denied(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Eve"); enroll(db_session, u, 5); assign(db_session, door, u)
    r = verify(client, door, 97)
    assert r["decision"] == "DENY" and r["user_id"] is None


def test_revoked_and_inactive_denied(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Fay"); enroll(db_session, u, 6); assign(db_session, door, u)
    face_service.revoke(db_session, u, actor=u, reason="x"); db_session.commit()
    assert verify(client, door, 6)["decision"] == "DENY"
    u2 = mk_user(db_session, "Gus"); enroll(db_session, u2, 7); assign(db_session, door, u2)
    u2.status = "inactive"; db_session.commit()
    assert verify(client, door, 7)["decision"] == "DENY"


def test_liveness_and_quality_failures_deny(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Hal"); enroll(db_session, u, 8); assign(db_session, door, u)
    assert verify(client, door, 8, liveness_passed=False)["decision"] == "DENY"
    assert verify(client, door, 8, liveness_passed=None)["decision"] == "DENY"
    assert verify(client, door, 8, quality=0.1)["decision"] == "DENY"


def test_node_failure_is_unavailable_never_grant(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Ian"); enroll(db_session, u, 9); assign(db_session, door, u)
    before = db_session.query(models.AccessEvent).count()
    r = verify(client, door, 9, node_status="camera_error")
    assert r["decision"] == "UNAVAILABLE" and r["event_id"] is None
    assert db_session.query(models.AccessEvent).count() == before
    r = client.post("/api/face/node/verify", json={"door_code": door.code}, headers=NODE).json()
    assert r["decision"] == "UNAVAILABLE"
    hh = db_session.query(models.HardwareHealth).first()
    assert hh is not None


def test_node_endpoints_reject_missing_or_wrong_key(client, db_session, monkeypatch):
    door, _ = mk_room(db_session)
    body = {"door_code": door.code, "embedding": vec(1), "quality": 0.9, "liveness_passed": True}
    assert client.post("/api/face/node/verify", json=body).status_code == 403
    assert client.post("/api/face/node/verify", json=body, headers={"X-Node-Key": "bad"}).status_code == 403
    monkeypatch.setattr(settings, "FACE_NODE_API_KEY", "")
    assert client.post("/api/face/node/verify", json=body, headers={"X-Node-Key": ""}).status_code == 403


def test_decision_audited_and_denials_audited(client, db_session):
    door, _ = mk_room(db_session); u = mk_user(db_session, "Jo"); enroll(db_session, u, 10); assign(db_session, door, u)
    verify(client, door, 10); verify(client, door, 55)
    actions = [a.action for a in db_session.query(models.AuditLog).all()]
    assert "face_access_granted" in actions and "face_access_denied" in actions and "face_enroll" in actions


# ------------------------------------------------------------------ enrollment
def test_enrollment_flow_never_returns_template(client, db_session):
    u = mk_user(db_session, "Kim"); h = token(client, "Kim")
    assert client.get("/api/face/me", headers=h).json()["status"] == "NOT_ENROLLED"
    r = client.post("/api/face/me/enroll", json={"embedding": vec(11), "quality": 0.9, "liveness_passed": True,
                                                 "source": "SIMULATED"}, headers=h)
    assert r.status_code == 201 and r.json()["status"] == "ENROLLED"
    assert "template" not in r.text and "embedding" not in r.text
    r2 = client.post("/api/face/me/enroll", json={"embedding": vec(12), "quality": 0.9, "liveness_passed": True}, headers=h)
    assert r2.status_code == 201
    rows = db_session.query(models.FaceCredential).filter_by(user_id=u.user_id).all()
    assert sorted(r.status for r in rows) == ["ENROLLED", "REVOKED"]
    assert all(vec(11)[0].__str__() not in r.template_enc for r in rows)  # encrypted at rest
    assert client.post("/api/face/me/revoke", json={}, headers=h).json()["status"] == "REVOKED"


def test_enrollment_quality_and_liveness_gates(client, db_session):
    mk_user(db_session, "Lee"); h = token(client, "Lee")
    assert client.post("/api/face/me/enroll", json={"embedding": vec(1), "quality": 0.1, "liveness_passed": True}, headers=h).status_code == 422
    assert client.post("/api/face/me/enroll", json={"embedding": vec(1), "quality": 0.9, "liveness_passed": False}, headers=h).status_code == 422
    assert client.post("/api/face/me/enroll", json={"embedding": [0.0] * 16, "quality": 0.9, "liveness_passed": True}, headers=h).status_code == 422


def test_admin_revoke_and_rbac(client, db_session, admin_token):
    u = mk_user(db_session, "Max"); enroll(db_session, u, 13)
    h_admin = {"Authorization": f"Bearer {admin_token}"}
    lst = client.get("/api/face/users", headers=h_admin).json()
    assert any(x["email"] == "max@example.edu" and x["status"] == "ENROLLED" for x in lst)
    assert "template" not in json.dumps(lst)
    h_doc = token(client, "Max")
    assert client.get("/api/face/users", headers=h_doc).status_code == 403
    assert client.post(f"/api/face/users/{u.user_id}/revoke", json={}, headers=h_doc).status_code == 403
    assert client.post(f"/api/face/users/{u.user_id}/revoke", json={"reason": "left"}, headers=h_admin).json()["status"] == "REVOKED"
    assert db_session.query(models.AuditLog).filter_by(action="face_revoke").count() == 1


# ------------------------------------------------------------------ occupancy
def test_occupancy_history_zero_vs_offline(client, db_session):
    _, z = mk_room(db_session)
    occupancy_service.ingest(db_session, z, node_id="occ1", count=0, confidence=0.9)
    c = occupancy_service.current(db_session, z)
    assert c["state"] == "OK" and c["count"] == 0
    occupancy_service.ingest(db_session, z, node_id="occ1", count=None, sensor_status="error")
    c = occupancy_service.current(db_session, z)
    assert c["state"] == "UNAVAILABLE" and c["count"] is None
    occupancy_service.ingest(db_session, z, node_id="occ1", count=37, confidence=0.8)
    assert occupancy_service.current(db_session, z)["count"] == 37
    assert db_session.query(models.OccupancyReading).count() == 3  # append-only
    assert occupancy_service.sensor_health(db_session, z) == "ONLINE"


def test_occupancy_stale_is_unavailable_and_capacity(client, db_session):
    _, z = mk_room(db_session, capacity=50)
    old = NOW - datetime.timedelta(seconds=settings.OCCUPANCY_STALE_AFTER_SECONDS + 60)
    occupancy_service.ingest(db_session, z, node_id="o", count=5, recorded_at=old)
    c = occupancy_service.current(db_session, z)
    assert c["state"] == "UNAVAILABLE" and c["capacity"] == 50
    assert occupancy_service.sensor_health(db_session, z) == "OFFLINE"


def test_occupancy_feeds_existing_presence_signal_not_identity(client, db_session):
    _, z = mk_room(db_session)
    occupancy_service.ingest(db_session, z, node_id="o", count=4)
    ev = db_session.query(models.OccupancyEvent).filter_by(zone_id=z.zone_id).all()
    assert len(ev) == 1 and ev[0].occupancy_state is True
    cols = {c.name for c in models.OccupancyReading.__table__.columns}
    assert not ({"user_id", "face", "student_id", "embedding"} & cols)
    occupancy_service.ingest(db_session, z, node_id="o", count=None, sensor_status="error")
    assert db_session.query(models.OccupancyEvent).count() == 1  # error writes no presence signal


def test_occupancy_ingest_endpoint_validation_and_auth(client, db_session):
    _, z = mk_room(db_session)
    assert client.post("/api/occupancy/ingest", json={"zone_id": z.zone_id, "count": 3}).status_code == 403
    assert client.post("/api/occupancy/ingest", json={"zone_id": z.zone_id, "count": -2}, headers=NODE).status_code == 422
    assert client.post("/api/occupancy/ingest", json={"zone_id": z.zone_id, "count": 3, "node_id": "n"}, headers=NODE).status_code == 201


def _class_now(db, user, door):
    now = datetime.datetime.now()
    c = models.Course(department_id=_dept(db), code="CS1", name="Intro")
    db.add(c); db.flush()
    s = models.Schedule(door_id=door.door_id, day_of_week=now.weekday(),
                        start_time=(now - datetime.timedelta(minutes=1)).time().replace(microsecond=0),
                        end_time=datetime.time(23, 59, 59), course_ref_id=c.course_id)
    if now.time() > datetime.time(23, 58):
        pytest.skip("too close to midnight")
    if now.time() < datetime.time(0, 2):
        s.start_time = datetime.time(0, 0)
    db.add(s); db.flush()
    db.add(models.CourseAssignment(course_id=c.course_id, user_id=user.user_id, status="active", schedule_id=s.schedule_id))
    db.commit()


def _dept(db):
    f = models.Faculty(name="Eng"); db.add(f); db.flush()
    d = models.Department(faculty_id=f.faculty_id, name="CS"); db.add(d); db.flush()
    return d.department_id


def test_doctor_sees_only_own_class_room_occupancy(client, db_session):
    d1, z1 = mk_room(db_session, "R1"); d2, z2 = mk_room(db_session, "R2")
    u = mk_user(db_session, "Nia"); _class_now(db_session, u, d1)
    occupancy_service.ingest(db_session, z1, node_id="o", count=37)
    occupancy_service.ingest(db_session, z2, node_id="o2", count=9)
    h = token(client, "Nia")
    mine = client.get("/api/occupancy/my-classes", headers=h).json()
    assert len(mine) == 1 and mine[0]["in_progress"] and mine[0]["occupancy"]["count"] == 37
    assert mine[0]["occupancy"]["capacity"] == 50
    assert client.get(f"/api/occupancy/zones/{z1.zone_id}", headers=h).status_code == 200
    assert client.get(f"/api/occupancy/zones/{z2.zone_id}", headers=h).status_code == 403
    assert client.get("/api/occupancy/overview", headers=h).status_code == 403


def test_admin_overview_campus_building_room(client, db_session, admin_token):
    _, z1 = mk_room(db_session, "R1"); _, z2 = mk_room(db_session, "R2"); mk_room(db_session, "R3")
    occupancy_service.ingest(db_session, z1, node_id="a", count=10)
    occupancy_service.ingest(db_session, z2, node_id="b", count=0)
    h = {"Authorization": f"Bearer {admin_token}"}
    o = client.get("/api/occupancy/overview", headers=h).json()
    assert o["campus"]["total_people"] == 10 and o["campus"]["occupied_rooms"] == 1
    assert o["campus"]["rooms_with_live_count"] == 2 and o["campus"]["rooms_total"] == 3
    assert o["sensor_health"]["UNKNOWN"] == 1 and o["sensor_health"]["ONLINE"] == 2


# ------------------------------------------------------------------ device faults
def mk_device(db, z, status=True, cmd="STATE_CONFIRMED", rated=1000.0):
    d = models.Device(zone_id=z.zone_id, name="Projector", type="OTHER", status=status, rated_power=rated,
                      last_command_status=cmd, last_command_at=NOW - datetime.timedelta(minutes=30))
    db.add(d); db.commit(); db.refresh(d)
    return d


def test_normal_operation_no_fault(db_session):
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    device_monitor_service.record_telemetry(db_session, d, power_watts=800)
    assert db_session.query(models.DeviceFaultAlert).count() == 0


def test_no_telemetry_no_invented_fault(db_session):
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    assert device_monitor_service.evaluate_device(db_session, d) == []


def test_expected_on_observed_off_is_high_and_persisted(db_session):
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    device_monitor_service.record_telemetry(db_session, d, power_watts=0.5)
    f = db_session.query(models.DeviceFaultAlert).one()
    assert f.severity == "HIGH" and f.kind == "STATE_MISMATCH" and f.expected_value == "ON" and f.observed_value == "OFF"
    device_monitor_service.record_telemetry(db_session, d, power_watts=0.4)  # dedup
    assert db_session.query(models.DeviceFaultAlert).count() == 1
    device_monitor_service.record_telemetry(db_session, d, power_watts=900)  # condition clears
    db_session.expire_all()
    assert db_session.query(models.DeviceFaultAlert).one().status == "RESOLVED"


def test_delayed_response_is_warning(db_session):
    _, z = mk_room(db_session)
    d = models.Device(zone_id=z.zone_id, name="AC", type="AC", status=True, rated_power=1500,
                      last_command_status="COMMAND_SENT", last_command_at=NOW - datetime.timedelta(minutes=2))
    db_session.add(d); db_session.commit()
    db_session.add(models.DeviceTelemetry(device_id=d.device_id, zone_id=z.zone_id, power_watts=0,
                                          recorded_at=NOW - datetime.timedelta(minutes=20)))
    db_session.commit()
    # telemetry predates command but is stale-ish within window? make it fresh enough:
    t = db_session.query(models.DeviceTelemetry).one(); t.recorded_at = NOW - datetime.timedelta(minutes=4); db_session.commit()
    f = device_monitor_service.findings(db_session, d, NOW)
    assert f and f[0]["kind"] == "NO_RESPONSE" and f[0]["severity"] == "WARNING"


def test_stale_telemetry_warning_and_critical_only_on_hazard(db_session):
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    old = NOW - datetime.timedelta(seconds=settings.DEVICE_TELEMETRY_STALE_AFTER_SECONDS + 100)
    db_session.add(models.DeviceTelemetry(device_id=d.device_id, zone_id=z.zone_id, power_watts=800, recorded_at=old)); db_session.commit()
    f = device_monitor_service.findings(db_session, d, NOW)
    assert [x["kind"] for x in f] == ["TELEMETRY_STALE"] and f[0]["severity"] == "WARNING"
    device_monitor_service.record_telemetry(db_session, d, power_watts=0.1)
    assert db_session.query(models.DeviceFaultAlert).filter_by(severity="CRITICAL").count() == 0
    device_monitor_service.record_telemetry(db_session, d, power_watts=900, temperature_c=95, hazard=True)
    assert db_session.query(models.DeviceFaultAlert).filter_by(severity="CRITICAL", kind="HAZARD").count() == 1


def test_fault_workflow_ack_assign_resolve_and_rbac(client, db_session, admin_token):
    d1, z = mk_room(db_session); dev = mk_device(db_session, z)
    device_monitor_service.record_telemetry(db_session, dev, power_watts=0)
    fid = db_session.query(models.DeviceFaultAlert).one().fault_id
    doc = mk_user(db_session, "Oz"); other = mk_user(db_session, "Pat"); assign(db_session, d1, doc)
    ha = {"Authorization": f"Bearer {admin_token}"}
    hd = token(client, "Oz"); ho = token(client, "Pat")
    admin_list = client.get("/api/device-faults", headers=ha).json()
    assert admin_list[0]["expected_value"] == "ON" and "evidence" in admin_list[0]
    doc_list = client.get("/api/device-faults", headers=hd).json()
    assert len(doc_list) == 1 and "evidence" not in doc_list[0] and doc_list[0]["room"]
    assert client.get("/api/device-faults", headers=ho).json() == []
    assert client.post(f"/api/device-faults/{fid}/acknowledge", headers=hd).status_code == 403
    assert client.post(f"/api/device-faults/{fid}/report", headers=hd).json()["reported_issue"] is True
    assert client.post(f"/api/device-faults/{fid}/retry-check", headers=ho).status_code == 403
    assert client.post(f"/api/device-faults/{fid}/retry-check", headers=hd).status_code == 200
    assert client.post(f"/api/device-faults/{fid}/acknowledge", headers=ha).json()["status"] == "ACKNOWLEDGED"
    assert client.post(f"/api/device-faults/{fid}/assign", json={"user_id": doc.user_id}, headers=ha).status_code == 200
    r = client.post(f"/api/device-faults/{fid}/resolve", json={"note": "replaced bulb"}, headers=ha).json()
    assert r["status"] == "RESOLVED"
    acts = {a.action for a in db_session.query(models.AuditLog).filter_by(resource_type="device_fault")}
    assert {"acknowledge", "assign", "resolve", "report"} <= acts


def test_telemetry_endpoint_requires_node_key(client, db_session):
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    body = {"device_id": d.device_id, "power_watts": 0.0}
    assert client.post("/api/device-faults/telemetry", json=body).status_code == 403
    assert client.post("/api/device-faults/telemetry", json=body, headers=NODE).status_code == 201
    assert db_session.query(models.DeviceFaultAlert).count() == 1


def test_maintenance_recommendation_rule_based(db_session):
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    for i in range(3):
        db_session.add(models.DeviceFaultAlert(device_id=d.device_id, zone_id=z.zone_id, kind="STATE_MISMATCH",
                                               severity="HIGH", reason="r", status="RESOLVED",
                                               detected_at=NOW - datetime.timedelta(days=i + 1)))
    db_session.commit()
    assert device_monitor_service.maintenance_recommendation(db_session, d) is None  # telemetry normal/absent
    device_monitor_service.record_telemetry(db_session, d, power_watts=0)
    rec = device_monitor_service.maintenance_recommendation(db_session, d)
    assert rec and rec["recommendation"] == "MAINTENANCE_RECOMMENDED" and "not a prediction" in rec["basis"]


# ------------------------------------------------------------------ health / timeline / map
def test_room_health_deterministic(client, db_session):
    d, z = mk_room(db_session)
    assert room_intel_service.room_health(db_session, z)["state"] == "HEALTHY"
    dev = mk_device(db_session, z)
    device_monitor_service.record_telemetry(db_session, dev, power_watts=0)
    assert room_intel_service.room_health(db_session, z)["state"] == "DEGRADED"
    device_monitor_service.record_telemetry(db_session, dev, power_watts=900, hazard=True)
    assert room_intel_service.room_health(db_session, z)["state"] == "CRITICAL"
    d.online = False; db_session.commit()
    s = models.Sensor(zone_id=z.zone_id, sensor_type="PIR", status="offline"); db_session.add(s); db_session.commit()
    db_session.query(models.DeviceFaultAlert).update({"status": "RESOLVED"}); db_session.commit()
    assert room_intel_service.room_health(db_session, z)["state"] == "OFFLINE"


def test_room_health_unknown_without_sources(db_session):
    z = models.Zone(name="Bare", zone_type="ROOM"); db_session.add(z); db_session.commit()
    assert room_intel_service.room_health(db_session, z)["state"] == "UNKNOWN"


def test_timeline_unifies_real_events_with_provenance(client, db_session, admin_token):
    d, z = mk_room(db_session); u = mk_user(db_session, "Quin"); enroll(db_session, u, 21); assign(db_session, d, u)
    verify(client, d, 21)
    occupancy_service.ingest(db_session, z, node_id="o", count=5)
    dev = mk_device(db_session, z); device_monitor_service.record_telemetry(db_session, dev, power_watts=0)
    ha = {"Authorization": f"Bearer {admin_token}"}
    tl = client.get(f"/api/rooms-intel/zones/{z.zone_id}/timeline", headers=ha).json()
    types = {t["type"] for t in tl}
    assert {"ACCESS", "OCCUPANCY", "DEVICE_FAULT"} <= types
    assert all("table" in t["provenance"] and t["timestamp"] for t in tl)
    ts = [t["timestamp"] for t in tl]; assert ts == sorted(ts, reverse=True)
    assert client.get(f"/api/rooms-intel/zones/{z.zone_id}/timeline", headers=token(client, "Quin")).status_code == 403


def test_campus_map_from_real_entities(client, db_session, admin_token):
    d, z = mk_room(db_session)
    m = client.get("/api/rooms-intel/campus-map", headers={"Authorization": f"Bearer {admin_token}"}).json()
    rooms = [r for b in m["buildings"] for f in b["floors"] for r in f["rooms"]]
    assert [r["zone_id"] for r in rooms] == [z.zone_id] and rooms[0]["health"] == "HEALTHY"
    assert rooms[0]["occupancy"] is None and rooms[0]["occupancy_state"] == "UNAVAILABLE"
    p = client.get(f"/api/rooms-intel/zones/{z.zone_id}/profile", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert p["door"]["code"] == "R1" and p["health"]["state"] == "HEALTHY"


def test_zone_capacity_roundtrip(client, db_session, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = client.post("/api/zones", json={"name": "Lab", "zone_type": "LAB", "capacity": 30}, headers=h)
    assert r.status_code == 201 and r.json()["capacity"] == 30
    assert client.put(f"/api/zones/{r.json()['zone_id']}", json={"capacity": 0}, headers=h).status_code == 400


# ------------------------------------------------------------------ MQTT + automation integration
class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


def test_mqtt_occupancy_count_topic_real_and_error(db_session):
    from app.services import mqtt_service
    _, z = mk_room(db_session)
    t = f"university/aiu/building/1/zone/{z.zone_id}/occupancy/count"
    mqtt_service._on_message(None, None, FakeMsg(t, json.dumps({"node_id": "occ-pi", "count": 12, "confidence": 0.9})))
    r = db_session.query(models.OccupancyReading).one()
    assert r.count == 12 and r.source == "REAL"
    mqtt_service._on_message(None, None, FakeMsg(t, json.dumps({"node_id": "occ-pi", "sensor_status": "error"})))
    assert occupancy_service.current(db_session, z)["state"] == "UNAVAILABLE"


def test_mqtt_face_verify_and_ack_topics(db_session):
    from app.services import mqtt_service
    door, _ = mk_room(db_session); u = mk_user(db_session, "Rae"); enroll(db_session, u, 31); assign(db_session, door, u)
    mqtt_service._on_message(None, None, FakeMsg(f"site/{door.code}/face/verify", json.dumps(
        {"embedding": vec(31), "quality": 0.9, "liveness_passed": True, "node_id": "pi-door"})))
    e = db_session.query(models.AccessEvent).filter_by(method="face").one()
    assert e.result == "granted"
    db_session.refresh(door); assert door.locked is True
    mqtt_service._on_message(None, None, FakeMsg(f"site/{door.code}/face/ack", json.dumps({"event_id": e.event_id, "unlocked": True})))
    db_session.refresh(door); assert door.locked is False
    # physical failure is recorded, door stays locked
    mqtt_service._on_message(None, None, FakeMsg(f"site/{door.code}/face/verify", json.dumps(
        {"embedding": vec(31), "quality": 0.9, "liveness_passed": True})))
    e2 = db_session.query(models.AccessEvent).filter_by(method="face").order_by(models.AccessEvent.event_id.desc()).first()
    door.locked = True; db_session.commit()
    mqtt_service._on_message(None, None, FakeMsg(f"site/{door.code}/face/ack", json.dumps({"event_id": e2.event_id, "unlocked": False})))
    db_session.refresh(door); assert door.locked is True


def test_mqtt_device_telemetry_topic_creates_fault(db_session):
    from app.services import mqtt_service
    _, z = mk_room(db_session); d = mk_device(db_session, z)
    mqtt_service._on_message(None, None, FakeMsg(
        f"university/aiu/building/1/zone/{z.zone_id}/device/{d.device_id}/telemetry", json.dumps({"power_watts": 0})))
    assert db_session.query(models.DeviceFaultAlert).filter_by(source="REAL", severity="HIGH").count() == 1


def test_zero_count_does_not_trigger_immediate_shutdown(db_session):
    """A single zero reading feeds the existing EMPTY->VERIFYING->confirm path;
    it must not power anything off on the first pass."""
    from app.services import automation_engine
    _, z = mk_room(db_session)
    dev = models.Device(zone_id=z.zone_id, name="Lamp", type="LIGHT", status=True, criticality="NON_CRITICAL",
                        controllable=True, automatic_control_enabled=True)
    db_session.add(dev); db_session.commit()
    db_session.add(models.ZoneSchedule(zone_id=z.zone_id, day_of_week=None, open_time=datetime.time(0, 0),
                                       close_time=datetime.time(0, 0), grace_minutes=10, verification_minutes=5))
    db_session.commit()
    occupancy_service.ingest(db_session, z, node_id="o", count=0)
    automation_engine.process_zone_once(db_session, z)
    db_session.refresh(dev); db_session.refresh(z)
    assert dev.status is True  # no immediate action
    assert z.occupancy_state in ("EMPTY", "VERIFYING", "UNKNOWN")


def test_scope_restricted_admin_cannot_see_campus_wide_room_data(client, db_session):
    """Rooms have no AdminScope mapping, so a restricted admin gets 403 rather
    than a fabricated filter (same rule as Command Center's doors section)."""
    f = models.Faculty(name="Eng"); db_session.add(f); db_session.flush()
    a = mk_user(db_session, "Scoped", role="admin")
    db_session.add(models.AdminScope(user_id=a.user_id, faculty_id=f.faculty_id)); db_session.commit()
    h = token(client, "Scoped")
    for path in ("/api/occupancy/overview", "/api/rooms-intel/campus-map", "/api/device-faults",
                 "/api/device-faults/maintenance"):
        assert client.get(path, headers=h).status_code == 403, path
