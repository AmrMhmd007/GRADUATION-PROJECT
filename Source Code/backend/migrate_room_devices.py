"""
One-time local migration adding Room device controls (AC / light / plugs)
to existing doors.

Run from backend/ with the server stopped:
  python3 migrate_room_devices.py
Then restart: ./restart.sh
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(doors)")
door_cols = {row[1] for row in cur.fetchall()}

for col, ddl in [
    ("ac_enabled", "ALTER TABLE doors ADD COLUMN ac_enabled BOOLEAN NOT NULL DEFAULT 0"),
    ("ac_on", "ALTER TABLE doors ADD COLUMN ac_on BOOLEAN NOT NULL DEFAULT 0"),
    ("light_enabled", "ALTER TABLE doors ADD COLUMN light_enabled BOOLEAN NOT NULL DEFAULT 0"),
    ("light_on", "ALTER TABLE doors ADD COLUMN light_on BOOLEAN NOT NULL DEFAULT 0"),
]:
    if col not in door_cols:
        cur.execute(ddl)
        print(f"Added doors.{col}.")
    else:
        print(f"doors.{col} already exists, skipping.")

cur.execute("""
    CREATE TABLE IF NOT EXISTS plugs (
        plug_id INTEGER PRIMARY KEY,
        door_id INTEGER NOT NULL REFERENCES doors(door_id),
        label VARCHAR(60) NOT NULL DEFAULT 'Plug',
        "on" BOOLEAN NOT NULL DEFAULT 0,
        current_amps FLOAT,
        last_seen DATETIME
    )
""")
print("plugs table present.")

conn.commit()
conn.close()
print("Migration done.")
