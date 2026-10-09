"""
Room Health, Room Timeline and Campus Map - READ MODELS over real rows.
Nothing here persists or invents data. A "room" is a Zone (plus its guarding
Door when linked) - the repo has no standalone Room model.

Room Health (deterministic, documented; no percentage):
  UNKNOWN   no monitored source is registered for the room at all
  OFFLINE   every registered source (door, hardware nodes, occupancy/sensors) is offline/stale
  CRITICAL  any open CRITICAL device fault or unresolved CRITICAL Alert
  DEGRADED  any open HIGH fault, or any hardware node DEGRADED/OFFLINE, or
            the door node offline while other sources are alive
  WARNING   any open WARNING fault / unresolved WARNING Alert
  HEALTHY   sources exist and none of the above
Precedence: OFFLINE > CRITICAL > DEGRADED > WARNING > HEALTHY.
"""
from __future__ import annotations

import datetime
import json

from .. import models
from . import hvac_service, occupancy_service


def _sources(db, zone, door, now):
    src = []
    if door is not None:
        src.append(("door", bool(door.online)))
    for n in db.query(models.HardwareHealth).filter(models.HardwareHealth.zone_id == zone.zone_id).all():
        src.append((f"node:{n.node_id}", n.status in ("ONLINE", "DEGRADED")))
    for s in db.query(models.Sensor).filter(models.Sensor.zone_id == zone.zone_id).all():
        src.append((f"sensor:{s.sensor_id}", s.status == "online"))
    return src


def room_health(db, zone: models.Zone, now=None) -> dict:
    now = now or datetime.datetime.utcnow()
    door = db.get(models.Door, zone.door_id) if zone.door_id else None
    sources = _sources(db, zone, door, now)
    reasons = []
    faults = (db.query(models.DeviceFaultAlert).filter(models.DeviceFaultAlert.zone_id == zone.zone_id,
                                                       models.DeviceFaultAlert.status != "RESOLVED").all())
    alert_q = db.query(models.Alert).filter(models.Alert.resolved.is_(False))
    alert_q = alert_q.filter((models.Alert.zone_id == zone.zone_id) |
                             ((models.Alert.door_id == zone.door_id) if zone.door_id else False))
    alerts = alert_q.all()
    nodes = db.query(models.HardwareHealth).filter(models.HardwareHealth.zone_id == zone.zone_id).all()

    if not sources and not faults and not alerts:
        return {"state": "UNKNOWN", "reasons": ["No monitored source registered for this room"]}

    crit = [f for f in faults if f.severity == "CRITICAL"] + [a for a in alerts if a.severity == "CRITICAL"]
    high = [f for f in faults if f.severity == "HIGH"]
    warn = [f for f in faults if f.severity in ("WARNING", "INFO")] + [a for a in alerts if a.severity == "WARNING"]
    bad_nodes = [n for n in nodes if n.status in ("DEGRADED", "OFFLINE")]
    hv = hvac_service.zone_hvac(db, zone, now)
    hvac_down = hv is not None and hv["system_node_status"] in ("OFFLINE", "DEGRADED")
    all_offline = bool(sources) and not any(up for _, up in sources)
    door_down_others_up = door is not None and not door.online and any(up for k, up in sources if k != "door")

    if all_offline:
        state = "OFFLINE"
        reasons.append("Every registered source for this room is offline")
    elif crit:
        state = "CRITICAL"
        reasons += [f"Critical: {getattr(x, 'reason', None) or getattr(x, 'type', '')}" for x in crit]
    elif high or bad_nodes or door_down_others_up or hvac_down:
        state = "DEGRADED"
        reasons += [f"Fault: {f.reason}" for f in high]
        reasons += [f"Node {n.node_id} is {n.status}" for n in bad_nodes]
        if door_down_others_up:
            reasons.append("Door node offline")
        if hvac_down:
            reasons.append(f"Central HVAC node is {hv['system_node_status']}")
    elif warn:
        state = "WARNING"
        reasons += [getattr(x, "reason", None) or f"Alert: {x.type}" for x in warn]
    else:
        state = "HEALTHY"
    return {"state": state, "reasons": reasons}


def timeline(db, zone: models.Zone, since: datetime.datetime, limit: int = 200) -> list[dict]:
    """Unified, newest-first. Each item keeps its own timestamp + provenance
    (source table & REAL/SIMULATED where recorded); storage is not duplicated."""
    ev = []
    did = zone.door_id

    def add(ts, kind, title, detail, source, ref, prov=None):
        if ts is not None and ts >= since:
            ev.append({"timestamp": ts, "type": kind, "title": title, "detail": detail,
                       "provenance": {"table": source, "ref_id": ref, **({"data_source": prov} if prov else {})}})

    if did:
        for e in db.query(models.AccessEvent).filter(models.AccessEvent.door_id == did,
                                                     models.AccessEvent.event_time >= since).all():
            who = e.user.name if e.user else "unknown"
            add(e.event_time, "ACCESS", f"Access {e.result} ({e.method})", f"Subject: {who}", "access_events", e.event_id)
            inv = db.query(models.EventInvestigation).filter(models.EventInvestigation.event_id == e.event_id).first()
            if inv:
                add(inv.updated_at, "INVESTIGATION", f"Investigation {inv.status}", inv.note or "",
                    "event_investigations", inv.investigation_id)
        for o in db.query(models.EmergencyOverride).filter(models.EmergencyOverride.door_id == did,
                                                           models.EmergencyOverride.created_at >= since).all():
            add(o.created_at, "EMERGENCY_OVERRIDE", f"Emergency {o.action} override ({o.status})", o.reason,
                "emergency_overrides", o.override_id)
    for r in (db.query(models.OccupancyReading).filter(models.OccupancyReading.zone_id == zone.zone_id,
                                                       models.OccupancyReading.recorded_at >= since).all()):
        add(r.recorded_at, "OCCUPANCY", "Occupancy " + (f"{r.count}" if r.count is not None else "unavailable"),
            f"sensor_status={r.sensor_status}", "occupancy_readings", r.reading_id, r.source)
    for f in db.query(models.DeviceFaultAlert).filter(models.DeviceFaultAlert.zone_id == zone.zone_id).all():
        name = f.device.name if f.device else f"device {f.device_id}"
        add(f.detected_at, "DEVICE_FAULT", f"{f.severity} - {name}: {f.kind}", f.reason, "device_fault_alerts",
            f.fault_id, f.source)
        add(f.acknowledged_at, "DEVICE_FAULT", f"Fault acknowledged - {name}", "", "device_fault_alerts", f.fault_id)
        add(f.resolved_at, "DEVICE_FAULT", f"Fault resolved - {name}", f.resolution_note or "",
            "device_fault_alerts", f.fault_id)
    aq = db.query(models.Alert).filter(models.Alert.alert_time >= since)
    aq = aq.filter((models.Alert.zone_id == zone.zone_id) | ((models.Alert.door_id == did) if did else False))
    for a in aq.all():
        add(a.alert_time, "ALERT", f"{a.severity} alert: {a.type}", "resolved" if a.resolved else "open",
            "alerts", a.alert_id)
    for l in (db.query(models.AutomationLog).filter(models.AutomationLog.zone_id == zone.zone_id,
                                                    models.AutomationLog.created_at >= since).all()):
        add(l.created_at, "AUTOMATION", f"Automation: {l.decision}", l.reason or "", "automation_logs", l.log_id)
    ev.sort(key=lambda x: x["timestamp"], reverse=True)
    return ev[:limit]


def campus_map(db, now=None) -> dict:
    now = now or datetime.datetime.utcnow()
    buildings: dict = {}
    for z in db.query(models.Zone).all():
        h = room_health(db, z, now)
        occ = occupancy_service.current(db, z, now)
        door = db.get(models.Door, z.door_id) if z.door_id else None
        b = buildings.setdefault(z.building_name or "Unassigned", {"name": z.building_name or "Unassigned", "floors": {}})
        f = b["floors"].setdefault(z.floor or "-", {"floor": z.floor or "-", "rooms": []})
        f["rooms"].append({"zone_id": z.zone_id, "name": z.name, "door_id": z.door_id,
                           "door_code": door.code if door else None, "health": h["state"], "health_reasons": h["reasons"],
                           "occupancy": occ["count"] if occ["state"] in ("OK", "DEGRADED") else None,
                           "occupancy_state": occ["state"], "capacity": z.capacity})
    out = []
    for b in buildings.values():
        b["floors"] = sorted(b["floors"].values(), key=lambda f: str(f["floor"]))
        out.append(b)
    return {"generated_at": now, "buildings": out}


def room_profile(db, zone: models.Zone, now=None) -> dict:
    now = now or datetime.datetime.utcnow()
    door = db.get(models.Door, zone.door_id) if zone.door_id else None
    faults = db.query(models.DeviceFaultAlert).filter(models.DeviceFaultAlert.zone_id == zone.zone_id,
                                                      models.DeviceFaultAlert.status != "RESOLVED").all()
    return {"zone_id": zone.zone_id, "name": zone.name, "building": zone.building_name, "floor": zone.floor,
            "hvac": hvac_service.zone_hvac(db, zone, now),
            "health": room_health(db, zone, now), "occupancy": occupancy_service.current(db, zone, now),
            "sensor_health": occupancy_service.sensor_health(db, zone, now),
            "door": ({"code": door.code, "online": door.online, "locked": door.locked, "last_seen": door.last_seen}
                     if door else None),
            "devices": [{"device_id": d.device_id, "name": d.name, "type": d.type, "status": d.status}
                        for d in zone.devices],
            "open_faults": [{"fault_id": f.fault_id, "severity": f.severity, "reason": f.reason} for f in faults]}


def energy_waste_candidates(db, now=None) -> list[dict]:
    """ANALYZE-only: rooms whose fresh occupancy count is 0 while a light is
    recorded/observed ON and/or the HVAC vent reports airflow. This issues NO
    command; ACT stays with the automation engine's verification window and
    rules. A single reading is a lead, not a decision."""
    now = now or datetime.datetime.utcnow()
    out = []
    for z in db.query(models.Zone).all():
        occ = occupancy_service.current(db, z, now)
        if occ["state"] != "OK" or occ["count"] != 0:
            continue
        reasons = []
        for d in z.devices:
            if d.type != "LIGHT":
                continue
            t = (db.query(models.DeviceTelemetry).filter(models.DeviceTelemetry.device_id == d.device_id)
                 .order_by(models.DeviceTelemetry.recorded_at.desc()).first())
            on_obs = t is not None and (now - t.recorded_at).total_seconds() < 600 and (
                t.observed_on if t.observed_on is not None else (t.power_watts or 0) > 5)
            if on_obs:
                reasons.append(f"{d.name}: observed ON")
            elif d.status:
                reasons.append(f"{d.name}: recorded ON (not sensor-verified)")
        hv = hvac_service.zone_hvac(db, z, now)
        if hv and hv["state"] == "OK" and (hv["airflow_m3h"] or 0) > 0:
            reasons.append("Central HVAC vent shows airflow")
        if reasons:
            out.append({"zone_id": z.zone_id, "room": z.name, "occupancy_count": 0,
                        "occupancy_last_updated": occ["last_updated"], "findings": reasons,
                        "action": "NONE - candidate only; automation requires verification window and rules"})
    return out
