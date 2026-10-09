"""Room occupancy: node ingest, doctor view (own classes only), admin overview."""
import datetime
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, security
from ..config import settings
from ..database import get_db
from ..services import occupancy_service

router = APIRouter(prefix="/api/occupancy", tags=["occupancy"])


class IngestIn(BaseModel):
    zone_id: int
    node_id: Optional[str] = None
    count: Optional[int] = None
    confidence: Optional[float] = None
    sensor_status: str = "ok"
    source: str = "REAL"


def _node_key(x_node_key: Optional[str] = Header(default=None)):
    expected = settings.FACE_NODE_API_KEY
    if not expected or not x_node_key or not hmac.compare_digest(expected, x_node_key):
        raise HTTPException(status_code=403, detail="Node authentication failed")


@router.post("/ingest", status_code=201, dependencies=[Depends(_node_key)])
def ingest(payload: IngestIn, db: Session = Depends(get_db)):
    zone = db.get(models.Zone, payload.zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Unknown zone")
    try:
        r = occupancy_service.ingest(db, zone, node_id=payload.node_id, count=payload.count,
                                     confidence=payload.confidence, sensor_status=payload.sensor_status,
                                     source=payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"reading_id": r.reading_id}


def _zone_for_door(db, door_id):
    return db.query(models.Zone).filter(models.Zone.door_id == door_id).first()


def _view(db, zone, door, now=None):
    return {"zone_id": zone.zone_id, "room": zone.name, "door_code": door.code if door else None,
            "occupancy": occupancy_service.current(db, zone, now),
            "sensor_health": occupancy_service.sensor_health(db, zone, now)}


@router.get("/my-classes")
def my_classes(db: Session = Depends(get_db), user=Depends(security.get_current_user)):
    """Today's classes for the signed-in doctor/TA with room occupancy ONLY for
    their own rooms. Occupancy is shown only for the class in progress."""
    if user.role not in ("doctor", "instructor"):
        raise HTTPException(status_code=403, detail="Staff accounts only")
    out = []
    for c in occupancy_service.classes_today(db, user):
        door = db.get(models.Door, c["door_id"])
        zone = _zone_for_door(db, c["door_id"])
        item = {"course_code": c["course_code"], "course_name": c["course_name"],
                "room": zone.name if zone else (door.name if door else None),
                "door_code": door.code if door else None,
                "start": c["start"].isoformat(timespec="minutes"), "end": c["end"].isoformat(timespec="minutes"),
                "in_progress": c["in_progress"], "zone_id": zone.zone_id if zone else None,
                "occupancy": None, "sensor_health": None}
        if c["in_progress"] and zone is not None:
            item["occupancy"] = occupancy_service.current(db, zone)
            item["sensor_health"] = occupancy_service.sensor_health(db, zone)
        out.append(item)
    return out


def _doctor_may_view(db, user, zone) -> bool:
    return any(c["in_progress"] and zone.door_id == c["door_id"] for c in occupancy_service.classes_today(db, user))


@router.get("/zones/{zone_id}")
def zone_occupancy(zone_id: int, hours: int = Query(3, ge=1, le=168), db: Session = Depends(get_db),
                   user=Depends(security.get_current_user)):
    zone = db.get(models.Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    if user.role in ("doctor", "instructor"):
        if not _doctor_may_view(db, user, zone):
            raise HTTPException(status_code=403, detail="Occupancy is only available for your class in progress")
        hours = min(hours, 3)
    elif user.role != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    door = db.get(models.Door, zone.door_id) if zone.door_id else None
    return {**_view(db, zone, door), "history": occupancy_service.history(db, zone_id, since)}


@router.get("/overview")
def overview(db: Session = Depends(get_db), admin=Depends(security.require_unrestricted_admin)):
    """Campus -> Building -> Floor -> Room, from real zones/readings only."""
    now = datetime.datetime.utcnow()
    zones = db.query(models.Zone).all()
    buildings: dict = {}
    total_people = 0
    occupied_rooms = 0
    counted_rooms = 0
    health = {"ONLINE": 0, "DEGRADED": 0, "OFFLINE": 0, "UNKNOWN": 0}
    for z in zones:
        door = db.get(models.Door, z.door_id) if z.door_id else None
        v = _view(db, z, door, now)
        health[v["sensor_health"]] += 1
        occ = v["occupancy"]
        if occ["state"] in ("OK", "DEGRADED"):
            counted_rooms += 1
            total_people += occ["count"]
            if occ["count"] > 0:
                occupied_rooms += 1
        b = buildings.setdefault(z.building_name or "Unassigned", {"name": z.building_name or "Unassigned",
                                                                   "floors": {}, "people": 0, "counted_rooms": 0})
        f = b["floors"].setdefault(z.floor or "-", {"floor": z.floor or "-", "rooms": []})
        f["rooms"].append(v)
        if occ["state"] in ("OK", "DEGRADED"):
            b["people"] += occ["count"]
            b["counted_rooms"] += 1
    out_b = []
    for b in buildings.values():
        b["floors"] = list(b["floors"].values())
        out_b.append(b)
    return {"generated_at": now,
            "campus": {"total_people": total_people, "occupied_rooms": occupied_rooms,
                       "rooms_with_live_count": counted_rooms, "rooms_total": len(zones),
                       "average_per_counted_room": round(total_people / counted_rooms, 1) if counted_rooms else None},
            "sensor_health": health, "buildings": out_b}
