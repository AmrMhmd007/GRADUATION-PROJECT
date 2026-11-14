"""Device identity registry (admin only) and device-security event feed.

Phase 1B. Manages per-device MQTT identities - NOT user accounts and NOT the
door-node X-Node-Key. Secrets are returned exactly once (create / rotate) and
are never readable again. Only unrestricted admins may manage identities,
because a device scope can span zones outside any one admin's faculty scope.
"""
import datetime
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, security
from ..database import get_db
from ..services import audit_service, device_auth_service

router = APIRouter(prefix="/api", tags=["device-trust"])


class ScopeIn(BaseModel):
    message_types: List[str] = Field(default_factory=list)
    zone_ids: List[int] = Field(default_factory=list)
    door_codes: List[str] = Field(default_factory=list)


class IdentityCreate(ScopeIn):
    device_id: str
    name: Optional[str] = None
    node_id: Optional[str] = None


class RevokeIn(BaseModel):
    reason: Optional[str] = None


class IdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    identity_id: int
    device_id: str
    name: Optional[str] = None
    node_id: Optional[str] = None
    status: str
    secret_version: int
    message_types: List[str]
    zone_ids: List[int]
    door_codes: List[str]
    created_at: Optional[datetime.datetime] = None
    secret_rotated_at: Optional[datetime.datetime] = None
    revoked_at: Optional[datetime.datetime] = None
    revoke_reason: Optional[str] = None
    last_seen_at: Optional[datetime.datetime] = None
    last_authenticated_at: Optional[datetime.datetime] = None


class IdentityWithSecret(IdentityOut):
    secret: str                       # shown ONCE
    secret_note: str = "Store this secret now; it cannot be shown again."


def _out(row: models.DeviceIdentity) -> dict:
    return {
        "identity_id": row.identity_id, "device_id": row.device_id, "name": row.name, "node_id": row.node_id,
        "status": row.status, "secret_version": row.secret_version,
        "message_types": json.loads(row.allowed_message_types or "[]"),
        "zone_ids": json.loads(row.allowed_zone_ids or "[]"),
        "door_codes": json.loads(row.allowed_door_codes or "[]"),
        "created_at": row.created_at, "secret_rotated_at": row.secret_rotated_at,
        "revoked_at": row.revoked_at, "revoke_reason": row.revoke_reason,
        "last_seen_at": row.last_seen_at, "last_authenticated_at": row.last_authenticated_at,
    }


def _get(db, device_id: str) -> models.DeviceIdentity:
    row = db.query(models.DeviceIdentity).filter(models.DeviceIdentity.device_id == device_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Device identity not found")
    return row


@router.post("/device-identities", response_model=IdentityWithSecret, status_code=201)
def create_identity(payload: IdentityCreate, db: Session = Depends(get_db),
                    admin: models.User = Depends(security.require_unrestricted_admin)):
    try:
        row, secret = device_auth_service.create_identity(
            db, device_id=payload.device_id, name=payload.name, node_id=payload.node_id,
            message_types=payload.message_types, zone_ids=payload.zone_ids,
            door_codes=payload.door_codes, actor=admin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit_service.log(db, admin, "device_identity_create", "device_identity", resource_id=row.identity_id,
                      resource_label=row.device_id, description=f"Registered device identity {row.device_id}")
    db.commit()
    return {**_out(row), "secret": secret}


@router.get("/device-identities", response_model=List[IdentityOut])
def list_identities(db: Session = Depends(get_db), admin: models.User = Depends(security.require_unrestricted_admin)):
    rows = db.query(models.DeviceIdentity).order_by(models.DeviceIdentity.device_id).all()
    return [_out(r) for r in rows]


@router.get("/device-identities/{device_id}", response_model=IdentityOut)
def get_identity(device_id: str, db: Session = Depends(get_db),
                 admin: models.User = Depends(security.require_unrestricted_admin)):
    return _out(_get(db, device_id))


@router.put("/device-identities/{device_id}/scope", response_model=IdentityOut)
def update_scope(device_id: str, payload: ScopeIn, db: Session = Depends(get_db),
                 admin: models.User = Depends(security.require_unrestricted_admin)):
    row = _get(db, device_id)
    if row.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Revoked identities cannot be modified")
    try:
        device_auth_service.update_scope(db, row, message_types=payload.message_types,
                                         zone_ids=payload.zone_ids, door_codes=payload.door_codes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit_service.log(db, admin, "device_identity_scope_update", "device_identity", resource_id=row.identity_id,
                      resource_label=row.device_id, description=f"Changed scope of device identity {row.device_id}")
    db.commit()
    return _out(row)


@router.post("/device-identities/{device_id}/rotate-secret", response_model=IdentityWithSecret)
def rotate(device_id: str, db: Session = Depends(get_db),
           admin: models.User = Depends(security.require_unrestricted_admin)):
    row = _get(db, device_id)
    try:
        secret = device_auth_service.rotate_secret(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    audit_service.log(db, admin, "device_identity_rotate", "device_identity", resource_id=row.identity_id,
                      resource_label=row.device_id, description=f"Rotated secret of {row.device_id}")
    db.commit()
    return {**_out(row), "secret": secret}


@router.post("/device-identities/{device_id}/revoke", response_model=IdentityOut)
def revoke(device_id: str, payload: RevokeIn, db: Session = Depends(get_db),
           admin: models.User = Depends(security.require_unrestricted_admin)):
    row = _get(db, device_id)
    if not device_auth_service.revoke(db, row, actor=admin, reason=payload.reason):
        raise HTTPException(status_code=409, detail="Already revoked")
    audit_service.log(db, admin, "device_identity_revoke", "device_identity", resource_id=row.identity_id,
                      resource_label=row.device_id, description=f"Revoked device identity {row.device_id}")
    db.commit()
    return _out(row)


@router.get("/device-security/events")
def list_events(event_type: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                db: Session = Depends(get_db), admin: models.User = Depends(security.require_unrestricted_admin)):
    q = db.query(models.DeviceSecurityEvent)
    if event_type:
        q = q.filter(models.DeviceSecurityEvent.event_type == event_type)
    rows = q.order_by(models.DeviceSecurityEvent.event_id.desc()).limit(limit).all()
    return [{"event_id": e.event_id, "occurred_at": e.occurred_at, "event_type": e.event_type,
             "severity": e.severity, "claimed_device_id": e.claimed_device_id, "identity_id": e.identity_id,
             "topic": e.topic, "zone_id": e.zone_id, "enforcement_mode": e.enforcement_mode,
             "action_taken": e.action_taken, "detail": e.detail, "suppressed_count": e.suppressed_count}
            for e in rows]


@router.get("/device-security/summary")
def summary(db: Session = Depends(get_db), admin: models.User = Depends(security.require_unrestricted_admin)):
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    counts = (db.query(models.DeviceSecurityEvent.event_type, func.count(models.DeviceSecurityEvent.event_id))
              .filter(models.DeviceSecurityEvent.occurred_at >= since)
              .group_by(models.DeviceSecurityEvent.event_type).all())
    ids = db.query(models.DeviceIdentity.status, func.count(models.DeviceIdentity.identity_id)).group_by(
        models.DeviceIdentity.status).all()
    return {
        "mode": device_auth_service.effective_mode(),
        "note": ("warn: messages are verified and findings recorded, but nothing is blocked"
                 if device_auth_service.effective_mode() == "warn" else None),
        "events_last_24h": {t: c for t, c in counts},
        "identities": {s: c for s, c in ids},
    }
