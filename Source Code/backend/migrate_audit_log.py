"""
One-time local migration for the final-hardening-pass centralized audit log
(Phase 6): a single new, independent table. Nothing existing is touched —
no other table gains a column, nothing is renamed, no data is modified.

Run from backend/ with the server stopped:
    python3 migrate_audit_log.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL,
        actor_user_id INTEGER REFERENCES users(user_id),
        actor_email VARCHAR(160),
        actor_role VARCHAR(20),
        action VARCHAR(40) NOT NULL,
        resource_type VARCHAR(40) NOT NULL,
        resource_id INTEGER,
        resource_label VARCHAR(160),
        result VARCHAR(10) NOT NULL DEFAULT 'success',
        description VARCHAR(500),
        CHECK (result IN ('success','failure'))
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs (timestamp)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_resource_type ON audit_logs (resource_type)")

conn.commit()
conn.close()
print("audit_logs table ready.")
