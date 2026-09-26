"""
Stage C — Investigation & Evidence.

This module invents NO new detection logic, NO new authorization decision,
and NO new evidence format. It assembles and labels what already exists:

  - AccessEvent.evidence_snapshot            (access_authorization_service,
                                               mqtt_service)
  - anomaly_detection_service.detect_anomalies_for_user (Feature #7)
  - emergency_override_service.to_out_dict / active_override_for_door
                                              (Feature #8)
  - audit_service / AuditLog                 (final-hardening-pass)

The one genuinely new piece of state is EventInvestigation (open/under_review
/resolved + a note) — see its docstring in models.py for why it's a
separate, minimal table rather than a second Alert/incident system.

Scope/RBAC follows the EXACT precedent already established in
command_center.py: an unrestricted admin sees everything; a scope-restricted
admin only sees an AccessEvent (and everything correlated to it) if the
event's resolved user is within their authorized college/department, and an
event with no resolved user at all is excluded rather than shown
unattributed. Nothing here is a second authorization system.
"""
from __future__ import annotations

import datetime
import json

from .. import models, security
from . import access_authorization_service, anomaly_detection_service, emergency_override_service

RELATED_WINDOW_MINUTES = 30
TIMELINE_WINDOW_MINUTES = 30
ANOMALY_LOOKBACK_DAYS_FOR_INVESTIGATION = 30

AUDIT_UNAVAILABLE_REASON = (
    "Audit log entries are only visible to an unrestricted admin (same rule as the Audit Log page itself)."
)


def resolve_event_user(db, event: "models.AccessEvent"):
    """Single source of truth for "who does this AccessEvent belong to" —
    promoted from command_center.py's private helper of the same logic so
    the two never drift apart. Direct user_id (schedule_check events) takes
    priority; otherwise falls back to the credential's owner (physical RFID
    events)."""
    if event.user_id:
        return db.get(models.User, event.user_id)
    if event.credential_id:
        cred = db.get(models.Credential, event.credential_id)
        if cred and cred.user_id:
            return db.get(models.User, cred.user_id)
    return None


def can_view_event(db, event: "models.AccessEvent", viewer: "models.User", resolved_user) -> bool:
    """Same predicate Command Center already applies when filtering its
    recent-events list, just evaluated for one specific event instead of a
    list. An unattributed event (no resolved user) can never be proven to
    fall in a restricted admin's scope, so it is excluded — never shown
    unattributed just to fill a page."""
    if viewer.role != "admin":
        return resolved_user is not None and resolved_user.user_id == viewer.user_id
    if not security.is_scope_restricted(viewer, db):
        return True
    if resolved_user is None:
        return False
    return security.is_staff_authorized(resolved_user, viewer, db)


def parse_evidence(event: "models.AccessEvent"):
    """Returns (evidence_dict_or_None, basis_label). Never falls back to
    recomputing a live authorization check to fill in a missing snapshot —
    doing so would silently replace historical evidence with current-state
    data, which is exactly what this feature must not do. A missing
    snapshot is reported as unavailable, not guessed."""
    if not event.evidence_snapshot:
        return None, "unavailable"
    try:
        evidence = json.loads(event.evidence_snapshot)
    except (ValueError, TypeError):
        return None, "unavailable"
    return evidence, "recorded_snapshot"


def _authorization_breakdown(evidence: dict | None) -> dict | None:
    if evidence is None:
        return None
    return {
        "authorized": evidence.get("authorized"),
        "reason": evidence.get("reason"),
        "authorization_source": evidence.get("authorization_source"),
        "has_permanent_access": evidence.get("has_permanent_access"),
        "matched_window": evidence.get("matched_window"),
        "temporary": evidence.get("temporary"),
    }


def _related_override(db, event: "models.AccessEvent"):
    """Best-effort correlation: an EmergencyOverride on the SAME door whose
    [created_at, effective end] span contains this event's timestamp. Never
    invented — returns None if no such row exists. `effective end` uses
    revoked_at when revoked, otherwise expires_at, matching effective_status's
    own notion of when an override actually stopped applying."""
    candidates = (
        db.query(models.EmergencyOverride)
        .filter(models.EmergencyOverride.door_id == event.door_id)
        .all()
    )
    for o in candidates:
        end = o.revoked_at or o.expires_at
        if o.created_at <= event.event_time <= end:
            return o
    return None


def _related_anomalies(db, user, event: "models.AccessEvent") -> list:
    """Real, already-computed anomaly indicators for this event's resolved
    user, filtered down to the ones that reference THIS door — never a
    fresh/invented correlation, purely a re-filter of
    detect_anomalies_for_user's own deterministic output."""
    if user is None:
        return []
    report = anomaly_detection_service.detect_anomalies_for_user(
        db, user, since_days=ANOMALY_LOOKBACK_DAYS_FOR_INVESTIGATION, now=event.event_time + datetime.timedelta(seconds=1)
    )
    return [ind for ind in report["indicators"] if ind["door_id"] == event.door_id]


def _related_audit(db, viewer, event: "models.AccessEvent", door):
    """AuditLog rows referencing this door around the event's time — gated
    on the viewer being an UNRESTRICTED admin, exactly like GET
    /api/audit-logs itself (_require_unrestricted_admin). A scope-restricted
    admin never sees audit rows here that they couldn't see on the Audit Log
    page directly — this view adds no new access to that data."""
    if viewer.role != "admin" or security.is_scope_restricted(viewer, db):
        return [], False, AUDIT_UNAVAILABLE_REASON
    if door is None:
        return [], True, None
    start = event.event_time - datetime.timedelta(minutes=RELATED_WINDOW_MINUTES)
    end = event.event_time + datetime.timedelta(minutes=RELATED_WINDOW_MINUTES)
    rows = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.resource_type == "door", models.AuditLog.resource_id == door.door_id,
                models.AuditLog.timestamp >= start, models.AuditLog.timestamp <= end)
        .order_by(models.AuditLog.timestamp.asc())
        .all()
    )
    return [
        {
            "log_id": r.log_id, "timestamp": r.timestamp, "actor_email": r.actor_email,
            "action": r.action, "result": r.result, "description": r.description,
        }
        for r in rows
    ], True, None


def build_event_detail(db, event: "models.AccessEvent", viewer: "models.User") -> dict:
    door = db.get(models.Door, event.door_id)
    user = resolve_event_user(db, event)
    evidence, basis = parse_evidence(event)

    related_audit, related_audit_available, related_audit_reason = _related_audit(db, viewer, event, door)
    related_override = _related_override(db, event)

    investigation = db.query(models.EventInvestigation).filter(models.EventInvestigation.event_id == event.event_id).first()

    return {
        "event_id": event.event_id,
        "door_id": event.door_id,
        "door_name": door.name if door else None,
        "door_code": door.code if door else None,
        "building": door.building if door else None,
        "event_time": event.event_time,
        "method": event.method,
        "result": event.result,
        "credential_id": event.credential_id,
        "user_id": user.user_id if user else None,
        "user_name": user.name if user else None,
        "physical_door_state": (
            {"available": True, "online": door.online, "locked": door.locked}
            if door else {"available": False}
        ),
        "evidence_available": evidence is not None,
        "evidence_basis": basis,
        "evidence": evidence,
        "authorization": _authorization_breakdown(evidence),
        "related_anomalies": _related_anomalies(db, user, event),
        "related_override": emergency_override_service.to_out_dict(related_override) if related_override else None,
        "related_audit": related_audit,
        "related_audit_available": related_audit_available,
        "related_audit_unavailable_reason": related_audit_reason,
        "investigation": investigation,
    }


def build_timeline(db, event: "models.AccessEvent", viewer: "models.User", window_minutes: int = TIMELINE_WINDOW_MINUTES) -> list:
    """A real chronological timeline built ONLY from persisted records
    within a fixed window around this event, on the SAME door. No
    fabricated correlation: an item only appears here because a real row
    exists with a timestamp inside the window."""
    start = event.event_time - datetime.timedelta(minutes=window_minutes)
    end = event.event_time + datetime.timedelta(minutes=window_minutes)
    items = []

    sibling_events = (
        db.query(models.AccessEvent)
        .filter(models.AccessEvent.door_id == event.door_id,
                models.AccessEvent.event_time >= start, models.AccessEvent.event_time <= end)
        .order_by(models.AccessEvent.event_time.asc())
        .all()
    )
    for e in sibling_events:
        items.append({
            "timestamp": e.event_time, "source": "access_event", "ref_id": e.event_id,
            "is_focus_event": e.event_id == event.event_id,
            "description": f"{e.result.capitalize()} access ({e.method})" + (" — this event" if e.event_id == event.event_id else ""),
        })

    user = resolve_event_user(db, event)
    if user is not None:
        report = anomaly_detection_service.detect_anomalies_for_user(db, user, since_days=ANOMALY_LOOKBACK_DAYS_FOR_INVESTIGATION, now=end)
        for ind in report["indicators"]:
            if ind["door_id"] == event.door_id and start <= ind["triggered_at"] <= end:
                items.append({
                    "timestamp": ind["triggered_at"], "source": "anomaly", "ref_id": None,
                    "is_focus_event": False, "description": f"Anomaly flagged: {ind['explanation']}",
                })

    overrides = db.query(models.EmergencyOverride).filter(models.EmergencyOverride.door_id == event.door_id).all()
    for o in overrides:
        if o.created_at <= end and (o.revoked_at or o.expires_at) >= start:
            if start <= o.created_at <= end:
                items.append({
                    "timestamp": o.created_at, "source": "emergency_override", "ref_id": o.override_id,
                    "is_focus_event": False, "description": f"Emergency {o.action} override activated — \"{o.reason}\"",
                })
            end_ts = o.revoked_at or (o.expires_at if o.status != "ACTIVE" else None)
            if end_ts is not None and start <= end_ts <= end:
                items.append({
                    "timestamp": end_ts, "source": "emergency_override", "ref_id": o.override_id,
                    "is_focus_event": False,
                    "description": "Emergency override revoked" if o.revoked_at == end_ts else "Emergency override expired",
                })

    if viewer.role == "admin" and not security.is_scope_restricted(viewer, db):
        audit_rows = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.resource_type == "door", models.AuditLog.resource_id == event.door_id,
                    models.AuditLog.timestamp >= start, models.AuditLog.timestamp <= end)
            .all()
        )
        for a in audit_rows:
            items.append({
                "timestamp": a.timestamp, "source": "audit_log", "ref_id": a.log_id,
                "is_focus_event": False,
                "description": f"{a.actor_email or 'System'} — {a.action}" + (f" ({a.description})" if a.description else ""),
            })

    items.sort(key=lambda i: i["timestamp"])
    return items


def list_access_events(db, viewer: "models.User", *, since=None, until=None, door_id=None, building=None,
                        result=None, method=None, user_id=None, limit=50, offset=0):
    """Scope-safe listing for the investigation search/filter view (C7).
    Filters are all applied in SQL except the final scope filter (which,
    like Command Center's, needs the resolved user per row and so is
    necessarily a post-fetch pass) and the `building` filter (Door.building
    is a plain string, not a foreign key — see buildings.py — so this is a
    simple string match, not a guessed relationship)."""
    q = db.query(models.AccessEvent)
    if since is not None:
        q = q.filter(models.AccessEvent.event_time >= since)
    if until is not None:
        q = q.filter(models.AccessEvent.event_time <= until)
    if door_id is not None:
        q = q.filter(models.AccessEvent.door_id == door_id)
    if result is not None:
        q = q.filter(models.AccessEvent.result == result)
    if method is not None:
        q = q.filter(models.AccessEvent.method == method)
    if user_id is not None:
        q = q.filter(models.AccessEvent.user_id == user_id)

    restricted = viewer.role == "admin" and security.is_scope_restricted(viewer, db)
    # Scope filtering (and the building string-match) happens post-fetch, so
    # pull a larger raw window than the page size when either is in play —
    # same bounded-scan-then-filter shape Command Center already uses.
    scan_limit = (limit + offset) * 5 if (restricted or building) else (limit + offset)
    scan_limit = min(scan_limit, 2000)

    rows = q.order_by(models.AccessEvent.event_time.desc()).limit(scan_limit).all()

    results = []
    for e in rows:
        door = db.get(models.Door, e.door_id)
        if building is not None and (door is None or door.building != building):
            continue
        user = resolve_event_user(db, e)
        if viewer.role != "admin":
            if user is None or user.user_id != viewer.user_id:
                continue
        elif restricted:
            if user is None or not security.is_staff_authorized(user, viewer, db):
                continue
        if user_id is not None and (user is None or user.user_id != user_id):
            continue
        investigation = db.query(models.EventInvestigation).filter(models.EventInvestigation.event_id == e.event_id).first()
        results.append({
            "event_id": e.event_id, "door_id": e.door_id,
            "door_name": door.name if door else None, "door_code": door.code if door else None,
            "building": door.building if door else None,
            "event_time": e.event_time, "method": e.method, "result": e.result,
            "user_id": user.user_id if user else None, "user_name": user.name if user else None,
            "has_evidence": bool(e.evidence_snapshot),
            "investigation_status": investigation.status if investigation else None,
        })

    return results[offset:offset + limit], len(results)


# ---------------------------------------------------------------------------
# Stage D / D8 — Failed automation -> Investigation linkage.
#
# AutomationLog rows are zone/device-level, not access-event-level, so there
# is no direct foreign key from an automation decision to an AccessEvent or
# an EventInvestigation — inventing one would be exactly the kind of
# artificial correlation the brief forbids. What DOES exist as a real,
# already-persisted relationship: AutomationLog.zone_id -> Zone.door_id (only
# when an admin explicitly linked that zone to a physical door) -> the same
# AccessEvent/Alert rows already surfced elsewhere for that door/zone. This
# function assembles exactly that chain and nothing more; a zone with no
# linked door reports door_available=False with an explicit reason rather
# than silently returning an empty list that could be misread as "no
# activity."
# ---------------------------------------------------------------------------
def build_automation_log_related(db, log: "models.AutomationLog") -> dict:
    zone = db.get(models.Zone, log.zone_id) if log.zone_id else None
    door = db.get(models.Door, zone.door_id) if (zone and zone.door_id) else None

    alerts = []
    if log.zone_id is not None:
        alerts = (
            db.query(models.Alert)
            .filter(models.Alert.zone_id == log.zone_id)
            .order_by(models.Alert.alert_time.desc())
            .limit(10)
            .all()
        )

    related_events = []
    door_available = door is not None
    reason = None
    if door is None:
        reason = (
            "This zone has no linked physical door, so it cannot be correlated "
            "to any access event." if zone is not None else
            "This automation decision has no zone (a building-wide sweep), so it cannot be correlated to a door."
        )
    else:
        window_start = log.created_at - datetime.timedelta(minutes=RELATED_WINDOW_MINUTES)
        window_end = log.created_at + datetime.timedelta(minutes=RELATED_WINDOW_MINUTES)
        events = (
            db.query(models.AccessEvent)
            .filter(models.AccessEvent.door_id == door.door_id,
                    models.AccessEvent.event_time >= window_start,
                    models.AccessEvent.event_time <= window_end)
            .order_by(models.AccessEvent.event_time.desc())
            .limit(10)
            .all()
        )
        for e in events:
            user = resolve_event_user(db, e)
            related_events.append({
                "event_id": e.event_id, "event_time": e.event_time, "method": e.method, "result": e.result,
                "user_id": user.user_id if user else None, "user_name": user.name if user else None,
            })

    return {
        "log_id": log.log_id,
        "zone_id": zone.zone_id if zone else None,
        "zone_name": zone.name if zone else None,
        "door_id": door.door_id if door else None,
        "door_name": door.name if door else None,
        "door_available": door_available,
        "door_unavailable_reason": reason,
        "alerts": alerts,
        "related_access_events": related_events,
    }
