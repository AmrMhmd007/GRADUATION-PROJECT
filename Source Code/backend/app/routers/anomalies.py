"""
Feature #7 — Access Anomaly / Unusual Access Indicator API.

  GET /api/staff/{user_id}/anomalies?since_days=   — self, or admin scoped to that staff member's college/department
  GET /api/doors/{door_id}/anomalies?since_days=    — any admin may call this (a Door itself has no college/
                                                        department scope), but the per-staff rows it returns are
                                                        about individual people, who DO have a scope — so a scoped
                                                        admin only receives the staff/indicator rows for people they
                                                        are actually authorized to see (Stage D / D0 hardening,
                                                        mirroring the access-windows fix's exact pattern).

Reuses the exact same require_staff_access/AdminScope/is_staff_authorized
checks as every other staff-scoped endpoint — no second RBAC system.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import anomaly_detection_service

router = APIRouter(tags=["anomalies"])


@router.get("/api/staff/{user_id}/anomalies", response_model=schemas.UserAnomalyReportOut)
def get_staff_anomalies(user_id: int, since_days: Optional[int] = None, db: Session = Depends(get_db),
                         user=Depends(security.get_current_user)):
    target = db.get(models.User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user.user_id != user_id:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="You can only view your own access history")
        security.require_staff_access(target, user, db)
    return anomaly_detection_service.detect_anomalies_for_user(db, target, since_days=since_days)


@router.get("/api/doors/{door_id}/anomalies", response_model=schemas.DoorAnomalyReportOut)
def get_door_anomalies(door_id: int, since_days: Optional[int] = None, db: Session = Depends(get_db),
                        admin=Depends(security.require_admin)):
    door = db.get(models.Door, door_id)
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    report = anomaly_detection_service.detect_anomalies_for_door(db, door, since_days=since_days)

    # D0 hardening: the door itself has no college/department scope, but each
    # row in report["staff"] is about a specific person, who does. A scoped
    # admin must not see another scope's staff member's name or indicators —
    # drop those rows entirely (never just redact the name), same rule and
    # same helper as the access-windows fix.
    if security.is_scope_restricted(admin, db):
        allowed_ids = {u.user_id for u in db.query(models.User).all() if security.is_staff_authorized(u, admin, db)}
        report["staff"] = [s for s in report["staff"] if s["user_id"] in allowed_ids]
        report["summary"] = {
            "UNUSUAL": sum(1 for s in report["staff"] for i in s["indicators"] if i["severity"] == "UNUSUAL"),
            "ANOMALOUS": sum(1 for s in report["staff"] for i in s["indicators"] if i["severity"] == "ANOMALOUS"),
            "ELEVATED_RISK_INDICATOR": sum(
                1 for s in report["staff"] for i in s["indicators"] if i["severity"] == "ELEVATED_RISK_INDICATOR"
            ),
        }

    return report
