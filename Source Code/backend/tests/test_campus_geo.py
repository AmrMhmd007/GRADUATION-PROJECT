"""Phase 2A - campus geography dataset validation and building mapping.

These tests guard the rule "never fabricate geometry": the shipped dataset must
validate, unmapped features must carry no coordinates, and anything marked
VERIFIED must have provenance. Mapping is checked against real Building rows.
"""
import copy

import pytest

from app import models
from app.services import campus_geo_service as geo


@pytest.fixture
def data():
    return geo.load()


def _building(**over):
    props = {"kind": "building", "name": "Test Hall", "backend_building_name": None,
             "geometry_status": "VERIFIED", "source_ids": ["unirank-location"],
             "source_date": "2026-11-15", "confidence": "MEDIUM", "floor_plan_refs": []}
    props.update(over.pop("props", {}))
    ring = [[28.9298, 30.8116], [28.9302, 30.8116], [28.9302, 30.8119], [28.9298, 30.8119], [28.9298, 30.8116]]
    f = {"type": "Feature", "id": over.pop("id", "t1"), "geometry": {"type": "Polygon", "coordinates": [ring]},
         "properties": props}
    f.update(over)
    return f


def _with(data, *features):
    d = copy.deepcopy(data)
    d["features"].extend(features)
    return d


def test_shipped_dataset_is_valid(data):
    assert geo.validate(data) == []


def test_shipped_dataset_has_no_fabricated_geometry(data):
    """Only the reference point carries coordinates; no polygon is claimed."""
    with_geom = [f for f in data["features"] if f["geometry"] is not None]
    assert [f["id"] for f in with_geom] == ["aiu-campus-reference"]
    assert with_geom[0]["properties"]["geometry_status"] == "APPROXIMATE"
    assert with_geom[0]["properties"]["confidence"] == "LOW"


def test_every_unmapped_feature_has_null_geometry(data):
    for f in data["features"]:
        if f["properties"]["geometry_status"] == "UNMAPPED":
            assert f["geometry"] is None


def test_crs_is_wgs84_and_documented(data):
    assert data["dataset"]["crs"] == "EPSG:4326"


def test_unretrieved_sources_are_recorded_as_such(data):
    for s in data["dataset"]["sources"]:
        if s["id"] in ("aiu-campus-maps", "aiu-gallery"):
            assert s["accessed"] is None and "NOT RETRIEVED" in s["provides"]


def test_unmapped_with_coordinates_is_rejected(data):
    f = _building(props={"geometry_status": "UNMAPPED", "confidence": "NONE"})
    assert any("UNMAPPED" in e for e in geo.validate(_with(data, f)))


def test_verified_requires_source_date_and_confidence(data):
    f = _building(props={"source_ids": [], "source_date": None, "confidence": "LOW"})
    errs = " ".join(geo.validate(_with(data, f)))
    assert "at least one source" in errs and "source_date" in errs and "MEDIUM or HIGH" in errs


def test_valid_verified_polygon_is_accepted(data):
    assert geo.validate(_with(data, _building())) == []


def test_open_ring_is_rejected(data):
    f = _building()
    f["geometry"]["coordinates"][0][-1] = [28.9, 30.8]
    assert any("closed Polygon" in e for e in geo.validate(_with(data, f)))


def test_out_of_range_and_far_positions_are_rejected(data):
    far = _building()
    far["geometry"]["coordinates"] = [[[29.5, 31.5], [29.51, 31.5], [29.51, 31.51], [29.5, 31.51], [29.5, 31.5]]]
    assert any("km from the campus reference" in e for e in geo.validate(_with(data, far)))
    bad = _building(id="t2")
    bad["geometry"]["coordinates"] = [[[200, 95], [201, 95], [201, 96], [200, 96], [200, 95]]]
    assert any("closed Polygon" in e for e in geo.validate(_with(data, bad)))


def test_duplicate_ids_and_unknown_sources_are_rejected(data):
    dup = _building(id="aiu-campus-boundary", props={"source_ids": ["nope"]})
    errs = " ".join(geo.validate(_with(data, dup)))
    assert "duplicated" in errs and "unknown source id" in errs


def test_duplicate_backend_link_is_rejected(data):
    a = _building(id="a", props={"backend_building_name": "Hall"})
    b = _building(id="b", props={"backend_building_name": "Hall"})
    assert any("used twice" in e for e in geo.validate(_with(data, a, b)))


def test_reference_point_is_required(data):
    d = copy.deepcopy(data)
    d["features"] = [f for f in d["features"] if f["id"] != "aiu-campus-reference"]
    assert any("campus_reference" in e for e in geo.validate(d))


def test_mapping_reports_unmapped_backend_buildings(data, db_session):
    for n in ("Mapped Hall", "Lonely Hall"):
        db_session.add(models.Building(name=n))
    db_session.commit()
    names = [b.name for b in db_session.query(models.Building).order_by(models.Building.name)]
    d = _with(data, _building(id="m1", props={"backend_building_name": "Mapped Hall"}),
              _building(id="m2", props={"backend_building_name": "Deleted Hall"}))
    result = geo.map_to_backend(d, names)
    assert result["linked"] == [{"building": "Mapped Hall", "feature_id": "m1"}]
    assert result["unmapped_backend_buildings"] == ["Lonely Hall"]
    assert result["dataset_links_without_backend_building"] == ["Deleted Hall"]


def test_unmapped_dataset_feature_never_counts_as_linked(data):
    d = copy.deepcopy(data)
    for f in d["features"]:
        if f["id"] == "aiu-service-building-b16":
            f["properties"]["backend_building_name"] = "Service Building B16"
    assert geo.validate(d) == []
    assert geo.map_to_backend(d, ["Service Building B16"])["linked"] == []


# ---- Phase 2A continuation: historical master plan register and reference files ----
import json as _json
from pathlib import Path as _Path

_DATA = geo.DATASET_PATH.parent


def _ref(name):
    return _json.loads((_DATA / name).read_text(encoding="utf-8"))


def test_master_plan_source_is_registered_with_limitations(data):
    s = next(x for x in data["dataset"]["sources"] if x["id"] == "aiu-faculties-pdf-2020")
    assert s["document_date"] == "2020-10"
    assert s["source_type"] == "historical architectural master plan"
    assert "not current satellite imagery" in s["limitations"] and "not surveyed GIS" in s["limitations"]
    assert any(r.startswith("6") for r in s["page_refs"])


def test_master_plan_adds_no_geometry(data):
    assert [f["id"] for f in data["features"] if f["geometry"]] == ["aiu-campus-reference"]


def test_reference_files_contain_no_coordinates():
    for name in ("aiu-master-plan-inventory.json", "aiu-facility-matching.json"):
        text = (_DATA / name).read_text(encoding="utf-8")
        for banned in ('"coordinates"', '"geometry"', '"lat"', '"lng"', '"lon"'):
            assert banned not in text, f"{name} must not carry {banned}"


def test_matching_never_verifies_without_evidence():
    for row in _ref("aiu-facility-matching.json")["rows"]:
        if row["verification_status"] == "VERIFIED":
            assert row["satellite_match"] and row["confidence"] in ("MEDIUM", "HIGH")
        else:
            assert row["missing_evidence"]


def test_inventory_does_not_claim_built_status():
    for f in _ref("aiu-master-plan-inventory.json")["facilities"]:
        assert f["built_status"] in ("UNCONFIRMED", "CONFIRMED_BUILT")
        if f["built_status"] == "CONFIRMED_BUILT":
            assert f["evidence"] != "page heading (text layer)"
