"""Adds N synthetic door rows (NODE01, NODE02, ...) to the seeded dev DB so
the Phase 6 concurrent-node load test has enough distinct door codes to
simulate a larger multi-node deployment than the 4 doors seed_db.py creates
for functional testing. Run from the backend/ directory."""
import sys

sys.path.insert(0, ".")
from app.database import SessionLocal
from app import models


def main(n: int):
    db = SessionLocal()
    try:
        for i in range(1, n + 1):
            code = f"NODE{i:02d}"
            if db.query(models.Door).filter(models.Door.code == code).first():
                continue
            db.add(models.Door(code=code, name=f"Load Test Door {i}",
                                building="Load Test Wing", fail_mode="secure",
                                online=False, locked=True))
        db.commit()
        print(f"Doors now in DB: {db.query(models.Door).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
