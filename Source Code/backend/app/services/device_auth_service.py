"""
Device identity registry + MQTT message authentication (Phase 1B).

WHAT THIS IS
  Every communicating node (ESP32, Raspberry Pi, gateway) gets its own
  DeviceIdentity with its own secret and an explicit scope (message types,
  zones, door codes). A node proves who it is by wrapping each MQTT payload
  in a small HMAC-SHA256 envelope. This is separate from user login (JWT)
  and from the shared door-node X-Node-Key used by the Face ID HTTP routes.

ENVELOPE (wire format, JSON, MQTT 3.1.1 compatible - no MQTT 5 features)
  {"auth": "aiu-hmac-v1", "device_id": "<id>", "ts": <unix seconds, int>,
   "nonce": "<8-64 chars, unique per message>", "payload": "<original payload, as a string>",
   "sig": "<64 hex chars>"}

  sig = HMAC-SHA256(key, "\n".join([auth, device_id, topic, str(ts), nonce,
                                    sha256_hex(payload_utf8)]))
  key = the device secret (32 random bytes, handed out once as 64 hex chars).

  Binding the TOPIC stops a captured message being replayed onto another
  topic/zone. Hashing the payload gives integrity. ts + a persisted nonce
  give replay protection (accepted window: MQTT_AUTH_MAX_SKEW_SECONDS).

  A message without the "aiu-hmac-v1" tag is a LEGACY message (what every
  existing simulator, firmware and test sends). It is never mistaken for an
  authenticated one.

MODES (settings.MQTT_AUTH_MODE)
  off      no inspection; identical to pre-Phase-1B behaviour.
  warn     DEFAULT. Verify everything, record structured security events, but
           process messages exactly as they would have been processed before.
           Warn-only grants NOTHING new: a failed or legacy message is handled
           like a legacy message always was, and every downstream control
           (RBAC, zone ownership checks in the handlers, automation safety
           rules, Face ID decide()) still applies unchanged.
  enforce  NOT enabled by default and not rolled out. Drops every message that
           is not a verified, authorized device message. Implemented and unit
           tested; never exercised against a live broker.

WHAT AUTHENTICATION DOES NOT DO
  A verified identity only establishes WHO sent a message and that it was
  authorized for that topic/zone. It never bypasses RBAC, the zone/sensor
  ownership checks in mqtt_service's handlers, automation safety rules, or
  face_service.decide(); all of those run afterwards, unchanged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
import datetime
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from .. import crypto, models
from ..config import settings

logger = logging.getLogger("device_auth")

AUTH_TAG = "aiu-hmac-v1"
MODES = ("off", "warn", "enforce")

# Message kinds a device may be authorized for (the registry's vocabulary).
LEGACY_KINDS = {
    "status": "door_status", "event": "door_event", "alert": "door_alert",
    "ac/status": "ac_status", "light/status": "light_status",
    "occupancy/status": "legacy_occupancy_status",
    "face/verify": "face_verify", "face/ack": "face_ack",
}
V2_KINDS = ("sensor_telemetry", "device_state", "occupancy", "occupancy_count",
            "hvac_telemetry", "device_telemetry", "health")
KNOWN_KINDS = tuple(sorted(set(LEGACY_KINDS.values()) | {"plug_status"} | set(V2_KINDS)))

# Event types (security findings).
EV_LEGACY = "LEGACY_UNSIGNED"
EV_UNKNOWN = "UNKNOWN_DEVICE"
EV_REVOKED = "REVOKED_DEVICE"
EV_MISSING_SIG = "MISSING_SIGNATURE"
EV_BAD_SIG = "INVALID_SIGNATURE"
EV_EXPIRED = "EXPIRED_TIMESTAMP"
EV_REPLAY = "REPLAY_DETECTED"
EV_BAD_TOPIC = "UNAUTHORIZED_TOPIC"
EV_BAD_ZONE = "UNAUTHORIZED_ZONE"
EV_NODE_MISMATCH = "NODE_ID_MISMATCH"
EV_MALFORMED = "MALFORMED_ENVELOPE"
EV_NO_SECRET = "SECRET_UNAVAILABLE"
EV_AUTH_OK = "AUTHENTICATED"

_SEVERITY = {
    EV_LEGACY: "INFO", EV_UNKNOWN: "WARNING", EV_REVOKED: "CRITICAL", EV_MISSING_SIG: "WARNING",
    EV_BAD_SIG: "CRITICAL", EV_EXPIRED: "WARNING", EV_REPLAY: "CRITICAL", EV_BAD_TOPIC: "CRITICAL",
    EV_BAD_ZONE: "CRITICAL", EV_NODE_MISMATCH: "CRITICAL", EV_MALFORMED: "WARNING", EV_NO_SECRET: "WARNING",
}

_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


# --------------------------------------------------------------------- helpers
def effective_mode() -> str:
    m = (settings.MQTT_AUTH_MODE or "").strip().lower()
    return m if m in MODES else "warn"          # unknown value never means enforce


def _load_list(text) -> list:
    try:
        v = json.loads(text or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def classify_topic(topic: str):
    """-> (kind | None, zone_id | None, door_code | None). kind None = a topic
    shape no device is ever authorized to publish to."""
    parts = topic.split("/")
    if parts[0] == "site" and len(parts) >= 3:
        code, tail = parts[1], "/".join(parts[2:])
        if tail in LEGACY_KINDS:
            return LEGACY_KINDS[tail], None, code
        if len(parts) == 5 and parts[2] == "plug" and parts[4] == "status":
            return "plug_status", None, code
        return None, None, code
    if (parts[0] == "university" and len(parts) >= 7 and parts[2] == "building" and parts[4] == "zone"):
        try:
            zone_id = int(parts[5])
        except ValueError:
            return None, None, None
        rest = parts[6:]
        if len(rest) == 3 and rest[0] == "sensor" and rest[2] == "telemetry":
            return "sensor_telemetry", zone_id, None
        if len(rest) == 3 and rest[0] == "device" and rest[2] == "state":
            return "device_state", zone_id, None
        if len(rest) == 3 and rest[0] == "device" and rest[2] == "telemetry":
            return "device_telemetry", zone_id, None
        if rest == ["occupancy"]:
            return "occupancy", zone_id, None
        if rest == ["occupancy", "count"]:
            return "occupancy_count", zone_id, None
        if rest == ["hvac", "telemetry"]:
            return "hvac_telemetry", zone_id, None
        if rest == ["health"]:
            return "health", zone_id, None
        return None, zone_id, None
    return None, None, None


def signing_string(device_id: str, topic: str, ts: int, nonce: str, payload: bytes) -> bytes:
    return "\n".join([AUTH_TAG, device_id, topic, str(int(ts)), nonce,
                      hashlib.sha256(payload).hexdigest()]).encode("utf-8")


def compute_signature(secret_hex: str, device_id: str, topic: str, ts: int, nonce: str, payload: bytes) -> str:
    return hmac.new(bytes.fromhex(secret_hex), signing_string(device_id, topic, ts, nonce, payload),
                    hashlib.sha256).hexdigest()


def sign_message(device_id: str, secret_hex: str, topic: str, payload, *, ts: int | None = None,
                 nonce: str | None = None) -> bytes:
    """Reference client implementation (used by tests/simulators; a Pi or ESP32
    client reimplements exactly this). Returns the bytes to publish."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    ts = int(time.time()) if ts is None else int(ts)
    nonce = nonce or secrets.token_hex(12)
    return json.dumps({
        "auth": AUTH_TAG, "device_id": device_id, "ts": ts, "nonce": nonce,
        "payload": raw.decode("utf-8"),
        "sig": compute_signature(secret_hex, device_id, topic, ts, nonce, raw),
    }, separators=(",", ":")).encode("utf-8")


# ------------------------------------------------------------ security events
_throttle_lock = threading.Lock()
_throttle: dict = {}          # (event_type, device, topic) -> [last_logged_epoch, suppressed]


def reset_throttle() -> None:
    with _throttle_lock:
        _throttle.clear()


def _record_event(db, event_type, *, mode, action, claimed_device_id=None, identity_id=None, topic=None,
                  zone_id=None, detail=None) -> None:
    """Never raises: a logging failure must not affect message handling. Holds
    no payload/signature/nonce/secret by construction (only the fields below)."""
    try:
        key = (event_type, claimed_device_id or "-", topic or "-")
        now = time.monotonic()
        window = max(0, int(settings.MQTT_AUTH_EVENT_THROTTLE_SECONDS))
        with _throttle_lock:
            entry = _throttle.get(key)
            if entry and window and now - entry[0] < window:
                entry[1] += 1
                return
            suppressed = entry[1] if entry else 0
            _throttle[key] = [now, 0]
        db.add(models.DeviceSecurityEvent(
            event_type=event_type, severity=_SEVERITY.get(event_type, "WARNING"),
            claimed_device_id=(claimed_device_id or None) and str(claimed_device_id)[:64],
            identity_id=identity_id, topic=(topic or None) and topic[:200], zone_id=zone_id,
            enforcement_mode=mode, action_taken=action, detail=(detail or None) and detail[:300],
            suppressed_count=suppressed))
        db.commit()
        logger.warning("device-auth %s device=%s topic=%s mode=%s action=%s",
                       event_type, claimed_device_id, topic, mode, action)
    except Exception:
        db.rollback()
        logger.exception("could not record device security event")


# ------------------------------------------------------------------ main entry
@dataclass
class AuthResult:
    status: str                 # EV_* constant, EV_AUTH_OK, or "OFF"
    process: bool               # should the caller handle the message?
    payload: bytes              # payload to hand to the existing handlers
    authenticated: bool = False
    identity_id: int | None = None
    device_id: str | None = None


def _parse_envelope(payload: bytes):
    """-> None (legacy message) | dict (envelope candidate)."""
    if AUTH_TAG.encode() not in payload:
        return None
    try:
        data = json.loads(payload)
    except ValueError:
        return {}                                   # tag present but not parseable
    if isinstance(data, dict) and data.get("auth") == AUTH_TAG:
        return data
    return None


def process_incoming(db, topic: str, payload: bytes, *, now_epoch: float | None = None) -> AuthResult:
    mode = effective_mode()
    if mode == "off":
        return AuthResult("OFF", True, payload)
    env = _parse_envelope(payload)
    if env is None:                                  # legacy / unsigned
        _record_event(db, EV_LEGACY, mode=mode, topic=topic, zone_id=classify_topic(topic)[1],
                      action="DROPPED" if mode == "enforce" else "PROCESSED_UNVERIFIED",
                      detail="no device authentication envelope")
        return AuthResult(EV_LEGACY, mode != "enforce", payload)

    status, ident, inner = _verify(db, topic, env, now_epoch if now_epoch is not None else time.time())
    claimed = env.get("device_id") if isinstance(env.get("device_id"), str) else None
    zone_id = classify_topic(topic)[1]
    if status == EV_AUTH_OK:
        return AuthResult(EV_AUTH_OK, True, inner, True, ident.identity_id, ident.device_id)

    handled = mode != "enforce"
    _record_event(db, status, mode=mode, claimed_device_id=claimed, topic=topic, zone_id=zone_id,
                  identity_id=ident.identity_id if ident is not None else None,
                  action="PROCESSED_UNVERIFIED" if handled else "DROPPED",
                  detail="message failed device authentication")
    # warn mode: hand over the inner payload (if any) as an UNVERIFIED legacy-equivalent message
    inner_bytes = inner if inner is not None else payload
    return AuthResult(status, handled, inner_bytes, False,
                      ident.identity_id if ident is not None else None, claimed)


def _verify(db, topic: str, env: dict, now_epoch: float):
    """-> (status, identity | None, inner_payload_bytes | None)"""
    device_id, ts, nonce = env.get("device_id"), env.get("ts"), env.get("nonce")
    inner_s, sig = env.get("payload"), env.get("sig")
    if (not isinstance(device_id, str) or not _DEVICE_ID_RE.match(device_id)
            or not isinstance(inner_s, str) or not isinstance(nonce, str) or not (8 <= len(nonce) <= 64)
            or not isinstance(ts, int) or isinstance(ts, bool)):
        return EV_MALFORMED, None, None
    inner = inner_s.encode("utf-8")

    ident = db.query(models.DeviceIdentity).filter(models.DeviceIdentity.device_id == device_id).first()
    if ident is None:
        return EV_UNKNOWN, None, inner
    ident.last_seen_at = datetime.datetime.utcnow()
    db.commit()
    if ident.status != "ACTIVE":
        return EV_REVOKED, ident, inner
    if not isinstance(sig, str) or not sig:
        return EV_MISSING_SIG, ident, inner

    secret_hex = crypto.decrypt_blob(ident.secret_enc)
    if secret_hex is None:
        return EV_NO_SECRET, ident, inner
    expected = compute_signature(secret_hex, device_id, topic, ts, nonce, inner)
    try:
        ok = hmac.compare_digest(expected.encode("ascii"), sig.lower().encode("ascii"))   # constant time
    except (UnicodeEncodeError, ValueError):
        ok = False
    if not ok:
        return EV_BAD_SIG, ident, inner

    if abs(now_epoch - ts) > settings.MQTT_AUTH_MAX_SKEW_SECONDS:
        return EV_EXPIRED, ident, inner

    # Authorization: scope is checked BEFORE the nonce is consumed.
    kind, zone_id, door_code = classify_topic(topic)
    if kind is None or kind not in _load_list(ident.allowed_message_types):
        return EV_BAD_TOPIC, ident, inner
    if zone_id is not None and zone_id not in _load_list(ident.allowed_zone_ids):
        return EV_BAD_ZONE, ident, inner
    if door_code is not None and door_code not in _load_list(ident.allowed_door_codes):
        return EV_BAD_ZONE, ident, inner
    try:                                   # a node may only speak as itself
        body = json.loads(inner_s)
        if isinstance(body, dict) and body.get("node_id") is not None and body.get("node_id") != ident.node_id:
            return EV_NODE_MISMATCH, ident, inner
    except ValueError:
        pass

    try:
        with db.begin_nested():
            db.add(models.DeviceMessageNonce(identity_id=ident.identity_id, nonce=nonce))
            db.flush()
    except IntegrityError:
        return EV_REPLAY, ident, inner
    ident.last_authenticated_at = datetime.datetime.utcnow()
    _prune_nonces(db)
    db.commit()
    return EV_AUTH_OK, ident, inner


def _prune_nonces(db) -> None:
    """Keep the nonce table bounded: anything older than 2x the accepted skew
    can no longer pass the timestamp check anyway."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=max(60, 2 * settings.MQTT_AUTH_MAX_SKEW_SECONDS))
    db.query(models.DeviceMessageNonce).filter(models.DeviceMessageNonce.seen_at < cutoff).delete(
        synchronize_session=False)


# ------------------------------------------------------------------- registry
def _validate_scope(db, message_types, zone_ids, door_codes):
    bad = [m for m in message_types if m not in KNOWN_KINDS]
    if bad:
        raise ValueError(f"unknown message type(s): {', '.join(sorted(bad))}")
    for z in zone_ids:
        if db.get(models.Zone, z) is None:
            raise ValueError(f"unknown zone_id {z}")
    for c in door_codes:
        if db.query(models.Door).filter(models.Door.code == c).first() is None:
            raise ValueError(f"unknown door code '{c}'")


def create_identity(db, *, device_id: str, name: str | None, node_id: str | None, message_types, zone_ids,
                    door_codes, actor: models.User):
    """-> (DeviceIdentity, secret_hex). The secret is returned ONCE and is not
    retrievable afterwards."""
    if not _DEVICE_ID_RE.match(device_id or ""):
        raise ValueError("device_id must be 3-64 characters: letters, digits, '.', '_' or '-'")
    if db.query(models.DeviceIdentity).filter(models.DeviceIdentity.device_id == device_id).first():
        raise ValueError("device_id already registered")
    _validate_scope(db, message_types, zone_ids, door_codes)
    secret_hex = secrets.token_bytes(32).hex()
    row = models.DeviceIdentity(
        device_id=device_id, name=name, node_id=node_id, status="ACTIVE",
        secret_enc=crypto.encrypt_blob(secret_hex), secret_version=1,
        allowed_message_types=json.dumps(sorted(set(message_types))),
        allowed_zone_ids=json.dumps(sorted(set(zone_ids))),
        allowed_door_codes=json.dumps(sorted(set(door_codes))), created_by_id=actor.user_id)
    db.add(row)
    db.flush()
    return row, secret_hex


def rotate_secret(db, ident: models.DeviceIdentity) -> str:
    """Immediate rotation: the previous secret stops working at once (there is
    no grace period yet - see docs)."""
    if ident.status != "ACTIVE":
        raise ValueError("cannot rotate the secret of a revoked identity")
    secret_hex = secrets.token_bytes(32).hex()
    ident.secret_enc = crypto.encrypt_blob(secret_hex)
    ident.secret_version = (ident.secret_version or 1) + 1
    ident.secret_rotated_at = datetime.datetime.utcnow()
    return secret_hex


def revoke(db, ident: models.DeviceIdentity, *, actor: models.User, reason: str | None) -> bool:
    if ident.status == "REVOKED":
        return False
    ident.status = "REVOKED"
    ident.revoked_at = datetime.datetime.utcnow()
    ident.revoked_by_id = actor.user_id
    ident.revoke_reason = (reason or "")[:200] or None
    return True


def update_scope(db, ident: models.DeviceIdentity, *, message_types, zone_ids, door_codes) -> None:
    _validate_scope(db, message_types, zone_ids, door_codes)
    ident.allowed_message_types = json.dumps(sorted(set(message_types)))
    ident.allowed_zone_ids = json.dumps(sorted(set(zone_ids)))
    ident.allowed_door_codes = json.dumps(sorted(set(door_codes)))


def secret_health(db) -> dict:
    """Counts ACTIVE identities whose stored secret cannot be decrypted with the
    current CREDENTIAL_ENCRYPTION_KEY (wrong/rotated/temporary key). Returns
    counts only - never a secret or any part of one."""
    active = db.query(models.DeviceIdentity).filter(models.DeviceIdentity.status == "ACTIVE").all()
    bad = sum(1 for r in active if crypto.decrypt_blob(r.secret_enc) is None)
    return {"active_identities": len(active), "undecryptable": bad}
