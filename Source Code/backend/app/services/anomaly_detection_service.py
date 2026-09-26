"""
Feature #7 — Access Anomaly / Unusual Access Indicator.

A deterministic, explainable, rule-based detection layer over EXISTING
audit data — AccessEvent (physical RFID events AND the schedule_check
events Feature #5 logs), AccessWindow, DoorAssignment. No machine-learning
model, no random/opaque "risk score": every indicator here is produced by a
named rule with a fixed, documented threshold, and carries the evidence
(which events, when, at which door) that triggered it.

This module makes NO claim that any flagged event is malicious — it labels
observable deviations from a user's own recorded normal pattern
(UNUSUAL/ANOMALOUS/ELEVATED_RISK_INDICATOR), nothing stronger. A human
(admin) is expected to read the evidence and decide what it means.

Evidence hardening: rules that ask "was this access authorized at the
time" now prefer the AccessEvent's OWN evidence_snapshot — frozen onto the
row at the moment it happened by mqtt_service.py (physical RFID events) or
access_authorization_service.log_authorization_check (schedule_check
events) — over recomputing against today's AccessWindow rows. This is what
makes an already-recorded event's anomaly classification immune to a
window being edited or deleted afterward. Every indicator produced this
way carries `"evidence_basis": "recorded_evidence"`.

Older events written before this evidence_snapshot existed (or any event
where, for whatever reason, no usable snapshot was stored) fall back to
live-evaluating against current AccessWindow/DoorAssignment rows, exactly
as before — this is a real, honest limitation for those specific rows (an
edited/deleted window CAN change how a pre-hardening event now reads), and
every indicator produced this way is explicitly marked
`"evidence_basis": "current_state_fallback"` rather than being silently
indistinguishable from a recorded-evidence one.
"""
import datetime
import json

from .. import models
from ..config import settings
from . import access_authorization_service

BASIS_RECORDED = "recorded_evidence"
BASIS_FALLBACK = "current_state_fallback"

# Only these AccessEvent.method values represent a genuine "did this
# person get past this door" decision. "override" is an admin's own
# already-audited manual action (see doors.py::override_door) and "rex"
# is a request-to-exit button, not an entry — both are excluded from the
# authorization-mismatch and unusual-door rules to avoid flagging a
# legitimate, already-accountable admin action as an anomaly.
_ENTRY_METHODS = {"card", "card+fingerprint", "schedule_check"}

SEVERITY_UNUSUAL = "UNUSUAL"
SEVERITY_ANOMALOUS = "ANOMALOUS"
SEVERITY_ELEVATED = "ELEVATED_RISK_INDICATOR"


def _user_events(db, user: "models.User", since: datetime.datetime, now: datetime.datetime) -> list:
    """Every AccessEvent attributable to this user — either directly
    (user_id, set by schedule_check) or via one of their RFID credentials
    (credential_id), ordered chronologically."""
    credential_ids = [
        c.credential_id for c in db.query(models.Credential).filter(models.Credential.user_id == user.user_id).all()
    ]
    q = db.query(models.AccessEvent).filter(
        models.AccessEvent.event_time >= since, models.AccessEvent.event_time <= now,
    )
    if credential_ids:
        q = q.filter(
            (models.AccessEvent.user_id == user.user_id) | (models.AccessEvent.credential_id.in_(credential_ids))
        )
    else:
        q = q.filter(models.AccessEvent.user_id == user.user_id)
    return q.order_by(models.AccessEvent.event_time.asc()).all()


def _find_bursts(timestamps: list, threshold: int, window_minutes: int) -> list:
    """Returns non-overlapping (start_index, end_index) ranges into
    `timestamps` (already sorted ascending) where at least `threshold`
    events fall within `window_minutes` of the first event in that range.
    Deterministic, greedy, single pass — no randomness."""
    bursts = []
    n = len(timestamps)
    i = 0
    window = datetime.timedelta(minutes=window_minutes)
    while i <= n - threshold:
        window_end = timestamps[i] + window
        j = i
        while j < n and timestamps[j] <= window_end:
            j += 1
        if (j - i) >= threshold:
            bursts.append((i, j))
            i = j
        else:
            i += 1
    return bursts


def _recorded_evidence(e: "models.AccessEvent") -> dict | None:
    """Returns the parsed evidence_snapshot for an event, or None if it has
    none (pre-hardening event) or the source isn't an authorization
    decision at all (e.g. an admin override, which stores authorized=None
    on purpose — see build_override_evidence). Callers treat None as "fall
    back to live evaluation"."""
    if not e.evidence_snapshot:
        return None
    try:
        evidence = json.loads(e.evidence_snapshot)
    except (ValueError, TypeError):
        return None
    if evidence.get("authorized") is None:
        return None
    if evidence.get("authorization_source") not in (
        access_authorization_service.EVIDENCE_SOURCE_SCHEDULE_DERIVED,
        access_authorization_service.EVIDENCE_SOURCE_PHYSICAL_DOOR_NODE,
    ):
        return None
    return evidence


def _door_label(db, door_id: int) -> str:
    door = db.get(models.Door, door_id)
    return f"{door.name} ({door.code})" if door else f"door #{door_id}"


# ---------------------------------------------------------------------------
# Individual rules — each returns a list of indicator dicts
# ---------------------------------------------------------------------------
def _rule_repeated_denied_attempts(db, events: list) -> list:
    by_door: dict = {}
    for e in events:
        if e.result == "denied":
            by_door.setdefault(e.door_id, []).append(e)

    indicators = []
    for door_id, denied in by_door.items():
        times = [e.event_time for e in denied]
        for start, end in _find_bursts(times, settings.ANOMALY_DENIED_BURST_THRESHOLD, settings.ANOMALY_DENIED_BURST_WINDOW_MINUTES):
            cluster = denied[start:end]
            indicators.append({
                "rule": "REPEATED_DENIED_ATTEMPTS",
                "severity": SEVERITY_ELEVATED,
                "door_id": door_id,
                "door_label": _door_label(db, door_id),
                "triggered_at": cluster[-1].event_time,
                "explanation": (
                    f"{len(cluster)} denied access attempts at {_door_label(db, door_id)} "
                    f"within {settings.ANOMALY_DENIED_BURST_WINDOW_MINUTES} minutes"
                ),
                "evidence": {
                    "event_count": len(cluster),
                    "window_minutes": settings.ANOMALY_DENIED_BURST_WINDOW_MINUTES,
                    "first_at": cluster[0].event_time.isoformat(),
                    "last_at": cluster[-1].event_time.isoformat(),
                    "event_ids": [e.event_id for e in cluster],
                },
            })
    return indicators


def _rule_rapid_repeated_attempts(db, events: list) -> list:
    by_door: dict = {}
    for e in events:
        by_door.setdefault(e.door_id, []).append(e)

    indicators = []
    for door_id, door_events in by_door.items():
        times = [e.event_time for e in door_events]
        for start, end in _find_bursts(times, settings.ANOMALY_RAPID_BURST_THRESHOLD, settings.ANOMALY_RAPID_BURST_WINDOW_MINUTES):
            cluster = door_events[start:end]
            indicators.append({
                "rule": "REPEATED_ATTEMPTS_SHORT_WINDOW",
                "severity": SEVERITY_ANOMALOUS,
                "door_id": door_id,
                "door_label": _door_label(db, door_id),
                "triggered_at": cluster[-1].event_time,
                "explanation": (
                    f"{len(cluster)} access attempts (granted or denied) at {_door_label(db, door_id)} "
                    f"within {settings.ANOMALY_RAPID_BURST_WINDOW_MINUTES} minutes"
                ),
                "evidence": {
                    "event_count": len(cluster),
                    "window_minutes": settings.ANOMALY_RAPID_BURST_WINDOW_MINUTES,
                    "first_at": cluster[0].event_time.isoformat(),
                    "last_at": cluster[-1].event_time.isoformat(),
                    "event_ids": [e.event_id for e in cluster],
                    "results": [e.result for e in cluster],
                },
            })
    return indicators


def _rule_unusual_access_time(db, events: list) -> list:
    indicators = []
    for e in events:
        hour = e.event_time.hour
        if hour < settings.ANOMALY_UNUSUAL_HOUR_START_UTC or hour >= settings.ANOMALY_UNUSUAL_HOUR_END_UTC:
            indicators.append({
                "rule": "UNUSUAL_ACCESS_TIME",
                "severity": SEVERITY_UNUSUAL,
                "door_id": e.door_id,
                "door_label": _door_label(db, e.door_id),
                "triggered_at": e.event_time,
                "explanation": (
                    f"{e.result.capitalize()} access at {_door_label(db, e.door_id)} at "
                    f"{e.event_time.strftime('%H:%M')} UTC, outside the usual "
                    f"{settings.ANOMALY_UNUSUAL_HOUR_START_UTC:02d}:00–{settings.ANOMALY_UNUSUAL_HOUR_END_UTC:02d}:00 UTC window"
                ),
                "evidence": {"event_id": e.event_id, "event_time": e.event_time.isoformat(), "result": e.result},
            })
    return indicators


def _authorization_at_event(db, user: "models.User", door: "models.Door", e: "models.AccessEvent") -> tuple[bool, str, dict]:
    """Single shared lookup used by both the schedule and unusual-door
    rules: prefer the event's own recorded evidence; only fall back to
    live-evaluating AccessWindow/DoorAssignment rows when no usable
    snapshot exists. Returns (authorized, basis, detail-for-evidence).

    Feature #8 (emergency override): a recorded snapshot may carry a
    separate `emergency_override_active` fact alongside the ordinary WHO/WHEN
    verdict (see mqtt_service.py's /event handler) — an access that wasn't
    otherwise authorized but happened while the door had an active,
    admin-declared emergency override is NOT an unexplained authorization
    gap, so it's treated as authorized here too. This never rewrites the
    recorded evidence itself (the WHO/WHEN `authorized` field it carries
    stays exactly as recorded — the override is additional, distinguishable
    context, per the "clearly distinguishable from normal scheduled
    authorization" requirement), it only affects what THIS lookup reports
    back to the calling rule.
    """
    recorded = _recorded_evidence(e)
    if recorded is not None:
        authorized = recorded["authorized"] or bool(recorded.get("emergency_override_active"))
        return authorized, BASIS_RECORDED, recorded
    evaluation = access_authorization_service.evaluate_door_authorization(db, user, door, now=e.event_time)
    return evaluation["authorized"], BASIS_FALLBACK, evaluation


def _rule_unusual_door_for_user(db, user: "models.User", events: list) -> list:
    known_doors = {
        a.door_id for a in db.query(models.DoorAssignment).filter(models.DoorAssignment.instructor_id == user.user_id).all()
    }
    known_doors |= {
        w.door_id for w in db.query(models.AccessWindow).filter(models.AccessWindow.user_id == user.user_id).all()
    }

    indicators = []
    for e in events:
        if e.method not in _ENTRY_METHODS or e.result != "granted":
            continue
        if e.door_id in known_doors:
            continue
        door = db.get(models.Door, e.door_id)
        # Requirement: don't imply anything is wrong without checking
        # whether this "new" door visit was itself a defensibly authorized
        # one (e.g. a temporary window admin-granted that day) — a first
        # visit that WAS authorized reads very differently from one that
        # wasn't, even though both are still worth surfacing as "new for
        # this person."
        authorized, basis, detail = (True, BASIS_FALLBACK, None) if door is None else _authorization_at_event(db, user, door, e)
        indicators.append({
            "rule": "UNUSUAL_DOOR_FOR_USER",
            "severity": SEVERITY_UNUSUAL,
            "door_id": e.door_id,
            "door_label": _door_label(db, e.door_id),
            "triggered_at": e.event_time,
            "explanation": (
                f"First recorded granted access for this user at {_door_label(db, e.door_id)} — "
                f"not a door they hold a permanent assignment or any access window for. "
                + (
                    f"This specific visit was itself authorized ({detail.get('reason')})."
                    if detail is not None and authorized
                    else "No authorization record explains this specific visit either — see evidence."
                )
            ),
            "evidence": {
                "event_id": e.event_id, "event_time": e.event_time.isoformat(),
                "evidence_basis": basis, "was_this_visit_authorized": authorized,
                "authorization_detail": detail,
            },
        })
        known_doors.add(e.door_id)  # only flag the first time this door is seen
    return indicators


def _rule_outside_authorized_schedule(db, user: "models.User", events: list) -> list:
    indicators = []
    for e in events:
        if e.method not in _ENTRY_METHODS or e.result != "granted":
            continue
        door = db.get(models.Door, e.door_id)
        if not door:
            continue
        authorized, basis, detail = _authorization_at_event(db, user, door, e)
        if authorized:
            continue
        indicators.append({
            "rule": "ACCESS_OUTSIDE_AUTHORIZED_SCHEDULE",
            "severity": SEVERITY_ANOMALOUS,
            "door_id": e.door_id,
            "door_label": _door_label(db, e.door_id),
            "triggered_at": e.event_time,
            "explanation": (
                f"Access was granted at {_door_label(db, e.door_id)} at {e.event_time.isoformat()}Z, "
                f"but no permanent assignment or active access window covers that moment "
                + ("(based on evidence recorded at the time)" if basis == BASIS_RECORDED
                   else "(evaluated against CURRENT authorization records — no recorded evidence exists for this older event, so this is a best-effort fallback that a since-changed AccessWindow could affect)")
            ),
            "evidence": {
                "event_id": e.event_id, "event_time": e.event_time.isoformat(),
                "evidence_basis": basis, "authorization_check": detail,
            },
        })
    return indicators


def _rule_access_after_temporary_expiration(db, user: "models.User", events: list) -> list:
    """Note on evidence basis: this rule's very premise — "did a temporary
    window that covered this door expire shortly before this event" — is a
    lookup against the AccessWindow table by construction; there is no way
    to ask "did a since-DELETED window expire before this event" from
    evidence alone, since the window row itself (its end_at, its
    door/reason) is what the rule is about, not just whether access was
    authorized. This is an accepted, documented limitation: if a temporary
    window is deleted outright, this specific rule can no longer relate a
    later event to it (deleting the window makes the event unremarkable to
    this rule either way, so it never *incorrectly* flags what was
    legitimate — it can only under-report, never over-report, from a
    deletion).
    What IS hardened here: whether some OTHER grant authorized this later
    event is checked via recorded evidence first (falling back to a live
    check only when no snapshot exists), consistent with the other rules,
    and every indicator is tagged with which basis was used.
    """
    windows = (
        db.query(models.AccessWindow)
        .filter(models.AccessWindow.user_id == user.user_id, models.AccessWindow.recurring == False)  # noqa: E712
        .all()
    )
    if not windows:
        return []

    followup = datetime.timedelta(hours=settings.ANOMALY_POST_EXPIRY_FOLLOWUP_HOURS)
    indicators = []
    for e in events:
        if e.method not in _ENTRY_METHODS:
            continue
        for w in windows:
            if w.door_id != e.door_id or w.end_at is None:
                continue
            if not (w.end_at < e.event_time <= w.end_at + followup):
                continue
            door = db.get(models.Door, e.door_id)
            if door is None:
                continue
            authorized, basis, detail = _authorization_at_event(db, user, door, e)
            if authorized:
                continue  # some other valid grant covers this — not an expiration-related anomaly
            indicators.append({
                "rule": "ACCESS_AFTER_TEMPORARY_EXPIRATION",
                "severity": SEVERITY_ANOMALOUS,
                "door_id": e.door_id,
                "door_label": _door_label(db, e.door_id),
                "triggered_at": e.event_time,
                "explanation": (
                    f"{e.result.capitalize()} access attempt at {_door_label(db, e.door_id)} "
                    f"{(e.event_time - w.end_at)} after a temporary access window "
                    f"(\"{w.reason or 'no reason given'}\") expired at {w.end_at.isoformat()}Z"
                ),
                "evidence": {
                    "event_id": e.event_id, "event_time": e.event_time.isoformat(),
                    "access_window_id": w.access_window_id, "window_end_at": w.end_at.isoformat(),
                    "evidence_basis": basis, "authorization_check": detail,
                },
            })
    return indicators


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def detect_anomalies_for_user(db, user: "models.User", since_days: int | None = None,
                               now: datetime.datetime | None = None) -> dict:
    now = now or datetime.datetime.utcnow()
    since_days = since_days if since_days is not None else settings.ANOMALY_DEFAULT_LOOKBACK_DAYS
    since = now - datetime.timedelta(days=since_days)

    events = _user_events(db, user, since, now)

    indicators = []
    indicators += _rule_repeated_denied_attempts(db, events)
    indicators += _rule_rapid_repeated_attempts(db, events)
    indicators += _rule_unusual_access_time(db, events)
    indicators += _rule_unusual_door_for_user(db, user, events)
    indicators += _rule_outside_authorized_schedule(db, user, events)
    indicators += _rule_access_after_temporary_expiration(db, user, events)

    indicators.sort(key=lambda i: i["triggered_at"], reverse=True)

    summary = {SEVERITY_UNUSUAL: 0, SEVERITY_ANOMALOUS: 0, SEVERITY_ELEVATED: 0}
    for i in indicators:
        summary[i["severity"]] = summary.get(i["severity"], 0) + 1

    return {
        "user_id": user.user_id,
        "evaluated_at": now,
        "lookback_since": since,
        "event_count_considered": len(events),
        "summary": summary,
        "indicators": indicators,
    }


def detect_anomalies_for_door(db, door: "models.Door", since_days: int | None = None,
                               now: datetime.datetime | None = None) -> dict:
    """Door-centric view: which staff members have anomaly indicators at
    this specific door. Built by finding everyone with at least one
    AccessEvent at this door in the lookback window, then reusing
    detect_anomalies_for_user per person and keeping only the indicators
    that belong to this door — same rules, same evidence, just filtered and
    re-grouped for a "what's unusual about THIS room" view rather than a
    "what's unusual about THIS person" view.
    """
    now = now or datetime.datetime.utcnow()
    since_days = since_days if since_days is not None else settings.ANOMALY_DEFAULT_LOOKBACK_DAYS
    since = now - datetime.timedelta(days=since_days)

    door_events = (
        db.query(models.AccessEvent)
        .filter(models.AccessEvent.door_id == door.door_id,
                models.AccessEvent.event_time >= since, models.AccessEvent.event_time <= now)
        .all()
    )
    user_ids = {e.user_id for e in door_events if e.user_id}
    credential_ids = {e.credential_id for e in door_events if e.credential_id}
    if credential_ids:
        for cred in db.query(models.Credential).filter(models.Credential.credential_id.in_(credential_ids)).all():
            if cred.user_id:
                user_ids.add(cred.user_id)

    by_user = []
    summary = {SEVERITY_UNUSUAL: 0, SEVERITY_ANOMALOUS: 0, SEVERITY_ELEVATED: 0}
    for uid in user_ids:
        user = db.get(models.User, uid)
        if not user:
            continue
        report = detect_anomalies_for_user(db, user, since_days=since_days, now=now)
        door_indicators = [i for i in report["indicators"] if i["door_id"] == door.door_id]
        if not door_indicators:
            continue
        for i in door_indicators:
            summary[i["severity"]] = summary.get(i["severity"], 0) + 1
        by_user.append({"user_id": uid, "user_name": user.name, "indicators": door_indicators})

    by_user.sort(key=lambda entry: max(i["triggered_at"] for i in entry["indicators"]), reverse=True)

    return {
        "door_id": door.door_id,
        "evaluated_at": now,
        "lookback_since": since,
        "summary": summary,
        "staff": by_user,
    }
