"""
Organizational hierarchy: College (existing Faculty) -> Department -> Staff
(existing User, role doctor/instructor) -> Course -> CourseAssignment, plus
AdminScope-based authorization.

Every list/detail endpoint here applies the acting admin's organizational
scope (see app/security.py's authorized_faculty_ids/require_*_access) —
never only hidden in the frontend. An unrestricted admin (no AdminScope
rows — every admin that existed before this feature) sees everything,
exactly as before.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service

router = APIRouter(tags=["academic"])


def _department_with_counts(db: Session, dept: models.Department) -> schemas.DepartmentOut:
    out = schemas.DepartmentOut.model_validate(dept)
    out.doctors_count = db.query(models.User).filter(
        models.User.department_id == dept.department_id, models.User.role == "doctor"
    ).count()
    out.tas_count = db.query(models.User).filter(
        models.User.department_id == dept.department_id, models.User.role == "instructor"
    ).count()
    out.courses_count = db.query(models.Course).filter(models.Course.department_id == dept.department_id).count()
    return out


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
@router.get("/api/departments", response_model=List[schemas.DepartmentOut])
def list_departments(faculty_id: Optional[int] = None, db: Session = Depends(get_db),
                      user=Depends(security.get_current_user)):
    q = db.query(models.Department)
    if faculty_id is not None:
        if user.role == "admin":
            security.require_faculty_access(faculty_id, user, db)
        q = q.filter(models.Department.faculty_id == faculty_id)
    elif user.role == "admin":
        allowed = security.authorized_faculty_ids(user, db)
        if allowed is not None:
            q = q.filter(models.Department.faculty_id.in_(allowed))
    depts = q.order_by(models.Department.name).all()
    return [_department_with_counts(db, d) for d in depts]


@router.get("/api/departments/{department_id}", response_model=schemas.DepartmentOut)
def get_department(department_id: int, db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    dept = db.get(models.Department, department_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    if user.role == "admin":
        security.require_department_access(dept, user, db)
    return _department_with_counts(db, dept)


@router.post("/api/departments", response_model=schemas.DepartmentOut, status_code=201)
def create_department(payload: schemas.DepartmentCreate, db: Session = Depends(get_db),
                       admin=Depends(security.require_admin)):
    security.require_faculty_access(payload.faculty_id, admin, db)
    faculty = db.get(models.Faculty, payload.faculty_id)
    if not faculty:
        raise HTTPException(status_code=404, detail="College not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name is required")
    existing = db.query(models.Department).filter(
        models.Department.faculty_id == payload.faculty_id, models.Department.name == name
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="That department already exists in this college")
    dept = models.Department(
        faculty_id=payload.faculty_id, name=name,
        code=(payload.code or "").strip() or None, description=payload.description,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    audit_service.log(db, actor=admin, action="create", resource_type="department", resource_id=dept.department_id,
                       resource_label=dept.name)
    return _department_with_counts(db, dept)


@router.put("/api/departments/{department_id}", response_model=schemas.DepartmentOut)
def update_department(department_id: int, payload: schemas.DepartmentUpdate, db: Session = Depends(get_db),
                       admin=Depends(security.require_admin)):
    dept = db.get(models.Department, department_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    security.require_department_access(dept, admin, db)
    if payload.faculty_id is not None:
        security.require_faculty_access(payload.faculty_id, admin, db)
        dept.faculty_id = payload.faculty_id
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Department name can't be empty")
        dept.name = name
    if payload.code is not None:
        dept.code = payload.code.strip() or None
    if payload.description is not None:
        dept.description = payload.description
    if payload.status is not None:
        dept.status = payload.status
    db.commit()
    db.refresh(dept)
    audit_service.log(db, actor=admin, action="update", resource_type="department", resource_id=dept.department_id,
                       resource_label=dept.name)
    return _department_with_counts(db, dept)


def _department_dependents(db: Session, department_id: int) -> dict:
    """Same rationale as faculties.py::_faculty_dependents — nothing here
    cascades at the DB level, so deletion must be blocked while any of
    these exist rather than silently orphaning them."""
    return {
        "courses": db.query(models.Course).filter(models.Course.department_id == department_id).count(),
        "staff": db.query(models.User).filter(models.User.department_id == department_id).count(),
        "admin_scopes": db.query(models.AdminScope).filter(models.AdminScope.department_id == department_id).count(),
    }


@router.delete("/api/departments/{department_id}", status_code=204)
def delete_department(department_id: int, db: Session = Depends(get_db),
                       admin=Depends(security.require_admin)):
    dept = db.get(models.Department, department_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    security.require_department_access(dept, admin, db)
    dependents = _department_dependents(db, department_id)
    blocking = {k: v for k, v in dependents.items() if v > 0}
    if blocking:
        parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in blocking.items())
        raise HTTPException(
            status_code=409,
            detail=f"Can't delete '{dept.name}' — it still has {parts}. Reassign or remove those first.",
        )
    dept_name = dept.name
    db.delete(dept)
    db.commit()
    audit_service.log(db, actor=admin, action="delete", resource_type="department", resource_id=department_id,
                       resource_label=dept_name)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
@router.get("/api/courses", response_model=List[schemas.CourseOut])
def list_courses(department_id: Optional[int] = None, faculty_id: Optional[int] = None,
                  db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    q = db.query(models.Course)
    if department_id is not None:
        dept = db.get(models.Department, department_id)
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        if user.role == "admin":
            security.require_department_access(dept, user, db)
        q = q.filter(models.Course.department_id == department_id)
    else:
        if faculty_id is not None:
            q = q.join(models.Department).filter(models.Department.faculty_id == faculty_id)
        if user.role == "admin":
            allowed = security.authorized_faculty_ids(user, db)
            if allowed is not None:
                q = q.join(models.Department, models.Course.department_id == models.Department.department_id) \
                     .filter(models.Department.faculty_id.in_(allowed))
    return q.order_by(models.Course.code).all()


@router.post("/api/courses", response_model=schemas.CourseOut, status_code=201)
def create_course(payload: schemas.CourseCreate, db: Session = Depends(get_db),
                   admin=Depends(security.require_admin)):
    dept = db.get(models.Department, payload.department_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    security.require_department_access(dept, admin, db)
    code = payload.code.strip()
    if not code or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Course code and name are required")
    existing = db.query(models.Course).filter(
        models.Course.department_id == payload.department_id, models.Course.code == code
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="That course code already exists in this department")
    course = models.Course(
        department_id=payload.department_id, code=code, name=payload.name.strip(),
        credit_hours=payload.credit_hours, level=payload.level, semester=payload.semester,
        description=payload.description,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    audit_service.log(db, actor=admin, action="create", resource_type="course", resource_id=course.course_id,
                       resource_label=f"{course.code} — {course.name}")
    return course


@router.put("/api/courses/{course_id}", response_model=schemas.CourseOut)
def update_course(course_id: int, payload: schemas.CourseUpdate, db: Session = Depends(get_db),
                   admin=Depends(security.require_admin)):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    security.require_department_access(course.department, admin, db)
    if payload.department_id is not None:
        new_dept = db.get(models.Department, payload.department_id)
        if not new_dept:
            raise HTTPException(status_code=404, detail="Department not found")
        security.require_department_access(new_dept, admin, db)
        course.department_id = payload.department_id
    if payload.code is not None:
        course.code = payload.code.strip()
    if payload.name is not None:
        course.name = payload.name.strip()
    if payload.credit_hours is not None:
        course.credit_hours = payload.credit_hours
    if payload.level is not None:
        course.level = payload.level
    if payload.semester is not None:
        course.semester = payload.semester
    if payload.description is not None:
        course.description = payload.description
    if payload.status is not None:
        course.status = payload.status
    db.commit()
    db.refresh(course)
    audit_service.log(db, actor=admin, action="update", resource_type="course", resource_id=course.course_id,
                       resource_label=f"{course.code} — {course.name}")
    return course


def _course_dependents(db: Session, course_id: int) -> dict:
    """Same rationale as faculties.py::_faculty_dependents /
    academic.py::_department_dependents — CourseAssignment and Schedule
    (via course_ref_id) both just hold a plain FK to Course with no
    cascading rule, so deletion must be blocked while either exists rather
    than silently orphaning them (an orphaned Schedule.course_ref_id would
    also quietly break the schedule-derived access checks in
    access_authorization_service.py)."""
    return {
        "staff assignments": db.query(models.CourseAssignment).filter(models.CourseAssignment.course_id == course_id).count(),
        "schedules": db.query(models.Schedule).filter(models.Schedule.course_ref_id == course_id).count(),
    }


@router.delete("/api/courses/{course_id}", status_code=204)
def delete_course(course_id: int, db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    security.require_department_access(course.department, admin, db)
    dependents = _course_dependents(db, course_id)
    blocking = {k: v for k, v in dependents.items() if v > 0}
    if blocking:
        parts = ", ".join(f"{v} {k}" for k, v in blocking.items())
        raise HTTPException(
            status_code=409,
            detail=f"Can't delete '{course.code}' — it still has {parts}. Remove those first.",
        )
    course_label = f"{course.code} — {course.name}"
    db.delete(course)
    db.commit()
    audit_service.log(db, actor=admin, action="delete", resource_type="course", resource_id=course_id,
                       resource_label=course_label)


# ---------------------------------------------------------------------------
# Course assignments (which Doctor/TA teaches/assists which Course)
# ---------------------------------------------------------------------------
@router.get("/api/courses/{course_id}/assignments", response_model=List[schemas.CourseAssignmentOut])
def list_course_assignments(course_id: int, db: Session = Depends(get_db),
                             user=Depends(security.get_current_user)):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if user.role == "admin":
        security.require_department_access(course.department, user, db)
    return db.query(models.CourseAssignment).filter(models.CourseAssignment.course_id == course_id).all()


def _validate_assignment_schedule(db: Session, course: models.Course, schedule_id: Optional[int]) -> None:
    """A CourseAssignment reuses the existing Schedule table for room+timing
    (see models.py::CourseAssignment docstring) rather than adding a
    duplicate door_id column. Guard against pointing an assignment at a
    schedule that belongs to a different course, which would make the
    room/time shown for this assignment misleading."""
    if schedule_id is None:
        return
    schedule = db.get(models.Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if schedule.course_ref_id is not None and schedule.course_ref_id != course.course_id:
        raise HTTPException(
            status_code=409,
            detail="That schedule is already linked to a different course",
        )


@router.post("/api/courses/{course_id}/assignments", response_model=schemas.CourseAssignmentOut, status_code=201)
def assign_staff_to_course(course_id: int, payload: schemas.CourseAssignmentCreate, db: Session = Depends(get_db),
                            admin=Depends(security.require_admin)):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    security.require_department_access(course.department, admin, db)
    staff = db.get(models.User, payload.user_id)
    if not staff or staff.role not in ("doctor", "instructor"):
        raise HTTPException(status_code=404, detail="Staff member (doctor/TA) not found")
    security.require_staff_access(staff, admin, db)

    # Business rule: a course assignment must stay inside the course's own
    # department/college — a doctor from Department A cannot be assigned to
    # teach a Department B course just because an admin has access to both.
    # Staff with no department/faculty set yet (freshly imported, not yet
    # scoped) are left alone here since update_staff_scope is the intended
    # place to fix that, not a silent block on every future assignment.
    if staff.department_id is not None and staff.department_id != course.department_id:
        raise HTTPException(
            status_code=409,
            detail=f"{staff.name} belongs to a different department than this course — reassign their department first, or choose a different course.",
        )
    if staff.department_id is None and staff.faculty_id is not None and staff.faculty_id != course.department.faculty_id:
        raise HTTPException(
            status_code=409,
            detail=f"{staff.name} belongs to a different college than this course.",
        )

    existing = db.query(models.CourseAssignment).filter(
        models.CourseAssignment.course_id == course_id, models.CourseAssignment.user_id == payload.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="That staff member is already assigned to this course")

    _validate_assignment_schedule(db, course, payload.schedule_id)

    assignment = models.CourseAssignment(
        course_id=course_id, user_id=payload.user_id,
        section=payload.section, semester=payload.semester, academic_year=payload.academic_year,
        schedule_id=payload.schedule_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    audit_service.log(db, actor=admin, action="create", resource_type="course_assignment",
                       resource_id=assignment.assignment_id,
                       resource_label=f"{staff.name} → {course.code}")
    return assignment


@router.put("/api/courses/{course_id}/assignments/{assignment_id}", response_model=schemas.CourseAssignmentOut)
def update_course_assignment(course_id: int, assignment_id: int, payload: schemas.CourseAssignmentUpdate,
                              db: Session = Depends(get_db), admin=Depends(security.require_admin)):
    assignment = db.get(models.CourseAssignment, assignment_id)
    if not assignment or assignment.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    security.require_department_access(assignment.course.department, admin, db)

    if payload.schedule_id is not None:
        _validate_assignment_schedule(db, assignment.course, payload.schedule_id)
        assignment.schedule_id = payload.schedule_id
    if payload.section is not None:
        assignment.section = payload.section
    if payload.semester is not None:
        assignment.semester = payload.semester
    if payload.academic_year is not None:
        assignment.academic_year = payload.academic_year
    if payload.status is not None:
        assignment.status = payload.status
    db.commit()
    db.refresh(assignment)
    audit_service.log(db, actor=admin, action="update", resource_type="course_assignment",
                       resource_id=assignment.assignment_id,
                       resource_label=f"{assignment.user.name} → {assignment.course.code}")
    return assignment


@router.delete("/api/courses/{course_id}/assignments/{assignment_id}", status_code=204)
def remove_course_assignment(course_id: int, assignment_id: int, db: Session = Depends(get_db),
                              admin=Depends(security.require_admin)):
    assignment = db.get(models.CourseAssignment, assignment_id)
    if not assignment or assignment.course_id != course_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    security.require_department_access(assignment.course.department, admin, db)
    assignment_label = f"{assignment.user.name} → {assignment.course.code}"
    db.delete(assignment)
    db.commit()
    audit_service.log(db, actor=admin, action="delete", resource_type="course_assignment",
                       resource_id=assignment_id, resource_label=assignment_label)


# ---------------------------------------------------------------------------
# Admin scopes (grant/revoke which colleges/departments a given admin can manage)
#
# Deliberately restricted to UNRESTRICTED admins only — a scoped admin must
# never be able to grant themselves (or anyone else) a wider scope than they
# hold, which would be a privilege-escalation hole.
# ---------------------------------------------------------------------------
def _require_unrestricted_admin(admin=Depends(security.require_admin), db: Session = Depends(get_db)):
    if security.is_scope_restricted(admin, db):
        raise HTTPException(status_code=403, detail="Only an unrestricted admin can manage admin scopes")
    return admin


@router.get("/api/admin-scopes", response_model=List[schemas.AdminScopeOut])
def list_admin_scopes(user_id: Optional[int] = None, db: Session = Depends(get_db),
                       _admin=Depends(_require_unrestricted_admin)):
    q = db.query(models.AdminScope)
    if user_id is not None:
        q = q.filter(models.AdminScope.user_id == user_id)
    return q.all()


@router.post("/api/admin-scopes", response_model=schemas.AdminScopeOut, status_code=201)
def create_admin_scope(payload: schemas.AdminScopeCreate, db: Session = Depends(get_db),
                        _admin=Depends(_require_unrestricted_admin)):
    """Phase 12: audited (action="grant") — this is exactly the kind of
    privilege-affecting admin mutation AuditLog exists for."""
    target = db.get(models.User, payload.user_id)
    if not target or target.role != "admin":
        raise HTTPException(status_code=404, detail="Admin user not found")
    if payload.faculty_id is None and payload.operational_scope_id is None:
        raise HTTPException(status_code=400, detail="Grant needs either a faculty_id (academic) or an operational_scope_id (infrastructure)")
    if payload.faculty_id is not None:
        if not db.get(models.Faculty, payload.faculty_id):
            raise HTTPException(status_code=404, detail="College not found")
        if payload.department_id is not None:
            dept = db.get(models.Department, payload.department_id)
            if not dept or dept.faculty_id != payload.faculty_id:
                raise HTTPException(status_code=400, detail="Department doesn't belong to that college")
    if payload.operational_scope_id is not None and not db.get(models.OperationalScope, payload.operational_scope_id):
        raise HTTPException(status_code=404, detail="Operational scope not found")
    scope = models.AdminScope(user_id=payload.user_id, faculty_id=payload.faculty_id,
                               department_id=payload.department_id,
                               operational_scope_id=payload.operational_scope_id)
    db.add(scope)
    db.commit()
    db.refresh(scope)
    label_parts = [target.email]
    if scope.faculty_id is not None:
        label_parts.append(f"faculty={scope.faculty_id}" + (f"/dept={scope.department_id}" if scope.department_id else ""))
    if scope.operational_scope_id is not None:
        label_parts.append(f"operational_scope={scope.operational_scope_id}")
    audit_service.log(db, actor=_admin, action="grant", resource_type="admin_scope", resource_id=scope.scope_id,
                       resource_label=" ".join(label_parts))
    return scope


# ---------------------------------------------------------------------------
# Operational scopes (Phase 3) — HVAC / Electrical / Residential /
# Administrative / Engineering areas. An "ACADEMIC" scope_type is
# deliberately not created here as a standalone row: the academic hierarchy
# stays Faculty->Department->Staff exactly as implemented, and any admin
# grant for it uses admin_scopes.faculty_id directly (see create_admin_scope
# above), not an OperationalScope row — this endpoint is only for the
# non-academic areas that had no existing model to hang authorization off.
# ---------------------------------------------------------------------------
@router.get("/api/operational-scopes", response_model=List[schemas.OperationalScopeOut])
def list_operational_scopes(db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    q = db.query(models.OperationalScope)
    if user.role == "admin":
        allowed = security.authorized_operational_scope_ids(user, db)
        if allowed is not None:
            q = q.filter(models.OperationalScope.scope_id.in_(allowed))
    return q.order_by(models.OperationalScope.name).all()


@router.post("/api/operational-scopes", response_model=schemas.OperationalScopeOut, status_code=201)
def create_operational_scope(payload: schemas.OperationalScopeCreate, db: Session = Depends(get_db),
                              admin=Depends(_require_unrestricted_admin)):
    if payload.scope_type not in ("HVAC", "ELECTRICAL", "RESIDENTIAL", "ADMINISTRATIVE", "ENGINEERING"):
        raise HTTPException(status_code=400,
                             detail="scope_type must be one of HVAC, ELECTRICAL, RESIDENTIAL, ADMINISTRATIVE, ENGINEERING")
    if payload.building_id is not None and not db.get(models.Building, payload.building_id):
        raise HTTPException(status_code=404, detail="Building not found")
    scope = models.OperationalScope(name=payload.name.strip(), scope_type=payload.scope_type,
                                     building_id=payload.building_id, description=payload.description)
    db.add(scope)
    db.commit()
    db.refresh(scope)
    audit_service.log(db, actor=admin, action="create", resource_type="operational_scope", resource_id=scope.scope_id,
                       resource_label=scope.name)
    return scope


@router.delete("/api/operational-scopes/{scope_id}", status_code=204)
def delete_operational_scope(scope_id: int, db: Session = Depends(get_db),
                              admin=Depends(_require_unrestricted_admin)):
    scope = db.get(models.OperationalScope, scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Operational scope not found")
    # Phase 12 fix: AdminScope.operational_scope_id is a plain FK with no
    # cascading rule (SQLite here doesn't enforce FKs at all — see
    # database.py), so deleting a scope still referenced by a grant would
    # silently leave that AdminScope row pointing at a dead scope_id,
    # quietly breaking that admin's authorization. Same dependent-blocking
    # pattern already used for Faculty/Department/Course deletion
    # (faculties.py::_faculty_dependents, academic.py::_department_dependents
    # /_course_dependents) — block instead of orphaning.
    grants_in_use = db.query(models.AdminScope).filter(models.AdminScope.operational_scope_id == scope_id).count()
    if grants_in_use > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Can't delete '{scope.name}' — {grants_in_use} admin scope grant(s) still use it. Revoke those first.",
        )
    scope_id_val, scope_name = scope.scope_id, scope.name
    db.delete(scope)
    db.commit()
    audit_service.log(db, actor=admin, action="delete", resource_type="operational_scope", resource_id=scope_id_val,
                       resource_label=scope_name)


@router.delete("/api/admin-scopes/{scope_id}", status_code=204)
def delete_admin_scope(scope_id: int, db: Session = Depends(get_db),
                        _admin=Depends(_require_unrestricted_admin)):
    scope = db.get(models.AdminScope, scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Scope grant not found")
    scope_id_val, user_id_val = scope.scope_id, scope.user_id
    db.delete(scope)
    db.commit()
    audit_service.log(db, actor=_admin, action="revoke", resource_type="admin_scope", resource_id=scope_id_val,
                       resource_label=f"user_id={user_id_val}")


# ---------------------------------------------------------------------------
# Scoped staff listing — the backend half of "Doctors/TAs must not appear as
# one giant university-wide list": a college/department-scoped admin gets
# only their authorized staff back, even on a direct API call.
# ---------------------------------------------------------------------------
@router.get("/api/staff", response_model=List[schemas.StaffOut])
def list_staff(faculty_id: Optional[int] = None, department_id: Optional[int] = None,
                role: Optional[str] = None, db: Session = Depends(get_db),
                user=Depends(security.get_current_user)):
    q = db.query(models.User).filter(models.User.role.in_(("doctor", "instructor")))

    if department_id is not None:
        dept = db.get(models.Department, department_id)
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        if user.role == "admin":
            security.require_department_access(dept, user, db)
        q = q.filter(models.User.department_id == department_id)
    elif faculty_id is not None:
        if user.role == "admin":
            security.require_faculty_access(faculty_id, user, db)
        q = q.filter(models.User.faculty_id == faculty_id)
    elif user.role == "admin":
        allowed = security.authorized_faculty_ids(user, db)
        if allowed is not None:
            q = q.filter(models.User.faculty_id.in_(allowed))

    if role is not None:
        if role not in ("doctor", "instructor"):
            raise HTTPException(status_code=400, detail="role must be 'doctor' or 'instructor'")
        q = q.filter(models.User.role == role)

    staff_list = q.order_by(models.User.name).all()
    course_ids_by_user = {}
    if staff_list:
        rows = (
            db.query(models.CourseAssignment)
            .filter(models.CourseAssignment.user_id.in_([s.user_id for s in staff_list]))
            .all()
        )
        for row in rows:
            course_ids_by_user.setdefault(row.user_id, []).append(row.course)

    results = []
    for s in staff_list:
        out = schemas.StaffOut.model_validate(s)
        out.assigned_courses = [schemas.CourseOut.model_validate(c) for c in course_ids_by_user.get(s.user_id, [])]
        results.append(out)
    return results
