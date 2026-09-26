# Hardware Readiness Checklist

Status as of the end of the software-groundwork phases (Phases 1–7). See
`HARDWARE_INTEGRATION.md` for the full detail behind every checked item.

- [x] Occupancy sensor interface defined (`app/hardware/interfaces.py::OccupancySensor`)
- [x] Power meter interface defined (`app/hardware/interfaces.py::PowerMeter`)
- [x] Relay/contactor abstraction defined (`app/hardware/interfaces.py::RelayController`, `LightingController`, `HVACController`, `SmartPlugController`)
- [x] MQTT telemetry schema defined (`app/hardware/telemetry.py::Telemetry`, `.../sensor/{id}/telemetry` topic)
- [x] MQTT command schema defined (`.../device/{id}/command`, legacy `.../ac|light|plug/cmd`)
- [x] Device acknowledgment defined (`COMMAND_SENT`/`COMMAND_FAILED`/`COMMAND_ACKNOWLEDGED`/`STATE_CONFIRMED`/`COMMAND_TIMEOUT` vocabulary — only the first two and `STATE_CONFIRMED` are actually produced today, honestly, since no real hardware acknowledges anything yet)
- [x] Heartbeat defined (`.../zone/{id}/health` topic, `node_id`/`firmware_version`/`uptime_seconds`/`rssi`/`mqtt_connected`/`sensor_healthy`/`error_state` payload)
- [x] Hardware health model defined (`HardwareHealth`, `hardware_health_service.py`, ONLINE/OFFLINE/DEGRADED/UNKNOWN)
- [x] Real/simulated data separation implemented (`Sensor.data_source`, `Device.power_source`, `EnergyReading.source` — all REAL/SIMULATED, enforced at every write site)
- [x] Critical-load protection implemented (enforced inside `automation_engine.shutdown_non_critical` itself, not delegated to rule configuration; blocked attempts recorded with reason)
- [x] Occupancy confidence implemented (`sense_zone_occupancy`, configurable weights, full evidence breakdown stored per-zone and per-decision)
- [x] Automation rules implemented (`AutomationRule` model, `resolve_rule`/`get_applicable_rules`, database-backed, no visual builder yet — by design, not yet requested)
- [x] Energy history implemented (`EnergyReading` time series, hourly/daily/weekly/monthly aggregation, REAL/SIMULATED flagged per bucket)
- [x] Hardware BOM documented (`HARDWARE_BOM.md`)
- [x] Hardware integration documented (`HARDWARE_INTEGRATION.md`)
- [x] Legacy door node compatibility verified (zero changes required to existing firmware or `site/{code}/...` topics; full test suite green throughout)
- [x] Existing tests passing (see the final test run recorded in the closing report)

## Work breakdown for what comes next

### SOFTWARE COMPLETE
- Hardware abstraction layer (interfaces + legacy/generic bridges)
- Telemetry contract and MQTT topic hierarchy (both legacy and new, coexisting)
- Confidence-scored occupancy fusion with explainable evidence
- Database-backed automation rules with engine-enforced critical-load protection
- Hardware health/heartbeat tracking and staleness sweep
- Energy time-series storage and aggregation
- Command-lifecycle status tracking (as far as software can honestly go without real acknowledging hardware)
- Full backend test coverage for all of the above

### HARDWARE REQUIRED
- An actual ESP32 occupancy node (PIR at minimum; mmWave/door-reed optional) — see `HARDWARE_BOM.md`
- An actual ESP32 relay/contactor node for a real controllable load
- An actual power-metering node (CT clamp or dedicated metering IC)
- Electrical review and correct relay/contactor sizing before any real mains load is switched

### INTEGRATION REQUIRED
- Flashing real firmware that speaks the topics documented in `HARDWARE_INTEGRATION.md` §10–12
- Registering real Sensor/Device rows for each physical node (no auto-provisioning from MQTT traffic exists — this is deliberate, to avoid ghost rows from stray/misconfigured messages)
- Deciding whether new nodes need their own MQTT authentication/TLS (not designed yet — the existing broker setup is used as-is)
- Tuning `OCCUPANCY_SOURCE_WEIGHTS` once real sensor behavior is observed, rather than the reasoned defaults currently in place

### TESTING REQUIRED
- Real-hardware end-to-end test of the full SENSE→ANALYZE→VERIFY→DECIDE→ACT→MONITOR→AUDIT cycle with an actual sensor and an actual relay (only simulated end-to-end testing exists today — see the closing report)
- Real command-failure and sensor-offline scenarios against actual hardware (simulated equivalents are covered by the automated test suite)
- Load testing of the MQTT broker under a realistic number of real nodes reporting on their own heartbeat/telemetry cadence
