"""
One-time local migration adding doors.floor.

Run from backend/ with the server stopped:
  python3 migrate_door_floor.py
Then restart: ./restart.sh
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(doors)")
door_cols = {row[1] for row in cur.fetchall()}
if "floor" not in door_cols:
    cur.execute("ALTER TABLE doors ADD COLUMN floor VARCHAR(20)")
    print("Added doors.floor.")
else:
    print("doors.floor already exists, skipping.")

conn.commit()
conn.close()
print("Migration done.")
