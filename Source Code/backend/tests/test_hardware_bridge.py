"""
Tests for the hardware abstraction layer (app/hardware/). These exist to
prove one thing above all: refactoring automation_engine.py to go through
get_relay_controller() instead of its own door_ref_id/plug_ref_id if/elif
chain changed NOTHING about observable behavior — same MQTT calls, same
fields flipped, same None-means-"no data" semantics.
"""
import datetime

from app import models
from app.hardware.bridge import (
    DoorAcController,
    DoorLightController,
    GenericDeviceController,
    PlugController,
    get_relay_controller,
)
from app.hardware.telemetry import Telemetry


def _zone(db, name="HW Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _door(db, code="HW-101", ac_on=False, ac_current_amps=None, light_on=False):
    door = models.Door(
        code=code, name="HW Room", building="Main", category="access_service",
        ac_enabled=True, ac_on=ac_on, ac_current_amps=ac_current_amps,
        light_enabled=True, light_on=light_on,
    )
    db.add(door)
    db.commit()
    db.refresh(door)
    return door


def _plug(db, door_id, on=False, current_amps=None):
    plug = models.Plug(door_id=door_id, label="Plug 1", on=on, current_amps=current_amps)
    db.add(plug)
    db.commit()
    db.refresh(plug)
    return plug


def _device(db, zone_id, type_, door_ref_id=None, plug_ref_id=None, status=False):
    device = models.Device(
        zone_id=zone_id, name="HW Device", type=type_, criticality="NON_CRITICAL",
        status=status, door_ref_id=door_ref_id, plug_ref_id=plug_ref_id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


# ---------------------------------------------------------------------------
# Legacy bridge: AC / light (Door-backed)
# ---------------------------------------------------------------------------
def test_ac_device_resolves_to_door_ac_controller(db_session):
    zone = _zone(db_session)
    door = _door(db_session, ac_on=True, ac_current_amps=2.0)
    device = _device(db_session, zone.zone_id, "AC", door_ref_id=door.door_id)

    controller = get_relay_controller(db_session, device)

    assert isinstance(controller, DoorAcController)
    assert controller.is_on() is True
    assert controller.read_power_watts() == 460.0  # 2.0A * 230V


def test_ac_controller_turn_off_flips_door_fields(db_session):
    zone = _zone(db_session)
    door = _door(db_session, ac_on=True, ac_current_amps=3.5)
    device = _device(db_session, zone.zone_id, "AC", door_ref_id=door.door_id, status=True)

    controller = get_relay_controller(db_session, device)
    controller.turn_off()

    assert door.ac_on is False
    assert door.ac_current_amps is None


def test_light_device_resolves_to_door_light_controller(db_session):
    zone = _zone(db_session)
    door = _door(db_session, light_on=True)
    device = _device(db_session, zone.zone_id, "LIGHT", door_ref_id=door.door_id)

    controller = get_relay_controller(db_session, device)

    assert isinstance(controller, DoorLightController)
    assert controller.is_on() is True

    controller.turn_off()
    assert door.light_on is False


# ---------------------------------------------------------------------------
# Legacy bridge: Plug
# ---------------------------------------------------------------------------
def test_plug_device_resolves_to_plug_controller(db_session):
    zone = _zone(db_session)
    door = _door(db_session)
    plug = _plug(db_session, door.door_id, on=True, current_amps=1.0)
    device = _device(db_session, zone.zone_id, "NON_CRITICAL_SOCKET", plug_ref_id=plug.plug_id)

    controller = get_relay_controller(db_session, device)

    assert isinstance(controller, PlugController)
    assert controller.is_on() is True
    assert controller.read_power_watts() == 230.0

    controller.turn_off()
    assert plug.on is False
    assert plug.current_amps is None


# ---------------------------------------------------------------------------
# Generic bridge: freestanding device (no door/plug behind it)
# ---------------------------------------------------------------------------
def test_freestanding_device_resolves_to_generic_controller(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, "SERVER", status=False)

    controller = get_relay_controller(db_session, device)

    assert isinstance(controller, GenericDeviceController)
    assert controller.is_on() is False

    controller.turn_on()
    assert device.status is True

    controller.turn_off()
    assert device.status is False
    assert device.current_power is None


def test_missing_backing_door_returns_none_not_an_error(db_session):
    zone = _zone(db_session)
    # door_ref_id points at nothing that exists — must fail soft, never raise.
    device = _device(db_session, zone.zone_id, "AC", door_ref_id=999999)

    controller = get_relay_controller(db_session, device)

    assert controller is None


# ---------------------------------------------------------------------------
# automation_engine.py actually goes through the abstraction now
# ---------------------------------------------------------------------------
def test_sync_device_power_and_turn_off_go_through_bridge(db_session):
    from app.services import automation_engine

    zone = _zone(db_session)
    door = _door(db_session, ac_on=True, ac_current_amps=1.5)
    device = _device(db_session, zone.zone_id, "AC", door_ref_id=door.door_id)

    automation_engine._sync_device_power(db_session, device)
    assert device.status is True
    assert device.current_power == 345.0

    automation_engine._turn_device_off(db_session, device)
    assert device.status is False
    assert device.current_power is None
    assert door.ac_on is False


# ---------------------------------------------------------------------------
# Telemetry contract
# ---------------------------------------------------------------------------
def test_telemetry_defaults_to_simulated_never_real_by_accident():
    t = Telemetry(zone_id=1, sensor_type="PIR", metric="occupancy", value=True)
    assert t.source == "simulated"
    assert t.is_real() is False


def test_telemetry_is_real_only_when_explicitly_set():
    t = Telemetry(
        zone_id=1, sensor_type="PIR", metric="occupancy", value=True,
        source="real", timestamp=datetime.datetime.utcnow(),
    )
    assert t.is_real() is True
