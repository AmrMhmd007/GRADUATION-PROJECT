from __future__ import annotations

import datetime
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import audit_service, automation_engine, energy_timeseries_service

router = APIRouter(prefix="/api", tags=["smart-building"])


# ============================================================================
# Zones
# ============================================================================
@router.get("/zones", response_model=List[schemas.ZoneSummaryOut])
def list_zones(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    """Includes each zone's sensors/devices inline so the dashboard's zone
    grid can render live occupancy/power/device state in one request."""
    return db.query(models.Zone).all()


@router.post("/zones", response_model=schemas.ZoneOut, status_code=201)
def create_zone(payload: schemas.ZoneCreate, db: Session = Depends(get_db),
                 _admin=Depends(security.require_admin)):
    valid_types = {"ROOM", "CLASSROOM", "LAB", "CORRIDOR", "OFFICE", "SERVER_ROOM", "OTHER"}
    if payload.zone_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"zone_type must be one of {sorted(valid_types)}")
    if payload.door_id is not None:
        door = db.query(models.Door).filter(models.Door.door_id == payload.door_id).first()
        if not door:
            raise HTTPException(status_code=404, detail="Door not found")
        existing = db.query(models.Zone).filter(models.Zone.door_id == payload.door_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="That door is already linked to another zone")

    zone = models.Zone(
        building_id=payload.building_id, floor=payload.floor, name=payload.name,
        zone_type=payload.zone_type, door_id=payload.door_id, occupancy_state="UNKNOWN",
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    audit_service.log(db, actor=_admin, action="create", resource_type="zone", resource_id=zone.zone_id,
                       resource_label=zone.name)
    return zone


@router.get("/zones/{zone_id}", response_model=schemas.ZoneDetailOut)
def get_zone(zone_id: int, db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    zone = db.query(models.Zone).filter(models.Zone.zone_id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    recent_events = (
        db.query(models.OccupancyEvent)
        .filter(models.OccupancyEvent.zone_id == zone_id)
        .order_by(models.OccupancyEvent.created_at.desc())
        .limit(50)
        .all()
    )
    recent_automation = (
        db.query(models.AutomationLog)
        .filter(models.AutomationLog.zone_id == zone_id)
        .order_by(models.AutomationLog.created_at.desc())
        .limit(50)
        .all()
    )
    detail = schemas.ZoneDetailOut.model_validate(zone)
    detail.recent_events = [schemas.OccupancyEventOut.model_validate(e) for e in recent_events]
    detail.recent_automation = [schemas.AutomationLogOut.model_validate(a) for a in recent_automation]
    return detail


@router.put("/zones/{zone_id}", response_model=schemas.ZoneOut)
def update_zone(zone_id: int, payload: schemas.ZoneUpdate, db: Session = Depends(get_db),
                 _admin=Depends(security.require_admin)):
    zone = db.query(models.Zone).filter(models.Zone.zone_id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    data = payload.model_dump(exclude_unset=True)
    if "door_id" in data and data["door_id"] is not None:
        existing = (
            db.query(models.Zone)
            .filter(models.Zone.door_id == data["door_id"], models.Zone.zone_id != zone_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="That door is already linked to another zone")
    for field, value in data.items():
        setattr(zone, field, value)
    db.commit()
    db.refresh(zone)
    audit_service.log(db, actor=_admin, action="update", resource_type="zone", resource_id=zone.zone_id,
                       resource_label=zone.name)
    return zone


@router.delete("/zones/{zone_id}", status_code=204)
def delete_zone(zone_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    zone = db.query(models.Zone).filter(models.Zone.zone_id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    zone_id_val, zone_name = zone.zone_id, zone.name
    db.query(models.Alert).filter(models.Alert.zone_id == zone_id).update({"zone_id": None})
    db.delete(zone)
    db.commit()
    audit_service.log(db, actor=_admin, action="delete", resource_type="zone", resource_id=zone_id_val,
                       resource_label=zone_name)


# ============================================================================
# Sensors
# ============================================================================
@router.get("/sensors", response_model=List[schemas.SensorOut])
def list_all_sensors(zone_id: Optional[int] = None, db: Session = Depends(get_db),
                      _user=Depends(security.get_current_user)):
    """Every sensor across every zone — backs the Sensor Monitoring panel,
    where seeing a stale/offline sensor anywhere in the building matters
    more than which zone it happens to be in."""
    query = db.query(models.Sensor)
    if zone_id is not None:
        query = query.filter(models.Sensor.zone_id == zone_id)
    return query.all()


@router.get("/zones/{zone_id}/sensors", response_model=List[schemas.SensorOut])
def list_zone_sensors(zone_id: int, db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Sensor).filter(models.Sensor.zone_id == zone_id).all()


@router.post("/zones/{zone_id}/sensors", response_model=schemas.SensorOut, status_code=201)
def create_sensor(zone_id: int, payload: schemas.SensorCreate, db: Session = Depends(get_db),
                   _admin=Depends(security.require_admin)):
    zone = db.query(models.Zone).filter(models.Zone.zone_id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    valid_types = {"PIR", "MMWAVE", "ESP32", "DOOR_EVENT", "RFID_EVENT", "OTHER"}
    if payload.sensor_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"sensor_type must be one of {sorted(valid_types)}")
    sensor = models.Sensor(zone_id=zone_id, sensor_type=payload.sensor_type, status="offline")
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    audit_service.log(db, actor=_admin, action="create", resource_type="sensor", resource_id=sensor.sensor_id,
                       resource_label=f"{sensor.sensor_type} in zone {zone_id}")
    return sensor


@router.post("/sensors/{sensor_id}/reading", response_model=schemas.SensorOut)
def report_sensor_reading(sensor_id: int, payload: schemas.SensorReadingUpdate, db: Session = Depends(get_db),
                           _admin=Depends(security.require_admin)):
    """Manual/testing stand-in for a real sensor reporting in over MQTT (see
    the Step 19/20 MQTT+ESP32 wiring, which will call the same update
    directly rather than through this HTTP endpoint). Also logs an
    OccupancyEvent so the zone's history/audit trail has a real record of
    every reading, not just the sensor's latest snapshot."""
    sensor = db.query(models.Sensor).filter(models.Sensor.sensor_id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    now = datetime.datetime.utcnow()
    sensor.occupancy_state = payload.occupied
    sensor.last_reading = payload.reading
    sensor.last_seen = now
    sensor.status = "online"
    # Hardening constraint #2: this is a human/testing input standing in for
    # real hardware, never treat it as if it were one. The MQTT telemetry
    # handlers (mqtt_service._handle_v2_telemetry/_handle_v2_occupancy) are
    # the only code paths allowed to write 'REAL' here.
    sensor.data_source = "SIMULATED"
    db.add(models.OccupancyEvent(
        zone_id=sensor.zone_id, sensor_id=sensor.sensor_id, occupancy_state=payload.occupied, source="sensor",
    ))
    db.commit()
    db.refresh(sensor)
    return sensor


@router.delete("/sensors/{sensor_id}", status_code=204)
def delete_sensor(sensor_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    sensor = db.query(models.Sensor).filter(models.Sensor.sensor_id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor_id_val, sensor_type, zone_id_val = sensor.sensor_id, sensor.sensor_type, sensor.zone_id
    db.delete(sensor)
    db.commit()
    audit_service.log(db, actor=_admin, action="delete", resource_type="sensor", resource_id=sensor_id_val,
                       resource_label=f"{sensor_type} in zone {zone_id_val}")


# ============================================================================
# Devices
# ============================================================================
@router.get("/zones/{zone_id}/devices", response_model=List[schemas.DeviceOut])
def list_zone_devices(zone_id: int, db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    return db.query(models.Device).filter(models.Device.zone_id == zone_id).all()


_VALID_DEVICE_TYPES = {
    "LIGHT", "AC", "NON_CRITICAL_SOCKET", "LAB_EQUIPMENT", "SERVER",
    "NETWORK_EQUIPMENT", "SECURITY_EQUIPMENT", "OTHER",
}


@router.post("/zones/{zone_id}/devices", response_model=schemas.DeviceOut, status_code=201)
def create_device(zone_id: int, payload: schemas.DeviceCreate, db: Session = Depends(get_db),
                   _admin=Depends(security.require_admin)):
    zone = db.query(models.Zone).filter(models.Zone.zone_id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    if payload.type not in _VALID_DEVICE_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(_VALID_DEVICE_TYPES)}")
    if payload.criticality not in ("CRITICAL", "NON_CRITICAL"):
        raise HTTPException(status_code=400, detail="criticality must be 'CRITICAL' or 'NON_CRITICAL'")

    device = models.Device(
        zone_id=zone_id, name=payload.name, type=payload.type, criticality=payload.criticality,
        rated_power=payload.rated_power, controllable=payload.controllable,
        automatic_control_enabled=payload.automatic_control_enabled,
        door_ref_id=payload.door_ref_id, plug_ref_id=payload.plug_ref_id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    audit_service.log(db, actor=_admin, action="create", resource_type="device", resource_id=device.device_id,
                       resource_label=device.name)
    return device


@router.put("/devices/{device_id}", response_model=schemas.DeviceOut)
def update_device(device_id: int, payload: schemas.DeviceUpdate, db: Session = Depends(get_db),
                   _admin=Depends(security.require_admin)):
    device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    data = payload.model_dump(exclude_unset=True)
    if "criticality" in data and data["criticality"] not in ("CRITICAL", "NON_CRITICAL"):
        raise HTTPException(status_code=400, detail="criticality must be 'CRITICAL' or 'NON_CRITICAL'")
    for field, value in data.items():
        setattr(device, field, value)
    db.commit()
    db.refresh(device)
    audit_service.log(db, actor=_admin, action="update", resource_type="device", resource_id=device.device_id,
                       resource_label=device.name)
    return device


@router.post("/devices/{device_id}/status", response_model=schemas.DeviceOut)
def set_device_status(device_id: int, payload: schemas.DeviceStatusUpdate, db: Session = Depends(get_db),
                       _admin=Depends(security.require_admin)):
    """Manual on/off for a device with no existing control path
    (door_ref_id/plug_ref_id) — e.g. LAB_EQUIPMENT. A device that *does*
    mirror a Door's AC/light or a Plug should be controlled through the
    existing /api/doors/... endpoints instead, which this Device's status
    is kept in sync with automatically (see automation_engine._sync_device_power).
    """
    device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.controllable:
        raise HTTPException(status_code=400, detail="This device isn't controllable")
    if device.door_ref_id or device.plug_ref_id:
        raise HTTPException(
            status_code=400,
            detail="This device mirrors existing door/plug hardware — control it via the door/plug endpoint instead.",
        )
    device.status = payload.status
    if not payload.status:
        device.current_power = None
    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device_id_val, device_name = device.device_id, device.name
    db.delete(device)
    db.commit()
    audit_service.log(db, actor=_admin, action="delete", resource_type="device", resource_id=device_id_val,
                       resource_label=device_name)


# ============================================================================
# Zone schedules
# ============================================================================
@router.get("/zone-schedules", response_model=List[schemas.ZoneScheduleOut])
def list_zone_schedules(zone_id: Optional[int] = None, db: Session = Depends(get_db),
                         _user=Depends(security.get_current_user)):
    query = db.query(models.ZoneSchedule)
    if zone_id is not None:
        query = query.filter(models.ZoneSchedule.zone_id == zone_id)
    return query.all()


@router.post("/zone-schedules", response_model=schemas.ZoneScheduleOut, status_code=201)
def create_zone_schedule(payload: schemas.ZoneScheduleCreate, db: Session = Depends(get_db),
                          _admin=Depends(security.require_admin)):
    if payload.zone_id is not None:
        zone = db.query(models.Zone).filter(models.Zone.zone_id == payload.zone_id).first()
        if not zone:
            raise HTTPException(status_code=404, detail="Zone not found")
    if payload.open_time >= payload.close_time:
        raise HTTPException(status_code=400, detail="open_time must be before close_time")
    schedule = models.ZoneSchedule(**payload.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    # Phase 12: a persisted automation-config mutation, same category as
    # AutomationRule CRUD (already audited, Phase 11) — not an
    # execution/query action, so it belongs in AuditLog.
    audit_service.log(db, actor=_admin, action="create", resource_type="zone_schedule", resource_id=schedule.schedule_id,
                       resource_label=f"zone {schedule.zone_id}" if schedule.zone_id else "all zones")
    return schedule


@router.put("/zone-schedules/{schedule_id}", response_model=schemas.ZoneScheduleOut)
def update_zone_schedule(schedule_id: int, payload: schemas.ZoneScheduleUpdate, db: Session = Depends(get_db),
                          _admin=Depends(security.require_admin)):
    schedule = db.query(models.ZoneSchedule).filter(models.ZoneSchedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Zone schedule not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)
    audit_service.log(db, actor=_admin, action="update", resource_type="zone_schedule", resource_id=schedule.schedule_id,
                       resource_label=f"zone {schedule.zone_id}" if schedule.zone_id else "all zones")
    return schedule


@router.delete("/zone-schedules/{schedule_id}", status_code=204)
def delete_zone_schedule(schedule_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    schedule = db.query(models.ZoneSchedule).filter(models.ZoneSchedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Zone schedule not found")
    schedule_id_val, zone_id_val = schedule.schedule_id, schedule.zone_id
    db.delete(schedule)
    db.commit()
    audit_service.log(db, actor=_admin, action="delete", resource_type="zone_schedule", resource_id=schedule_id_val,
                       resource_label=f"zone {zone_id_val}" if zone_id_val else "all zones")


# ============================================================================
# Energy time series (Phase 6) — Zone/Device-scoped, see EnergyReading's own
# docstring in models.py for how this relates to the legacy PowerReading
# table the original /api/energy endpoints (routers/energy.py) still serve.
# ============================================================================
@router.get("/energy/current")
def get_energy_current(zone_id: Optional[int] = None, db: Session = Depends(get_db),
                        _user=Depends(security.get_current_user)):
    return energy_timeseries_service.current_snapshot(db, zone_id=zone_id)


@router.get("/energy/timeseries")
def get_energy_timeseries(granularity: str, zone_id: Optional[int] = None, device_id: Optional[int] = None,
                           start: Optional[datetime.datetime] = None, end: Optional[datetime.datetime] = None,
                           db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    if granularity not in ("hourly", "daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="granularity must be one of hourly, daily, weekly, monthly")
    return energy_timeseries_service.aggregate(
        db, granularity, zone_id=zone_id, device_id=device_id, start=start, end=end,
    )


@router.get("/energy/savings-estimate")
def get_energy_savings_estimate(zone_id: Optional[int] = None, db: Session = Depends(get_db),
                                 _user=Depends(security.get_current_user)):
    return {"estimated_savings_watts": round(energy_timeseries_service.estimate_savings_watts(db, zone_id=zone_id), 1)}


# ============================================================================
# Automation
# ============================================================================
@router.get("/automation/logs", response_model=List[schemas.AutomationLogOut])
def list_automation_logs(zone_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_db),
                          _user=Depends(security.get_current_user)):
    query = db.query(models.AutomationLog)
    if zone_id is not None:
        query = query.filter(models.AutomationLog.zone_id == zone_id)
    return query.order_by(models.AutomationLog.created_at.desc()).limit(limit).all()


@router.get("/hardware-health", response_model=List[schemas.HardwareHealthOut])
def list_hardware_health(zone_id: Optional[int] = None, db: Session = Depends(get_db),
                          _user=Depends(security.get_current_user)):
    """Phase 5: node connectivity/liveness — see
    services/hardware_health_service.py. Purely informational; never an
    occupancy input (see HardwareHealth's own docstring in models.py)."""
    query = db.query(models.HardwareHealth)
    if zone_id is not None:
        query = query.filter(models.HardwareHealth.zone_id == zone_id)
    return query.order_by(models.HardwareHealth.updated_at.desc()).all()


@router.get("/automation/rules", response_model=List[schemas.AutomationRuleOut])
def list_automation_rules(zone_id: Optional[int] = None, db: Session = Depends(get_db),
                           _user=Depends(security.get_current_user)):
    """Phase 4: the data-backed rules the engine actually consults each pass
    (see services/automation_engine.get_applicable_rules) — no visual rule
    builder yet, this is the raw CRUD API those come from."""
    query = db.query(models.AutomationRule)
    if zone_id is not None:
        query = query.filter(models.AutomationRule.zone_id == zone_id)
    return query.order_by(models.AutomationRule.priority.desc()).all()


@router.post("/automation/rules", response_model=schemas.AutomationRuleOut, status_code=201)
def create_automation_rule(payload: schemas.AutomationRuleCreate, db: Session = Depends(get_db),
                            _admin=Depends(security.require_admin)):
    if payload.zone_id is not None:
        zone = db.query(models.Zone).filter(models.Zone.zone_id == payload.zone_id).first()
        if not zone:
            raise HTTPException(status_code=404, detail="Zone not found")
    if payload.conditions.get("trigger") != automation_engine.TRIGGER_CONFIRMED_EMPTY:
        raise HTTPException(
            status_code=400,
            detail=f"Only trigger '{automation_engine.TRIGGER_CONFIRMED_EMPTY}' is implemented today",
        )
    data = payload.model_dump()
    data["conditions"] = json.dumps(data["conditions"])
    data["actions"] = json.dumps(data["actions"])
    rule = models.AutomationRule(**data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    audit_service.log(db, actor=_admin, action="create", resource_type="automation_rule", resource_id=rule.rule_id,
                       resource_label=rule.name)
    return rule


@router.put("/automation/rules/{rule_id}", response_model=schemas.AutomationRuleOut)
def update_automation_rule(rule_id: int, payload: schemas.AutomationRuleUpdate, db: Session = Depends(get_db),
                            _admin=Depends(security.require_admin)):
    rule = db.query(models.AutomationRule).filter(models.AutomationRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    updates = payload.model_dump(exclude_unset=True)
    if "conditions" in updates:
        updates["conditions"] = json.dumps(updates["conditions"])
    if "actions" in updates:
        updates["actions"] = json.dumps(updates["actions"])
    for field, value in updates.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    audit_service.log(db, actor=_admin, action="update", resource_type="automation_rule", resource_id=rule.rule_id,
                       resource_label=rule.name)
    return rule


@router.delete("/automation/rules/{rule_id}", status_code=204)
def delete_automation_rule(rule_id: int, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    rule = db.query(models.AutomationRule).filter(models.AutomationRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    rule_id_val, rule_name = rule.rule_id, rule.name
    db.delete(rule)
    db.commit()
    audit_service.log(db, actor=_admin, action="delete", resource_type="automation_rule", resource_id=rule_id_val,
                       resource_label=rule_name)


@router.post("/automation/run-once")
def run_automation_once(db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    """Manual "run a pass right now" trigger for demos/testing — the
    background engine already does this every AUTOMATION_INTERVAL_SECONDS
    on its own."""
    count = automation_engine.run_automation_pass(db)
    return {"zones_with_activity": count, "ran_at": datetime.datetime.utcnow()}


@router.get("/automation/summary", response_model=schemas.SmartBuildingSummary)
def smart_building_summary(db: Session = Depends(get_db), _user=Depends(security.get_current_user)):
    zones = db.query(models.Zone).all()
    devices = db.query(models.Device).all()
    active_alerts = db.query(models.Alert).filter(models.Alert.resolved.is_(False)).count()

    devices_on = sum(1 for d in devices if d.status)
    devices_off = sum(1 for d in devices if not d.status)
    critical_on = sum(1 for d in devices if d.status and d.criticality == "CRITICAL")
    current_power = sum((d.current_power or 0) for d in devices if d.status)

    # Rough "energy saved" estimate: what every currently-off, automatically-
    # controlled non-critical device would be drawing at its rated power if
    # the engine hadn't switched it off. A simple, explainable number for
    # the dashboard rather than a rigorous energy-accounting figure — see
    # energy_timeseries_service.estimate_savings_watts, the one place this
    # project computes it.
    saved_estimate = energy_timeseries_service.estimate_savings_watts(db)

    return schemas.SmartBuildingSummary(
        building_state=automation_engine.building_occupancy_state(db),
        zones_total=len(zones),
        zones_occupied=sum(1 for z in zones if z.occupancy_state == "OCCUPIED"),
        zones_empty=sum(1 for z in zones if z.occupancy_state == "EMPTY"),
        zones_verifying=sum(1 for z in zones if z.occupancy_state == "VERIFYING"),
        zones_unknown=sum(1 for z in zones if z.occupancy_state == "UNKNOWN"),
        devices_on=devices_on,
        devices_off=devices_off,
        critical_devices_on=critical_on,
        current_power_watts=round(current_power, 1),
        energy_saved_watts_estimate=round(saved_estimate, 1),
        active_alerts=active_alerts,
    )
