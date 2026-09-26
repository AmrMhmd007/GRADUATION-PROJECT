from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Scope note (final hardening pass, Phase 7 — closes a real gap found during
# the anomaly/alert audit): alerts are door- or zone-anchored, and neither
# Door nor Zone has a safe, authoritative FK to a Faculty/Department/
# OperationalScope (same documented limitation as Command Center's
# doors/alerts — see command_center.py's module docstring). Rather than
# guess a scope mapping (matching on Door.building strings, say), a
# scope-restricted admin gets an empty list here — never someone else's
# alerts, and never a fabricated "your alerts" subset — and cannot resolve
# any alert at all. An unrestricted admin is unaffected (today's exact
# behavior). This mirrors the Command Center's "unavailable" treatment,
# adapted to this endpoint's plain-list response shape.


@router.get("", response_model=List[schemas.AlertOut])
def list_alerts(resolved: Optional[bool] = Query(None), db: Session = Depends(get_db),
                 user=Depends(security.get_current_user)):
    if user.role == "admin" and security.is_scope_restricted(user, db):
        return []
    q = db.query(models.Alert)
    if resolved is not None:
        q = q.filter(models.Alert.resolved == resolved)
    return q.order_by(models.Alert.alert_time.desc()).all()


@router.put("/{alert_id}/resolve", response_model=schemas.AlertOut)
def resolve_alert(alert_id: int, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    if security.is_scope_restricted(admin, db):
        raise HTTPException(
            status_code=403,
            detail="Alerts have no scope mapping yet — only an unrestricted admin can resolve them.",
        )
    alert = db.query(models.Alert).filter(models.Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    db.commit()
    db.refresh(alert)
    return alert
