"""
One-time local migration for the "doctor" role + door category feature.

Run this yourself in Terminal (NOT through any remote/mounted access) — SQLite
schema changes need exclusive access to the .db file, and the backend server
must not be running while this executes.

Steps:
  1. Stop the backend (Ctrl+C in the uvicorn terminal).
  2. cd into the backend/ folder (where access_control.db lives).
  3. Run: python3 migrate_doctor_category.py
  4. Restart the backend: uvicorn app.main:app --reload
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

# 1. Doors: add a category column (critical vs access_service) so the
#    dashboard can split "Main Doors" (server room, main entrance) from
#    "Access Service" (halls, section/classroom doors).
cur.execute("PRAGMA table_info(doors)")
door_cols = {row[1] for row in cur.fetchall()}
if "category" not in door_cols:
    cur.execute("ALTER TABLE doors ADD COLUMN category TEXT NOT NULL DEFAULT 'access_service'")
    cur.execute("UPDATE doors SET category = 'critical' WHERE code = 'MAIN'")
    print("Added doors.category (MAIN marked as critical).")
else:
    print("doors.category already exists, skipping.")

# 2. Users: SQLite CHECK constraints can't be altered in place, so the table
#    has to be rebuilt with the wider constraint that allows 'doctor'.
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
current_ddl = cur.fetchone()[0]
if "'doctor'" not in current_ddl:
    cur.executescript("""
        CREATE TABLE users_new (
            user_id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            email VARCHAR(160) NOT NULL UNIQUE,
            role VARCHAR(20) NOT NULL CHECK (role IN ('admin','instructor','doctor')),
            password_hash VARCHAR(200) NOT NULL,
            created_at DATETIME
        );
        INSERT INTO users_new (user_id, name, email, role, password_hash, created_at)
            SELECT user_id, name, email, role, password_hash, created_at FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email);
    """)
    print("Rebuilt users table: role now accepts 'doctor'.")
else:
    print("users.role already accepts 'doctor', skipping.")

conn.commit()
conn.close()
print("Migration done.")
