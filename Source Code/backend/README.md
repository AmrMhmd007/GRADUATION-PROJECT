# Access Control Backend — Phase 3 (+ Phase 5 security, Phase 6 multi-node, Phase 7 fixes)

FastAPI backend implementing the REST API spec, MQTT topic structure, and
database schema from the Phase 1 System Design Document. Covers all of
Section 3's Phase 3 tasks: repo/dev setup, DB schema, auth, credential
management, scheduling engine with a mock registrar import, the MQTT
event/alert listener, and audit logging via the access_events table.

**Update (Phase 4):** CORS is now enabled (`CORSMiddleware`, permissive
`allow_origins=["*"]`) so the Phase 4 dashboard, running on a different
origin/port, can call this API from a browser. Tighten this to the real
dashboard's deployed origin before production.

This has been run and tested in a real Python environment (FastAPI +
SQLite), not just written and assumed correct — see "What's been verified"
below.

## Setup

```bash
cd backend
python3 -m venv venv && source venv/bin/activate    # optional but recommended
pip install -r requirements.txt
cp .env.example .env                                 # edit as needed
python -m scripts.seed_db                             # creates tables + sample data
uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs for interactive API docs (FastAPI
generates this automatically from the code — it's not a separate thing to
maintain).

Default seeded logins (from `scripts/seed_db.py`):
- `admin@example.edu` / `admin123` (admin role)
- `instructor@example.edu` / `instructor123` (instructor role)

## Database

Defaults to SQLite (`access_control.db`) so it runs with zero setup. Point
`DATABASE_URL` in `.env` at PostgreSQL for anything beyond local dev/testing
— the code uses SQLAlchemy throughout, so no query changes are needed,
only the connection string. One schema difference from the original ERD in
the System Design Document: `doors.code` was added — a human-readable
identifier (e.g. `"A101"`) that matches each door node firmware's `DOOR_ID`
and is what MQTT topics use, since the ERD's numeric `door_id` primary key
isn't something firmware should need to know about.

## Mock registrar import

The real registrar's export format isn't known yet (see the System Design
Document's open questions). `scripts/import_schedule_csv.py` defines a
plausible CSV shape and imports it into `schedules`:

```bash
python -m scripts.import_schedule_csv scripts/sample_timetable.csv
```

When the real integration is scoped, only this importer should need to
change — the schedules table and API are already shaped to receive the data.

## MQTT

`app/services/mqtt_service.py` runs a background thread that subscribes to
`site/+/status`, `site/+/event`, and `site/+/alert` (matching the door node
firmware from Phase 2) and writes what it receives into the database. It
also exposes `publish_override()`, used by `POST /api/doors/{id}/override`
to send `site/{code}/cmd` down to a door node.

Set `DISABLE_MQTT=true` in `.env` to run the API without a broker (tests do
this automatically). There was no MQTT broker available in the sandbox this
was built in, so the ingestion logic was unit-tested directly against
`_on_message()` with fake messages rather than over a real network
connection — see `tests/test_mqtt_ingestion.py`. Test against a real
Mosquitto/HiveMQ broker before relying on this for the multi-node phase.

## Testing

```bash
pip install -r requirements.txt   # includes pytest, httpx
pytest -v
```

43 tests (up from 29 as of Phase 3) cover auth (login, bad password, token
requirement, rate limiting), role-based access control (admin-only
endpoints reject instructors with 403), doors (list/get/404/override +
audit logging), credentials (issue/revoke, encryption at rest), schedules
(create/update/validation), alerts (list/resolve), the MQTT message
handler, and the Phase 7 staleness watchdog (below).

## Door staleness watchdog (Phase 7)

Found during full-system fault-injection testing: a door's `online` flag
only ever went back to `false` because of an explicit "offline" message —
either a node's MQTT last-will, or (since Phase 6) the Building Gateway
publishing it after missing polls. If the gateway process itself dies
outright, neither path fires, and the doors it was relaying stay
`online=true` forever. `app/services/staleness_watchdog.py` fixes this with
a periodic sweep: any door still marked online whose `last_seen` is older
than `DOOR_STALE_AFTER_SECONDS` (default 30s, `.env`-configurable) gets
flipped to offline, regardless of transport. See
`Phase7_System_Test_Report.docx` for how this was found and verified live
(gateway killed mid-test, doors correctly marked offline within seconds).

## What's been verified vs. what's assumed

Verified by actually running the server and hitting endpoints, and by the
pytest suite (all 29 passing):
- Login, JWT issuance, and token validation
- Role-based 403s on admin-only routes
- Door override → MQTT publish attempt → audit log entry, even when no
  broker is connected
- Schedule creation/update against a real door foreign key
- Credential issue/revoke (revoke soft-deletes, doesn't break event history)
- CSV timetable import against the sample file
- MQTT message handling logic (status/event/alert) via direct unit tests

Not yet verified against a real broker or a real door node:
- The full site/{code}/cmd → firmware → site/{code}/cmd/ack round trip
- Behavior under concurrent access from multiple door nodes (Phase 6 scope)

## Known scope limitations (same spirit as the Phase 2 firmware README)

- Credential lookups match on `card_uid` only; there is no DESFire-level
  cryptographic verification happening at the backend either — that
  authentication happens (once implemented) at the firmware/reader level,
  and the backend simply trusts the UID it's given via MQTT. Treat this as
  a Phase 5 security item, not something this backend already closes.
- JWT secret and DB credentials in `.env.example` are placeholders — this
  file is gitignored for a reason, never commit real secrets.
- No rate limiting or account lockout on `/api/auth/login` yet.
