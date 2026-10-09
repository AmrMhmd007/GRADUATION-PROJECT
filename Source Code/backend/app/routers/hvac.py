"""Central HVAC topology (system -> vents) and sensor ingest."""
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, security
from ..config import settings
from ..database import get_db
from ..services import audit_service, hvac_service

router = APIRouter(prefix="/api/hvac", tags=["hvac"])


class SystemIn(BaseModel):
    name: str
    building_id: Optional[int] = None
    node_id: Optional[str] = None


class VentIn(BaseModel):
    zone_id: int
    main_duct: Optional[str] = None
    branch_duct: Optional[str] = None
    label: Optional[str] = None


class TelemetryIn(BaseModel):
    zone_id: int
    temperature_c: Optional[float] = None
    airflow_m3h: Optional[float] = None
    fan_running: Optional[bool] = None
    node_id: Optional[str] = None
    source: str = "REAL"


def _node_key(x_node_key: Optional[str] = Header(default=None)):
    expected = settings.FACE_NODE_API_KEY
    if not expected or not x_node_key or not hmac.compare_digest(expected, x_node_key):
        raise HTTPException(status_code=403, detail="Node authentication failed")


@router.post("/systems", status_code=201)
def create_system(p: SystemIn, db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    s = models.HvacSystem(name=p.name, building_id=p.building_id, node_id=p.node_id)
    db.add(s); db.flush()
    audit_service.log(db, admin, "create", "hvac_system", s.hvac_id, s.name)
    return {"hvac_id": s.hvac_id}


@router.post("/systems/{hvac_id}/vents", status_code=201)
def add_vent(hvac_id: int, p: VentIn, db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    if db.get(models.HvacSystem, hvac_id) is None or db.get(models.Zone, p.zone_id) is None:
        raise HTTPException(status_code=404, detail="System or zone not found")
    if db.query(models.HvacVent).filter(models.HvacVent.zone_id == p.zone_id).first():
        raise HTTPException(status_code=409, detail="Zone already has a vent")
    v = models.HvacVent(hvac_id=hvac_id, zone_id=p.zone_id, main_duct=p.main_duct, branch_duct=p.branch_duct, label=p.label)
    db.add(v); db.flush()
    audit_service.log(db, admin, "create", "hvac_vent", v.vent_id, f"zone {p.zone_id}")
    return {"vent_id": v.vent_id}


@router.get("")
def topology(db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    out = []
    for s in db.query(models.HvacSystem).all():
        out.append({"hvac_id": s.hvac_id, "name": s.name, "node_id": s.node_id, "vents": [
            {"zone_id": v.zone_id, "room": v.zone.name, "main_duct": v.main_duct, "branch_duct": v.branch_duct,
             "label": v.label, "conditions": hvac_service.zone_hvac(db, v.zone)} for v in s.vents]})
    return out


@router.post("/telemetry", status_code=201, dependencies=[Depends(_node_key)])
def telemetry(p: TelemetryIn, db: Session = Depends(get_db)):
    zone = db.get(models.Zone, p.zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Unknown zone")
    try:
        r = hvac_service.ingest(db, zone, temperature_c=p.temperature_c, airflow_m3h=p.airflow_m3h,
                                fan_running=p.fan_running, node_id=p.node_id, source=p.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"reading_id": r.reading_id}
