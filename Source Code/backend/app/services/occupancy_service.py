"""
Room occupancy COUNTING (not attendance, not identity).

Ingest path: occupancy node -> OccupancyReading (append-only count history) +
- when the reading is usable - the existing Sensor/OccupancyEvent presence
signal, so the automation engine's own VERIFY window still guards every
action. A count of 0 is a real observation; an errored/stale/absent sensor is
UNAVAILABLE and never reads as 0. Nothing here identifies a person.
"""
from __future__ import annotations

import datetime
import json

from .. import models
from ..config import settings

NODE_SENSOR_TYPE = "OTHER"  # camera people-counter; no dedicated sensor_type exists


def _sensor_for_node(db, zone: models.Zone, node_id: str | None, source: str):
    for s in db.query(models.Sensor).filter(models.Sensor.zone_id == zone.zone_id,
                                            models.Sensor.sensor_type == NODE_SENSOR_TYPE).all():
        try:
            if json.loads(s.last_reading or "{}").get("node_id") == node_id:
                return s
        except ValueError:
            continue
    s = models.Sensor(zone_id=zone.zone_id, sensor_type=NODE_SENSOR_TYPE, status="offline")
    db.add(s)
    db.flush()
    return s


def ingest(db, zone: models.Zone, *, node_id: str | None, count: int | None, confidence: float | None = None,
           sensor_status: str = "ok", source: str = "REAL", recorded_at=None) -> models.OccupancyReading:
    if sensor_status not in ("ok", "degraded", "error"):
        raise ValueError("sensor_status must be ok|degraded|error")
    if source not in ("REAL", "SIMULATED"):
        raise ValueError("source must be REAL or SIMULATED")
    if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > 10000):
        raise ValueError("count must be a non-negative integer")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ValueError("confidence must be within 0..1")
    now = recorded_at or datetime.datetime.utcnow()
    usable = sensor_status != "error" and count is not None
    stored_count = count if usable else None  # error => NULL, never 0

    sensor = _sensor_for_node(db, zone, node_id, source)
    reading = models.OccupancyReading(
        zone_id=zone.zone_id, node_id=node_id, sensor_id=sensor.sensor_id, count=stored_count,
        confidence=confidence, sensor_status=sensor_status, source=source,
        capacity_snapshot=zone.capacity, recorded_at=now)
    db.add(reading)

    sensor.last_seen = now
    sensor.data_source = source
    sensor.status = "online" if usable else "offline"
    sensor.last_reading = json.dumps({"node_id": node_id, "metric": "people_count", "value": stored_count,
                                      "sensor_status": sensor_status, "source": source.lower()})
    if usable:
        present = stored_count > 0
        sensor.occupancy_state = present
        db.add(models.OccupancyEvent(zone_id=zone.zone_id, sensor_id=sensor.sensor_id,
                                     occupancy_state=present, source="sensor"))
        if source == "REAL" and zone.door_id:
            door = db.get(models.Door, zone.door_id)
            if door is not None:
                door.occupied = present
                door.occupancy_updated_at = now
    db.commit()
    db.refresh(reading)
    return reading


def current(db, zone: models.Zone, now=None) -> dict:
    """Latest honest state. count is only present when state == 'OK'."""
    now = now or datetime.datetime.utcnow()
    r = (db.query(models.OccupancyReading).filter(models.OccupancyReading.zone_id == zone.zone_id)
         .order_by(models.OccupancyReading.recorded_at.desc(), models.OccupancyReading.reading_id.desc()).first())
    out = {"zone_id": zone.zone_id, "capacity": zone.capacity, "count": None, "state": "UNAVAILABLE",
           "reason": "No occupancy sensor has reported for this room", "last_updated": None,
           "confidence": None, "source": None, "sensor_status": None, "node_id": None}
    if r is None:
        return out
    out.update(last_updated=r.recorded_at, confidence=r.confidence, source=r.source,
               sensor_status=r.sensor_status, node_id=r.node_id)
    age = (now - r.recorded_at).total_seconds()
    if r.sensor_status == "error" or r.count is None:
        out["reason"] = "Occupancy sensor reported an error"
    elif age > settings.OCCUPANCY_STALE_AFTER_SECONDS:
        out["reason"] = f"Last reading is {int(age)}s old (stale)"
    else:
        out.update(state="OK", count=r.count, reason=None)
        if r.sensor_status == "degraded":
            out["state"] = "DEGRADED"
    return out


def history(db, zone_id: int, since: datetime.datetime, limit: int = 500) -> list[dict]:
    rows = (db.query(models.OccupancyReading)
            .filter(models.OccupancyReading.zone_id == zone_id, models.OccupancyReading.recorded_at >= since)
            .order_by(models.OccupancyReading.recorded_at.asc()).limit(limit).all())
    return [{"recorded_at": r.recorded_at, "count": r.count, "confidence": r.confidence,
             "sensor_status": r.sensor_status, "source": r.source, "capacity": r.capacity_snapshot} for r in rows]


def sensor_health(db, zone: models.Zone, now=None) -> str:
    """ONLINE | DEGRADED | OFFLINE | UNKNOWN for the zone's counting node."""
    c = current(db, zone, now)
    if c["last_updated"] is None:
        return "UNKNOWN"
    if c["state"] == "OK":
        return "ONLINE"
    if c["state"] == "DEGRADED":
        return "DEGRADED"
    return "OFFLINE"


# ---- doctor scope ----------------------------------------------------------
def classes_today(db, user: models.User, now_local=None, now_utc=None) -> list[dict]:
    """Today's classes for this staff member, from REAL rows only:
    CourseAssignment -> Schedule (local-time convention of the legacy
    Schedule table) and recurring AccessWindow (UTC convention)."""
    now_local = now_local or datetime.datetime.now()
    now_utc = now_utc or datetime.datetime.utcnow()
    out = []
    seen = set()
    asg = db.query(models.CourseAssignment).filter(models.CourseAssignment.user_id == user.user_id,
                                                   models.CourseAssignment.status == "active").all()
    for a in asg:
        q = db.query(models.Schedule).filter(models.Schedule.day_of_week == now_local.weekday())
        q = q.filter((models.Schedule.schedule_id == a.schedule_id) | (models.Schedule.course_ref_id == a.course_id))
        for s in q.all():
            if s.schedule_id in seen:
                continue
            seen.add(s.schedule_id)
            out.append({"door_id": s.door_id, "course_code": a.course.code if a.course else s.course_id,
                        "course_name": getattr(a.course, "name", None) if a.course else None,
                        "start": s.start_time, "end": s.end_time,
                        "in_progress": s.start_time <= now_local.time() < s.end_time})
    from . import access_authorization_service as authz
    for w in db.query(models.AccessWindow).filter(models.AccessWindow.user_id == user.user_id,
                                                  models.AccessWindow.recurring.is_(True),
                                                  models.AccessWindow.day_of_week == now_utc.weekday()).all():
        active, _ = authz.is_window_active(w, now_utc)
        key = ("w", w.access_window_id)
        if key in seen:
            continue
        seen.add(key)
        out.append({"door_id": w.door_id, "course_code": w.course_code, "course_name": None,
                    "start": w.start_time, "end": w.end_time, "in_progress": active})
    return sorted(out, key=lambda c: c["start"])
