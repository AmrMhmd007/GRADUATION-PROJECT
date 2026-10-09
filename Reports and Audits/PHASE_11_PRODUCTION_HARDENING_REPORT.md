# Phase 11 — Production Hardening & Final Demo Readiness — Completion Report

Scope executed: the second ("Production Hardening & Final Demo Readiness") Phase 11 message, which explicitly superseded the earlier, broader "Final Deep Verification & Academic Administration Audit" message sent moments before it. No code or tests were written against the superseded scope.

## Implemented

**1. AuditLog coverage extended** to the mutation paths identified in Phase 10 as unaudited:
- Zone create/update/delete, Sensor create/delete, Device create/update/delete, AutomationRule create/update/delete (`app/routers/zones.py`)
- Building create/delete (`app/routers/buildings.py`) — verified the pre-existing duplicate-name short-circuit does not double-log a phantom "create"
- System Settings (checkout_time) update (`app/routers/energy.py`)
- Password Reset approve/deny (`app/routers/password_resets.py`)

The existing `AuditLog` schema, actor denormalization, result semantics, and unrestricted-admin-only read policy were not changed. Not extended (deliberately, out of this scope): zone-schedules CRUD, `run_automation_once`, `run_checkout_sweep_now`, `set_occupancy` — these are execution/query actions, not the mutation categories the user listed.

**2. Automation Rules** — 7 tests added to the existing `test_automation_rules.py` (persistence-via-fresh-read on update/delete, 404s on updating/deleting a nonexistent rule, RBAC on update/delete, unauthenticated rejection, read access for any authenticated role). The engine itself was not touched.

**3. Bulk Import** — new `test_bulk_import.py` (14 tests) covering both `POST /api/users/import` and `POST /api/doors/import`: valid import with fresh-read persistence, malformed rows (reported in `errors`, not silently dropped, and not created), duplicates (reported in `skipped`, not duplicated), unauthorized access (403), a scoped admin's per-row faculty check for user import, non-.xlsx/unparseable-file rejection, missing required columns, and auto-created Faculty/Building side effects. No import behavior was changed — testing surfaced no defect.

**4. Smart Building controls** — new `test_room_device_controls.py` (19 tests) for AC/light/plug add/toggle/delete. Confirmed and locked in the existing, intentional RBAC policy (`security.require_room_control`): admin always allowed; a doctor only if assigned to that specific door via `DoorAssignment`; an instructor never allowed, even if assigned. Also covers persistence-via-fresh-read, invalid-state handling (AC/light not enabled on that room, plug belonging to a different door, nonexistent plug/door), and unauthenticated rejection. No policy change was made.

**5. UX error handling** (`dashboard/src/api/client.js`, `dashboard/src/components/AccountMenu.jsx`) — presentation-layer only, no API contract changes:
- FastAPI's array-of-`{loc, msg, type}` 422 validation body is now formatted into one readable sentence (e.g. `email: field required`) instead of rendering as `[object Object]` or raw JSON.
- A `fetch()` that never reaches the server (offline, DNS failure, backend down) now throws a clear `"Couldn't reach the server. Check your connection and try again."` instead of the raw `TypeError: Failed to fetch`.
- `AccountMenu`'s profile-save flow now distinguishes a failed `updateProfile` call from a failed post-save `refreshToken` call — previously, if only the token refresh failed, the user saw "Could not update profile" even though the profile update had already succeeded. It now reports "Profile saved. Please sign in again to continue." and relies on the existing `onUnauthorized` → `logout()` path (unchanged) to return the user to the login screen on a 401.

**6. Schedule.course_ref_id API path** — investigated and found straightforward to add safely, so it was implemented rather than deferred:
- `ScheduleCreate`/`ScheduleUpdate` (`app/schemas.py`) gained an optional `course_ref_id` field.
- `app/routers/schedules.py` gained `_validate_course_ref()`, applied on both create and update: the referenced Course must exist (404), the acting admin must have department access to it (403 for a scoped admin outside their scope — the same rule already used for course assignments and course mutations), and if the schedule is already linked to a `CourseAssignment` for a different course, the change is rejected (409) rather than silently orphaning that assignment's implied course.
- 7 tests added to `test_schedules.py` covering create-with-course_ref_id-persists, unknown-course-404, update-persists-on-fresh-read, scoped-admin-403, conflict-409, and non-admin-403.
- `course_id` (the pre-existing free-text field) and all other schedule behavior are untouched.

**7. AdminScope/OperationalScope UI** — left deferred, as instructed. No UI work was done; this remains a documented gap (existing scope-management is API/DB-only for these two resources).

## Tested

Full backend suite run in four batches (bash tool's runtime ceiling required splitting): **449 / 449 passing**, up from the Phase 10 baseline of 392 (57 new tests this phase: 11 audit-log, 7 automation-rules, 14 bulk-import, 19 room-device-controls, 6 net new schedule tests — the schedules test file's total went from 7 to 13). Zero failures, zero regressions in any pre-existing test file.

Frontend: `npm run lint` → 0 errors, 13 warnings (identical, pre-existing warning set — none introduced by this phase). `npm run build` → clean, same bundle-size class as before.

## Modified files

- `backend/app/routers/zones.py` — audit logging on Zone/Sensor/Device/AutomationRule CRUD
- `backend/app/routers/buildings.py` — audit logging on Building create/delete
- `backend/app/routers/energy.py` — audit logging on System Settings update
- `backend/app/routers/password_resets.py` — audit logging on approve/deny
- `backend/app/routers/schedules.py` — `course_ref_id` create/update path + validation
- `backend/app/schemas.py` — `course_ref_id` added to `ScheduleCreate`/`ScheduleUpdate`
- `backend/tests/test_audit_log_extended.py` (new, 11 tests)
- `backend/tests/test_automation_rules.py` (+7 tests, 19 total)
- `backend/tests/test_bulk_import.py` (new, 14 tests)
- `backend/tests/test_room_device_controls.py` (new, 19 tests)
- `backend/tests/test_schedules.py` (+6 net tests, 13 total)
- `dashboard/src/api/client.js` — human-readable 422 errors, network-error wrapping
- `dashboard/src/components/AccountMenu.jsx` — split update/refresh error handling

## Remaining / Known Limitations

- AdminScope/OperationalScope management still has no dedicated UI (API/DB only) — explicitly kept deferred per instruction.
- Zone-schedules CRUD, `run_automation_once`, `run_checkout_sweep_now`, and `set_occupancy` are still not audit-logged — these are execution/query actions rather than the mutation categories in scope for this pass; flagged here rather than silently left out.
- `Schedule.course_id` (legacy free-text) and `course_ref_id` remain two parallel fields by design — this phase only added a write path for the latter, it did not unify or migrate the former.
- No browser/runtime click-through was performed for any change in this phase — all verification is backend test suite + API-level assertions + frontend lint/build, consistent with the sandbox's lack of access to the user's real running instance. A manual smoke test (per the existing `PHASE_10.1_MANUAL_SMOKE_TEST_CHECKLIST.md`) is still recommended before a live demo, and should now also cover: an admin linking a schedule to a course from an as-yet-unbuilt UI surface (no frontend UI calls the new `course_ref_id` field yet — this phase added the backend path only, since no UI request was made for it), AC/light/plug controls, and a 422/network-error scenario to see the new frontend messages in practice.
- The new `course_ref_id` write path has no frontend UI consumer yet (it was added at the API layer per the "if straightforward, implement it" instruction); wiring a UI control for it, if wanted, would be a new, separate scope item.

## Verification Results

- Backend: 449/449 tests passing (4 batches, 0 failures, 0 regressions)
- Frontend: lint 0 errors / 13 pre-existing warnings; build clean
- Browser verification: **not performed** (no access to the user's real running instance in this environment)
