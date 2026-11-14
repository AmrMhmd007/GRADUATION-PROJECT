"""
READ-ONLY comparison of the live database schema with the SQLAlchemy models.
Changes nothing. Use it before `alembic stamp`/`upgrade` on an existing
database, and after deploying a new version.

Run from backend/:  python3 schema_check.py
Honours DATABASE_URL (SQLite or PostgreSQL).

Exit code 0 = nothing missing; 1 = missing tables or columns (details printed);
extra tables/columns present only in the database are reported but are not an
error (they may belong to a newer or older version).
Checks table and column NAMES only (not types, constraints or indexes).
"""
import sys

from sqlalchemy import inspect

from app import models  # noqa: F401
from app.database import Base, engine


def compare(bind) -> dict:
    insp = inspect(bind)
    live = set(insp.get_table_names())
    expected = {t.name: t for t in Base.metadata.sorted_tables}
    report = {"missing_tables": sorted(set(expected) - live),
              "extra_tables": sorted(live - set(expected) - {"alembic_version"}),
              "missing_columns": {}, "extra_columns": {}}
    for name, table in expected.items():
        if name not in live:
            continue
        have = {c["name"] for c in insp.get_columns(name)}
        want = {c.name for c in table.columns}
        if want - have:
            report["missing_columns"][name] = sorted(want - have)
        if have - want:
            report["extra_columns"][name] = sorted(have - want)
    return report


def main() -> int:
    r = compare(engine)
    print(f"database: {engine.url.render_as_string(hide_password=True)}")
    print(f"missing tables : {r['missing_tables'] or 'none'}")
    print(f"missing columns: {r['missing_columns'] or 'none'}")
    print(f"extra tables   : {r['extra_tables'] or 'none'}")
    print(f"extra columns  : {r['extra_columns'] or 'none'}")
    return 1 if (r["missing_tables"] or r["missing_columns"]) else 0


if __name__ == "__main__":
    sys.exit(main())
