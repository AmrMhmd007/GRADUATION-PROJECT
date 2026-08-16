from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security, crypto
from ..database import get_db

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _to_out(cred: models.Credential) -> schemas.CredentialOut:
    masked = None
    if cred.card_uid:
        plain = crypto.decrypt_uid(cred.card_uid)
        if plain:
            masked = ("*" * max(len(plain) - 4, 0)) + plain[-4:]
        else:
            masked = "**decrypt-error**"  # wrong/rotated key — surfaced, not hidden
    return schemas.CredentialOut(
        credential_id=cred.credential_id,
        user_id=cred.user_id,
        card_uid_masked=masked,
        active=cred.active,
        issued_at=cred.issued_at,
    )


@router.get("", response_model=List[schemas.CredentialOut])
def list_credentials(db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    return [_to_out(c) for c in db.query(models.Credential).all()]


@router.post("", response_model=schemas.CredentialOut, status_code=201)
def issue_credential(payload: schemas.CredentialCreate, db: Session = Depends(get_db),
                      _admin=Depends(security.require_admin)):
    card_uid_enc, card_uid_idx = None, None
    if payload.card_uid:
        existing = db.query(models.Credential).filter(
            models.Credential.card_uid_index == crypto.uid_index(payload.card_uid)
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="A credential with this card UID already exists")
        card_uid_enc = crypto.encrypt_uid(payload.card_uid)
        card_uid_idx = crypto.uid_index(payload.card_uid)

    cred = models.Credential(
        user_id=payload.user_id,
        card_uid=card_uid_enc,
        card_uid_index=card_uid_idx,
        fp_template_hash=payload.fp_template_hash,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return _to_out(cred)


@router.delete("/{credential_id}", status_code=204)
def revoke_credential(credential_id: int, db: Session = Depends(get_db),
                       _admin=Depends(security.require_admin)):
    cred = db.query(models.Credential).filter(models.Credential.credential_id == credential_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    # Revoke, don't hard-delete — access_events keeps a foreign key to this row.
    cred.active = False
    db.commit()
    return None
