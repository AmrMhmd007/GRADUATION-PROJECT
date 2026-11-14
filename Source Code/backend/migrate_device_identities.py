"""
One-time local migration for Phase 1B (device trust foundation): creates three
NEW tables - device_identities, device_security_events, device_message_nonces.
No existing table or row is touched.

Strictly, this script is optional: the API's start-up runs
Base.metadata.create_all(), which creates missing tables by itself (and is the
only path on PostgreSQL). It exists so an existing SQLite database can be
upgraded explicitly and reviewed, like the other migrate_*.py scripts.

Run from backend/ with the server stopped:
    python3 migrate_device_identities.py
Honours DATABASE_URL (SQLite only) through db_path.sqlite_db_path().

Idempotent: safe to run more than once. Rollback (loses only Phase 1B data):
    DROP TABLE device_message_nonces; DROP TABLE device_security_events;
    DROP TABLE device_identities;
"""
import sqlite3
from db_path import sqlite_db_path

conn = sqlite3.connect(sqlite_db_path())
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS device_identities (
        identity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id VARCHAR(64) NOT NULL UNIQUE,
        name VARCHAR(120),
        node_id VARCHAR(80),
        status VARCHAR(10) NOT NULL DEFAULT 'ACTIVE',
        secret_enc TEXT NOT NULL,
        secret_version INTEGER NOT NULL DEFAULT 1,
        secret_rotated_at TIMESTAMP,
        allowed_message_types TEXT NOT NULL DEFAULT '[]',
        allowed_zone_ids TEXT NOT NULL DEFAULT '[]',
        allowed_door_codes TEXT NOT NULL DEFAULT '[]',
        created_at TIMESTAMP,
        created_by_id INTEGER REFERENCES users(user_id),
        revoked_at TIMESTAMP,
        revoked_by_id INTEGER REFERENCES users(user_id),
        revoke_reason VARCHAR(200),
        last_seen_at TIMESTAMP,
        last_authenticated_at TIMESTAMP,
        CHECK (status IN ('ACTIVE','REVOKED'))
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_device_identities_device_id ON device_identities(device_id)")

cur.execute("""
    CREATE TABLE IF NOT EXISTS device_security_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at TIMESTAMP NOT NULL,
        event_type VARCHAR(32) NOT NULL,
        severity VARCHAR(10) NOT NULL DEFAULT 'WARNING',
        claimed_device_id VARCHAR(64),
        identity_id INTEGER REFERENCES device_identities(identity_id),
        topic VARCHAR(200),
        zone_id INTEGER,
        enforcement_mode VARCHAR(10) NOT NULL,
        action_taken VARCHAR(20) NOT NULL,
        detail VARCHAR(300),
        suppressed_count INTEGER NOT NULL DEFAULT 0
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_device_security_events_occurred_at ON device_security_events(occurred_at)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_device_security_events_event_type ON device_security_events(event_type)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_device_security_events_identity_id ON device_security_events(identity_id)")

cur.execute("""
    CREATE TABLE IF NOT EXISTS device_message_nonces (
        nonce_id INTEGER PRIMARY KEY AUTOINCREMENT,
        identity_id INTEGER NOT NULL REFERENCES device_identities(identity_id),
        nonce VARCHAR(64) NOT NULL,
        seen_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_device_nonce UNIQUE (identity_id, nonce)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_device_message_nonces_seen_at ON device_message_nonces(seen_at)")

conn.commit()
conn.close()
print("device_identities, device_security_events, device_message_nonces: ready")
