// Runtime helpers for the campus geography dataset. Mirrors the rules enforced
// by backend/app/services/campus_geo_service.py (which CI tests): a feature is
// only drawn as a footprint when it is VERIFIED with a valid closed polygon.
// Nothing here creates or guesses coordinates.
import raw from "../../data/aiu-campus.geojson?raw";

const dataset = JSON.parse(raw);

const validPos = (p) =>
  Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) &&
  Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;

const validPolygon = (g) =>
  g?.type === "Polygon" && Array.isArray(g.coordinates) && g.coordinates.length > 0 &&
  g.coordinates.every((r) => Array.isArray(r) && r.length >= 4 && r.every(validPos) &&
    r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1]);

export const GEO = dataset;
export const SOURCES = dataset.dataset.sources;

export function referencePoint() {
  const f = dataset.features.find((x) => x.properties.kind === "campus_reference" && x.geometry?.type === "Point");
  return f && validPos(f.geometry.coordinates)
    ? { lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0], feature: f }
    : null;
}

// Only VERIFIED, valid polygons may be drawn as footprints.
export function drawableFootprints() {
  return dataset.features.filter(
    (f) => f.properties.kind === "building" && f.properties.geometry_status === "VERIFIED" && validPolygon(f.geometry)
  );
}

// One row per building the user can search: every backend Building plus every
// dataset building. `mapped` is true only for a drawable footprint.
export function buildBuildingIndex(backendBuildings) {
  const feats = dataset.features.filter((f) => f.properties.kind === "building");
  const drawable = new Set(drawableFootprints().map((f) => f.id));
  const rows = [];
  const usedFeatures = new Set();
  for (const b of backendBuildings || []) {
    const feat = feats.find((f) => f.properties.backend_building_name === b.name);
    if (feat) usedFeatures.add(feat.id);
    rows.push({
      key: `b${b.building_id}`, name: b.name, backendId: b.building_id, backendName: b.name,
      feature: feat || null, mapped: !!feat && drawable.has(feat.id),
      status: feat ? feat.properties.geometry_status : "UNMAPPED",
    });
  }
  for (const f of feats) {
    if (usedFeatures.has(f.id)) continue;
    rows.push({
      key: f.id, name: f.properties.name, backendId: null, backendName: null,
      feature: f, mapped: drawable.has(f.id), status: f.properties.geometry_status,
    });
  }
  return rows.sort((a, b) => a.name.localeCompare(b.name));
}

// Live figures come only from the existing campus-map read model. Anything
// missing is reported as unavailable, never as zero.
export function summariseLive(campusMap, backendName) {
  if (!campusMap) return { available: false, reason: "Live campus data could not be loaded." };
  const b = campusMap.buildings.find((x) => x.name === backendName);
  if (!b) return { available: false, reason: "No rooms (zones) are registered for this building." };
  const rooms = b.floors.flatMap((f) => f.rooms);
  const reporting = rooms.filter((r) => r.occupancy_state !== "UNAVAILABLE" && r.occupancy != null);
  const health = {};
  for (const r of rooms) health[r.health] = (health[r.health] || 0) + 1;
  return {
    available: true, rooms: rooms.length, reporting: reporting.length,
    occupancy: reporting.length ? reporting.reduce((s, r) => s + r.occupancy, 0) : null, health,
  };
}
