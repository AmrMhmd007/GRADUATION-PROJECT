# Campus geography: data model, sources and licensing

*Phase 2A, 2026-11-15, branch `feature/campus-digital-twin`. Status: foundation only. **No verified building outline exists yet.** Not browser-verified; checked by lint, production build and 15 backend tests.*

## 1. What exists

| Item | Where |
|---|---|
| Dataset (GeoJSON, WGS 84 / EPSG:4326, `[lon, lat]`) | `Source Code/dashboard/src/data/aiu-campus.geojson` |
| Validator and building mapping | `backend/app/services/campus_geo_service.py` |
| Tests (15) | `backend/tests/test_campus_geo.py` |
| Map view (tab "Campus Twin") | `dashboard/src/components/physical/CampusTwinMap.jsx`, `campusGeo.js` |

No database table was added. Geometry lives in the dataset file; backend records are linked by `properties.backend_building_name`, which matches the unique `Building.name`. Building ids are not used because they differ between databases. Zones keep pointing at buildings by name as before.

## 2. Feature schema

Every feature has `id`, `geometry` (or `null`) and these properties: `kind` (`campus_reference`, `campus_boundary`, `building`), `name`, `backend_building_name` (nullable), `geometry_status`, `source_ids`, `source_date`, `confidence` (`NONE`, `LOW`, `MEDIUM`, `HIGH`), `floor_plan_refs` (list of strings, currently unused) and `notes`.

| `geometry_status` | Geometry | Required |
|---|---|---|
| `UNMAPPED` | must be `null` | confidence `NONE` |
| `APPROXIMATE` | `Point` | source, ISO date, confidence above `NONE` |
| `VERIFIED` | closed `Polygon` | source, ISO date, confidence `MEDIUM` or `HIGH` |

The validator also rejects duplicate ids, unknown source ids, a duplicate `backend_building_name`, out-of-range coordinates, open rings and any position more than 5 km from the campus reference. The map draws only `VERIFIED` polygons that pass the same checks in the browser.

## 3. Current content (verified against sources on 2026-11-15)

| Feature | Status | Basis |
|---|---|---|
| Campus reference point 30.8116875 N, 28.9298125 E | `APPROXIMATE`, confidence `LOW` | Centre of the map embed on the uniRank location page (Plus Code RW8J+JWW). Not surveyed; not a centroid. |
| Campus boundary | `UNMAPPED` | No source retrieved. |
| Service Building B16 | `UNMAPPED` | Named in the EMCO 2025 profile ("Alamein University - Service Building B16"). No coordinates. |

## 4. Source status

| Source | Result |
|---|---|
| uniRank location page | Retrieved. Gives the point above only. |
| EMCO Company Profile 2025 | Retrieved. One building name, no geometry. |
| AIU Campus Maps, `aiu.edu.eg/campus-maps/` | **Not retrieved.** The fetch was refused by the site's robots.txt policy. Needs manual review by a person. |
| AIU Gallery, `aiu.edu.eg/gallery-2/` | **Not retrieved**, same reason. Photographs and renders are not satellite imagery in any case. |

Not attempted by other means: no workaround was used for the blocked pages.

## 5. Remaining unmapped buildings

All of them. The campus boundary and Service Building B16 are in the dataset as unmapped. Every Building record in a deployment's database also shows as unmapped unless a `VERIFIED` feature names it. The demo seed's "Building A" and "Building B" are placeholder names, not confirmed AIU buildings.

## 6. How to add a verified building

1. Obtain an outline from a source you are entitled to use (the official campus map, or tracing on imagery whose licence allows derivative vector data).
2. Add a `Feature` with a closed `Polygon`, `geometry_status: "VERIFIED"`, a `source_ids` entry declared in `dataset.sources`, an ISO `source_date`, confidence `MEDIUM` or `HIGH`.
3. Set `backend_building_name` to the exact `Building.name`.
4. Run `pytest tests/test_campus_geo.py`.

## 7. Map library choice

| | Leaflet 1.9.4 (chosen) | MapLibre GL JS |
|---|---|---|
| Size added | about 48 kB gzip, lazy-loaded with the tab | several times larger, WebGL |
| Needs | raster tiles or none | WebGL; vector style/tiles for best use |
| Fit here | A few polygons and optional raster basemaps; no 3D | Better for vector tiles, rotation, 3D extrusion |

Leaflet was chosen because there is no vector tile source and the scope is a handful of footprints. MapLibre is the better choice if Phase 2B needs extruded 3D buildings or vector basemaps. Main bundle stayed at 520 kB (previously about 518 kB); the map chunk loads on demand.

## 8. Basemaps and licensing

No imagery or tiles are bundled or hard-coded. The deployer configures providers in `dashboard/.env`:

| Variable | Effect |
|---|---|
| `VITE_SATELLITE_TILE_URL`, `VITE_SATELLITE_ATTRIBUTION` | Enables the Satellite layer. Without them the option is disabled. |
| `VITE_CLEAN_TILE_URL`, `VITE_CLEAN_ATTRIBUTION` | Enables the Clean layer. |

Provider terms are the deployer's responsibility (many providers forbid use outside their SDK, caching, or resale; some require an API key or account). The attribution string is shown on the map. Without configuration the map shows a plain dark canvas. The uniRank page embeds Google Maps with its own key; that key and imagery are not used here.

Leaflet is BSD-2-Clause. Its npm audit notices were not reviewed.

## 9. Live data

The detail panel reads the existing `GET /api/rooms-intel/campus-map` (unrestricted admin only). Room count, health and occupancy are shown only when the building name matches zones there; occupancy that is missing is "Unavailable", never 0; partial coverage is shown as "n/m rooms reporting". Energy is shown as unavailable. A failed call or a non-admin user gets an explicit "Unavailable" message.

## 10. Limits

Not verified in a browser or with screenshots. No test covers the React view or the browser-side validator (there is no frontend test runner). The Python and JavaScript validators are separate copies of the same rules.
