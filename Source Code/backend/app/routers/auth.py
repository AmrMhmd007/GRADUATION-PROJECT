import secrets

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


@router.post(
    "/forgot-password", response_model=schemas.ForgotPasswordResponse, status_code=status.HTTP_202_ACCEPTED
)
def forgot_password(payload: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Queues a password-reset request for an admin to review — this
    deployment has no mail server, so there's no reset link to email.
    Instead, the requesting browser gets back an opaque `request_token` and
    sits on a "waiting for approval" screen (see the dashboard's Login
    page), polling GET /forgot-password/status with it. The detail message
    is always the same regardless of whether the address matches an
    account, and an unmatched request still gets back a token (one that
    will just never resolve) — both so this endpoint can't be used to probe
    which emails are registered.
    """
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user:
        # Only reuse a request that's still genuinely PENDING (e.g. they
        # reopened/resubmitted the form while an admin hadn't looked at it
        # yet) — this is what makes the sequence strict: every request that
        # isn't currently awaiting a decision starts a brand new one, which
        # always begins "pending" and always needs a fresh admin approval
        # before that browser is ever let past the waiting screen. Reusing
        # an already-approved-but-unconsumed row here was the bug: it let a
        # brand new submission come back "approved" on its very first poll
        # with no admin having done anything in that session at all.
        existing = (
            db.query(models.PasswordResetRequest)
            .filter(
                models.PasswordResetRequest.user_id == user.user_id,
                models.PasswordResetRequest.status == "pending",
            )
            .first()
        )
        if existing:
            if not existing.request_token:
                existing.request_token = secrets.token_urlsafe(32)
                db.commit()
            token = existing.request_token
        else:
            token = secrets.token_urlsafe(32)
            db.add(models.PasswordResetRequest(user_id=user.user_id, request_token=token))
            db.commit()
    else:
        token = secrets.token_urlsafe(32)  # not stored — never resolves, indistinguishable from a real one

    return schemas.ForgotPasswordResponse(
        detail="If that email is registered, an admin will review your request.",
        request_token=token,
    )


@router.get("/forgot-password/status", response_model=schemas.PasswordResetStatusOut)
def forgot_password_status(token: str, db: Session = Depends(get_db)):
    req = db.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == token
    ).first()
    # Unknown/dummy tokens report "pending" forever, same as a real request
    # nobody has actioned yet — keeps this endpoint from leaking whether a
    # token was ever real.
    if not req:
        return schemas.PasswordResetStatusOut(status="pending")
    if req.password_set:
        return schemas.PasswordResetStatusOut(status="used")
    return schemas.PasswordResetStatusOut(status=req.status)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    """Lets the browser holding an *approved* request_token set its own new
    password directly — no current password needed, since possessing this
    unguessable token (handed out only once, to the tab that requested it)
    is what stands in for one here.
    """
    req = db.query(models.PasswordResetRequest).filter(
        models.PasswordResetRequest.request_token == payload.request_token
    ).first()
    if not req or req.status != "approved" or req.password_set:
        raise HTTPException(status_code=400, detail="This reset request is no longer valid.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    req.user.password_hash = security.hash_password(payload.new_password)
    req.password_set = True
    db.commit()
