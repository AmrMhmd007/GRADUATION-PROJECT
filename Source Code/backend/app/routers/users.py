import io
import os
import random
import re
import string
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service

router = APIRouter(prefix="/api/users", tags=["users"])

# backend/media/avatars — see app/main.py for the StaticFiles mount that
# serves this directory at /media.
AVATAR_DIR = Path(__file__).resolve().parent.parent.parent / "media" / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024

STAFF_EMAIL_DOMAIN = "aiu.is"


def _suggest_email(name: str) -> str:
    slug = re.sub(r"[^a-z0-9\s.]", "", name.strip().lower())
    parts = [p for p in slug.split() if p]
    base = ".".join(parts) or "user"
    return f"{base}@{STAFF_EMAIL_DOMAIN}"


def _random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


@router.get("", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    q = db.query(models.User)
    allowed = security.authorized_faculty_ids(admin, db)
    if allowed is not None:
        # A scoped admin only ever sees staff in their authorized college(s)
        # (plus themselves and other admins are excluded from this generic
        # listing being scope-limited would be surprising — but staff rows
        # outside scope must never leak here). Admin/self rows have no
        # faculty_id in the common case, so we scope by role instead: other
        # admins are still visible (org chart), doctor/instructor rows are
        # filtered to the authorized colleges only.
        from sqlalchemy import or_
        q = q.filter(or_(models.User.role == "admin", models.User.faculty_id.in_(allowed)))
    return q.all()


# ---------- "Me" (the logged-in user managing their own account) ----------
# Declared before "/{user_id}/..." routes so "/me" isn't ever swallowed by a
# path-param route.

@router.get("/me", response_model=schemas.UserOut)
def get_me(user=Depends(security.get_current_user), db: Session = Depends(get_db)):
    data = schemas.UserOut.model_validate(user).model_dump()
    # Phase 12: lets the AdminScope/OperationalScope management UI show
    # itself only to an unrestricted admin, matching exactly what
    # academic.py::_require_unrestricted_admin already enforces server-side
    # — this is presentation only, not a new authorization check.
    data["is_scope_restricted"] = security.is_scope_restricted(user, db) if user.role == "admin" else None
    return data


@router.patch("/me/profile", response_model=schemas.UserOut)
def update_my_profile(payload: schemas.ProfileUpdate, db: Session = Depends(get_db),
                       user=Depends(security.get_current_user)):
    """Updates name/email for the logged-in user. Note the JWT's subject is
    the email, so changing it invalidates the *meaning* of the old token
    (it'll still decode, but won't match any user by email) — the frontend
    must call POST /api/auth/refresh right after this to get a token that
    matches the new email, or the next request will 401.
    """
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name can't be empty")
        user.name = name

    if payload.email is not None and payload.email != user.email:
        existing = db.query(models.User).filter(
            models.User.email == payload.email, models.User.user_id != user.user_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"A user with email '{payload.email}' already exists")
        user.email = payload.email

    db.commit()
    db.refresh(user)
    return user


@router.patch("/me/password", status_code=204)
def change_my_password(payload: schemas.PasswordChange, db: Session = Depends(get_db),
                        user=Depends(security.get_current_user)):
    if not security.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    user.password_hash = security.hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()


@router.post("/me/photo", response_model=schemas.UserOut)
async def upload_my_photo(file: UploadFile = File(...), db: Session = Depends(get_db),
                           user=Depends(security.get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_PHOTO_EXTS:
        raise HTTPException(status_code=400, detail="Photo must be a PNG, JPG, GIF, or WEBP image")

    contents = await file.read()
    if len(contents) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Photo must be under 5MB")

    filename = f"{user.user_id}-{uuid.uuid4().hex}{ext}"
    with open(AVATAR_DIR / filename, "wb") as f:
        f.write(contents)

    user.photo_url = f"/media/avatars/{filename}"
    db.commit()
    db.refresh(user)
    return user


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    if payload.role not in ("admin", "instructor", "doctor"):
        raise HTTPException(status_code=400, detail="role must be 'admin', 'instructor', or 'doctor'")
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A user with email '{payload.email}' already exists")
    if payload.faculty_id is not None:
        security.require_faculty_access(payload.faculty_id, admin, db)
    if payload.department_id is not None:
        dept = db.get(models.Department, payload.department_id)
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        if payload.faculty_id is not None and dept.faculty_id != payload.faculty_id:
            raise HTTPException(status_code=400, detail="Department doesn't belong to that college")
        security.require_department_access(dept, admin, db)
    if payload.staff_id:
        existing_staff_id = db.query(models.User).filter(models.User.staff_id == payload.staff_id).first()
        if existing_staff_id:
            raise HTTPException(status_code=409, detail=f"Staff ID '{payload.staff_id}' is already in use")
    user = models.User(
        name=payload.name,
        email=payload.email,
        role=payload.role,
        password_hash=security.hash_password(payload.password),
        faculty_id=payload.faculty_id,
        department_id=payload.department_id,
        staff_id=payload.staff_id or None,
        academic_title=payload.academic_title,
        specialization=payload.specialization,
        phone=payload.phone,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_service.log(db, actor=admin, action="create", resource_type="user", resource_id=user.user_id,
                       resource_label=f"{user.name} ({user.email})", description=f"role={user.role}")
    return user


@router.put("/{user_id}/scope", response_model=schemas.UserOut)
def update_staff_scope(user_id: int, payload: schemas.UserUpdateScope, db: Session = Depends(get_db),
                        admin=Depends(security.require_admin)):
    """Reassign a Doctor/TA's college/department — the write side of the
    organizational hierarchy staff scoping."""
    staff = db.get(models.User, user_id)
    if not staff:
        raise HTTPException(status_code=404, detail="User not found")
    security.require_staff_access(staff, admin, db)
    if payload.faculty_id is not None:
        security.require_faculty_access(payload.faculty_id, admin, db)
        if not db.get(models.Faculty, payload.faculty_id):
            raise HTTPException(status_code=404, detail="College not found")
        staff.faculty_id = payload.faculty_id
    if payload.department_id is not None:
        dept = db.get(models.Department, payload.department_id)
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        security.require_department_access(dept, admin, db)
        staff.department_id = payload.department_id
    db.commit()
    db.refresh(staff)
    audit_service.log(db, actor=admin, action="update", resource_type="user", resource_id=staff.user_id,
                       resource_label=staff.name, description="college/department scope changed")
    return staff


@router.post("/{user_id}/unassign", response_model=schemas.UserOut)
def unassign_staff(user_id: int, db: Session = Depends(get_db),
                    admin=Depends(security.require_unrestricted_admin)):
    """Removes a Doctor/TA from the academic organization — clears
    faculty_id/department_id back to NULL (both columns are nullable at the
    DB level precisely for this; see models.py's User docstring). This is
    deliberately a separate action from update_staff_scope above, which only
    ever *reassigns* to a specific college/department and has no way to
    express "no college" through its schema (both fields being absent means
    "leave unchanged", not "clear").

    Does NOT delete the user/account (see DELETE /{user_id} for that
    separate, explicit operation) and does NOT touch DoorAssignment/
    AccessWindow rows — physical building access is independent of academic
    org membership. It DOES refuse to silently orphan an active
    CourseAssignment: a course lives under a specific department, so a TA
    with an active assignment there and suddenly no department at all would
    be a dangling, meaningless combination. The admin must reassign or
    remove those course assignments first, exactly like the existing
    College/Department delete endpoints refuse to cascade-delete their own
    dependents (see faculties.py's _faculty_dependents).

    Unrestricted-admin only (see security.require_unrestricted_admin): this
    clears organizational identity entirely, not a same-scope edit.
    """
    staff = db.get(models.User, user_id)
    if not staff:
        raise HTTPException(status_code=404, detail="User not found")
    if staff.role not in ("doctor", "instructor"):
        raise HTTPException(status_code=400, detail="Only Doctor/TA staff can be removed from the academic organization")
    if staff.faculty_id is None and staff.department_id is None:
        raise HTTPException(status_code=400, detail=f"{staff.name} already has no academic college/department assignment")

    active_assignments = db.query(models.CourseAssignment).filter(
        models.CourseAssignment.user_id == user_id, models.CourseAssignment.status == "active"
    ).count()
    if active_assignments:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Can't remove {staff.name} from the academic organization — they still have "
                f"{active_assignments} active course assignment{'s' if active_assignments != 1 else ''}. "
                "Reassign or remove those course assignments first."
            ),
        )

    staff.faculty_id = None
    staff.department_id = None
    db.commit()
    db.refresh(staff)
    audit_service.log(db, actor=admin, action="update", resource_type="user", resource_id=staff.user_id,
                       resource_label=staff.name,
                       description="removed from academic organization (college/department cleared)")
    return staff


@router.put("/{user_id}/staff-profile", response_model=schemas.UserOut)
def update_staff_profile(user_id: int, payload: schemas.StaffUpdate, db: Session = Depends(get_db),
                          admin=Depends(security.require_admin)):
    """Admin edit of a Doctor/TA's academic profile fields (staff_id,
    academic_title, specialization, phone, status/active-deactivate) — the
    write side of Phase 5/8's "Edit doctor/TA" + "Activate/deactivate"
    actions. Deliberately separate from update_staff_scope (college/
    department reassignment already has its own endpoint+tests) and from
    the self-service PATCH /me/profile (name/email only, no admin fields)."""
    staff = db.get(models.User, user_id)
    if not staff:
        raise HTTPException(status_code=404, detail="User not found")
    if staff.role not in ("doctor", "instructor"):
        raise HTTPException(status_code=400, detail="Only Doctor/TA staff profiles can be edited here")
    security.require_staff_access(staff, admin, db)

    if payload.staff_id is not None:
        if payload.staff_id:
            clash = db.query(models.User).filter(
                models.User.staff_id == payload.staff_id, models.User.user_id != user_id
            ).first()
            if clash:
                raise HTTPException(status_code=409, detail=f"Staff ID '{payload.staff_id}' is already in use")
            staff.staff_id = payload.staff_id
        else:
            staff.staff_id = None
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name can't be empty")
        staff.name = name
    if payload.academic_title is not None:
        staff.academic_title = payload.academic_title
    if payload.specialization is not None:
        staff.specialization = payload.specialization
    if payload.phone is not None:
        staff.phone = payload.phone
    if payload.status is not None:
        staff.status = payload.status
    db.commit()
    db.refresh(staff)
    audit_service.log(db, actor=admin, action="update", resource_type="user", resource_id=staff.user_id,
                       resource_label=staff.name, description="staff profile fields edited")
    return staff


@router.post("/import")
async def import_users(role: str = Form(...), file: UploadFile = File(...),
                        db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    """Bulk-creates TAs or doctors from an uploaded .xlsx — for importing a
    whole staff roster at once instead of adding each one by hand. Expected
    columns (header row, any order, case-insensitive): Name (required), and
    optionally Email (auto-generated as name@aiu.is if blank), Password
    (a random one is generated if blank), and Faculty (created if it
    doesn't already exist). Generated passwords are returned in the
    response since they can't be recovered later — bcrypt only stores the
    hash — so the admin needs to copy them out immediately to hand out.
    """
    if role not in ("instructor", "doctor"):
        raise HTTPException(status_code=400, detail="role must be 'instructor' or 'doctor'")
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx (Excel) file")

    contents = await file.read()
    try:
        wb = load_workbook(io.BytesIO(contents), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Couldn't read that file — is it a valid .xlsx?")
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="That sheet is empty")

    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]

    def find_col(aliases):
        for i, h in enumerate(header):
            if h in aliases:
                return i
        return None

    col_name = find_col({"name", "full name", "fullname"})
    col_email = find_col({"email"})
    col_password = find_col({"password"})
    col_faculty = find_col({"faculty"})

    if col_name is None:
        raise HTTPException(
            status_code=400,
            detail="Sheet needs a Name column (Email, Password, and Faculty are optional).",
        )

    def cell(row, idx):
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None

    existing_emails = {e for (e,) in db.query(models.User.email).all()}
    faculty_by_name = {f.name: f for f in db.query(models.Faculty).all()}

    created, skipped, errors = [], [], []
    for row_num, row in enumerate(rows[1:], start=2):
        name = cell(row, col_name)
        if not name:
            errors.append(f"Row {row_num}: missing name — skipped")
            continue

        email = (cell(row, col_email) or _suggest_email(name)).lower()
        if email in existing_emails:
            skipped.append(f"Row {row_num}: email '{email}' already exists — skipped")
            continue

        password = cell(row, col_password) or _random_password()

        faculty_name = cell(row, col_faculty)
        faculty_id = None
        if faculty_name:
            faculty = faculty_by_name.get(faculty_name)
            if not faculty:
                faculty = models.Faculty(name=faculty_name)
                db.add(faculty)
                db.flush()
                faculty_by_name[faculty_name] = faculty
            faculty_id = faculty.faculty_id

        # A scope-restricted admin may only import staff into a college
        # they're authorized for — mirrors create_user's require_faculty_access
        # check below, closing a gap where bulk import bypassed it entirely.
        if faculty_id is not None:
            try:
                security.require_faculty_access(faculty_id, admin, db)
            except HTTPException:
                errors.append(f"Row {row_num}: not authorized to add staff to '{faculty_name}' — skipped")
                continue
        elif security.is_scope_restricted(admin, db):
            errors.append(f"Row {row_num}: missing Faculty column — required for a scoped admin — skipped")
            continue

        user = models.User(
            name=name, email=email, role=role,
            password_hash=security.hash_password(password),
            faculty_id=faculty_id,
        )
        db.add(user)
        existing_emails.add(email)
        created.append({"name": name, "email": email, "password": password})

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


# ---------- Door assignments (which doors a TA is allowed to request) ----------

@router.get("/{user_id}/doors", response_model=List[schemas.DoorAssignmentOut])
def list_door_assignments(user_id: int, db: Session = Depends(get_db),
                           admin=Depends(security.require_admin)):
    target = db.query(models.User).filter(models.User.user_id == user_id).first()
    if target:
        security.require_staff_access(target, admin, db)
    return (
        db.query(models.DoorAssignment)
        .filter(models.DoorAssignment.instructor_id == user_id)
        .all()
    )


@router.post("/{user_id}/doors", response_model=schemas.DoorAssignmentOut, status_code=201)
def add_door_assignment(user_id: int, payload: schemas.DoorAssignmentCreate,
                         db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    target = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    security.require_staff_access(target, admin, db)
    door = db.query(models.Door).filter(models.Door.door_id == payload.door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")

    existing = (
        db.query(models.DoorAssignment)
        .filter(
            models.DoorAssignment.instructor_id == user_id,
            models.DoorAssignment.door_id == payload.door_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="This door is already assigned to this user")

    assignment = models.DoorAssignment(instructor_id=user_id, door_id=payload.door_id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    """Removes a TA/doctor (or any user) entirely — not just a door
    assignment. This touches every table with a foreign key into `users`
    (see app/models.py), following the same
    dependency-check-then-cascade/nullify pattern already used by
    delete_department/delete_course/delete_faculty in academic.py:

    - Blocked outright (400, audit-critical, never silently deleted):
      EmergencyOverride rows this user created (created_by_id). An
      override's authorizing admin must remain traceable for as long as
      the override record exists.
    - Cascade-deleted (meaningless once the person is gone):
      DoorAssignment, CourseAssignment, AccessWindow (rows this user
      themself holds), AdminScope, PasswordResetRequest (rows this user
      themself filed).
    - Nullified (kept for audit/history, just unlinked from a person):
      Credential.user_id, AccessWindow.created_by_id, AccessEvent.user_id,
      Alert.requested_by, PasswordResetRequest.resolved_by,
      EmergencyOverride.revoked_by_id.
    """
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="You can't delete your own account while logged in as it")

    target = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.role == "admin":
        # Deleting another admin account is itself a scope grant/privilege
        # decision — same "unrestricted admins only" guard used for
        # admin-scope management in academic.py, not a new authorization
        # concept.
        if security.is_scope_restricted(admin, db):
            raise HTTPException(status_code=403, detail="Only an unrestricted admin can delete an admin account")
        remaining_admins = db.query(models.User).filter(
            models.User.role == "admin", models.User.user_id != user_id
        ).count()
        if remaining_admins == 0:
            raise HTTPException(status_code=400, detail="Can't delete the last remaining admin account")
    else:
        security.require_staff_access(target, admin, db)

    created_overrides = db.query(models.EmergencyOverride).filter(
        models.EmergencyOverride.created_by_id == user_id
    ).count()
    if created_overrides:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Can't delete '{target.name}' — they authorized {created_overrides} emergency "
                "override(s) that must stay attributable. Those records can't be reassigned."
            ),
        )

    # Cascade-delete: rows that only make sense as this person's own record.
    db.query(models.DoorAssignment).filter(models.DoorAssignment.instructor_id == user_id).delete()
    db.query(models.CourseAssignment).filter(models.CourseAssignment.user_id == user_id).delete()
    db.query(models.AccessWindow).filter(models.AccessWindow.user_id == user_id).delete()
    db.query(models.AdminScope).filter(models.AdminScope.user_id == user_id).delete()
    db.query(models.PasswordResetRequest).filter(models.PasswordResetRequest.user_id == user_id).delete()

    # Nullify: audit/history rows that outlive the person.
    db.query(models.Credential).filter(models.Credential.user_id == user_id).update({"user_id": None})
    db.query(models.AccessWindow).filter(models.AccessWindow.created_by_id == user_id).update({"created_by_id": None})
    db.query(models.AccessEvent).filter(models.AccessEvent.user_id == user_id).update({"user_id": None})
    db.query(models.Alert).filter(models.Alert.requested_by == user_id).update({"requested_by": None})
    db.query(models.PasswordResetRequest).filter(models.PasswordResetRequest.resolved_by == user_id).update({"resolved_by": None})
    db.query(models.EmergencyOverride).filter(models.EmergencyOverride.revoked_by_id == user_id).update({"revoked_by_id": None})

    target_name, target_email, target_role = target.name, target.email, target.role
    db.delete(target)
    db.commit()
    audit_service.log(db, actor=admin, action="delete", resource_type="user", resource_id=user_id,
                       resource_label=f"{target_name} ({target_email})", description=f"role={target_role}")


@router.delete("/{user_id}/doors/{assignment_id}", status_code=204)
def remove_door_assignment(user_id: int, assignment_id: int, db: Session = Depends(get_db),
                            admin=Depends(security.require_admin)):
    target = db.query(models.User).filter(models.User.user_id == user_id).first()
    if target:
        security.require_staff_access(target, admin, db)
    assignment = (
        db.query(models.DoorAssignment)
        .filter(
            models.DoorAssignment.assignment_id == assignment_id,
            models.DoorAssignment.instructor_id == user_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()
