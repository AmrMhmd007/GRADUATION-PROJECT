"""Resolve the SQLite file the standalone maintenance scripts (migrate_*.py,
seed_buildings.py, reset_admin_password.py) should operate on.

They previously hard-coded ``access_control.db`` in the current directory and
ignored ``DATABASE_URL``. With no ``DATABASE_URL`` (or the default one) the
result is unchanged: ``access_control.db`` relative to the current directory.
Non-SQLite URLs (e.g. PostgreSQL) are refused with a clear message instead of
silently touching the wrong database.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings  # noqa: E402  (also loads .env)

_PREFIX = "sqlite:///"


def sqlite_db_path() -> str:
    url = settings.DATABASE_URL
    if not url.startswith(_PREFIX):
        raise SystemExit(
            "This maintenance script only supports SQLite databases "
            "(DATABASE_URL must start with 'sqlite:///'). "
            "For PostgreSQL apply the schema changes with your own migration tooling."
        )
    path = url[len(_PREFIX):]
    return path[2:] if path.startswith("./") else path
