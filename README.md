# Smart Building Access Control System

A cyber-physical access control system built as a graduation project: ESP32-based door nodes with RFID/DESFire authentication, an RS-485/Wi-Fi gateway, a FastAPI backend, MQTT-based real-time messaging, and a React admin dashboard for managing doors, schedules, staff, and alerts.

![Python](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB?logo=react&logoColor=black)
![MQTT](https://img.shields.io/badge/messaging-MQTT-660066?logo=mqtt&logoColor=white)
![ESP32](https://img.shields.io/badge/firmware-ESP32-E7352C?logo=espressif&logoColor=white)

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
