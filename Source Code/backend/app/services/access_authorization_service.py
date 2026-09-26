"""
Feature #5 — Schedule-Derived Access Authorization: the WHEN layer on top of
the existing WHO (User, scoped by College/Department via AdminScope) and
WHERE (Door / OperationalScope) authorization. See AccessWindow's docstring
in app/models.py for the full design rationale (why this is separate from
DoorAssignment and the legacy door-wide Schedule, and why everything here is
UTC).

Pure, dependency-light functions — no FastAPI/HTTP concerns — so they're
directly unit-testable with an injected `now`, the same style already used
by energy_timeseries_service.py.
"""
import datetime
import json

from .. import models


def validate_window_shape(payload_dict: dict) -> None:
    """Raises ValueError with a specific, user-facing message for any
    structurally invalid window. Called by the router before writing
    anything, so a bad request never reaches the database.
    """
    recurring = payload_dict.get("recurring")
    if recurring:
        if payload_dict.get("day_of_week") is None:
            raise ValueError("A recurring window needs day_of_week (0=Monday .. 6=Sunday)")
        if not (0 <= payload_dict["day_of_week"] <= 6):
            raise ValueError("day_of_week must be between 0 (Monday) and 6 (Sunday)")
        if payload_dict.get("start_time") is None or payload_dict.get("end_time") is None:
            raise ValueError("A recurring window needs both start_time and end_time")
        if payload_dict["end_time"] <= payload_dict["start_time"]:
            raise ValueError("end_time must be after start_time")
        valid_from = payload_dict.get("valid_from")
        valid_until = payload_dict.get("valid_until")
        if valid_from and valid_until and valid_until <= valid_from:
            raise ValueError("valid_until must be after valid_from")
    else:
        if payload_dict.get("start_at") is None or payload_dict.get("end_at") is None:
            raise ValueError("A temporary (non-recurring) window needs both start_at and end_at")
        if payload_dict["end_at"] <= payload_dict["start_at"]:
            raise ValueError("end_at must be after start_at")


def is_window_active(window: "models.AccessWindow", now: datetime.datetime | None = None) -> tuple[bool, str]:
    """Returns (active, human-readable reason) for a single window at `now`
    (UTC, defaults to datetime.utcnow()). Never mutates the row — an expired
    window simply evaluates to (False, ...) forever after, it is not
    deleted, so it stays visible in history as an expired grant.
    """
    now = now or datetime.datetime.utcnow()

    if window.recurring:
        if window.valid_from and now < window.valid_from:
            return False, f"Recurring window not active yet (starts {window.valid_from.isoformat()}Z)"
        if window.valid_until and now > window.valid_until:
            return False, f"Recurring window has ended (was valid until {window.valid_until.isoformat()}Z)"
        if now.weekday() != window.day_of_week:
            return False, f"Not the scheduled day (this window is for weekday {window.day_of_week}, today is {now.weekday()})"
        t = now.time()
        if not (window.start_time <= t < window.end_time):
            return False, f"Outside the scheduled daily window ({window.start_time}–{window.end_time} UTC)"
        return True, f"Within recurring scheduled window ({window.start_time}–{window.end_time} UTC on weekday {window.day_of_week})"

    # One-off / temporary window
    if now < window.start_at:
        return False, f"Access not yet active (starts {window.start_at.isoformat()}Z)"
    if now > window.end_at:
        return False, f"Temporary access has expired (ended {window.end_at.isoformat()}Z)"
    return True, f"Within temporary access window (until {window.end_at.isoformat()}Z)"


def evaluate_door_authorization(db, user: "models.User", door: "models.Door",
                                 now: datetime.datetime | None = None) -> dict:
    """The single source of truth for "is this user allowed through this
    door right now". Combines two additive sources with OR — a window can
    never take away DoorAssignment's permanent access, and multiple windows
    never conflict with each other (any one being active is enough), the
    same non-conflicting-additive-evidence pattern already used for
    occupancy-signal fusion elsewhere in this codebase.
    """
    now = now or datetime.datetime.utcnow()

    permanent = (
        db.query(models.DoorAssignment)
        .filter(models.DoorAssignment.door_id == door.door_id, models.DoorAssignment.instructor_id == user.user_id)
        .first()
        is not None
    )

    windows = (
        db.query(models.AccessWindow)
        .filter(models.AccessWindow.door_id == door.door_id, models.AccessWindow.user_id == user.user_id)
        .all()
    )
    window_evals = []
    any_active = False
    for w in windows:
        active, reason = is_window_active(w, now)
        any_active = any_active or active
        window_evals.append({
            "access_window_id": w.access_window_id,
            "recurring": w.recurring,
            "active": active,
            "reason": reason,
            "door_id": w.door_id,
            "course_code": w.course_code,
        })

    authorized = permanent or any_active
    if permanent:
        overall_reason = "Permanent access assignment (DoorAssignment) — always authorized regardless of schedule"
    elif any_active:
        overall_reason = "No permanent access, but authorized via an active scheduled/temporary access window"
    else:
        overall_reason = "No permanent access and no currently active scheduled or temporary window"

    return {
        "door_id": door.door_id,
        "user_id": user.user_id,
        "evaluated_at": now,
        "has_permanent_access": permanent,
        "authorized": authorized,
        "reason": overall_reason,
        "windows": window_evals,
    }


EVIDENCE_SOURCE_SCHEDULE_DERIVED = "schedule_derived"   # /api/doors/{id}/authorization check (Feature #5)
EVIDENCE_SOURCE_PHYSICAL_DOOR_NODE = "physical_door_node"  # a real RFID event reported by the door hardware
EVIDENCE_SOURCE_ADMIN_OVERRIDE = "admin_override"       # doors.py::override_door — not a WHO/WHEN decision at all
EVIDENCE_SOURCE_AUTO_SHUTDOWN = "auto_shutdown"          # energy_service.py's own automation, same rationale


def build_authorization_evidence(evaluation: dict, *, source: str) -> dict:
    """Anomaly-evidence hardening: turns an evaluate_door_authorization()
    result into the flat, storable shape every AccessEvent.evidence_snapshot
    now uses, regardless of which code path produced the event (a real
    schedule/authorization check, an actual RFID swipe, or an admin
    override). This is what makes historical anomaly analysis stop
    depending on today's AccessWindow rows — the fields below are computed
    and frozen onto the event AT THE MOMENT IT HAPPENED, so deleting or
    editing an AccessWindow afterward can never retroactively change how an
    already-recorded event reads.

    `matched_window`/`temporary`/`expires_at` describe whichever window
    made the difference (the first ACTIVE one, if any — permanent access
    doesn't need one) purely for explainability; `authorized`/`reason` are
    the actual decision fields anomaly rules key off of.
    """
    active_window = next((w for w in evaluation["windows"] if w["active"]), None)
    return {
        "authorization_source": source,
        "authorized": evaluation["authorized"],
        "reason": evaluation["reason"],
        "has_permanent_access": evaluation["has_permanent_access"],
        "matched_window": active_window,
        "temporary": (not active_window["recurring"]) if active_window else None,
        "door_id": evaluation["door_id"],
        "user_id": evaluation["user_id"],
        "evaluated_at": evaluation["evaluated_at"],
        # Kept for completeness/debugging — the fields above are what
        # anomaly_detection_service.py actually reads.
        "full_evaluation": evaluation,
    }


def build_override_evidence(*, action: str, actor: "models.User", reason: str | None = None,
                             override_id: int | None = None, expires_at: "datetime.datetime | None" = None,
                             operational_scope_id: int | None = None, status: str | None = None) -> dict:
    """Evidence for an admin override — covers both the plain instant
    lock/unlock (doors.py::override_door, no reason/expiry) and Feature #8's
    Emergency Override (emergency_override_service.py, which passes reason/
    override_id/expires_at/operational_scope_id/status). One evidence shape
    for both, per the "reuse build_override_evidence rather than a second
    format" requirement — the extra fields are simply None for the plain
    case.

    This is explicitly NOT a WHO/WHEN authorization decision (an admin can
    always lock/unlock, and an emergency override deliberately bypasses the
    normal WHO/WHEN question rather than answering it) — authorized/
    temporary/matched_window stay None rather than a misleading True/False.
    `temporary` becomes True specifically when this override HAS an
    expires_at (i.e. is a real Feature #8 emergency override, not the plain
    door endpoint's fire-and-forget action), which is what makes it
    "clearly distinguishable from normal scheduled authorization" in the
    stored evidence itself.
    """
    return {
        "authorization_source": EVIDENCE_SOURCE_ADMIN_OVERRIDE,
        "authorized": None,
        "reason": reason or f"Manual {action} override by admin {actor.name} (#{actor.user_id})",
        "has_permanent_access": None,
        "matched_window": None,
        "temporary": expires_at is not None,
        "actor_user_id": actor.user_id,
        "actor_name": actor.name,
        "action": action,
        # Feature #8 fields — None for the plain instant override.
        "override_id": override_id,
        "expires_at": expires_at,
        "operational_scope_id": operational_scope_id,
        "status": status,
    }


def log_authorization_check(db, *, door: "models.Door", user: "models.User", evaluation: dict) -> "models.AccessEvent":
    """Persists the evaluation into the EXISTING access_events audit table
    (method="schedule_check") rather than a second logging system — see
    AccessEvent's additive user_id/evidence_snapshot columns."""
    evidence = build_authorization_evidence(evaluation, source=EVIDENCE_SOURCE_SCHEDULE_DERIVED)
    event = models.AccessEvent(
        door_id=door.door_id,
        credential_id=None,
        method="schedule_check",
        result="granted" if evaluation["authorized"] else "denied",
        user_id=user.user_id,
        evidence_snapshot=json.dumps(evidence, default=str),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
