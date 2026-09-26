"""
Tests for the Smart Building automation engine (app/services/
automation_engine.py). Calls process_zone_once()/building_occupancy_state()
directly against a real DB session rather than waiting on the background
timer, following the same pattern as test_staleness_watchdog.py.

The single most important behavior under test, repeated throughout: an
empty or stale sensor reading is NEVER enough on its own to shut anything
down — occupancy must be confirmed fresh, after a full verification window,
with no re-occupancy in between. See automation_engine.py's own docstring
for the full SENSE->ANALYZE->VERIFY->DECIDE->ACT->MONITOR cycle this tests.
"""
import datetime

from app import models
from app.services import automation_engine


def _zone(db, name="Test Zone", zone_type="CLASSROOM"):
    zone = models.Zone(name=name, zone_type=zone_type, occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _sensor(db, zone_id, occupied):
    sensor = models.Sensor(
        zone_id=zone_id, sensor_type="PIR", status="online",
        occupancy_state=occupied, last_seen=datetime.datetime.utcnow(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def _device(db, zone_id, name, type_, criticality, status=False, current_power=None,
            automatic_control_enabled=True):
    device = models.Device(
        zone_id=zone_id, name=name, type=type_, criticality=criticality,
        status=status, current_power=current_power,
        automatic_control_enabled=automatic_control_enabled,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _open_schedule(db, zone_id, verification_minutes=5):
    now = datetime.datetime.now()
    db.add(models.ZoneSchedule(
        zone_id=zone_id, day_of_week=None,
        open_time=(now - datetime.timedelta(hours=1)).time(),
        close_time=(now + datetime.timedelta(hours=2)).time(),
        grace_minutes=10, verification_minutes=verification_minutes,
    ))
    db.commit()


def _closed_schedule(db, zone_id, verification_minutes=5):
    # "closed" = close_time already passed (with zero grace), so the zone is
    # firmly past its scheduled hours as far as the engine is concerned.
    now = datetime.datetime.now()
    db.add(models.ZoneSchedule(
        zone_id=zone_id, day_of_week=None,
        open_time=(now - datetime.timedelta(hours=2)).time(),
        close_time=(now - datetime.timedelta(minutes=2)).time(),
        grace_minutes=0, verification_minutes=verification_minutes,
    ))
    db.commit()


def test_fresh_occupied_signal_keeps_zone_occupied(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=True)

    automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    assert zone.occupancy_state == "OCCUPIED"


def test_no_fresh_signal_is_unknown_not_empty(db_session):
    # No sensors, no door link at all — this must never be treated as "empty".
    zone = _zone(db_session)
    _closed_schedule(db_session, zone.zone_id)

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    assert zone.occupancy_state == "UNKNOWN"
    assert zone.verification_started_at is None
    assert result is None


def test_empty_during_open_hours_does_not_start_verification(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _open_schedule(db_session, zone.zone_id)

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    assert zone.occupancy_state == "EMPTY"
    assert zone.verification_started_at is None
    assert result is None


# ---------------------------------------------------------------------------
# get_schedule_state — midnight-wrap fix regression coverage.
#
# get_schedule_state() used to be documented as "does not handle a schedule
# that crosses midnight" — comparing bare time() values with open_time <=
# t < close_time silently misreads an overnight window (e.g. open 22:00,
# close 02:00) as CLOSED whenever `now` falls after midnight but before
# close_time, and this was also the exact root cause of
# test_empty_during_open_hours_does_not_start_verification's flakiness
# (its `_open_schedule` helper builds a window relative to `now`, which
# wraps past midnight whenever the suite runs late in the evening). Fixed
# at the source in automation_engine.get_schedule_state; these tests pin
# explicit `now` values so they're deterministic regardless of what time it
# actually is when the suite runs — no reliance on local wall-clock luck.
# ---------------------------------------------------------------------------
def _schedule_row(db, zone_id, open_time, close_time, grace_minutes=10, verification_minutes=5):
    db.add(models.ZoneSchedule(
        zone_id=zone_id, day_of_week=None,
        open_time=open_time, close_time=close_time,
        grace_minutes=grace_minutes, verification_minutes=verification_minutes,
    ))
    db.commit()


def test_schedule_state_normal_daytime_window(db_session):
    zone = _zone(db_session)
    _schedule_row(db_session, zone.zone_id, datetime.time(8, 0), datetime.time(18, 0))

    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 5, 12, 0))
    assert state == "OPEN"

    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 5, 6, 0))
    assert state == "CLOSED"

    # Just past close_time, but still within the grace window.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 5, 18, 5))
    assert state == "OPEN"

    # Well past close_time and its grace period.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 5, 19, 0))
    assert state == "CLOSED"


def test_schedule_state_midnight_crossing_window(db_session):
    """An overnight schedule (open 22:00, close 02:00) — the core fix. Open
    late evening, open past midnight into the early morning, closed during
    the daytime gap."""
    zone = _zone(db_session)
    _schedule_row(db_session, zone.zone_id, datetime.time(22, 0), datetime.time(2, 0))

    # Late evening, before midnight — open.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 5, 23, 0))
    assert state == "OPEN"

    # Early morning, after midnight but before close_time — still open.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 6, 1, 0))
    assert state == "OPEN"

    # Midday, well inside the closed daytime gap.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 6, 12, 0))
    assert state == "CLOSED"

    # Just before opening again that evening.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 6, 21, 59))
    assert state == "CLOSED"


def test_schedule_state_just_before_midnight(db_session):
    zone = _zone(db_session)
    _schedule_row(db_session, zone.zone_id, datetime.time(22, 0), datetime.time(2, 0))
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 5, 23, 59, 59))
    assert state == "OPEN"


def test_schedule_state_just_after_midnight(db_session):
    zone = _zone(db_session)
    _schedule_row(db_session, zone.zone_id, datetime.time(22, 0), datetime.time(2, 0))
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 6, 0, 0, 1))
    assert state == "OPEN"


def test_schedule_state_midnight_wrap_grace_period_after_close(db_session):
    """close_time (02:00) is crossed while still within the wrap window —
    grace should still apply exactly like the non-wrapping case."""
    zone = _zone(db_session)
    _schedule_row(db_session, zone.zone_id, datetime.time(22, 0), datetime.time(2, 0), grace_minutes=15)

    # 5 minutes after close_time — still within the 15-minute grace period.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 6, 2, 5))
    assert state == "OPEN"

    # 30 minutes after close_time — grace has elapsed.
    state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=datetime.datetime(2026, 1, 6, 2, 30))
    assert state == "CLOSED"


def test_schedule_state_relative_to_now_schedule_never_flaky_across_midnight(db_session):
    """Direct regression test for the exact bug that caused
    test_empty_during_open_hours_does_not_start_verification to flake: a
    schedule built as (now-1h, now+2h) must read as OPEN at `now`,
    regardless of what wall-clock time `now` actually is — including when
    the window wraps past midnight."""
    zone = _zone(db_session)
    for anchor in (
        datetime.datetime(2026, 1, 5, 12, 0),   # ordinary daytime, no wrap
        datetime.datetime(2026, 1, 5, 23, 30),  # wraps: open 22:30, close 01:30
        datetime.datetime(2026, 1, 5, 0, 30),   # wraps: open 23:30 (prev day time-of-day), close 02:30
    ):
        db_session.query(models.ZoneSchedule).delete()
        db_session.commit()
        _schedule_row(
            db_session, zone.zone_id,
            (anchor - datetime.timedelta(hours=1)).time(),
            (anchor + datetime.timedelta(hours=2)).time(),
        )
        state, _ = automation_engine.get_schedule_state(db_session, zone.zone_id, now=anchor)
        assert state == "OPEN", f"expected OPEN at anchor={anchor}"


def test_empty_after_closing_starts_verification(db_session):
    zone = _zone(db_session)
    zone.occupancy_state = "OCCUPIED"
    db_session.commit()
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id)

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    assert zone.occupancy_state == "VERIFYING"
    assert zone.verification_started_at is not None
    assert result["decision"] == "VERIFICATION_STARTED"


def test_reoccupancy_cancels_verification(db_session):
    zone = _zone(db_session)
    sensor = _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id)
    zone.occupancy_state = "OCCUPIED"
    db_session.commit()

    automation_engine.process_zone_once(db_session, zone)
    db_session.refresh(zone)
    assert zone.occupancy_state == "VERIFYING"

    # Someone walks back in mid-verification.
    sensor.occupancy_state = True
    sensor.last_seen = datetime.datetime.utcnow()
    db_session.commit()

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    assert zone.occupancy_state == "OCCUPIED"
    assert zone.verification_started_at is None
    assert result["decision"] == "VERIFICATION_CANCELLED"


def test_confirmed_empty_shuts_down_non_critical_only(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()

    light = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL",
                     status=True, current_power=40)
    server = _device(db_session, zone.zone_id, "Server", "SERVER", "CRITICAL",
                      status=True, current_power=150)

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    db_session.refresh(light)
    db_session.refresh(server)
    assert zone.occupancy_state == "EMPTY"
    assert zone.verification_started_at is None
    assert result["decision"] == "SHUTDOWN_NON_CRITICAL"
    assert light.status is False
    assert server.status is True  # critical load: engine never touches it


def test_stale_sensor_blocks_shutdown_fail_safe(db_session):
    zone = _zone(db_session)
    sensor = _sensor(db_session, zone.zone_id, occupied=False)
    sensor.last_seen = datetime.datetime.utcnow() - datetime.timedelta(hours=1)  # long stale
    db_session.commit()
    _closed_schedule(db_session, zone.zone_id)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()

    device = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    db_session.refresh(device)
    assert zone.occupancy_state == "VERIFYING"  # stays waiting, never guesses "empty"
    assert device.status is True  # never touched
    assert result["decision"] == "SHUTDOWN_SKIPPED_UNCERTAIN"


def test_manual_override_device_not_touched(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()

    device = _device(db_session, zone.zone_id, "Experiment rig", "LAB_EQUIPMENT", "NON_CRITICAL",
                      status=True, automatic_control_enabled=False)

    automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(device)
    assert device.status is True


def test_still_within_verification_window_takes_no_action(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
    db_session.commit()

    device = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    db_session.refresh(device)
    assert zone.occupancy_state == "VERIFYING"
    assert device.status is True
    assert result is None


def test_automation_log_written_on_shutdown(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True, current_power=40)

    automation_engine.process_zone_once(db_session, zone)

    log = db_session.query(models.AutomationLog).filter(models.AutomationLog.zone_id == zone.zone_id).first()
    assert log is not None
    assert log.decision == "SHUTDOWN_NON_CRITICAL"
    assert "Light" in (log.devices_changed or "")


def test_building_occupancy_state_aggregation(db_session):
    z1 = _zone(db_session, name="Z1")
    z2 = _zone(db_session, name="Z2")
    z1.occupancy_state = "EMPTY"
    z2.occupancy_state = "OCCUPIED"
    db_session.commit()
    assert automation_engine.building_occupancy_state(db_session) == "OCCUPIED"

    z2.occupancy_state = "VERIFYING"
    db_session.commit()
    assert automation_engine.building_occupancy_state(db_session) == "VERIFYING"

    z2.occupancy_state = "EMPTY"
    db_session.commit()
    assert automation_engine.building_occupancy_state(db_session) == "EMPTY"
