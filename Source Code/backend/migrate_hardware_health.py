"""
One-time local migration for Phase 5 (hardware node health/heartbeat
tracking): creates the new `hardware_health` table. No existing table is
touched — see app/models.py's HardwareHealth docstring for the full
field-by-field rationale, and app/services/hardware_health_service.py for
how rows get populated (a heartbeat over the Phase 2 MQTT
university/.../zone/{id}/health topic) and swept stale (a background
thread, same pattern as staleness_watchdog.py's door sweep).

Run from backend/ with the server stopped:
    python3 migrate_hardware_health.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS hardware_health (
        health_id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id VARCHAR(80) NOT NULL UNIQUE,
        zone_id INTEGER REFERENCES zones(zone_id),
        status VARCHAR(10) NOT NULL DEFAULT 'UNKNOWN',
        last_seen TIMESTAMP,
        firmware_version VARCHAR(40),
        uptime_seconds INTEGER,
        rssi INTEGER,
        mqtt_connected BOOLEAN,
        sensor_healthy BOOLEAN,
        error_state VARCHAR(120),
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        CHECK (status IN ('ONLINE','OFFLINE','DEGRADED','UNKNOWN'))
    )
""")

conn.commit()
conn.close()
print("hardware_health table ready.")
