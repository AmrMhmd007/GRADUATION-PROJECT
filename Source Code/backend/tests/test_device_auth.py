"""Phase 1B: device identity registry + MQTT HMAC message authentication.

Everything here runs against the in-process handlers (mqtt_service._on_message)
and the REST API. No live MQTT broker, no ESP32, no Raspberry Pi was used.
"""
import json
import logging
import time

import pytest

from app import models
from app.config import settings
from app.services import device_auth_service as das
from app.services import mqtt_service


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


@pytest.fixture(autouse=True)
def _auth_defaults(monkeypatch):
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "warn")
    monkeypatch.setattr(settings, "MQTT_AUTH_EVENT_THROTTLE_SECONDS", 0)
    monkeypatch.setattr(settings, "MQTT_AUTH_MAX_SKEW_SECONDS", 120)
    das.reset_throttle()
    yield
    das.reset_throttle()


def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def mk_zone(db, name="Z"):
    z = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(z)
    db.commit()
    db.refresh(z)
    return z


def mk_sensor(db, zone_id):
    s = models.Sensor(zone_id=zone_id, sensor_type="PIR", status="offline")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def register(client, admin_token, *, device_id="esp-a1", zones=(), types=("sensor_telemetry",), doors=(),
             node_id=None):
    r = client.post("/api/device-identities", headers=H(admin_token), json={
        "device_id": device_id, "name": device_id, "node_id": node_id,
        "message_types": list(types), "zone_ids": list(zones), "door_codes": list(doors)})
    assert r.status_code == 201, r.text
    return r.json()["secret"]


def telem_topic(zone, sensor):
    return f"university/aiu/building/1/zone/{zone.zone_id}/sensor/{sensor.sensor_id}/telemetry"


def occ_payload(v=True):
    return json.dumps({"metric": "occupancy", "value": v, "quality": "good", "sequence_number": 1})


def send(topic, raw):
    mqtt_service._on_message(None, None, FakeMsg(topic, raw))


def events(db):
    db.expire_all()
    return [e.event_type for e in db.query(models.DeviceSecurityEvent).order_by(models.DeviceSecurityEvent.event_id)]


def reading_applied(db, sensor):
    db.expire_all()
    return db.get(models.Sensor, sensor.sensor_id).occupancy_state is not None


@pytest.fixture
def setup(client, admin_token, db_session):
    z = mk_zone(db_session)
    s = mk_sensor(db_session, z.zone_id)
    secret = register(client, admin_token, zones=[z.zone_id])
    return z, s, secret


# -------------------------------------------------------------- valid
def test_valid_signed_message_is_authenticated_and_processed(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    send(topic, das.sign_message("esp-a1", secret, topic, occ_payload(True)))
    db_session.expire_all()
    assert db_session.get(models.Sensor, s.sensor_id).occupancy_state is True
    ident = db_session.query(models.DeviceIdentity).one()
    assert ident.last_authenticated_at is not None and ident.last_seen_at is not None
    assert events(db_session) == []                       # nothing suspicious to report
    assert db_session.query(models.DeviceMessageNonce).count() == 1


def test_process_incoming_distinguishes_authenticated_from_legacy(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    ok = das.process_incoming(db_session, topic, das.sign_message("esp-a1", secret, topic, occ_payload()))
    legacy = das.process_incoming(db_session, topic, occ_payload().encode())
    assert ok.authenticated and ok.status == das.EV_AUTH_OK and ok.device_id == "esp-a1"
    assert not legacy.authenticated and legacy.status == das.EV_LEGACY
    assert ok.payload == occ_payload().encode()          # envelope removed for the real handlers


# -------------------------------------------------------------- failures (warn mode)
def test_unknown_device(setup, db_session):
    z, s, _ = setup
    topic = telem_topic(z, s)
    send(topic, das.sign_message("ghost-99", "ab" * 32, topic, occ_payload()))
    assert events(db_session) == [das.EV_UNKNOWN]
    assert reading_applied(db_session, s)                 # warn: handled like any legacy message, nothing more


def test_revoked_device(client, admin_token, setup, db_session):
    z, s, secret = setup
    assert client.post("/api/device-identities/esp-a1/revoke", json={"reason": "stolen"},
                       headers=H(admin_token)).json()["status"] == "REVOKED"
    topic = telem_topic(z, s)
    send(topic, das.sign_message("esp-a1", secret, topic, occ_payload()))
    assert events(db_session) == [das.EV_REVOKED]
    ev = db_session.query(models.DeviceSecurityEvent).one()
    assert ev.severity == "CRITICAL" and ev.action_taken == "PROCESSED_UNVERIFIED"


def test_missing_signature(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    env = json.loads(das.sign_message("esp-a1", secret, topic, occ_payload()))
    del env["sig"]
    send(topic, json.dumps(env))
    assert events(db_session) == [das.EV_MISSING_SIG]


def test_invalid_signature_wrong_secret(setup, db_session):
    z, s, _ = setup
    topic = telem_topic(z, s)
    send(topic, das.sign_message("esp-a1", "cd" * 32, topic, occ_payload()))
    assert events(db_session) == [das.EV_BAD_SIG]


def test_non_hex_or_non_ascii_signature_is_invalid_not_a_crash(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    for bad in ("zz" * 32, "é" * 64, "0" * 63):
        env = json.loads(das.sign_message("esp-a1", secret, topic, occ_payload()))
        env["sig"] = bad
        send(topic, json.dumps(env))
    assert events(db_session) == [das.EV_BAD_SIG] * 3


def test_tampered_payload(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    env = json.loads(das.sign_message("esp-a1", secret, topic, occ_payload(True)))
    env["payload"] = occ_payload(False)
    send(topic, json.dumps(env))
    assert events(db_session) == [das.EV_BAD_SIG]


def test_signature_is_bound_to_topic(setup, db_session):
    z, s, secret = setup
    other = mk_sensor(db_session, z.zone_id)
    signed_for = telem_topic(z, s)
    msg = das.sign_message("esp-a1", secret, signed_for, occ_payload())
    send(telem_topic(z, other), msg)                      # captured message replayed on another topic
    assert events(db_session) == [das.EV_BAD_SIG]


def test_replay_attempt(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    msg = das.sign_message("esp-a1", secret, topic, occ_payload())
    send(topic, msg)
    assert events(db_session) == []
    send(topic, msg)                                      # identical bytes again
    assert events(db_session) == [das.EV_REPLAY]


def test_expired_and_future_timestamps(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    send(topic, das.sign_message("esp-a1", secret, topic, occ_payload(), ts=int(time.time()) - 3600))
    send(topic, das.sign_message("esp-a1", secret, topic, occ_payload(), ts=int(time.time()) + 3600))
    assert events(db_session) == [das.EV_EXPIRED, das.EV_EXPIRED]


def test_unauthorized_message_type(client, admin_token, db_session):
    z = mk_zone(db_session)
    secret = register(client, admin_token, device_id="esp-b1", zones=[z.zone_id], types=["sensor_telemetry"])
    topic = f"university/aiu/building/1/zone/{z.zone_id}/health"
    send(topic, das.sign_message("esp-b1", secret, topic, json.dumps({"rssi": -50})))
    assert events(db_session) == [das.EV_BAD_TOPIC]


def test_unknown_topic_shape_is_unauthorized(client, admin_token, db_session):
    z = mk_zone(db_session)
    secret = register(client, admin_token, device_id="esp-b2", zones=[z.zone_id],
                      types=list(das.KNOWN_KINDS))
    for topic in (f"university/aiu/building/1/zone/{z.zone_id}/device/1/command", "site/A101/cmd",
                  "something/else"):
        send(topic, das.sign_message("esp-b2", secret, topic, "{}"))
    assert events(db_session) == [das.EV_BAD_TOPIC] * 3


def test_unauthorized_zone(client, admin_token, db_session):
    za, zb = mk_zone(db_session, "A"), mk_zone(db_session, "B")
    sb = mk_sensor(db_session, zb.zone_id)
    secret = register(client, admin_token, device_id="esp-c1", zones=[za.zone_id])
    topic = telem_topic(zb, sb)
    send(topic, das.sign_message("esp-c1", secret, topic, occ_payload()))
    assert events(db_session) == [das.EV_BAD_ZONE]


def test_unauthorized_door_code(client, admin_token, db_session):
    secret = register(client, admin_token, device_id="door-1", types=["door_status"], doors=["A101"])
    send("site/A101/status", das.sign_message("door-1", secret, "site/A101/status", "online"))
    assert events(db_session) == []
    send("site/ZZZ/status", das.sign_message("door-1", secret, "site/ZZZ/status", "online"))
    assert events(db_session) == [das.EV_BAD_ZONE]


def test_empty_scope_authorizes_nothing(client, admin_token, db_session):
    z = mk_zone(db_session)
    s = mk_sensor(db_session, z.zone_id)
    secret = register(client, admin_token, device_id="esp-d1", zones=[], types=[])
    topic = telem_topic(z, s)
    send(topic, das.sign_message("esp-d1", secret, topic, occ_payload()))
    assert events(db_session) == [das.EV_BAD_TOPIC]


def test_node_id_must_match_registered_node(client, admin_token, db_session):
    z = mk_zone(db_session)
    secret = register(client, admin_token, device_id="esp-e1", zones=[z.zone_id], types=["health"],
                      node_id="node-e1")
    topic = f"university/aiu/building/1/zone/{z.zone_id}/health"
    send(topic, das.sign_message("esp-e1", secret, topic, json.dumps({"node_id": "node-e1", "rssi": -40})))
    assert events(db_session) == []
    send(topic, das.sign_message("esp-e1", secret, topic, json.dumps({"node_id": "someone-else"})))
    assert events(db_session) == [das.EV_NODE_MISMATCH]


# -------------------------------------------------------------- warn mode grants nothing new
def test_authenticated_identity_does_not_bypass_handler_zone_checks(client, admin_token, db_session):
    za, zb = mk_zone(db_session, "A"), mk_zone(db_session, "B")
    sensor_in_b = mk_sensor(db_session, zb.zone_id)
    secret = register(client, admin_token, device_id="esp-f1", zones=[za.zone_id, zb.zone_id])
    # authorized zone A, but the sensor belongs to zone B: the existing handler check still rejects it
    topic = f"university/aiu/building/1/zone/{za.zone_id}/sensor/{sensor_in_b.sensor_id}/telemetry"
    send(topic, das.sign_message("esp-f1", secret, topic, occ_payload()))
    assert not reading_applied(db_session, sensor_in_b)
    assert db_session.query(models.OccupancyEvent).count() == 0


def test_warn_mode_never_blocks_what_was_processed_before(setup, db_session):
    z, s, secret = setup
    topic = telem_topic(z, s)
    send(topic, das.sign_message("esp-a1", "ee" * 32, topic, occ_payload()))   # failed auth, warn mode
    assert reading_applied(db_session, s)


# -------------------------------------------------------------- existing simulators
def test_legacy_simulators_unchanged_and_flagged_as_unverified(setup, db_session):
    z, s, _ = setup
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    door.online = False
    db_session.commit()
    send("site/A101/status", "online")
    send(telem_topic(z, s), occ_payload(True))
    db_session.expire_all()
    assert db_session.get(models.Door, door.door_id).online is True
    assert db_session.get(models.Sensor, s.sensor_id).occupancy_state is True
    ev = db_session.query(models.DeviceSecurityEvent).all()
    assert {e.event_type for e in ev} == {das.EV_LEGACY}
    assert all(e.severity == "INFO" and e.action_taken == "PROCESSED_UNVERIFIED" for e in ev)


def test_legacy_event_throttling_counts_suppressed(setup, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MQTT_AUTH_EVENT_THROTTLE_SECONDS", 300)
    for _ in range(5):
        send("site/A101/status", "online")
    assert events(db_session) == [das.EV_LEGACY]          # one row, not five


# -------------------------------------------------------------- rotation / revocation
def test_secret_rotation_invalidates_old_secret(client, admin_token, setup, db_session):
    z, s, old = setup
    topic = telem_topic(z, s)
    r = client.post("/api/device-identities/esp-a1/rotate-secret", headers=H(admin_token))
    assert r.status_code == 200 and r.json()["secret_version"] == 2
    new = r.json()["secret"]
    assert new != old
    send(topic, das.sign_message("esp-a1", old, topic, occ_payload()))
    assert events(db_session) == [das.EV_BAD_SIG]
    send(topic, das.sign_message("esp-a1", new, topic, occ_payload()))
    assert events(db_session) == [das.EV_BAD_SIG]          # new secret accepted, no new finding


def test_revoked_identity_cannot_be_rotated_or_edited(client, admin_token, setup):
    client.post("/api/device-identities/esp-a1/revoke", json={}, headers=H(admin_token))
    assert client.post("/api/device-identities/esp-a1/rotate-secret", headers=H(admin_token)).status_code == 409
    assert client.put("/api/device-identities/esp-a1/scope", headers=H(admin_token),
                      json={"message_types": ["health"]}).status_code == 409
    assert client.post("/api/device-identities/esp-a1/revoke", json={}, headers=H(admin_token)).status_code == 409


# -------------------------------------------------------------- modes
def test_enforce_mode_drops_everything_not_verified(setup, db_session, monkeypatch):
    z, s, secret = setup
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "enforce")
    topic = telem_topic(z, s)
    send(topic, occ_payload(True))                                              # legacy
    send(topic, das.sign_message("esp-a1", "ee" * 32, topic, occ_payload(True)))  # bad signature
    assert not reading_applied(db_session, s)
    assert set(e.action_taken for e in db_session.query(models.DeviceSecurityEvent)) == {"DROPPED"}
    good = das.sign_message("esp-a1", secret, topic, occ_payload(True))
    send(topic, good)
    assert reading_applied(db_session, s)
    send(topic, good)                                                           # replay dropped, state unchanged
    assert events(db_session)[-1] == das.EV_REPLAY


def test_off_mode_is_inert(setup, db_session, monkeypatch):
    z, s, _ = setup
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "off")
    send("site/A101/status", "online")
    assert events(db_session) == []


def test_unrecognised_mode_falls_back_to_warn_never_enforce(monkeypatch):
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "enforced")
    assert das.effective_mode() == "warn"
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "")
    assert das.effective_mode() == "warn"


def test_default_mode_is_warn_not_enforce():
    import inspect
    from app import config
    assert 'os.getenv("MQTT_AUTH_MODE", "warn")' in inspect.getsource(config)
    assert das.effective_mode() == "warn"


def test_screening_failure_fails_open_in_warn_and_closed_in_enforce(setup, db_session, monkeypatch):
    z, s, _ = setup
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(das, "process_incoming", boom)
    send(telem_topic(z, s), occ_payload(True))
    assert reading_applied(db_session, s)                  # warn: pre-Phase-1B behaviour preserved
    db_session.query(models.Sensor).filter_by(sensor_id=s.sensor_id).update({"occupancy_state": None})
    db_session.commit()
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "enforce")
    send(telem_topic(z, s), occ_payload(True))
    assert not reading_applied(db_session, s)


# -------------------------------------------------------------- secrets hygiene
def test_secrets_never_logged_stored_plain_or_returned_again(client, admin_token, setup, db_session, caplog):
    z, s, secret = setup
    topic = telem_topic(z, s)
    caplog.set_level(logging.DEBUG)
    bad = das.sign_message("esp-a1", "ee" * 32, topic, occ_payload())
    good = das.sign_message("esp-a1", secret, topic, occ_payload())
    sig_bad = json.loads(bad)["sig"]
    send(topic, bad)
    send(topic, good)
    log_text = caplog.text
    assert secret not in log_text and sig_bad not in log_text and json.loads(good)["sig"] not in log_text
    assert json.loads(good)["nonce"] not in log_text
    ident = db_session.query(models.DeviceIdentity).one()
    assert secret not in ident.secret_enc                  # encrypted at rest
    for r in (client.get("/api/device-identities", headers=H(admin_token)),
              client.get("/api/device-identities/esp-a1", headers=H(admin_token)),
              client.get("/api/device-security/events", headers=H(admin_token)),
              client.get("/api/device-security/summary", headers=H(admin_token))):
        assert r.status_code == 200 and secret not in r.text and "secret_enc" not in r.text
    cols = " ".join(str(getattr(e, c)) for e in db_session.query(models.DeviceSecurityEvent).all()
                    for c in ("detail", "topic", "claimed_device_id"))
    assert secret not in cols and sig_bad not in cols


def test_signature_compare_is_constant_time():
    import inspect
    assert "hmac.compare_digest" in inspect.getsource(das._verify)


# -------------------------------------------------------------- admin API / RBAC
def test_api_requires_unrestricted_admin(client, admin_token):
    assert client.get("/api/device-identities").status_code in (401, 403)
    r = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    inst = {"Authorization": "Bearer " + r.json()["access_token"]}
    for method, path in (("get", "/api/device-identities"), ("post", "/api/device-identities"),
                         ("get", "/api/device-security/events"), ("get", "/api/device-security/summary"),
                         ("post", "/api/device-identities/x/revoke"), ("post", "/api/device-identities/x/rotate-secret")):
        assert getattr(client, method)(path, headers=inst).status_code == 403, path


def test_api_validation(client, admin_token, db_session):
    z = mk_zone(db_session)
    ok = {"device_id": "esp-v1", "message_types": ["health"], "zone_ids": [z.zone_id], "door_codes": []}
    assert client.post("/api/device-identities", headers=H(admin_token), json=ok).status_code == 201
    assert client.post("/api/device-identities", headers=H(admin_token), json=ok).status_code == 422       # duplicate
    for bad in ({**ok, "device_id": "x"}, {**ok, "device_id": "has space"}, {**ok, "message_types": ["root"]},
                {**ok, "device_id": "esp-v2", "zone_ids": [99999]},
                {**ok, "device_id": "esp-v3", "door_codes": ["NOPE"]}):
        assert client.post("/api/device-identities", headers=H(admin_token), json=bad).status_code == 422
    assert client.get("/api/device-identities/nope", headers=H(admin_token)).status_code == 404


def test_registry_changes_are_audited_without_secrets(client, admin_token, setup, db_session):
    z, s, secret = setup
    client.post("/api/device-identities/esp-a1/rotate-secret", headers=H(admin_token))
    client.post("/api/device-identities/esp-a1/revoke", json={"reason": "test"}, headers=H(admin_token))
    db_session.expire_all()
    rows = db_session.query(models.AuditLog).filter(models.AuditLog.resource_type == "device_identity").all()
    assert {r.action for r in rows} == {"device_identity_create", "device_identity_rotate", "device_identity_revoke"}
    assert secret not in " ".join(str(r.description) for r in rows)


def test_summary_reports_mode_and_counts(client, admin_token, setup, db_session):
    send("site/A101/status", "online")
    j = client.get("/api/device-security/summary", headers=H(admin_token)).json()
    assert j["mode"] == "warn" and j["events_last_24h"].get(das.EV_LEGACY) == 1 and j["identities"]["ACTIVE"] == 1
