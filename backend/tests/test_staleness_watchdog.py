"""
Phase 7 — tests for the door staleness watchdog (app/services/
staleness_watchdog.py), added after full system integration testing found
that a door's `online` flag never went back to False if the process
reporting it (a direct node, or the Building Gateway relaying several
RS-485 nodes) died without a clean MQTT disconnect. See that module's
docstring for the full story.

These call sweep_once() directly against a real DB session rather than
waiting on the background thread's timer, so the test suite stays fast and
deterministic.
"""
import datetime

from app import models
from app.services import staleness_watchdog


def _set_last_seen(db, door_id, when):
    door = db.query(models.Door).filter(models.Door.door_id == door_id).first()
    door.last_seen = when
    db.commit()


def test_stale_online_door_gets_marked_offline(db_session):
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    _set_last_seen(db_session, door.door_id, datetime.datetime.utcnow() - datetime.timedelta(minutes=5))

    from app.config import settings
    assert settings.DOOR_STALE_AFTER_SECONDS < 300, "test assumes the default threshold is under 5 minutes"

    marked = staleness_watchdog.sweep_once(db_session)
    assert "A101" in marked

    db_session.refresh(door)
    assert door.online is False


def test_recently_seen_door_is_left_alone(db_session):
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    _set_last_seen(db_session, door.door_id, datetime.datetime.utcnow())

    marked = staleness_watchdog.sweep_once(db_session)
    assert "A101" not in marked

    db_session.refresh(door)
    assert door.online is True


def test_door_with_no_last_seen_is_not_flagged(db_session):
    # A door that has never reported in at all (last_seen still NULL, e.g.
    # freshly seeded for a demo) is a different situation from one that
    # WAS reporting and stopped — the sweep only acts on the latter.
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    assert door.last_seen is None
    assert door.online is True

    marked = staleness_watchdog.sweep_once(db_session)
    assert "A101" not in marked

    db_session.refresh(door)
    assert door.online is True


def test_already_offline_door_is_not_reported_again(db_session):
    door = db_session.query(models.Door).filter(models.Door.code == "A101").first()
    door.online = False
    door.last_seen = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    db_session.commit()

    marked = staleness_watchdog.sweep_once(db_session)
    assert marked == []
