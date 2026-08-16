"""
Populate a fresh database with sample data so the API is testable without a
running door node: one admin user, a few doors, and a couple of credentials.

Run from the backend/ directory:  python -m scripts.seed_db
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, engine, SessionLocal
from app import models, security, crypto


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.User).count() > 0:
            print("Database already has data — skipping seed.")
            return

        admin = models.User(
            name="Admin User", email="admin@example.edu", role="admin",
            password_hash=security.hash_password("admin123"),
        )
        instructor = models.User(
            name="Dr. Instructor", email="instructor@example.edu", role="instructor",
            password_hash=security.hash_password("instructor123"),
        )
        db.add_all([admin, instructor])
        db.flush()

        doors = [
            models.Door(code="A101", name="Room A101", building="Building A", fail_mode="secure", online=True, locked=True),
            models.Door(code="A102", name="Room A102", building="Building A", fail_mode="secure", online=True, locked=True),
            models.Door(code="MAIN", name="Main Entrance", building="Building A", fail_mode="safe", online=True, locked=False),
            models.Door(code="SRV1", name="Server Room", building="Building B", fail_mode="secure", online=True, locked=True),
        ]
        db.add_all(doors)
        db.flush()

        # card_uid is encrypted at rest (Phase 5) — encrypt here rather than
        # storing the plaintext demo UIDs directly.
        creds = [
            models.Credential(
                user_id=admin.user_id,
                card_uid=crypto.encrypt_uid("DEADBEEF"),
                card_uid_index=crypto.uid_index("DEADBEEF"),
                active=True,
            ),
            models.Credential(
                user_id=instructor.user_id,
                card_uid=crypto.encrypt_uid("12345678"),
                card_uid_index=crypto.uid_index("12345678"),
                active=True,
            ),
        ]
        db.add_all(creds)
        db.commit()

        print("Seeded: 2 users, 4 doors, 2 credentials.")
        print("Login with admin@example.edu / admin123 or instructor@example.edu / instructor123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
