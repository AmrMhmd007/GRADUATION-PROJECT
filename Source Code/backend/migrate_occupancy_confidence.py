"""
One-time local migration for Phase 3 (confidence-scored occupancy fusion):
adds three new, purely additive nullable columns to `zones` —
occupancy_confidence, occupancy_evidence, occupancy_computed_at. None of
this changes occupancy_state or any existing column, and no existing row's
data is touched beyond the new columns defaulting to NULL until the next
automation pass fills them in.

Run from backend/ with the server stopped:
    python3 migrate_occupancy_confidence.py
Then restart: ./restart.sh

SQLite can ALTER TABLE ... ADD COLUMN for a plain nullable column without
the rename/recreate/copy/drop dance migrate_zones_and_automation.py needed
(that was only required there because door_id's NOT NULL constraint had to
change) — so this script is much simpler.

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(zones)").fetchall()}

added = []
if "occupancy_confidence" not in existing_cols:
    cur.execute("ALTER TABLE zones ADD COLUMN occupancy_confidence REAL")
    added.append("occupancy_confidence")
if "occupancy_evidence" not in existing_cols:
    cur.execute("ALTER TABLE zones ADD COLUMN occupancy_evidence TEXT")
    added.append("occupancy_evidence")
if "occupancy_computed_at" not in existing_cols:
    cur.execute("ALTER TABLE zones ADD COLUMN occupancy_computed_at TIMESTAMP")
    added.append("occupancy_computed_at")

conn.commit()
conn.close()

if added:
    print(f"Added columns to zones: {', '.join(added)}")
else:
    print("zones already has all Phase 3 columns — nothing to do.")
