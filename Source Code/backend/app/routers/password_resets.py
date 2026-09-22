import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/password-resets", tags=["password-resets"])


@router.get("", response_model=List[schemas.PasswordResetRequestOut])
def list_password_resets(db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    """Pending requests only — approved/denied ones drop off the admin's
    list once handled, since there's nothing left to do about them.
    """
    return (
        db.query(models.PasswordResetRequest)
        .filter(models.PasswordResetRequest.status == "pending")
        .order_by(models.PasswordResetRequest.requested_at.asc())
        .all()
    )


@router.post("/{request_id}/approve", status_code=204)
def approve_password_reset(
    request_id: int, db: Session = Depends(get_db), admin: models.User = Depends(security.require_admin)
):
    """Just greenlights the request — no password is generated or shown
    here. The user's own browser (the one holding the request_token from
    when they submitted the form) is already polling for this and will
    move itself straight to a "set your new password" screen.
    """
    req = db.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="This request was already resolved")

    req.status = "approved"
    req.resolved_at = datetime.datetime.utcnow()
    req.resolved_by = admin.user_id
    db.commit()


@router.post("/{request_id}/deny", status_code=204)
def deny_password_reset(
    request_id: int, db: Session = Depends(get_db), admin: models.User = Depends(security.require_admin)
):
    req = db.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="This request was already resolved")

    req.status = "denied"
    req.resolved_at = datetime.datetime.utcnow()
    req.resolved_by = admin.user_id
    db.commit()
