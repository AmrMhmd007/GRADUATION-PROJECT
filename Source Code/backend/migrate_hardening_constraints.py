"""
One-time local migration for the mandatory hardening constraints added
mid-way through the software-groundwork phases: real-vs-simulated data
provenance, and the automation audit trail's full decision context.

Adds (all nullable, purely additive — no existing column or row changes):

  sensors.data_source          VARCHAR(10)   'REAL' | 'SIMULATED' | NULL
  devices.power_source         VARCHAR(10)   'REAL' | 'SIMULATED' | NULL
  devices.last_command_status  VARCHAR(20)   COMMAND_SENT | COMMAND_FAILED |
                                              COMMAND_ACKNOWLEDGED | STATE_CONFIRMED
  devices.last_command_at      TIMESTAMP
  automation_logs.trigger              VARCHAR(30)
  automation_logs.confidence           REAL
  automation_logs.evidence_snapshot    TEXT (JSON)
  automation_logs.matched_rule_id      INTEGER REFERENCES automation_rules(rule_id)
  automation_logs.matched_rule_name    VARCHAR(120)
  automation_logs.requested_action     VARCHAR(30)
  automation_logs.blocked_actions      TEXT (JSON)

Run from backend/ with the server stopped:
    python3 migrate_hardening_constraints.py
Then restart: ./restart.sh

Idempotent: safe to run more than once.
"""
import sqlite3

conn = sqlite3.connect("access_control.db")
cur = conn.cursor()

added = []


def _add(table, column, ddl):
    cols = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        added.append(f"{table}.{column}")


_add("sensors", "data_source", "VARCHAR(10)")
_add("devices", "power_source", "VARCHAR(10)")
_add("devices", "last_command_status", "VARCHAR(20)")
_add("devices", "last_command_at", "TIMESTAMP")
_add("automation_logs", "trigger", "VARCHAR(30)")
_add("automation_logs", "confidence", "REAL")
_add("automation_logs", "evidence_snapshot", "TEXT")
_add("automation_logs", "matched_rule_id", "INTEGER REFERENCES automation_rules(rule_id)")
_add("automation_logs", "matched_rule_name", "VARCHAR(120)")
_add("automation_logs", "requested_action", "VARCHAR(30)")
_add("automation_logs", "blocked_actions", "TEXT")

conn.commit()
conn.close()

if added:
    print(f"Added columns: {', '.join(added)}")
else:
    print("All hardening-constraint columns already exist — nothing to do.")
