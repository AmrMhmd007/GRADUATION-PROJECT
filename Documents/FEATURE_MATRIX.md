# Verified feature inventory

*As of 2026-11-15, repository HEAD `e078a20` (local, not pushed). Each status comes from reading the code named in the table and from the automated backend tests listed. All tests ran on **SQLite** (668 collected, 668 passed in the last full serial run). Nothing here has been run on PostgreSQL, in a browser, on hardware, or in production.*

**How to read the status**

| Status | Rule used |
|---|---|
| **PASS** | Implemented in code **and** exercised by automated tests that passed. Where only the backend is tested, the row says the UI was not browser-verified. |
| **PARTIAL** | Real code exists, but it is limited (one case only, simulated data, rule-based where a model is wanted), or it is untested in an important dimension (live broker, hardware, PostgreSQL, UI). The Notes column says which. |
| **MISSING** | No code exists, or the code is explicitly a placeholder. |

"Tests" names the pytest files (number of tests in brackets). A file name is evidence of coverage in that area, not proof that every behaviour is covered.

## A. Identity, access and administration

| Feature | Status | Code | Tests | Notes |
|---|---|---|---|---|
| Login, JWT, roles (admin, doctor, instructor) | PASS | `security.py`, `routers/auth.py`, `routers/users.py` | `auth` (8), `users_scope_gaps` (7) | HS256 shared secret; no token revocation; no MFA |
| Login lockout | PARTIAL | `rate_limit.py` | `auth` | In memory, per process, lost on restart |
| Scoped administration (faculty, department, operational scope) | PASS | `security.py`, `routers/faculties.py`, `academic.py` | `scope_management_phase12` (9), `org_hierarchy` (52), `academic_admin_depth` (20) | |
| Password change, forced change, admin-approved reset | PASS | `routers/auth.py`, `password_resets.py` | `password_reset` (26), `account_profile` (13) | |
| Academic administration (colleges, departments, courses, assignments, Excel import) | PASS | `routers/academic.py`, `faculties.py`, `users.py` | `academic_admin_depth`, `bulk_import` (14), `phase8_persistence` (6), `delete_user` (10) | UI not browser-verified |
| Door management, assignments, schedules | PASS | `routers/doors.py`, `schedules.py` | `doors` (17), `schedules` (13) | |
| Access windows (WHEN layer, UTC) | PASS | `access_authorization_service.py`, `routers/access_windows.py` | `access_windows` (26) | |
| Access events with frozen authorization evidence | PASS | `mqtt_service.py` (event branch), `access_authorization_service.py` | `mqtt_ingestion` (5), `investigations` (11) | The node's own granted/denied result is recorded as reported |
| Emergency overrides (time-boxed, audited) | PASS | `emergency_override_service.py`, `routers/emergency_overrides.py` | `emergency_overrides` (26) | |
| Access anomaly indicators | PARTIAL | `anomaly_detection_service.py`, `routers/anomalies.py` | `anomaly_detection` (31) | Rule-based thresholds only; no statistics or ML. Tests now use a frozen clock |
| Audit log with filters and investigations | PASS | `audit_service.py`, `routers/audit_logs.py`, `investigations.py` | `audit_log` (7), `audit_log_extended` (12), `audit_log_filters_phase12` (6), `investigations` (11) | |
| Encrypted credentials with blind index | PASS | `crypto.py`, `routers/credentials.py` | `crypto` (6), `credentials` (6), `config_hardening` (5), `db_reliability` (14) | No key-rotation tool |
| Command center, global search | PASS | `routers/command_center.py`, `search.py` | `command_center` (15), `search` (21) | UI not browser-verified |
| Alerts | PASS | `routers/alerts.py` | `alerts` (3), `alerts_scope` (4) | |

## B. Smart building

| Feature | Status | Code | Tests | Notes |
|---|---|---|---|---|
| Buildings, zones, sensors, devices CRUD | PASS | `routers/zones.py`, `buildings.py` | `zone_sensor_device_crud` (31), `buildings_and_system_settings` (21) | Rooms are zones; no standalone Room model |
| Room device controls (AC, light, plugs) | PASS | `routers/doors.py`, `mqtt_service.publish_*` | `room_device_controls` (19) | Tests have no broker; commands are unsigned |
| Occupancy fusion with confidence | PASS | `automation_engine.sense_zone_occupancy` | `occupancy_confidence` (7), `automation_engine` (17) | Source weights are reasoned defaults, not measured |
| Occupancy counting (no identity) | PASS | `occupancy_service.py`, `routers/occupancy.py` | `cyber_physical` (41, shared) | Needs a real counting node to be useful |
| Automation engine | PARTIAL | `automation_engine.py` | `automation_engine` (17), `automation_rules` (19), `automation_investigation_link` (8) | Safe and tested, but one trigger and one action only; no rule builder |
| Staleness watchdog and hardware health | PASS | `staleness_watchdog.py`, `hardware_health_service.py` | `staleness_watchdog` (6), `hardware_health` (12) | |
| Device faults and maintenance recommendation | PARTIAL | `device_monitor_service.py`, `routers/device_faults.py` | `cyber_physical` | Threshold rule (3 faults in 30 days), explicitly not predictive |
| Room health, timeline and campus map read models | PARTIAL | `room_intel_service.py`, `routers/rooms_intel.py`, `physical/CampusMap.jsx` | `cyber_physical` | Floor/room grid only; no geometry or stored twin state |
| HVAC | PARTIAL | `hvac_service.py`, `routers/hvac.py` | `cyber_physical` | Monitoring only; the service issues no commands |
| Energy time series and savings estimate | PARTIAL | `energy_timeseries_service.py`, `routers/energy.py` | `energy_timeseries` (10) | Real-meter path exists; default data is simulated |
| Energy simulator and checkout sweep | PARTIAL (SIMULATED) | `energy_service.py` | `buildings_and_system_settings`, `hardening_constraints` (10) | No dedicated test of the high-power-in-empty-room alert was located. Does not run when `DISABLE_MQTT=true` |
| Real energy metering | MISSING | | | No meter hardware or ingestion beyond the MQTT state topic |

## C. Messaging and hardware abstraction

| Feature | Status | Code | Tests | Notes |
|---|---|---|---|---|
| Legacy MQTT topics `site/{code}/...` | PASS | `mqtt_service.py` | `mqtt_ingestion` (5) | Handlers fed directly; no live broker in the tests |
| v2 MQTT topics `university/.../zone/...` | PASS | `mqtt_service.py` | `mqtt_v2_topics` (11) | Same limit |
| Hardware abstraction interfaces and bridges | PARTIAL | `hardware/*.py` | `hardware_bridge` (9) | Interfaces and MQTT bridges only; no real device behind them |
| RS-485 gateway | PARTIAL | `gateway/` | none in pytest | Run end to end once with fake Python nodes (2026-10-09); not repeated in this phase; no real serial hardware |
| ESP32 door-node firmware | PARTIAL | `door_node_firmware/` | none | Never compiled or run in this project's verified work; wire-protocol header referenced by the gateway README is absent |
| Backend-to-device command authentication | MISSING | | | Commands and decisions are unsigned |

## D. Security and trust (Phases 1A to 1C)

| Feature | Status | Code | Tests | Notes |
|---|---|---|---|---|
| Face ID REAL enrolment blocked for client-supplied embeddings | PASS | `routers/face.py`, `face_service.enroll` | `face_enroll_restriction` (20) | Phase 1A |
| Face ID backend decision (match, then full authorization) | PASS | `face_service.decide` | `cyber_physical` (41) | Never a grant on its own; unchanged since before Phase 1 |
| Face ID SIMULATED enrolment | PARTIAL | `/api/face/me/enroll` | `cyber_physical`, `face_enroll_restriction` | Accepts a client vector, labelled SIMULATED, still honoured at the door by `decide` |
| Face ID real enrolment, capture, liveness, Raspberry Pi | MISSING | | | Not implemented. Embedding provider is `none` |
| Device identity registry | PASS | `device_auth_service.py`, `routers/device_identities.py` | `device_auth` (34) | In-process only; no dashboard screen |
| MQTT HMAC authentication and replay protection | PARTIAL | `device_auth_service.py`, `mqtt_service._screen_message` | `device_auth` | Verified in `warn` mode; `enforce` is unit tested but never run against a broker; legacy messages still accepted |
| Start-up validation of the encryption key | PASS | `config.py`, `crypto.py` | `db_reliability` | |
| Per-device broker credentials and topic ACLs | MISSING | | | One shared broker login |
| Token revocation, MFA | MISSING | | | |

## E. Data, migrations and delivery

| Feature | Status | Code | Tests | Notes |
|---|---|---|---|---|
| SQLite persistence | PASS | `models.py`, `database.py` | all files | |
| Alembic baseline and schema check | PARTIAL | `migrations/`, `schema_check.py` | `db_reliability` (14) | Baseline only; verified on temp SQLite files |
| PostgreSQL support | PARTIAL | `DATABASE_URL`, `requirements-postgres.txt` | DDL compiles for the PostgreSQL dialect | **Never executed against a PostgreSQL server** |
| GitHub CI | PARTIAL | `.github/workflows/ci.yml` | not observed | Jobs (SQLite backend, PostgreSQL backend, dashboard, gateway) are written; **none has been observed passing**; the PostgreSQL test step is allowed to fail |
| Dashboard build and lint | PARTIAL | `dashboard/` | oxlint: 0 errors, 14 warnings (re-run 2026-11-15) | No frontend tests; production build not re-run; browser flows not verified |

## F. The planned platform

| Planned system | Status | What exists today | What is missing |
|---|---|---|---|
| Campus Digital Twin | PARTIAL | Building, zone, occupancy, room-health read models, floor grid; Phase 2A (branch `feature/campus-digital-twin`, unpushed): geographic dataset format, validator, Leaflet map with unmapped/unavailable states (see `CAMPUS_GEOGRAPHY.md`) | **Any verified building outline** (none exists), campus boundary, licensed basemap, stored twin state and history, versioned twin API, browser verification |
| Intelligent Automation | PARTIAL | Safe occupancy-driven shutdown (section B) | General triggers and actions, rule builder, optimisation |
| AI Intelligence Engine | MISSING | Rule-based anomaly and maintenance indicators; energy and occupancy tables | Forecasting, prediction, models, feature pipeline, real data |
| Cybersecurity Center | PARTIAL | Audit log, lockout, device registry, HMAC warn mode, security events API | Dashboard, enforcement, broker ACLs, intrusion detection, alert routing |
| Campus AI Copilot | MISSING | | Everything |
| Simulation and Optimization Lab | MISSING | An energy simulator and a fake-node gateway simulator | Scenario engine, optimisation |
| Per-student attendance | MISSING | | Not implemented anywhere |

## G. Baseline totals

| Check | Result |
|---|---|
| Backend tests (SQLite, serial, 44 files) | 668 collected, 668 passed, 0 failed |
| Of which added in Phase 1 | 20 (Face ID restriction) + 34 (device auth) + 14 (database and configuration) = 68 |
| The earlier 3 anomaly failures | Caused by fixed 2026-09 test dates against a 30-day lookback; fixed by freezing the service clock in the test; verified by freezing it either side of the boundary |
| Dashboard lint (oxlint, 63 files) | 0 errors, 14 warnings (re-run 2026-11-15); the production build was not re-run |
| PostgreSQL, GitHub CI, browser, hardware | Not executed |
