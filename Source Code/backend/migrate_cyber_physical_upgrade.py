"""
Additive migration for the cyber-physical upgrade (face door access, room
occupancy counts, device fault monitoring):
  - zones.capacity (nullable INTEGER)
  - new tables: face_credentials, occupancy_readings, device_telemetry,
    device_fault_alerts (created from the SQLAlchemy models; no existing
    table is dropped, renamed, or has a column made NOT NULL).

Run from backend/ with the server stopped:  python3 migrate_cyber_physical_upgrade.py
Idempotent. (The server's lifespan create_all also creates the new tables.)
"""
import sqlite3
from db_path import sqlite_db_path

from app.database import Base, engine
from app import models  # noqa: F401  (registers tables)

conn = sqlite3.connect(sqlite_db_path())
cur = conn.cursor()
cur.execute("PRAGMA table_info(zones)")
if "capacity" not in {r[1] for r in cur.fetchall()}:
    cur.execute("ALTER TABLE zones ADD COLUMN capacity INTEGER")
    print("  + zones.capacity")
else:
    print("  = zones.capacity already present")
conn.commit()
conn.close()

Base.metadata.create_all(bind=engine, tables=[
    models.FaceCredential.__table__, models.OccupancyReading.__table__,
    models.DeviceTelemetry.__table__, models.DeviceFaultAlert.__table__,
    models.HvacSystem.__table__, models.HvacVent.__table__, models.HvacReading.__table__,
])
print("New tables ensured.")
