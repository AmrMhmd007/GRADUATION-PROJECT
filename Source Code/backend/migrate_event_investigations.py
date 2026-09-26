"""
One-time local migration for Stage C (Investigation & Evidence): a single
new, independent table — event_investigations. Nothing existing is touched.

Run from backend/ with the server stopped:
    python3 migrate_event_investigations.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS event_investigations (
        investigation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL UNIQUE REFERENCES access_events(event_id),
        status VARCHAR(20) NOT NULL DEFAULT 'open',
        note VARCHAR(1000),
        updated_by_id INTEGER REFERENCES users(user_id),
        updated_at TIMESTAMP,
        CHECK (status IN ('open','under_review','resolved'))
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_event_investigations_event_id ON event_investigations (event_id)")

conn.commit()
conn.close()
print("event_investigations table ready.")
