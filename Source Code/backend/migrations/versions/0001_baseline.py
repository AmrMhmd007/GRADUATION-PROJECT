"""Baseline: the schema as of Phase 1C (41 tables).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-15

WHAT THIS DOES
  Creates any of the 41 baseline tables that do not exist yet
  (CREATE TABLE IF NOT EXISTS semantics via checkfirst). It NEVER alters,
  drops, truncates or rewrites an existing table or row, so it is safe on:
    - an empty database  -> builds the whole schema;
    - a database the API already created with create_all() -> adds nothing,
      then Alembic records the revision;
    - a legacy SQLite database upgraded by the old migrate_*.py scripts.
  It does NOT add missing COLUMNS to existing tables: run `python3 schema_check.py`
  first, and apply the matching legacy migrate_*.py script for any reported
  missing column.

WHY THE TABLE LIST IS FROZEN
  The names below are fixed, so tables added to the models LATER are not
  created by this revision; they get their own revision. (Column definitions
  still come from the live models, which is why later revisions must be
  idempotent - see script.py.mako.)

DOWNGRADE
  Deliberately unsupported: reverting the baseline would mean dropping every
  table. Restore from a backup instead.
"""
from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_TABLES = frozenset("""
    faculties departments courses course_assignments operational_scopes admin_scopes buildings users
    credentials doors plugs door_assignments schedules access_windows access_events emergency_overrides
    alerts password_reset_requests power_readings energy_readings system_settings zones sensors
    occupancy_events devices automation_logs automation_rules hardware_health zone_schedules audit_logs
    event_investigations face_credentials occupancy_readings device_telemetry device_fault_alerts
    hvac_systems hvac_vents hvac_readings device_identities device_security_events device_message_nonces
""".split())


def upgrade() -> None:
    bind = op.get_bind()
    tables = [t for t in Base.metadata.sorted_tables if t.name in BASELINE_TABLES]
    missing_in_models = BASELINE_TABLES - {t.name for t in tables}
    if missing_in_models:
        raise RuntimeError(f"baseline tables not found in models: {sorted(missing_in_models)}")
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    raise NotImplementedError("The baseline cannot be downgraded (it would drop every table). "
                              "Restore from a backup.")
