"""
Feature #8 — Emergency Access / Override.

A controlled, time-bounded, reasoned, fully audited alternative to the
plain instant lock/unlock in routers/doors.py::override_door. See
EmergencyOverride's docstring in models.py for the full design rationale.

Important behavior (per the feature spec, enforced here — not just in the
UI):
  Normal access stays:   Permanent Assignment / Schedule -> Authorization
  Emergency access is:   Authorized Admin -> Emergency Override ->
                          Temporary Authorization -> Audit Evidence

This module never writes to DoorAssignment or AccessWindow — an emergency
override is a distinct, clearly-labeled pathway, not a disguised permanent
grant or a disguised schedule entry. It reuses the EXISTING AdminScope /
OperationalScope authorization system (via security.require_operational_
scope_access) rather than inventing a second RBAC system, and reuses
access_authorization_service.build_override_evidence() for its evidence
shape rather than inventing a second evidence format.

Pure, testable functions — the router is a thin HTTP wrapper around these,
same split as access_authorization_service.py / anomaly_detection_service.py.
"""
from __future__ import annotations

import datetime
import json
import logging
import threading

from fastapi import HTTPException, status

from ..database import SessionLocal
from .. import models, security
from ..config import settings
from . import access_authorization_service, mqtt_service

logger = logging.getLogger("emergency_override_service")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def effective_status(override: "models.EmergencyOverride", now: datetime.datetime | None = None) -> str:
    """Live-computed status — never mutates the row. Mirrors AccessWindow's
    is_window_active()/evaluate-on-read pattern: the stored `status` column
    is the durable audit record of a TERMINAL event (REVOKED, or EXPIRED
    once the sweep has run), but a row can be "actually" expired for a
    little while before the background sweep next runs, and callers (the
    UI, the authorization check below) must never show or act on stale
    ACTIVE status just because the sweep hasn't caught up yet."""
    now = now or _now()
    if override.status == "REVOKED":
        return "REVOKED"
    if override.status == "EXPIRED" or now >= override.expires_at:
        return "EXPIRED"
    return "ACTIVE"


def seconds_remaining(override: "models.EmergencyOverride", now: datetime.datetime | None = None) -> int | None:
    now = now or _now()
    if effective_status(override, now) != "ACTIVE":
        return None
    return max(0, int((override.expires_at - now).total_seconds()))


def to_out_dict(override: "models.EmergencyOverride", now: datetime.datetime | None = None) -> dict:
    now = now or _now()
    return {
        "override_id": override.override_id,
        "door_id": override.door_id,
        "door_code": override.door_code,
        "door_name": override.door_name,
        "operational_scope_id": override.operational_scope_id,
        "action": override.action,
        "reason": override.reason,
        "created_by_id": override.created_by_id,
        "created_by_name": override.created_by_name,
        "created_at": override.created_at,
        "expires_at": override.expires_at,
        "status": override.status,
        "effective_status": effective_status(override, now),
        "revoked_at": override.revoked_at,
        "revoked_by_id": override.revoked_by_id,
        "seconds_remaining": seconds_remaining(override, now),
    }


def _authorize_scope(db, admin: "models.User", operational_scope_id: int | None) -> None:
    """Reuses the EXISTING AdminScope/OperationalScope system — no second
    RBAC system. Door itself has no faculty/department/operational-scope
    link (deliberately not introduced by this feature — see EmergencyOverride's
    docstring), so a scope-restricted admin proves their authority by
    declaring which operational area justifies the emergency, and that
    declaration is checked exactly like any other operational-scope grant.
    An unrestricted admin (zero AdminScope rows — today's default for every
    existing admin) is never blocked here, matching every other scope check
    in this codebase."""
    if not security.is_scope_restricted(admin, db):
        return
    if operational_scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your admin account is scope-restricted — an emergency override must declare "
                   "which operational scope it falls under",
        )
    security.require_operational_scope_access(operational_scope_id, admin, db)


def active_override_for_door(db, door_id: int, now: datetime.datetime | None = None) -> "models.EmergencyOverride | None":
    """The one override (if any) currently in force for a door. Used both
    by the "conflict" check on creation and by evidence-building at ingestion
    time (mqtt_service.py) so a physical access event during an emergency
    window can explain itself without touching WHO/WHEN authorization."""
    now = now or _now()
    candidates = (
        db.query(models.EmergencyOverride)
        .filter(models.EmergencyOverride.door_id == door_id, models.EmergencyOverride.status == "ACTIVE")
        .all()
    )
    for o in candidates:
        if effective_status(o, now) == "ACTIVE":
            return o
    return None


def create_override(db, *, door: "models.Door", admin: "models.User", action: str, reason: str,
                     duration_minutes: int, operational_scope_id: int | None = None) -> "models.EmergencyOverride":
    """Validates everything server-side (never trusts frontend state, per
    the spec) then executes the override through the SAME publish_override
    plumbing the plain door endpoint uses, and logs it via the SAME
    AccessEvent audit table + build_override_evidence() shape Feature #7's
    evidence architecture already established — just enriched with the
    override's id/expiry/scope/status so historical analysis can tell an
    emergency-authorized access apart from an ordinary one.
    """
    if action not in ("lock", "unlock"):
        raise HTTPException(status_code=400, detail="action must be 'lock' or 'unlock'")
    if not reason or not reason.strip():
        raise HTTPException(status_code=400, detail="A reason/justification is required for an emergency override")
    if duration_minutes is None or duration_minutes <= 0:
        raise HTTPException(status_code=400, detail="duration_minutes must be a positive number")
    if duration_minutes > settings.EMERGENCY_OVERRIDE_MAX_DURATION_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=f"duration_minutes cannot exceed {settings.EMERGENCY_OVERRIDE_MAX_DURATION_MINUTES} minutes — "
                   f"an emergency override must never silently become permanent access",
        )
    if operational_scope_id is not None:
        scope = db.get(models.OperationalScope, operational_scope_id)
        if scope is None:
            raise HTTPException(status_code=404, detail="Operational scope not found")

    _authorize_scope(db, admin, operational_scope_id)

    now = _now()
    conflict = active_override_for_door(db, door.door_id, now=now)
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Door already has an active emergency override (#{conflict.override_id}, "
                   f"expires {conflict.expires_at.isoformat()}Z) — revoke it before creating another",
        )

    expires_at = now + datetime.timedelta(minutes=duration_minutes)

    override = models.EmergencyOverride(
        door_id=door.door_id,
        operational_scope_id=operational_scope_id,
        action=action,
        reason=reason.strip(),
        created_by_id=admin.user_id,
        created_at=now,
        expires_at=expires_at,
        status="ACTIVE",
    )
    db.add(override)
    db.flush()  # assigns override.override_id for the evidence below

    sent = mqtt_service.publish_override(door.code, action)
    evidence = access_authorization_service.build_override_evidence(
        action=action, actor=admin,
        reason=f"Emergency {action} override — {override.reason}",
        override_id=override.override_id, expires_at=expires_at,
        operational_scope_id=operational_scope_id, status="ACTIVE",
    )
    db.add(models.AccessEvent(
        door_id=door.door_id, credential_id=None, method="override",
        result="sent" if sent else "queued_no_broker",
        user_id=admin.user_id,
        evidence_snapshot=json.dumps(evidence, default=str),
    ))
    door.locked = (action == "lock")

    db.commit()
    db.refresh(override)
    return override


def revoke_override(db, *, override: "models.EmergencyOverride", admin: "models.User",
                     note: str | None = None) -> "models.EmergencyOverride":
    """Ends an override early. Reverts the door to locked (the safe default)
    unless another active override says otherwise — an admin cancelling an
    emergency unlock should not leave the door silently unlocked forever,
    which would be exactly the "silently becomes permanent access" failure
    mode this feature is required to prevent."""
    now = _now()
    current = effective_status(override, now)
    if current != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"This override is already {current.lower()}, not active")

    override.status = "REVOKED"
    override.revoked_at = now
    override.revoked_by_id = admin.user_id
    db.flush()

    _revert_door_after_override(db, override, admin, now, reason_prefix="Emergency override revoked")

    db.commit()
    db.refresh(override)
    return override


def _revert_door_after_override(db, override: "models.EmergencyOverride", actor: "models.User",
                                 now: datetime.datetime, *, reason_prefix: str) -> None:
    """Shared by revoke and the expiry sweep: re-locks the door (undoing an
    'unlock' override) unless some OTHER active override on the same door
    already dictates otherwise, and logs one more audited AccessEvent for
    the reversion itself so "override ended" is as visible in the trail as
    "override created"."""
    door = db.get(models.Door, override.door_id)
    if door is None:
        return

    still_active = active_override_for_door(db, override.door_id, now=now)
    if still_active is not None:
        return  # another override is in force — don't clobber it

    reverted_action = "lock" if override.action == "unlock" else None
    if reverted_action:
        sent = mqtt_service.publish_override(door.code, reverted_action)
        door.locked = True
        evidence = access_authorization_service.build_override_evidence(
            action=reverted_action, actor=actor,
            reason=f"{reason_prefix} (#{override.override_id}) — reverting to locked",
            override_id=override.override_id, expires_at=override.expires_at,
            operational_scope_id=override.operational_scope_id, status=override.status,
        )
        db.add(models.AccessEvent(
            door_id=door.door_id, credential_id=None, method="override",
            result="sent" if sent else "queued_no_broker",
            user_id=actor.user_id,
            evidence_snapshot=json.dumps(evidence, default=str),
        ))


def expire_overrides_sweep(db, now: datetime.datetime | None = None) -> list[int]:
    """Periodic background sweep (same shape as staleness_watchdog.sweep_once
    / energy_service.run_checkout_sweep): finds every ACTIVE override whose
    expires_at has passed, marks it EXPIRED, reverts the door, and logs an
    audit event — factored out as a pure function so it's directly
    unit-testable without a real timer/thread. Returns the ids just expired."""
    now = now or _now()
    stale = (
        db.query(models.EmergencyOverride)
        .filter(models.EmergencyOverride.status == "ACTIVE", models.EmergencyOverride.expires_at <= now)
        .all()
    )
    expired_ids = []
    for override in stale:
        override.status = "EXPIRED"
        db.flush()
        actor = db.get(models.User, override.created_by_id) or override.created_by
        _revert_door_after_override(db, override, actor, now, reason_prefix="Emergency override expired")
        expired_ids.append(override.override_id)
    if expired_ids:
        db.commit()
    return expired_ids


def _loop():
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            expired = expire_overrides_sweep(db)
            if expired:
                logger.info("Expired %d emergency override(s): %s", len(expired), expired)
        except Exception:
            logger.exception("Emergency override expiry sweep failed")
        finally:
            db.close()
        _stop_event.wait(settings.EMERGENCY_OVERRIDE_SWEEP_INTERVAL_SECONDS)


def start():
    global _thread
    if settings.DISABLE_MQTT:
        # Same guard as staleness_watchdog/energy_service — no live door
        # control transport is running in this mode (tests, or MQTT
        # deliberately disabled), so an override's revert-the-door action
        # would have nothing to actually publish to anyway. Overrides
        # created directly via the service/router still work and still
        # expire correctly (evaluated live by effective_status()) — only
        # the background auto-revert convenience is skipped.
        logger.info("DISABLE_MQTT set — emergency override sweep not started")
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    logger.info("Emergency override sweep started (checked every %ss)",
                settings.EMERGENCY_OVERRIDE_SWEEP_INTERVAL_SECONDS)


def stop():
    _stop_event.set()
