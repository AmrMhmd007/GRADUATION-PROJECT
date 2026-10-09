# AIU Smart Campus — Cyber-Physical Campus Management System

Graduation project for Alamein International University (AIU). A cyber-physical smart campus platform covering secure door access, room occupancy counting, smart-building automation and energy monitoring. Built as: ESP32-based door nodes with RFID/DESFire authentication, an RS-485/Wi-Fi gateway, a FastAPI backend, MQTT-based real-time messaging, and a React admin dashboard for managing doors, schedules, staff, and alerts.

![Python](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=black)
![MQTT](https://img.shields.io/badge/messaging-MQTT-660066?logo=mqtt&logoColor=white)
![ESP32](https://img.shields.io/badge/firmware-ESP32-E7352C?logo=espressif&logoColor=white)

## What's in the platform

- **Access & Authorization** — schedule/temporary access windows, a real WHO/WHEN authorization check, persisted access events with investigation detail, emergency overrides.
- **Face ID credential** (Phase 1–2) — encrypted templates, door-node authorization flow. Door-node firmware is a prototype; no live door hardware is claimed.
- **Occupancy** — anonymous people-count ingest per room (source `REAL` or `SIMULATED`, always labelled). It counts people only; it does **not** identify students or record attendance.
- **Smart Building** — zones, sensors, devices, automation engine with a verification window and decision log, HVAC model and energy-waste leads.
- **Campus Intelligence** — campus map, room occupancy, device faults and health.
- **Academic Administration** — colleges, departments, courses, doctors and teaching assistants.
- **Command Hub dashboard** — global search, command palette, role-based sidebar.
- **Energy Impact Study** — model, report and presentation for the AIU campus.
- **Graduation film** — 115 s bilingual narrated trailer built from Blender scenes and real recordings of this software (demo data, labelled).

## Overview

The system controls physical door access across a university building using DESFire-secured RFID credentials, with every door node reporting status and events over MQTT to a central backend. Admins manage doors, schedules, and staff (TAs/doctors) through a web dashboard; the backend enforces role-based access, audit-logs every access event, and raises alerts on tamper or offline conditions.

## Key features

- **Role-based dashboard** — admin, instructor, and doctor roles, each with a scoped view (door control, schedules, staff management).
- **Door management** — add, edit, delete, and bulk-import doors from Excel, with building/floor/category metadata distinguishing main entrances from access-service rooms.
- **Staff management** — add, remove, and bulk-import TAs/doctors from Excel, with per-faculty organization and door-assignment/request-access workflows.
- **Real-time door status** — live lock/unlock state, online/offline detection, and a staleness watchdog over MQTT.
- **Security** — JWT authentication, bcrypt password hashing, DESFire AES mutual authentication at the door node, tamper lockout, and encrypted credentials at rest.
- **Resilient firmware** — RS-485 as the primary link with automatic Wi-Fi fallback, plus offline event buffering when disconnected from the gateway.
- **Account self-service** — users can update their name/email, change their password, and upload a profile photo; admins can create additional admin accounts.
- **LAN sharing** — helper scripts (`start_lan.sh`, `Source Code/backend/restart_lan.sh`) to expose the running system to other devices on the same network for demos.

## Architecture

```
Door Node (ESP32 + RFID/DESFire)
        │  RS-485 (primary) / Wi-Fi (fallback)
        ▼
   Building Gateway  ──MQTT──►  FastAPI Backend  ◄──REST──►  React Dashboard
                                      │
                                   SQLite / PostgreSQL
```

Full design rationale, the database ERD, and the REST/MQTT API spec are in [`Documents/System_Design_Document.docx`](./Documents/System_Design_Document.docx).

## Project structure

```
Source Code/
  backend/              FastAPI backend (REST API, MQTT listener, auth, scheduling)
  dashboard/             React + Vite admin dashboard
  door_node_firmware/    ESP32 firmware (PlatformIO project)
Documents/                Design docs, reports, and Excel import templates
Reports and Audits/       Phase 9–11 audits, smoke-test checklist, cyber-physical upgrade notes
Hardware/                 Bill of materials, integration guide, readiness checklist
Energy Impact Study/      Energy model (model.py), report (docx/pdf), presentation, charts
Trailer and Media/        Graduation-film production: scripts, reports and tooling (large media kept local, not in git)
start.sh                  Start the full stack locally (mosquitto + backend + dashboard)
start_lan.sh               Same, but reachable from other devices on the same network
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
| Firmware | ESP32 (PlatformIO/C++), RFID/DESFire, RS-485 |
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

## Author

**Amr Mohamed** — [github.com/AmrMhmd007](https://github.com/AmrMhmd007)

## Graduation film

Production scripts, timeline, mix tooling and reports live in `Trailer and Media/AIU_SMART_CAMPUS_FINAL/`. The film combines Blender concept scenes (clearly labelled), real screen recordings of this dashboard on an isolated demo database, and a supplied voice-over. Simulated data is labelled SIMULATED; the indoor attendance camera is a **concept** and not part of the implemented backend. Videos, audio, renders and `.blend` files are not stored in git.

## Honest scope

Implemented: access control and authorization, access-event audit trail, anonymous occupancy ingest, automation engine, dashboards. Prototype or concept: door-node firmware, Face ID at the door, physical occupancy cameras, per-student attendance.
