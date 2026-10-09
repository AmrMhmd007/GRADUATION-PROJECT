# AIU Smart Campus — Cyber-Physical Campus Management System

Graduation project for Alamein International University (AIU). A cyber-physical smart campus platform covering secure door access, room occupancy counting, smart-building automation and energy monitoring. Built as: ESP32-based door nodes with RFID/DESFire authentication, an RS-485/Wi-Fi gateway, a FastAPI backend, MQTT-based real-time messaging, and a React admin dashboard for managing doors, schedules, staff, and alerts.

![Python](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=black)
![MQTT](https://img.shields.io/badge/messaging-MQTT-660066?logo=mqtt&logoColor=white)
![ESP32](https://img.shields.io/badge/firmware-ESP32-E7352C?logo=espressif&logoColor=white)

## What's in the platform

- **Access & Authorization** — scheduled and temporary access windows, a real WHO/WHEN authorization check, persisted access events with investigation detail, emergency overrides, anomaly indicators.
- **Face ID credential** (prototype) — encrypted templates and a door-node authorization flow. Face embedding is designed to run on a door-side Raspberry Pi; no adapter is configured on the server and no live door hardware is claimed.
- **Occupancy** — anonymous people-count ingest per room (source `REAL` or `SIMULATED`, always labelled). It counts people only; it does **not** identify students or record attendance.
- **Smart Building** — zones, sensors and devices, an automation engine with a verification window and decision log, HVAC model, energy-waste leads, hardware-node health.
- **Campus Intelligence** — campus map, room occupancy, device faults, room health and timeline.
- **Academic Administration** — colleges, departments, courses, doctors and teaching assistants.
- **Command Hub dashboard** — global search, command palette, role-based sidebar (admin, doctor, instructor).
- **Energy Impact Study** — model, report and presentation for the AIU campus.
- **Graduation film** — 115 s bilingual narrated trailer built from Blender concept scenes and real recordings of this software on demo data (labelled).

## Architecture

```
 Door node                         Edge (prototype)
 ESP32 + RFID/DESFire     ┐        Raspberry Pi: Face ID capture / embedding
                          │ RS-485 (primary) / Wi-Fi (fallback)
                          ▼
                  Building Gateway (RS-485 ⇄ MQTT bridge)
                          │ MQTT
                          ▼
 ┌──────────────────────── FastAPI backend ────────────────────────┐
 │ routers: auth · doors · access windows · schedules · face ·       │
 │          occupancy · zones · hvac · energy · alerts · anomalies · │
 │          investigations · audit logs · academic · search          │
 │ services: access authorization · automation engine · occupancy · │
 │           energy · device/hardware health · staleness watchdog   │
 └───────────────┬───────────────────────────────┬──────────────────┘
                 │ SQLAlchemy                    │ REST (JWT)
         SQLite / PostgreSQL               React + Vite dashboard
```

Full design rationale, the ERD and the API spec: [`Documents/System_Design_Document.docx`](./Documents/System_Design_Document.docx).

## Project structure

```
GRADUATION PROJECT/
├─ Source Code/
│  ├─ backend/                FastAPI app (app/routers, app/services, models, tests/, scripts/, migrate_*.py)
│  ├─ dashboard/              React + Vite admin dashboard (src/pages, src/components, src/api)
│  ├─ door_node_firmware/     ESP32 firmware (PlatformIO)
│  └─ Archive (phase snapshots)/   older zipped snapshots
├─ Documents/                 Design document, proposal, phase guides/reports, import templates
├─ Reports and Audits/        Phase 9–11 audits, smoke-test checklist, cyber-physical upgrade notes
├─ Hardware/                  Bill of materials, integration guide, readiness checklist
├─ Energy Impact Study/       model.py, report (docx/pdf), presentation, charts
├─ Trailer and Media/         Graduation-film scripts, reports and tooling (large media kept local)
├─ start.sh                   Start mosquitto + backend + dashboard locally
├─ start_lan.sh               Same, reachable from other devices on the network
└─ README.md
```

## Getting started

Requires Python 3.10+, Node.js 18+, and (optionally) `mosquitto` for MQTT.

```bash
git clone https://github.com/AmrMhmd007/GRADUATION-PROJECT.git
cd GRADUATION-PROJECT
./start.sh
```

This starts mosquitto (if installed), the backend on `:8000`, and the dashboard on `:5173`.

**Manual setup**, if you'd rather run each piece yourself:

```bash
# Backend
cd "Source Code/backend"
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m scripts.seed_db        # creates tables + a sample admin account
uvicorn app.main:app --reload

# Dashboard (in a separate terminal)
cd "Source Code/dashboard"
npm install
cp .env.example .env
npm run dev
```

Then open `http://localhost:5173` and log in with the admin account created by `seed_db.py`.

To let someone else on the same network open the dashboard (e.g. for a demo), use `./start_lan.sh` instead of `./start.sh`.

## Tech stack

| Layer | Technology |
|---|---|
| Firmware / edge | ESP32 (PlatformIO/C++), RFID/DESFire, RS-485; Raspberry Pi as the planned door-side Face ID capture/embedding device (prototype, not demonstrated live) |
| Gateway | Python, RS-485 ↔ MQTT bridge |
| Backend | FastAPI, SQLAlchemy, SQLite/PostgreSQL, JWT, MQTT (paho-mqtt) |
| Frontend | React, Vite |
| Bulk data | openpyxl (Excel import/export) |

## Documentation

- [System Design Document](./Documents/System_Design_Document.docx)
- [Security Review](./Documents/Phase5_Security_Review.pdf)
- [Multi-Node Deployment Guide](./Documents/Phase6_Multi_Node_Deployment_Guide.pdf)
- [System Test Report](./Documents/Phase7_System_Test_Report.pdf)
- [Study Guide](./Documents/Study_Guide_Access_Control_Project.pdf)

## Graduation film

Production scripts, timeline, mix tooling and reports live in `Trailer and Media/AIU_SMART_CAMPUS_FINAL/`. The film combines Blender concept scenes (clearly labelled), real screen recordings of this dashboard on an isolated demo database, and a supplied voice-over. Simulated data is labelled SIMULATED; the indoor attendance camera is a **concept** and not part of the implemented backend. Videos, audio, renders and `.blend` files are not stored in git.

## Honest scope

Implemented: access control and authorization, access-event audit trail, anonymous occupancy ingest, automation engine, dashboards. Prototype or concept: door-node firmware, Face ID at the door, physical occupancy cameras, per-student attendance.

## Author

**Amr Mohamed** — [github.com/AmrMhmd007](https://github.com/AmrMhmd007)
