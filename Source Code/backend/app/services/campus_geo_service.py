"""Validation and building mapping for the campus geography dataset.

The dataset (dashboard/src/data/aiu-campus.geojson) is the single source for
map geometry. It never duplicates the Building/Zone tables: a feature points at
a backend Building by its unique name (`backend_building_name`). Building ids
are database-local, names are the stable key (Building.name is unique).

Rule enforced here: geometry is never guessed. UNMAPPED features have no
geometry; APPROXIMATE features are points; VERIFIED features are closed
polygons with a source, a date and MEDIUM/HIGH confidence.
"""
from __future__ import annotations

import datetime
import json
import math
from pathlib import Path

STATUSES = ("UNMAPPED", "APPROXIMATE", "VERIFIED")
CONFIDENCES = ("NONE", "LOW", "MEDIUM", "HIGH")
KINDS = ("campus_reference", "campus_boundary", "building")
# Sanity window around the campus reference point: anything farther is a typo.
MAX_DISTANCE_KM = 5.0

DATASET_PATH = Path(__file__).resolve().parents[3] / "dashboard" / "src" / "data" / "aiu-campus.geojson"


def load(path: Path = DATASET_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _haversine_km(a, b) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _valid_position(pos) -> bool:
    return (isinstance(pos, (list, tuple)) and len(pos) >= 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pos[:2])
            and -180 <= pos[0] <= 180 and -90 <= pos[1] <= 90)


def _ring_ok(ring) -> bool:
    return (isinstance(ring, list) and len(ring) >= 4 and all(_valid_position(p) for p in ring)
            and list(ring[0][:2]) == list(ring[-1][:2]))


def _polygon_ok(geom) -> bool:
    coords = geom.get("coordinates")
    return isinstance(coords, list) and len(coords) >= 1 and all(_ring_ok(r) for r in coords)


def _date_ok(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate(data: dict) -> list[str]:
    """Return a list of problems; empty means the dataset is acceptable."""
    errors: list[str] = []
    if data.get("type") != "FeatureCollection":
        return ["root must be a FeatureCollection"]
    meta = data.get("dataset") or {}
    if meta.get("crs") != "EPSG:4326":
        errors.append("dataset.crs must be EPSG:4326")
    source_ids = {s.get("id") for s in meta.get("sources", [])}
    if None in source_ids or len(source_ids) != len(meta.get("sources", [])):
        errors.append("every source needs a unique id")

    seen_ids: set = set()
    seen_names: set = set()
    reference = None
    for f in data.get("features", []):
        fid = f.get("id")
        p = f.get("properties") or {}
        where = f"feature {fid!r}"
        if not fid or fid in seen_ids:
            errors.append(f"{where}: id missing or duplicated")
        seen_ids.add(fid)
        if p.get("kind") not in KINDS:
            errors.append(f"{where}: unknown kind {p.get('kind')!r}")
        status, conf, geom = p.get("geometry_status"), p.get("confidence"), f.get("geometry")
        if status not in STATUSES:
            errors.append(f"{where}: geometry_status must be one of {STATUSES}")
            continue
        if conf not in CONFIDENCES:
            errors.append(f"{where}: confidence must be one of {CONFIDENCES}")
        for sid in p.get("source_ids", []):
            if sid not in source_ids:
                errors.append(f"{where}: unknown source id {sid!r}")
        if not isinstance(p.get("floor_plan_refs", []), list):
            errors.append(f"{where}: floor_plan_refs must be a list")
        name = p.get("backend_building_name")
        if name is not None:
            if name in seen_names:
                errors.append(f"{where}: backend_building_name {name!r} used twice")
            seen_names.add(name)

        if status == "UNMAPPED":
            if geom is not None:
                errors.append(f"{where}: UNMAPPED features must have geometry null")
            if conf != "NONE":
                errors.append(f"{where}: UNMAPPED requires confidence NONE")
            continue

        # APPROXIMATE / VERIFIED need provenance.
        if not p.get("source_ids"):
            errors.append(f"{where}: {status} requires at least one source")
        if not _date_ok(p.get("source_date")):
            errors.append(f"{where}: {status} requires an ISO source_date")
        if not isinstance(geom, dict):
            errors.append(f"{where}: {status} requires geometry")
            continue
        gtype = geom.get("type")
        if status == "APPROXIMATE":
            if gtype != "Point" or not _valid_position(geom.get("coordinates")):
                errors.append(f"{where}: APPROXIMATE requires a valid Point")
            elif conf == "NONE":
                errors.append(f"{where}: APPROXIMATE needs confidence LOW or higher")
        else:  # VERIFIED
            if conf not in ("MEDIUM", "HIGH"):
                errors.append(f"{where}: VERIFIED requires MEDIUM or HIGH confidence")
            if gtype != "Polygon" or not _polygon_ok(geom):
                errors.append(f"{where}: VERIFIED requires a closed Polygon with valid positions")
        if p.get("kind") == "campus_reference" and gtype == "Point" and _valid_position(geom.get("coordinates")):
            reference = geom["coordinates"]

    if reference is None:
        errors.append("a campus_reference Point is required to place the initial view")
    else:
        for f in data.get("features", []):
            g = f.get("geometry")
            if not g:
                continue
            pts = [g["coordinates"]] if g.get("type") == "Point" else (g.get("coordinates") or [[]])[0]
            for pt in pts:
                if _valid_position(pt) and _haversine_km(reference, pt) > MAX_DISTANCE_KM:
                    errors.append(f"feature {f.get('id')!r}: position is more than {MAX_DISTANCE_KM} km from the campus reference")
                    break
    return errors


def map_to_backend(data: dict, backend_building_names: list[str]) -> dict:
    """Join dataset features to existing Building rows by name. Never creates
    buildings and never invents geometry: unmatched sides are reported."""
    by_name = {f["properties"].get("backend_building_name"): f
               for f in data.get("features", []) if f["properties"].get("backend_building_name")}
    linked, unmapped_backend = [], []
    for name in backend_building_names:
        feat = by_name.get(name)
        if feat and feat["properties"]["geometry_status"] == "VERIFIED":
            linked.append({"building": name, "feature_id": feat["id"]})
        else:
            unmapped_backend.append(name)
    stale_links = sorted(set(by_name) - set(backend_building_names))
    return {"linked": linked, "unmapped_backend_buildings": unmapped_backend,
            "dataset_links_without_backend_building": stale_links}
