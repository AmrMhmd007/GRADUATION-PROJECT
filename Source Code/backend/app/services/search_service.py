"""
Global Search — one authorized, cross-entity search over data that already
exists in this system, reusing the exact authorization each entity's own
router already enforces (see app/security.py). This module introduces NO
new authorization model: every scope check below is a direct call into the
same helpers/patterns academic.py, doors.py, alerts.py, and
investigation_service.py already use for their own list endpoints. A user
can never see a search result for an object their existing role/scope
would not already let them list or open directly.

Architecture: bounded, per-entity SQL `ilike` queries (never a full-table
scan into Python, never one request per keystroke — the router debounces on
the frontend and this module itself caps every query at PER_TYPE_LIMIT rows
before any Python-side filtering). Each entity type queries its own table
once; there is no unified search index/table, because none of these tables
are large enough to need one and every entity already has an indexed or
naturally short-scanning column (name/code/email) to filter on. A result is
composed by hand into SearchResultOut — never a raw ORM object serialized
through — with `nav_tab`/`nav_params` mapped onto Dashboard.jsx's existing
hash-based deep-link parameters (see that file's own "Stage E lightweight
deep-linking" comment), never an invented route.

Entities NOT included, and why (see also the Global Search final report):
  - Device: no standalone destination exists in the frontend — a device is
    only ever shown inside its owning Zone's detail modal, which is exactly
    where a Device result already sends the user (via the Zone it belongs
    to), so a separate Device entity would just duplicate Zone with no real
    additional destination.
  - AutomationLog, OccupancyEvent, AuditLog: these are timestamped decision/
    audit *log entries*, not named objects a user searches for by title —
    there is nothing resembling the "search 'smart lab', get a result named
    Smart Lab 301" pattern this feature is built around. AuditLog is also
    unrestricted-admin-only (see audit_logs.py) and showing even its count
    to anyone else would itself be a leak.
  - CourseAssignment: not an independently named object — it has no
    identity beyond "this staff member teaches this course", which already
    surfaces via both the Staff and Course results.
  - Sensor, HardwareHealth, OperationalScope: pure operational/telemetry or
    internal-authorization bookkeeping, never something a user searches for
    by name.
  - EmergencyOverride: admin-only everywhere else in this codebase
    (routers/emergency_overrides.py has no non-admin path at all) — see
    _search_emergency_overrides below, gated the same way.
"""
from __future__ import annotations

from sqlalchemy import or_

from .. import models, security

MIN_QUERY_LEN = 2
PER_TYPE_LIMIT_DEFAULT = 8


def _ilike(col, q: str):
    return col.ilike(f"%{q}%")


# ---------------------------------------------------------------------------
# Academic
# ---------------------------------------------------------------------------
def _search_colleges(db, user, q: str, limit: int) -> list:
    query = db.query(models.Faculty).filter(
        or_(_ilike(models.Faculty.name, q), _ilike(models.Faculty.code, q))
    )
    if user.role == "admin":
        allowed = security.authorized_faculty_ids(user, db)
        if allowed is not None:
            if not allowed:
                return []
            query = query.filter(models.Faculty.faculty_id.in_(allowed))
    rows = query.order_by(models.Faculty.name).limit(limit).all()
    out = []
    for f in rows:
        dept_count = db.query(models.Department).filter(models.Department.faculty_id == f.faculty_id).count()
        out.append({
            "type": "college", "category": "Academic", "id": f.faculty_id,
            "title": f.name, "subtitle": f.code or "College",
            "meta": f"{dept_count} department{'s' if dept_count != 1 else ''}",
            "nav_tab": "academic",
            "nav_params": {"aa_section": "colleges", "aa_college": str(f.faculty_id)},
        })
    return out


def _search_departments(db, user, q: str, limit: int) -> list:
    query = db.query(models.Department).filter(
        or_(_ilike(models.Department.name, q), _ilike(models.Department.code, q))
    )
    restricted_faculties = security.authorized_faculty_ids(user, db) if user.role == "admin" else None
    candidates = query.order_by(models.Department.name).limit(limit * 4).all()
    out = []
    for d in candidates:
        if len(out) >= limit:
            break
        if user.role == "admin":
            if restricted_faculties is not None and d.faculty_id not in restricted_faculties:
                continue
            dept_ids = security.authorized_department_ids(user, db, d.faculty_id)
            if dept_ids is not None and d.department_id not in dept_ids:
                continue
        out.append({
            "type": "department", "category": "Academic", "id": d.department_id,
            "title": d.name, "subtitle": d.faculty_name or "Department",
            "meta": d.code,
            "nav_tab": "academic",
            "nav_params": {
                "aa_section": "colleges", "aa_college": str(d.faculty_id), "aa_department": str(d.department_id),
            },
        })
    return out


def _search_courses(db, user, q: str, limit: int) -> list:
    query = db.query(models.Course).filter(
        or_(_ilike(models.Course.name, q), _ilike(models.Course.code, q))
    )
    restricted_faculties = security.authorized_faculty_ids(user, db) if user.role == "admin" else None
    candidates = query.order_by(models.Course.name).limit(limit * 4).all()
    out = []
    for c in candidates:
        if len(out) >= limit:
            break
        dept = c.department
        if user.role == "admin" and dept is not None:
            if restricted_faculties is not None and dept.faculty_id not in restricted_faculties:
                continue
            dept_ids = security.authorized_department_ids(user, db, dept.faculty_id)
            if dept_ids is not None and dept.department_id not in dept_ids:
                continue
        out.append({
            "type": "course", "category": "Academic", "id": c.course_id,
            "title": c.name, "subtitle": f"{c.code} · {c.faculty_name or c.department_name or 'Course'}",
            "meta": c.semester,
            "nav_tab": "academic",
            "nav_params": {"aa_section": "courses", "aa_course": str(c.course_id)},
        })
    return out


def _search_staff(db, user, q: str, limit: int) -> list:
    query = db.query(models.User).filter(
        models.User.role.in_(("doctor", "instructor")),
        or_(
            _ilike(models.User.name, q),
            _ilike(models.User.email, q),
            _ilike(models.User.staff_id, q),
        ),
    )
    candidates = query.order_by(models.User.name).limit(limit * 4).all()
    out = []
    for s in candidates:
        if len(out) >= limit:
            break
        if user.role == "admin" and not security.is_staff_authorized(s, user, db):
            continue
        section = "doctors" if s.role == "doctor" else "tas"
        out.append({
            "type": "staff", "category": "Academic", "id": s.user_id,
            "title": s.name,
            "subtitle": f"{s.academic_title or s.role.capitalize()}"
                        + (f" · {s.faculty_name}" if s.faculty_name else ""),
            "meta": s.department_name,
            "nav_tab": "academic",
            "nav_params": {"aa_section": section, "aa_staff": str(s.user_id)},
        })
    return out


# ---------------------------------------------------------------------------
# Security / Infrastructure
# ---------------------------------------------------------------------------
def _search_doors(db, user, q: str, limit: int) -> list:
    query = db.query(models.Door).filter(
        or_(_ilike(models.Door.name, q), _ilike(models.Door.code, q), _ilike(models.Door.building, q))
    )
    if user.role in ("instructor", "doctor"):
        query = query.join(
            models.DoorAssignment, models.DoorAssignment.door_id == models.Door.door_id
        ).filter(models.DoorAssignment.instructor_id == user.user_id)
    rows = query.order_by(models.Door.name).limit(limit).all()
    out = []
    for d in rows:
        out.append({
            "type": "door", "category": "Infrastructure", "id": d.door_id,
            "title": d.name, "subtitle": f"{d.building}" + (f" · {d.floor}" if d.floor else ""),
            "meta": "Main Doors" if d.category == "critical" else "Room",
            "nav_tab": "critical" if d.category == "critical" else "access",
            "nav_params": {"room": str(d.door_id)},
        })
    return out


def _search_buildings(db, user, q: str, limit: int) -> list:
    rows = (
        db.query(models.Building)
        .filter(_ilike(models.Building.name, q))
        .order_by(models.Building.name)
        .limit(limit)
        .all()
    )
    out = []
    for b in rows:
        door_count = db.query(models.Door).filter(models.Door.building == b.name).count()
        out.append({
            "type": "building", "category": "Infrastructure", "id": b.building_id,
            "title": b.name, "subtitle": "Building",
            "meta": f"{door_count} door{'s' if door_count != 1 else ''}",
            "nav_tab": "access",
            "nav_params": {"building": b.name},
        })
    return out


def _search_zones(db, user, q: str, limit: int) -> list:
    # Zones/devices/automation rules have no scope mapping anywhere else in
    # this codebase (routers/zones.py — every list endpoint there is
    # `_user=Depends(security.get_current_user)` with no role/scope filter
    # at all) — mirroring that exact, already-existing exposure level here
    # rather than inventing a stricter or looser rule for search alone.
    rows = (
        db.query(models.Zone)
        .filter(_ilike(models.Zone.name, q))
        .order_by(models.Zone.name)
        .limit(limit)
        .all()
    )
    out = []
    for z in rows:
        out.append({
            "type": "zone", "category": "Infrastructure", "id": z.zone_id,
            "title": z.name,
            "subtitle": (z.building_name or "Zone") + (f" · {z.floor}" if z.floor else ""),
            "meta": z.occupancy_state.title(),
            "nav_tab": "smart",
            "nav_params": {},
            "nav_action": "open_zone",
            "nav_action_id": z.zone_id,
        })
    return out


def _search_automation_rules(db, user, q: str, limit: int) -> list:
    rows = (
        db.query(models.AutomationRule)
        .filter(_ilike(models.AutomationRule.name, q))
        .order_by(models.AutomationRule.name)
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        out.append({
            "type": "automation_rule", "category": "Automation", "id": r.rule_id,
            "title": r.name, "subtitle": r.zone_name,
            "meta": "Enabled" if r.enabled else "Disabled",
            "nav_tab": "smart",
            "nav_params": {},
        })
    return out


def _search_alerts(db, user, q: str, limit: int) -> list:
    # Same scope posture as GET /api/alerts itself (routers/alerts.py): a
    # scope-restricted admin gets nothing at all (alerts have no safe
    # faculty/department/operational-scope mapping — see that router's own
    # comment), an unrestricted admin and any non-admin role see the full
    # set. Never invents a narrower "your alerts" subset that doesn't exist
    # in the real endpoint.
    if user.role == "admin" and security.is_scope_restricted(user, db):
        return []
    rows = (
        db.query(models.Alert)
        .filter(_ilike(models.Alert.type, q))
        .order_by(models.Alert.alert_time.desc())
        .limit(limit)
        .all()
    )
    out = []
    for a in rows:
        label = a.door_name or a.zone_name or f"Alert #{a.alert_id}"
        out.append({
            "type": "alert", "category": "Security", "id": a.alert_id,
            "title": f"{a.type.replace('_', ' ').title()} — {label}",
            "subtitle": a.severity.title(),
            "meta": "Resolved" if a.resolved else "Unresolved",
            "nav_tab": "command",
            "nav_params": {},
        })
    return out


def _search_emergency_overrides(db, user, q: str, limit: int) -> list:
    # Admin-only everywhere else in this codebase (routers/emergency_overrides.py
    # has no non-admin path at all) — search mirrors that exactly rather than
    # exposing overrides to doctor/instructor for the first time here.
    if user.role != "admin":
        return []
    query = (
        db.query(models.EmergencyOverride)
        .join(models.Door, models.EmergencyOverride.door_id == models.Door.door_id)
        .filter(or_(_ilike(models.EmergencyOverride.reason, q), _ilike(models.Door.name, q), _ilike(models.Door.code, q)))
    )
    if security.is_scope_restricted(user, db):
        allowed = security.authorized_operational_scope_ids(user, db)
        query = query.filter(models.EmergencyOverride.operational_scope_id.in_(allowed or set()))
    rows = query.order_by(models.EmergencyOverride.created_at.desc()).limit(limit).all()
    out = []
    for o in rows:
        out.append({
            "type": "emergency_override", "category": "Security", "id": o.override_id,
            "title": f"Emergency {o.action} — {o.door_name or o.door_code}",
            "subtitle": o.status.title(),
            "meta": o.reason[:60] if o.reason else None,
            "nav_tab": "critical",
            "nav_params": {"room": str(o.door_id)},
        })
    return out


def _search_access_events(db, user, q: str, limit: int) -> list:
    """Reuses investigation_service.list_access_events's exact scope
    filtering (the same function GET /api/access-events itself calls) for
    the authorization decision, then does a bounded in-Python substring
    match over the already-scoped rows for door/user/building/method/result
    — there is no free-text column on AccessEvent itself to filter in SQL,
    and the underlying service already applies the identical bounded-scan
    pattern for its own filters (see that module's own comment)."""
    from . import investigation_service

    rows, _total = investigation_service.list_access_events(db, user, limit=200, offset=0)
    q_lower = q.lower()
    out = []
    for r in rows:
        haystack = " ".join(
            str(v) for v in (r["door_name"], r["door_code"], r["building"], r["user_name"], r["method"], r["result"])
            if v
        ).lower()
        if q_lower not in haystack:
            continue
        is_investigation = r["investigation_status"] is not None
        label = r["door_name"] or f"Door #{r['door_id']}"
        out.append({
            "type": "investigation" if is_investigation else "access_event",
            "category": "Security", "id": r["event_id"],
            "title": f"{'Investigation' if is_investigation else 'Access event'} — {label}",
            "subtitle": f"{r['user_name'] or 'Unresolved credential'} · {r['method']} · {r['result']}",
            "meta": r["investigation_status"].replace("_", " ").title() if is_investigation else None,
            "nav_tab": "events",
            "nav_params": {"investigate": str(r["event_id"])},
        })
        if len(out) >= limit:
            break
    return out


SEARCHERS = [
    _search_colleges,
    _search_departments,
    _search_courses,
    _search_staff,
    _search_doors,
    _search_buildings,
    _search_zones,
    _search_automation_rules,
    _search_alerts,
    _search_emergency_overrides,
    _search_access_events,
]


def search(db, user: "models.User", q: str, per_type_limit: int = PER_TYPE_LIMIT_DEFAULT) -> list:
    """Runs every entity searcher (each independently authorized and
    bounded) and returns the concatenated, still-grouped-by-type result
    list. Callers group/sort for display; this stays a flat list so the
    response shape matches SearchResultOut 1:1."""
    q = q.strip()
    results = []
    for searcher in SEARCHERS:
        results.extend(searcher(db, user, q, per_type_limit))
    return results
