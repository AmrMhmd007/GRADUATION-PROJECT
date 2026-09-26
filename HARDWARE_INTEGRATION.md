# Hardware Integration Guide

This document describes exactly what the software side of the Smart Building
platform expects from real hardware, and exactly how much of that hardware
exists today. It is written for whoever wires up the first real ESP32 node —
most likely a future version of this same team.

**Status in one sentence: the software foundation is built, tested, and
ready to receive real hardware; no occupancy, power-metering, or generic
relay firmware exists yet, and nothing here should be read as claiming
otherwise.**

What *is* real today, unchanged by any of the work described in this
document: the original door-node firmware (`Source Code/door_node_firmware`)
— RFID/DESFire authentication, lock/unlock relay control, RS-485 primary
link with Wi-Fi fallback, and the `site/{code}/...` MQTT topics it speaks.
That firmware needs zero changes and is not discussed further here except
where it interacts with the new layers.

---

## 1. Architecture overview

```
                          ┌─────────────────────────────┐
                          │        FastAPI backend        │
                          │                                │
Real or       MQTT        │  app/hardware/                │
simulated  ─────────────► │    interfaces.py  (contracts) │
telemetry                 │    bridge.py       (impls)    │
                           │                                │
                           │  app/services/                 │
                           │    automation_engine.py        │
                           │    mqtt_service.py              │
                           │    hardware_health_service.py   │
                           │    energy_timeseries_service.py │
                           └───────────────┬────────────────┘
                                            │ REST
                                            ▼
                                    React dashboard
```

The engine (`automation_engine.py`) never talks to a Door, Plug, or Device
row's fields directly to command hardware — it calls
`hardware/bridge.get_relay_controller(db, device)`, which resolves to one of:

- **Legacy bridge** (`DoorAcController`, `DoorLightController`,
  `PlugController`) — wraps the original, already-working
  `site/{code}/ac|light|plug/...` MQTT topics. This is what every Room
  created before this work, and every Room created through the existing
  "Add Room" flow, is backed by. **Nothing about this path needs to change
  for real hardware** — it already works with the existing door-node
  firmware's AC/light/plug extensions.
- **Generic bridge** (`GenericDeviceController`) — for a freestanding
  `Device` row with no door/plug behind it (e.g. `SERVER`,
  `NETWORK_EQUIPMENT`, a future standalone smart plug). Commands are meant
  to go out over the new `university/.../device/{id}/command` topic; **no
  real node subscribes to that topic today**, so this class currently only
  mirrors the command onto the database row.

Both return a `str` command-lifecycle status (see §5) rather than a bare
`bool` — a real relay node closes the loop on that status asynchronously,
over MQTT, not as a return value of the publish call.

---

## 2. The one hard safety rule

**An ESP32 GPIO pin must never be wired directly to mains voltage.** The
required chain is always:

```
ESP32 GPIO  →  low-voltage control signal  →  relay or contactor module
           →  mains-rated switching contact  →  the actual load (AC unit,
                                                  light circuit, socket)
```

Nothing in this codebase issues anything more specific than an abstract
"turn this load on/off" command (`RelayController.turn_on()/turn_off()` in
`app/hardware/interfaces.py`). Which GPIO drives which relay, what relay
module is used, and how it's rated for the load it switches are entirely a
hardware/wiring decision made when a real node is built — the software
layer is deliberately blind to that detail so it can never assume a wiring
shortcut that skips the relay/contactor stage.

For anything switching a genuinely high-current load (a window AC unit, a
lab bench, a server rack PDU), use a contactor rated for that load, driven
by a relay module, driven by the ESP32 — not a single relay module
undersized for the actual current.

---

## 3. MQTT topic reference

### 3.1 Legacy (`site/{code}/...`) — unchanged, still authoritative for Rooms

| Topic | Direction | Payload | Notes |
|---|---|---|---|
| `site/{code}/status` | node → backend | `"online"` / `"offline"` | |
| `site/{code}/event` | node → backend | JSON access event | |
| `site/{code}/alert` | node → backend | JSON `{"type": ...}` | |
| `site/{code}/cmd` | backend → node | JSON `{"cmd": "lock"/"unlock"}` | |
| `site/{code}/ac/status`, `.../ac/cmd` | both | `"on"`/`"off"` | |
| `site/{code}/light/status`, `.../light/cmd` | both | `"on"`/`"off"` | |
| `site/{code}/plug/{id}/status`, `.../plug/{id}/cmd` | both | JSON `{"on": bool, "current_amps": num}` | current sensing not built yet |
| `site/{code}/occupancy/status` | node → backend | JSON `{"occupied": bool}` | no publish side — backend only listens |

### 3.2 New hierarchy (`university/{university_id}/building/{building_id}/zone/{zone_id}/...`)

`university_id` is a fixed config value (`MQTT_UNIVERSITY_ID`, default
`"aiu"` — this is a single-tenant deployment, not a multi-tenant SaaS, so
it never needs to come from a database row). `building_id` is carried for
firmware bookkeeping only; the backend always resolves by `zone_id`
(globally unique) so a zone's building reassignment in the dashboard never
orphans an already-flashed node.

| Topic | Direction | Payload | Handler |
|---|---|---|---|
| `.../zone/{zid}/sensor/{sensor_id}/telemetry` | node → backend | `Telemetry` JSON (§4) | `mqtt_service._handle_v2_telemetry` |
| `.../zone/{zid}/device/{device_id}/command` | backend → node | `{"cmd": "on"/"off"}` | published by `bridge.GenericDeviceController` |
| `.../zone/{zid}/device/{device_id}/state` | node → backend | `{"on": bool, "current_power": num, "voltage": num, "current": num, "energy_kwh": num, "power_factor": num}` | `mqtt_service._handle_v2_device_state` |
| `.../zone/{zid}/occupancy` | node → backend | `{"occupied": bool}` | `mqtt_service._handle_v2_occupancy` — for a node doing its own on-board multi-sensor fusion for a whole room |
| `.../zone/{zid}/health` | node → backend | heartbeat JSON (§6) | `mqtt_service._handle_v2_health` |
| `automation/{zone_id}/decision` | backend → world | full decision JSON | broadcast, not subscribed to; mirrors every `AutomationLog` row |

Only `device/{id}/state` and `.../health` currently have a payload field
list a real firmware author needs (below) — the others are already fully
specified above.

**Migration strategy:** the two hierarchies are permanent, not a
transition. No existing door node is ever reflashed to speak the new
topics; every new Sensor/Device (Zone/Device model) only ever speaks the
new hierarchy. The only overlap — AC/light/plug devices that already exist
as Doors/Plugs — keeps speaking `site/{code}/...` forever, mirrored into
the newer `Device` rows purely inside the database (`hardware/bridge.py`'s
legacy bridge), never re-published onto the new topic tree.

---

## 4. Telemetry contract (`app/hardware/telemetry.py`)

Every sensor reading, real or simulated, is expected to conform to this
shape before it reaches the database:

```json
{
  "device_id": null,
  "sensor_id": 7,
  "zone_id": 3,
  "timestamp": "2026-09-24T10:15:00Z",
  "sensor_type": "PIR",
  "metric": "occupancy",
  "value": true,
  "unit": null,
  "quality": "good",
  "source": "real",
  "sequence_number": 42
}
```

`source` must be `"real"` **only** when the reading arrived over an actual
MQTT message from actual hardware. Every simulated/manual code path in this
project (the `/api/sensors/{id}/reading` testing endpoint,
`energy_service.py`'s power simulation loop) sets `"simulated"`, and this is
enforced at the database level too — see §7.

A real occupancy node should publish to
`.../zone/{zid}/sensor/{sensor_id}/telemetry` with at minimum `metric` and
`value` set; `quality` and `sequence_number` are optional but recommended
(sequence numbers let the backend eventually detect dropped/reordered
messages, though nothing currently acts on gaps — that's a natural Phase 8
extension, not built).

---

## 5. Command lifecycle (hardening requirement — see `app/hardware/interfaces.py`)

A synchronous MQTT `publish()` call succeeding is **not** the same fact as
"the physical device changed state." This codebase distinguishes:

| Status | Meaning | Set by |
|---|---|---|
| `COMMAND_SENT` | The outgoing publish call succeeded | `RelayController.turn_on()/turn_off()`, synchronously |
| `COMMAND_FAILED` | Broker unreachable, or nothing to command | same, synchronously |
| `COMMAND_ACKNOWLEDGED` | *(reserved)* a node ack'd receipt before actually switching | not emitted by anything today — no node acks receipt separately from reporting state |
| `STATE_CONFIRMED` | A real status/state message reported the load actually changed | `mqtt_service._handle_v2_device_state`, and the legacy `ac/status`/`light/status`/`plug/.../status` handlers, whenever a real message arrives |
| `COMMAND_TIMEOUT` | *(reserved)* no ack/state arrived within an expected window | not implemented — there is no timeout tracker yet |

`Device.last_command_status` / `Device.last_command_at` persist the latest
of these. **Today, with no real relay/power hardware built, every command
in this project realistically stops at `COMMAND_SENT` or `COMMAND_FAILED`
and never reaches `STATE_CONFIRMED`** — that gap is exactly what a real
node publishing to `.../device/{id}/state` (or the legacy `.../status`
topics) closes. A real relay/contactor node's firmware should publish its
actual resulting state back over the appropriate status/state topic
immediately after actuating — that single message is what upgrades the
status to `STATE_CONFIRMED`.

---

## 6. Hardware health / heartbeat (`app/services/hardware_health_service.py`)

A node should periodically (every 30–60s is reasonable) publish to
`.../zone/{zid}/health`:

```json
{
  "node_id": "esp32-classroom-3-abc123",
  "firmware_version": "1.0.0",
  "uptime_seconds": 4521,
  "rssi": -58,
  "mqtt_connected": true,
  "sensor_healthy": true,
  "error_state": null
}
```

`node_id` should be stable across reboots (e.g. the chip's own MAC/efuse
ID) — one physical node can drive several Sensor/Device rows, so this is
the actual identity key, not `zone_id` alone. Omitting it is tolerated (a
synthetic per-zone ID is used and a warning logged) but not recommended.

A missing heartbeat for `HARDWARE_HEALTH_STALE_AFTER_SECONDS` (default
120s) marks the node `OFFLINE` via a background sweep — mirroring the
existing `staleness_watchdog.py` pattern for doors. **This table is
informational only and must never be wired into occupancy decisions**: a
node going offline means "don't trust this node's own reporting," which
`sense_zone_occupancy` already achieves independently via
`Sensor.last_seen` staleness (see §8). Do not connect `HardwareHealth`
status to the automation engine's SENSE step.

---

## 7. Real vs. simulated data — non-negotiable

Every place this project can produce a number that looks like a hardware
reading is required to say whether it is real:

| Field | Table | Set to `REAL` by | Set to `SIMULATED` by |
|---|---|---|---|
| `data_source` | `sensors` | `mqtt_service._handle_v2_telemetry` / `_handle_v2_occupancy` | `POST /api/sensors/{id}/reading` (manual/testing endpoint) |
| `power_source` | `devices` | `mqtt_service._handle_v2_device_state`, legacy `plug/.../status` (when `current_amps` present) | `energy_service.py`'s simulation loop |
| `source` | `energy_readings` | same MQTT handlers, via `energy_timeseries_service.record_reading(..., source="REAL")` | same simulation loop |

Nothing in this codebase is permitted to set any of these to `REAL` except
an actual received MQTT message. Every aggregation
(`energy_timeseries_service.aggregate`) reports how many readings in a
bucket were real vs. simulated (`all_simulated: true/false`) rather than
silently blending them — a dashboard chart built from this must surface
that flag, not hide it.

---

## 8. Occupancy confidence model (`config.OCCUPANCY_SOURCE_WEIGHTS`)

Confidence is a weighted-agreement score over whichever fresh signals exist
for a zone (door sensor, RFID grant, and any attached Sensor row), computed
in `automation_engine.sense_zone_occupancy`. The verdict itself
(OCCUPIED/EMPTY/UNKNOWN) is unaffected by weighting — any fresh OCCUPIED
signal wins outright regardless of confidence, by design. A **stale**
reading (older than `SENSOR_STALE_AFTER_SECONDS`, default 120s) is not
merely down-weighted — it is excluded entirely, so a zone with only stale
data reads `UNKNOWN`, never `EMPTY`.

Default weights (all overridable per-deployment via
`OCCUPANCY_SOURCE_WEIGHTS_JSON`, a JSON object merged over the defaults —
see `config.py`):

| Source | Default weight | Rationale |
|---|---|---|
| `sensor_mmwave` | 0.90 | Best available presence signal in this list |
| `sensor_esp32` | 0.85 | An ESP32 doing its own on-board fusion |
| `sensor_pir` | 0.80 | Reliable but can miss stationary occupants |
| `door_sensor` | 0.60 | Indirect — a closed door doesn't prove emptiness |
| `sensor_rfid_event` / `rfid_grant` | 0.50 | A badge-in doesn't prove the person stayed |
| `sensor_door_event` | 0.40 | A door-open event is a very indirect signal |
| `sensor_other` | 0.30 | Unclassified/unknown sensor type |

**These are reasoned starting points, not measured accuracy figures** — no
real occupancy sensor has been tested against this system yet. Tune them
once real hardware gives grounds to.

`Zone.occupancy_evidence` stores the full per-signal breakdown (source,
weight, raw state, human-readable text) as JSON — this is what makes a
confidence number explainable rather than a bare percentage; an admin
looking at a zone's evidence can answer "why did the system think this room
was empty?" without guessing.

---

## 9. Automation rules (`AutomationRule`, `automation_engine.resolve_rule`)

Only one trigger/action pair is implemented today:
`{"trigger": "CONFIRMED_EMPTY"}` → `{"action": "SHUTDOWN_NON_CRITICAL"}`. A
rule with any other action is accepted (the schema is open JSON, for
forward compatibility) but the engine logs `NO_ACTION` and does nothing for
it — it does not pretend to support an action it can't execute.

**Critical-load protection is enforced in the engine itself
(`shutdown_non_critical`), not by rule configuration.** Even a
hypothetical future rule that somehow implies a `CRITICAL` device should be
switched off cannot make the engine act on it — every such device is
explicitly refused and recorded in that decision's `AutomationLog.
blocked_actions` with reason `"Critical load protection"`.

---

## 10. What a real occupancy sensor node must do

1. Read presence from whatever sensor is wired in (PIR, mmWave, etc.).
2. Register the `Sensor` row it corresponds to once, via the dashboard's
   "+ Add sensor" form or `POST /api/zones/{id}/sensors` — this project
   does not auto-provision Sensor rows from MQTT traffic; a message for an
   unknown `sensor_id` is logged and dropped.
3. Publish to `university/{uid}/building/{bid}/zone/{zid}/sensor/{sensor_id}/telemetry`
   with `{"metric": "occupancy", "value": true|false, "quality": "good"}` on
   every state change, and periodically even if unchanged (a stale reading
   is exactly what `SENSOR_STALE_AFTER_SECONDS` protects against).
4. Publish a heartbeat to `.../zone/{zid}/health` per §6.

## 11. What a real relay/contactor node must do

1. Subscribe to `.../zone/{zid}/device/{device_id}/command` (or the legacy
   `site/{code}/ac|light|plug/.../cmd` topics, if it's replacing a Room's
   existing AC/light/plug).
2. On receiving `{"cmd": "on"|"off"}`, actuate the relay/contactor per §2 —
   never a GPIO directly to mains.
3. Publish the resulting state to `.../device/{id}/state` (or the legacy
   `.../status` topic) immediately after — this is the `STATE_CONFIRMED`
   signal (§5). Include `current_power`/`voltage`/`current` if the same
   node also has metering (§12).
4. Publish a heartbeat per §6.

## 12. What a real power-meter node must do

1. Measure voltage/current/power/power factor for whatever load it's
   attached to (a CT clamp on an AC circuit, an inline meter on a plug).
2. Publish readings on `.../device/{id}/state` — this project deliberately
   does not add a separate power-only topic; state and power reporting are
   the same message, matching the legacy plug/status shape.
3. Include enough of `{"current_power", "voltage", "current", "energy_kwh",
   "power_factor"}` as the hardware actually supports; missing fields are
   left `null`, never guessed.

---

## 13. Explicitly NOT done — do not assume otherwise

- No ESP32 occupancy firmware exists.
- No ESP32 power-metering firmware exists.
- No actual mains/electrical wiring has been designed or reviewed by
  anyone qualified to do so — that review must happen before any relay
  is wired to a real load, regardless of what this document says.
- `COMMAND_ACKNOWLEDGED` and `COMMAND_TIMEOUT` are reserved vocabulary
  only — nothing produces or consumes them yet.
- DESFire secure credential support is real (existing door firmware); the
  new hierarchy's node authentication (should a node need its own MQTT
  credentials, TLS client certs, etc.) has not been designed — see
  HARDWARE_READINESS_CHECKLIST.md's "INTEGRATION REQUIRED" section.
- PostgreSQL migration for a larger real deployment is documented as
  future work (see the backend's own `config.py`/README) — not built,
  intentionally, per this project's own "do not migrate now" instruction.
