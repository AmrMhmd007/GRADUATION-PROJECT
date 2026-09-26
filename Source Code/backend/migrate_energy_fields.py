"""
One-time local migration adding the energy/occupancy fields (power
consumption + room occupancy + auto-shutdown) to an existing database.

The two brand-new tables (power_readings, system_settings) don't need this
script — SQLAlchemy's Base.metadata.create_all(), which already runs on
every backend startup, creates any table that doesn't exist yet. Only the
new columns on the existing `doors` table need an explicit ALTER TABLE,
same as migrate_room_devices.py before it.

Run from backend/ with the server stopped:
  python3 migrate_energy_fields.py
Then restart: ./restart.sh
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(doors)")
door_cols = {row[1] for row in cur.fetchall()}

for col, ddl in [
    ("ac_current_amps", "ALTER TABLE doors ADD COLUMN ac_current_amps FLOAT"),
    ("occupied", "ALTER TABLE doors ADD COLUMN occupied BOOLEAN"),
    ("occupancy_updated_at", "ALTER TABLE doors ADD COLUMN occupancy_updated_at DATETIME"),
]:
    if col not in door_cols:
        cur.execute(ddl)
        print(f"Added doors.{col}.")
    else:
        print(f"doors.{col} already exists, skipping.")

conn.commit()
conn.close()
print("Migration done. power_readings / system_settings tables are created "
      "automatically the next time the backend starts.")
