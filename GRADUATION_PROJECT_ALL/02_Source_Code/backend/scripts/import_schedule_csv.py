"""
Mock registrar timetable importer (Phase 3 scope note).

The real registrar system's export format is unknown at this stage of the
project (see the System Design Document's open questions), so this script
defines a plausible CSV shape — door_code, day_of_week, start_time,
end_time, course_id — and imports it into the schedules table. When the
real integration is scoped, only this file should need to change; the
schedules table and API are already shaped to receive this data.

Usage (from the backend/ directory):
    python -m scripts.import_schedule_csv scripts/sample_timetable.csv
"""
import csv
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app import models


def parse_time(value: str) -> datetime.time:
    hour, minute = value.strip().split(":")
    return datetime.time(int(hour), int(minute))


def run(csv_path: str):
    db = SessionLocal()
    imported, skipped = 0, 0
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                door = db.query(models.Door).filter(models.Door.code == row["door_code"]).first()
                if not door:
                    print(f"  skip: unknown door code '{row['door_code']}'")
                    skipped += 1
                    continue
                schedule = models.Schedule(
                    door_id=door.door_id,
                    day_of_week=int(row["day_of_week"]),
                    start_time=parse_time(row["start_time"]),
                    end_time=parse_time(row["end_time"]),
                    course_id=row.get("course_id") or None,
                )
                db.add(schedule)
                imported += 1
        db.commit()
        print(f"Imported {imported} schedule rows, skipped {skipped}.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.import_schedule_csv <path_to_csv>")
        sys.exit(1)
    run(sys.argv[1])
