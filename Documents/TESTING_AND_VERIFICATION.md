# Testing baseline and verification ledger

*As of 2026-11-15, repository HEAD `e078a20` (local, not pushed).*

## 1. Current baseline (executed)

| Check | Result | How it was run |
|---|---|---|
| Backend tests, **SQLite** | **668 collected, 668 passed, 0 failed** | All 44 files in `Source Code/backend/tests`, run serially one file at a time (Python 3.10.12, `DISABLE_MQTT=true`, default SQLite test file). Collection count (`pytest --collect-only`) matches the passed count |
| Dashboard lint | 0 errors, 14 warnings (oxlint, 63 files) | `npx oxlint`, re-run 2026-11-15 |
| Schema/migration checks | Passed on temporary SQLite files | `tests/test_db_reliability.py` (14 tests) |
| `git diff --check` over the local commits | Clean | run before each Phase 1 commit |

Growth of the suite during Phase 1: 600 tests before, then +20 (`face_enroll_restriction`), +34 (`device_auth`), +14 (`db_reliability`) = 668.

The earlier 3 failures in `test_anomaly_detection.py` were **date-dependent**, not functional: the tests placed events on 2026-09-24 and the service looks back 30 days from the real clock. Freezing the service clock reproduced the boundary exactly (pass at 2026-10-24 09:00, fail at 11:00), and the test file now freezes that clock itself. Production code was not changed.

## 2. Not executed (pending, do not treat as verified)

| Item | Status |
|---|---|
| Backend tests or migrations on **PostgreSQL** | **Pending.** Only DDL compilation for the PostgreSQL dialect was checked. No PostgreSQL server was available |
| **GitHub Actions** jobs (`backend`, `backend-postgres`, `dashboard`, `gateway`) | **Not observed passing.** The workflow file parses as YAML; no run has been seen. The PostgreSQL test step is set to `continue-on-error` until a first run is seen |
| Dashboard production build | Not re-run in this phase (succeeded in an earlier audit) |
| Browser flows, UI behaviour | Not verified; no frontend tests exist |
| Live MQTT broker (TLS, authentication, ACLs) | Not run. Tests call the message handlers directly |
| MQTT `enforce` mode | Unit tested only |
| RS-485 gateway end-to-end | Passed once on 2026-10-09 with Python fake nodes; not repeated in this phase |
| ESP32 firmware build and run | Never done |
| Raspberry Pi, camera, physical doors, sensors, meters | No hardware used |
| Face ID real enrolment, liveness, spoof resistance | Not implemented, so not testable |
| Windows, macOS-specific start scripts end to end | Not executed |
| Load, soak, security or penetration testing | Not done |
| Alembic on a database that is behind on **columns** | Detected by `schema_check.py` only; no revision exists to fix it |

## 3. Test areas

| Area | Test files (tests) |
|---|---|
| Authentication, lockout, passwords | `auth` (8), `password_reset` (26), `account_profile` (13), `users_scope_gaps` (7), `delete_user` (10) |
| Scope and organisation | `scope_management_phase12` (9), `org_hierarchy` (52), `academic_admin_depth` (20), `bulk_import` (14), `phase8_persistence` (6) |
| Doors and access | `doors` (17), `schedules` (13), `access_windows` (26), `emergency_overrides` (26), `investigations` (11), `credentials` (6), `crypto` (6) |
| Audit and anomaly | `audit_log` (7), `audit_log_extended` (12), `audit_log_filters_phase12` (6), `anomaly_detection` (31) |
| Smart building and automation | `zone_sensor_device_crud` (31), `buildings_and_system_settings` (21), `room_device_controls` (19), `automation_engine` (17), `automation_rules` (19), `automation_investigation_link` (8), `occupancy_confidence` (7), `staleness_watchdog` (6), `hardware_health` (12), `hardware_bridge` (9), `energy_timeseries` (10), `hardening_constraints` (10) |
| Messaging | `mqtt_ingestion` (5), `mqtt_v2_topics` (11) |
| Face ID, occupancy counts, faults, HVAC, room health | `cyber_physical` (41), `face_enroll_restriction` (20) |
| Device trust | `device_auth` (34) |
| Database and configuration | `db_reliability` (14), `config_hardening` (5) |
| Command centre, search, alerts | `command_center` (15), `search` (21), `alerts` (3), `alerts_scope` (4) |

## 4. How to reproduce

See [`DEVELOPER_GUIDE.md`](./DEVELOPER_GUIDE.md), section "Running the tests". The suite takes several minutes serially. Run it from `Source Code/backend`; never run two pytest sessions in the same folder at once.

## 5. Honesty rules for this repository's documents

1. A check that was not run is written as "not run" or "pending", never as passed.
2. "Tested" means automated tests that were executed, and says on what (SQLite, in process).
3. Simulated data and simulated nodes are called simulated.
4. Hardware, browser, PostgreSQL and production claims need an executed check and a date.
