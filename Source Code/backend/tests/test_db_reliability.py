"""Phase 1C: migration baseline, schema check, PostgreSQL DDL portability,
FaceCredential default, and encryption-key configuration validation.

The Alembic tests use throw-away SQLite files under pytest's tmp_path and never
touch the shared test database. PostgreSQL is NOT executed here: the
portability test only COMPILES DDL for the PostgreSQL dialect.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import config, models
from app.config import settings
from app.database import Base
from app.services import device_auth_service as das

BACKEND = Path(__file__).resolve().parent.parent


def _alembic_cfg():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setattr(settings, "DATABASE_URL", url)      # migrations/env.py reads this at run time
    eng = create_engine(url)
    yield eng
    eng.dispose()


def _version(eng):
    with eng.connect() as c:
        return [r[0] for r in c.execute(text("select version_num from alembic_version"))]


def _compare(eng):
    import importlib
    sc = importlib.import_module("schema_check")
    return sc.compare(eng)


# ------------------------------------------------------------ migration baseline
def test_baseline_builds_full_schema_on_empty_database_and_is_repeatable(tmp_db):
    command.upgrade(_alembic_cfg(), "head")
    assert _version(tmp_db) == ["0001_baseline"]
    r = _compare(tmp_db)
    assert r["missing_tables"] == [] and r["missing_columns"] == {}
    command.upgrade(_alembic_cfg(), "head")                       # second run: no change, no error
    assert _version(tmp_db) == ["0001_baseline"]


def test_baseline_on_existing_database_preserves_data_and_adds_only_missing_tables(tmp_db):
    Base.metadata.create_all(tmp_db)
    from sqlalchemy.orm import sessionmaker
    with sessionmaker(bind=tmp_db)() as s:
        u = models.User(name="Keep", email="keep@x.edu", role="doctor", password_hash="h")
        s.add(u)
        s.commit()
        s.add(models.FaceCredential(user_id=u.user_id, status="ENROLLED", template_enc="enc", template_dim=8,
                                    enrolled_source="REAL"))
        s.commit()
    for t in (models.DeviceMessageNonce, models.DeviceSecurityEvent, models.DeviceIdentity):
        t.__table__.drop(tmp_db)                                  # mimic a pre-Phase-1B database
    assert set(_compare(tmp_db)["missing_tables"]) == {"device_identities", "device_security_events",
                                                       "device_message_nonces"}
    command.upgrade(_alembic_cfg(), "head")
    assert _compare(tmp_db)["missing_tables"] == []
    with tmp_db.connect() as c:
        assert c.execute(text("select count(*) from users")).scalar() == 1
        # an existing REAL credential is neither downgraded nor deleted
        assert c.execute(text("select enrolled_source, status from face_credentials")).fetchall() == [
            ("REAL", "ENROLLED")]


def test_baseline_downgrade_is_refused_and_changes_nothing(tmp_db):
    command.upgrade(_alembic_cfg(), "head")
    with pytest.raises(NotImplementedError):
        command.downgrade(_alembic_cfg(), "base")
    assert _version(tmp_db) == ["0001_baseline"]
    assert _compare(tmp_db)["missing_tables"] == []


def test_schema_check_reports_missing_columns_and_tables(tmp_db):
    Base.metadata.create_all(tmp_db)
    with tmp_db.begin() as c:
        c.execute(text("alter table zones drop column capacity"))
        c.execute(text("drop table hvac_readings"))
    r = _compare(tmp_db)
    assert r["missing_columns"] == {"zones": ["capacity"]} and r["missing_tables"] == ["hvac_readings"]


def test_baseline_table_list_matches_the_models():
    """If you add a model, add an Alembic revision for it (and extend this
    check). This keeps create_all and the migration history from drifting."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("baseline", BACKEND / "migrations/versions/0001_baseline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.BASELINE_TABLES) == {t.name for t in Base.metadata.sorted_tables}


# ------------------------------------------------------------ PostgreSQL portability (compile only)
def test_all_tables_compile_for_postgresql_dialect():
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "CREATE TABLE" in ddl
        for idx in table.indexes:
            str(CreateIndex(idx).compile(dialect=dialect))


def test_no_table_has_a_database_level_default_that_differs_between_dialects():
    """Defaults are Python-side; a server default added later must be reviewed for both dialects."""
    sd = [(t.name, c.name) for t in Base.metadata.sorted_tables for c in t.columns if c.server_default is not None]
    assert sd == [], f"server defaults present - review for SQLite/PostgreSQL parity: {sd}"


# ------------------------------------------------------------ FaceCredential safety
def test_face_credential_orm_default_is_simulated(db_session):
    u = models.User(name="F", email="f@x.edu", role="doctor", password_hash="h")
    db_session.add(u)
    db_session.commit()
    row = models.FaceCredential(user_id=u.user_id, status="ENROLLED", template_enc="e", template_dim=8)
    db_session.add(row)
    db_session.commit()
    assert row.enrolled_source == "SIMULATED"


def test_face_credential_has_no_database_default_so_no_schema_migration_is_needed(db_session):
    cols = {c["name"]: c for c in inspect(db_session.get_bind()).get_columns("face_credentials")}
    assert cols["enrolled_source"]["default"] is None


# ------------------------------------------------------------ encryption configuration
def test_valid_unset_and_invalid_encryption_keys(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", "")
    assert config.encryption_key_problem() is None
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert config.encryption_key_problem() is None
    bad = "definitely-not-a-key-TOPSECRET"
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", bad)
    msg = config.encryption_key_problem()
    assert msg and "CREDENTIAL_ENCRYPTION_KEY" in msg and bad not in msg
    assert all(bad not in w for w in config.insecure_configuration_warnings())


def test_invalid_key_stops_startup_with_a_clear_secret_free_error():
    env = {**os.environ, "CREDENTIAL_ENCRYPTION_KEY": "definitely-not-a-key-TOPSECRET", "DISABLE_MQTT": "true",
           "DATABASE_URL": "sqlite://"}
    p = subprocess.run([sys.executable, "-B", "-c", "import app.crypto"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    assert "not a valid Fernet key" in p.stderr
    assert "TOPSECRET" not in p.stderr and "TOPSECRET" not in p.stdout


def test_missing_key_still_starts_with_warnings_and_no_device_registry_needed(monkeypatch):
    env = {k: v for k, v in os.environ.items() if k not in ("CREDENTIAL_ENCRYPTION_KEY", "CREDENTIAL_INDEX_KEY")}
    env.update({"DISABLE_MQTT": "true", "DATABASE_URL": "sqlite://"})
    p = subprocess.run([sys.executable, "-B", "-c", "import app.crypto, app.main"], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    monkeypatch.setattr(settings, "CREDENTIAL_ENCRYPTION_KEY", "")
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("CREDENTIAL_INDEX_KEY", raising=False)
    w = " ".join(config.insecure_configuration_warnings())
    assert "CREDENTIAL_ENCRYPTION_KEY is unset" in w and "CREDENTIAL_INDEX_KEY is unset" in w


def test_mqtt_auth_mode_warnings(monkeypatch):
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "enforced")
    assert any("MQTT_AUTH_MODE" in w for w in config.insecure_configuration_warnings())
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "off")
    assert any("not being checked" in w for w in config.insecure_configuration_warnings())
    monkeypatch.setattr(settings, "MQTT_AUTH_MODE", "warn")
    assert not any("MQTT_AUTH_MODE" in w for w in config.insecure_configuration_warnings())


def test_secret_health_counts_undecryptable_secrets_without_exposing_them(client, admin_token, db_session):
    H = {"Authorization": f"Bearer {admin_token}"}
    r = client.post("/api/device-identities", headers=H, json={
        "device_id": "esp-h1", "message_types": ["health"], "zone_ids": [], "door_codes": []})
    secret = r.json()["secret"]
    h = das.secret_health(db_session)
    assert h == {"active_identities": 1, "undecryptable": 0}
    ident = db_session.query(models.DeviceIdentity).one()
    ident.secret_enc = "gAAAAA-corrupted-or-encrypted-under-another-key"
    db_session.commit()
    h = das.secret_health(db_session)
    assert h == {"active_identities": 1, "undecryptable": 1} and secret not in str(h)


# ------------------------------------------------------------ which database is the suite really on?
def test_suite_runs_on_the_requested_database(db_session):
    """Guards against the PostgreSQL CI job silently running on SQLite. CI sets
    EXPECT_DB_DIALECT; locally it defaults to the dialect implied by
    TEST_DATABASE_URL (or sqlite when that is unset)."""
    from app.database import engine as app_engine
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    default = url.split(":", 1)[0].split("+", 1)[0] if url else "sqlite"
    expected = os.environ.get("EXPECT_DB_DIALECT") or default
    assert db_session.get_bind().dialect.name == expected
    assert app_engine.dialect.name == expected       # the application's own engine, not just the test one
