"""
Seeds the buildings dropdown with your university's actual building names.

Run from backend/ with the server stopped:
  python3 seed_buildings.py
Then restart: ./restart.sh

Safe to re-run — skips any name that's already there.
"""
import sqlite3
from db_path import sqlite_db_path

BUILDINGS = ["B2", "B8", "B9", "B10", "B11"]

conn = sqlite3.connect(sqlite_db_path())
cur = conn.cursor()

added = []
for name in BUILDINGS:
    cur.execute("SELECT 1 FROM buildings WHERE name = ?", (name,))
    if cur.fetchone():
        continue
    cur.execute("INSERT INTO buildings (name) VALUES (?)", (name,))
    added.append(name)

conn.commit()
conn.close()

if added:
    print(f"Added buildings: {', '.join(added)}")
else:
    print("All buildings already existed, nothing to add.")
