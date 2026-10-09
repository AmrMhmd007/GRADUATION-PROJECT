"""Device fault alerts: node telemetry ingest, doctor (own rooms) and admin views."""
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, security
from ..config import settings
from ..database import get_db
from ..services import audit_service, device_monitor_service, occupancy_service

router = APIRouter(prefix="/api/device-faults", tags=["device-faults"])


class TelemetryIn(BaseModel):
    device_id: int
    node_id: Optional[str] = None
    observed_on: Optional[bool] = None
    power_watts: Optional[float] = None
    current_amps: Optional[float] = None
    temperature_c: Optional[float] = None
    hazard: bool = False
    source: str = "REAL"


class NoteIn(BaseModel):
    note: Optional[str] = None


class AssignIn(BaseModel):
    user_id: int


def _node_key(x_node_key: Optional[str] = Header(default=None)):
    expected = settings.FACE_NODE_API_KEY
    if not expected or not x_node_key or not hmac.compare_digest(expected, x_node_key):
        raise HTTPException(status_code=403, detail="Node authentication failed")


@router.post("/telemetry", status_code=201, dependencies=[Depends(_node_key)])
def ingest(payload: TelemetryIn, db: Session = Depends(get_db)):
    device = db.get(models.Device, payload.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Unknown device")
    try:
        row = device_monitor_service.record_telemetry(
            db, device, node_id=payload.node_id, observed_on=payload.observed_on, power_watts=payload.power_watts,
            current_amps=payload.current_amps, temperature_c=payload.temperature_c, hazard=payload.hazard,
            source=payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"telemetry_id": row.telemetry_id}


def staff_can_see_zone(db, user, zone) -> bool:
    if user.role == "admin":
        return True
    if user.role not in ("doctor", "instructor") or zone.door_id is None:
        return False
    if db.query(models.DoorAssignment).filter(models.DoorAssignment.door_id == zone.door_id,
                                              models.DoorAssignment.instructor_id == user.user_id).first():
        return True
    return any(c["door_id"] == zone.door_id for c in occupancy_service.classes_today(db, user))


def _row(r: models.DeviceFaultAlert, full: bool):
    base = {"fault_id": r.fault_id, "zone_id": r.zone_id, "room": r.zone.name if r.zone else None,
            "device_id": r.device_id, "device": r.device.name if r.device else None,
            "device_type": r.device.type if r.device else None,
            "severity": r.severity, "status": r.status, "reason": r.reason, "detected_at": r.detected_at,
            "reported_issue": r.reported_issue, "source": r.source}
    if full:
        import json
        base.update(kind=r.kind, expected_value=r.expected_value, observed_value=r.observed_value,
                    building=r.zone.building_name if r.zone else None,
                    evidence=json.loads(r.evidence) if r.evidence else None,
                    acknowledged_at=r.acknowledged_at, acknowledged_by_id=r.acknowledged_by_id,
                    assigned_to_id=r.assigned_to_id, resolved_at=r.resolved_at, resolved_by_id=r.resolved_by_id,
                    resolution_note=r.resolution_note)
    return base


@router.get("")
def list_faults(status: Optional[str] = None, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    q = db.query(models.DeviceFaultAlert)
    if status:
        q = q.filter(models.DeviceFaultAlert.status == status.upper())
    rows = q.order_by(models.DeviceFaultAlert.detected_at.desc()).limit(300).all()
    if user.role == "admin":
        if security.is_scope_restricted(user, db):
            raise HTTPException(status_code=403, detail="Rooms have no scope mapping; unrestricted admin required")
        return [_row(r, True) for r in rows]
    if user.role not in ("doctor", "instructor"):
        raise HTTPException(status_code=403, detail="Not allowed")
    return [_row(r, False) for r in rows if r.zone and staff_can_see_zone(db, user, r.zone) and r.status != "RESOLVED"]


def _get(db, fault_id):
    r = db.get(models.DeviceFaultAlert, fault_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Fault not found")
    return r


@router.post("/{fault_id}/acknowledge")
def acknowledge(fault_id: int, db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    r = _get(db, fault_id)
    if r.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Already resolved")
    import datetime
    r.status = "ACKNOWLEDGED"
    r.acknowledged_at = datetime.datetime.utcnow()
    r.acknowledged_by_id = admin.user_id
    audit_service.log(db, admin, "acknowledge", "device_fault", r.fault_id, r.reason[:160])
    db.commit()
    return _row(r, True)


@router.post("/{fault_id}/assign")
def assign(fault_id: int, payload: AssignIn, db: Session = Depends(get_db),
           admin=Depends(security.require_unrestricted_admin)):
    r = _get(db, fault_id)
    if db.get(models.User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    r.assigned_to_id = payload.user_id
    audit_service.log(db, admin, "assign", "device_fault", r.fault_id, r.reason[:160],
                      description=f"Assigned to user #{payload.user_id}")
    db.commit()
    return _row(r, True)


@router.post("/{fault_id}/resolve")
def resolve(fault_id: int, payload: NoteIn, db: Session = Depends(get_db),
            admin=Depends(security.require_unrestricted_admin)):
    r = _get(db, fault_id)
    import datetime
    r.status = "RESOLVED"
    r.resolved_at = datetime.datetime.utcnow()
    r.resolved_by_id = admin.user_id
    r.resolution_note = (payload.note or "Resolved by admin")[:300]
    audit_service.log(db, admin, "resolve", "device_fault", r.fault_id, r.reason[:160])
    db.commit()
    return _row(r, True)


@router.post("/{fault_id}/retry-check")
def retry_check(fault_id: int, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    r = _get(db, fault_id)
    if not staff_can_see_zone(db, user, r.zone):
        raise HTTPException(status_code=403, detail="Not your room")
    device_monitor_service.evaluate_device(db, r.device)
    db.refresh(r)
    return _row(r, False)


@router.post("/{fault_id}/report")
def report(fault_id: int, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    r = _get(db, fault_id)
    if not staff_can_see_zone(db, user, r.zone) or user.role == "admin":
        raise HTTPException(status_code=403, detail="Not your room")
    r.reported_issue = True
    audit_service.log(db, user, "report", "device_fault", r.fault_id, r.reason[:160])
    db.commit()
    return _row(r, False)


@router.get("/maintenance")
def maintenance(db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    out = []
    for d in db.query(models.Device).all():
        rec = device_monitor_service.maintenance_recommendation(db, d)
        if rec:
            out.append(rec)
    return out
