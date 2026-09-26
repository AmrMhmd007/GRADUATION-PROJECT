"""
Energy & occupancy background service.

Two independent jobs, each mirroring staleness_watchdog.py's shape — the
real work factored into a plain function that takes a db session, so it can
be unit-tested directly without waiting on a real timer, with a thin
daemon-thread loop wrapped around it:

1. simulate_power_and_check_alerts_once() — every
   settings.ENERGY_SIM_INTERVAL_SECONDS, for every Room (an access_service
   Door) with its AC on or any plug on: generates a plausible current_amps
   reading (no current-sensor hardware exists yet — see Door.ac_current_amps
   and Plug.current_amps's own docstrings — so this is simulated, the same
   "real hardware would just write into this same field" pattern used
   throughout this codebase), logs it to PowerReading, and — only once that
   room's real occupancy sensor has explicitly reported it empty
   (Door.occupied is False, not merely unknown/None) while something at or
   above HIGH_POWER_WATTS_THRESHOLD keeps running — raises an
   Alert(type="high_power_empty_room") through the existing alerts feed
   (already polled and rendered by AlertBanner), unless one is already open
   for that door.

2. run_checkout_sweep() — the "end of day" scan the user asked for: when
   employees/doctors check out, walk every room/corridor/section/lab (every
   access_service Door), log one final PowerReading for anything still
   drawing power, then switch its AC/light/every plug off — through the same
   mqtt_service.publish_*() calls the manual toggle endpoints already use —
   and record one AccessEvent(method="auto_shutdown") per room so the sweep
   shows up in that room's History table exactly like a manual override
   would. Callable directly (POST /api/system/run-checkout-sweep, for a demo
   or a "do it now" admin action) or from the daily-clock loop below, which
   fires once when the local wall-clock time matches the admin-configured
   checkout_time (see SystemSetting).
"""
from __future__ import annotations

import datetime
import logging
import random
import threading

from ..config import settings
from ..database import SessionLocal
from .. import models
from . import mqtt_service
from . import energy_timeseries_service

logger = logging.getLogger("energy_service")

_stop_event = threading.Event()
_sim_thread: threading.Thread | None = None
_checkout_thread: threading.Thread | None = None
_last_sweep_date: datetime.date | None = None

MAINS_VOLTAGE = 230  # matches schemas.py's watts computation


def _simulate_amps_for_plug() -> float:
    # Mostly an everyday load (laptop charger, monitor, lamp: ~5-60W),
    # occasionally something power-hungry left running (a kettle, heater,
    # microwave: ~800-1800W) — that occasional spike is what the
    # high-power-empty-room alert exists to catch. Hardware doesn't exist
    # yet; a real current sensor would replace this function outright.
    if random.random() < 0.15:
        watts = random.uniform(800, 1800)
    else:
        watts = random.uniform(5, 60)
    return round(watts / MAINS_VOLTAGE, 3)


def _simulate_amps_for_ac() -> float:
    # A typical split-unit AC draws roughly 700-1100W while running.
    watts = random.uniform(700, 1100)
    return round(watts / MAINS_VOLTAGE, 3)


def get_checkout_time(db) -> str:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == "checkout_time").first()
    return row.value if row else settings.DEFAULT_CHECKOUT_TIME


def set_checkout_time(db, value: str) -> None:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == "checkout_time").first()
    if row:
        row.value = value
    else:
        db.add(models.SystemSetting(key="checkout_time", value=value))
    db.commit()


def _find_device(db, *, door_id: int | None = None, plug_id: int | None = None) -> models.Device | None:
    query = db.query(models.Device)
    if plug_id is not None:
        return query.filter(models.Device.plug_ref_id == plug_id).first()
    if door_id is not None:
        return query.filter(models.Device.door_ref_id == door_id, models.Device.type == "AC").first()
    return None


def _stamp_simulated(db, *, door_id: int | None = None, plug_id: int | None = None,
                      amps: float | None = None, watts: float | None = None) -> None:
    """Hardening constraint #2: every reading this simulation loop invents
    must be marked SIMULATED on the Device row that mirrors it, so nothing
    downstream (API, dashboard, energy reports) can mistake it for a real
    hardware measurement. Real hardware doesn't exist for AC/plug current
    sensing yet — see this module's own docstring — so this is currently
    the *only* writer of power_source for these devices; the day a real
    sensor reports over MQTT, that handler stamps 'REAL' instead.

    Also logs one Phase 6 EnergyReading row for this same sample, so the
    Zone/Device time series (services/energy_timeseries_service.py) has
    something to aggregate without a second, separate polling loop."""
    device = _find_device(db, door_id=door_id, plug_id=plug_id)
    if device is None:
        return
    device.power_source = "SIMULATED"
    energy_kwh = None
    if watts is not None:
        # This sample represents ENERGY_SIM_INTERVAL_SECONDS of running at
        # `watts` — an honest interval-energy estimate given the fixed
        # sampling cadence, not a fabricated historical figure.
        energy_kwh = round(watts * settings.ENERGY_SIM_INTERVAL_SECONDS / 3600.0 / 1000.0, 6)
    energy_timeseries_service.record_reading(
        db, zone_id=device.zone_id, device_id=device.device_id, power=watts,
        voltage=MAINS_VOLTAGE if amps is not None else None, current=amps,
        energy_kwh=energy_kwh, source="SIMULATED",
    )


def _rooms(db):
    """Every Room (access_service Door) — Main Doors (category == 'critical':
    the main entrance, server room) are intentionally left out of both the
    power simulation and the checkout sweep, same as they're left out of
    AC/light/plug control entirely."""
    return db.query(models.Door).filter(models.Door.category == "access_service").all()


def simulate_power_and_check_alerts_once(db) -> int:
    """Runs one simulation + alert-check pass. Returns how many new alerts
    were raised."""
    new_alerts = 0
    now = datetime.datetime.utcnow()

    for door in _rooms(db):
        high_power_active = False

        if door.ac_enabled and door.ac_on:
            amps = _simulate_amps_for_ac()
            door.ac_current_amps = amps
            _stamp_simulated(db, door_id=door.door_id, amps=amps, watts=round(amps * MAINS_VOLTAGE, 1))
            db.add(models.PowerReading(
                door_id=door.door_id, device="ac", current_amps=amps,
                watts=round(amps * MAINS_VOLTAGE, 1), recorded_at=now,
            ))
            if amps * MAINS_VOLTAGE >= settings.HIGH_POWER_WATTS_THRESHOLD:
                high_power_active = True

        for plug in door.plugs:
            if not plug.on:
                continue
            amps = _simulate_amps_for_plug()
            plug.current_amps = amps
            plug.last_seen = now
            _stamp_simulated(db, plug_id=plug.plug_id, amps=amps, watts=round(amps * MAINS_VOLTAGE, 1))
            db.add(models.PowerReading(
                door_id=door.door_id, device="plug", plug_id=plug.plug_id,
                current_amps=amps, watts=round(amps * MAINS_VOLTAGE, 1), recorded_at=now,
            ))
            if amps * MAINS_VOLTAGE >= settings.HIGH_POWER_WATTS_THRESHOLD:
                high_power_active = True

        if high_power_active and door.occupied is False:
            already_open = (
                db.query(models.Alert)
                .filter(
                    models.Alert.door_id == door.door_id,
                    models.Alert.type == "high_power_empty_room",
                    models.Alert.resolved.is_(False),
                )
                .first()
            )
            if not already_open:
                db.add(models.Alert(door_id=door.door_id, type="high_power_empty_room"))
                new_alerts += 1

    db.commit()
    return new_alerts


def run_checkout_sweep(db) -> list[str]:
    """Scans every room, logs a final reading for anything still running,
    switches AC/light/every plug off, and logs one audit-trail AccessEvent
    per room actually touched. Returns the door codes that were swept."""
    now = datetime.datetime.utcnow()
    swept = []

    for door in _rooms(db):
        touched = False

        if door.ac_enabled and door.ac_on:
            amps = door.ac_current_amps or _simulate_amps_for_ac()
            db.add(models.PowerReading(
                door_id=door.door_id, device="ac", current_amps=amps,
                watts=round(amps * MAINS_VOLTAGE, 1), recorded_at=now,
            ))
            mqtt_service.publish_ac(door.code, "off")
            door.ac_on = False
            door.ac_current_amps = None
            touched = True

        if door.light_enabled and door.light_on:
            mqtt_service.publish_light(door.code, "off")
            door.light_on = False
            touched = True

        for plug in door.plugs:
            if plug.on:
                amps = plug.current_amps or _simulate_amps_for_plug()
                db.add(models.PowerReading(
                    door_id=door.door_id, device="plug", plug_id=plug.plug_id,
                    current_amps=amps, watts=round(amps * MAINS_VOLTAGE, 1), recorded_at=now,
                ))
                mqtt_service.publish_plug(door.code, plug.plug_id, "off")
                plug.on = False
                plug.current_amps = None
                touched = True

        if touched:
            db.add(models.AccessEvent(
                door_id=door.door_id, credential_id=None, method="auto_shutdown", result="sent",
            ))
            swept.append(door.code)

    db.commit()
    return swept


def _sim_loop():
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            simulate_power_and_check_alerts_once(db)
        except Exception:
            logger.exception("Energy simulation pass failed")
        finally:
            db.close()
        _stop_event.wait(settings.ENERGY_SIM_INTERVAL_SECONDS)


def _checkout_loop():
    # Deliberately compares against local wall-clock time, not UTC — a
    # checkout time like "18:00" is meaningful to the admin who set it as
    # "6pm here," not as a UTC instant. Every other timestamp in this
    # codebase stays UTC; this is the one place local time is the right
    # comparison, since that's the axis the admin actually configured it on.
    global _last_sweep_date
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            checkout_time = get_checkout_time(db)
            now = datetime.datetime.now()
            if now.strftime("%H:%M") == checkout_time and _last_sweep_date != now.date():
                codes = run_checkout_sweep(db)
                _last_sweep_date = now.date()
                logger.info("Scheduled checkout sweep at %s: %d room(s) — %s",
                            checkout_time, len(codes), codes)
        except Exception:
            logger.exception("Checkout sweep check failed")
        finally:
            db.close()
        _stop_event.wait(settings.CHECKOUT_CHECK_INTERVAL_SECONDS)


def start():
    global _sim_thread, _checkout_thread
    if settings.DISABLE_MQTT:
        # No live device data is flowing in this mode (tests, or MQTT
        # deliberately disabled) — matches staleness_watchdog's own guard.
        logger.info("DISABLE_MQTT set — energy service not started")
        return
    _stop_event.clear()
    _sim_thread = threading.Thread(target=_sim_loop, daemon=True)
    _sim_thread.start()
    _checkout_thread = threading.Thread(target=_checkout_loop, daemon=True)
    _checkout_thread.start()
    logger.info("Energy service started (simulate every %ss, checkout checked every %ss)",
                settings.ENERGY_SIM_INTERVAL_SECONDS, settings.CHECKOUT_CHECK_INTERVAL_SECONDS)


def stop():
    _stop_event.set()
