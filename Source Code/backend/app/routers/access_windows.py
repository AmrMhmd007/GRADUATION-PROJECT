"""
Feature #5 — Schedule-Derived Access Authorization API.

Endpoints:
  GET/POST      /api/access-windows              — manage recurring/temporary access grants
  PUT/DELETE    /api/access-windows/{id}
  GET           /api/doors/{door_id}/authorization?user_id=  — "is this user allowed through this door right now"

Authorization reuses the EXISTING AdminScope/require_staff_access model —
an admin may only create/edit/delete/view a window for a staff member
within their own authorized college/department (or any staff member, if
unrestricted). This is not a second RBAC system: it is the same check
already used for course assignment and staff-scope updates, applied to a
new kind of staff-scoped record.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import access_authorization_service

router = APIRouter(tags=["access-windows"])


def _target_staff_or_404(db: Session, user_id: int) -> models.User:
    staff = db.get(models.User, user_id)
    if not staff:
        raise HTTPException(status_code=404, detail="User not found")
    return staff


@router.get("/api/access-windows", response_model=List[schemas.AccessWindowOut])
def list_access_windows(door_id: Optional[int] = None, user_id: Optional[int] = None,
                         db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    q = db.query(models.AccessWindow)
    if user.role == "admin":
        if user_id is not None:
            target = _target_staff_or_404(db, user_id)
            security.require_staff_access(target, user, db)
            q = q.filter(models.AccessWindow.user_id == user_id)
        # else: no specific user_id requested (e.g. a door-only lookup like
        # the Access & Authorization panel's door_id= call) — fall through
        # to the row-level scope filter below rather than returning every
        # window unfiltered.
    else:
        # Non-admin staff can only ever see their own windows.
        q = q.filter(models.AccessWindow.user_id == user.user_id)
    if door_id is not None:
        q = q.filter(models.AccessWindow.door_id == door_id)

    windows = q.order_by(models.AccessWindow.created_at.desc()).all()

    if user.role == "admin" and user_id is None and security.is_scope_restricted(user, db):
        # Fixes a real authorization gap: a scoped admin listing by door_id
        # alone (no user_id) previously saw EVERY window on that door,
        # including ones belonging to staff outside their authorized
        # college/department. This reuses the exact same predicate
        # require_staff_access enforces for a single target
        # (is_staff_authorized — already used for Command Center's scope
        # isolation) applied per-row here instead of a single 403, since
        # this is a list endpoint, not a single-target lookup. The
        # unauthorized row is dropped entirely, not just its user's name.
        windows = [w for w in windows if security.is_staff_authorized(w.user, user, db)]

    return windows


@router.post("/api/access-windows", response_model=schemas.AccessWindowOut, status_code=201)
def create_access_window(payload: schemas.AccessWindowCreate, db: Session = Depends(get_db),
                          admin=Depends(security.require_admin)):
    door = db.get(models.Door, payload.door_id)
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    target = _target_staff_or_404(db, payload.user_id)
    if target.role not in ("doctor", "instructor"):
        raise HTTPException(status_code=400, detail="Access windows are for Doctors/TAs (staff), not this user's role")
    security.require_staff_access(target, admin, db)
    if payload.course_id is not None and not db.get(models.Course, payload.course_id):
        raise HTTPException(status_code=404, detail="Course not found")

    try:
        access_authorization_service.validate_window_shape(payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    window = models.AccessWindow(**payload.model_dump(), created_by_id=admin.user_id)
    db.add(window)
    db.commit()
    db.refresh(window)
    return window


@router.put("/api/access-windows/{access_window_id}", response_model=schemas.AccessWindowOut)
def update_access_window(access_window_id: int, payload: schemas.AccessWindowUpdate, db: Session = Depends(get_db),
                          admin=Depends(security.require_admin)):
    window = db.get(models.AccessWindow, access_window_id)
    if not window:
        raise HTTPException(status_code=404, detail="Access window not found")
    security.require_staff_access(window.user, admin, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(window, field, value)

    merged = {
        "recurring": window.recurring, "day_of_week": window.day_of_week,
        "start_time": window.start_time, "end_time": window.end_time,
        "valid_from": window.valid_from, "valid_until": window.valid_until,
        "start_at": window.start_at, "end_at": window.end_at,
    }
    try:
        access_authorization_service.validate_window_shape(merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(window)
    return window


@router.delete("/api/access-windows/{access_window_id}", status_code=204)
def delete_access_window(access_window_id: int, db: Session = Depends(get_db),
                          admin=Depends(security.require_admin)):
    window = db.get(models.AccessWindow, access_window_id)
    if not window:
        raise HTTPException(status_code=404, detail="Access window not found")
    security.require_staff_access(window.user, admin, db)
    db.delete(window)
    db.commit()


@router.get("/api/doors/{door_id}/authorization", response_model=schemas.DoorAuthorizationOut)
def check_door_authorization(door_id: int, user_id: Optional[int] = None, db: Session = Depends(get_db),
                              user=Depends(security.get_current_user)):
    door = db.get(models.Door, door_id)
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")

    if user_id is not None and user_id != user.user_id:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="You can only check your own authorization")
        target = _target_staff_or_404(db, user_id)
        security.require_staff_access(target, user, db)
    else:
        target = user

    evaluation = access_authorization_service.evaluate_door_authorization(db, target, door)
    access_authorization_service.log_authorization_check(db, door=door, user=target, evaluation=evaluation)
    return evaluation
