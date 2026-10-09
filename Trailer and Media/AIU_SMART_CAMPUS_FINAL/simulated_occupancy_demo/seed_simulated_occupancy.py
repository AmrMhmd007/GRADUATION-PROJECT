#!/usr/bin/env python3
"""
SIMULATED occupancy dataset for the cinematic dashboard shot — ISOLATED from the real database.

* Snapshot: the real DB is opened READ-ONLY (mode=ro&immutable=1) and copied with sqlite's backup API into
  simulated_occupancy_demo/sim_occupancy_demo.db. The real file is never opened for writing.
* Seeding: uses the app's own occupancy_service.ingest(..., source="SIMULATED") against the COPY only (DATABASE_URL is forced to the copy
  before any app module is imported, and the resolved engine path is asserted).
* Honesty: rooms that are not simulated keep NO reading -> the UI shows Unavailable / UNKNOWN / UNAVAILABLE exactly as in the real system.
  Capacity values written to the copy are demo room metadata, not hardware telemetry.

Usage:  python3 seed_simulated_occupancy.py --fresh            # (re)build the copy and seed it
        python3 seed_simulated_occupancy.py --refresh          # keep readings fresh while recording (Ctrl-C to stop)
        python3 seed_simulated_occupancy.py --show             # print what the app will show
"""
import argparse, datetime, hashlib, json, os, sqlite3, sys, time, urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
DESKTOP = BASE.parent.parent                                       # .../Desktop
PROJECT = Path(os.environ.get('AIU_PROJECT', DESKTOP / 'TOP PR' / 'GRADUATION PROJECT' / 'Source Code'))
REAL_DB = PROJECT / 'backend' / 'access_control.db'
SIM_DB = BASE / 'sim_occupancy_demo.db'
BASELINE = BASE / 'real_db_baseline.json'

# room name -> (capacity, simulated head-count). Everything else stays Unavailable. 134 people / 4 rooms in total.
ROOMS = {'Room A101': (40, 31), 'Room A102': (30, 18), 'Smart Lab 301': (24, 11), 'Lecture Hall 101': (120, 74)}
NODE = {'Room A101': 'SIM-NODE-A101', 'Room A102': 'SIM-NODE-A102', 'Smart Lab 301': 'SIM-NODE-LAB301', 'Lecture Hall 101': 'SIM-NODE-LH101'}

def sha256(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(chunk), b''): h.update(b)
    return h.hexdigest()

def real_db_state():
    c = sqlite3.connect(f'file:{urllib.parse.quote(str(REAL_DB))}?mode=ro&immutable=1', uri=True)
    try:
        tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
        counts = {t: c.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tabs}
    finally: c.close()
    return {'sha256': sha256(REAL_DB), 'bytes': REAL_DB.stat().st_size, 'mtime': REAL_DB.stat().st_mtime, 'row_counts': counts}

def cmd_baseline():
    s = real_db_state(); BASELINE.write_text(json.dumps(s, indent=2)); print('real DB baseline written:', s['sha256'], s['bytes'], 'bytes')

def cmd_check_real():
    b = json.loads(BASELINE.read_text()); s = real_db_state()
    same = (b['sha256'] == s['sha256'] and b['row_counts'] == s['row_counts'])
    print(f"real DB sha256 baseline={b['sha256'][:16]}… now={s['sha256'][:16]}…  row-counts identical={b['row_counts'] == s['row_counts']}  -> {'UNCHANGED' if same else 'CHANGED (investigate: is the real backend running?)'}")
    only_audit = [t for t in s['row_counts'] if s['row_counts'][t] != b['row_counts'].get(t)] in ([], ['audit_logs'])
    occ = s['row_counts'].get('occupancy_readings', 0)
    print(f"  tables whose row count changed: {[t for t in s['row_counts'] if s['row_counts'][t] != b['row_counts'].get(t)]} | occupancy_readings in real DB: {occ} (must be 0)")
    if not same and only_audit and occ == 0: print('  NOTE: only audit_logs grew (a login on your real backend). No occupancy/simulated data in the real DB -> simulation did not touch it.')
    return same

def snapshot(fresh):
    assert SIM_DB.resolve() != REAL_DB.resolve() and SIM_DB.resolve().parent == BASE.resolve(), 'refusing: sim DB path unsafe'
    if fresh and SIM_DB.exists(): SIM_DB.unlink()
    if SIM_DB.exists(): print('using existing simulation copy', SIM_DB); return
    if not BASELINE.exists(): cmd_baseline()
    src = sqlite3.connect(f'file:{urllib.parse.quote(str(REAL_DB))}?mode=ro&immutable=1', uri=True)
    dst = sqlite3.connect(SIM_DB); src.backup(dst); dst.close(); src.close(); print('read-only snapshot copied ->', SIM_DB)

def load_app():
    os.environ['DATABASE_URL'] = f'sqlite:///{SIM_DB.resolve()}'; os.environ['DISABLE_MQTT'] = 'true'    # BEFORE importing the app
    sys.path.insert(0, str(PROJECT / 'backend'))
    from app.config import settings; from app.database import engine, SessionLocal
    from app import models; from app.services import occupancy_service as svc
    eng_path = Path(engine.url.database).resolve()
    assert eng_path == SIM_DB.resolve() and eng_path != REAL_DB.resolve(), f'ENGINE POINTS AT {eng_path} — aborting'
    print('engine bound to the SIMULATION copy:', eng_path)
    return settings, SessionLocal, models, svc

def ingest_all(SessionLocal, models, svc, now, history=True):
    n = 0
    with SessionLocal() as db:
        for name, (cap, target) in ROOMS.items():
            z = db.query(models.Zone).filter(models.Zone.name == name).first()
            if z is None: print('  skip (zone not found in copy):', name); continue
            z.capacity = cap; db.commit()                                              # demo metadata, copy only
            pts = []
            if history:
                for k in range(90, 0, -5):                                             # every 5 min for the last 90 min: ramp up then hold
                    f = min(1.0, max(0.0, (90 - k) / 25.0)); wob = ((k // 5) * 7 + len(name)) % 3 - 1
                    pts.append((now - datetime.timedelta(minutes=k), max(0, min(cap, round(target * f) + (wob if f >= 1 else 0)))))
            pts.append((now, target))                                                  # newest reading == the headline number
            for ts, cnt in pts:
                svc.ingest(db, z, node_id=NODE[name], count=int(cnt), confidence=0.9, sensor_status='ok', source='SIMULATED', recorded_at=ts); n += 1
    return n

def show(SessionLocal, models, svc):
    now = datetime.datetime.utcnow(); tot = occ = live = 0
    print(f"{'Room':24s}{'state':13s}{'count':>6s}{'cap':>6s}  source")
    with SessionLocal() as db:
        for z in db.query(models.Zone).order_by(models.Zone.zone_id).all():
            c = svc.current(db, z, now); ok = c['state'] in ('OK', 'DEGRADED')
            print(f"{z.name:24s}{c['state']:13s}{str(c['count'] if ok else '—'):>6s}{str(z.capacity or '—'):>6s}  {c['source'] or 'UNAVAILABLE'}")
            if ok: tot += c['count']; live += 1; occ += 1 if c['count'] > 0 else 0
    print(f'totals: people={tot} occupied_rooms={occ} rooms_with_live_count={live}/7')
    return tot, occ, live

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--fresh', action='store_true'); ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--show', action='store_true'); ap.add_argument('--check-real', action='store_true'); ap.add_argument('--interval', type=int, default=45)
    a = ap.parse_args()
    if a.check_real: sys.exit(0 if cmd_check_real() else 1)
    if a.fresh: snapshot(True); settings, SL, models, svc = load_app(); print('seeded', ingest_all(SL, models, svc, datetime.datetime.utcnow()), 'SIMULATED readings'); show(SL, models, svc)
    elif a.show: settings, SL, models, svc = load_app(); show(SL, models, svc)
    elif a.refresh:
        snapshot(False); settings, SL, models, svc = load_app(); print(f'refreshing SIMULATED readings every {a.interval}s (same counts; keeps them under the {settings.OCCUPANCY_STALE_AFTER_SECONDS}s stale limit). Ctrl-C to stop.')
        while True:
            ingest_all(SL, models, svc, datetime.datetime.utcnow(), history=False); time.sleep(a.interval)
    else: ap.print_help()
