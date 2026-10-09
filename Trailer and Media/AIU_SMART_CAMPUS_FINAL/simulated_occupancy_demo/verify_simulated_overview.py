#!/usr/bin/env python3
"""Calls the app's REAL /api/occupancy/overview endpoint in-process (FastAPI TestClient, no server, no lifespan loops) against the SIMULATION copy
and checks the response is internally consistent and honestly labelled. Admin auth is bypassed with a dependency override (test only)."""
import os, sys
from pathlib import Path
from types import SimpleNamespace
BASE = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get('AIU_PROJECT', BASE.parent.parent / 'TOP PR' / 'GRADUATION PROJECT' / 'Source Code'))
SIM_DB = BASE / 'sim_occupancy_demo.db'
assert SIM_DB.exists(), 'run seed_simulated_occupancy.py --fresh first'
os.environ['DATABASE_URL'] = f'sqlite:///{SIM_DB.resolve()}'; os.environ['DISABLE_MQTT'] = 'true'
sys.path.insert(0, str(PROJECT / 'backend'))
from app.database import engine
assert Path(engine.url.database).resolve() == SIM_DB.resolve(), 'engine not on the simulation copy'
from fastapi.testclient import TestClient
from app.main import app
from app import security
app.dependency_overrides[security.require_unrestricted_admin] = lambda: SimpleNamespace(role='admin', user_id=0, username='test-only')
r = TestClient(app).get('/api/occupancy/overview'); print('GET /api/occupancy/overview ->', r.status_code)
assert r.status_code == 200, r.text[:300]
d = r.json(); ok = True
def need(c, m):
    global ok; print(f'  [{"PASS" if c else "FAIL"}] {m}'); ok &= bool(c)
rooms = [x for b in d['buildings'] for f in b['floors'] for x in f['rooms']]
sim = [x for x in rooms if x['occupancy']['source'] == 'SIMULATED']; una = [x for x in rooms if x['occupancy']['state'] == 'UNAVAILABLE']
for x in rooms: print(f"    {x['room']:24s} state={x['occupancy']['state']:12s} count={x['occupancy']['count']!s:>4} cap={x['occupancy']['capacity']!s:>4} source={x['occupancy']['source']} health={x['sensor_health']}")
need(len(rooms) == 7, '7 rooms returned')
need(len(sim) == 4 and all(x['occupancy']['state'] == 'OK' for x in sim), '4 rooms carry source=SIMULATED with state OK')
need(len(una) == 3 and all(x['occupancy']['source'] is None and x['occupancy']['count'] is None for x in una), '3 rooms remain UNAVAILABLE with no source and no count (not shown as 0)')
need(all(x['occupancy']['count'] <= x['occupancy']['capacity'] for x in sim), 'every simulated count <= its capacity')
c = d['campus']
need(c['total_people'] == sum(x['occupancy']['count'] for x in sim) == 134, f"campus total_people={c['total_people']} equals the sum of the simulated rooms (134)")
need(c['occupied_rooms'] == 4 and c['rooms_with_live_count'] == 4 and c['rooms_total'] == 7, f"occupied_rooms={c['occupied_rooms']} rooms_with_live_count={c['rooms_with_live_count']}/{c['rooms_total']}")
print('RESULT:', 'ALL PASS' if ok else 'FAILURES'); sys.exit(0 if ok else 1)
