from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service

router = APIRouter(prefix="/api/faculties", tags=["faculties"])


def _with_counts(db: Session, faculty: models.Faculty) -> schemas.FacultyOut:
    """Rollup counts for the College overview screen — computed on read from
    the same tables StaffScopeView already queries (Department/User/Course),
    never a separately-maintained counter that could drift or a fake number."""
    out = schemas.FacultyOut.model_validate(faculty)
    out.departments_count = db.query(models.Department).filter(models.Department.faculty_id == faculty.faculty_id).count()
    out.doctors_count = db.query(models.User).filter(
        models.User.faculty_id == faculty.faculty_id, models.User.role == "doctor"
    ).count()
    out.tas_count = db.query(models.User).filter(
        models.User.faculty_id == faculty.faculty_id, models.User.role == "instructor"
    ).count()
    out.courses_count = (
        db.query(models.Course)
        .join(models.Department, models.Course.department_id == models.Department.department_id)
        .filter(models.Department.faculty_id == faculty.faculty_id)
        .count()
    )
    return out


@router.get("", response_model=List[schemas.FacultyOut])
def list_faculties(db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    q = db.query(models.Faculty)
    if user.role == "admin":
        allowed = security.authorized_faculty_ids(user, db)
        if allowed is not None:
            q = q.filter(models.Faculty.faculty_id.in_(allowed))
    faculties = q.order_by(models.Faculty.name).all()
    return [_with_counts(db, f) for f in faculties]


@router.get("/{faculty_id}", response_model=schemas.FacultyOut)
def get_faculty(faculty_id: int, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    if user.role == "admin":
        security.require_faculty_access(faculty_id, user, db)
    faculty = db.get(models.Faculty, faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="College not found")
    return _with_counts(db, faculty)


@router.post("", response_model=schemas.FacultyOut, status_code=201)
def create_faculty(payload: schemas.FacultyCreate, db: Session = Depends(get_db),
                    admin=Depends(security.require_admin)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Faculty name is required")
    existing = db.query(models.Faculty).filter(models.Faculty.name == name).first()
    if existing:
        return _with_counts(db, existing)
    code = (payload.code or "").strip() or None
    if code:
        code_clash = db.query(models.Faculty).filter(models.Faculty.code == code).first()
        if code_clash:
            raise HTTPException(status_code=409, detail=f"College code '{code}' is already in use")
    faculty = models.Faculty(name=name, code=code, description=payload.description)
    db.add(faculty)
    db.commit()
    db.refresh(faculty)
    audit_service.log(db, actor=admin, action="create", resource_type="faculty", resource_id=faculty.faculty_id,
                       resource_label=faculty.name)
    return _with_counts(db, faculty)


@router.put("/{faculty_id}", response_model=schemas.FacultyOut)
def update_faculty(faculty_id: int, payload: schemas.FacultyUpdate, db: Session = Depends(get_db),
                    admin=Depends(security.require_admin)):
    security.require_faculty_access(faculty_id, admin, db)
    faculty = db.get(models.Faculty, faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="College not found")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="College name is required")
        existing = db.query(models.Faculty).filter(models.Faculty.name == name, models.Faculty.faculty_id != faculty_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Another college already has that name")
        faculty.name = name
    if payload.code is not None:
        code = payload.code.strip() or None
        if code:
            code_clash = db.query(models.Faculty).filter(
                models.Faculty.code == code, models.Faculty.faculty_id != faculty_id
            ).first()
            if code_clash:
                raise HTTPException(status_code=409, detail=f"College code '{code}' is already in use")
        faculty.code = code
    if payload.description is not None:
        faculty.description = payload.description
    if payload.status is not None:
        faculty.status = payload.status
    db.commit()
    db.refresh(faculty)
    audit_service.log(db, actor=admin, action="update", resource_type="faculty", resource_id=faculty.faculty_id,
                       resource_label=faculty.name)
    return _with_counts(db, faculty)


def _faculty_dependents(db: Session, faculty_id: int) -> dict:
    """Everything that would be orphaned/dangling if this college were
    deleted. The data model has no cascading-delete rule for any of these
    (Department/User/AdminScope/OperationalScope all just hold a plain FK),
    so deletion must be explicitly blocked while any of them exist rather
    than silently cascading or leaving dangling references."""
    return {
        "departments": db.query(models.Department).filter(models.Department.faculty_id == faculty_id).count(),
        "staff": db.query(models.User).filter(models.User.faculty_id == faculty_id).count(),
        "admin_scopes": db.query(models.AdminScope).filter(models.AdminScope.faculty_id == faculty_id).count(),
        "operational_scopes": db.query(models.OperationalScope).filter(models.OperationalScope.faculty_id == faculty_id).count(),
    }


@router.delete("/{faculty_id}", status_code=204)
def delete_faculty(faculty_id: int, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    security.require_faculty_access(faculty_id, admin, db)
    faculty = db.get(models.Faculty, faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="College not found")
    dependents = _faculty_dependents(db, faculty_id)
    blocking = {k: v for k, v in dependents.items() if v > 0}
    if blocking:
        parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in blocking.items())
        raise HTTPException(
            status_code=409,
            detail=f"Can't delete '{faculty.name}' — it still has {parts}. Reassign or remove those first.",
        )
    faculty_name = faculty.name
    db.delete(faculty)
    db.commit()
    audit_service.log(db, actor=admin, action="delete", resource_type="faculty", resource_id=faculty_id,
                       resource_label=faculty_name)


# ---------------------------------------------------------------------------
# High-risk cascade delete — a College that STILL has dependent academic data
# (departments/staff/courses/etc). The plain DELETE above stays exactly as it
# was (still blocks on any dependent, used by the "Manage Colleges" modal for
# the ordinary/empty case). This is a deliberately separate, more dangerous
# operation: it inspects the real FK graph, deletes/detaches through it in
# one transaction, and requires re-proving identity (password) — not just an
# "are you sure" — before it touches anything.
#
# Deletion/detachment order, derived from the actual FK relationships in
# models.py (not invented):
#   CourseAssignment (FK course_id -> Course, which is FK'd to this college's
#     departments) is the leaf — delete first.
#   Course (FK department_id) — delete next, now nothing references it.
#   User.faculty_id/department_id (staff) — NEVER deleted; cleared back to
#     NULL, exactly the semantics of the existing unassign endpoint. The
#     account, login, audit history, and door assignments are untouched.
#     (Any active CourseAssignment a staff member had under this college was
#     already removed above — course-assignment validation elsewhere in this
#     codebase requires staff and course to share a college, so no staff
#     member here can have a *surviving* assignment outside this college's
#     courses that would need separate handling.)
#   AdminScope rows granting this faculty or one of its departments — deleted
#     (the thing they grant access to no longer exists).
#   OperationalScope rows pointing at this faculty — deleted, same reason.
#   Department — deleted once its courses/scopes are gone.
#   Faculty — deleted last.
# AuditLog is never touched: resource_id there is a plain int, not a foreign
# key, so historical rows about this college/its departments/courses/staff
# stay exactly as they are after the college is gone.
@router.get("/{faculty_id}/deletion-impact", response_model=schemas.FacultyDeletionImpact)
def get_faculty_deletion_impact(faculty_id: int, db: Session = Depends(get_db),
                                 admin=Depends(security.require_unrestricted_admin)):
    faculty = db.get(models.Faculty, faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="College not found")
    department_ids = [d.department_id for d in db.query(models.Department.department_id).filter(
        models.Department.faculty_id == faculty_id
    )]
    course_ids = []
    if department_ids:
        course_ids = [c.course_id for c in db.query(models.Course.course_id).filter(
            models.Course.department_id.in_(department_ids)
        )]
    course_assignments = 0
    if course_ids:
        course_assignments = db.query(models.CourseAssignment).filter(
            models.CourseAssignment.course_id.in_(course_ids)
        ).count()
    _scope_cond = models.AdminScope.faculty_id == faculty_id
    if department_ids:
        _scope_cond = _scope_cond | models.AdminScope.department_id.in_(department_ids)
    admin_scopes = db.query(models.AdminScope).filter(_scope_cond).count()
    return schemas.FacultyDeletionImpact(
        faculty_id=faculty.faculty_id,
        name=faculty.name,
        departments=len(department_ids),
        doctors=db.query(models.User).filter(models.User.faculty_id == faculty_id, models.User.role == "doctor").count(),
        teaching_assistants=db.query(models.User).filter(models.User.faculty_id == faculty_id, models.User.role == "instructor").count(),
        courses=len(course_ids),
        course_assignments=course_assignments,
        admin_scopes=admin_scopes,
        operational_scopes=db.query(models.OperationalScope).filter(models.OperationalScope.faculty_id == faculty_id).count(),
    )


@router.post("/{faculty_id}/cascade-delete", status_code=200)
def cascade_delete_faculty(
    faculty_id: int,
    payload: schemas.FacultyDeleteConfirm,
    db: Session = Depends(get_db),
    admin=Depends(security.require_unrestricted_admin),
):
    """The actual high-risk destructive operation. RBAC (unrestricted-admin
    only), exact-name confirmation, and password re-verification are ALL
    enforced here, server-side — the frontend only collects the two fields
    and displays whatever this endpoint says. Nothing is deleted unless both
    checks pass; if either fails, a failure AuditLog row is written (never
    containing the password) and nothing else changes."""
    faculty = db.get(models.Faculty, faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="College not found")

    if payload.confirm_name.strip() != faculty.name:
        audit_service.log(
            db, actor=admin, action="delete", resource_type="faculty", resource_id=faculty_id,
            resource_label=faculty.name, result="failure",
            description="Cascade-delete rejected — typed college name did not match",
        )
        raise HTTPException(status_code=400, detail="The college name you typed doesn't match. Deletion cancelled.")

    if not security.verify_password(payload.password, admin.password_hash):
        audit_service.log(
            db, actor=admin, action="delete", resource_type="faculty", resource_id=faculty_id,
            resource_label=faculty.name, result="failure",
            description="Cascade-delete rejected — password verification failed",
        )
        raise HTTPException(status_code=401, detail="Incorrect password. Deletion cancelled.")

    faculty_name = faculty.name
    try:
        department_ids = [d.department_id for d in db.query(models.Department.department_id).filter(
            models.Department.faculty_id == faculty_id
        )]
        course_ids = []
        if department_ids:
            course_ids = [c.course_id for c in db.query(models.Course.course_id).filter(
                models.Course.department_id.in_(department_ids)
            )]

        if course_ids:
            db.query(models.CourseAssignment).filter(
                models.CourseAssignment.course_id.in_(course_ids)
            ).delete(synchronize_session=False)
            db.query(models.Course).filter(
                models.Course.course_id.in_(course_ids)
            ).delete(synchronize_session=False)

        # Detach staff — clear, never delete. Same semantics as
        # POST /api/users/{id}/unassign, applied in bulk within this
        # transaction rather than calling that endpoint N times.
        db.query(models.User).filter(models.User.faculty_id == faculty_id).update(
            {models.User.faculty_id: None, models.User.department_id: None}, synchronize_session=False
        )

        _scope_cond = models.AdminScope.faculty_id == faculty_id
        if department_ids:
            _scope_cond = _scope_cond | models.AdminScope.department_id.in_(department_ids)
        db.query(models.AdminScope).filter(_scope_cond).delete(synchronize_session=False)

        db.query(models.OperationalScope).filter(
            models.OperationalScope.faculty_id == faculty_id
        ).delete(synchronize_session=False)

        if department_ids:
            db.query(models.Department).filter(
                models.Department.department_id.in_(department_ids)
            ).delete(synchronize_session=False)

        db.delete(faculty)
        db.commit()
    except Exception:
        db.rollback()
        audit_service.log(
            db, actor=admin, action="delete", resource_type="faculty", resource_id=faculty_id,
            resource_label=faculty_name, result="failure",
            description="Cascade-delete failed — transaction rolled back, no data was deleted",
        )
        raise HTTPException(status_code=500, detail="Deletion failed and was rolled back. No data was changed.")

    audit_service.log(
        db, actor=admin, action="delete", resource_type="faculty", resource_id=faculty_id,
        resource_label=faculty_name, result="success",
        description=f"Deleted college {faculty_name} and its dependent academic records",
    )
    return {"detail": f"'{faculty_name}' and its dependent academic records were deleted."}
