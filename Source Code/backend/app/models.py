import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, SmallInteger,
    String, Text, Time,
)
from sqlalchemy.orm import relationship

from .database import Base


class Faculty(Base):
    """A TA/doctor's home faculty (e.g. "Faculty of Engineering") — picked
    when adding a TA or doctor, managed by the admin from that same form.

    Organizational-scoping note: this is the authoritative "College" level
    of the University -> College -> Department -> Staff hierarchy. It is
    deliberately NOT renamed/replaced with a new "College" table — the
    table name, FK columns (`faculty_id` on User/Department/AdminScope) and
    every existing endpoint stay exactly as they were, so nothing that
    already depends on Faculty breaks. New organizational-hierarchy code
    (Department, Course, AdminScope, the /api/departments and /api/courses
    routers) simply treats a Faculty row as "a College" and exposes it that
    way in schemas/UI wording. See Department below for the next level.
    """
    __tablename__ = "faculties"

    faculty_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    # Additive fields (final hardening pass) — all nullable/defaulted so no
    # existing College row needs a backfill. `code` is a short human
    # identifier (e.g. "ENG") shown alongside the name, not a second name.
    code = Column(String(20), unique=True, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (CheckConstraint("status IN ('active','inactive')", name="ck_faculty_status"),)

    departments = relationship("Department", back_populates="faculty")


class Department(Base):
    """A department within a College (Faculty) — e.g. "Electronics &
    Communication Engineering" within "Faculty of Engineering".

    This is the second level of the organizational hierarchy requested for
    academic-staff scoping: University -> College (Faculty) -> Department ->
    Staff (User, role doctor/instructor) -> Course -> Assigned
    Rooms/Areas (DoorAssignment, already existing) -> Access Permissions.
    Deliberately a new table (no existing model covered this level), but
    it hangs off the existing Faculty table rather than introducing a
    second, competing "College" concept.
    """
    __tablename__ = "departments"

    department_id = Column(Integer, primary_key=True, index=True)
    faculty_id = Column(Integer, ForeignKey("faculties.faculty_id"), nullable=False)
    name = Column(String(160), nullable=False)
    # Additive fields (final hardening pass) — same rationale as Faculty's.
    code = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("length(name) > 0", name="ck_department_name_nonempty"),
        CheckConstraint("status IN ('active','inactive')", name="ck_department_status"),
    )

    faculty = relationship("Faculty", back_populates="departments")
    courses = relationship("Course", back_populates="department")

    @property
    def faculty_name(self):
        return self.faculty.name if self.faculty else None


class Course(Base):
    """A course offered by a Department (e.g. "DSP" in Electronics &
    Communication Engineering). Deliberately separate from
    `Schedule.course_id`, which stays the free-text field it always was
    (existing schedules keep working unmodified) — `Schedule.course_ref_id`
    below is an additive, nullable link to this table for schedules that
    want to point at a real Course row going forward.
    """
    __tablename__ = "courses"

    course_id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=False)
    code = Column(String(40), nullable=False)
    name = Column(String(160), nullable=False)
    # Additive fields (final hardening pass) — all nullable/defaulted so no
    # existing Course row needs a backfill.
    credit_hours = Column(Integer, nullable=True)
    level = Column(String(20), nullable=True)     # e.g. "1", "2", "Undergraduate", "Graduate" — free text, no existing convention to match
    semester = Column(String(20), nullable=True)  # e.g. "Fall", "Spring", "Summer"
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("length(code) > 0", name="ck_course_code_nonempty"),
        CheckConstraint("credit_hours IS NULL OR credit_hours > 0", name="ck_course_credit_hours_positive"),
        CheckConstraint("status IN ('active','inactive')", name="ck_course_status"),
    )

    department = relationship("Department", back_populates="courses")

    @property
    def department_name(self):
        return self.department.name if self.department else None

    @property
    def faculty_name(self):
        return self.department.faculty_name if self.department else None

    @property
    def faculty_id(self):
        """Read-only, computed via the existing Course -> Department ->
        Faculty relationship — no new column/migration. Lets callers filter
        courses by college ID (department_id.faculty_id) instead of matching
        on the display name (`faculty_name`), which was a fragile substitute
        the frontend used only because this wasn't exposed yet."""
        return self.department.faculty_id if self.department else None


class CourseAssignment(Base):
    """Which Doctor/TA (User) is assigned to teach/assist a given Course —
    the "Assigned Courses" a staff profile shows. Many-to-many via this
    join table since a course can have more than one doctor/TA and a
    staff member can teach more than one course.
    """
    __tablename__ = "course_assignments"

    assignment_id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Additive fields (final hardening pass). `schedule_id` is a deliberate
    # reuse of the existing Schedule table rather than a new door_id/room
    # column: Schedule already carries door_id (the room) + day/start/end
    # time, so pointing an assignment at a Schedule row gives it both a room
    # AND a timing without duplicating either.
    section = Column(String(20), nullable=True)
    semester = Column(String(20), nullable=True)      # e.g. "Fall", "Spring", "Summer"
    academic_year = Column(String(20), nullable=True)  # e.g. "2026/2027"
    status = Column(String(20), nullable=False, default="active")
    schedule_id = Column(Integer, ForeignKey("schedules.schedule_id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    course = relationship("Course")
    user = relationship("User")
    schedule = relationship("Schedule")

    __table_args__ = (
        CheckConstraint("course_id IS NOT NULL AND user_id IS NOT NULL", name="ck_course_assignment_complete"),
        CheckConstraint("status IN ('active','inactive')", name="ck_course_assignment_status"),
    )

    @property
    def room_name(self):
        return self.schedule.door.name if self.schedule and self.schedule.door else None

    @property
    def room_code(self):
        return self.schedule.door.code if self.schedule and self.schedule.door else None


class OperationalScope(Base):
    """The minimum abstraction needed to authorize NON-academic operational
    areas (HVAC, Electrical, Residential, Administrative, Engineering/
    Technical) alongside the existing Faculty->Department academic
    hierarchy — WITHOUT duplicating it or introducing a second competing
    "College" concept.

    An academic operational area is simply represented by pointing at the
    existing Faculty row (faculty_id set) — there is no separate "academic
    OperationalScope table", just this thin pointer, so Faculty stays the
    one and only College-level model. A non-academic scope instead has
    faculty_id NULL and describes itself with scope_type + name (e.g.
    scope_type="HVAC", name="Chiller Plant") and optionally a building_id
    for scopes tied to a physical building.

    Authorization stays unified: see AdminScope.operational_scope_id below
    — the SAME grant table drives both academic and infrastructure access,
    there is no second authorization pathway.
    """
    __tablename__ = "operational_scopes"

    scope_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), nullable=False)
    scope_type = Column(String(20), nullable=False)  # ACADEMIC | HVAC | ELECTRICAL | RESIDENTIAL | ADMINISTRATIVE | ENGINEERING
    faculty_id = Column(Integer, ForeignKey("faculties.faculty_id"), nullable=True)
    building_id = Column(Integer, ForeignKey("buildings.building_id"), nullable=True)
    description = Column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('ACADEMIC','HVAC','ELECTRICAL','RESIDENTIAL','ADMINISTRATIVE','ENGINEERING')",
            name="ck_operational_scope_type",
        ),
    )

    faculty = relationship("Faculty")
    building = relationship("Building")

    @property
    def faculty_name(self):
        return self.faculty.name if self.faculty else None

    @property
    def building_name(self):
        return self.building.name if self.building else None


class AdminScope(Base):
    """Restricts an admin User to specific College(s)/Department(s) —
    the "Authorized Organizational Scope" layer of User -> Role ->
    Authorized Scope -> College -> Department -> ... .

    Deliberately additive and backward-compatible: an admin with ZERO
    AdminScope rows is unrestricted (exactly today's behavior — every
    admin that existed before this feature keeps full access with no
    migration needed). An admin who has at least one AdminScope row is
    restricted to the union of those rows: a row with department_id set
    grants that one department; a row with only faculty_id set grants the
    whole college (every department under it). This is enforced in
    app/security.py's scope-check helpers and applied in the
    departments/courses/staff routers — never only hidden in the UI.
    """
    __tablename__ = "admin_scopes"

    scope_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    # Exactly one of (faculty_id) or (operational_scope_id) is set per row —
    # enforced in app/routers/academic.py, not a DB-level XOR constraint
    # (SQLite CHECK can reference multiple columns, but keeping the
    # validation in Python keeps the error message useful). faculty_id is
    # nullable now (it used to be required) purely so an infrastructure
    # grant row can leave it out — every existing academic grant still sets
    # it exactly as before.
    faculty_id = Column(Integer, ForeignKey("faculties.faculty_id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    operational_scope_id = Column(Integer, ForeignKey("operational_scopes.scope_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    faculty = relationship("Faculty")
    department = relationship("Department")
    operational_scope = relationship("OperationalScope")

    __table_args__ = (
        CheckConstraint(
            "(faculty_id IS NOT NULL) OR (operational_scope_id IS NOT NULL)",
            name="ck_admin_scope_has_a_target",
        ),
    )

    @property
    def faculty_name(self):
        return self.faculty.name if self.faculty else None

    @property
    def department_name(self):
        return self.department.name if self.department else None

    @property
    def operational_scope_name(self):
        return self.operational_scope.name if self.operational_scope else None


class Building(Base):
    """A campus building — picked when adding a door, managed by the admin
    from that same form. Kept separate from Door.building (which stays a
    plain string for backward compatibility) so the dropdown has a source
    of truth without requiring a data migration on the doors table.
    """
    __tablename__ = "buildings"

    building_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)


class User(Base):
    """Matches the `users` table in the System Design Document (Section 4)."""
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'admin' | 'instructor' | 'doctor'
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Which faculty a TA/doctor belongs to. Nullable so admin accounts (and
    # any pre-existing TA rows from before this feature) don't need one.
    faculty_id = Column(Integer, ForeignKey("faculties.faculty_id"), nullable=True)
    # Department within that faculty/college — nullable so admins and any
    # doctor/TA added before this feature (or without a department set)
    # keep working unchanged. Not enforced to belong to `faculty_id`'s
    # departments at the DB level (SQLite has no composite-FK-via-column
    # trick here); routers/academic.py validates this at write time instead.
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    # Relative URL under /media (e.g. "/media/avatars/3-ab12cd34.jpg"), served
    # as a static file — see app/main.py's StaticFiles mount.
    photo_url = Column(String(255), nullable=True)
    # Set when an admin approves a password-reset request (see
    # PasswordResetRequest below) — the dashboard checks this on login and
    # forces the user to pick their own password before it lets them past
    # that screen, instead of leaving the admin's temp password in place
    # indefinitely. Cleared as soon as they successfully change it.
    must_change_password = Column(Boolean, default=False, nullable=False)

    # Additive academic-staff fields (final hardening pass). All nullable so
    # admin accounts and any staff row created before this pass keep working
    # unchanged. Deliberately kept on User rather than a new AcademicStaff
    # table: a Staff member IS a User (role doctor/instructor) everywhere
    # else in this codebase (DoorAssignment, CourseAssignment, AccessWindow,
    # AdminScope all key off users.user_id directly) — splitting that into a
    # second table now would mean rewriting every one of those FKs and every
    # existing query/test that joins on User, for no behavioral gain.
    #
    # `staff_id` is a human-facing employee/staff number, distinct from the
    # `user_id` primary key (which is an internal row id, not something HR
    # would hand out). `academic_title` is the professorial rank — distinct
    # from `role`, which stays the *system* permission level
    # ('doctor'/'instructor') exactly as it already means elsewhere in this
    # codebase (see StaffScopeView.jsx's Doctors/TAs tabs, already keyed off
    # role). A "doctor" row's academic_title is typically Professor/
    # Associate/Assistant Professor/Lecturer; an "instructor" (TA) row's is
    # typically "Teaching Assistant" or "Instructor" — but the two are
    # independent columns, not inferred from one another, since a real
    # university does have Lecturers who aren't TAs.
    staff_id = Column(String(40), unique=True, nullable=True)
    academic_title = Column(String(40), nullable=True)
    specialization = Column(String(160), nullable=True)
    phone = Column(String(30), nullable=True)
    status = Column(String(20), nullable=False, default="active")

    __table_args__ = (
        CheckConstraint("role IN ('admin','instructor','doctor')", name="ck_user_role"),
        CheckConstraint(
            "academic_title IS NULL OR academic_title IN "
            "('Professor','Associate Professor','Assistant Professor','Lecturer','Instructor','Teaching Assistant')",
            name="ck_user_academic_title",
        ),
        CheckConstraint("status IN ('active','inactive')", name="ck_user_status"),
    )

    credentials = relationship("Credential", back_populates="user")
    faculty = relationship("Faculty")
    department = relationship("Department")

    @property
    def faculty_name(self):
        return self.faculty.name if self.faculty else None

    @property
    def department_name(self):
        return self.department.name if self.department else None


class Credential(Base):
    __tablename__ = "credentials"

    credential_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    # Phase 5: encrypted at rest (Fernet token, see app/crypto.py), not the
    # plaintext UID. `card_uid_index` is a deterministic keyed HMAC of the
    # same UID, indexed for O(1) equality lookup without decrypting every
    # row — this is what the MQTT ingestion service and the API actually
    # query against.
    card_uid = Column(String(256), nullable=True)
    card_uid_index = Column(String(64), nullable=True, index=True, unique=True)
    fp_template_hash = Column(String(256), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    issued_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="credentials")
    access_events = relationship("AccessEvent", back_populates="credential")


class Door(Base):
    __tablename__ = "doors"

    door_id = Column(Integer, primary_key=True, index=True)
    # Human-readable identifier used in MQTT topics (site/{code}/event) and
    # burned into each door node's firmware config.h as DOOR_ID. Not in the
    # original ERD (which only had the numeric PK) — added so the MQTT
    # ingestion service can map a firmware topic back to a database row.
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    building = Column(String(80), nullable=False)
    # Which floor within the building (e.g. "Ground", "1", "2") — optional
    # since some doors (a standalone main entrance/gate) don't really have one.
    floor = Column(String(20), nullable=True)
    fail_mode = Column(String(10), nullable=False, default="secure")  # 'safe' | 'secure'
    # Live status fields, updated by the MQTT ingestion service — not in the
    # original ERD but needed to back the dashboard's door-status cards.
    online = Column(Boolean, default=False)
    locked = Column(Boolean, default=True)
    last_seen = Column(DateTime, nullable=True)
    # 'critical' (server room, main entrance) vs 'access_service' (halls,
    # section/classroom doors) — drives which top-level admin dashboard tab
    # a door shows up under.
    category = Column(String(20), nullable=False, default="access_service")

    # Room device controls — only meaningful for category == 'access_service'
    # ("Rooms"): Main Doors stay lock-only and never set these. *_enabled is
    # decided once by the admin when the room is created (whether that room
    # even has an AC unit / controllable light wired up); *_on is the live
    # state, updated either optimistically on command or by a real status
    # message from the node over MQTT (see services/mqtt_service.py).
    ac_enabled = Column(Boolean, default=False, nullable=False)
    ac_on = Column(Boolean, default=False, nullable=False)
    light_enabled = Column(Boolean, default=False, nullable=False)
    light_on = Column(Boolean, default=False, nullable=False)
    # The AC's own live current draw, same idea as Plug.current_amps below —
    # only ever set by a real MQTT reading once that hardware exists
    # (site/{code}/ac/status carrying a current_amps field alongside on/off).
    # Simulated for the demo by services/energy_service.py in the meantime.
    ac_current_amps = Column(Float, nullable=True)

    # Occupancy — a real per-room sensor, once wired up, reports here over
    # MQTT (site/{code}/occupancy/status, see services/mqtt_service.py),
    # exactly the same "real hardware writes this, nothing else guesses it"
    # pattern as ac_on/light_on/Plug.current_amps. None means no sensor has
    # ever reported for this room yet — deliberately distinct from False, so
    # the dashboard and the high-power-empty-room alert can tell "confirmed
    # vacant" apart from "we simply don't know."
    occupied = Column(Boolean, nullable=True)
    occupancy_updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("fail_mode IN ('safe','secure')", name="ck_door_fail_mode"),
        CheckConstraint("category IN ('critical','access_service')", name="ck_door_category"),
    )

    schedules = relationship("Schedule", back_populates="door")
    access_events = relationship("AccessEvent", back_populates="door")
    alerts = relationship("Alert", back_populates="door")
    plugs = relationship("Plug", back_populates="door", cascade="all, delete-orphan")


class Plug(Base):
    """A single smart plug inside a Room (an access_service Door). Hardware
    isn't built yet — the user's own words: "we will built it in the plug" —
    but the plan is a plug with a built-in current sensor, so a forgotten
    charger or appliance left running can be spotted (current_amps stays
    nonzero with nothing useful happening) and cut remotely. `on` is the
    commanded/last-known state; `current_amps` and `last_seen` are only ever
    set by a real MQTT status message from the plug itself, never guessed.
    A room can have any number of plugs (e.g. "Plug 1", "Projector outlet").
    """
    __tablename__ = "plugs"

    plug_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    label = Column(String(60), nullable=False, default="Plug")
    on = Column(Boolean, default=False, nullable=False)
    current_amps = Column(Float, nullable=True)  # only set once a real plug reports a reading over MQTT
    last_seen = Column(DateTime, nullable=True)

    door = relationship("Door", back_populates="plugs")


class DoorAssignment(Base):
    """Which doors a given instructor/TA is allowed to *request* access to.

    This is deliberately separate from Schedule (which is about automatic
    time-based unlock windows tied to a course). A door assignment just says
    "this TA is allowed to see this door and send an access request for it" —
    no day/time attached. An admin manages these from the TA's profile in the
    dashboard; the instructor's own door list is filtered down to only the
    doors they have an assignment row for (see routers/doors.py list_doors).
    """
    __tablename__ = "door_assignments"

    assignment_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)

    door = relationship("Door")
    instructor = relationship("User", foreign_keys=[instructor_id])

    @property
    def door_code(self):
        return self.door.code if self.door else None

    @property
    def door_name(self):
        return self.door.name if self.door else None

    @property
    def instructor_name(self):
        return self.instructor.name if self.instructor else None


class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Monday .. 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    course_id = Column(String(40), nullable=True)
    # Additive, nullable link to a real Course row (app/models.py::Course).
    # `course_id` above stays exactly as it was (free-text, still read by
    # every existing schedule) — this is only populated going forward when a
    # schedule is created/edited against a Course that exists in the new
    # organizational hierarchy, so nothing existing needs a backfill.
    course_ref_id = Column(Integer, ForeignKey("courses.course_id"), nullable=True)

    door = relationship("Door", back_populates="schedules")
    course_ref = relationship("Course")


class AccessWindow(Base):
    """Feature #5 — Schedule-Derived Access Authorization: the WHEN layer on
    top of WHO (User, scoped by College/Department via AdminScope) and
    WHERE (Door/OperationalScope). This is deliberately a NEW, separate
    concept from two existing ones it must not duplicate or replace:

    - DoorAssignment is PERMANENT, evergreen access ("this TA may request
      this door, no day/time attached") — untouched, still the primary
      grant. An AccessWindow never removes or overrides it; the two are
      pure ADDITIONAL sources, combined with OR (see
      access_authorization_service.evaluate_door_authorization): if either
      says "yes", the answer is yes. No window can revoke DoorAssignment
      access, and multiple windows never conflict with each other for the
      same reason — authorization is a same additive logic already used
      for occupancy-signal fusion ("any fresh OCCUPIED signal wins
      outright") and rule resolution elsewhere in this codebase.
    - Schedule (above) is a door-wide, course-tied AUTOMATIC UNLOCK window
      (no specific user) used by the legacy building-automation flow. An
      AccessWindow is scoped to one specific user — "is Dr. Ahmed allowed
      into Lab 204 right now" — a different question with a different
      audience (an individual's authorization, not a door's own schedule).

    A row is exactly one of two shapes, enforced in the router (not a DB
    CHECK, so the validation error message can be specific):
    - recurring=True: day_of_week/start_time/end_time set (weekly,
      optionally bounded by valid_from/valid_until — e.g. "for this
      semester"), start_at/end_at left NULL.
    - recurring=False: start_at/end_at set (a one-off/temporary window,
      e.g. "External Lecturer, 24 Sep 10:00-14:00 UTC"), the recurring
      fields left NULL. This is what auto-expires — evaluate_door_
      authorization simply stops returning "active" once now > end_at;
      the row itself is left in place (not auto-deleted) so it stays in
      the audit trail as an expired grant, not silently vanished data.

    All datetimes here are UTC, matching every other subsystem in this
    codebase that tracks time (HardwareHealth.last_seen, EnergyReading.
    timestamp, AutomationLog.timestamp, Device.last_command_at all use
    datetime.utcnow()) — day_of_week/start_time/end_time are also compared
    against datetime.utcnow() for the same reason. This is a deliberate
    choice to NOT introduce a second timezone convention: the legacy
    Schedule/ZoneSchedule automatic-unlock code uses naive local time
    (datetime.datetime.now()) instead, which is a pre-existing
    inconsistency in this codebase (visible today as a wall-clock-
    dependent test flake near local midnight) — Feature #5 does not
    inherit that pattern.
    """
    __tablename__ = "access_windows"

    access_window_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.course_id"), nullable=True)  # context only, e.g. "why" this window exists

    recurring = Column(Boolean, nullable=False, default=False)
    day_of_week = Column(SmallInteger, nullable=True)  # 0=Monday .. 6=Sunday, matches Schedule.day_of_week
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    valid_from = Column(DateTime, nullable=True)   # optional bound on a recurring window (e.g. semester start)
    valid_until = Column(DateTime, nullable=True)  # optional bound on a recurring window (e.g. semester end)

    start_at = Column(DateTime, nullable=True)  # one-off/temporary window start (UTC)
    end_at = Column(DateTime, nullable=True)    # one-off/temporary window end/expiration (UTC)

    reason = Column(String(255), nullable=True)  # e.g. "External Lecturer — network maintenance"
    created_by_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    door = relationship("Door")
    user = relationship("User", foreign_keys=[user_id])
    course = relationship("Course")
    created_by = relationship("User", foreign_keys=[created_by_id])

    @property
    def door_code(self):
        return self.door.code if self.door else None

    @property
    def door_name(self):
        return self.door.name if self.door else None

    @property
    def course_code(self):
        return self.course.code if self.course else None


class AccessEvent(Base):
    __tablename__ = "access_events"

    event_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    credential_id = Column(Integer, ForeignKey("credentials.credential_id"), nullable=True)
    event_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    method = Column(String(20), nullable=False)   # card | card+fingerprint | override | rex | schedule_check
    result = Column(String(20), nullable=False)   # granted | denied
    # Additive (Feature #5: schedule-derived access authorization). A
    # "schedule_check" row has no physical RFID credential involved — the
    # check is against a logged-in staff member's identity, evaluated by
    # access_authorization_service.py — so user_id identifies who was
    # checked, and evidence_snapshot is the full explainable evaluation
    # (permanent access? which windows were active/inactive and why),
    # mirroring the evidence_snapshot pattern already used on AutomationLog
    # rather than inventing a second audit-logging shape.
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    evidence_snapshot = Column(Text, nullable=True)

    door = relationship("Door", back_populates="access_events")
    credential = relationship("Credential", back_populates="access_events")
    user = relationship("User", foreign_keys=[user_id])


class EmergencyOverride(Base):
    """Feature #8 — Emergency Access / Override: a controlled, time-bounded,
    reasoned, fully audited alternative to the plain instant lock/unlock in
    routers/doors.py::override_door.

    Deliberately a SEPARATE concept from everything Feature #5/#7 built, not
    a modification of it — the important-behavior requirement is explicit:
    normal access stays Permanent Assignment / Schedule -> Authorization
    (DoorAssignment / AccessWindow, both untouched by this feature); an
    emergency override is Authorized Admin -> Emergency Override -> Temporary
    Authorization -> Audit Evidence, a distinct pathway that never writes to
    DoorAssignment or AccessWindow. This is what keeps an emergency override
    "clearly distinguishable from normal scheduled authorization" rather than
    quietly becoming another AccessWindow row.

    Scope/authorization reuses the EXISTING AdminScope system rather than
    inventing a second one: Door has no faculty/department/operational-scope
    link of its own (and per the Anomaly Evidence Hardening pass, that
    Door->College/Department hierarchy is deliberately NOT being introduced
    here either) — so a scope-RESTRICTED admin must declare which
    OperationalScope justifies the override, checked with the same
    security.require_operational_scope_access() every other operational-area
    grant uses. An UNRESTRICTED admin (today's default — zero AdminScope
    rows) may leave operational_scope_id unset, exactly like every other
    scope-optional grant in this codebase.

    Never silently permanent: expires_at is REQUIRED and capped at creation
    time by EMERGENCY_OVERRIDE_MAX_DURATION_MINUTES (see config.py); the
    background sweep in emergency_override_service.py reverts the door and
    marks the row EXPIRED the moment expires_at passes — nothing about an
    override lingers past its declared window without an explicit new
    override. `status` is the durable audit record of how it ended
    (ACTIVE/EXPIRED/REVOKED); like AccessWindow, a row is never deleted, so
    history stays intact.
    """
    __tablename__ = "emergency_overrides"

    override_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    # Set only when a scope-restricted admin created this override (see
    # docstring above) — an unrestricted admin may leave this NULL. Purely an
    # authorization/audit facet, never a new Door->scope hierarchy.
    operational_scope_id = Column(Integer, ForeignKey("operational_scopes.scope_id"), nullable=True)
    action = Column(String(10), nullable=False)  # 'lock' | 'unlock' — what was overridden
    reason = Column(String(500), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | EXPIRED | REVOKED
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        CheckConstraint("action IN ('lock','unlock')", name="ck_emergency_override_action"),
        CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED')", name="ck_emergency_override_status"),
    )

    door = relationship("Door")
    operational_scope = relationship("OperationalScope")
    created_by = relationship("User", foreign_keys=[created_by_id])
    revoked_by = relationship("User", foreign_keys=[revoked_by_id])

    @property
    def door_code(self):
        return self.door.code if self.door else None

    @property
    def door_name(self):
        return self.door.name if self.door else None

    @property
    def created_by_name(self):
        return self.created_by.name if self.created_by else None


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, index=True)
    # Nullable as of the smart-building expansion: a zone-only alert (e.g. a
    # corridor occupancy sensor going offline) has no associated Door. Any
    # alert raised by the original door/lock system still sets this as
    # before; new zone/device/sensor alerts set zone_id instead (or both,
    # when a zone happens to be guarded by a door).
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=True)
    # tamper | forced | offline | propped_open | access_denied | access_requested |
    # high_power_empty_room | sensor_offline | sensor_stale | device_failed |
    # unexpected_occupancy | mqtt_failure | gateway_failure | critical_device_failure
    type = Column(String(30), nullable=False)
    severity = Column(String(10), nullable=False, default="WARNING")  # INFO | WARNING | CRITICAL
    alert_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    resolved = Column(Boolean, default=False)
    # Set only for type == "access_requested": which instructor asked. Reuses
    # the existing alert feed/AlertBanner (already polled + rendered) instead
    # of building a separate notifications system from scratch.
    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (CheckConstraint("severity IN ('INFO','WARNING','CRITICAL')", name="ck_alert_severity"),)

    door = relationship("Door", back_populates="alerts")
    zone = relationship("Zone")
    requester = relationship("User", foreign_keys=[requested_by])

    @property
    def requested_by_name(self):
        return self.requester.name if self.requester else None

    @property
    def door_name(self):
        return self.door.name if self.door else None

    @property
    def door_code(self):
        return self.door.code if self.door else None

    @property
    def zone_name(self):
        return self.zone.name if self.zone else None


class PasswordResetRequest(Base):
    """A "forgot password" request awaiting admin review.

    This deployment has no mail server, so there's no reset link to email.
    Instead: the browser that submits the forgot-password form gets back an
    opaque `request_token` and sits on a "waiting for approval" screen,
    polling with it. An admin approves or denies from the dashboard's
    account menu — no password is generated or relayed by the admin at all.
    Once approved, that same browser (and only it, since it's the only
    holder of the token) uses the token to set its own new password
    directly, at which point `password_set` flips to True and the token is
    spent.
    """
    __tablename__ = "password_reset_requests"

    request_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    request_token = Column(String(64), unique=True, index=True, nullable=True)
    requested_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String(10), nullable=False, default="pending")  # 'pending' | 'approved' | 'denied'
    password_set = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','denied')", name="ck_password_reset_status"),
    )

    user = relationship("User", foreign_keys=[user_id])
    resolver = relationship("User", foreign_keys=[resolved_by])

    @property
    def user_name(self):
        return self.user.name if self.user else None

    @property
    def user_email(self):
        return self.user.email if self.user else None

    @property
    def resolved_by_name(self):
        return self.resolver.name if self.resolver else None


class PowerReading(Base):
    """A single wattage sample for one device inside a Room — the AC, or one
    of its plugs — logged periodically so the dashboard has a real time
    series to chart instead of just a live number. `current_amps`/`watts`
    are simulated for now (see services/energy_service.py), the same
    "real hardware would just as happily write into these same fields, once
    it exists" pattern as Plug.current_amps itself.
    """
    __tablename__ = "power_readings"

    reading_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False, index=True)
    device = Column(String(10), nullable=False)  # 'ac' | 'plug'
    # Set only when device == 'plug'; NULL for the room's AC reading.
    plug_id = Column(Integer, ForeignKey("plugs.plug_id"), nullable=True)
    current_amps = Column(Float, nullable=False)
    watts = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    __table_args__ = (CheckConstraint("device IN ('ac','plug')", name="ck_power_reading_device"),)

    door = relationship("Door")
    plug = relationship("Plug")


class EnergyReading(Base):
    """Phase 6: the Smart Building (Zone/Device) analog of PowerReading
    above — kept as a separate table rather than extending PowerReading
    in place, because the two are keyed on genuinely different concepts:
    PowerReading is door_id/plug_id (the legacy per-Room dashboard, and
    still what that dashboard reads from), this is zone_id/device_id (the
    Zone/Sensor/Device model everything from Phase 1 onward is built on),
    with a richer field set (voltage, energy_kwh, power_factor) and the
    mandatory REAL/SIMULATED source tag PowerReading was never given. Both
    tables coexist permanently — see hardware/bridge.py's own coexistence
    note for why the two device models aren't merged.

    `source` follows the same rule as everywhere else in this codebase:
    'REAL' only for a reading that arrived from an actual hardware message;
    'SIMULATED' for anything services/energy_service.py invents because no
    real power-metering hardware exists yet. Never fabricated as history —
    a gap in this table means no reading was taken then, not an
    interpolated or backfilled guess.
    """
    __tablename__ = "energy_readings"

    reading_id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.device_id"), nullable=True, index=True)
    voltage = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    power = Column(Float, nullable=True)  # watts
    energy_kwh = Column(Float, nullable=True)  # this reading's own interval energy, not a running total
    power_factor = Column(Float, nullable=True)
    source = Column(String(10), nullable=False, default="SIMULATED")

    __table_args__ = (
        CheckConstraint("source IN ('REAL','SIMULATED')", name="ck_energy_reading_source"),
    )

    zone = relationship("Zone")
    device = relationship("Device")


class SystemSetting(Base):
    """Tiny key/value store for building-wide settings that don't warrant a
    dedicated table of their own — right now just the daily auto-shutdown
    ("checkout") time. `value` is always a plain string; callers parse it
    (e.g. "18:30" for checkout_time).
    """
    __tablename__ = "system_settings"

    key = Column(String(60), primary_key=True)
    value = Column(String(200), nullable=False)


# ============================================================================
# Smart Building Platform expansion — Zones, Sensors, Devices, Automation.
#
# The original access-control system is organized around Door (a physical
# door with a lock). This expansion introduces Zone as the general container
# for occupancy/energy/device management — a classroom or lab zone usually
# has a Door guarding it, but a corridor, open office, or generic area does
# not, and still needs occupancy sensors, lighting, and automation. Rather
# than duplicating the AC/light/plug control this project already has working
# (services/mqtt_service.py's publish_ac/publish_light/publish_plug, and the
# Door.ac_on/light_on/Plug.on fields they update), a Device optionally points
# back at the existing Door or Plug it controls (door_ref_id/plug_ref_id) —
# the automation engine's ACT step reuses that exact same command path, it
# doesn't invent a second one. A Device with no hardware equivalent yet
# (e.g. LAB_EQUIPMENT) simply leaves both references null.
# ============================================================================

class Zone(Base):
    """A configurable space the smart-building platform manages: a
    classroom, lab, corridor, office, server room, or anything else worth
    tracking occupancy/energy for. Building + floor mirror the existing
    Door.building/Door.floor convention (a plain string floor label) rather
    than modeling a full recursive space hierarchy, since the rest of this
    codebase already organizes rooms that way.
    """
    __tablename__ = "zones"

    zone_id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.building_id"), nullable=True)
    floor = Column(String(20), nullable=True)
    name = Column(String(80), nullable=False)
    zone_type = Column(String(20), nullable=False, default="ROOM")

    # Optional link to the Door that guards this zone (a classroom/lab
    # usually has one; a corridor typically doesn't). One door guards at
    # most one zone.
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=True, unique=True)

    # The automation engine's fused verdict across every sensor/signal in
    # this zone — see services/automation_engine.py. Distinct from any one
    # Sensor's own occupancy_state below.
    occupancy_state = Column(String(12), nullable=False, default="UNKNOWN")
    occupancy_state_changed_at = Column(DateTime, nullable=True)
    # Set when a VERIFYING countdown starts (Step 11's mandatory
    # re-check-before-shutdown timer); cleared once verification resolves
    # either back to OCCUPIED or through to a completed shutdown.
    verification_started_at = Column(DateTime, nullable=True)

    # Phase 3 (confidence-scored occupancy fusion): occupancy_state above is
    # still the plain OCCUPIED/EMPTY/VERIFYING/UNKNOWN verdict the rest of
    # the engine (VERIFY/DECIDE/ACT) acts on — none of that logic changes.
    # These three are additional, purely informational output of the same
    # fusion pass: how strongly the current verdict is corroborated
    # (0.0-1.0, computed from configurable per-source-type weights — see
    # config.OCCUPANCY_SOURCE_WEIGHTS — never a random or guessed number),
    # a JSON-encoded breakdown of exactly which signals fed that number, and
    # when this fusion last actually ran. occupancy_state_changed_at (above)
    # only moves on a state transition; occupancy_computed_at moves every
    # single automation pass, transition or not.
    occupancy_confidence = Column(Float, nullable=True)
    occupancy_evidence = Column(Text, nullable=True)
    occupancy_computed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "zone_type IN ('ROOM','CLASSROOM','LAB','CORRIDOR','OFFICE','SERVER_ROOM','OTHER')",
            name="ck_zone_type",
        ),
        CheckConstraint(
            "occupancy_state IN ('OCCUPIED','EMPTY','VERIFYING','UNKNOWN')",
            name="ck_zone_occupancy_state",
        ),
    )

    building = relationship("Building")
    door = relationship("Door")
    sensors = relationship("Sensor", back_populates="zone", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="zone", cascade="all, delete-orphan")

    @property
    def building_name(self):
        return self.building.name if self.building else None

    @property
    def door_code(self):
        return self.door.code if self.door else None


class Sensor(Base):
    """A generic occupancy-detection source for a zone — deliberately not
    hard-coded to one piece of hardware. sensor_type documents what kind of
    signal it is (a literal PIR/mmWave board, an ESP32 doing its own fusion,
    or a signal derived from a door/RFID event); `status` reflects whether it
    has reported in recently enough to be trusted (see
    services/automation_engine.py's staleness handling — a stale sensor
    is never treated as "confirms empty").
    """
    __tablename__ = "sensors"

    sensor_id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=False, index=True)
    sensor_type = Column(String(20), nullable=False)
    status = Column(String(10), nullable=False, default="offline")
    last_reading = Column(String(200), nullable=True)
    last_seen = Column(DateTime, nullable=True)
    # This sensor's own latest call: True = presence, False = clear,
    # None = no reading yet. The zone's fused occupancy_state (above) is the
    # engine's verdict across all of a zone's sensors plus door/RFID/schedule
    # context, not just this one reading.
    occupancy_state = Column(Boolean, nullable=True)
    # Hardening constraint #2: 'REAL' only when the Phase 2 MQTT telemetry
    # handler wrote this reading from an actual received message
    # (mqtt_service._handle_v2_telemetry/_handle_v2_occupancy); 'SIMULATED'
    # for a manual/testing write via PUT /api/sensors/{id}/reading. Never
    # set to 'REAL' by anything else in this codebase.
    data_source = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "sensor_type IN ('PIR','MMWAVE','ESP32','DOOR_EVENT','RFID_EVENT','OTHER')",
            name="ck_sensor_type",
        ),
        CheckConstraint("status IN ('online','offline')", name="ck_sensor_status"),
        CheckConstraint("data_source IN ('REAL','SIMULATED') OR data_source IS NULL", name="ck_sensor_data_source"),
    )

    zone = relationship("Zone", back_populates="sensors")


class OccupancyEvent(Base):
    """Raw occupancy signal history for a zone — every sensor reading, door
    event, or RFID event that fed into a fused occupancy decision, kept as
    an audit trail separate from the zone's current (mutable) state.
    """
    __tablename__ = "occupancy_events"

    event_id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.sensor_id"), nullable=True)
    occupancy_state = Column(Boolean, nullable=False)  # True = presence detected, False = cleared
    source = Column(String(20), nullable=False)  # sensor | door_event | rfid_event | manual
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    __table_args__ = (
        CheckConstraint(
            "source IN ('sensor','door_event','rfid_event','manual')", name="ck_occupancy_event_source"
        ),
    )

    zone = relationship("Zone")
    sensor = relationship("Sensor")


class Device(Base):
    """A controllable electrical device inside a zone. See the module
    docstring above for why door_ref_id/plug_ref_id exist: when set, this
    Device mirrors an already-working Door AC/light or Plug, and the
    automation engine's ACT step commands it through the existing
    mqtt_service publish_ac/publish_light/publish_plug functions rather than
    a new, parallel control path.
    """
    __tablename__ = "devices"

    device_id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    type = Column(String(30), nullable=False)
    # CRITICAL loads (servers, networking, access control/security systems,
    # the MQTT gateway, emergency systems) stay ON regardless of occupancy —
    # see services/automation_engine.py. Everything else defaults NON_CRITICAL.
    criticality = Column(String(15), nullable=False, default="NON_CRITICAL")
    rated_power = Column(Float, nullable=True)
    current_power = Column(Float, nullable=True)
    status = Column(Boolean, nullable=False, default=False)
    controllable = Column(Boolean, nullable=False, default=True)
    # The automation engine only ever acts on a device with this True — an
    # admin/doctor can flip a device to manual-only (e.g. lab equipment mid-
    # experiment) without disabling the whole zone's automation.
    automatic_control_enabled = Column(Boolean, nullable=False, default=True)

    door_ref_id = Column(Integer, ForeignKey("doors.door_id"), nullable=True)
    plug_ref_id = Column(Integer, ForeignKey("plugs.plug_id"), nullable=True)

    # Hardening constraint #2 (real vs simulated must survive DB storage):
    # whatever most recently set current_power — a real MQTT reading
    # (Phase 2's device/state topic, or a real ac/status|plug/.../status
    # message) sets this to 'REAL'; the energy simulation loop
    # (services/energy_service.py, only used because no real power-metering
    # hardware exists yet) sets it to 'SIMULATED'. None until any reading
    # has ever arrived.
    power_source = Column(String(10), nullable=True)

    # Hardening constraint #6 (command lifecycle, see hardware/interfaces.py
    # for the full COMMAND_SENT/COMMAND_FAILED/COMMAND_ACKNOWLEDGED/
    # STATE_CONFIRMED vocabulary): what the last command issued to this
    # device actually achieved, distinct from device.status, which is this
    # project's optimistic best-guess of the device's current state.
    last_command_status = Column(String(20), nullable=True)
    last_command_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "type IN ('LIGHT','AC','NON_CRITICAL_SOCKET','LAB_EQUIPMENT','SERVER',"
            "'NETWORK_EQUIPMENT','SECURITY_EQUIPMENT','OTHER')",
            name="ck_device_type",
        ),
        CheckConstraint("criticality IN ('CRITICAL','NON_CRITICAL')", name="ck_device_criticality"),
        CheckConstraint("power_source IN ('REAL','SIMULATED') OR power_source IS NULL", name="ck_device_power_source"),
    )

    zone = relationship("Zone", back_populates="devices")
    door_ref = relationship("Door", foreign_keys=[door_ref_id])
    plug_ref = relationship("Plug", foreign_keys=[plug_ref_id])

    @property
    def plug_door_id(self):
        # A plug-backed Device's own door_ref_id is null (plug_ref_id is
        # set instead) — the dashboard still needs the owning door's id to
        # call the existing PUT /api/doors/{door_id}/plugs/{plug_id} control
        # endpoint, so it's exposed here rather than making the frontend
        # guess it.
        return self.plug_ref.door_id if self.plug_ref else None


class AutomationLog(Base):
    """One row per automation decision — the audit trail Step 18 asks for.
    Every SENSE→ANALYZE→VERIFY→DECIDE→ACT pass that results in anything
    other than silently doing nothing gets logged here, with enough context
    (occupancy/schedule/verification/power snapshot + which devices changed
    + why) to fully explain the decision after the fact without guessing.
    zone_id is null for a building-wide decision (e.g. the nightly sweep
    evaluating every zone).
    """
    __tablename__ = "automation_logs"

    log_id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=True, index=True)
    decision = Column(String(30), nullable=False)
    occupancy_snapshot = Column(String(12), nullable=True)
    schedule_state = Column(String(20), nullable=True)  # OPEN | CLOSED | UNKNOWN
    verification_result = Column(String(20), nullable=True)  # PASSED | FAILED | N/A
    power_snapshot = Column(Float, nullable=True)
    devices_changed = Column(Text, nullable=True)  # JSON-encoded [{device_id, name, from, to, command_status}, ...]
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    # Hardening constraint #7 (full decision audit trail): everything below
    # is additional, nullable, and purely explanatory — none of it feeds
    # back into the engine's own decisions, so its absence on old rows (from
    # before this migration) never changes how those rows are interpreted.
    trigger = Column(String(30), nullable=True)  # e.g. "CONFIRMED_EMPTY", "OCCUPANCY_DETECTED"
    confidence = Column(Float, nullable=True)  # Zone.occupancy_confidence snapshot at decision time (Phase 3)
    evidence_snapshot = Column(Text, nullable=True)  # JSON: the same evidence_detail sense_zone_occupancy produced
    matched_rule_id = Column(Integer, ForeignKey("automation_rules.rule_id"), nullable=True)
    # Denormalized on purpose: a rule can be edited or deleted later, but the
    # audit trail must still say which rule (by name, as it was at the time)
    # actually fired — a live FK alone would let history silently change
    # meaning under an admin's feet.
    matched_rule_name = Column(String(120), nullable=True)
    requested_action = Column(String(30), nullable=True)  # the matched rule's actions.action, verbatim
    # JSON: [{"device_id", "name", "reason"}, ...] — anything the engine
    # refused to do and why (e.g. "Critical load protection"). Empty/None
    # means nothing was blocked this pass.
    blocked_actions = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('NO_ACTION','VERIFICATION_STARTED','VERIFICATION_CANCELLED',"
            "'SHUTDOWN_NON_CRITICAL','SHUTDOWN_SKIPPED_UNCERTAIN')",
            name="ck_automation_decision",
        ),
    )

    zone = relationship("Zone")

    @property
    def zone_name(self):
        return self.zone.name if self.zone else "Building-wide"


class AutomationRule(Base):
    """Phase 4: moves the automation engine's decision logic out of hardcoded
    Python and into data an admin can edit/disable per zone, without a code
    change or a redeploy. A null zone_id is a building-wide default that
    applies to any zone without a more specific rule of its own — same
    "null = default" convention as ZoneSchedule above.

    `conditions`/`actions` are deliberately open JSON rather than fixed
    columns, so a future trigger/action type doesn't need another schema
    migration — but only one of each is actually implemented by the engine
    today (see services/automation_engine.py): conditions={"trigger":
    "CONFIRMED_EMPTY"}, actions={"action": "SHUTDOWN_NON_CRITICAL"}. A rule
    with any other action is accepted (kept for forward compatibility) but
    the engine logs NO_ACTION and does nothing for it rather than pretending
    to support it.

    IF a zone reads EMPTY, past its schedule's closing time, and stays that
    way through the full grace_period_minutes (or the schedule's own
    verification_minutes if this rule doesn't override it) THEN
    SHUTDOWN_NON_CRITICAL fires — turning off exactly the NON_CRITICAL,
    automatically-controlled devices in that zone — BUT ONLY IF
    occupancy_confidence at that moment is >= minimum_confidence; below that
    bar the engine refuses to act (SHUTDOWN_SKIPPED_UNCERTAIN) even though
    the verdict itself is EMPTY. CRITICAL devices are never touched by any
    rule, regardless of what actions/criticality_restriction says — that
    protection lives in shutdown_non_critical() itself, not here, so no rule
    (misconfigured or otherwise) can ever switch it off.
    """
    __tablename__ = "automation_rules"

    rule_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    # Among rules equally specific to a zone (or equally building-wide),
    # higher priority is tried first — see automation_engine.get_applicable_rules.
    priority = Column(Integer, nullable=False, default=0)

    conditions = Column(Text, nullable=False)  # JSON, see class docstring
    actions = Column(Text, nullable=False)     # JSON, see class docstring

    # Overrides the applicable ZoneSchedule's verification_minutes when set —
    # lets an admin tune the mandatory wait-before-acting window per rule
    # without editing a raw ZoneSchedule row. Never lets a rule skip the
    # window entirely: None just means "use the schedule's own value."
    grace_period_minutes = Column(Integer, nullable=True)
    # Reserved for a future rule type that acts on an unverified reading.
    # Every trigger implemented today (CONFIRMED_EMPTY) already requires the
    # full verification window as a hard invariant regardless of this flag —
    # seeing it False here does not, by itself, skip verification.
    verification_required = Column(Boolean, nullable=False, default=True)
    # The fused occupancy_confidence (Phase 3) must be at least this high for
    # the rule to fire; below it, the engine logs SHUTDOWN_SKIPPED_UNCERTAIN
    # instead of acting. Never invented at runtime — this is the admin's own
    # configured threshold.
    minimum_confidence = Column(Float, nullable=False, default=0.0)
    schedule_id = Column(Integer, ForeignKey("zone_schedules.schedule_id"), nullable=True)
    # The only legal value today — CRITICAL devices are a hard invariant no
    # rule can override (see class docstring). Kept as a column rather than
    # assumed so a future, deliberately-reviewed rule type has somewhere to
    # say otherwise without a schema change.
    criticality_restriction = Column(String(20), nullable=False, default="NON_CRITICAL_ONLY")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("criticality_restriction IN ('NON_CRITICAL_ONLY')", name="ck_automation_rule_criticality"),
    )

    zone = relationship("Zone")
    schedule = relationship("ZoneSchedule")

    @property
    def zone_name(self):
        return self.zone.name if self.zone else "Building-wide"


class HardwareHealth(Base):
    """Phase 5: connectivity/liveness bookkeeping for one physical node (an
    ESP32, a gateway, a standalone meter — see hardware/interfaces.py's
    HardwareNode). Deliberately keyed by a free-form `node_id` string
    (whatever the node identifies itself as in its heartbeat payload —
    typically its MQTT client id or chip id) rather than a FK to Device or
    Sensor: one physical node commonly drives several of each (one ESP32
    with a relay AND a PIR sensor attached), so there's no single row this
    would otherwise belong to. zone_id is optional, purely for the
    dashboard to group nodes by location.

    status is the one field other code should actually read:
    - ONLINE: a heartbeat arrived within HARDWARE_HEALTH_STALE_AFTER_SECONDS
      and it reported nothing wrong.
    - DEGRADED: a heartbeat arrived on time, but the node itself reported a
      problem (sensor_healthy=False, or a non-empty error_state) — it's
      alive but should not be fully trusted.
    - OFFLINE: no heartbeat within the stale window (see
      services/hardware_health_service.py's sweep, mirroring
      staleness_watchdog.py's own door-staleness pattern).
    - UNKNOWN: no heartbeat has ever arrived for this node_id.

    Hard fail-safe rule this table exists to support, unchanged from
    Phase 3/automation_engine.py: a node going OFFLINE or DEGRADED is never,
    by itself, treated as proof that its zone is empty. It only ever means
    "don't trust this node's own occupancy signal right now" — which
    sense_zone_occupancy already achieves independently via Sensor.last_seen
    staleness. This table does not (and must not) feed occupancy verdicts
    directly; it is a separate, purely informational health signal for
    admins/maintenance, not a new occupancy input.
    """
    __tablename__ = "hardware_health"

    health_id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(80), unique=True, nullable=False, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=True)
    status = Column(String(10), nullable=False, default="UNKNOWN")
    last_seen = Column(DateTime, nullable=True)
    firmware_version = Column(String(40), nullable=True)
    uptime_seconds = Column(Integer, nullable=True)
    rssi = Column(Integer, nullable=True)  # WiFi signal strength in dBm, negative (closer to 0 = stronger)
    mqtt_connected = Column(Boolean, nullable=True)
    # The node's own self-report of its attached sensor(s)' health — distinct
    # from Sensor.status/last_seen, which this backend derives independently.
    sensor_healthy = Column(Boolean, nullable=True)
    error_state = Column(String(120), nullable=True)  # free-form, whatever the node last reported wrong
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        CheckConstraint("status IN ('ONLINE','OFFLINE','DEGRADED','UNKNOWN')", name="ck_hardware_health_status"),
    )

    zone = relationship("Zone")

    @property
    def zone_name(self):
        return self.zone.name if self.zone else None


class ZoneSchedule(Base):
    """Operating hours for the automation engine — distinct from the
    existing Schedule model, which governs automatic *door unlock* windows
    for a course and has nothing to do with HVAC/lighting. A null zone_id
    is the building-wide default that applies to any zone without its own
    override row.
    """
    __tablename__ = "zone_schedules"

    schedule_id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.zone_id"), nullable=True)
    day_of_week = Column(SmallInteger, nullable=True)  # 0=Monday..6=Sunday; null = every day
    open_time = Column(Time, nullable=False)
    close_time = Column(Time, nullable=False)
    # Extra leeway added after close_time before the engine starts caring at
    # all (e.g. a lecture running slightly over) — separate from...
    grace_minutes = Column(Integer, nullable=False, default=10)
    # ...the mandatory Step 11 re-check-before-shutdown window: once the
    # engine first observes a zone reading empty past close_time+grace, it
    # must wait this long and re-verify before it's allowed to act.
    verification_minutes = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    zone = relationship("Zone")


class AuditLog(Base):
    """Final-hardening-pass centralized audit trail — the generic "who did
    what, when, to what, with what result" record that the inspection pass
    found missing: everything before this was piecemeal (AccessEvent is
    door/credential-centric, AutomationLog is automation-engine-only,
    EmergencyOverride logs only itself). This table doesn't replace any of
    those — they stay exactly as they are, each still the authoritative
    detail record for its own domain — this is the cross-cutting index over
    security-sensitive actions system-wide (logins, CRUD on the
    organizational hierarchy, door overrides, user/role changes) that
    nothing could answer "show me every admin action in the last hour"
    against before.

    Immutable by design: no UPDATE/DELETE endpoint is exposed anywhere for
    this table — see app/routers/audit_logs.py, which is read-only.
    `actor_email`/`actor_role` are denormalized (captured at write time, not
    joined live) so a row stays legible even if the actor's account is later
    deleted — same pattern already used for AutomationRule.rule_name on
    AutomationLog and EmergencyOverride's own audit fields.
    """
    __tablename__ = "audit_logs"

    log_id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    actor_email = Column(String(160), nullable=True)  # denormalized; survives actor deletion
    actor_role = Column(String(20), nullable=True)
    action = Column(String(40), nullable=False)  # e.g. 'login_success','login_failed','create','update','delete','lock','unlock','revoke'
    resource_type = Column(String(40), nullable=False, index=True)  # e.g. 'user','faculty','department','course','course_assignment','door','emergency_override'
    resource_id = Column(Integer, nullable=True)
    resource_label = Column(String(160), nullable=True)  # human-readable name/code at the time of the action
    result = Column(String(10), nullable=False, default="success")  # 'success' | 'failure'
    description = Column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint("result IN ('success','failure')", name="ck_audit_log_result"),
    )


class EventInvestigation(Base):
    """Stage C (Investigation & Evidence) — the ONLY new persistent state
    this feature introduces. Deliberately minimal and deliberately NOT a
    second incident/alert system: Alert already owns "is this door/zone
    condition resolved" (Alert.resolved); this table owns a completely
    different question — "has a human reviewed THIS specific AccessEvent,
    and what did they conclude" — for events that have no Alert row at all
    (most access events never generate an Alert).

    One row per AccessEvent that an admin has actually started investigating
    (not one row per event up front — most events are never opened). Lazily
    created on first status change by the investigation router; GET-only
    viewing of an event's investigation never creates a row, matching the
    "read-only views should not generate audit noise" requirement — there is
    nothing to persist until someone changes something.
    """
    __tablename__ = "event_investigations"

    investigation_id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("access_events.event_id"), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="open")  # open | under_review | resolved
    note = Column(String(1000), nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    event = relationship("AccessEvent")
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        CheckConstraint("status IN ('open','under_review','resolved')", name="ck_event_investigation_status"),
    )

    @property
    def updated_by_name(self):
        return self.updated_by.name if self.updated_by else None
