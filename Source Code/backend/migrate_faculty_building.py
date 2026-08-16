"""
One-time local migration for the Faculty + Building feature.

Run this yourself in Terminal (same rules as migrate_doctor_category.py):
  1. Stop the backend (Ctrl+C, or if you're using restart.sh just Ctrl+C once).
  2. cd into the backend/ folder (where access_control.db lives).
  3. Run: python3 migrate_faculty_building.py
  4. Restart the backend: ./restart.sh   (or uvicorn app.main:app --reload)
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faculties'")
if not cur.fetchone():
    cur.execute("""
        CREATE TABLE faculties (
            faculty_id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL UNIQUE
        )
    """)
    print("Created faculties table.")
else:
    print("faculties table already exists, skipping.")

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='buildings'")
if not cur.fetchone():
    cur.execute("""
        CREATE TABLE buildings (
            building_id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL UNIQUE
        )
    """)
    print("Created buildings table.")
else:
    print("buildings table already exists, skipping.")

cur.execute("PRAGMA table_info(users)")
user_cols = {row[1] for row in cur.fetchall()}
if "faculty_id" not in user_cols:
    cur.execute("ALTER TABLE users ADD COLUMN faculty_id INTEGER REFERENCES faculties(faculty_id)")
    print("Added users.faculty_id.")
else:
    print("users.faculty_id already exists, skipping.")

# Seed the buildings list with whatever building names are already in use on
# existing doors, so the new dropdown isn't empty on first load.
cur.execute("SELECT DISTINCT building FROM doors WHERE building IS NOT NULL AND TRIM(building) != ''")
existing_buildings = [row[0] for row in cur.fetchall()]
for name in existing_buildings:
    cur.execute("INSERT OR IGNORE INTO buildings (name) VALUES (?)", (name,))
if existing_buildings:
    print(f"Seeded buildings from existing doors: {existing_buildings}")

conn.commit()
conn.close()
print("Migration done.")
