"""
Phase 6 — Command Center summary API.

One aggregation endpoint over data that ALREADY exists — this file invents
no telemetry, no mock activity, and no second authorization/detection
pathway. It simply assembles, in one round trip, what the Command Center UI
needs to show the People -> Places -> Access -> Physical Events ->
Anomalies -> Emergency Actions story:

  - door/system status                (Door table, as-is)
  - recent physical access events     (AccessEvent, as-is)
  - active anomaly indicators         (anomaly_detection_service, reused)
  - active emergency overrides        (emergency_override_service, reused)
  - unresolved alerts                 (Alert table, as-is)

Admin-only, matching every other cross-door aggregate endpoint in this
codebase (doors.py, anomalies.py's door-anomalies endpoint).

---------------------------------------------------------------------------
Security hardening pass — Command Center scope isolation
---------------------------------------------------------------------------
An UNRESTRICTED admin (zero AdminScope rows — today's default) sees
everything below, exactly as before.

A scope-RESTRICTED admin must only see data this endpoint can PROVE falls
within their authorized scope, using the EXISTING AdminScope/security
helpers — no second authorization system, no new Door->scope hierarchy.
The mapping was worked out per-entity from what actually has an
authoritative relationship today:

  - Recent access events   -> scoped via the event's own resolved user's
                               faculty_id/department_id (User.faculty_id/
                               department_id is the SAME authoritative
                               relationship security.require_staff_access
                               already enforces for staff profiles/access
                               windows). An event with no resolved user
                               (an RFID swipe whose credential never
                               matched anyone) cannot be attributed to any
                               scope and is EXCLUDED for a restricted
                               admin — never shown just to fill the list.

  - Anomaly indicators     -> same relationship: every indicator already
                               belongs to one User (that's what
                               detect_anomalies_for_user computes), so it's
                               scoped exactly like a recent event above.

  - Emergency overrides    -> scoped via EmergencyOverride.operational_
                               scope_id, which Feature #8 already requires
                               a restricted admin to declare (and checks
                               with security.require_operational_scope_
                               access) at CREATION time. An override with
                               operational_scope_id left NULL (created by
                               an unrestricted admin, no scope declared) is
                               EXCLUDED for a restricted admin — it cannot
                               be proven to fall in their scope, so it is
                               never shown to them.

  - Doors / door_status    -> Door has NO authoritative relationship to
                               Faculty/Department/OperationalScope at all:
                               Door.building is a plain string kept only
                               for backward compatibility (see Building's
                               own docstring in models.py) — not a foreign
                               key to Building, let alone to any scope.
                               Matching by that string would be exactly
                               the kind of guess this hardening pass was
                               told not to make. So for a restricted admin,
                               door_status is returned with
                               `"available": False` and an explanation,
                               never a filtered-looking (but actually
                               fabricated) count.

  - Alerts                 -> same reasoning as doors (every alert here is
                               door-anchored) — `"available": False` for a
                               restricted admin rather than a guessed
                               filter.

This is a real, load-bearing limitation, not a cosmetic one: until Door
gains its own authoritative scope relationship, a restricted admin's
Command Center will always be missing the doors/alerts sections. Widening
that "just to make the dashboard look complete" was explicitly the thing
NOT to do.
"""
import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, security
from ..database import get_db
from ..services import anomaly_detection_service, emergency_override_service, investigation_service

router = APIRouter(prefix="/api/command-center", tags=["command-center"])

# How far back "recent" reaches for the Command Center's own event/anomaly
# feeds — deliberately short (this is an at-a-glance operational view, not
# an audit report; Feature #7's /api/staff/{id}/anomalies and
# /api/doors/{id}/anomalies remain the full-history, longer-lookback tools).
RECENT_EVENTS_LIMIT = 25
# A restricted admin's events are filtered AFTER fetching, so more rows are
# pulled than will necessarily be kept — this caps that raw fetch.
RECENT_EVENTS_SCAN_LIMIT = 300
ANOMALY_LOOKBACK_DAYS = 7
ANOMALY_SCAN_USER_CAP = 40  # safety cap on how many distinct users get a full anomaly re-scan per request
ANOMALY_RESULT_LIMIT = 15

DOORS_UNAVAILABLE_REASON = (
    "Doors have no organizational/operational scope mapping yet, so door status "
    "cannot be safely restricted to your authorized scope — ask an unrestricted "
    "admin, or use Main Doors/Access Service directly."
)
ALERTS_UNAVAILABLE_REASON = (
    "Alerts are door-anchored and doors have no scope mapping yet, so they "
    "cannot be safely restricted to your authorized scope."
)


# Promoted to investigation_service.resolve_event_user (Stage C) so this
# exact logic has one implementation, not two that could drift apart.
_resolve_event_user = investigation_service.resolve_event_user


def _event_row(db: Session, e: "models.AccessEvent", user: "models.User | None") -> dict:
    door = db.get(models.Door, e.door_id)
    # Stage E-hardening: reuses the exact same EventInvestigation lookup
    # investigation_service already does for the dedicated Access Events
    # page — no new investigation concept, just surfacing the existing
    # status on the row Command Center already builds, so "Security" can
    # show at a glance how many of these recent events are under review.
    investigation = db.query(models.EventInvestigation).filter(models.EventInvestigation.event_id == e.event_id).first()
    return {
        "event_id": e.event_id,
        "event_time": e.event_time,
        "door_id": e.door_id,
        "door_name": door.name if door else None,
        "door_code": door.code if door else None,
        "method": e.method,
        "result": e.result,
        "user_id": e.user_id,
        "user_name": user.name if user else None,
        "investigation_status": investigation.status if investigation else None,
    }


@router.get("/summary")
def command_center_summary(db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    now = datetime.datetime.utcnow()
    restricted = security.is_scope_restricted(admin, db)
    allowed_operational_scope_ids = security.authorized_operational_scope_ids(admin, db) if restricted else None

    # ---- Door / system status ----
    # See module docstring: Door has no authoritative scope relationship, so
    # this section is only computed for an UNRESTRICTED admin.
    if not restricted:
        doors = db.query(models.Door).all()
        door_status = {
            "available": True,
            "total": len(doors),
            "online": sum(1 for d in doors if d.online),
            "offline": sum(1 for d in doors if not d.online),
            "locked": sum(1 for d in doors if d.locked),
            "unlocked": sum(1 for d in doors if not d.locked),
            "critical": sum(1 for d in doors if d.category == "critical"),
            "rooms": sum(1 for d in doors if d.category == "access_service"),
        }
    else:
        door_status = {"available": False, "reason": DOORS_UNAVAILABLE_REASON}

    # ---- Recent physical/authorization access events ----
    # For a restricted admin, only an event whose resolved user is within
    # their authorized college/department is kept — an unresolved event
    # (no matching credential) is dropped rather than shown unattributed.
    scan_limit = RECENT_EVENTS_SCAN_LIMIT if restricted else RECENT_EVENTS_LIMIT
    raw_events = (
        db.query(models.AccessEvent)
        .order_by(models.AccessEvent.event_time.desc())
        .limit(scan_limit)
        .all()
    )
    recent_events = []
    for e in raw_events:
        user = _resolve_event_user(db, e)
        if restricted and (user is None or not security.is_staff_authorized(user, admin, db)):
            continue
        recent_events.append(_event_row(db, e, user))
        if len(recent_events) >= RECENT_EVENTS_LIMIT:
            break

    # ---- Active emergency overrides (Feature #8) ----
    override_query = db.query(models.EmergencyOverride).filter(models.EmergencyOverride.status == "ACTIVE")
    if restricted:
        # An override with no operational_scope_id was created by an
        # unrestricted admin with nothing declared — it can't be proven to
        # fall in this admin's scope, so it's excluded rather than shown.
        override_query = override_query.filter(
            models.EmergencyOverride.operational_scope_id.in_(allowed_operational_scope_ids or set())
        )
    active_override_rows = override_query.order_by(models.EmergencyOverride.created_at.desc()).all()
    active_overrides = [
        emergency_override_service.to_out_dict(o, now=now)
        for o in active_override_rows
        if emergency_override_service.effective_status(o, now=now) == "ACTIVE"
    ]

    # ---- Active anomaly indicators (Feature #7, evidence-hardened) ----
    # Scanned over whoever actually generated an access event recently —
    # never a random/synthetic population, and capped so this endpoint
    # can't be made to do unbounded work by event volume alone. For a
    # restricted admin, the candidate user pool itself is pre-filtered to
    # their authorized staff, so an anomaly belonging to another college's
    # staff member is never even evaluated for this request, let alone
    # returned.
    since = now - datetime.timedelta(days=ANOMALY_LOOKBACK_DAYS)
    recent_user_ids: set[int] = set()
    for e in db.query(models.AccessEvent).filter(models.AccessEvent.event_time >= since).all():
        u = _resolve_event_user(db, e)
        if u is None:
            continue
        if restricted and not security.is_staff_authorized(u, admin, db):
            continue
        recent_user_ids.add(u.user_id)

    anomaly_indicators = []
    for uid in list(recent_user_ids)[:ANOMALY_SCAN_USER_CAP]:
        user = db.get(models.User, uid)
        if not user:
            continue
        report = anomaly_detection_service.detect_anomalies_for_user(db, user, since_days=ANOMALY_LOOKBACK_DAYS, now=now)
        for ind in report["indicators"]:
            if ind["severity"] == anomaly_detection_service.SEVERITY_UNUSUAL:
                continue  # command center surfaces ANOMALOUS/ELEVATED only — UNUSUAL stays in the full staff/door reports
            anomaly_indicators.append({**ind, "user_id": uid, "user_name": user.name})
    anomaly_indicators.sort(key=lambda i: i["triggered_at"], reverse=True)
    anomaly_indicators = anomaly_indicators[:ANOMALY_RESULT_LIMIT]

    # ---- Unresolved alerts ----
    # Same reasoning as doors: every alert here is door-anchored, and doors
    # have no scope mapping, so this section is unrestricted-admin-only too.
    if not restricted:
        unresolved_alerts = (
            db.query(models.Alert)
            .filter(models.Alert.resolved == False)  # noqa: E712
            .order_by(models.Alert.alert_id.desc())
            .all()
        )
        alerts_out = {"available": True, "items": []}
        for a in unresolved_alerts:
            door = db.get(models.Door, a.door_id) if a.door_id else None
            alerts_out["items"].append({
                "alert_id": a.alert_id, "door_id": a.door_id, "door_name": door.name if door else None,
                "type": a.type, "severity": a.severity, "alert_time": a.alert_time, "resolved": a.resolved,
            })
    else:
        alerts_out = {"available": False, "reason": ALERTS_UNAVAILABLE_REASON, "items": []}

    return {
        "evaluated_at": now,
        "scope": {"restricted": restricted},
        "door_status": door_status,
        "recent_events": recent_events,
        "active_overrides": active_overrides,
        "anomaly_indicators": anomaly_indicators,
        "alerts": alerts_out,
    }
