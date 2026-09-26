"""
Feature #8 — Emergency Access / Override API.

Endpoints:
  GET   /api/doors/{door_id}/emergency-override        — current/active override for a door (admin-only)
  POST  /api/doors/{door_id}/emergency-override         — create a new emergency override (admin-only, scope-checked)
  POST  /api/emergency-overrides/{id}/revoke            — cancel an active override early (admin-only)
  GET   /api/emergency-overrides                        — recent overrides, for audit review (admin-only)

Authorization reuses the EXISTING AdminScope/OperationalScope system (via
security.require_operational_scope_access, applied inside
emergency_override_service._authorize_scope) — this is not a second RBAC
system. Door lock/unlock stays admin-only, matching the existing plain
override endpoint's own authorization level (routers/doors.py::override_door);
Feature #8 adds the missing reason/expiry/audit/scope-declaration layer on
top of that same admin-only gate, it does not loosen it.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import emergency_override_service, audit_service

router = APIRouter(tags=["emergency-overrides"])


@router.get("/api/doors/{door_id}/emergency-override", response_model=Optional[schemas.EmergencyOverrideOut])
def get_active_emergency_override(door_id: int, db: Session = Depends(get_db),
                                   admin=Depends(security.require_admin)):
    door = db.get(models.Door, door_id)
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    override = emergency_override_service.active_override_for_door(db, door_id)
    if override is None:
        return None
    return emergency_override_service.to_out_dict(override)


@router.post("/api/doors/{door_id}/emergency-override", response_model=schemas.EmergencyOverrideOut, status_code=201)
def create_emergency_override(door_id: int, payload: schemas.EmergencyOverrideCreate, db: Session = Depends(get_db),
                               admin=Depends(security.require_admin)):
    if payload.door_id != door_id:
        raise HTTPException(status_code=400, detail="door_id in the URL and body must match")
    door = db.get(models.Door, door_id)
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")

    override = emergency_override_service.create_override(
        db, door=door, admin=admin, action=payload.action, reason=payload.reason,
        duration_minutes=payload.duration_minutes, operational_scope_id=payload.operational_scope_id,
    )
    audit_service.log(db, actor=admin, action=f"emergency_override_{payload.action}",
                       resource_type="emergency_override", resource_id=override.override_id,
                       resource_label=f"{door.name} ({door.code})", description=payload.reason)
    return emergency_override_service.to_out_dict(override)


@router.post("/api/emergency-overrides/{override_id}/revoke", response_model=schemas.EmergencyOverrideOut)
def revoke_emergency_override(override_id: int, payload: schemas.EmergencyOverrideRevoke = schemas.EmergencyOverrideRevoke(),
                               db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    override = db.get(models.EmergencyOverride, override_id)
    if not override:
        raise HTTPException(status_code=404, detail="Emergency override not found")
    # A scope-restricted admin may only revoke overrides within their own
    # authorized operational scope — same reasoning as creation: reuses the
    # existing scope-check helper rather than a bespoke rule.
    if security.is_scope_restricted(admin, db):
        if override.operational_scope_id is None:
            raise HTTPException(status_code=403, detail="You aren't authorized to revoke this override")
        security.require_operational_scope_access(override.operational_scope_id, admin, db)

    override = emergency_override_service.revoke_override(db, override=override, admin=admin, note=payload.note)
    audit_service.log(db, actor=admin, action="emergency_override_revoke",
                       resource_type="emergency_override", resource_id=override.override_id,
                       resource_label=f"{override.door.name} ({override.door.code})", description=payload.note)
    return emergency_override_service.to_out_dict(override)


@router.get("/api/emergency-overrides", response_model=List[schemas.EmergencyOverrideOut])
def list_emergency_overrides(door_id: Optional[int] = None, limit: int = 100,
                              db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    q = db.query(models.EmergencyOverride)
    if door_id is not None:
        q = q.filter(models.EmergencyOverride.door_id == door_id)
    if security.is_scope_restricted(admin, db):
        allowed = security.authorized_operational_scope_ids(admin, db)
        q = q.filter(models.EmergencyOverride.operational_scope_id.in_(allowed or set()))
    rows = q.order_by(models.EmergencyOverride.created_at.desc()).limit(limit).all()
    return [emergency_override_service.to_out_dict(r) for r in rows]
