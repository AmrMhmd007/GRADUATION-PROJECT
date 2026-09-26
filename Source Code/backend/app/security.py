import datetime

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from . import models

# Plain bearer-token scheme instead of OAuth2PasswordBearer. The OAuth2
# password flow expects a form-encoded username/password POST to the token
# URL, but our /api/auth/login takes JSON with an "email" field — a real
# mismatch, not a config nuance, and it made Swagger's "Authorize" button
# fail with "Unprocessable Entity" every time. HTTPBearer instead just gives
# Swagger a single "paste your token" field, which actually matches how
# every endpoint here checks the Authorization header.
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    payload = decode_token(credentials.credentials)
    email = payload.get("sub")
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


# ---------------------------------------------------------------------------
# Organizational-scope authorization (College/Department)
#
# Single source of truth for "what is this admin allowed to see/manage
# organizationally" — every academic-hierarchy router (departments, courses,
# staff) calls into these instead of re-deriving scope logic itself, per the
# "one coherent authorization model" requirement. An admin with zero
# AdminScope rows is UNRESTRICTED (today's exact behavior — no existing
# admin needs any migration). An admin with at least one row is restricted
# to the union of those rows: a row with department_id set grants just that
# department; a row with only faculty_id set grants the whole college.
# ---------------------------------------------------------------------------

def get_admin_scope_grants(user: models.User, db: Session) -> list:
    return db.query(models.AdminScope).filter(models.AdminScope.user_id == user.user_id).all()


def is_scope_restricted(user: models.User, db: Session) -> bool:
    """True only for an admin who has at least one AdminScope row. Non-admin
    roles are handled by their own existing checks (require_admin gates every
    organizational-hierarchy mutation) and are never "restricted admins"."""
    if user.role != "admin":
        return False
    return db.query(models.AdminScope).filter(models.AdminScope.user_id == user.user_id).first() is not None


def authorized_faculty_ids(user: models.User, db: Session):
    """Returns None for unrestricted access (no filtering needed), or a set
    of faculty_ids (colleges) the user may access."""
    if not is_scope_restricted(user, db):
        return None
    return {g.faculty_id for g in get_admin_scope_grants(user, db)}


def require_unrestricted_admin(admin: models.User = Depends(require_admin), db: Session = Depends(get_db)) -> models.User:
    """Gate for admin mutations that affect the organizational model itself
    (admin-scope grants, operational scopes, and — final hardening pass —
    fully removing a staff member's college/department assignment) rather
    than day-to-day data within an existing scope. A scoped admin managing
    only their own college has no business clearing a staff member's
    organizational identity entirely. academic.py's admin-scope endpoints
    have their own identical local `_require_unrestricted_admin` (left
    as-is to avoid touching already-tested behavior); this shared version
    is for users.py's new staff-unassign endpoint."""
    if is_scope_restricted(admin, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an unrestricted admin can do this")
    return admin


def authorized_department_ids(user: models.User, db: Session, faculty_id: int):
    """For a restricted admin, returns None if the whole faculty_id is
    granted (a college-level grant), or a set of specifically-granted
    department_ids under that faculty otherwise. Only meaningful after
    confirming the faculty itself is authorized."""
    if not is_scope_restricted(user, db):
        return None
    grants = [g for g in get_admin_scope_grants(user, db) if g.faculty_id == faculty_id]
    if any(g.department_id is None for g in grants):
        return None  # whole-college grant
    return {g.department_id for g in grants}


def require_faculty_access(faculty_id: int, user: models.User, db: Session) -> None:
    allowed = authorized_faculty_ids(user, db)
    if allowed is not None and faculty_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="You aren't authorized for this college")


def require_department_access(department: models.Department, user: models.User, db: Session) -> None:
    require_faculty_access(department.faculty_id, user, db)
    dept_ids = authorized_department_ids(user, db, department.faculty_id)
    if dept_ids is not None and department.department_id not in dept_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="You aren't authorized for this department")


def is_staff_authorized(staff: models.User, user: models.User, db: Session) -> bool:
    """Boolean predicate version of require_staff_access's exact same
    logic — used by callers that need to silently FILTER a list down to
    what's authorized (e.g. Command Center's scope isolation) rather than
    403 on a single target. Deliberately not implemented by wrapping
    require_staff_access in a try/except (that would work but reads as if
    an exception is the normal control-flow path for a filter); instead
    this mirrors the same checks so the two stay obviously equivalent."""
    if not is_scope_restricted(user, db):
        return True
    if staff.faculty_id is None:
        return False
    allowed = authorized_faculty_ids(user, db)
    if allowed is not None and staff.faculty_id not in allowed:
        return False
    if staff.department_id is not None:
        dept_ids = authorized_department_ids(user, db, staff.faculty_id)
        if dept_ids is not None and staff.department_id not in dept_ids:
            return False
    return True


def require_staff_access(staff: models.User, user: models.User, db: Session) -> None:
    """Gate for viewing/editing a specific Doctor/TA — checks the target
    staff member's own faculty/department against the acting admin's scope.
    A staff member with no faculty_id set is only reachable by an
    unrestricted admin (there's no college to authorize against)."""
    if not is_scope_restricted(user, db):
        return
    if staff.faculty_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="This staff member has no assigned college")
    require_faculty_access(staff.faculty_id, user, db)
    if staff.department_id is not None:
        dept_ids = authorized_department_ids(user, db, staff.faculty_id)
        if dept_ids is not None and staff.department_id not in dept_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail="You aren't authorized for this staff member's department")


def authorized_operational_scope_ids(user: models.User, db: Session):
    """Non-academic counterpart to authorized_faculty_ids — same AdminScope
    table, same "None means unrestricted" convention. A grant row with
    operational_scope_id set authorizes exactly that one operational area
    (HVAC/Electrical/Residential/Administrative/Engineering)."""
    if not is_scope_restricted(user, db):
        return None
    return {g.operational_scope_id for g in get_admin_scope_grants(user, db) if g.operational_scope_id is not None}


def require_operational_scope_access(scope_id: int, user: models.User, db: Session) -> None:
    allowed = authorized_operational_scope_ids(user, db)
    if allowed is not None and scope_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="You aren't authorized for this operational scope")


def require_room_control(door: models.Door, user: models.User, db: Session) -> None:
    """Gate for the AC/light/plug endpoints (routers/doors.py).

    Unlike the door lock itself — which stays admin-direct / doctor-request
    only, unchanged — a doctor gets to flip these directly for a Room they've
    actually been assigned (same assignment table request-access already
    uses), since a classroom's AC/lights/plugs are lower-stakes than its
    lock. Admin can always do this; instructors never can (only doctors were
    asked for this control).
    """
    if user.role == "admin":
        return
    if user.role == "doctor":
        assigned = (
            db.query(models.DoorAssignment)
            .filter(
                models.DoorAssignment.door_id == door.door_id,
                models.DoorAssignment.instructor_id == user.user_id,
            )
            .first()
        )
        if assigned:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You aren't assigned to this room")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to control this room")
