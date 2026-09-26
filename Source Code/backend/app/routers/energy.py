from __future__ import annotations

import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service, energy_service

router = APIRouter(prefix="/api", tags=["energy"])


@router.post("/doors/{door_id}/occupancy", response_model=schemas.DoorOut)
def set_occupancy(door_id: int, payload: schemas.OccupancyUpdate, db: Session = Depends(get_db),
                   _admin=Depends(security.require_admin)):
    """Admin-only manual/testing path for setting a room's occupancy flag.

    The real path is the occupancy sensor itself, reporting straight over
    MQTT (site/{code}/occupancy/status — see services/mqtt_service.py) with
    no admin involved at all. This endpoint exists only so the feature can
    be demoed or tested before that hardware is wired up, the same reason
    /{door_id}/status exists for online/offline.
    """
    door = db.query(models.Door).filter(models.Door.door_id == door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    if door.category != "access_service":
        raise HTTPException(status_code=400, detail="Only rooms (access_service) have occupancy sensors")

    door.occupied = payload.occupied
    door.occupancy_updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(door)
    return door


@router.get("/doors/{door_id}/power", response_model=List[schemas.PowerReadingOut])
def door_power_readings(door_id: int, limit: int = 100, db: Session = Depends(get_db),
                         _user=Depends(security.get_current_user)):
    """Recent power-reading history for one room's AC + plugs combined,
    newest first — what a per-room consumption chart on the dashboard would
    plot directly."""
    door = db.query(models.Door).filter(models.Door.door_id == door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    return (
        db.query(models.PowerReading)
        .filter(models.PowerReading.door_id == door_id)
        .order_by(models.PowerReading.recorded_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/system/settings", response_model=schemas.SystemSettingsOut)
def get_system_settings(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return schemas.SystemSettingsOut(checkout_time=energy_service.get_checkout_time(db))


@router.put("/system/settings", response_model=schemas.SystemSettingsOut)
def update_system_settings(payload: schemas.SystemSettingsUpdate, db: Session = Depends(get_db),
                            _admin=Depends(security.require_admin)):
    try:
        datetime.datetime.strptime(payload.checkout_time, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="checkout_time must be 'HH:MM' (24h)")
    energy_service.set_checkout_time(db, payload.checkout_time)
    audit_service.log(db, actor=_admin, action="update", resource_type="system_settings",
                       resource_label="checkout_time", description=f"checkout_time set to {payload.checkout_time}")
    return schemas.SystemSettingsOut(checkout_time=payload.checkout_time)


@router.post("/system/run-checkout-sweep", response_model=schemas.CheckoutSweepResult)
def run_checkout_sweep_now(db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    """Manual "do it now" trigger for the same sweep the daily clock runs
    automatically — lets an admin demo it, or run it early on a day when
    everyone's already left."""
    codes = energy_service.run_checkout_sweep(db)
    return schemas.CheckoutSweepResult(
        rooms_swept=len(codes), door_codes=codes, ran_at=datetime.datetime.utcnow(),
    )
