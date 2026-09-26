from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service

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
    audit_service.log(db, actor=_admin, action="create", resource_type="building", resource_id=building.building_id,
                       resource_label=building.name)
    return building


@router.delete("/{building_id}", status_code=204)
def delete_building(building_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    building = db.query(models.Building).filter(models.Building.building_id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    # Door.building is a plain string, not a foreign key (see models.py), so
    # this delete can't cascade — block it instead of silently leaving doors
    # pointing at a building that's no longer in the picker.
    in_use = db.query(models.Door).filter(models.Door.building == building.name).count()
    if in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"{in_use} door{'s' if in_use != 1 else ''} still use \"{building.name}\" — reassign or delete them first.",
        )
    # Phase 12 fix: OperationalScope.building_id IS a real FK (unlike
    # Door.building above), but SQLite here doesn't enforce FKs (no PRAGMA
    # foreign_keys=ON — see database.py), so deleting a building still
    # referenced by an OperationalScope would silently orphan that scope's
    # building_id rather than raise. Same dependent-blocking pattern as the
    # door check just above.
    scopes_in_use = db.query(models.OperationalScope).filter(models.OperationalScope.building_id == building_id).count()
    if scopes_in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"{scopes_in_use} operational scope(s) still use \"{building.name}\" — reassign or delete them first.",
        )

    building_id_val, building_name = building.building_id, building.name
    db.delete(building)
    db.commit()
    audit_service.log(db, actor=_admin, action="delete", resource_type="building", resource_id=building_id_val,
                       resource_label=building_name)
