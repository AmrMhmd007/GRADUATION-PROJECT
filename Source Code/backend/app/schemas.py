import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, ConfigDict, computed_field, field_validator

# Academic titles a Doctor/TA profile can carry — kept in one place so the
# API validates against the exact same list the DB CheckConstraint enforces
# (app/models.py::User.__table_args__), rather than duplicating the list and
# risking drift.
ACADEMIC_TITLES = (
    "Professor", "Associate Professor", "Assistant Professor",
    "Lecturer", "Instructor", "Teaching Assistant",
)
STATUS_VALUES = ("active", "inactive")


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Users ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    name: str
    email: EmailStr
    role: str
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    photo_url: Optional[str] = None
    must_change_password: bool = False
    staff_id: Optional[str] = None
    academic_title: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None
    status: str = "active"
    # Phase 12: only ever populated on GET /api/users/me (see routers/users.py
    # get_me) — tells the frontend whether this admin is unrestricted (can
    # manage AdminScope/OperationalScope grants) or scope-limited (cannot;
    # the backend's _require_unrestricted_admin already enforces this
    # server-side regardless of what the UI shows). None for non-admin roles
    # and for any other endpoint returning UserOut, since it isn't relevant
    # there and isn't computed for list endpoints.
    is_scope_restricted: Optional[bool] = None


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: str
    password: str
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None
    staff_id: Optional[str] = None
    academic_title: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("academic_title")
    @classmethod
    def _valid_title(cls, v):
        if v is not None and v not in ACADEMIC_TITLES:
            raise ValueError(f"academic_title must be one of {', '.join(ACADEMIC_TITLES)}")
        return v


class UserUpdateScope(BaseModel):
    """Admin-only: (re)assign a staff member's college/department."""
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None


class StaffUpdate(BaseModel):
    """Admin-only: edit a Doctor/TA's academic profile fields — deliberately
    separate from UserUpdateScope (college/department reassignment) and
    ProfileUpdate (self-service name/photo), since those already have their
    own distinct authorization rules (require_staff_access vs self-only)."""
    name: Optional[str] = None
    staff_id: Optional[str] = None
    academic_title: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None

    @field_validator("academic_title")
    @classmethod
    def _valid_title(cls, v):
        if v is not None and v not in ACADEMIC_TITLES:
            raise ValueError(f"academic_title must be one of {', '.join(ACADEMIC_TITLES)}")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        if v is not None and v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {', '.join(STATUS_VALUES)}")
        return v


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


# ---------- Faculties ----------
class FacultyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    faculty_id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    # Lightweight rollup counts for the College overview screen — computed
    # in the router (not stored) from the same tables StaffScopeView already
    # queries, never a separately-maintained/fake counter.
    departments_count: int = 0
    doctors_count: int = 0
    tas_count: int = 0
    courses_count: int = 0


class FacultyDeletionImpact(BaseModel):
    """Real, backend-computed counts of everything that would be affected by
    permanently deleting a College — shown in the high-risk delete
    confirmation modal so the admin isn't asked to confirm blind. Every
    number here is a live COUNT() against the actual tables, never hardcoded
    or estimated."""
    faculty_id: int
    name: str
    departments: int = 0
    doctors: int = 0
    teaching_assistants: int = 0
    courses: int = 0
    course_assignments: int = 0
    admin_scopes: int = 0
    operational_scopes: int = 0

    @property
    def total_dependent_records(self) -> int:
        return (
            self.departments + self.doctors + self.teaching_assistants + self.courses
            + self.course_assignments + self.admin_scopes + self.operational_scopes
        )


class FacultyDeleteConfirm(BaseModel):
    """Body for the high-risk cascade-delete endpoint. Both fields are
    verified server-side — the frontend never decides whether the name
    matches or the password is correct, it only collects them."""
    confirm_name: str
    password: str


class FacultyCreate(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None


class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        if v is not None and v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {', '.join(STATUS_VALUES)}")
        return v


# ---------- Organizational hierarchy: Department / Course / staff scoping ----------
class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    department_id: int
    faculty_id: int
    faculty_name: Optional[str] = None
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    doctors_count: int = 0
    tas_count: int = 0
    courses_count: int = 0


class DepartmentCreate(BaseModel):
    faculty_id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    faculty_id: Optional[int] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        if v is not None and v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {', '.join(STATUS_VALUES)}")
        return v


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    course_id: int
    department_id: int
    department_name: Optional[str] = None
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    code: str
    name: str
    credit_hours: Optional[int] = None
    level: Optional[str] = None
    semester: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None


class CourseCreate(BaseModel):
    department_id: int
    code: str
    name: str
    credit_hours: Optional[int] = None
    level: Optional[str] = None
    semester: Optional[str] = None
    description: Optional[str] = None

    @field_validator("credit_hours")
    @classmethod
    def _positive_credit_hours(cls, v):
        if v is not None and v <= 0:
            raise ValueError("credit_hours must be positive")
        return v


class CourseUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    department_id: Optional[int] = None
    credit_hours: Optional[int] = None
    level: Optional[str] = None
    semester: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

    @field_validator("credit_hours")
    @classmethod
    def _positive_credit_hours(cls, v):
        if v is not None and v <= 0:
            raise ValueError("credit_hours must be positive")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        if v is not None and v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {', '.join(STATUS_VALUES)}")
        return v


class CourseAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    assignment_id: int
    course_id: int
    user_id: int
    assigned_at: Optional[datetime.datetime] = None
    section: Optional[str] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    status: str = "active"
    schedule_id: Optional[int] = None
    room_name: Optional[str] = None
    room_code: Optional[str] = None


class CourseAssignmentCreate(BaseModel):
    user_id: int
    section: Optional[str] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    schedule_id: Optional[int] = None


class CourseAssignmentUpdate(BaseModel):
    section: Optional[str] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    schedule_id: Optional[int] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v):
        if v is not None and v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {', '.join(STATUS_VALUES)}")
        return v


class AdminScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scope_id: int
    user_id: int
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    operational_scope_id: Optional[int] = None
    operational_scope_name: Optional[str] = None
    created_at: Optional[datetime.datetime] = None


class AdminScopeCreate(BaseModel):
    user_id: int
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None
    operational_scope_id: Optional[int] = None


# ---------- Phase 3: OperationalScope (non-academic operational areas) ----------
class OperationalScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scope_id: int
    name: str
    scope_type: str
    faculty_id: Optional[int] = None
    faculty_name: Optional[str] = None
    building_id: Optional[int] = None
    building_name: Optional[str] = None
    description: Optional[str] = None


class OperationalScopeCreate(BaseModel):
    name: str
    scope_type: str
    building_id: Optional[int] = None
    description: Optional[str] = None


class StaffOut(UserOut):
    """UserOut plus the organizational-hierarchy context a Staff Management
    view needs, without leaking unrelated internal fields (password_hash,
    must_change_password is already on UserOut and is fine to show — an
    admin managing staff legitimately needs to know that)."""
    assigned_courses: List[CourseOut] = []


# ---------- Audit log (Phase 6, final hardening pass) ----------
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: int
    timestamp: datetime.datetime
    actor_user_id: Optional[int] = None
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[int] = None
    resource_label: Optional[str] = None
    result: str
    description: Optional[str] = None


# ---------- Buildings ----------
class BuildingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    building_id: int
    name: str


class BuildingCreate(BaseModel):
    name: str


# ---------- Credentials ----------
class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    credential_id: int
    user_id: Optional[int]
    # Masked (e.g. "****EF01"), never the full decrypted UID — see
    # app/routers/credentials.py for where this gets built. Admins managing
    # cards need enough to recognize *which* card, not the full UID at rest.
    card_uid_masked: Optional[str] = None
    active: bool
    issued_at: datetime.datetime


class CredentialCreate(BaseModel):
    user_id: Optional[int] = None
    card_uid: Optional[str] = None
    fp_template_hash: Optional[str] = None


# ---------- Doors / Rooms ----------
# "Room" is the dashboard-facing name for an access_service Door once it has
# device controls attached — Main Doors (category == 'critical') stay plain
# doors and never populate ac_enabled/light_enabled/plugs.
class PlugOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plug_id: int
    door_id: int
    label: str
    on: bool
    current_amps: Optional[float] = None
    last_seen: Optional[datetime.datetime] = None

    @computed_field
    @property
    def watts(self) -> Optional[float]:
        # Assumes 230V mains — same assumption services/energy_service.py
        # uses when it simulates current_amps in the first place. Purely a
        # display convenience; current_amps stays the value of record.
        return round(self.current_amps * 230, 1) if self.current_amps is not None else None


class PlugCreate(BaseModel):
    label: str = "Plug"


class DeviceToggle(BaseModel):
    on: bool


class DoorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    door_id: int
    code: str
    name: str
    building: str
    floor: Optional[str] = None
    fail_mode: str
    online: bool
    locked: bool
    last_seen: Optional[datetime.datetime]
    category: str  # "critical" | "access_service"
    ac_enabled: bool = False
    ac_on: bool = False
    light_enabled: bool = False
    light_on: bool = False
    ac_current_amps: Optional[float] = None
    plugs: List[PlugOut] = []
    # None = no occupancy sensor has ever reported for this room. True/False
    # once one has (see models.Door.occupied).
    occupied: Optional[bool] = None
    occupancy_updated_at: Optional[datetime.datetime] = None

    @computed_field
    @property
    def ac_watts(self) -> Optional[float]:
        return round(self.ac_current_amps * 230, 1) if self.ac_current_amps is not None else None


class DoorOverrideRequest(BaseModel):
    action: str  # "lock" | "unlock"


class DoorStatusUpdate(BaseModel):
    online: bool


class DoorCreate(BaseModel):
    code: str
    name: str
    building: str
    floor: Optional[str] = None
    fail_mode: str = "secure"  # "secure" | "safe"
    category: str = "access_service"  # "critical" | "access_service"
    # Only meaningful (and only accepted) when category == 'access_service' —
    # the room's device capabilities, decided once at creation time.
    ac_enabled: bool = False
    light_enabled: bool = False
    plug_labels: List[str] = []


# ---------- Door assignments (which TA can request which door) ----------
class DoorAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    assignment_id: int
    door_id: int
    instructor_id: int
    door_code: Optional[str] = None
    door_name: Optional[str] = None
    instructor_name: Optional[str] = None


class DoorAssignmentCreate(BaseModel):
    door_id: int


# ---------- Schedules ----------
class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    schedule_id: int
    door_id: int
    day_of_week: int
    start_time: datetime.time
    end_time: datetime.time
    course_id: Optional[str]
    # Additive, backward-compatible exposure of the existing
    # Schedule.course_ref_id column (models.py) — the real, nullable FK to
    # Course that _validate_assignment_schedule (routers/academic.py) already
    # uses server-side to reject a schedule already linked to a different
    # course. Exposing it lets a client (the Course Assignment UI) pre-filter
    # its own dropdown to the right course's schedules; the backend 409 check
    # remains the sole authoritative enforcement regardless of what the
    # frontend sends. No new column, no duplicate of course_id — same field,
    # just no longer write-only.
    course_ref_id: Optional[int] = None


class ScheduleCreate(BaseModel):
    door_id: int
    day_of_week: int
    start_time: datetime.time
    end_time: datetime.time
    course_id: Optional[str] = None
    # Phase 11: optional, additive admin path for setting course_ref_id at
    # creation time (previously only settable by a direct DB write). See
    # routers/schedules.py for the existence/department-scope/conflict
    # validation applied when this is provided.
    course_ref_id: Optional[int] = None


class ScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    course_id: Optional[str] = None
    course_ref_id: Optional[int] = None


# ---------- Feature #5: Schedule-derived access authorization ----------
class AccessWindowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    access_window_id: int
    door_id: int
    door_code: Optional[str] = None
    door_name: Optional[str] = None
    user_id: int
    course_id: Optional[int] = None
    course_code: Optional[str] = None
    recurring: bool
    day_of_week: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    valid_from: Optional[datetime.datetime] = None
    valid_until: Optional[datetime.datetime] = None
    start_at: Optional[datetime.datetime] = None
    end_at: Optional[datetime.datetime] = None
    reason: Optional[str] = None
    created_by_id: Optional[int] = None
    created_at: Optional[datetime.datetime] = None


class AccessWindowCreate(BaseModel):
    door_id: int
    user_id: int
    course_id: Optional[int] = None
    recurring: bool
    day_of_week: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    valid_from: Optional[datetime.datetime] = None
    valid_until: Optional[datetime.datetime] = None
    start_at: Optional[datetime.datetime] = None
    end_at: Optional[datetime.datetime] = None
    reason: Optional[str] = None


class AccessWindowUpdate(BaseModel):
    day_of_week: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    valid_from: Optional[datetime.datetime] = None
    valid_until: Optional[datetime.datetime] = None
    start_at: Optional[datetime.datetime] = None
    end_at: Optional[datetime.datetime] = None
    reason: Optional[str] = None


class AccessWindowEvaluationOut(BaseModel):
    access_window_id: int
    recurring: bool
    active: bool
    reason: str
    door_id: Optional[int] = None
    course_code: Optional[str] = None


class DoorAuthorizationOut(BaseModel):
    door_id: int
    user_id: int
    evaluated_at: datetime.datetime
    has_permanent_access: bool
    authorized: bool
    reason: str
    windows: List[AccessWindowEvaluationOut] = []


# ---------- Feature #7: Access anomaly indicators ----------
class AnomalyIndicatorOut(BaseModel):
    rule: str
    severity: str
    door_id: int
    door_label: Optional[str] = None
    triggered_at: datetime.datetime
    explanation: str
    evidence: dict


class UserAnomalyReportOut(BaseModel):
    user_id: int
    evaluated_at: datetime.datetime
    lookback_since: datetime.datetime
    event_count_considered: int
    summary: dict
    indicators: List[AnomalyIndicatorOut]


class DoorStaffAnomalyOut(BaseModel):
    user_id: int
    user_name: str
    indicators: List[AnomalyIndicatorOut]


class DoorAnomalyReportOut(BaseModel):
    door_id: int
    evaluated_at: datetime.datetime
    lookback_since: datetime.datetime
    summary: dict
    staff: List[DoorStaffAnomalyOut]


# ---------- Feature #8: Emergency Access / Override ----------
class EmergencyOverrideCreate(BaseModel):
    door_id: int
    action: str  # "lock" | "unlock"
    reason: str
    duration_minutes: int
    # Required for a scope-RESTRICTED admin (checked against
    # security.require_operational_scope_access); optional for an
    # unrestricted admin — same convention as AdminScope.operational_scope_id.
    operational_scope_id: Optional[int] = None


class EmergencyOverrideRevoke(BaseModel):
    # Optional note on WHY it's being revoked early (e.g. "situation
    # resolved") — distinct from the original creation reason, kept for a
    # complete audit trail.
    note: Optional[str] = None


class EmergencyOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    override_id: int
    door_id: int
    door_code: Optional[str] = None
    door_name: Optional[str] = None
    operational_scope_id: Optional[int] = None
    action: str
    reason: str
    created_by_id: int
    created_by_name: Optional[str] = None
    created_at: datetime.datetime
    expires_at: datetime.datetime
    status: str  # stored status: ACTIVE | EXPIRED | REVOKED
    effective_status: str  # live-computed: ACTIVE | EXPIRED | REVOKED (catches a not-yet-swept expiry)
    revoked_at: Optional[datetime.datetime] = None
    revoked_by_id: Optional[int] = None
    seconds_remaining: Optional[int] = None  # None once no longer active


# ---------- Access events ----------
class AccessEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: int
    door_id: int
    credential_id: Optional[int]
    event_time: datetime.datetime
    method: str
    result: str
    user_id: Optional[int] = None


# ---------- Password resets (no-email "forgot password" flow) ----------
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    detail: str
    # Opaque token handed back to the requesting browser only — it's what
    # that tab polls with, and later uses to set its own new password. Not
    # shown to the admin; the admin only ever sees the request's identity.
    request_token: str


class PasswordResetStatusOut(BaseModel):
    status: str  # 'pending' | 'approved' | 'denied' | 'used'


class ResetPasswordRequest(BaseModel):
    request_token: str
    new_password: str


class PasswordResetRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    request_id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    requested_at: datetime.datetime
    status: str
    resolved_at: Optional[datetime.datetime] = None
    resolved_by_name: Optional[str] = None


# ---------- Alerts ----------
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alert_id: int
    # Nullable as of the smart-building expansion: a zone-only alert (e.g. a
    # corridor sensor going offline) has no Door at all.
    door_id: Optional[int] = None
    zone_id: Optional[int] = None
    type: str
    severity: str = "WARNING"  # INFO | WARNING | CRITICAL
    alert_time: datetime.datetime
    resolved: bool
    requested_by: Optional[int] = None
    requested_by_name: Optional[str] = None
    door_name: Optional[str] = None
    door_code: Optional[str] = None
    zone_name: Optional[str] = None


# ---------- Energy: occupancy, power readings, checkout sweep ----------
class OccupancyUpdate(BaseModel):
    occupied: bool


class PowerReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reading_id: int
    door_id: int
    device: str  # 'ac' | 'plug'
    plug_id: Optional[int] = None
    current_amps: float
    watts: float
    recorded_at: datetime.datetime


class SystemSettingsOut(BaseModel):
    checkout_time: str  # "HH:MM", 24h


class SystemSettingsUpdate(BaseModel):
    checkout_time: str


class CheckoutSweepResult(BaseModel):
    rooms_swept: int
    door_codes: List[str]
    ran_at: datetime.datetime


# ============================================================================
# Smart Building Platform: Zones, Sensors, Devices, Automation
# ============================================================================

# ---------- Zones ----------
class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    zone_id: int
    building_id: Optional[int] = None
    building_name: Optional[str] = None
    floor: Optional[str] = None
    name: str
    zone_type: str
    door_id: Optional[int] = None
    door_code: Optional[str] = None
    occupancy_state: str  # OCCUPIED | EMPTY | VERIFYING | UNKNOWN
    occupancy_state_changed_at: Optional[datetime.datetime] = None
    verification_started_at: Optional[datetime.datetime] = None
    # Phase 3: how strongly occupancy_state is corroborated (0.0-1.0) by the
    # signals that fed it, when the fusion pass last ran, and (JSON-encoded,
    # parsed client-side like devices_changed) exactly which signals and
    # weights produced that number.
    occupancy_confidence: Optional[float] = None
    occupancy_computed_at: Optional[datetime.datetime] = None
    occupancy_evidence: Optional[str] = None
    created_at: datetime.datetime


class ZoneCreate(BaseModel):
    building_id: Optional[int] = None
    floor: Optional[str] = None
    name: str
    zone_type: str = "ROOM"
    door_id: Optional[int] = None


class ZoneUpdate(BaseModel):
    building_id: Optional[int] = None
    floor: Optional[str] = None
    name: Optional[str] = None
    zone_type: Optional[str] = None
    door_id: Optional[int] = None


# ---------- Sensors ----------
class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sensor_id: int
    zone_id: int
    sensor_type: str
    status: str  # online | offline
    last_reading: Optional[str] = None
    last_seen: Optional[datetime.datetime] = None
    occupancy_state: Optional[bool] = None
    data_source: Optional[str] = None  # REAL | SIMULATED | None (no reading yet)
    created_at: datetime.datetime


class SensorCreate(BaseModel):
    # zone_id comes from the URL path (/api/zones/{zone_id}/sensors), not
    # duplicated here — matches PlugCreate's own convention.
    sensor_type: str = "OTHER"


class SensorReadingUpdate(BaseModel):
    """What a sensor (real hardware, or the simulation mode) reports in
    with — either over MQTT or this manual/testing endpoint."""
    occupied: bool
    reading: Optional[str] = None  # free-form raw value (a distance, a count, "motion", ...)


# ---------- Devices ----------
class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    device_id: int
    zone_id: int
    name: str
    type: str
    criticality: str  # CRITICAL | NON_CRITICAL
    rated_power: Optional[float] = None
    current_power: Optional[float] = None
    status: bool
    controllable: bool
    automatic_control_enabled: bool
    door_ref_id: Optional[int] = None
    plug_ref_id: Optional[int] = None
    plug_door_id: Optional[int] = None  # the door that owns plug_ref_id, if this is a plug-backed device
    power_source: Optional[str] = None  # REAL | SIMULATED | None (no power reading yet)
    # Command lifecycle (see hardware/interfaces.py's COMMAND_SENT/COMMAND_FAILED/
    # COMMAND_ACKNOWLEDGED/STATE_CONFIRMED vocabulary) — what the last issued
    # command actually achieved, distinct from `status` (this project's
    # optimistic best-guess of the device's current state).
    last_command_status: Optional[str] = None
    last_command_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime


class DeviceCreate(BaseModel):
    # zone_id comes from the URL path (/api/zones/{zone_id}/devices), not
    # duplicated here.
    name: str
    type: str
    criticality: str = "NON_CRITICAL"
    rated_power: Optional[float] = None
    controllable: bool = True
    automatic_control_enabled: bool = True
    door_ref_id: Optional[int] = None
    plug_ref_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    criticality: Optional[str] = None
    rated_power: Optional[float] = None
    controllable: Optional[bool] = None
    automatic_control_enabled: Optional[bool] = None


class DeviceStatusUpdate(BaseModel):
    status: bool  # on/off — for a device with no door_ref/plug_ref (e.g. LAB_EQUIPMENT)


# ---------- Occupancy events & automation log ----------
class OccupancyEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: int
    zone_id: int
    sensor_id: Optional[int] = None
    occupancy_state: bool
    source: str  # sensor | door_event | rfid_event | manual
    created_at: datetime.datetime


class AutomationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: int
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    decision: str
    occupancy_snapshot: Optional[str] = None
    schedule_state: Optional[str] = None
    verification_result: Optional[str] = None
    power_snapshot: Optional[float] = None
    devices_changed: Optional[str] = None  # JSON-encoded list, parsed client-side
    reason: Optional[str] = None
    # Full decision audit trail (hardening constraint #7) — everything
    # needed to reconstruct WHY a decision happened without guessing.
    trigger: Optional[str] = None
    confidence: Optional[float] = None
    evidence_snapshot: Optional[str] = None  # JSON-encoded, same shape as Zone.occupancy_evidence
    matched_rule_id: Optional[int] = None
    matched_rule_name: Optional[str] = None
    requested_action: Optional[str] = None
    blocked_actions: Optional[str] = None  # JSON-encoded [{device_id, name, reason}, ...]
    created_at: datetime.datetime


# ---------- Automation rules (Phase 4) ----------
class AutomationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rule_id: int
    name: str
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    enabled: bool
    priority: int
    conditions: str  # JSON, e.g. {"trigger": "CONFIRMED_EMPTY"}
    actions: str      # JSON, e.g. {"action": "SHUTDOWN_NON_CRITICAL"}
    grace_period_minutes: Optional[int] = None
    verification_required: bool
    minimum_confidence: float
    schedule_id: Optional[int] = None
    criticality_restriction: str
    created_at: datetime.datetime


class AutomationRuleCreate(BaseModel):
    name: str
    zone_id: Optional[int] = None
    enabled: bool = True
    priority: int = 0
    conditions: dict
    actions: dict
    grace_period_minutes: Optional[int] = None
    verification_required: bool = True
    minimum_confidence: float = 0.0
    schedule_id: Optional[int] = None
    criticality_restriction: str = "NON_CRITICAL_ONLY"


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    conditions: Optional[dict] = None
    actions: Optional[dict] = None
    grace_period_minutes: Optional[int] = None
    verification_required: Optional[bool] = None
    minimum_confidence: Optional[float] = None
    schedule_id: Optional[int] = None
    criticality_restriction: Optional[str] = None


# ---------- Stage D / D8: Failed-automation -> Investigation linkage ----------
class RelatedAccessEventOut(BaseModel):
    event_id: int
    event_time: datetime.datetime
    method: str
    result: str
    user_id: Optional[int] = None
    user_name: Optional[str] = None


class AutomationLogRelatedOut(BaseModel):
    log_id: int
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    # A zone only has a real Door to correlate against when it was explicitly
    # linked to one (Zone.door_id) — most zones (corridors, server rooms)
    # never are, and that is reported honestly rather than guessed.
    door_id: Optional[int] = None
    door_name: Optional[str] = None
    door_available: bool = False
    door_unavailable_reason: Optional[str] = None
    alerts: List[AlertOut] = []
    related_access_events: List[RelatedAccessEventOut] = []


# ---------- Hardware health (Phase 5) ----------
class HardwareHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    health_id: int
    node_id: str
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    status: str  # ONLINE | OFFLINE | DEGRADED | UNKNOWN
    last_seen: Optional[datetime.datetime] = None
    firmware_version: Optional[str] = None
    uptime_seconds: Optional[int] = None
    rssi: Optional[int] = None
    mqtt_connected: Optional[bool] = None
    sensor_healthy: Optional[bool] = None
    error_state: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


# ---------- Zone schedules ----------
class ZoneScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    schedule_id: int
    zone_id: Optional[int] = None  # null = building-wide default
    day_of_week: Optional[int] = None
    open_time: datetime.time
    close_time: datetime.time
    grace_minutes: int
    verification_minutes: int


class ZoneScheduleCreate(BaseModel):
    zone_id: Optional[int] = None
    day_of_week: Optional[int] = None
    open_time: datetime.time
    close_time: datetime.time
    grace_minutes: int = 10
    verification_minutes: int = 5


class ZoneScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = None
    open_time: Optional[datetime.time] = None
    close_time: Optional[datetime.time] = None
    grace_minutes: Optional[int] = None
    verification_minutes: Optional[int] = None


# ---------- Combined views ----------
class ZoneSummaryOut(ZoneOut):
    """Used by the zone list endpoint — includes each zone's sensors/devices
    (small, bounded lists) so the dashboard's zone grid can render live
    occupancy/power/device state without an extra round-trip per zone.
    Leaves out the heavier recent_events/recent_automation history that only
    the single-zone detail view needs."""
    sensors: List[SensorOut] = []
    devices: List[DeviceOut] = []


class ZoneDetailOut(ZoneOut):
    """The "click a zone, see everything about it" view (dashboard live map)."""
    sensors: List[SensorOut] = []
    devices: List[DeviceOut] = []
    recent_events: List[OccupancyEventOut] = []
    recent_automation: List[AutomationLogOut] = []


class SmartBuildingSummary(BaseModel):
    """Top-level numbers for the Smart Building dashboard tab."""
    building_state: str  # OCCUPIED | EMPTY | VERIFYING | UNKNOWN (fused across all zones)
    zones_total: int
    zones_occupied: int
    zones_empty: int
    zones_verifying: int
    zones_unknown: int
    devices_on: int
    devices_off: int
    critical_devices_on: int
    current_power_watts: float
    energy_saved_watts_estimate: float


# ---------- Stage C: Investigation & Evidence ----------
class EventInvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    investigation_id: int
    event_id: int
    status: str
    note: Optional[str] = None
    updated_by_id: Optional[int] = None
    updated_by_name: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None


class EventInvestigationUpdate(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


class TimelineItemOut(BaseModel):
    timestamp: datetime.datetime
    source: str  # access_event | anomaly | emergency_override | audit_log
    description: str
    is_focus_event: bool = False
    ref_id: Optional[int] = None  # the source record's own id (event_id/override_id/log_id), for click-through


class AccessEventDetailOut(BaseModel):
    """The full "investigate this event" view — see investigation_service.py
    for how each section is built and the PHYSICAL / DECISION / SECURITY
    INTERPRETATION distinction the frontend relies on."""
    event_id: int
    door_id: int
    door_name: Optional[str] = None
    door_code: Optional[str] = None
    building: Optional[str] = None
    event_time: datetime.datetime
    method: str
    result: str
    credential_id: Optional[int] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None

    # PHYSICAL FACTS — the door's CURRENT state (never historical; there is
    # no persisted physical-state-at-time-of-event snapshot in this system).
    physical_door_state: dict

    # AUTHORIZATION DECISION — from the event's own recorded evidence_snapshot
    # where available; None if this event has no usable snapshot at all.
    evidence_available: bool
    evidence_basis: str  # "recorded_snapshot" | "unavailable"
    evidence: Optional[dict] = None
    authorization: Optional[dict] = None

    # SECURITY INTERPRETATION — real, already-computed anomaly indicators
    # that reference this same door/user around this event, never invented.
    related_anomalies: List[dict] = []
    related_override: Optional[dict] = None
    related_audit: List[dict] = []
    related_audit_available: bool = True
    related_audit_unavailable_reason: Optional[str] = None

    investigation: Optional[EventInvestigationOut] = None


class AccessEventListItemOut(BaseModel):
    event_id: int
    door_id: int
    door_name: Optional[str] = None
    door_code: Optional[str] = None
    building: Optional[str] = None
    event_time: datetime.datetime
    method: str
    result: str
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    has_evidence: bool
    investigation_status: Optional[str] = None


# ---------- Global Search ----------
class SearchResultOut(BaseModel):
    """One authorized, real, navigable hit. Deliberately NOT a raw ORM
    object or a passthrough of any *Out schema above — a hand-picked, small
    set of display fields plus real navigation metadata (see
    services/search_service.py for how `nav` maps onto Dashboard.jsx's
    existing hash-based deep-link params, never an invented route). No
    field here is a secret, credential, or internal DB implementation
    detail — see search_service.py's per-entity builders for exactly what
    is (and is deliberately not) included."""
    type: str          # e.g. "college" | "department" | "course" | "staff" | "door" | ...
    category: str      # display grouping: "Academic" | "Security" | "Infrastructure" | "Automation"
    id: int
    title: str
    subtitle: Optional[str] = None
    meta: Optional[str] = None
    nav_tab: str
    nav_params: dict = {}
    nav_action: Optional[str] = None   # only "open_zone" today — see search_service.py
    nav_action_id: Optional[int] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultOut] = []
    query_too_short: bool = False
