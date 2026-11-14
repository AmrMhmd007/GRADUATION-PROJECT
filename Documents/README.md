# Documentation index

*As of 2026-11-15, repository HEAD `e078a20` (local, not pushed). Start here. Documents are marked **current** (kept in line with the code), **reference** (design or hardware material), or **historical** (a dated report that describes the system at that time and is not updated).*

## Current documents

| Document | Read it for |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | How the system is built: backend, frontend, authentication, device registry, MQTT authentication, automation boundaries, data flows, hardware abstraction, database strategy |
| [`FEATURE_MATRIX.md`](./FEATURE_MATRIX.md) | What exists, as PASS / PARTIAL / MISSING, with code and test evidence |
| [`SECURITY_LIMITATIONS.md`](./SECURITY_LIMITATIONS.md) | What is not protected today (register with IDs SEC-01 to SEC-21) |
| [`TESTING_AND_VERIFICATION.md`](./TESTING_AND_VERIFICATION.md) | Test baseline (668 on SQLite) and the list of checks that have not been run |
| [`DEVELOPER_GUIDE.md`](./DEVELOPER_GUIDE.md) | Day-to-day setup: environment, keys, database, Alembic, tests, simulators |
| [`SETUP.md`](./SETUP.md) | First run from a fresh clone, step by step, including optional broker and gateway |
| [`CONFIGURATION.md`](./CONFIGURATION.md) | Every environment variable with its default; encryption-key lifecycle |
| [`DEVICE_AUTHENTICATION.md`](./DEVICE_AUTHENTICATION.md) | Device identity registry and the `aiu-hmac-v1` MQTT envelope; warn and enforce modes |
| [`DATABASE_MIGRATIONS.md`](./DATABASE_MIGRATIONS.md) | Alembic baseline, schema check, rollback limits, reviewing REAL Face ID credentials |
| [`ROADMAP.md`](./ROADMAP.md) | Planned stages: Cybersecurity Center, Data foundation, Digital Twin, AI Engine, Automation v2, Simulation Lab, Copilot |

## Reference documents

- [`../Hardware/HARDWARE_INTEGRATION.md`](../Hardware/HARDWARE_INTEGRATION.md), [`HARDWARE_BOM.md`](../Hardware/HARDWARE_BOM.md), [`HARDWARE_READINESS_CHECKLIST.md`](../Hardware/HARDWARE_READINESS_CHECKLIST.md): hardware design. The checklist records software groundwork only; no item has been verified on hardware.
- Design and project documents in this folder: `System_Design_Document.docx`, `Access_Control_System_Proposal_Revised.docx`, `Access_Control_System_Project_Timeline.xlsx`, `Phase2_Wiring_and_Bench_Test_Guide.docx`, `Phase5_Security_Review.pdf`, `Phase6_Multi_Node_Deployment_Guide.pdf`, `Phase7_System_Test_Report.pdf`, `Study_Guide_Access_Control_Project.pdf`, and the two import templates. These pre-date the Phase 1 work and are not updated.
- [`../Energy Impact Study/`](../Energy%20Impact%20Study/): offline energy analysis, not live data.

## Historical reports (not updated)

In [`../Reports and Audits/`](../Reports%20and%20Audits/): `PHASE_9_FRONTEND_API_AUDIT.md`, `PHASE_10_FINAL_SYSTEM_AUDIT.md`, `PHASE_10.1_MANUAL_SMOKE_TEST_CHECKLIST.md`, `PHASE_11_PRODUCTION_HARDENING_REPORT.md`, `CYBER_PHYSICAL_UPGRADE.md`, `REPOSITORY_AUDIT_2026-10-09.md`. Where one of them disagrees with a current document (for example the old "600 tests" or "no Alembic" statements), the current document wins.

## Conventions

- Maturity labels: `TESTED`, `IMPLEMENTED`, `PROTOTYPE`, `SIMULATED`, `PLANNED` (see `ARCHITECTURE.md`); feature status: PASS, PARTIAL, MISSING (see `FEATURE_MATRIX.md`).
- A check that was not run is written as "not run" or "pending". PostgreSQL, GitHub Actions, browser, live-broker and hardware results are all pending.
- Command blocks are kept narrow: one command per line, comments on their own lines.
