# Cyber-Physical Upgrade — Implementation Report

Principle: SENSE → ANALYZE → VERIFY → DECIDE → ACT → MONITOR. A command/software state is never presented as a physical fact.

## Architecture decisions (conflicts with the existing repo)
| Conflict | Decision |
|---|---|
| No `Room` model — a room is a `Door` (+ `Zone` linked by `Zone.door_id`) | Occupancy/devices/health anchor on `Zone`; access on `Door`. No new Room concept. |
| `OccupancyEvent` exists (boolean presence for the automation engine) | Kept untouched. New append-only `OccupancyReading` stores **counts**; each usable count also writes an `OccupancyEvent`, so the existing VERIFY window still guards automation. |
| `Credential.fp_template_hash` is a fingerprint hash | Face data is a separate `FaceCredential` (Fernet-encrypted embedding, never serialized). |
| `Alert.severity` CHECK is INFO/WARNING/CRITICAL; SQLite cannot alter a CHECK without a table rebuild (destructive risk) | New `DeviceFaultAlert` (adds HIGH, ack/assign/resolve). Surfaced in Room Health + Timeline. `Alert` untouched. |
| `Alert`/doors have no AdminScope mapping (see command_center.py) | Campus-wide room endpoints require an **unrestricted** admin (403 for scoped admins) instead of a fabricated filter. |
| No embedding model ships with the repo | Backend accepts embeddings from an adapter (Pi/enrollment station). Dashboard shows capture as **UNAVAILABLE** (`FACE_EMBEDDING_PROVIDER=none`); it does not fake a camera flow. |

## New models (additive) / migration
`FaceCredential`, `OccupancyReading`, `DeviceTelemetry`, `DeviceFaultAlert`, `Zone.capacity` (nullable).
Run `python3 migrate_cyber_physical_upgrade.py` (idempotent; lifespan `create_all` also creates the tables). Nothing dropped/renamed.

## APIs
- Face: `GET /api/face/capabilities|me|users`, `POST /api/face/me/enroll|me/revoke|users/{id}/revoke|users/{id}/disable`, node (X-Node-Key): `POST /api/face/node/verify|ack`
- Occupancy: `POST /api/occupancy/ingest` (node key), `GET /api/occupancy/my-classes|zones/{id}|overview`
- Device faults: `POST /api/device-faults/telemetry` (node key), `GET /api/device-faults[ /maintenance]`, `POST /{id}/acknowledge|assign|resolve|retry-check|report`
- Room intel (admin): `GET /api/rooms-intel/campus-map|zones/{id}/profile|zones/{id}/timeline`
- `Zone` create/update accept `capacity`.

## MQTT (inside the existing hierarchy)
- `site/{door}/face/verify` (node→backend), `site/{door}/face/decision` (backend→node, GRANT/DENY/UNAVAILABLE), `site/{door}/face/ack` (node→backend: physically unlocked or not)
- `university/{u}/building/{b}/zone/{z}/occupancy/count` `{node_id,count,confidence,sensor_status}`
- `university/{u}/building/{b}/zone/{z}/device/{id}/telemetry` `{observed_on,power_watts,current_amps,temperature_c,hazard,node_id}`
- Heartbeats reuse the existing `.../health` topic → `HardwareHealth` (ONLINE/DEGRADED/OFFLINE/UNKNOWN).

## Face door rules
GRANT only if: node healthy + quality ≥ threshold + liveness passed + unambiguous match to an ENROLLED template + active account + existing `evaluate_door_authorization` (permanent assignment or active AccessWindow for **this** room). Schedule alone never unlocks. Node/camera fault → `UNAVAILABLE` (no event, no grant, no denial of the person). `door.locked` only becomes false after the node's `face/ack` (`unlocked:true`). Every decision writes an `AccessEvent(method="face")` with frozen evidence + AuditLog; enroll/re-enroll/revoke/disable are audited.

## Security
Templates Fernet-encrypted, never in any schema/search/log; no raw photos stored; admins see status only; HTTP node endpoints are 403 unless `FACE_NODE_API_KEY` is set; scoped admins get 403 on campus-wide room data; doctors only see occupancy for their own class in progress and faults for rooms they are assigned/teach in.

## Room Health (deterministic)
OFFLINE (all sources down) > CRITICAL (critical fault/alert) > DEGRADED (HIGH fault / node degraded / door node down) > WARNING > HEALTHY; UNKNOWN when no source exists. No percentage.

## Device fault rules
Expectation exists only when `Device.last_command_status` is set. WARNING: no response in window / stale telemetry. HIGH: expected ≠ observed. CRITICAL **only** when the node sets `hazard:true`. No telemetry ⇒ unmonitored, no fault invented. Conditions that clear auto-resolve (history kept). Maintenance recommendation = rule-based (≥3 faults in 30 days **and** abnormal now), labelled not-ML.

## REAL vs SIMULATED vs UNAVAILABLE
REAL: only data received through MQTT/node-key endpoints. SIMULATED: explicit `source:"SIMULATED"` (tests / dev adapters), badged in UI. UNAVAILABLE: no sensor / stale / error (occupancy shows "Unavailable", never 0). Hardware still required: door Pi + camera + embedding/liveness adapter + door relay; occupancy Pi + camera counter; per-device current/state sensors.

## Manual test scenarios
1. Set `FACE_NODE_API_KEY`; enroll via `POST /api/face/me/enroll` (source SIMULATED) → `POST /api/face/node/verify` with same embedding and an assigned door → GRANT; wrong door → DENY; `node_status:"camera_error"` → UNAVAILABLE.
2. `POST /api/occupancy/ingest` count 37 for a zone with capacity 50 → doctor with the class in progress sees 37/50; send `sensor_status:"error"` → "Unavailable".
3. `POST /api/device-faults/telemetry` power 0 for a device marked ON → HIGH fault visible to doctor (Retry/Report) and admin (Acknowledge/Resolve).
4. Admin → Campus Intelligence → Campus Map → click room → profile/timeline → Open Room Profile.

## Verification
Backend: 590 tests passed (37 new in `tests/test_cyber_physical.py`) + the new RBAC test; frontend `oxlint`: 0 errors (14 warnings, same as baseline); `vite build` succeeds.
Known limits: browser-side face capture not implemented (needs an embedding adapter); live click-through in a browser and 390×844 visual QA were not performed in this session.
