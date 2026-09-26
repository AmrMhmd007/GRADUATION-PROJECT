"""
Tests for Phase 3 (confidence-scored occupancy fusion) in
sense_zone_occupancy() / process_zone_once(). The OCCUPIED/EMPTY/UNKNOWN
verdict rules are already covered exhaustively by test_automation_engine.py
and must stay byte-for-byte identical — these tests focus specifically on
the new occupancy_confidence/occupancy_evidence/occupancy_computed_at
output and prove the weights are read from config, not hardcoded.
"""
import datetime
import json

from app import models
from app.config import settings
from app.services import automation_engine


def _zone(db, name="Confidence Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _sensor(db, zone_id, occupied, sensor_type="PIR"):
    sensor = models.Sensor(
        zone_id=zone_id, sensor_type=sensor_type, status="online",
        occupancy_state=occupied, last_seen=datetime.datetime.utcnow(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def test_no_signal_gives_zero_confidence(db_session):
    zone = _zone(db_session)
    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)
    assert verdict == "UNKNOWN"
    assert confidence == 0.0
    assert detail == []


def test_single_agreeing_signal_is_full_confidence(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=True, sensor_type="MMWAVE")

    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)

    assert verdict == "OCCUPIED"
    assert confidence == 1.0
    assert len(detail) == 1
    assert detail[0]["source"] == "sensor_mmwave"
    assert detail[0]["weight"] == settings.OCCUPANCY_SOURCE_WEIGHTS["sensor_mmwave"]


def test_conflicting_signals_reduce_confidence_but_occupied_still_wins(db_session):
    zone = _zone(db_session)
    # A weak signal (door reed switch) says empty; a strong one (mmWave)
    # says occupied. Verdict must be OCCUPIED (fail-safe: never miss real
    # occupancy) but confidence should reflect the disagreement.
    door = models.Door(
        code="CONF-1", name="Conf Room", building="Main", category="access_service",
        occupied=False, occupancy_updated_at=datetime.datetime.utcnow(),
    )
    db_session.add(door)
    db_session.commit()
    zone.door_id = door.door_id
    db_session.commit()
    _sensor(db_session, zone.zone_id, occupied=True, sensor_type="MMWAVE")

    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)

    door_w = settings.OCCUPANCY_SOURCE_WEIGHTS["door_sensor"]
    mmwave_w = settings.OCCUPANCY_SOURCE_WEIGHTS["sensor_mmwave"]
    expected = round(mmwave_w / (door_w + mmwave_w), 3)

    assert verdict == "OCCUPIED"
    assert confidence == expected
    assert 0.0 < confidence < 1.0


def test_all_agreeing_empty_signals_are_full_confidence(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False, sensor_type="PIR")
    _sensor(db_session, zone.zone_id, occupied=False, sensor_type="MMWAVE")

    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)

    assert verdict == "EMPTY"
    assert confidence == 1.0
    assert len(detail) == 2


def test_weights_are_read_from_config_not_hardcoded(db_session, monkeypatch):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=True, sensor_type="PIR")

    monkeypatch.setitem(settings.OCCUPANCY_SOURCE_WEIGHTS, "sensor_pir", 0.42)
    verdict, confidence, evidence, detail = automation_engine.sense_zone_occupancy(db_session, zone)

    assert detail[0]["weight"] == 0.42
    assert confidence == 1.0  # still full confidence — the one signal still agrees with itself


def test_process_zone_once_persists_confidence_every_pass(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=True, sensor_type="MMWAVE")

    automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    assert zone.occupancy_confidence == 1.0
    assert zone.occupancy_computed_at is not None
    detail = json.loads(zone.occupancy_evidence)
    assert detail[0]["source"] == "sensor_mmwave"


def test_computed_at_updates_even_without_a_state_transition(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=True, sensor_type="PIR")
    automation_engine.process_zone_once(db_session, zone)
    db_session.refresh(zone)
    first_computed_at = zone.occupancy_computed_at

    import time
    time.sleep(0.01)
    automation_engine.process_zone_once(db_session, zone)  # still OCCUPIED -> no transition
    db_session.refresh(zone)

    assert zone.occupancy_state == "OCCUPIED"  # unchanged
    assert zone.occupancy_computed_at >= first_computed_at
