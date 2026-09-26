"""
Feature #8 — Emergency Access / Override: creates the `emergency_overrides`
table. A controlled, time-bounded, reasoned, fully audited alternative to
the plain instant lock/unlock in routers/doors.py::override_door — see
EmergencyOverride's docstring in models.py for the full design rationale
(why this is a separate concept from DoorAssignment/AccessWindow, and how
scope authorization reuses the existing AdminScope/OperationalScope system
rather than introducing a second one).

Does not touch any existing data or tables. Purely additive.

Run from backend/ with the server stopped:
    python3 migrate_emergency_overrides.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS emergency_overrides (
        override_id INTEGER PRIMARY KEY AUTOINCREMENT,
        door_id INTEGER NOT NULL REFERENCES doors(door_id),
        operational_scope_id INTEGER REFERENCES operational_scopes(scope_id),
        action VARCHAR(10) NOT NULL,
        reason VARCHAR(500) NOT NULL,
        created_by_id INTEGER NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        revoked_at TIMESTAMP,
        revoked_by_id INTEGER REFERENCES users(user_id),
        CHECK (action IN ('lock','unlock')),
        CHECK (status IN ('ACTIVE','EXPIRED','REVOKED'))
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_emergency_overrides_door_id ON emergency_overrides (door_id)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_emergency_overrides_status ON emergency_overrides (status)")

conn.commit()
conn.close()
print("emergency_overrides table ready.")
