from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("", response_model=List[schemas.ScheduleOut])
def list_schedules(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Schedule).all()


def _validate_course_ref(db: Session, admin: models.User, course_ref_id, schedule_id=None) -> None:
    """Phase 11: closes the previously-documented gap where
    Schedule.course_ref_id had no API create/update path (only a direct DB
    write). Deliberately additive and narrow:
      - course_ref_id must point at a real Course (404 otherwise).
      - the admin must have department access to that course, the same rule
        already enforced for course assignments (academic.py) and course
        mutations themselves — a scoped admin cannot link a schedule to a
        course outside their own college/department.
      - if this schedule is already used by a CourseAssignment (via
        CourseAssignment.schedule_id), the assignment's own course must
        match, or the assignment's implied room/time would silently point
        at the wrong course. This mirrors _validate_assignment_schedule's
        check in academic.py but in the other direction.
    Does not touch course_id (the pre-existing free-text field) or change
    any other schedule behavior.
    """
    if course_ref_id is None:
        return
    course = db.get(models.Course, course_ref_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    security.require_department_access(course.department, admin, db)

    if schedule_id is not None:
        conflicting = (
            db.query(models.CourseAssignment)
            .filter(
                models.CourseAssignment.schedule_id == schedule_id,
                models.CourseAssignment.course_id != course_ref_id,
            )
            .first()
        )
        if conflicting:
            raise HTTPException(
                status_code=409,
                detail="This schedule is already used by a course assignment for a different course",
            )


@router.post("", response_model=schemas.ScheduleOut, status_code=201)
def create_schedule(payload: schemas.ScheduleCreate, db: Session = Depends(get_db),
                     admin=Depends(security.require_admin)):
    door = db.query(models.Door).filter(models.Door.door_id == payload.door_id).first()
    if not door:
        raise HTTPException(status_code=404, detail="Door not found")
    _validate_course_ref(db, admin, payload.course_ref_id)
    schedule = models.Schedule(**payload.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.put("/{schedule_id}", response_model=schemas.ScheduleOut)
def update_schedule(schedule_id: int, payload: schemas.ScheduleUpdate, db: Session = Depends(get_db),
                     admin=Depends(security.require_admin)):
    schedule = db.query(models.Schedule).filter(models.Schedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    updates = payload.model_dump(exclude_unset=True)
    if "course_ref_id" in updates:
        _validate_course_ref(db, admin, updates["course_ref_id"], schedule_id=schedule_id)
    for field, value in updates.items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)
    return schedule
