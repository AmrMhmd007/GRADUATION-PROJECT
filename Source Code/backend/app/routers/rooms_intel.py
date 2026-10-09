"""Room Health / Timeline / Campus Map (admin) - read models only."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, security
from ..database import get_db
from ..services import room_intel_service

router = APIRouter(prefix="/api/rooms-intel", tags=["rooms-intel"])


@router.get("/campus-map")
def campus_map(db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    return room_intel_service.campus_map(db)


def _zone(db, zone_id):
    z = db.get(models.Zone, zone_id)
    if z is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return z


@router.get("/zones/{zone_id}/profile")
def profile(zone_id: int, db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    return room_intel_service.room_profile(db, _zone(db, zone_id))


@router.get("/zones/{zone_id}/timeline")
def timeline(zone_id: int, hours: int = Query(24, ge=1, le=720), db: Session = Depends(get_db),
             admin=Depends(security.require_unrestricted_admin)):
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    return room_intel_service.timeline(db, _zone(db, zone_id), since)


@router.get("/energy-waste-candidates")
def energy_waste(db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    return room_intel_service.energy_waste_candidates(db)
