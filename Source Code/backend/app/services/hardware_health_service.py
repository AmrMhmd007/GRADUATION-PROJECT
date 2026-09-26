"""
Phase 5: hardware node health/heartbeat tracking (HardwareHealth model, see
models.py for the full field-by-field rationale).

Two halves, mirroring staleness_watchdog.py's own shape:

1. record_heartbeat() — called from mqtt_service._handle_v2_health whenever
   a real heartbeat message arrives on university/.../zone/{id}/health.
   Find-or-creates the node's HardwareHealth row and marks it ONLINE (or
   DEGRADED, if the node itself reported a problem).

2. sweep_once() / the background loop — periodically marks any node OFFLINE
   whose last heartbeat is older than HARDWARE_HEALTH_STALE_AFTER_SECONDS.
   A node that simply stops sending anything (crashed, lost power, fell off
   WiFi) never gets to say "offline" about itself — this sweep is what
   actually catches that, exactly like staleness_watchdog.py does for doors.

Hard rule (see HardwareHealth's own docstring): nothing here ever feeds an
occupancy verdict. A node going OFFLINE/DEGRADED only means "don't trust
this node's own reporting right now" — sense_zone_occupancy already
achieves that independently via Sensor.last_seen staleness. This module is
a separate, purely informational signal for admins.
"""
from __future__ import annotations

import datetime
import logging
import threading

from ..config import settings
from ..database import SessionLocal
from .. import models

logger = logging.getLogger("hardware_health_service")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def record_heartbeat(db, node_id: str, payload: dict, zone_id: int | None = None) -> models.HardwareHealth:
    """Find-or-creates the HardwareHealth row for `node_id` and applies one
    heartbeat's worth of fields. Only ever called from a real received MQTT
    message (mqtt_service._handle_v2_health) — this function has no way to
    tell real from simulated itself, so it trusts its caller, same as every
    other MQTT ingestion handler in this codebase."""
    node = db.query(models.HardwareHealth).filter(models.HardwareHealth.node_id == node_id).first()
    if node is None:
        node = models.HardwareHealth(node_id=node_id, zone_id=zone_id, status="UNKNOWN")
        db.add(node)

    now = datetime.datetime.utcnow()
    node.last_seen = now
    if zone_id is not None:
        node.zone_id = zone_id
    if "firmware_version" in payload:
        node.firmware_version = payload["firmware_version"]
    if "uptime_seconds" in payload:
        node.uptime_seconds = payload["uptime_seconds"]
    if "rssi" in payload:
        node.rssi = payload["rssi"]
    if "mqtt_connected" in payload:
        node.mqtt_connected = bool(payload["mqtt_connected"])
    if "sensor_healthy" in payload:
        node.sensor_healthy = bool(payload["sensor_healthy"])
    node.error_state = payload.get("error_state")  # explicitly overwrite — an absent field means "cleared"

    # A message just arrived, so this node is alive right now, full stop.
    # DEGRADED is for "alive but reporting a problem," never "might be dead."
    previous_status = node.status
    if node.error_state or node.sensor_healthy is False:
        node.status = "DEGRADED"
    else:
        node.status = "ONLINE"

    # Real, persisted alert (final hardening pass, Phase 7) on the
    # transition INTO degraded — not on every heartbeat that repeats it, so
    # a node stuck degraded doesn't spam one alert per message.
    if node.status == "DEGRADED" and previous_status != "DEGRADED" and node.zone_id is not None:
        already = (
            db.query(models.Alert)
            .filter(models.Alert.zone_id == node.zone_id, models.Alert.type == "device_failed",
                    models.Alert.resolved.is_(False))
            .first()
        )
        if not already:
            db.add(models.Alert(zone_id=node.zone_id, type="device_failed", severity="WARNING"))

    db.commit()
    db.refresh(node)
    return node


def sweep_once(db) -> list[str]:
    """Marks any node whose last_seen has gone stale as OFFLINE. Returns the
    node_ids just marked (empty if none were stale) — factored out for unit
    testing, same pattern as staleness_watchdog.sweep_once."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=settings.HARDWARE_HEALTH_STALE_AFTER_SECONDS)
    stale = (
        db.query(models.HardwareHealth)
        .filter(models.HardwareHealth.status.in_(["ONLINE", "DEGRADED"]))
        .filter(models.HardwareHealth.last_seen.isnot(None))
        .filter(models.HardwareHealth.last_seen < cutoff)
        .all()
    )
    node_ids = []
    alerted_zone_ids = set()  # avoid a same-sweep duplicate when >1 node in one zone goes offline together
    for node in stale:
        node.status = "OFFLINE"
        node_ids.append(node.node_id)
        if node.zone_id is not None and node.zone_id not in alerted_zone_ids:
            already = (
                db.query(models.Alert)
                .filter(models.Alert.zone_id == node.zone_id, models.Alert.type == "device_failed",
                        models.Alert.resolved.is_(False))
                .first()
            )
            if not already:
                db.add(models.Alert(zone_id=node.zone_id, type="device_failed", severity="CRITICAL"))
                alerted_zone_ids.add(node.zone_id)
    if stale:
        db.commit()
        logger.warning("Marked %d hardware node(s) OFFLINE (stale heartbeat): %s", len(stale), node_ids)
    return node_ids


def _loop():
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            sweep_once(db)
        except Exception:
            logger.exception("Hardware health sweep failed")
        finally:
            db.close()
        _stop_event.wait(settings.HARDWARE_HEALTH_CHECK_INTERVAL_SECONDS)


def start():
    global _thread
    if settings.DISABLE_MQTT:
        logger.info("DISABLE_MQTT set — hardware health sweep not started")
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    logger.info("Hardware health sweep started (stale after %ss, checked every %ss)",
                settings.HARDWARE_HEALTH_STALE_AFTER_SECONDS, settings.HARDWARE_HEALTH_CHECK_INTERVAL_SECONDS)


def stop():
    _stop_event.set()
