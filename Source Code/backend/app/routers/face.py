"""Face ID enrollment (self-service) and door-node verification endpoints.

Templates are never serialized: every response here carries metadata only.
Door-node endpoints are authenticated by the shared X-Node-Key and are
DISABLED (403) when FACE_NODE_API_KEY is unset - never open by default.
"""
import hmac
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from .. import models, security
from ..config import settings
from ..database import get_db
from ..services import face_service, hardware_health_service

router = APIRouter(prefix="/api/face", tags=["face-id"])


class FaceStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    status: str  # NOT_ENROLLED | ENROLLED | REVOKED | DISABLED
    enrolled_at: Optional[str] = None
    model_version: Optional[str] = None
    quality_score: Optional[float] = None
    liveness_passed: Optional[bool] = None
    source: Optional[str] = None


class FaceStaffRow(FaceStatusOut):
    name: str
    email: str
    role: str


class EnrollIn(BaseModel):
    embedding: List[float]
    quality: float
    liveness_passed: Optional[bool] = None
    model_version: Optional[str] = None
    source: str = "REAL"  # REAL | SIMULATED (tests / dev adapters must say so)


class RevokeIn(BaseModel):
    reason: Optional[str] = None


class NodeVerifyIn(BaseModel):
    door_code: str
    node_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    quality: Optional[float] = None
    liveness_passed: Optional[bool] = None
    node_status: str = "ok"  # ok | camera_error | verifier_error | degraded


class NodeAckIn(BaseModel):
    door_code: str
    event_id: int
    unlocked: bool


def _status(db, user_id) -> dict:
    d = face_service.face_status(db, user_id)
    if d["enrolled_at"] is not None:
        d["enrolled_at"] = d["enrolled_at"].isoformat()
    return d


def require_node_key(x_node_key: Optional[str] = Header(default=None)):
    expected = settings.FACE_NODE_API_KEY
    if not expected or not x_node_key or not hmac.compare_digest(expected, x_node_key):
        raise HTTPException(status_code=403, detail="Door node authentication failed")


@router.get("/capabilities")
def capabilities(_user=Depends(security.get_current_user)):
    provider = settings.FACE_EMBEDDING_PROVIDER
    return {
        "embedding_provider": provider,
        "capture_available": provider != "none",
        "capture_status": "AVAILABLE" if provider != "none" else "UNAVAILABLE",
        "note": ("Face capture needs an embedding adapter on an enrollment device (e.g. the door Raspberry Pi). "
                 "None is configured on this server." if provider == "none" else "Embedding adapter configured."),
        "node_api_enabled": bool(settings.FACE_NODE_API_KEY),
        "liveness_required": settings.FACE_REQUIRE_LIVENESS,
    }


@router.get("/me", response_model=FaceStatusOut)
def my_status(user=Depends(security.get_current_user), db: Session = Depends(get_db)):
    return _status(db, user.user_id)


@router.post("/me/enroll", response_model=FaceStatusOut, status_code=201)
def enroll_me(payload: EnrollIn, user=Depends(security.get_current_user), db: Session = Depends(get_db)):
    if payload.source not in ("REAL", "SIMULATED"):
        raise HTTPException(status_code=400, detail="source must be REAL or SIMULATED")
    try:
        face_service.enroll(db, user, embedding=payload.embedding, quality=payload.quality,
                            liveness_passed=payload.liveness_passed, model_version=payload.model_version,
                            source=payload.source, actor=user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _status(db, user.user_id)


@router.post("/me/revoke", response_model=FaceStatusOut)
def revoke_me(payload: RevokeIn, user=Depends(security.get_current_user), db: Session = Depends(get_db)):
    if not face_service.revoke(db, user, actor=user, reason=payload.reason or "self-revoked"):
        raise HTTPException(status_code=404, detail="No active Face ID")
    db.commit()
    return _status(db, user.user_id)


@router.get("/users", response_model=List[FaceStaffRow])
def list_staff(db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    """Enrollment STATUS only for staff the admin is scoped to - no templates,
    no quality vectors beyond the summary score."""
    staff = db.query(models.User).filter(models.User.role.in_(["doctor", "instructor"])).order_by(models.User.name).all()
    rows = []
    for u in staff:
        if not security.is_staff_authorized(u, admin, db):
            continue
        rows.append({**_status(db, u.user_id), "name": u.name, "email": u.email, "role": u.role})
    return rows


def _target(db, user_id, admin):
    u = db.get(models.User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    security.require_staff_access(u, admin, db)
    return u


@router.post("/users/{user_id}/revoke", response_model=FaceStatusOut)
def revoke_user(user_id: int, payload: RevokeIn, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    u = _target(db, user_id, admin)
    if not face_service.revoke(db, u, actor=admin, reason=payload.reason):
        raise HTTPException(status_code=404, detail="No active Face ID")
    db.commit()
    return _status(db, u.user_id)


@router.post("/users/{user_id}/disable", response_model=FaceStatusOut)
def disable_user(user_id: int, payload: RevokeIn, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    u = _target(db, user_id, admin)
    if not face_service.revoke(db, u, actor=admin, reason=payload.reason, disable_only=True):
        raise HTTPException(status_code=404, detail="No active Face ID")
    db.commit()
    return _status(db, u.user_id)


# ---------------------------------------------------------------- door node
@router.post("/node/verify", dependencies=[Depends(require_node_key)])
def node_verify(payload: NodeVerifyIn, db: Session = Depends(get_db)):
    door = db.query(models.Door).filter(models.Door.code == payload.door_code).first()
    if door is None:
        raise HTTPException(status_code=404, detail="Unknown door")
    result = process_verification(db, door, payload.model_dump())
    return result


def process_verification(db, door, data: dict) -> dict:
    """Shared by the HTTP endpoint and the MQTT handler so both paths run the
    exact same backend authorization."""
    node_id = data.get("node_id") or f"face-door-{door.code}"
    node_status = data.get("node_status") or "ok"
    hardware_health_service.record_heartbeat(
        db, node_id=node_id,
        payload={"sensor_healthy": node_status == "ok", "error_state": None if node_status == "ok" else node_status},
        zone_id=_zone_id_for_door(db, door))
    return face_service.decide(db, door, embedding=data.get("embedding"), quality=data.get("quality"),
                               liveness_passed=data.get("liveness_passed"), node_status=node_status,
                               node_id=node_id)


def _zone_id_for_door(db, door):
    z = db.query(models.Zone).filter(models.Zone.door_id == door.door_id).first()
    return z.zone_id if z else None


@router.post("/node/ack", dependencies=[Depends(require_node_key)])
def node_ack(payload: NodeAckIn, db: Session = Depends(get_db)):
    door = db.query(models.Door).filter(models.Door.code == payload.door_code).first()
    if door is None:
        raise HTTPException(status_code=404, detail="Unknown door")
    if not face_service.confirm_physical(db, door, payload.event_id, payload.unlocked):
        raise HTTPException(status_code=409, detail="Event not found, not a face event, or already confirmed")
    return {"ok": True}
