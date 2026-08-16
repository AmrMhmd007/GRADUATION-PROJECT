from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas, security, rate_limit
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    locked, remaining = rate_limit.is_locked_out(payload.email)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {int(remaining)}s.",
        )

    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not security.verify_password(payload.password, user.password_hash):
        rate_limit.record_failure(payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    rate_limit.record_success(payload.email)
    token = security.create_access_token(subject=user.email, role=user.role)
    return schemas.TokenResponse(access_token=token)


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(current_user: models.User = Depends(security.get_current_user)):
    # Reissues a token for an already-valid session. A production version
    # would also check a refresh-token / revocation list.
    token = security.create_access_token(subject=current_user.email, role=current_user.role)
    return schemas.TokenResponse(access_token=token)
