"""
One-time local migration for the Smart Building Platform expansion (Zones,
Sensors, Devices, Occupancy Events, Automation Logs, Zone Schedules), plus a
schema change to the existing `alerts` table.

Run from backend/ with the server stopped:
    python3 migrate_zones_and_automation.py
Then restart: ./restart.sh

What this does:

1. Creates the six new tables if they don't already exist. Normally a
   brand-new table doesn't need a migration script at all — create_all()
   makes it automatically the next time the backend starts (see
   migrate_energy_fields.py's own note on this) — but this script creates
   them explicitly anyway, because step 3 below needs to insert rows into
   them immediately, before the backend has ever started with the new
   models loaded.

2. Rebuilds the `alerts` table so door_id is nullable and two new columns
   (zone_id, severity) exist. SQLite can't ALTER a column's NOT NULL
   constraint or bolt on a new CHECK constraint after the fact, so this
   uses the standard rename -> recreate -> copy -> drop pattern. Every
   existing alert row is preserved: it keeps its door_id, gets zone_id=NULL
   and severity='WARNING'.

3. Auto-provisions a Zone for every existing access_service Door (a "Room"
   in the original system), carrying over its building/floor/name, plus a
   Device row for its AC, its light, and each of its Plugs. Each Device
   points back at the original door_id/plug_id via door_ref_id/plug_ref_id,
   so the new automation engine controls exactly the same hardware the
   existing AC/light/plug toggle endpoints already control, through the
   same MQTT commands (services/mqtt_service.py) — nothing about the
   original control path changes. This means every Room that already
   exists locally is immediately usable by the automation engine with zero
   manual re-setup. Corridors/offices/etc. have no Door to migrate from —
   create those directly through the new /api/zones endpoint.

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

# ---------------------------------------------------------------------------
# 1. New tables
# ---------------------------------------------------------------------------
cur.execute("""
    CREATE TABLE IF NOT EXISTS zones (
        zone_id INTEGER PRIMARY KEY,
        building_id INTEGER REFERENCES buildings(building_id),
        floor VARCHAR(20),
        name VARCHAR(80) NOT NULL,
        zone_type VARCHAR(20) NOT NULL DEFAULT 'ROOM'
            CHECK (zone_type IN ('ROOM','CLASSROOM','LAB','CORRIDOR','OFFICE','SERVER_ROOM','OTHER')),
        door_id INTEGER UNIQUE REFERENCES doors(door_id),
        occupancy_state VARCHAR(12) NOT NULL DEFAULT 'UNKNOWN'
            CHECK (occupancy_state IN ('OCCUPIED','EMPTY','VERIFYING','UNKNOWN')),
        occupancy_state_changed_at DATETIME,
        verification_started_at DATETIME,
        created_at DATETIME
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS sensors (
        sensor_id INTEGER PRIMARY KEY,
        zone_id INTEGER NOT NULL REFERENCES zones(zone_id),
        sensor_type VARCHAR(20) NOT NULL
            CHECK (sensor_type IN ('PIR','MMWAVE','ESP32','DOOR_EVENT','RFID_EVENT','OTHER')),
        status VARCHAR(10) NOT NULL DEFAULT 'offline' CHECK (status IN ('online','offline')),
        last_reading VARCHAR(200),
        last_seen DATETIME,
        occupancy_state BOOLEAN,
        created_at DATETIME
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS occupancy_events (
        event_id INTEGER PRIMARY KEY,
        zone_id INTEGER NOT NULL REFERENCES zones(zone_id),
        sensor_id INTEGER REFERENCES sensors(sensor_id),
        occupancy_state BOOLEAN NOT NULL,
        source VARCHAR(20) NOT NULL CHECK (source IN ('sensor','door_event','rfid_event','manual')),
        created_at DATETIME
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        device_id INTEGER PRIMARY KEY,
        zone_id INTEGER NOT NULL REFERENCES zones(zone_id),
        name VARCHAR(80) NOT NULL,
        type VARCHAR(30) NOT NULL CHECK (type IN
            ('LIGHT','AC','NON_CRITICAL_SOCKET','LAB_EQUIPMENT','SERVER','NETWORK_EQUIPMENT','SECURITY_EQUIPMENT','OTHER')),
        criticality VARCHAR(15) NOT NULL DEFAULT 'NON_CRITICAL' CHECK (criticality IN ('CRITICAL','NON_CRITICAL')),
        rated_power FLOAT,
        current_power FLOAT,
        status BOOLEAN NOT NULL DEFAULT 0,
        controllable BOOLEAN NOT NULL DEFAULT 1,
        automatic_control_enabled BOOLEAN NOT NULL DEFAULT 1,
        door_ref_id INTEGER REFERENCES doors(door_id),
        plug_ref_id INTEGER REFERENCES plugs(plug_id),
        created_at DATETIME
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS automation_logs (
        log_id INTEGER PRIMARY KEY,
        zone_id INTEGER REFERENCES zones(zone_id),
        decision VARCHAR(30) NOT NULL CHECK (decision IN
            ('NO_ACTION','VERIFICATION_STARTED','VERIFICATION_CANCELLED','SHUTDOWN_NON_CRITICAL','SHUTDOWN_SKIPPED_UNCERTAIN')),
        occupancy_snapshot VARCHAR(12),
        schedule_state VARCHAR(20),
        verification_result VARCHAR(20),
        power_snapshot FLOAT,
        devices_changed TEXT,
        reason TEXT,
        created_at DATETIME
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS zone_schedules (
        schedule_id INTEGER PRIMARY KEY,
        zone_id INTEGER REFERENCES zones(zone_id),
        day_of_week SMALLINT,
        open_time TIME NOT NULL,
        close_time TIME NOT NULL,
        grace_minutes INTEGER NOT NULL DEFAULT 10,
        verification_minutes INTEGER NOT NULL DEFAULT 5,
        created_at DATETIME
    )
""")
print("New tables ready: zones, sensors, occupancy_events, devices, automation_logs, zone_schedules.")

# ---------------------------------------------------------------------------
# 2. Rebuild `alerts` so door_id is nullable and zone_id/severity exist
# ---------------------------------------------------------------------------
cur.execute("PRAGMA table_info(alerts)")
alert_cols = {row[1]: row for row in cur.fetchall()}  # name -> (cid, name, type, notnull, dflt, pk)

needs_rebuild = (
    "zone_id" not in alert_cols
    or "severity" not in alert_cols
    or alert_cols["door_id"][3] == 1  # notnull flag still set
)
if needs_rebuild:
    cur.execute("ALTER TABLE alerts RENAME TO alerts_old")
    cur.execute("""
        CREATE TABLE alerts (
            alert_id INTEGER PRIMARY KEY,
            door_id INTEGER REFERENCES doors(door_id),
            zone_id INTEGER REFERENCES zones(zone_id),
            type VARCHAR(30) NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'WARNING' CHECK (severity IN ('INFO','WARNING','CRITICAL')),
            alert_time DATETIME,
            resolved BOOLEAN,
            requested_by INTEGER REFERENCES users(user_id)
        )
    """)
    cur.execute("""
        INSERT INTO alerts (alert_id, door_id, zone_id, type, severity, alert_time, resolved, requested_by)
        SELECT alert_id, door_id, NULL, type, 'WARNING', alert_time, resolved, requested_by FROM alerts_old
    """)
    cur.execute("DROP TABLE alerts_old")
    print("Rebuilt alerts table: door_id is now nullable, added zone_id + severity "
          "(existing rows kept, severity defaulted to 'WARNING').")
else:
    print("alerts table already has zone_id/severity and a nullable door_id, skipping rebuild.")

# ---------------------------------------------------------------------------
# 3. Auto-provision a Zone (+ Devices) for every existing Room (access_service Door)
# ---------------------------------------------------------------------------
cur.execute("SELECT door_id, code, name, building, floor, category, ac_enabled, light_enabled FROM doors")
doors = cur.fetchall()

# Door.building is a plain string; best-effort match it to a Building row.
cur.execute("SELECT building_id, name FROM buildings")
building_by_name = {name: bid for bid, name in cur.fetchall()}

zones_created = 0
devices_created = 0
for door_id, code, name, building, floor, category, ac_enabled, light_enabled in doors:
    if category != "access_service":
        continue  # Main Doors (critical) aren't "Rooms" and get no zone

    cur.execute("SELECT zone_id FROM zones WHERE door_id = ?", (door_id,))
    existing = cur.fetchone()
    if existing:
        zone_id = existing[0]
    else:
        building_id = building_by_name.get(building)
        cur.execute(
            "INSERT INTO zones (building_id, floor, name, zone_type, door_id, occupancy_state, created_at) "
            "VALUES (?, ?, ?, 'CLASSROOM', ?, 'UNKNOWN', datetime('now'))",
            (building_id, floor, name, door_id),
        )
        zone_id = cur.lastrowid
        zones_created += 1

    if ac_enabled:
        cur.execute("SELECT device_id FROM devices WHERE door_ref_id = ? AND type = 'AC'", (door_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO devices (zone_id, name, type, criticality, controllable, "
                "automatic_control_enabled, door_ref_id, status, created_at) "
                "VALUES (?, 'AC', 'AC', 'NON_CRITICAL', 1, 1, ?, 0, datetime('now'))",
                (zone_id, door_id),
            )
            devices_created += 1

    if light_enabled:
        cur.execute("SELECT device_id FROM devices WHERE door_ref_id = ? AND type = 'LIGHT'", (door_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO devices (zone_id, name, type, criticality, controllable, "
                "automatic_control_enabled, door_ref_id, status, created_at) "
                "VALUES (?, 'Light', 'LIGHT', 'NON_CRITICAL', 1, 1, ?, 0, datetime('now'))",
                (zone_id, door_id),
            )
            devices_created += 1

    cur.execute("SELECT plug_id, label FROM plugs WHERE door_id = ?", (door_id,))
    for plug_id, label in cur.fetchall():
        cur.execute("SELECT device_id FROM devices WHERE plug_ref_id = ?", (plug_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO devices (zone_id, name, type, criticality, controllable, "
                "automatic_control_enabled, plug_ref_id, status, created_at) "
                "VALUES (?, ?, 'NON_CRITICAL_SOCKET', 'NON_CRITICAL', 1, 1, ?, 0, datetime('now'))",
                (zone_id, label, plug_id),
            )
            devices_created += 1

print(f"Provisioned {zones_created} new zone(s), {devices_created} new device(s) from existing Rooms.")

conn.commit()
conn.close()
print("Migration done.")
