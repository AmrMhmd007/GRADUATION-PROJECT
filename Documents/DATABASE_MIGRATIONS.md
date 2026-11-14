# Database schema management and migrations

Status (Phase 1C): an Alembic **baseline** exists. It has been exercised on
temporary SQLite databases only. It has **not** been run against PostgreSQL by
anyone yet; the CI job that will do so exists but has never executed.

## How the schema is managed today

1. On start-up the API runs `Base.metadata.create_all()`. That creates tables
   that are missing. It never alters an existing table.
2. Column changes to existing tables were applied by 22 hand-written,
   idempotent, **SQLite-only** `migrate_*.py` scripts in `backend/`.
3. New in Phase 1C: Alembic, with a baseline revision `0001_baseline`.
   Nothing runs it automatically; it is a command you run.

Why Alembic with a conservative baseline (the recommendation): existing
databases are at unknown, mixed levels of the old scripts and carry real data,
so a baseline that "rebuilds" the schema would be unsafe. This baseline only
creates tables that do not exist (`checkfirst`), never alters, drops or
rewrites anything, and is therefore safe on an empty database, on one the API
already created, and on a legacy database. Missing **columns** are reported by
`schema_check.py`, not guessed at.

## Commands (run from `Source Code/backend/`)

Set `DATABASE_URL` first if you are not using the default SQLite file.

    python3 schema_check.py
    python3 -m alembic upgrade head
    python3 -m alembic current

- `schema_check.py` is read-only. Exit code 1 means a table or column the code
  expects is missing. It compares names only, not types, constraints or indexes.
- `alembic upgrade head` on a new empty database builds the whole schema.
- On an existing database it adds only missing tables, then records the
  revision. Run `schema_check.py` before and after.
- Running it twice is safe.

### Upgrading an existing SQLite database

1. Stop the API and **back up the database file.**
2. `python3 schema_check.py`.
3. If columns are reported missing, apply the matching legacy script (for
   example `migrate_cyber_physical_upgrade.py`) and re-check.
4. `python3 -m alembic upgrade head`, then `python3 schema_check.py` again.

### PostgreSQL

Install `requirements-postgres.txt`, point `DATABASE_URL` at an empty
database and run `python3 -m alembic upgrade head`. The legacy
`migrate_*.py` scripts refuse non-SQLite URLs. A PostgreSQL database that was
created by an older version of the code has no equivalent of those scripts;
use Alembic revisions written for it.

## Writing the next migration

Add a new revision under `migrations/versions/` (`python3 -m alembic revision -m "..."`).
Rules (also in `migrations/script.py.mako`):

- Make every operation idempotent: inspect the live schema before adding a
  table, column or index, because a database may already contain the change.
- Do not delete or rewrite data without an explicit, reviewed data step.
- Provide a `downgrade()` whenever it is safe.
- A new model needs its own revision; `test_baseline_table_list_matches_the_models`
  fails to remind you.

## Rollback limits

- The baseline cannot be downgraded (it would drop everything). Restore from a
  backup.
- Legacy `migrate_*.py` scripts have no rollback.
- Only SQLite and the baseline have been exercised. SQLite cannot alter most
  columns in place; Alembic's batch mode is enabled for it but has not been
  needed yet.

## FaceCredential source and existing REAL credentials

- The model default for `face_credentials.enrolled_source` changed from `REAL`
  to `SIMULATED`. This is a Python-side default only: no database has a DDL
  default for the column (verified), so **no schema migration is needed** and
  no existing row is touched.
- Rows already marked `REAL` are **not** downgraded, deleted or rewritten.
- Before Phase 1A, any logged-in user could submit their own embedding and have
  it recorded as `REAL`. Review existing rows with the read-only tool:

        python3 review_face_credentials.py

  It prints metadata only (never a template). Pay most attention to rows that
  are `REAL` and still `ENROLLED` (usable at the door), especially
  `self_enrolled=yes`, which is how the old API recorded them. Options per row,
  decided by an administrator: leave it, or revoke it through
  `POST /api/face/users/{user_id}/revoke` (audited) and have the person
  re-enrol once the trusted pipeline exists. There is no automatic action.
- Face ID real enrolment is still not implemented.

## What was and was not tested

Executed locally (SQLite): empty database upgrade, repeat upgrade, upgrade of a
populated database missing three tables (data and a `REAL` credential kept),
downgrade refusal, schema-check detection of missing columns/tables, and
offline SQL generation. PostgreSQL: DDL for every table compiles for the
PostgreSQL dialect, which proves nothing about execution. The `backend-postgres`
CI job (migrations, then the whole test-suite) is **written but has not run**.
