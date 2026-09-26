"""
Stage C — Investigation & Evidence API.

  GET  /api/access-events                          — filtered/paginated list (search/filter, C7)
  GET  /api/access-events/{event_id}                — full investigation detail (C2/C4/C5/C8)
  GET  /api/access-events/{event_id}/timeline        — correlated real-record timeline (C3)
  PUT  /api/access-events/{event_id}/investigation   — set status/note (the only new persistent state, C6)
  GET  /api/emergency-overrides/{override_id}/related-events — reverse direction of the override->events link (C1/C8)

RBAC reuses the exact scope model already established by Command Center
(security.is_scope_restricted / is_staff_authorized) and by the existing
Emergency Override endpoints (security.require_operational_scope_access) —
no parallel authorization system. Viewing is open to any authenticated user
but scope-limited to their own data (non-admin) or their authorized
college/department (scoped admin); mutating investigation status is
admin-only and audited.
"""
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service, investigation_service

router = APIRouter(tags=["investigations"])

VALID_STATUSES = ("open", "under_review", "resolved")


def _get_event_or_404(db: Session, event_id: int) -> "models.AccessEvent":
    event = db.get(models.AccessEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Access event not found")
    return event


def _authorize_event_view(db: Session, event: "models.AccessEvent", viewer: "models.User") -> None:
    resolved_user = investigation_service.resolve_event_user(db, event)
    if not investigation_service.can_view_event(db, event, viewer, resolved_user):
        raise HTTPException(status_code=403, detail="You aren't authorized to view this access event")


@router.get("/api/access-events", response_model=List[schemas.AccessEventListItemOut])
def list_access_events(
    since: Optional[datetime.datetime] = None,
    until: Optional[datetime.datetime] = None,
    door_id: Optional[int] = None,
    building: Optional[str] = None,
    result: Optional[str] = None,
    method: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user=Depends(security.get_current_user),
):
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must not be negative")
    if result is not None and result not in ("granted", "denied"):
        raise HTTPException(status_code=422, detail="result must be 'granted' or 'denied'")

    rows, _total = investigation_service.list_access_events(
        db, user, since=since, until=until, door_id=door_id, building=building,
        result=result, method=method, user_id=user_id, limit=limit, offset=offset,
    )
    return rows


@router.get("/api/access-events/{event_id}", response_model=schemas.AccessEventDetailOut)
def get_access_event_detail(event_id: int, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    event = _get_event_or_404(db, event_id)
    _authorize_event_view(db, event, user)
    return investigation_service.build_event_detail(db, event, user)


@router.get("/api/access-events/{event_id}/timeline", response_model=List[schemas.TimelineItemOut])
def get_access_event_timeline(event_id: int, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    event = _get_event_or_404(db, event_id)
    _authorize_event_view(db, event, user)
    return investigation_service.build_timeline(db, event, user)


@router.put("/api/access-events/{event_id}/investigation", response_model=schemas.EventInvestigationOut)
def update_event_investigation(
    event_id: int, payload: schemas.EventInvestigationUpdate,
    db: Session = Depends(get_db), admin=Depends(security.require_admin),
):
    """Changing investigation status/note is the only mutation this feature
    introduces — admin-only, scope-checked exactly like viewing, and always
    audited (unlike the read-only GETs above, which intentionally create no
    audit noise)."""
    event = _get_event_or_404(db, event_id)
    _authorize_event_view(db, event, admin)

    if payload.status is not None and payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {VALID_STATUSES}")
    if payload.status is None and payload.note is None:
        raise HTTPException(status_code=422, detail="Provide at least one of status or note")

    investigation = db.query(models.EventInvestigation).filter(models.EventInvestigation.event_id == event_id).first()
    is_new = investigation is None
    if investigation is None:
        investigation = models.EventInvestigation(event_id=event_id, status="open")
        db.add(investigation)

    if payload.status is not None:
        investigation.status = payload.status
    if payload.note is not None:
        investigation.note = payload.note
    investigation.updated_by_id = admin.user_id
    investigation.updated_at = datetime.datetime.utcnow()

    db.commit()
    db.refresh(investigation)

    audit_service.log(
        db, actor=admin,
        action="create" if is_new else "update",
        resource_type="event_investigation", resource_id=event_id,
        resource_label=f"Access event #{event_id}",
        description=f"status={investigation.status}" + (f", note updated" if payload.note is not None else ""),
    )
    return investigation


@router.get("/api/emergency-overrides/{override_id}/related-events", response_model=List[schemas.AccessEventListItemOut])
def get_related_events_for_override(override_id: int, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    override = db.get(models.EmergencyOverride, override_id)
    if not override:
        raise HTTPException(status_code=404, detail="Emergency override not found")
    # Same scope check list_emergency_overrides already applies.
    if security.is_scope_restricted(admin, db):
        if override.operational_scope_id is None:
            raise HTTPException(status_code=403, detail="You aren't authorized to view this override")
        security.require_operational_scope_access(override.operational_scope_id, admin, db)

    end = override.revoked_at or override.expires_at
    rows, _total = investigation_service.list_access_events(
        db, admin, since=override.created_at, until=end, door_id=override.door_id, limit=200, offset=0,
    )
    return rows


@router.get("/api/automation/logs/{log_id}/related", response_model=schemas.AutomationLogRelatedOut)
def get_automation_log_related(log_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    """Stage D / D8 — 'Automation Failure -> Device -> Room -> Related Access
    Events/Alerts' navigation. Automation itself is admin-only everywhere
    else in this codebase (zones/devices/rules all require_admin, with no
    scope mapping — see routers/zones.py), so this mirrors that exact
    authorization level rather than inventing a scoped view for a resource
    type that has never had one."""
    log = db.get(models.AutomationLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Automation log entry not found")
    return investigation_service.build_automation_log_related(db, log)
