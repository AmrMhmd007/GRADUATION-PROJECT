"""
Concrete hardware-abstraction implementations.

Two families exist today:

1. Legacy bridge (DoorAcController, DoorLightController, PlugController) —
   thin wrappers around this project's original, already-working control
   path: services/mqtt_service.py's publish_ac()/publish_light()/
   publish_plug(), and the Door.ac_on/light_on/Plug.on fields they update.
   Nothing about that path changes; these classes just give it the shape
   the decision engine now expects (RelayController/PowerMeter), so the
   engine stops needing to know Door and Plug exist at all.

2. Generic bridge (GenericDeviceController, GenericOccupancySensor) — for a
   freestanding Device/Sensor with no legacy door/plug behind it. A command
   goes out over the new university/.../device/{id}/command MQTT topic
   (services/mqtt_service.py) for whatever real node is meant to be
   listening, and — since no real node exists yet for any deployment of
   this project — is also applied directly to the Device row so the
   software stack stays internally consistent with zero physical hardware
   attached. Once a real node acknowledges commands over
   .../device/{id}/state instead, that state topic becomes the sole writer
   and this direct-write fallback simply stops firing (the state topic
   handler already overwrites the same field).

get_relay_controller() is the single factory the decision engine calls —
callers never need to know which of the two families they got.
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..services import mqtt_service
from .interfaces import (
    COMMAND_FAILED, COMMAND_SENT, HVACController, LightingController, OccupancySensor, PowerMeter,
    SmartPlugController,
)

MAINS_VOLTAGE = 230  # matches energy_service.py / automation_engine.py's own assumption


# ---------------------------------------------------------------------------
# Legacy bridge — Door (AC / light) and Plug
# ---------------------------------------------------------------------------
class DoorAcController(HVACController, PowerMeter):
    def __init__(self, db: Session, door: models.Door):
        self.db = db
        self.door = door

    def turn_on(self) -> str:
        sent = mqtt_service.publish_ac(self.door.code, "on")
        self.door.ac_on = True
        return COMMAND_SENT if sent else COMMAND_FAILED

    def turn_off(self) -> str:
        sent = mqtt_service.publish_ac(self.door.code, "off")
        self.door.ac_on = False
        self.door.ac_current_amps = None
        return COMMAND_SENT if sent else COMMAND_FAILED

    def is_on(self) -> Optional[bool]:
        return bool(self.door.ac_on)

    def read_power_watts(self) -> Optional[float]:
        return round(self.door.ac_current_amps * MAINS_VOLTAGE, 1) if self.door.ac_current_amps is not None else None

    def read_current_amps(self) -> Optional[float]:
        return self.door.ac_current_amps


class DoorLightController(LightingController):
    def __init__(self, db: Session, door: models.Door):
        self.db = db
        self.door = door

    def turn_on(self) -> str:
        sent = mqtt_service.publish_light(self.door.code, "on")
        self.door.light_on = True
        return COMMAND_SENT if sent else COMMAND_FAILED

    def turn_off(self) -> str:
        sent = mqtt_service.publish_light(self.door.code, "off")
        self.door.light_on = False
        return COMMAND_SENT if sent else COMMAND_FAILED

    def is_on(self) -> Optional[bool]:
        return bool(self.door.light_on)


class PlugController(SmartPlugController, PowerMeter):
    def __init__(self, db: Session, plug: models.Plug):
        self.db = db
        self.plug = plug

    def turn_on(self) -> str:
        sent = mqtt_service.publish_plug(self.plug.door.code, self.plug.plug_id, "on")
        self.plug.on = True
        return COMMAND_SENT if sent else COMMAND_FAILED

    def turn_off(self) -> str:
        sent = mqtt_service.publish_plug(self.plug.door.code, self.plug.plug_id, "off")
        self.plug.on = False
        self.plug.current_amps = None
        return COMMAND_SENT if sent else COMMAND_FAILED

    def is_on(self) -> Optional[bool]:
        return bool(self.plug.on)

    def read_power_watts(self) -> Optional[float]:
        return round(self.plug.current_amps * MAINS_VOLTAGE, 1) if self.plug.current_amps is not None else None

    def read_current_amps(self) -> Optional[float]:
        return self.plug.current_amps


# ---------------------------------------------------------------------------
# Generic bridge — freestanding Device / Sensor rows
# ---------------------------------------------------------------------------
class GenericDeviceController(SmartPlugController, PowerMeter):
    """Covers any Device with no door_ref_id/plug_ref_id — e.g. LAB_EQUIPMENT,
    SERVER, NETWORK_EQUIPMENT. Publishes to the Phase 2 MQTT device-command
    topic (university/.../zone/{id}/device/{id}/command) for whichever real
    node ends up listening, and — since no real node exists yet for any
    deployment of this project — also mirrors the change directly onto the
    Device row so the software stack stays internally consistent with zero
    physical hardware attached. Once a real node starts publishing its own
    .../device/{id}/state instead, that topic's handler
    (mqtt_service._handle_v2_device_state) becomes the sole writer of these
    same fields and this mirror simply stops being the source of truth."""

    def __init__(self, db: Session, device: models.Device):
        self.db = db
        self.device = device

    def turn_on(self) -> str:
        sent = mqtt_service.publish_device_command(
            self.device.zone.building_id, self.device.zone_id, self.device.device_id, "on"
        )
        self.device.status = True
        return COMMAND_SENT if sent else COMMAND_FAILED

    def turn_off(self) -> str:
        sent = mqtt_service.publish_device_command(
            self.device.zone.building_id, self.device.zone_id, self.device.device_id, "off"
        )
        self.device.status = False
        self.device.current_power = None
        return COMMAND_SENT if sent else COMMAND_FAILED

    def is_on(self) -> Optional[bool]:
        return bool(self.device.status)

    def read_power_watts(self) -> Optional[float]:
        return self.device.current_power


class GenericOccupancySensor(OccupancySensor):
    """Wraps a Sensor row — real hardware writes into that row over the new
    telemetry MQTT topic (or, today, a human writes into it via the manual
    /api/sensors/{id}/reading testing endpoint). Either way this class is
    just a typed read view over what's already stored."""

    def __init__(self, sensor: models.Sensor, stale_after_seconds: int):
        self.sensor = sensor
        self.stale_after_seconds = stale_after_seconds

    def read_occupancy(self) -> Optional[bool]:
        if not self.is_healthy():
            return None
        return self.sensor.occupancy_state

    def last_seen(self) -> Optional[datetime.datetime]:
        return self.sensor.last_seen

    def is_healthy(self) -> bool:
        if self.sensor.occupancy_state is None or self.sensor.last_seen is None:
            return False
        age = (datetime.datetime.utcnow() - self.sensor.last_seen).total_seconds()
        return age <= self.stale_after_seconds


# ---------------------------------------------------------------------------
# Factories — the only thing the decision engine actually calls
# ---------------------------------------------------------------------------
def get_relay_controller(db: Session, device: models.Device):
    """Resolves a Device row to whichever concrete controller actually
    knows how to command it. `Device.controllable` is deliberately NOT
    checked here — it never gated the automation engine before this
    abstraction existed (only the manual /api/devices/{id}/status endpoint
    enforces it, see routers/zones.py) and this refactor changes no
    behavior. Returns None only when the door/plug this device is
    supposed to be backed by can't actually be found."""
    if device.door_ref_id and device.type == "AC":
        door = db.query(models.Door).filter(models.Door.door_id == device.door_ref_id).first()
        return DoorAcController(db, door) if door else None
    if device.door_ref_id and device.type == "LIGHT":
        door = db.query(models.Door).filter(models.Door.door_id == device.door_ref_id).first()
        return DoorLightController(db, door) if door else None
    if device.plug_ref_id:
        plug = db.query(models.Plug).filter(models.Plug.plug_id == device.plug_ref_id).first()
        return PlugController(db, plug) if plug else None
    return GenericDeviceController(db, device)


def get_occupancy_sensor(sensor: models.Sensor, stale_after_seconds: int) -> GenericOccupancySensor:
    return GenericOccupancySensor(sensor, stale_after_seconds)
