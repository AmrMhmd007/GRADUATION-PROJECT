# Backend configuration reference

All settings are environment variables read by `Source Code/backend/app/config.py`; put them in `Source Code/backend/.env` (git-ignored, copy from `.env.example`). Defaults below are generated from the code. **Secret values are never shown here.**

Generate keys:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # CREDENTIAL_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # JWT_SECRET, CREDENTIAL_INDEX_KEY, FACE_NODE_API_KEY
```

Dashboard: `Source Code/dashboard/.env` — `VITE_API_BASE_URL` only if the API is not on the dashboard's host at port 8000. Firmware: `door_node_firmware/include/secrets.h` (from `secrets_example.h`).

## Core & security (set these for any real deployment)

`JWT_SECRET` signs login tokens. `CREDENTIAL_ENCRYPTION_KEY` (Fernet key) encrypts card UIDs at rest and `CREDENTIAL_INDEX_KEY` is the HMAC key for the lookup index — both must be **persisted**; if the encryption key is unset a temporary one is generated at every start and stored credentials become unreadable after a restart. `ALLOWED_ORIGINS` is the CORS allow-list (`*` only for local development). Login lockout settings throttle repeated failures.

| Variable | Type | Default |
|---|---|---|
| `DATABASE_URL` | str | `sqlite:///./access_control.db` |
| `JWT_SECRET` | str | `(not shown)` |
| `JWT_ALGORITHM` | str | `HS256` |
| `JWT_EXPIRE_MINUTES` | int | `60` |
| `ALLOWED_ORIGINS` | str | `*` |
| `CREDENTIAL_ENCRYPTION_KEY` | str | `(not shown)` |
| `CREDENTIAL_INDEX_KEY` | str | `(not shown)` |
| `LOGIN_MAX_ATTEMPTS` | int | `5` |
| `LOGIN_LOCKOUT_SECONDS` | int | `300` |

## MQTT

Connection to the broker. `DISABLE_MQTT=true` runs the API with no broker (used by the tests). `MQTT_UNIVERSITY_ID` is the id used in the `university/{id}/…` topic tree.

| Variable | Type | Default |
|---|---|---|
| `MQTT_BROKER_HOST` | str | `localhost` |
| `MQTT_BROKER_PORT` | int | `1883` |
| `MQTT_USE_TLS` | bool | `false` |
| `MQTT_USERNAME` | str | `(empty)` |
| `MQTT_PASSWORD` | str | `(not shown)` |
| `MQTT_UNIVERSITY_ID` | str | `aiu` |
| `DISABLE_MQTT` | bool | `false` |

## Face ID (prototype)

`FACE_NODE_API_KEY` is the shared secret an edge device sends as `X-Node-Key`; empty disables the HTTP node endpoints. `FACE_EMBEDDING_PROVIDER=none` means no embedding provider is installed (enrolment capture reports UNAVAILABLE). The thresholds only tune the verifier; none can turn a failure into a grant.

| Variable | Type | Default |
|---|---|---|
| `FACE_NODE_API_KEY` | str | `(empty = HTTP node endpoints disabled)` |
| `FACE_EMBEDDING_PROVIDER` | str | `none` |
| `FACE_MATCH_THRESHOLD` | float | `0.80` |
| `FACE_AMBIGUITY_MARGIN` | float | `0.05` |
| `FACE_MIN_QUALITY` | float | `0.5` |
| `FACE_REQUIRE_LIVENESS` | bool | `true` |

## Door, device and hardware health timing

How long silence is tolerated before a door/device/sensor is marked stale or offline, and fault thresholds.

| Variable | Type | Default |
|---|---|---|
| `DOOR_STALE_AFTER_SECONDS` | int | `30` |
| `DOOR_STALENESS_CHECK_INTERVAL_SECONDS` | int | `10` |
| `DEVICE_TELEMETRY_STALE_AFTER_SECONDS` | int | `300` |
| `DEVICE_COMMAND_RESPONSE_SECONDS` | int | `60` |
| `DEVICE_OFF_POWER_THRESHOLD_WATTS` | float | `5` |
| `DEVICE_ON_MIN_FRACTION_OF_RATED` | float | `0.05` |
| `HARDWARE_HEALTH_CHECK_INTERVAL_SECONDS` | int | `30` |
| `HARDWARE_HEALTH_STALE_AFTER_SECONDS` | int | `120` |
| `SENSOR_STALE_AFTER_SECONDS` | int | `120` |
| `HVAC_STALE_AFTER_SECONDS` | int | `600` |
| `MAINTENANCE_FAULT_THRESHOLD` | int | `3` |
| `MAINTENANCE_WINDOW_DAYS` | int | `30` |

## Occupancy, energy and automation

`ENERGY_SIM_INTERVAL_SECONDS` drives the **simulated** current readings (no current-sensor hardware is installed). Automation settings control the rule-engine cadence and verification window.

| Variable | Type | Default |
|---|---|---|
| `OCCUPANCY_STALE_AFTER_SECONDS` | int | `180` |
| `OCCUPANCY_SOURCE_WEIGHTS_JSON` | str | (see code) |
| `RFID_OCCUPANCY_WINDOW_SECONDS` | int | `900` |
| `ENERGY_SIM_INTERVAL_SECONDS` | int | `20` |
| `HIGH_POWER_WATTS_THRESHOLD` | float | `300` |
| `CHECKOUT_CHECK_INTERVAL_SECONDS` | int | `30` |
| `DEFAULT_CHECKOUT_TIME` | str | `18:00` |
| `AUTOMATION_INTERVAL_SECONDS` | int | `30` |
| `DEFAULT_VERIFICATION_MINUTES` | int | `5` |
| `EMERGENCY_OVERRIDE_MAX_DURATION_MINUTES` | int | `240` |
| `EMERGENCY_OVERRIDE_SWEEP_INTERVAL_SECONDS` | int | `15` |

## Access anomaly detection

Thresholds for the anomaly indicators shown in the dashboard.

| Variable | Type | Default |
|---|---|---|
| `ANOMALY_DEFAULT_LOOKBACK_DAYS` | int | `30` |
| `ANOMALY_DENIED_BURST_THRESHOLD` | int | `3` |
| `ANOMALY_DENIED_BURST_WINDOW_MINUTES` | int | `15` |
| `ANOMALY_POST_EXPIRY_FOLLOWUP_HOURS` | int | `24` |
| `ANOMALY_RAPID_BURST_THRESHOLD` | int | `5` |
| `ANOMALY_RAPID_BURST_WINDOW_MINUTES` | int | `5` |
| `ANOMALY_UNUSUAL_HOUR_START_UTC` | int | `6` |
| `ANOMALY_UNUSUAL_HOUR_END_UTC` | int | `22` |
