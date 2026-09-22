import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, ConfigDict


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
    photo_url: Optional[str] = None
    must_change_password: bool = False


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: str
    password: str
    faculty_id: Optional[int] = None


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


class FacultyCreate(BaseModel):
    name: str


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
    plugs: List[PlugOut] = []


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


class ScheduleCreate(BaseModel):
    door_id: int
    day_of_week: int
    start_time: datetime.time
    end_time: datetime.time
    course_id: Optional[str] = None


class ScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = None
    start_time: Optional[datetime.time] = None
    end_time: Optional[datetime.time] = None
    course_id: Optional[str] = None


# ---------- Access events ----------
class AccessEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: int
    door_id: int
    credential_id: Optional[int]
    event_time: datetime.datetime
    method: str
    result: str


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
    door_id: int
    type: str
    alert_time: datetime.datetime
    resolved: bool
    requested_by: Optional[int] = None
    requested_by_name: Optional[str] = None
