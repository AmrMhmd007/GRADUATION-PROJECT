"""
The one telemetry shape every hardware source — real or simulated — is
expected to produce, whether it arrives over the new MQTT telemetry topic
(services/mqtt_service.py), gets written by the simulation loop
(services/energy_service.py, services/automation_engine.py), or gets posted
through a manual/testing HTTP endpoint.

`source` is not decorative: `real` must only ever be set by code paths that
received an actual message from actual hardware (the MQTT telemetry
handler). Every simulated/manual code path in this codebase sets
`simulated`. Nothing here is allowed to claim `real` for data this project
generated itself — see the Step-18/audit rule this was built to satisfy.
"""
from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Telemetry(BaseModel):
    device_id: Optional[int] = None   # a Device.device_id, when this reading is about a controllable device
    sensor_id: Optional[int] = None   # a Sensor.sensor_id, when this reading is about a sensor
    zone_id: int
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    sensor_type: str                  # PIR | MMWAVE | ESP32 | DOOR_EVENT | RFID_EVENT | POWER_METER | OTHER
    metric: str                       # "occupancy" | "power" | "voltage" | "current" | "energy" | "power_factor" | ...
    value: float | bool | str
    unit: Optional[str] = None        # "W", "V", "A", "kWh", None for a boolean/occupancy metric
    quality: str = "unknown"          # "good" | "degraded" | "unknown" — mirrors HardwareHealth's own vocabulary
    source: str = "simulated"         # "real" | "simulated" — see module docstring; never fabricate "real"
    sequence_number: Optional[int] = None  # a node-local monotonic counter, for detecting drops/duplicates/reordering

    def is_real(self) -> bool:
        return self.source == "real"
