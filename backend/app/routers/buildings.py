from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/buildings", tags=["buildings"])


@router.get("", response_model=List[schemas.BuildingOut])
def list_buildings(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Building).order_by(models.Building.name).all()


@router.post("", response_model=schemas.BuildingOut, status_code=201)
def create_building(payload: schemas.BuildingCreate, db: Session = Depends(get_db),
                     _admin=Depends(security.require_admin)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Building name is required")
    existing = db.query(models.Building).filter(models.Building.name == name).first()
    if existing:
        return existing
    building = models.Building(name=name)
    db.add(building)
    db.commit()
    db.refresh(building)
    return building
