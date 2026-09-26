"""
Abstract hardware interfaces the decision engine programs against.

None of these are implemented by real hardware yet (see this package's
__init__.py). Each one exists so that a specific future physical capability
has exactly one place to plug into this codebase, rather than the engine
growing a new if/elif branch per sensor brand the way the original
Door.ac_on/light_on bridge did. Every method is deliberately small and
read/command-oriented — no interface here assumes a specific transport
(MQTT, RS-485, a REST callback); that choice belongs to whatever concrete
class implements the interface (see bridge.py for the two that exist today).
"""
from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import Optional


class OccupancySensor(ABC):
    """A PIR, mmWave, ESP32-fused, or any future presence-detection source
    for one zone. Deliberately returns Optional[bool]: None means "no
    reading available", which the fusion logic (Phase 3) must never treat
    the same as a confirmed False."""

    @abstractmethod
    def read_occupancy(self) -> Optional[bool]:
        ...

    @abstractmethod
    def last_seen(self) -> Optional[datetime.datetime]:
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        ...


class DoorSensor(ABC):
    """A door position sensor (reed switch, etc.) — distinct from RFID:
    this reports open/closed, not who (if anyone) went through."""

    @abstractmethod
    def is_open(self) -> Optional[bool]:
        ...

    @abstractmethod
    def last_event_at(self) -> Optional[datetime.datetime]:
        ...


class RFIDReader(ABC):
    """A card/credential reader. The decision engine only ever cares about
    "was there a recent granted access here" (a positive occupancy signal),
    not the raw card-read protocol — that's already handled by the existing
    door-node firmware and services/mqtt_service.py's /event topic."""

    @abstractmethod
    def last_grant_at(self) -> Optional[datetime.datetime]:
        ...


class PowerMeter(ABC):
    """Any device capable of reporting electrical measurements for a zone or
    a single device — a CT clamp, a smart meter, a Modbus meter, or a
    plug/AC's own built-in sensing. A concrete meter is free to only
    implement the metrics it actually has (return None for the rest)."""

    @abstractmethod
    def read_power_watts(self) -> Optional[float]:
        ...

    def read_voltage(self) -> Optional[float]:
        return None

    def read_current_amps(self) -> Optional[float]:
        return None

    def read_energy_kwh(self) -> Optional[float]:
        return None

    def read_power_factor(self) -> Optional[float]:
        return None


# Command lifecycle (mandatory hardening constraint #6): "the MQTT publish
# call returned" is NOT the same fact as "the physical device changed
# state," and this codebase must never conflate the two. Only the first two
# values below can ever be produced *synchronously*, by turn_on()/turn_off()
# themselves — command acknowledgement and state confirmation are
# inherently asynchronous (they can only ever arrive later, over MQTT, from
# whatever actually did the switching), so no concrete class in bridge.py
# returns them directly. They're set later, out-of-band, on Device (see
# Device.last_command_status) by whatever code path receives that real
# message: mqtt_service._handle_v2_device_state for the new hierarchy, and
# the legacy ac/status, light/status, plug/.../status handlers for the
# Door/Plug bridge. Today NO real hardware sends any of those messages (see
# HARDWARE_INTEGRATION.md), so in practice every command in this project
# currently stops at COMMAND_SENT or COMMAND_FAILED and never reaches
# COMMAND_ACKNOWLEDGED/STATE_CONFIRMED — that gap is exactly what a real
# relay/contactor node closes once it exists, not something to fake here.
COMMAND_SENT = "COMMAND_SENT"           # the outgoing publish call succeeded
COMMAND_FAILED = "COMMAND_FAILED"       # broker unreachable, or nothing to command (missing backing row)
COMMAND_ACKNOWLEDGED = "COMMAND_ACKNOWLEDGED"  # reserved: a node ack'd receipt, before actually switching
STATE_CONFIRMED = "STATE_CONFIRMED"     # a real status message reported the load actually changed
COMMAND_TIMEOUT = "COMMAND_TIMEOUT"     # reserved: no ack/state arrived within an expected window


class RelayController(ABC):
    """The base abstraction every controllable load ultimately reduces to:
    an on/off command sent to *a relay or contactor*, never to mains
    electricity directly from a GPIO pin. See HARDWARE_INTEGRATION.md for
    why that boundary matters and where it physically sits."""

    @abstractmethod
    def turn_on(self) -> str:
        """Returns COMMAND_SENT or COMMAND_FAILED (see the module-level
        constants above) — never a bare bool, and never anything stronger
        than "the command was dispatched." Mirrors this project's existing
        publish_ac()/publish_light()/publish_plug() dispatch convention,
        just spelled out as one of the named command-lifecycle states
        instead of True/False."""

    @abstractmethod
    def turn_off(self) -> str:
        ...

    @abstractmethod
    def is_on(self) -> Optional[bool]:
        ...


class LightingController(RelayController):
    """Room lighting. Dimming/brightness is intentionally not part of this
    interface yet — no lighting hardware in this project supports anything
    beyond on/off today, and adding it speculatively would be exactly the
    kind of "feature to make the project look bigger" the brief warns
    against."""


class HVACController(RelayController):
    """A room's AC/HVAC unit. `target_temperature` is accepted as an
    optional no-op today (returns False) precisely so a future thermostat-
    capable unit can implement it without changing this interface or any
    code that calls it."""

    def set_target_temperature(self, celsius: float) -> bool:
        return False


class SmartPlugController(RelayController):
    """A single switched outlet — usually also a PowerMeter (a plug that can
    both switch and report its own load), but the two capabilities are kept
    as separate interfaces so a plug without metering still fully qualifies
    as a SmartPlugController."""


class HardwareNode(ABC):
    """The backend-side handle for one physical node (an ESP32, a gateway,
    a standalone meter) — not something the backend calls out to, since a
    node initiates its own heartbeat/telemetry over MQTT, but the receiving
    side of that relationship: how the backend records what a node last
    told it and decides whether the node counts as healthy right now. See
    services/hardware_health_service.py for the concrete implementation
    (Phase 5) backed by the HardwareHealth model."""

    @abstractmethod
    def record_heartbeat(self, payload: dict) -> None:
        ...

    @abstractmethod
    def current_status(self) -> str:
        """One of 'ONLINE' | 'OFFLINE' | 'DEGRADED' | 'UNKNOWN'."""
