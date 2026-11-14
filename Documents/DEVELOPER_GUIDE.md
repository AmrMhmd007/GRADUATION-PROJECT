# Developer guide

*As of 2026-11-15, repository HEAD `e078a20` (local, not pushed). Commands marked "not run" were not executed during this documentation work. For a first run from a fresh clone use [`SETUP.md`](./SETUP.md); this guide is the day-to-day reference.*

All paths below are relative to the repository root unless stated. Backend commands run in `Source Code/backend` with the virtual environment active.

## 1. Prerequisites

Python 3.10 or newer, Node.js 18 or newer (22 is what CI uses), Git. Optional: mosquitto (MQTT broker), socat (gateway simulation), PlatformIO (firmware; never run in this project's verified work).

## 2. First-time backend setup

```
cd "Source Code/backend"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell activates with `venv\Scripts\Activate.ps1` (not tested).

## 3. Environment variables

Settings are read from the process environment and from `backend/.env` (git-ignored). The complete list with defaults is in [`CONFIGURATION.md`](./CONFIGURATION.md). The ones you will touch most:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLite file or PostgreSQL URL | `sqlite:///./access_control.db` |
| `DISABLE_MQTT` | Run without a broker (also stops the energy simulator) | `false` |
| `JWT_SECRET` | Signs login tokens | known development string (warning at start-up) |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for card UIDs, Face ID templates, device secrets | unset = temporary key |
| `CREDENTIAL_INDEX_KEY` | HMAC key for the card lookup index | unset = development key |
| `ALLOWED_ORIGINS` | CORS allow-list | `*` |
| `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_USE_TLS` | Broker connection | localhost:1883, no auth |
| `MQTT_AUTH_MODE` | `off`, `warn` or `enforce` | `warn` |
| `MQTT_AUTH_MAX_SKEW_SECONDS`, `MQTT_AUTH_EVENT_THROTTLE_SECONDS` | Replay window, event throttling | 120, 300 |
| `TEST_DATABASE_URL` | Run the test suite on another database (it is **dropped and recreated** between tests) | unset = SQLite |
| `FACE_NODE_API_KEY`, `FACE_EMBEDDING_PROVIDER` | Face ID node endpoints (empty key = disabled) | empty, `none` |

Never commit `.env`, `secrets.h` or any `.db` file; all are git-ignored. Start-up logs warnings for insecure defaults and never prints secret values.

## 4. Encryption keys: generate and persist

Generate once:

```
python -c "from cryptography.fernet import Fernet; \
print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The first command produces `CREDENTIAL_ENCRYPTION_KEY`. The second, run twice, produces `JWT_SECRET` and `CREDENTIAL_INDEX_KEY`. Put them in `backend/.env` or your secret manager, and **back them up separately from the database**.

- Persist them. With no encryption key the API still starts, using a temporary key, and everything encrypted with it (card UIDs, Face ID templates, device identity secrets) is unreadable after the next restart.
- An invalid `CREDENTIAL_ENCRYPTION_KEY` stops start-up with a message that never prints the value.
- There is **no key rotation or re-encryption tool.** Changing a key makes existing ciphertext unreadable and breaks card lookups when the index key changes. Do not change keys on a database that holds real credentials without a tested plan. See `SECURITY_LIMITATIONS.md` (SEC-11).

## 5. Database

**Initialise (new SQLite database with sample data):**

```
python -m scripts.seed_db
```

It skips if users already exist. The API also creates missing tables on every start. The seed script prints the sample logins; they are for local use only.

**PostgreSQL (never executed in this project):**

```
pip install -r requirements-postgres.txt
export DATABASE_URL="postgresql+psycopg2://user:pass@host/db"
python -m alembic upgrade head
```

**Alembic (Phase 1C baseline):**

```
python3 schema_check.py
python3 -m alembic upgrade head
python3 -m alembic current
```

- `schema_check.py` is read-only and lists missing tables or columns.
- `upgrade head` creates only missing tables and records the revision; it is safe to repeat and never alters or deletes data. It does not add missing columns: apply the matching legacy `migrate_*.py` script first (SQLite only).
- The baseline cannot be downgraded. Back up the database before any change.
- To add a change, create a new revision with `python3 -m alembic revision -m "message"` and follow the rules in `migrations/script.py.mako` (idempotent, no data rewrites).
- Full details: [`DATABASE_MIGRATIONS.md`](./DATABASE_MIGRATIONS.md).

**Reviewing existing Face ID credentials (read-only):**

```
python3 review_face_credentials.py
```

## 6. Running the system

```
DISABLE_MQTT=true uvicorn app.main:app --reload --port 8000
```

Dashboard, in a second terminal:

```
cd "Source Code/dashboard"
npm install
cp .env.example .env
npm run dev
```

API documentation: http://localhost:8000/docs. With a broker running, drop `DISABLE_MQTT=true` and set the `MQTT_*` variables.

## 7. Running the tests

```
cd "Source Code/backend"
source venv/bin/activate
pytest -q
```

- `conftest.py` forces `DISABLE_MQTT=true`, a throw-away SQLite file (`test_access_control.db`, git-ignored) and recreates all tables before every test. Your real database is never touched.
- The last full run on 2026-11-15 was serial, one file at a time: **668 passed, 0 failed** on SQLite. It takes several minutes; run one file or one test while developing:

```
pytest -q tests/test_device_auth.py
pytest -q tests/test_device_auth.py -k replay
```

- Do not run two pytest sessions in the same folder at once. With `pytest-xdist`, each worker uses its own SQLite file (the repository uses `pytest -n` only if you install it yourself).
- Other databases: set `TEST_DATABASE_URL` to a **throw-away** database. This path exists for the PostgreSQL CI job and **has not been run** by anyone.
- Dashboard:

```
cd "Source Code/dashboard"
npm run lint
npm run build
```

Lint reports 14 warnings and 0 errors. There are no frontend tests.

## 8. Simulators and test doubles

| What | Where | What it simulates | Verified |
|---|---|---|---|
| Direct message injection | tests call `mqtt_service._on_message(None, None, msg)` with a small object having `topic` and `payload` | Any MQTT message, without a broker | Used by `mqtt_ingestion`, `mqtt_v2_topics`, `device_auth`, `cyber_physical` |
| Energy simulator | `app/services/energy_service.py`, starts with the API when MQTT is enabled | Random power for rooms with AC or plugs on; daily checkout sweep | Not started when `DISABLE_MQTT=true`; data is labelled SIMULATED |
| Fake door nodes and virtual RS-485 | `Source Code/gateway/tests/fake_node_sim.py`, `run_e2e_simulation.sh` | Gateway to backend chain with a pure-Python broker | Passed once on 2026-10-09; not repeated since |
| Gateway load test | `gateway/tests/load_test.py` | Gateway traffic | Not run in this work |

`SIMULATED` sources are accepted by the occupancy, HVAC and energy services and are always flagged in the data.

### Signing a message as a device (in-process example)

Register an identity as an unrestricted admin (the secret is shown **once**):

```
curl -X POST http://localhost:8000/api/device-identities \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"esp-a1","message_types":["health"],
       "zone_ids":[1],"door_codes":[],"node_id":"node-a1"}'
```

Sign a payload with the reference client and deliver it:

```python
from app.services import device_auth_service as das
topic = "university/aiu/building/1/zone/1/health"
body = '{"node_id":"node-a1","rssi":-52}'
wire = das.sign_message("esp-a1", SECRET_HEX, topic, body)
# in a test or shell: mqtt_service._on_message(None, None, Msg(topic, wire))
# against a broker (not run): publish `wire` to `topic` with any MQTT client
```

With `MQTT_AUTH_MODE=warn` the message is processed either way and a finding is recorded for anything unsigned or invalid; read them at `GET /api/device-security/events` and `/summary`. Wire format and checks: [`DEVICE_AUTHENTICATION.md`](./DEVICE_AUTHENTICATION.md).

## 9. Working rules in this repository

- Do not push from automation; the owner pushes manually.
- Keep `face_service.decide` unchanged unless a change is explicitly approved; add tests with any change near Face ID, device authentication or access decisions.
- New tables need an Alembic revision (a test fails otherwise); new endpoints need RBAC tests.
- Write documents with maturity labels; do not describe a check that was not run as passed.
- Keep command blocks in documents narrow (one command per line, comments on their own lines).

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `RuntimeError: CREDENTIAL_ENCRYPTION_KEY is set but is not a valid Fernet key` | Regenerate it with the command in section 4 |
| Device secrets or card UIDs unreadable after a restart | The encryption key was not persisted |
| `NotImplementedError: The baseline cannot be downgraded` | By design; restore from a backup |
| `schema_check.py` reports missing columns | Apply the matching legacy `migrate_*.py` script (SQLite) before `alembic upgrade head` |
| MQTT connection errors repeat | Start a broker or set `DISABLE_MQTT=true` |
| Energy values never appear | The simulator is off when `DISABLE_MQTT=true` |
| Tests fail with `database is locked` | Two pytest sessions share a folder; run one |
