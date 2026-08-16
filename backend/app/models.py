import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, SmallInteger,
    String, Time,
)
from sqlalchemy.orm import relationship

from .database import Base


class Faculty(Base):
    """A TA/doctor's home faculty (e.g. "Faculty of Engineering") — picked
    when adding a TA or doctor, managed by the admin from that same form.
    """
    __tablename__ = "faculties"

    faculty_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)


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
    # Relative URL under /media (e.g. "/media/avatars/3-ab12cd34.jpg"), served
    # as a static file — see app/main.py's StaticFiles mount.
    photo_url = Column(String(255), nullable=True)

    __table_args__ = (CheckConstraint("role IN ('admin','instructor','doctor')", name="ck_user_role"),)

    credentials = relationship("Credential", back_populates="user")
    faculty = relationship("Faculty")

    @property
    def faculty_name(self):
        return self.faculty.name if self.faculty else None


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

    __table_args__ = (
        CheckConstraint("fail_mode IN ('safe','secure')", name="ck_door_fail_mode"),
        CheckConstraint("category IN ('critical','access_service')", name="ck_door_category"),
    )

    schedules = relationship("Schedule", back_populates="door")
    access_events = relationship("AccessEvent", back_populates="door")
    alerts = relationship("Alert", back_populates="door")


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


class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Monday .. 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    course_id = Column(String(40), nullable=True)

    door = relationship("Door", back_populates="schedules")


class AccessEvent(Base):
    __tablename__ = "access_events"

    event_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    credential_id = Column(Integer, ForeignKey("credentials.credential_id"), nullable=True)
    event_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    method = Column(String(20), nullable=False)   # card | card+fingerprint | override | rex
    result = Column(String(20), nullable=False)   # granted | denied

    door = relationship("Door", back_populates="access_events")
    credential = relationship("Credential", back_populates="access_events")


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, index=True)
    door_id = Column(Integer, ForeignKey("doors.door_id"), nullable=False)
    # tamper | forced | offline | propped_open | access_denied | access_requested
    type = Column(String(30), nullable=False)
    alert_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    resolved = Column(Boolean, default=False)
    # Set only for type == "access_requested": which instructor asked. Reuses
    # the existing alert feed/AlertBanner (already polled + rendered) instead
    # of building a separate notifications system from scratch.
    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    door = relationship("Door", back_populates="alerts")
    requester = relationship("User", foreign_keys=[requested_by])

    @property
    def requested_by_name(self):
        return self.requester.name if self.requester else None
