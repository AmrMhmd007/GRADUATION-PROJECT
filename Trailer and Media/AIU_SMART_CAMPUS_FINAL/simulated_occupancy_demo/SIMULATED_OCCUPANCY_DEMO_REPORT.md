# Simulated occupancy dashboard demo — implementation report (Shot 5 preparation)

Status: **data layer built and tested at API level. The screen recording is NOT yet captured** (it must run on your Mac; see "Record it").

## What exists
All new files are in `AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/`. **No application source file was changed.**
- `seed_simulated_occupancy.py` — builds the isolated copy and seeds it; `--refresh` keeps readings fresh while recording; `--show`; `--check-real`.
- `verify_simulated_overview.py` — calls the app's real `GET /api/occupancy/overview` in-process against the copy and checks consistency.
- `sim_occupancy_demo.db` — the isolated database (a read-only snapshot of the real DB + SIMULATED readings). It contains a copy of your real users table (incl. password hashes) so you can log in as usual: keep it on this Mac, never commit or share it.
- `real_db_baseline.json` — hash and per-table row counts of the real DB taken before anything else.

## Isolation
1. The real DB (`backend/access_control.db`) is only opened with SQLite URI `mode=ro&immutable=1` and copied with the backup API.
2. The seeder forces `DATABASE_URL` to the copy **before importing the app** and asserts the SQLAlchemy engine path equals the copy and differs from the real file; it also refuses any sim path outside this folder.
3. The demo backend runs on **port 8001** with `DATABASE_URL` pointing at the copy and `DISABLE_MQTT=true`. The environment variable overrides `.env` (config loads `.env` with `setdefault`). Your normal backend on port 8000 and its DB are untouched.
4. The dashboard for the demo runs on **port 5174** with `VITE_API_BASE_URL=http://localhost:8001` (no file edited; separate browser origin and login from your normal :5173).

## Source labelling used (existing mechanism)
`occupancy_readings.source` ∈ {REAL, SIMULATED} (CHECK constraint) ← `occupancy_service.ingest(..., source="SIMULATED")` ← `/api/occupancy/overview` ← `SourceBadge` in `OccupancyOverview.jsx` (amber **SIMULATED**; grey **UNAVAILABLE**). `ingest` only triggers door automation for REAL readings, so the simulated counts cannot drive real actions.

## Data (internally consistent; verified by the endpoint test)
| Room | Count / capacity | Source |
|---|---|---|
| Room A101 | 31 / 40 | SIMULATED |
| Room A102 | 18 / 30 | SIMULATED |
| Smart Lab 301 | 11 / 24 | SIMULATED |
| Lecture Hall 101 | 74 / 120 | SIMULATED |
| Server Room, Section Room 204, Hall B – Ground Floor | — | stay **Unavailable / UNKNOWN / UNAVAILABLE** |

Campus tiles computed by the app from those rows: 134 people, 4 occupied rooms, 4 / 7 rooms with live count. Each simulated room has 90 minutes of history (5-minute readings: ramp-up, then hold) so history views are not empty. Capacities are demo room metadata written to the copy only.

## Verification actually executed (sandbox)
- Real DB before/after: SHA-256 `463ae1e97de905ef…` identical, file size 724,992 bytes identical, mtime identical, every table's row count identical → **UNCHANGED**.
- `verify_simulated_overview.py`: HTTP 200, 6/6 checks PASS (7 rooms; 4 SIMULATED with state OK; 3 UNAVAILABLE with no source and no count, not shown as 0; every count ≤ capacity; total 134 = sum of rooms; occupied 4, live 4/7).
- Not tested yet: the actual browser rendering of the amber badges (needs the app running on your Mac).

## Record it (your Mac, 3 terminals; activate the same Python environment you use for the backend)
1. Backend (demo DB, port 8001):
   `cd "$HOME/Desktop/TOP PR/GRADUATION PROJECT/Source Code/backend" && DATABASE_URL="sqlite:///$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/sim_occupancy_demo.db" DISABLE_MQTT=true uvicorn app.main:app --port 8001`
2. Keep readings fresh (the app treats readings older than 180 s as stale):
   `python3 "$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/seed_simulated_occupancy.py" --refresh`
3. Dashboard (port 5174):
   `cd "$HOME/Desktop/TOP PR/GRADUATION PROJECT/Source Code/dashboard" && VITE_API_BASE_URL=http://localhost:8001 npm run dev -- --port 5174`
4. Open http://localhost:5174, log in yourself, go to Campus Intelligence → Occupancy. Record with Cmd+Shift+5 at 1920×1080 (16:9): 2 s still on the page, slow scroll through Building A and B, 2 s hold. Tell me when the file is saved; I will trim and convert it (1080p30 H.264 + ProRes for compositing) and verify it.
After recording: stop the three terminals, then check the real DB again with `python3 …/seed_simulated_occupancy.py --check-real`.

## Limitations (honest)
- **Nothing here is live camera or hardware data.** It exercises the app's own SIMULATED path with invented counts. In the film it must be labelled (the per-row SIMULATED badge, plus a separate "SIMULATED DATA" overlay in post).
- The four tiles at the top ("People", "Occupied rooms", "Rooms with live count") carry no SIMULATED label, and the sensor pill reads ONLINE for the simulated rooms (the app derives it from fresh readings). I did not change the UI; a viewer could misread those. Options: label them in post, or (with your approval) a small UI change that shows a banner whenever SIMULATED data is present.
- The counts do not correspond to people visible in the 3D classroom (no people assets yet) — the dashboard shot and the classroom shot must not be presented as the same data until they do.
- The refresh loop re-sends the same counts every 45 s so the headline numbers stay constant while recording.
