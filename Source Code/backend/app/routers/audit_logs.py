"""
Read-only view over the centralized audit trail (app/models.py::AuditLog,
app/services/audit_service.py). Deliberately exposes no PUT/PATCH/DELETE —
"immutable from the admin UI" per the hardening pass's Phase 6 requirement.

Scope note: audit events span every resource type in the system (users,
colleges, departments, courses, doors, overrides, logins...), most of which
have no single, safe way to map back to a faculty/department/operational
scope (the same limitation already documented for Command Center's
doors/alerts — Door has no scope FK, and a login event has no resource at
all). Rather than guess a per-resource-type scope mapping, this endpoint
follows the same pattern already used for admin-scope management
(academic.py::_require_unrestricted_admin): only an unrestricted admin can
view the audit log. A scoped (College/Department) admin does not get a
partial/guessed view — this is a documented limitation, not an oversight.
"""
import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


def _require_unrestricted_admin(admin=Depends(security.require_admin), db: Session = Depends(get_db)):
    if security.is_scope_restricted(admin, db):
        raise HTTPException(status_code=403, detail="Only an unrestricted admin can view the audit log")
    return admin


@router.get("", response_model=List[schemas.AuditLogOut])
def list_audit_logs(
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    result: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[datetime.date] = None,
    until: Optional[datetime.date] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin=Depends(_require_unrestricted_admin),
):
    """Phase 12 (Master UX pass): added resource_id/q/since/until/offset —
    all additive, all optional, none change the existing response shape or
    break an existing caller that only passes resource_type/actor_user_id/
    result/limit. `q` is a plain substring match over resource_label and
    description (no full-text index — fine at this table's size); `since`/
    `until` are inclusive calendar-day bounds on `timestamp`; `offset` gives
    real server-side pagination alongside the existing `limit`.

    IMPORTANT — timezone convention: `AuditLog.timestamp` is always written
    with `datetime.datetime.utcnow()` (see services/audit_service.py), the
    same convention used for every other timestamp in this codebase (no
    column anywhere stores a timezone-aware or local-time value). `since`
    and `until` are therefore interpreted as UTC calendar dates, not the
    caller's local date — a caller passing "today" must pass today's date in
    UTC to get calendar-day-accurate results. This was previously undocumented
    and a test assumed local-date semantics, which is incorrect for a
    UTC-only system; see test_audit_log_filters_phase12.py.
    """
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    query = db.query(models.AuditLog)
    if resource_type is not None:
        query = query.filter(models.AuditLog.resource_type == resource_type)
    if resource_id is not None:
        query = query.filter(models.AuditLog.resource_id == resource_id)
    if actor_user_id is not None:
        query = query.filter(models.AuditLog.actor_user_id == actor_user_id)
    if result is not None:
        if result not in ("success", "failure"):
            raise HTTPException(status_code=400, detail="result must be 'success' or 'failure'")
        query = query.filter(models.AuditLog.result == result)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(models.AuditLog.resource_label.ilike(like), models.AuditLog.description.ilike(like)))
    if since is not None:
        query = query.filter(models.AuditLog.timestamp >= datetime.datetime.combine(since, datetime.time.min))
    if until is not None:
        query = query.filter(models.AuditLog.timestamp <= datetime.datetime.combine(until, datetime.time.max))
    return query.order_by(models.AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
