"""
Phase 6: Zone/Device-scoped energy time series (EnergyReading model) and its
aggregation, separate from the legacy per-Room PowerReading table used by
the original energy/checkout dashboard feature (see EnergyReading's own
docstring in models.py for why the two aren't merged).

Two writers exist today, both already-existing code paths extended rather
than a new polling loop:

- services/energy_service.py's simulation pass (no real power-metering
  hardware exists yet) — writes a SIMULATED row alongside its existing
  PowerReading write, at the same ENERGY_SIM_INTERVAL_SECONDS cadence.
- services/mqtt_service.py's _handle_v2_device_state — writes a REAL row
  whenever an actual node reports current_power over MQTT.

aggregate() rolls raw readings up into current/hourly/daily/weekly/monthly
buckets. "current" doesn't touch this table at all — it reads live
Device.current_power directly, since that's already the freshest number
available and re-deriving it from the time series would just be slower and
staler. estimate_savings_watts() is the one canonical place this project
computes "how much are we saving right now" — routers/zones.py's dashboard
summary endpoint calls this rather than keeping its own copy of the same
arithmetic.

Do not fabricate historical energy data: aggregate() only ever reports on
rows that were actually written by one of the two paths above. A time
bucket with no readings in it is simply absent from the result, never
interpolated or backfilled.
"""
from __future__ import annotations

import datetime

from .. import models

MAINS_VOLTAGE = 230  # matches energy_service.py / automation_engine.py's own assumption

_BUCKET_FORMAT = {
    "hourly": "%Y-%m-%d %H:00",
    "daily": "%Y-%m-%d",
    "weekly": "%Y-W%W",
    "monthly": "%Y-%m",
}


def record_reading(db, *, zone_id: int | None, device_id: int | None, power: float | None,
                    source: str, voltage: float | None = None, current: float | None = None,
                    energy_kwh: float | None = None, power_factor: float | None = None,
                    timestamp: datetime.datetime | None = None) -> models.EnergyReading:
    """The one function that writes to EnergyReading — both callers
    (energy_service.py's simulation pass, mqtt_service.py's real-telemetry
    handler) go through this rather than constructing the row themselves,
    so `source` can never be forgotten."""
    if source not in ("REAL", "SIMULATED"):
        raise ValueError(f"source must be 'REAL' or 'SIMULATED', got {source!r}")
    reading = models.EnergyReading(
        timestamp=timestamp or datetime.datetime.utcnow(),
        zone_id=zone_id, device_id=device_id,
        voltage=voltage, current=current, power=power, energy_kwh=energy_kwh,
        power_factor=power_factor, source=source,
    )
    db.add(reading)
    return reading


def current_snapshot(db, zone_id: int | None = None) -> dict:
    """"Current" isn't a time-series aggregation — it's just the live
    Device.current_power total, same numbers the rest of the dashboard
    already shows, split out by REAL vs SIMULATED provenance so the caller
    can tell whether any of it is real hardware yet."""
    query = db.query(models.Device).filter(models.Device.status.is_(True))
    if zone_id is not None:
        query = query.filter(models.Device.zone_id == zone_id)
    devices = query.all()
    real_watts = sum((d.current_power or 0) for d in devices if d.power_source == "REAL")
    simulated_watts = sum((d.current_power or 0) for d in devices if d.power_source != "REAL")
    return {
        "total_watts": round(real_watts + simulated_watts, 1),
        "real_watts": round(real_watts, 1),
        "simulated_watts": round(simulated_watts, 1),
        "devices_on": len(devices),
    }


def aggregate(db, granularity: str, zone_id: int | None = None, device_id: int | None = None,
              start: datetime.datetime | None = None, end: datetime.datetime | None = None) -> list[dict]:
    """Buckets raw EnergyReading rows by `granularity` ('hourly' | 'daily' |
    'weekly' | 'monthly'). Each bucket reports average power, summed
    interval energy, and how many of its readings were REAL vs SIMULATED —
    so a chart built from this can visibly flag a bucket built entirely
    from simulated data rather than silently presenting it as measured.
    """
    if granularity not in _BUCKET_FORMAT:
        raise ValueError(f"granularity must be one of {sorted(_BUCKET_FORMAT)}, got {granularity!r}")

    query = db.query(models.EnergyReading)
    if zone_id is not None:
        query = query.filter(models.EnergyReading.zone_id == zone_id)
    if device_id is not None:
        query = query.filter(models.EnergyReading.device_id == device_id)
    if start is not None:
        query = query.filter(models.EnergyReading.timestamp >= start)
    if end is not None:
        query = query.filter(models.EnergyReading.timestamp <= end)

    fmt = _BUCKET_FORMAT[granularity]
    buckets: dict[str, dict] = {}
    for reading in query.order_by(models.EnergyReading.timestamp.asc()).all():
        key = reading.timestamp.strftime(fmt)
        bucket = buckets.setdefault(key, {
            "bucket": key, "power_sum": 0.0, "power_count": 0,
            "energy_kwh_total": 0.0, "real_count": 0, "simulated_count": 0,
        })
        if reading.power is not None:
            bucket["power_sum"] += reading.power
            bucket["power_count"] += 1
        if reading.energy_kwh is not None:
            bucket["energy_kwh_total"] += reading.energy_kwh
        if reading.source == "REAL":
            bucket["real_count"] += 1
        else:
            bucket["simulated_count"] += 1

    result = []
    for key in sorted(buckets):
        b = buckets[key]
        result.append({
            "bucket": b["bucket"],
            "avg_power_watts": round(b["power_sum"] / b["power_count"], 1) if b["power_count"] else None,
            "energy_kwh_total": round(b["energy_kwh_total"], 4),
            "reading_count": b["real_count"] + b["simulated_count"],
            "real_count": b["real_count"],
            "simulated_count": b["simulated_count"],
            "all_simulated": b["real_count"] == 0,
        })
    return result


def estimate_savings_watts(db, zone_id: int | None = None) -> float:
    """The canonical "how much are we saving right now" figure: the rated
    power of every currently-off, automatically-controlled NON_CRITICAL
    device — i.e. what would be drawing power right now if automation
    hadn't switched it off. A simple, explainable estimate (not a rigorous
    energy-accounting figure), and the single place this project computes
    it — routers/zones.py's dashboard summary calls this rather than
    keeping its own copy of the same arithmetic.
    """
    query = db.query(models.Device).filter(
        models.Device.status.is_(False),
        models.Device.criticality == "NON_CRITICAL",
        models.Device.automatic_control_enabled.is_(True),
    )
    if zone_id is not None:
        query = query.filter(models.Device.zone_id == zone_id)
    return sum((d.rated_power or 0) for d in query.all())
