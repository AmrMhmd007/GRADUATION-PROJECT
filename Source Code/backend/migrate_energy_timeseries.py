"""
One-time local migration for Phase 6 (Zone/Device-scoped energy time
series): creates the new `energy_readings` table. This is deliberately
separate from the existing `power_readings` table (still used by the
legacy per-Room dashboard) — see EnergyReading's docstring in models.py for
why the two coexist rather than being merged.

Run from backend/ with the server stopped:
    python3 migrate_energy_timeseries.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS energy_readings (
        reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP,
        zone_id INTEGER REFERENCES zones(zone_id),
        device_id INTEGER REFERENCES devices(device_id),
        voltage REAL,
        current REAL,
        power REAL,
        energy_kwh REAL,
        power_factor REAL,
        source VARCHAR(10) NOT NULL DEFAULT 'SIMULATED',
        CHECK (source IN ('REAL','SIMULATED'))
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_energy_readings_timestamp ON energy_readings (timestamp)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_energy_readings_zone_id ON energy_readings (zone_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_energy_readings_device_id ON energy_readings (device_id)")

conn.commit()
conn.close()
print("energy_readings table ready.")
