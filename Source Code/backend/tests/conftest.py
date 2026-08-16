import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force an isolated in-memory-per-file SQLite DB and disable MQTT before any
# app module is imported, so tests never touch the developer's real .env.
os.environ["DATABASE_URL"] = "sqlite:///./test_access_control.db"
os.environ["DISABLE_MQTT"] = "true"
os.environ["JWT_SECRET"] = "test-secret"

from app.main import app  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app import models, security, crypto, rate_limit  # noqa: E402

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_access_control.db"

engine = create_engine("sqlite:///./test_access_control.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def fresh_db():
    rate_limit.reset_all()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    admin = models.User(name="Admin", email="admin@example.edu", role="admin",
                         password_hash=security.hash_password("admin123"))
    instructor = models.User(name="Instructor", email="instructor@example.edu", role="instructor",
                              password_hash=security.hash_password("instructor123"))
    db.add_all([admin, instructor])
    db.flush()
    door = models.Door(code="A101", name="Room A101", building="Building A", fail_mode="secure",
                        online=True, locked=True)
    db.add(door)
    db.flush()
    cred = models.Credential(
        user_id=admin.user_id,
        card_uid=crypto.encrypt_uid("DEADBEEF"),
        card_uid_index=crypto.uid_index("DEADBEEF"),
        active=True,
    )
    db.add(cred)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    rate_limit.reset_all()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_token(client):
    resp = client.post("/api/auth/login", json={"email": "admin@example.edu", "password": "admin123"})
    return resp.json()["access_token"]


@pytest.fixture
def instructor_token(client):
    resp = client.post("/api/auth/login", json={"email": "instructor@example.edu", "password": "instructor123"})
    return resp.json()["access_token"]


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
