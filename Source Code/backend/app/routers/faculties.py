from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/faculties", tags=["faculties"])


@router.get("", response_model=List[schemas.FacultyOut])
def list_faculties(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Faculty).order_by(models.Faculty.name).all()


@router.post("", response_model=schemas.FacultyOut, status_code=201)
def create_faculty(payload: schemas.FacultyCreate, db: Session = Depends(get_db),
                    _admin=Depends(security.require_admin)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Faculty name is required")
    existing = db.query(models.Faculty).filter(models.Faculty.name == name).first()
    if existing:
        return existing
    faculty = models.Faculty(name=name)
    db.add(faculty)
    db.commit()
    db.refresh(faculty)
    return faculty
