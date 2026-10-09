"""
Face-based door access (backend-authoritative).

Pipeline: door-node camera -> node-side embedding + liveness -> THIS service
(match -> identity -> evaluate_door_authorization -> GRANT/DENY) -> AccessEvent
(method="face") -> AuditLog. A schedule alone never reaches GRANT here: a face
must match an ENROLLED template AND the existing WHO/WHEN evaluation must
pass. Every failure path (no match, ambiguous, low quality, liveness fail,
revoked/inactive user, unauthorized, node fault) resolves to DENY or
UNAVAILABLE - never GRANT. UNAVAILABLE (node/camera fault) is NOT a denial of
the person and NOT a grant: no AccessEvent decision is fabricated.

Templates are Fernet-encrypted (crypto.py) and only decrypted in-process to
compare; they are never returned by any schema.
"""
from __future__ import annotations

import datetime
import json
import math

from .. import crypto, models
from ..config import settings
from . import access_authorization_service as authz
from . import audit_service, emergency_override_service

EVIDENCE_SOURCE_FACE = "face_door_node"


def _norm(v):
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        raise ValueError("embedding has zero magnitude")
    return [x / n for x in v]


def validate_embedding(embedding) -> list[float]:
    if not isinstance(embedding, (list, tuple)) or not (8 <= len(embedding) <= 4096):
        raise ValueError("embedding must be a numeric vector of length 8-4096")
    try:
        vec = [float(x) for x in embedding]
    except (TypeError, ValueError):
        raise ValueError("embedding must contain only numbers")
    if any(math.isnan(x) or math.isinf(x) for x in vec):
        raise ValueError("embedding contains non-finite values")
    return _norm(vec)


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def active_face(db, user_id: int):
    return (db.query(models.FaceCredential)
            .filter(models.FaceCredential.user_id == user_id, models.FaceCredential.status == "ENROLLED")
            .order_by(models.FaceCredential.face_id.desc()).first())


def face_status(db, user_id: int) -> dict:
    """Metadata only - never the template."""
    f = active_face(db, user_id)
    if f is None:
        last = (db.query(models.FaceCredential).filter(models.FaceCredential.user_id == user_id)
                .order_by(models.FaceCredential.face_id.desc()).first())
        return {"user_id": user_id, "status": "REVOKED" if last and last.status == "REVOKED" else
                ("DISABLED" if last and last.status == "DISABLED" else "NOT_ENROLLED"),
                "enrolled_at": None, "model_version": None, "quality_score": None,
                "liveness_passed": None, "source": None}
    return {"user_id": user_id, "status": "ENROLLED", "enrolled_at": f.enrolled_at,
            "model_version": f.model_version, "quality_score": f.quality_score,
            "liveness_passed": f.liveness_passed, "source": f.enrolled_source}


def enroll(db, user: models.User, *, embedding, quality: float, liveness_passed: bool | None,
           model_version: str | None, source: str, actor: models.User) -> models.FaceCredential:
    """Quality-gated enrollment. Re-enrollment supersedes (REVOKES) the
    previous ENROLLED row rather than overwriting it."""
    if user.status != "active":
        raise ValueError("Account is not active")
    if quality is None or quality < settings.FACE_MIN_QUALITY:
        raise ValueError(f"Capture quality too low (need >= {settings.FACE_MIN_QUALITY})")
    if settings.FACE_REQUIRE_LIVENESS and liveness_passed is not True:
        raise ValueError("Liveness check did not pass")
    vec = validate_embedding(embedding)
    now = datetime.datetime.utcnow()
    prev = active_face(db, user.user_id)
    if prev is not None:
        prev.status = "REVOKED"
        prev.revoked_at = now
        prev.revoked_by_id = actor.user_id
        prev.revoke_reason = "re-enrolled"
    row = models.FaceCredential(
        user_id=user.user_id, status="ENROLLED", template_enc=crypto.encrypt_blob(json.dumps(vec)),
        template_dim=len(vec), model_version=model_version, quality_score=quality,
        liveness_checked=liveness_passed is not None, liveness_passed=liveness_passed,
        enrolled_source=source, enrolled_by_id=actor.user_id,
    )
    db.add(row)
    db.flush()
    audit_service.log(db, actor, "face_reenroll" if prev else "face_enroll", "face_credential",
                      resource_id=row.face_id, resource_label=user.email,
                      description=f"Face ID {'re-enrolled' if prev else 'enrolled'} for {user.email} (source={source})")
    return row


def revoke(db, user: models.User, *, actor: models.User, reason: str | None, disable_only: bool = False) -> bool:
    f = active_face(db, user.user_id)
    if f is None:
        return False
    f.status = "DISABLED" if disable_only else "REVOKED"
    f.revoked_at = datetime.datetime.utcnow()
    f.revoked_by_id = actor.user_id
    f.revoke_reason = (reason or "")[:200] or None
    audit_service.log(db, actor, "face_disable" if disable_only else "face_revoke", "face_credential",
                      resource_id=f.face_id, resource_label=user.email,
                      description=f"Face ID {'disabled' if disable_only else 'revoked'} for {user.email}")
    return True


def _candidates(db):
    rows = (db.query(models.FaceCredential, models.User)
            .join(models.User, models.User.user_id == models.FaceCredential.user_id)
            .filter(models.FaceCredential.status == "ENROLLED").all())
    out = []
    for fc, u in rows:
        raw = crypto.decrypt_blob(fc.template_enc)
        if raw is None:
            continue  # unreadable template can never match
        out.append((u, json.loads(raw)))
    return out


def identify(db, probe: list[float]):
    """Returns (user|None, best_score, reason). Ambiguity => no identity."""
    scored = sorted(((cosine(probe, t), u) for u, t in _candidates(db) if len(t) == len(probe)),
                    key=lambda x: -x[0])
    if not scored:
        return None, 0.0, "No enrolled faces"
    best, user = scored[0]
    if best < settings.FACE_MATCH_THRESHOLD:
        return None, best, "No enrolled face matched"
    if len(scored) > 1 and best - scored[1][0] < settings.FACE_AMBIGUITY_MARGIN and scored[1][1].user_id != user.user_id:
        return None, best, "Ambiguous match between enrolled faces"
    return user, best, "Matched"


def _record(db, door, *, result, user, evidence, reason):
    ev = models.AccessEvent(door_id=door.door_id, credential_id=None, method="face", result=result,
                            user_id=user.user_id if user else None,
                            evidence_snapshot=json.dumps(evidence, default=str))
    db.add(ev)
    db.flush()
    audit_service.log(db, None, "face_access_" + result, "door", resource_id=door.door_id,
                      resource_label=door.code,
                      description=f"Face access {result.upper()} at {door.code}: {reason}",
                      result="success")
    return ev


def decide(db, door: models.Door, *, embedding, quality: float | None, liveness_passed: bool | None,
           node_status: str = "ok", node_id: str | None = None, now=None) -> dict:
    """Returns {decision: GRANT|DENY|UNAVAILABLE, reason, event_id, user_id}."""
    now = now or datetime.datetime.utcnow()
    base = {"face_door_node": True, "node_id": node_id, "node_status": node_status,
            "face_match_threshold": settings.FACE_MATCH_THRESHOLD}

    # Hardware/node failure: neither grant nor a verdict about the person.
    if node_status != "ok" or embedding is None:
        return {"decision": "UNAVAILABLE", "reason": "Door node could not produce a face verification "
                f"(node_status={node_status}) - no access decision made", "event_id": None, "user_id": None}

    def deny(reason, user=None, extra=None):
        ev = {"authorization_source": EVIDENCE_SOURCE_FACE, "authorized": False, "reason": reason,
              "face": {**base, "quality": quality, "liveness_passed": liveness_passed, **(extra or {})}}
        e = _record(db, door, result="denied", user=user, evidence=ev, reason=reason)
        db.commit()
        return {"decision": "DENY", "reason": reason, "event_id": e.event_id,
                "user_id": user.user_id if user else None}

    if quality is None or quality < settings.FACE_MIN_QUALITY:
        return deny("Capture quality too low")
    if settings.FACE_REQUIRE_LIVENESS and liveness_passed is not True:
        return deny("Liveness check failed or not performed")
    try:
        probe = validate_embedding(embedding)
    except ValueError as exc:
        return deny(f"Invalid face data: {exc}")

    user, score, why = identify(db, probe)
    if user is None:
        return deny(why, extra={"match_score": round(score, 4)})
    if user.status != "active":
        return deny("Account is not active", user=user, extra={"match_score": round(score, 4)})

    evaluation = authz.evaluate_door_authorization(db, user, door, now=now)
    evidence = authz.build_authorization_evidence(evaluation, source=EVIDENCE_SOURCE_FACE)
    evidence["face"] = {**base, "quality": quality, "liveness_passed": liveness_passed,
                        "match_score": round(score, 4), "identity_resolved": True}
    ov = emergency_override_service.active_override_for_door(db, door.door_id)
    evidence["emergency_override_active"] = (
        {"override_id": ov.override_id, "action": ov.action, "reason": ov.reason, "expires_at": ov.expires_at}
        if ov else None)
    if not evaluation["authorized"]:
        evidence["reason"] = "Face verified but not authorized: " + evaluation["reason"]
        e = _record(db, door, result="denied", user=user, evidence=evidence, reason=evidence["reason"])
        db.commit()
        return {"decision": "DENY", "reason": evidence["reason"], "event_id": e.event_id, "user_id": user.user_id}

    e = _record(db, door, result="granted", user=user, evidence=evidence,
                reason="Face verified + authorized + valid schedule/window")
    db.commit()
    return {"decision": "GRANT", "reason": "Face verified and authorized", "event_id": e.event_id,
            "user_id": user.user_id}


def confirm_physical(db, door: models.Door, event_id: int, unlocked: bool) -> bool:
    """The door node reports whether it ACTUALLY unlocked. Only this sets
    door.locked=False for a face grant - a sent decision is not a physical
    action. Recorded on the original event's evidence (append-only note)."""
    e = db.get(models.AccessEvent, event_id)
    if e is None or e.door_id != door.door_id or e.method != "face":
        return False
    ev = json.loads(e.evidence_snapshot or "{}")
    if "physical_confirmation" in ev:
        return False
    ev["physical_confirmation"] = {"unlocked": bool(unlocked), "at": datetime.datetime.utcnow().isoformat() + "Z"}
    e.evidence_snapshot = json.dumps(ev, default=str)
    if e.result == "granted" and unlocked:
        door.locked = False
    db.commit()
    return True
