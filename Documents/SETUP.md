# Manual setup guide

Step-by-step setup of every runnable part of AIU Smart Campus. The **backend** and **dashboard** steps below were verified on 2026-10-09 from a clean `git archive` of the repository (new venv, `pip install`, seed, server start, `/docs` returns 200; `npm ci`, lint and build succeed). Firmware and gateway steps are documented from their READMEs and were **not** executed (no hardware, PlatformIO or serial adapter in the audit environment).

## 0. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.10+ (see `Source Code/backend/.python-version`) | backend, gateway |
| Node.js | 18+ (22 tested) | dashboard |
| mosquitto | any recent | MQTT broker (optional for API-only use) |
| PlatformIO | latest | ESP32 firmware (hardware only) |

```bash
git clone https://github.com/AmrMhmd007/GRADUATION-PROJECT.git
cd GRADUATION-PROJECT
```

## 1. Backend (FastAPI)

```bash
cd "Source Code/backend"
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # edit: JWT_SECRET, ALLOWED_ORIGINS, MQTT_*, keys
python -m scripts.seed_db           # creates tables + sample users/doors (sample logins are printed; change before any shared use)
DISABLE_MQTT=true uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs (Swagger) · `/redoc`
- Drop `DISABLE_MQTT=true` once a broker is running.
- Database: SQLite file `access_control.db` in the working directory by default; set `DATABASE_URL` for PostgreSQL.
- Optional extra data (stop the server first for the second one): `python -m scripts.import_schedule_csv scripts/sample_timetable.csv` imports a mock timetable; `python3 seed_buildings.py` adds the building names B2, B8, B9, B10, B11 to the dropdown (edit the list for your campus; safe to re-run).
- **Existing databases from older versions:** back them up, then run the needed `migrate_*.py` scripts from `Source Code/backend` (they are idempotent, SQLite-only, and use the file from `DATABASE_URL`, default `./access_control.db`).

Generate persistent keys (do this for any real deployment):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # CREDENTIAL_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # JWT_SECRET / CREDENTIAL_INDEX_KEY
```

## 2. Dashboard (React + Vite)

```bash
cd "Source Code/dashboard"
npm install            # or: npm ci
cp .env.example .env   # normally leave VITE_API_BASE_URL unset
npm run dev            # http://localhost:5173
npm run lint && npm run build
```

The dashboard finds the API at the same host on port 8000 unless `VITE_API_BASE_URL` is set. Add the dashboard origin to `ALLOWED_ORIGINS` in the backend `.env` when you restrict CORS.

## 3. MQTT broker

```bash
brew install mosquitto && mosquitto -d        # macOS;  Linux: apt install mosquitto
```

Set `MQTT_BROKER_HOST/PORT` (and `MQTT_USERNAME/PASSWORD/USE_TLS` for a secured broker) in the backend `.env`. The default broker setting is localhost:1883, unauthenticated — local development only.

## 4. One-command start (after steps 1–2)

```bash
./start.sh          # mosquitto (if installed) + backend :8000 + dashboard :5173
./start_lan.sh      # same, reachable from other devices on the LAN
```

On first run `start.sh` creates `Source Code/backend/venv` and a `.env` (from `.env.example`) if missing. It stops a previous uvicorn backend on port 8000 but **refuses to touch any other program** using that port. Backend output goes to `backend.log` (git-ignored). (Script logic checked by dry run; a full start with mosquitto and Vite was not executed in the audit environment.)

## 5. Gateway (hardware / simulation)

```bash
cd "Source Code/gateway"
pip install -r requirements.txt
cp gateway_config.example.yaml gateway_config.yaml   # set serial.port, nodes, mqtt
python rs485_gateway.py --config gateway_config.yaml
```

Without hardware, run the automated simulation `Source Code/gateway/tests/run_e2e_simulation.sh` (needs `socat` and a throw-away venv with `amqtt pyserial PyYAML paho-mqtt==2.1.0`; see the header of the script for the environment variables). It passed on 2026-10-09 in a Linux sandbox.

## 6. ESP32 door-node firmware (hardware only)

1. Install PlatformIO.
2. `cp "Source Code/door_node_firmware/include/secrets_example.h" "Source Code/door_node_firmware/include/secrets.h"` and fill in Wi-Fi, broker and CA certificate (`secrets.h` is git-ignored — never commit it).
3. Set `DOOR_ID`, `DOOR_REQUIRES_BIO`, `DOOR_FAIL_MODE_SAFE` in `include/config.h`.
4. `pio run --target upload` then `pio device monitor`.

This firmware is a prototype; see its README for what it does not yet do. Note: the gateway README refers to `door_node_firmware/include/rs485_protocol.h` and `tests/test_cross_lang.py`, which are **not present** in this repository (only `config.h`, `secrets_example.h` and `src/main.cpp` are), so the RS-485 framing cannot be cross-checked from this tree.

## 7. Face ID edge device (planned)

The backend exposes node endpoints guarded by `X-Node-Key` (set `FACE_NODE_API_KEY`; empty means disabled) and `FACE_EMBEDDING_PROVIDER` (default `none`). No Raspberry Pi capture software is included in this repository.

## 8. Tests

```bash
cd "Source Code/backend" && source venv/bin/activate
DISABLE_MQTT=true pytest -q            # serial only: tests share one SQLite file
```

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `start.sh` says port 8000 is used by another program | Free the port or run uvicorn on another `--port` |
| `TypeError: unsupported operand type(s) for \|` | Python older than 3.10 |
| Repeated MQTT connection errors | Start mosquitto or set `DISABLE_MQTT=true` |
| Dashboard shows network errors | Backend not on :8000, or CORS: set `ALLOWED_ORIGINS` / `VITE_API_BASE_URL` |
| Stored credentials unreadable after restart | `CREDENTIAL_ENCRYPTION_KEY` was not persisted |
| `npm` install fails on a non-Mac | The macOS-only optional dependency is skipped normally; use `npm install` (not a stale lockfile copy) |
