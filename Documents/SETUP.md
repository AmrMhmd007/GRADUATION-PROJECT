# Manual Setup Guide — run AIU Smart Campus from a fresh clone

Follow this top to bottom and the system runs on your machine with nothing else needed. **Time: about 10 minutes.**

**What was verified.** On 2026-10-09 / 10 the *Quick start* below was executed from a clean `git archive` of the repository in a Linux sandbox (new virtualenv, `pip install -r requirements.txt`, seed, API start, `npm install`, Vite dev server, login through the API with a browser `Origin` header): backend `/docs` = 200, dashboard `/` = 200, login = 200 with CORS headers. The backend test suite (600 tests) and the dashboard lint/build also passed. **Not executed** (no hardware or matching OS in the audit environment): Windows, a real MQTT broker via `mosquitto`, `start.sh` end to end, ESP32 firmware, the RS-485 gateway on real serial hardware, Face ID capture. Those sections say so.

---

## 1. Quick start (backend + dashboard, no hardware, no MQTT broker)

```bash
git clone https://github.com/AmrMhmd007/GRADUATION-PROJECT.git
cd GRADUATION-PROJECT

# --- Terminal 1: backend ---
cd "Source Code/backend"
python3 -m venv venv
source venv/bin/activate                 # Windows (PowerShell): venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python -m scripts.seed_db                # creates the database + sample users and doors
DISABLE_MQTT=true uvicorn app.main:app --reload --port 8000
#   Windows PowerShell:  $env:DISABLE_MQTT="true"; uvicorn app.main:app --reload --port 8000

# --- Terminal 2: dashboard ---
cd "Source Code/dashboard"
npm install
cp .env.example .env
npm run dev                              # opens on http://localhost:5173
```

Open **http://localhost:5173** and sign in with a sample account. `seed_db` prints the sample logins when it runs (they are defined in `Source Code/backend/scripts/seed_db.py`; they are for local use only — change or delete them before any shared deployment).

You should see the dashboard with four sample doors (Room A101, Room A102, Main Entrance, Server Room). API docs: **http://localhost:8000/docs**.

| Part | Port | URL |
|---|---|---|
| Backend API | 8000 | http://localhost:8000 (`/docs`, `/redoc`) |
| Dashboard (dev) | 5173 | http://localhost:5173 |
| MQTT broker (optional) | 1883 | — |

### Check that it works

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs      # expect 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/          # expect 200
```

Then sign in on the dashboard. If the login page loads but sign-in fails, see *Troubleshooting*.

---

## 2. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any | to clone |
| Python | **3.10 or newer** (`Source Code/backend/.python-version` = 3.10) | older versions fail with `TypeError: unsupported operand type(s) for \|` |
| Node.js + npm | 18+ (22 tested) | dashboard only |
| mosquitto | any recent | optional: only for MQTT/hardware |
| PlatformIO | latest | optional: only for the ESP32 firmware |
| socat | any | optional: only for the gateway simulation |

Install hints — macOS: `brew install python@3.11 node mosquitto`. Ubuntu/Debian: `sudo apt install python3 python3-venv python3-pip nodejs npm mosquitto socat`. Windows: install Python and Node from their websites; `start.sh` needs Git Bash or WSL (the manual commands above work in PowerShell). *The Windows route was not tested.*

---

## 3. Backend in detail

```bash
cd "Source Code/backend"
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

1. **Edit `.env`** (git-ignored). For local development the defaults work. For anything shared, set the keys in section 6 and read [`CONFIGURATION.md`](./CONFIGURATION.md) (every variable, its default and meaning).
2. **Create the database:** `python -m scripts.seed_db`. It is safe to re-run (it skips if users already exist). Tables are also created automatically whenever the API starts.
   - SQLite file `access_control.db` is created in `Source Code/backend/` (git-ignored). To use PostgreSQL set `DATABASE_URL=postgresql+psycopg2://user:pass@host/db` and `pip install psycopg2-binary` *(PostgreSQL was not tested in the audit)*.
3. **Optional demo data:**
   - `python -m scripts.import_schedule_csv scripts/sample_timetable.csv` — mock timetable.
   - `python3 seed_buildings.py` — adds building names B2, B8, B9, B10, B11 to the dropdown (stop the server first; edit the list for your campus).
4. **Run:** `uvicorn app.main:app --reload --port 8000` (add `--host 0.0.0.0` to allow other devices). Without a broker set `DISABLE_MQTT=true`.

### Keep an existing database up to date
Back up `access_control.db` first, then from `Source Code/backend` run the `migrate_*.py` scripts you need (`python migrate_<name>.py`). They are idempotent, SQLite-only and use the file named by `DATABASE_URL` (default `./access_control.db`). A fresh database never needs them.

### Reset to a clean state
Stop the server, delete `Source Code/backend/access_control.db`, run `python -m scripts.seed_db` again.

---

## 4. Dashboard in detail

```bash
cd "Source Code/dashboard"
npm install            # or: npm ci (uses the lockfile exactly)
cp .env.example .env
npm run dev
```

- The dashboard calls the API at **the same host it was opened from, port 8000**, so opening it as `http://192.168.1.20:5173` from a phone automatically uses `http://192.168.1.20:8000`. Only set `VITE_API_BASE_URL` in `.env` if the API lives elsewhere (it is read at build/start time).
- `npm run lint` and `npm run build` should both succeed (lint prints 14 non-blocking warnings).
- **Production build:** `npm run build` writes `dist/`; serve it with any static web server and build with `VITE_API_BASE_URL=https://your-api` set. Also set `ALLOWED_ORIGINS` on the backend to the dashboard URL.

---

## 5. One-command start (after the one-time setup in sections 1–4)

```bash
./start.sh          # mosquitto (if installed) + backend :8000 + dashboard :5173
./start_lan.sh      # same, reachable from other devices on your network
```

`start.sh` creates the backend `venv` and `.env` on first run if missing, stops a previous uvicorn on port 8000 (it refuses to touch any other program using that port), writes backend output to `backend.log`, and stops the backend when you press Ctrl+C. It uses `lsof`, so run it on macOS, Linux or WSL. *(Script logic was dry-run checked; a full start with mosquitto was not executed in the audit.)*

---

## 6. Before sharing or deploying (security checklist)

1. Generate keys and put them in `.env`:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # CREDENTIAL_ENCRYPTION_KEY
   python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # JWT_SECRET, CREDENTIAL_INDEX_KEY
   ```
   Keep `CREDENTIAL_ENCRYPTION_KEY` and `CREDENTIAL_INDEX_KEY` **stable** — if they change, stored encrypted credentials cannot be read.
2. Set `ALLOWED_ORIGINS` to the dashboard URL(s) (the backend warns at start-up while it is `*`).
3. Replace or remove the seeded sample users; use HTTPS in front of the API and dashboard.
4. Enable MQTT authentication and TLS (`MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_USE_TLS=true`).
5. Run without `--reload` (for example `uvicorn app.main:app --host 0.0.0.0 --port 8000`).

---

## 7. MQTT broker (optional — needed for doors, gateway and live device messages)

```bash
brew install mosquitto && mosquitto -d          # macOS     (Ubuntu: sudo apt install mosquitto && sudo systemctl start mosquitto)
```

Then remove `DISABLE_MQTT=true` and set `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` in `.env`. The default is `localhost:1883`, unauthenticated, for local development only. Topic reference: [`../Hardware/HARDWARE_INTEGRATION.md`](../Hardware/HARDWARE_INTEGRATION.md) and the README.

---

## 8. Hardware side (optional)

### 8.1 Try the gateway without hardware (verified in simulation)
`Source Code/gateway/tests/run_e2e_simulation.sh` starts the backend, a pure-Python MQTT broker, the gateway, a virtual serial pair and fake nodes, and checks status relay, an unlock command reaching a node, and the node's event landing in the backend. Requirements: `socat`, a throw-away venv with `pip install amqtt pyserial PyYAML paho-mqtt==2.1.0`, and the variables described at the top of the script (`E2E_PY`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD`, optional `E2E_BE_PY`). It passed on 2026-10-09; the node is a Python stand-in, not the ESP32 firmware.

### 8.2 Real gateway
```bash
cd "Source Code/gateway"
pip install -r requirements.txt
cp gateway_config.example.yaml gateway_config.yaml     # set serial.port, nodes (addr -> door code), mqtt
python rs485_gateway.py --config gateway_config.yaml
```
*Not run against real RS-485 hardware.*

### 8.3 ESP32 door-node firmware
1. Install PlatformIO.
2. `cp "Source Code/door_node_firmware/include/secrets_example.h" "Source Code/door_node_firmware/include/secrets.h"` and fill in Wi-Fi, broker and CA certificate (`secrets.h` is git-ignored — never commit it).
3. Set `DOOR_ID`, `DOOR_REQUIRES_BIO`, `DOOR_FAIL_MODE_SAFE` in `include/config.h`.
4. `pio run --target upload`, then `pio device monitor`.

*Not compiled in the audit.* The gateway README refers to `rs485_protocol.h` and `tests/test_cross_lang.py`, which are **not in this repository**; the RS-485 framing therefore cannot be cross-checked from this tree. Wiring and bench tests: [`Phase2_Wiring_and_Bench_Test_Guide.docx`](./Phase2_Wiring_and_Bench_Test_Guide.docx).

### 8.4 Face ID edge device
The backend supports it (`X-Node-Key` HTTP endpoints, set `FACE_NODE_API_KEY`; `FACE_EMBEDDING_PROVIDER`), but **no Raspberry Pi capture software is included** and by default no embedding provider is installed.

---

## 9. Tests

```bash
cd "Source Code/backend" && source venv/bin/activate
DISABLE_MQTT=true pytest -q                       # 600 tests, serial (~6-8 min on a small machine)
pip install pytest-xdist && DISABLE_MQTT=true pytest -q -n auto     # optional, parallel
cd ../dashboard && npm run lint && npm run build
```
Tests use their own SQLite files and never touch your real `access_control.db`. GitHub Actions (`.github/workflows/ci.yml`) runs the same checks on every push.

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `TypeError: unsupported operand type(s) for \|` | Python is older than 3.10. |
| `ModuleNotFoundError` when starting the backend | The virtualenv is not active (`source venv/bin/activate`) or `pip install -r requirements.txt` was skipped. |
| Backend log shows repeated MQTT connection errors | Start mosquitto, or run with `DISABLE_MQTT=true`. |
| Dashboard loads but login says network error | Backend not running on port 8000, or opened from another device while the backend only listens on localhost (use `--host 0.0.0.0`); check `VITE_API_BASE_URL` and `ALLOWED_ORIGINS`. |
| Cannot sign in with the sample account | `seed_db` was not run, or the database already had users (reset: delete `access_control.db` and re-seed). Too many failures lock the account temporarily. |
| `start.sh` says port 8000 is used by another program | Free the port or start uvicorn on another `--port` (also set `VITE_API_BASE_URL`). |
| Stored credentials unreadable after a restart | `CREDENTIAL_ENCRYPTION_KEY` was not persisted in `.env`. |
| `npm install` errors about `@rolldown/binding-darwin-arm64` | It is an optional macOS-only package and is skipped on other systems; use a current npm and `npm install` (not a copied `node_modules`). |
| Port 5173 busy | Vite chooses the next free port and prints it. |
| Tests fail with `database is locked` | Run serially, or install `pytest-xdist` and use `-n`; do not run two pytest sessions in the same folder at once. |

## 11. Getting updates
```bash
git pull
cd "Source Code/backend" && source venv/bin/activate && pip install -r requirements.txt
cd ../dashboard && npm install
```
Apply any new `migrate_*.py` scripts to an existing database (see section 3).

## 12. Not provided
No Docker/Docker Compose files are included, and there is no hosted demo. Windows and PostgreSQL paths are documented but untested.
