from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("", response_model=List[schemas.ScheduleOut])
def list_schedules(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Schedule).all()


@router.post("", response_model=schemas.ScheduleOut, status_code=201)
def create_schedule(payload: schemas.ScheduleCreate, db: Session = Depends(get_db),
                     _admin=Depends(security.require_admin)):
    door = db.query(models.Door).filter(models.Door.door_id == payload.door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    schedule = models.Schedule(**payload.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.put("/{schedule_id}", response_model=schemas.ScheduleOut)
def update_schedule(schedule_id: int, payload: schemas.ScheduleUpdate, db: Session = Depends(get_db),
                     _admin=Depends(security.require_admin)):
    schedule = db.query(models.Schedule).filter(models.Schedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)
    return schedule
