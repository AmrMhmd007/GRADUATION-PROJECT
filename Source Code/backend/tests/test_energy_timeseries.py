"""
Tests for Phase 6 (Zone/Device-scoped energy time series):
app/services/energy_timeseries_service.py, its two writers
(energy_service.py's simulation pass, mqtt_service.py's real-telemetry
handler), and the /api/energy/* endpoints.
"""
import datetime
import json

from app import models
from app.services import energy_service, energy_timeseries_service, mqtt_service


def _zone(db, name="Energy Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _device(db, zone_id, name="AC", type_="AC", criticality="NON_CRITICAL", status=False,
            rated_power=None, automatic_control_enabled=True):
    device = models.Device(
        zone_id=zone_id, name=name, type=type_, criticality=criticality, status=status,
        rated_power=rated_power, automatic_control_enabled=automatic_control_enabled,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


# ---------------------------------------------------------------------------
# record_reading / aggregate
# ---------------------------------------------------------------------------
def test_record_reading_rejects_missing_source(db_session):
    zone = _zone(db_session)
    try:
        energy_timeseries_service.record_reading(db_session, zone_id=zone.zone_id, device_id=None,
                                                   power=100, source="MADE_UP")
        assert False, "should have raised"
    except ValueError:
        pass


def test_aggregate_buckets_by_hour_and_flags_all_simulated(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id)
    now = datetime.datetime(2026, 1, 1, 10, 15)
    energy_timeseries_service.record_reading(
        db_session, zone_id=zone.zone_id, device_id=device.device_id, power=500,
        energy_kwh=0.05, source="SIMULATED", timestamp=now,
    )
    energy_timeseries_service.record_reading(
        db_session, zone_id=zone.zone_id, device_id=device.device_id, power=700,
        energy_kwh=0.07, source="SIMULATED", timestamp=now.replace(minute=45),
    )
    db_session.commit()

    result = energy_timeseries_service.aggregate(db_session, "hourly", zone_id=zone.zone_id)

    assert len(result) == 1
    bucket = result[0]
    assert bucket["avg_power_watts"] == 600.0
    assert round(bucket["energy_kwh_total"], 2) == 0.12
    assert bucket["all_simulated"] is True
    assert bucket["real_count"] == 0
    assert bucket["simulated_count"] == 2


def test_aggregate_marks_bucket_not_all_simulated_when_a_real_reading_exists(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id)
    now = datetime.datetime(2026, 1, 1, 10, 0)
    energy_timeseries_service.record_reading(
        db_session, zone_id=zone.zone_id, device_id=device.device_id, power=500, source="SIMULATED", timestamp=now,
    )
    energy_timeseries_service.record_reading(
        db_session, zone_id=zone.zone_id, device_id=device.device_id, power=550, source="REAL", timestamp=now,
    )
    db_session.commit()

    result = energy_timeseries_service.aggregate(db_session, "hourly", zone_id=zone.zone_id)
    assert result[0]["all_simulated"] is False
    assert result[0]["real_count"] == 1


def test_aggregate_rejects_bad_granularity(db_session):
    try:
        energy_timeseries_service.aggregate(db_session, "fortnightly")
        assert False, "should have raised"
    except ValueError:
        pass


def test_aggregate_reports_nothing_for_a_gap_never_interpolates(db_session):
    zone = _zone(db_session)
    result = energy_timeseries_service.aggregate(db_session, "daily", zone_id=zone.zone_id)
    assert result == []


# ---------------------------------------------------------------------------
# current_snapshot / estimate_savings_watts
# ---------------------------------------------------------------------------
def test_current_snapshot_splits_real_and_simulated(db_session):
    zone = _zone(db_session)
    real_device = _device(db_session, zone.zone_id, name="Real AC", status=True)
    real_device.current_power = 300
    real_device.power_source = "REAL"
    sim_device = _device(db_session, zone.zone_id, name="Sim Light", type_="LIGHT", status=True)
    sim_device.current_power = 40
    sim_device.power_source = "SIMULATED"
    db_session.commit()

    snap = energy_timeseries_service.current_snapshot(db_session, zone_id=zone.zone_id)
    assert snap["real_watts"] == 300
    assert snap["simulated_watts"] == 40
    assert snap["total_watts"] == 340


def test_estimate_savings_only_counts_eligible_off_devices(db_session):
    zone = _zone(db_session)
    _device(db_session, zone.zone_id, name="Off non-critical", status=False, rated_power=100)
    _device(db_session, zone.zone_id, name="On non-critical", status=True, rated_power=200)
    _device(db_session, zone.zone_id, name="Off critical", status=False, rated_power=500,
            criticality="CRITICAL")
    _device(db_session, zone.zone_id, name="Off manual-override", status=False, rated_power=300,
            automatic_control_enabled=False)

    estimate = energy_timeseries_service.estimate_savings_watts(db_session, zone_id=zone.zone_id)
    assert estimate == 100


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def test_energy_simulation_writes_energy_reading_simulated(db_session):
    door = models.Door(code="ENERGY-1", name="Energy Room", building="Main",
                        category="access_service", ac_enabled=True, ac_on=True)
    db_session.add(door)
    db_session.commit()
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id)
    device.door_ref_id = door.door_id
    db_session.commit()

    energy_service.simulate_power_and_check_alerts_once(db_session)

    reading = db_session.query(models.EnergyReading).filter(
        models.EnergyReading.device_id == device.device_id
    ).first()
    assert reading is not None
    assert reading.source == "SIMULATED"
    assert reading.power is not None
    assert reading.energy_kwh is not None


def test_mqtt_device_state_with_power_writes_energy_reading_real(db_session):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, name="Freestanding", type_="SERVER", status=False)

    topic = f"university/aiu/building/1/zone/{zone.zone_id}/device/{device.device_id}/state"
    mqtt_service._on_message(None, None, FakeMsg(
        topic, json.dumps({"on": True, "current_power": 88.0, "voltage": 231, "current": 0.38}),
    ))

    reading = db_session.query(models.EnergyReading).filter(
        models.EnergyReading.device_id == device.device_id
    ).first()
    assert reading is not None
    assert reading.source == "REAL"
    assert reading.power == 88.0
    assert reading.voltage == 231


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_energy_endpoints(db_session, client, admin_token):
    zone = _zone(db_session)
    device = _device(db_session, zone.zone_id, status=True)
    device.current_power = 400
    device.power_source = "SIMULATED"
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    current = client.get(f"/api/energy/current?zone_id={zone.zone_id}", headers=headers)
    assert current.status_code == 200
    assert current.json()["total_watts"] == 400

    ts = client.get(f"/api/energy/timeseries?granularity=daily&zone_id={zone.zone_id}", headers=headers)
    assert ts.status_code == 200

    bad = client.get("/api/energy/timeseries?granularity=nonsense", headers=headers)
    assert bad.status_code == 400

    savings = client.get(f"/api/energy/savings-estimate?zone_id={zone.zone_id}", headers=headers)
    assert savings.status_code == 200
    assert "estimated_savings_watts" in savings.json()
