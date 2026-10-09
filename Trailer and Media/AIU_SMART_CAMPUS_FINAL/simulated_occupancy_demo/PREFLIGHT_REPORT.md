# Preflight report — simulated occupancy dashboard recording

## CONFIRMED (sandbox, read-only inspection)
- Inspected: backend config.py, database.py, main.py, occupancy_service.py, routers/occupancy.py, restart.sh, .env (keys only); dashboard OccupancyOverview.jsx, Badges.jsx, api/client.js, vite.config.js, package.json.
- Effective DB: `DATABASE_URL` is forced before the app imports; engine path asserted = `simulated_occupancy_demo/sim_occupancy_demo.db` (differs from real `backend/access_control.db`). API test: HTTP 200, 6/6 checks pass.
- Real DB has 0 occupancy_readings. Only change vs. baseline: audit_logs +1 (`login_success`, 11:33:22 UTC) — a login on the real backend, not written by the simulation (all my access is `mode=ro&immutable=1`).
- Sim DB is stamped with 4 SIMULATED rooms (134 people); 3 rooms have no reading (Unavailable).
- No application file modified. No MQTT (`DISABLE_MQTT=true`); SIMULATED readings never trigger door automation.

## BLOCKED — rule J
The overview endpoint reports `sensor_health = ONLINE` for the 4 simulated rooms; the UI shows ONLINE pills and an "ONLINE 4" legend, and the top tiles have no SIMULATED label. Recording now would misrepresent hardware as online.

### Proposed minimal fix (NOT applied — needs approval)
Frontend only, `dashboard/src/components/physical/OccupancyOverview.jsx`:
1. Sensor column: if `r.occupancy.source === "SIMULATED"` show `<SourceBadge source="SIMULATED" />` instead of the health pill.
2. Legend counts computed client-side: simulated rooms counted under SIMULATED, not ONLINE.
3. Small banner when any room is SIMULATED: "Contains SIMULATED readings — not live hardware."
No backend/CSS change (amber style exists). Alternative with zero code change: label in post only (weaker; the ONLINE pills would still be on screen).

## Commands (Mac, 3 terminals, same Python env as your normal backend)
1. `cd "$HOME/Desktop/TOP PR/GRADUATION PROJECT/Source Code/backend" && DATABASE_URL="sqlite:///$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/sim_occupancy_demo.db" DISABLE_MQTT=true uvicorn app.main:app --port 8001`
2. `python3 "$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/seed_simulated_occupancy.py" --refresh`
3. `cd "$HOME/Desktop/TOP PR/GRADUATION PROJECT/Source Code/dashboard" && VITE_API_BASE_URL=http://localhost:8001 npm run dev -- --port 5174`
Log in yourself at http://localhost:5174 (do not share credentials).

## NOT YET VERIFIED
Running uvicorn's effective DB; browser rendering; SIMULATED badge on screen; recording (none exists yet); conversion; trailer shot plan.
