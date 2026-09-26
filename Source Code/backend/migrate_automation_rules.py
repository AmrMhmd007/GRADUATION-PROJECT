"""
One-time local migration for Phase 4 (database-backed automation rules):
creates the new `automation_rules` table and seeds exactly one row — a
building-wide (zone_id NULL) default rule that reproduces this project's
pre-Phase-4 hardcoded behavior exactly: any zone confirmed empty past its
schedule shuts down its NON_CRITICAL devices, no confidence floor, no extra
grace period beyond whatever the zone's own ZoneSchedule already specifies.

This means every existing zone keeps behaving identically after this
migration runs — the rule is now visible and editable (enable/disable,
raise minimum_confidence, add a zone-specific override with a different
priority) through /api/automation/rules, where before it was invisible,
hardcoded Python.

Run from backend/ with the server stopped:
    python3 migrate_automation_rules.py
Then restart: ./restart.sh

Idempotent: safe to run more than once (checks for an existing row with the
same name before inserting).
"""
import json
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS automation_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(120) NOT NULL,
        zone_id INTEGER REFERENCES zones(zone_id),
        enabled BOOLEAN NOT NULL DEFAULT 1,
        priority INTEGER NOT NULL DEFAULT 0,
        conditions TEXT NOT NULL,
        actions TEXT NOT NULL,
        grace_period_minutes INTEGER,
        verification_required BOOLEAN NOT NULL DEFAULT 1,
        minimum_confidence REAL NOT NULL DEFAULT 0.0,
        schedule_id INTEGER REFERENCES zone_schedules(schedule_id),
        criticality_restriction VARCHAR(20) NOT NULL DEFAULT 'NON_CRITICAL_ONLY',
        created_at TIMESTAMP,
        CHECK (criticality_restriction IN ('NON_CRITICAL_ONLY'))
    )
""")

DEFAULT_RULE_NAME = "Default: shut down non-critical devices once confirmed empty"

existing = cur.execute(
    "SELECT rule_id FROM automation_rules WHERE name = ?", (DEFAULT_RULE_NAME,)
).fetchone()

if existing is None:
    cur.execute(
        """
        INSERT INTO automation_rules
            (name, zone_id, enabled, priority, conditions, actions,
             grace_period_minutes, verification_required, minimum_confidence,
             schedule_id, criticality_restriction, created_at)
        VALUES (?, NULL, 1, 0, ?, ?, NULL, 1, 0.0, NULL, 'NON_CRITICAL_ONLY', CURRENT_TIMESTAMP)
        """,
        (
            DEFAULT_RULE_NAME,
            json.dumps({"trigger": "CONFIRMED_EMPTY"}),
            json.dumps({"action": "SHUTDOWN_NON_CRITICAL"}),
        ),
    )
    conn.commit()
    print(f"Seeded default automation rule: '{DEFAULT_RULE_NAME}'")
else:
    print("Default automation rule already exists — nothing to do.")

conn.close()
