from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import mqtt_service

router = APIRouter(prefix="/api/doors", tags=["doors"])


@router.get("", response_model=List[schemas.DoorOut])
def list_doors(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Door).all()
@router.post("", response_model=schemas.DoorOut, status_code=201)
def create_door(payload: schemas.DoorCreate, db: Session = Depends(get_db),
                 admin=Depends(security.require_admin)):
    if payload.fail_mode not in ("secure", "safe"):
        raise HTTPException(status_code=400, detail="fail_mode must be 'secure' or 'safe'")

    existing = db.query(models.Door).filter(models.Door.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A door with code '{payload.code}' already exists")

    door = models.Door(
        code=payload.code, name=payload.name, building=payload.building,
        fail_mode=payload.fail_mode, online=False, locked=True,
    )
    db.add(door)
    db.commit()
    db.refresh(door)
    return door


@router.get("/{door_id}", response_model=schemas.DoorOut)
def get_door(door_id: int, db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    door = db.query(models.Door).filter(models.Door.door_id == door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    return door


@router.get("/{door_id}/logs", response_model=List[schemas.AccessEventOut])
def door_logs(door_id: int, db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return (
        db.query(models.AccessEvent)
        .filter(models.AccessEvent.door_id == door_id)
        .order_by(models.AccessEvent.event_time.desc())
        .limit(200)
        .all()
    )


@router.post("/{door_id}/override")
def override_door(door_id: int, payload: schemas.DoorOverrideRequest, db: Session = Depends(get_db),
                   admin=Depends(security.require_admin)):
    door = db.query(models.Door).filter(models.Door.door_id == door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    if payload.action not in ("lock", "unlock"):
        raise HTTPException(status_code=400, detail="action must be 'lock' or 'unlock'")

    sent = mqtt_service.publish_override(door.code, payload.action)

    # Log the override attempt regardless of delivery, so there's an audit
    # trail even if the broker/node didn't acknowledge it.
    event = models.AccessEvent(
        door_id=door.door_id,
        credential_id=None,
        method="override",
        result="sent" if sent else "queued_no_broker",
    )
    db.add(event)
    if payload.action == "unlock":
        door.locked = False
    else:
        door.locked = True
    db.commit()

    return {"door_id": door_id, "action": payload.action, "mqtt_delivered": sent}
