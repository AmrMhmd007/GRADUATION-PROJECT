"""
Feature #5 — Schedule-Derived Access Authorization: creates the
`access_windows` table (recurring weekly windows AND one-off/temporary
windows with automatic expiration, per user+door — see AccessWindow's
docstring in models.py for how this differs from DoorAssignment and the
legacy door-wide Schedule) plus two additive, nullable columns on the
existing `access_events` table (user_id, evidence_snapshot) so a
schedule-derived authorization check can be logged in the SAME audit table
physical RFID access events already use, instead of a second logging
system.

Does not touch any existing data. Purely additive.

Run from backend/ with the server stopped:
    python3 migrate_access_windows.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS access_windows (
        access_window_id INTEGER PRIMARY KEY AUTOINCREMENT,
        door_id INTEGER NOT NULL REFERENCES doors(door_id),
        user_id INTEGER NOT NULL REFERENCES users(user_id),
        course_id INTEGER REFERENCES courses(course_id),
        recurring BOOLEAN NOT NULL DEFAULT 0,
        day_of_week SMALLINT,
        start_time TIME,
        end_time TIME,
        valid_from TIMESTAMP,
        valid_until TIMESTAMP,
        start_at TIMESTAMP,
        end_at TIMESTAMP,
        reason VARCHAR(255),
        created_by_id INTEGER REFERENCES users(user_id),
        created_at TIMESTAMP
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_access_windows_door_id ON access_windows (door_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_access_windows_user_id ON access_windows (user_id)")


def _add_column(table, column, ddl):
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"  + {table}.{column}")
    else:
        print(f"  = {table}.{column} already present")


print("Adding additive columns:")
_add_column("access_events", "user_id", "user_id INTEGER REFERENCES users(user_id)")
_add_column("access_events", "evidence_snapshot", "evidence_snapshot TEXT")

conn.commit()
conn.close()
print("access_windows table + access_events columns ready.")
