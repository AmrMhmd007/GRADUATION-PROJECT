"""
Physical device fault monitoring: expected state vs OBSERVED physical state.

Humans operate devices physically; a sensor reports; the backend verifies.
This service never commands anything and never assumes a device has a
sensor: with no telemetry there is nothing to verify and NO fault is
invented (a device without a sensor is simply "unmonitored").

Expectation basis (explicit, never implied by a class merely existing):
Device.status is treated as the expected state only when the device has a
recorded command lifecycle (Device.last_command_status is set), i.e. the
system or node has actually asserted a state for it.

Severity: INFO / WARNING / HIGH / CRITICAL.
  WARNING  delayed response (command sent, no confirmation in window), stale
           telemetry from a previously reporting sensor
  HIGH     expected state != observed physical state
  CRITICAL ONLY when the node explicitly flags a hazard in telemetry (the
           sensor itself supports dangerous-condition detection)
"""
from __future__ import annotations

import datetime
import json
import threading
import time

from .. import models
from ..config import settings
from . import audit_service

_stop = threading.Event()
_thread = None


def record_telemetry(db, device: models.Device, *, node_id=None, observed_on=None, power_watts=None,
                     current_amps=None, temperature_c=None, hazard=False, source="REAL", now=None):
    if source not in ("REAL", "SIMULATED"):
        raise ValueError("source must be REAL or SIMULATED")
    row = models.DeviceTelemetry(
        device_id=device.device_id, zone_id=device.zone_id, node_id=node_id, observed_on=observed_on,
        power_watts=power_watts, current_amps=current_amps, temperature_c=temperature_c, hazard=bool(hazard),
        source=source, recorded_at=now or datetime.datetime.utcnow())
    db.add(row)
    db.commit()
    evaluate_device(db, device, now=now)
    return row


def _latest(db, device_id):
    return (db.query(models.DeviceTelemetry).filter(models.DeviceTelemetry.device_id == device_id)
            .order_by(models.DeviceTelemetry.recorded_at.desc(), models.DeviceTelemetry.telemetry_id.desc()).first())


def _observed_on(t: models.DeviceTelemetry, device: models.Device):
    if t.observed_on is not None:
        return t.observed_on
    if t.power_watts is None:
        return None
    floor = max(settings.DEVICE_OFF_POWER_THRESHOLD_WATTS,
                (device.rated_power or 0) * settings.DEVICE_ON_MIN_FRACTION_OF_RATED)
    return t.power_watts >= floor


def findings(db, device: models.Device, now=None) -> list[dict]:
    now = now or datetime.datetime.utcnow()
    out = []
    t = _latest(db, device.device_id)
    if t is None:
        return out  # unmonitored: no sensor has ever reported
    age = (now - t.recorded_at).total_seconds()
    base_ev = {"telemetry_id": t.telemetry_id, "telemetry_at": t.recorded_at.isoformat() + "Z",
               "source": t.source, "node_id": t.node_id}
    if t.hazard:
        out.append(dict(kind="HAZARD", severity="CRITICAL", expected="no hazard", observed="hazard flagged by sensor",
                        reason="Sensor node reported a dangerous condition", source=t.source, evidence=base_ev))
    expects = device.last_command_status is not None
    if age > settings.DEVICE_TELEMETRY_STALE_AFTER_SECONDS:
        out.append(dict(kind="TELEMETRY_STALE", severity="WARNING", expected="periodic telemetry",
                        observed=f"last reading {int(age)}s ago",
                        reason="Device sensor stopped reporting; physical state cannot be verified",
                        source=t.source, evidence=base_ev))
        return out
    if not expects:
        return out
    if (device.last_command_status in ("COMMAND_SENT", "COMMAND_ACKNOWLEDGED") and device.last_command_at
            and (now - device.last_command_at).total_seconds() > settings.DEVICE_COMMAND_RESPONSE_SECONDS
            and t.recorded_at < device.last_command_at):
        out.append(dict(kind="NO_RESPONSE", severity="WARNING",
                        expected="ON" if device.status else "OFF", observed="no newer telemetry since command",
                        reason="Device has not responded within the expected time", source=t.source,
                        evidence={**base_ev, "last_command_at": device.last_command_at.isoformat() + "Z"}))
        return out
    obs = _observed_on(t, device)
    if obs is not None and obs != bool(device.status):
        out.append(dict(kind="STATE_MISMATCH", severity="HIGH", expected="ON" if device.status else "OFF",
                        observed="ON" if obs else "OFF",
                        reason=f"Expected {'ON' if device.status else 'OFF'} but sensor observes {'ON' if obs else 'OFF'}",
                        source=t.source, evidence={**base_ev, "power_watts": t.power_watts,
                                                   "current_amps": t.current_amps, "observed_on": t.observed_on}))
    return out


def evaluate_device(db, device: models.Device, now=None) -> list[models.DeviceFaultAlert]:
    """Opens one alert per (device, kind) while a condition holds; auto-resolves
    (history kept) when the sensor later shows it cleared."""
    now = now or datetime.datetime.utcnow()
    found = {f["kind"]: f for f in findings(db, device, now)}
    open_rows = (db.query(models.DeviceFaultAlert)
                 .filter(models.DeviceFaultAlert.device_id == device.device_id,
                         models.DeviceFaultAlert.status != "RESOLVED").all())
    existing = {r.kind: r for r in open_rows}
    created = []
    for kind, f in found.items():
        if kind in existing:
            continue
        row = models.DeviceFaultAlert(
            device_id=device.device_id, zone_id=device.zone_id, kind=kind, severity=f["severity"],
            expected_value=f["expected"], observed_value=f["observed"], reason=f["reason"],
            source=f["source"], evidence=json.dumps(f["evidence"], default=str), detected_at=now)
        db.add(row)
        created.append(row)
    for kind, row in existing.items():
        if kind not in found:
            row.status = "RESOLVED"
            row.resolved_at = now
            row.resolution_note = "Condition cleared - verified by later sensor telemetry"
    db.commit()
    return created


def sweep_once(db) -> int:
    n = 0
    for d in db.query(models.Device).all():
        n += len(evaluate_device(db, d))
    return n


def maintenance_recommendation(db, device: models.Device, now=None) -> dict | None:
    """Rule-based signal, NOT machine learning: >= N faults inside the window
    AND the latest telemetry is itself abnormal/stale."""
    now = now or datetime.datetime.utcnow()
    since = now - datetime.timedelta(days=settings.MAINTENANCE_WINDOW_DAYS)
    n = (db.query(models.DeviceFaultAlert)
         .filter(models.DeviceFaultAlert.device_id == device.device_id,
                 models.DeviceFaultAlert.detected_at >= since,
                 models.DeviceFaultAlert.kind != "TELEMETRY_STALE").count())
    if n < settings.MAINTENANCE_FAULT_THRESHOLD:
        return None
    current = [f["kind"] for f in findings(db, device, now)]
    if not current:
        return None
    return {"device_id": device.device_id, "device": device.name, "zone_id": device.zone_id,
            "recommendation": "MAINTENANCE_RECOMMENDED", "fault_count": n,
            "window_days": settings.MAINTENANCE_WINDOW_DAYS, "current_abnormal": current,
            "basis": f">= {settings.MAINTENANCE_FAULT_THRESHOLD} faults in {settings.MAINTENANCE_WINDOW_DAYS} days "
                     "and telemetry currently abnormal. Rule-based recommendation, not a prediction model."}


def _loop():
    from ..database import SessionLocal
    while not _stop.wait(30):
        db = SessionLocal()
        try:
            sweep_once(db)
        except Exception:
            pass
        finally:
            db.close()


def start():
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="device-monitor")
    _thread.start()


def stop():
    _stop.set()
