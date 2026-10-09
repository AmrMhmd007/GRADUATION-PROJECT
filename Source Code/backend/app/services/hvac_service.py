"""Central HVAC read/ingest logic. No commands are issued here; a reading is
only what a sensor reported. Missing/stale data is UNAVAILABLE, not 0."""
import datetime

from .. import models
from ..config import settings


def ingest(db, zone, *, temperature_c=None, airflow_m3h=None, fan_running=None, node_id=None,
           source="REAL", now=None):
    if source not in ("REAL", "SIMULATED"):
        raise ValueError("source must be REAL or SIMULATED")
    if temperature_c is not None and not (-40 <= temperature_c <= 100):
        raise ValueError("temperature_c out of plausible range")
    if airflow_m3h is not None and airflow_m3h < 0:
        raise ValueError("airflow_m3h must be >= 0")
    if temperature_c is None and airflow_m3h is None and fan_running is None:
        raise ValueError("reading carries no measurement")
    if db.query(models.HvacVent).filter(models.HvacVent.zone_id == zone.zone_id).first() is None:
        raise ValueError("zone has no HVAC vent configured")
    row = models.HvacReading(zone_id=zone.zone_id, temperature_c=temperature_c, airflow_m3h=airflow_m3h,
                             fan_running=fan_running, node_id=node_id, source=source,
                             recorded_at=now or datetime.datetime.utcnow())
    db.add(row)
    db.commit()
    return row


def zone_hvac(db, zone, now=None) -> dict | None:
    now = now or datetime.datetime.utcnow()
    vent = db.query(models.HvacVent).filter(models.HvacVent.zone_id == zone.zone_id).first()
    if vent is None:
        return None
    node = None
    if vent.system.node_id:
        node = db.query(models.HardwareHealth).filter(models.HardwareHealth.node_id == vent.system.node_id).first()
    r = (db.query(models.HvacReading).filter(models.HvacReading.zone_id == zone.zone_id)
         .order_by(models.HvacReading.recorded_at.desc(), models.HvacReading.reading_id.desc()).first())
    out = {"system": vent.system.name, "main_duct": vent.main_duct, "branch_duct": vent.branch_duct,
           "vent": vent.label, "system_node_status": node.status if node else "UNKNOWN",
           "state": "UNAVAILABLE", "reason": "No HVAC sensor has reported for this zone",
           "temperature_c": None, "airflow_m3h": None, "fan_running": None, "last_updated": None, "source": None}
    if r is None:
        return out
    out.update(last_updated=r.recorded_at, source=r.source)
    if (now - r.recorded_at).total_seconds() > settings.HVAC_STALE_AFTER_SECONDS:
        out["reason"] = "Last HVAC reading is stale"
        return out
    out.update(state="OK", reason=None, temperature_c=r.temperature_c, airflow_m3h=r.airflow_m3h,
               fan_running=r.fan_running)
    return out
