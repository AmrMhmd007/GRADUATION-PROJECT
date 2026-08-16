from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=List[schemas.AlertOut])
def list_alerts(resolved: Optional[bool] = Query(None), db: Session = Depends(get_db),
                 _user=Depends(security.get_current_user)):
    q = db.query(models.Alert)
    if resolved is not None:
        q = q.filter(models.Alert.resolved == resolved)
    return q.order_by(models.Alert.alert_time.desc()).all()


@router.put("/{alert_id}/resolve", response_model=schemas.AlertOut)
def resolve_alert(alert_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    alert = db.query(models.Alert).filter(models.Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    db.commit()
    db.refresh(alert)
    return alert
