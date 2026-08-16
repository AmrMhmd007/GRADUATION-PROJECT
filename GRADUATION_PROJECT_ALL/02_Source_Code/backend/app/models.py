import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, SmallInteger,
    String, Time,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """Matches the `users` table in the System Design Document (Section 4)."""
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'admin' | 'instructor'
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (CheckConstraint("role IN ('admin','instructor')", name="ck_user_role"),)

    credentials = relationship("Credential", back_populates="user")


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
    fail_mode = Column(String(10), nullable=False, default="secure")  # 'safe' | 'secure'
    # Live status fields, updated by the MQTT ingestion service — not in the
    # original ERD but needed to back the dashboard's door-status cards.
    online = Column(Boolean, default=False)
    locked = Column(Boolean, default=True)
    last_seen = Column(DateTime, nullable=True)

    __table_args__ = (CheckConstraint("fail_mode IN ('safe','secure')", name="ck_door_fail_mode"),)

    schedules = relationship("Schedule", back_populates="door")
    access_events = relationship("AccessEvent", back_populates="door")
    alerts = relationship("Alert", back_populates="door")


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
    type = Column(String(30), nullable=False)  # tamper | forced | offline | propped_open | access_denied
    alert_time = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    resolved = Column(Boolean, default=False)

    door = relationship("Door", back_populates="alerts")
