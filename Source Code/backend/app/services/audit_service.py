"""
Centralized audit logging (final hardening pass, Phase 6). One function,
called from every security-sensitive router mutation, writing to the
generic AuditLog table (app/models.py) — see that class's docstring for why
this exists alongside the domain-specific logs (AccessEvent, AutomationLog,
EmergencyOverride) rather than replacing them.

Deliberately synchronous and part of the same DB session/transaction as the
action it's recording: if the action's own db.commit() succeeds, the audit
row is already staged and commits with it (call log() BEFORE the caller's
final db.commit() so a single commit covers both — see call sites). If a
caller commits its own change first and log() is called after, log() does
its own commit; either way the row is never dropped by mistake.
"""
from typing import Optional

from .. import models


def log(
    db,
    actor: Optional[models.User],
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    resource_label: Optional[str] = None,
    result: str = "success",
    description: Optional[str] = None,
    actor_email: Optional[str] = None,
) -> models.AuditLog:
    """Records one audit event. `actor` is None for pre-authentication
    events (e.g. a failed login for an email that may not even correspond to
    a real account) — pass `actor_email` directly in that case instead."""
    entry = models.AuditLog(
        actor_user_id=actor.user_id if actor else None,
        actor_email=actor.email if actor else actor_email,
        actor_role=actor.role if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_label=resource_label,
        result=result,
        description=description,
    )
    db.add(entry)
    db.commit()
    return entry
