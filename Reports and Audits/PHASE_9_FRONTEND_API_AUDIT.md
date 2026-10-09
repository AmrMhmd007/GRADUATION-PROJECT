# Phase 9 — Full Frontend Button → API Audit

Every user-triggerable action in the dashboard (`dashboard/src/`), mapped to
the `api.*` client function it calls, the HTTP method/endpoint that hits,
whether the backend route exists (all do — this audit found no orphaned
frontend call), whether it persists to the database, what RBAC guard the
backend applies, and whether a backend test exercises it today.

Legend for **RBAC**:
- `get_current_user` — any authenticated user (admin/doctor/instructor)
- `require_admin` — admin role only
- `require_admin` + org-scope check — admin role, then further checked
  against `AdminScope` (a scope-restricted admin can be narrowed or blocked)
- `require_admin` + unrestricted-only — admin role, and only an
  **unrestricted** admin (zero `AdminScope` rows) may proceed
- `require_admin` (device toggle) — see the AC/light/plug note below

**Persists DB?** — "Yes" means the action is a real write through
SQLAlchemy/`db.commit()`. "Read" means the action only queries data (listed
for completeness, not because "persists" applies).

---

## 1. Login / Auth (`pages/Login.jsx`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Sign in | `api.login` | POST | `/api/auth/login` | Yes | Read | none (public) | Yes — `test_auth.py` |
| Forgot password → send request | `api.forgotPassword` | POST | `/api/auth/forgot-password` | Yes | Yes | none (public) | No dedicated test file |
| Poll reset status | `api.checkPasswordResetStatus` | GET | `/api/auth/forgot-password/status` | Yes | Read | none (public, token-gated) | No dedicated test file |
| Set new password after approval | `api.resetPassword` | POST | `/api/auth/reset-password` | Yes | Yes | none (public, token-gated) | No dedicated test file |

**Gap found:** `auth.py`'s forgot-password/status/reset-password flow and
all of `password_resets.py` (approve/deny) have **no backend test file** —
no `test_password_reset*.py` exists in `backend/tests/`. This is real,
security-relevant flow (it sets a password) that is currently only
verified by manual/browser testing, not automated. Flagging rather than
silently marking it "tested."

## 2. Force Password Change (`pages/ForcePasswordChange.jsx`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Save and continue | `api.changePassword` | PATCH | `/api/users/me/password` | Yes | Yes | `get_current_user` (self only) | Indirectly — no dedicated test asserting `must_change_password` clears |

## 3. Command Center (`components/CommandCenter.jsx`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Poll summary (5s) | `api.getCommandCenterSummary` | GET | `/api/command-center/summary` | Yes | Read | `require_admin` | Yes — `test_command_center.py` |

Door-name links only navigate locally (open Room Profile) — no separate API call.

## 4. Main Doors (`pages/Dashboard.jsx` + `components/DoorCard.jsx`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Poll doors + alerts (5s) | `api.listDoors`, `api.listAlerts` | GET | `/api/doors`, `/api/alerts` | Yes | Read | `get_current_user`; alerts additionally scope-filtered to `[]` for a restricted admin | Yes — `test_doors.py`, `test_alerts.py`, `test_alerts_scope.py` |
| Import from Excel | `api.importDoors` | POST | `/api/doors/import` | Yes | Yes | `require_admin` | Yes — `test_doors.py` |
| Add Door / Add Room (save) | `api.createDoor` | POST | `/api/doors` | Yes | Yes | `require_admin` | Yes — `test_doors.py` |
| Lock / Unlock | `api.overrideDoor` | POST | `/api/doors/{id}/override` | Yes | Yes | `require_admin` | Yes — `test_doors.py` |
| Mark Online/Offline | `api.setDoorStatus` | POST | `/api/doors/{id}/status` | Yes | Yes | `require_admin` | Yes — `test_doors.py`, `test_staleness_watchdog.py` |
| Request Access | `api.requestDoorAccess` | POST | `/api/doors/{id}/request-access` | Yes | Yes (creates an Alert) | `get_current_user` | Yes — `test_doors.py` |
| History (load logs) | `api.doorLogs` | GET | `/api/doors/{id}/logs` | Yes | Read | `get_current_user` | Yes — `test_doors.py` |
| Delete door | `api.deleteDoor` | DELETE | `/api/doors/{id}` | Yes | Yes | `require_admin` | Yes — `test_doors.py` |
| Resolve alert (AlertBanner) | `api.resolveAlert` | PUT | `/api/alerts/{id}/resolve` | Yes | Yes | `require_admin`; blocked (403) for a scope-restricted admin | Yes — `test_alerts.py`, `test_alerts_scope.py` |

## 5. Access Service / Room Profile (`components/RoomProfile.jsx` + children)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Toggle AC | `api.toggleAc` | POST | `/api/doors/{id}/ac` | Yes | Yes | `get_current_user` (any authenticated role — see note) | Partial — covered incidentally, no dedicated AC-toggle test |
| Toggle light | `api.toggleLight` | POST | `/api/doors/{id}/light` | Yes | Yes | `get_current_user` | Partial — same as above |
| Toggle plug | `api.togglePlug` | POST | `/api/doors/{id}/plugs/{plugId}` | Yes | Yes | `get_current_user` | Partial |
| Add plug | `api.addPlug` | POST | `/api/doors/{id}/plugs` | Yes | Yes | `require_admin` | No dedicated test found |
| Remove plug | `api.deletePlug` | DELETE | `/api/doors/{id}/plugs/{plugId}` | Yes | Yes | `require_admin` | No dedicated test found |
| Mark Occupied/Vacant | `api.setOccupancy` | POST | `/api/doors/{id}/occupancy` | Yes | Yes | `require_admin` | Yes — `test_energy_timeseries.py`, `test_occupancy_confidence.py` |
| Emergency override — create | `api.createEmergencyOverride` | POST | `/api/doors/{id}/emergency-override` | Yes | Yes | `require_admin` | Yes — `test_emergency_overrides.py` |
| Emergency override — revoke | `api.revokeEmergencyOverride` | POST | `/api/emergency-overrides/{id}/revoke` | Yes | Yes | `require_admin` | Yes — `test_emergency_overrides.py` |
| Access window — create/update/delete | `api.createAccessWindow` / `updateAccessWindow` / `deleteAccessWindow` | POST/PUT/DELETE | `/api/access-windows[/{id}]` | Yes | Yes | `require_admin` | Yes — `test_access_windows.py` |
| Door anomalies (view) | `api.getDoorAnomalies` | GET | `/api/doors/{id}/anomalies` | Yes | Read | `require_admin` | Yes — `test_anomaly_detection.py` |
| Staff anomalies (view) | `api.getStaffAnomalies` | GET | `/api/staff/{id}/anomalies` | Yes | Read | `get_current_user` | Yes — `test_anomaly_detection.py` |

**Note (AC/light/plug RBAC):** `toggle_ac`/`toggle_light`/`toggle_plug`
only require `get_current_user`, not `require_admin` — meaning a doctor or
instructor with the dashboard open could toggle a room's AC/light/plug.
This was an intentional, pre-existing design choice from the room-controls
feature (rooms are meant to be usable by whoever is legitimately in them),
not a Phase 9 finding of broken RBAC — flagging only so it's a documented
decision, not an assumption.

## 6. Smart Building (`components/smart-building/*`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Poll zones/automation/logs/sensors/schedules | `listZones`, `getAutomationSummary`, `listAutomationLogs`, `listSensors`, `listZoneSchedules` | GET | `/api/zones`, `/api/automation/summary`, `/api/automation/logs`, `/api/sensors`, `/api/zone-schedules` | Yes | Read | `get_current_user` | Partial — engine logic well-tested (`test_automation_engine.py`, `test_automation_rules.py`), but these specific list endpoints have no direct test |
| Run automation pass now | `api.runAutomationOnce` | POST | `/api/automation/run-once` | Yes | Yes (writes AutomationLog/state) | `require_admin` | Yes (indirectly) — `test_automation_engine.py` exercises the same engine function |
| Add zone | `api.createZone` | POST | `/api/zones` | Yes | Yes | `require_admin` | **No test found** for zone CRUD directly |
| Update zone | `api.updateZone` | PUT | `/api/zones/{id}` | Yes | Yes | `require_admin` | **No test found** |
| Delete zone | `api.deleteZone` | DELETE | `/api/zones/{id}` | Yes | Yes | `require_admin` | **No test found** |
| Add sensor | `api.createSensor` | POST | `/api/zones/{id}/sensors` | Yes | Yes | `require_admin` | Partial — `test_hardening_constraints.py` creates sensors as fixtures, not testing the endpoint's own rules |
| Simulate sensor reading | `api.reportSensorReading` | POST | `/api/sensors/{id}/reading` | Yes | Yes | `require_admin` | Yes (indirectly) — `test_occupancy_confidence.py` |
| Delete sensor | `api.deleteSensor` | DELETE | `/api/sensors/{id}` | Yes | Yes | `require_admin` | **No test found** |
| Add device | `api.createDevice` | POST | `/api/zones/{id}/devices` | Yes | Yes | `require_admin` | Partial — used as a fixture in `test_hardening_constraints.py` |
| Toggle device on/off | `api.setDeviceStatus` | POST | `/api/devices/{id}/status` | Yes | Yes | `require_admin` | Yes (indirectly) — `test_hardening_constraints.py` |
| Toggle device automatic control | `api.updateDevice` | PUT | `/api/devices/{id}` | Yes | Yes | `require_admin` | **No test found** |

**Gap found:** Zone/Sensor/Device basic CRUD (create/update/delete) has
**no dedicated test file** — `test_hardening_constraints.py`,
`test_automation_engine.py`, and `test_occupancy_confidence.py` use these
models as setup fixtures for testing the *automation engine's* behavior,
not the CRUD endpoints' own validation/RBAC. Functionally these routes
work (used constantly through the fixtures), but their own edge cases
(e.g. deleting a zone with devices still attached, invalid zone_type) are
unverified by an automated test.

## 7. Academic Administration (`components/academic/*`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Create/update/delete College | `createFaculty`/`updateFaculty`/`deleteFaculty` | POST/PUT/DELETE | `/api/faculties[/{id}]` | Yes | Yes | `require_admin` + org-scope check | Yes — `test_org_hierarchy.py`, `test_academic_admin_depth.py`, `test_phase8_persistence.py` |
| Create/update/delete Department | `createDepartment`/`updateDepartment`/`deleteDepartment` | POST/PUT/DELETE | `/api/departments[/{id}]` | Yes | Yes | `require_admin` + org-scope check | Yes — same files |
| Create/update/delete Course | `createCourse`/`updateCourse`/`deleteCourse` | POST/PUT/DELETE | `/api/courses[/{id}]` | Yes | Yes | `require_admin` + org-scope check | Yes — `test_academic_admin_depth.py`, `test_phase8_persistence.py` |
| Assign/update/remove Course Assignment | `assignStaffToCourse`/`updateCourseAssignment`/`removeCourseAssignment` | POST/PUT/DELETE | `/api/courses/{id}/assignments[/{id}]` | Yes | Yes | `require_admin` + org-scope + same-department/college business rules | Yes — `test_academic_admin_depth.py`, `test_phase8_persistence.py`, `test_schedules.py` (schedule-filter contract) |
| Create staff (doctor/TA) | `api.createUser` | POST | `/api/users` | Yes | Yes | `require_admin` | Yes — `test_org_hierarchy.py`, `test_users_scope_gaps.py` |
| Update staff academic profile | `api.updateStaffProfile` | PUT | `/api/users/{id}/staff-profile` | Yes | Yes | `require_admin` + `require_staff_access` | Yes — `test_academic_admin_depth.py`, `test_phase8_persistence.py` |
| Delete staff | `api.deleteUser` | DELETE | `/api/users/{id}` | Yes | Yes (cascade/nullify) | `require_admin` + `require_staff_access` | Yes — `test_delete_user.py`, `test_users_scope_gaps.py` |
| Load door assignments (Staff Profile) | `api.listDoorAssignments` | GET | `/api/users/{id}/doors` | Yes | Read | `require_admin` | Yes — `test_users_scope_gaps.py` |

All Academic Administration mutations refetch from the backend after
success (no local-state-only mutation) — verified by code inspection of
`onCreated`/`onChanged`/`load()` callbacks in every component in this
directory.

## 8. Account Menu (`components/AccountMenu.jsx`)

| Action | Frontend fn | Method | Endpoint | Backend exists | Persists DB | RBAC | Tested |
|---|---|---|---|---|---|---|---|
| Change photo | `api.uploadPhoto` | POST | `/api/users/me/photo` | Yes | Yes | `get_current_user` (self) | No dedicated test found |
| Update name/email | `api.updateProfile` + `api.refreshToken` | PATCH + POST | `/api/users/me/profile` + `/api/auth/refresh` | Yes | Yes | `get_current_user` (self) | No dedicated test found |
| Change own password | `api.changePassword` | PATCH | `/api/users/me/password` | Yes | Yes | `get_current_user` (self) | No dedicated test found |
| List/Approve/Deny password reset requests | `listPasswordResets`/`approvePasswordReset`/`denyPasswordReset` | GET/POST/POST | `/api/password-resets[/{id}/approve\|deny]` | Yes | Yes | `require_admin` | **No test found** (see Section 1 gap) |
| Manage buildings — list/create/delete | `listBuildings`/`createBuilding`/`deleteBuilding` | GET/POST/DELETE | `/api/buildings[/{id}]` | Yes | Yes | `get_current_user` (list) / `require_admin` (create/delete) | **No test found** |
| Energy & checkout — view/save settings | `getSystemSettings`/`updateSystemSettings` | GET/PUT | `/api/system/settings` | Yes | Yes | `get_current_user` (view) / `require_admin` (save) | **No test found** |
| Run checkout sweep now | `api.runCheckoutSweep` | POST | `/api/system/run-checkout-sweep` | Yes | Yes | `require_admin` | **No test found** |
| Add admin | `api.createUser` (role: admin) | POST | `/api/users` | Yes | Yes | `require_admin` | Yes — `test_org_hierarchy.py`/`test_users_scope_gaps.py` cover admin creation generally |

**Gap found:** `buildings.py` and the checkout/system-settings endpoints
in `energy.py` have **no backend test coverage at all** — every route in
this table marked "No test found" is exercised only by manual/UI use, not
CI. This is the single biggest testing gap surfaced by this audit.

## 9. Legacy `StaffPanel.jsx` — dead code

`StaffPanel.jsx` is fully wired to real API calls (`listFaculties`,
`listUsers`, `importUsers`, `createFaculty`, `createUser`,
`listDoorAssignments`, `deleteUser`, `removeDoorAssignment`,
`addDoorAssignment`) but **is not imported or rendered anywhere** in the
current `Dashboard.jsx` — it was superseded by `AcademicAdmin.jsx`'s
College→Department hierarchy in an earlier phase and appears to have been
left in the source tree rather than deleted. It is not part of any
reachable screen today, so it carries no live RBAC/persistence risk, but
it is unused code that should either be deleted or explicitly kept as a
documented fallback — flagging for your decision rather than deleting it
myself.

---

## Summary of findings (not fixed in this pass — audit only, per Phase 9 scope)

1. **No automated test coverage**: `password_resets.py` (approve/deny),
   the forgot-password/reset-password flow in `auth.py`, `buildings.py`
   (create/delete), and the checkout/system-settings endpoints in
   `energy.py`. These are all real, currently-working features — the gap
   is test coverage, not functionality.
2. **Partial test coverage**: Zone/Sensor/Device CRUD endpoints in
   `zones.py` are only exercised as fixtures inside automation-engine
   tests, not tested for their own validation/RBAC/edge cases.
3. **Dead code**: `StaffPanel.jsx` is unreachable from the current UI.
4. **Unused API client surface**: `api.getDoor`, `api.checkDoorAuthorization`,
   `api.listCredentials`, and the admin-scope/operational-scope CRUD
   methods (`listAdminScopes`, `createAdminScope`, `deleteAdminScope`,
   `listOperationalScopes`, `createOperationalScope`,
   `deleteOperationalScope`) have no UI control anywhere — the backend
   endpoints exist and are tested at the API level, but there is no admin
   screen to grant/revoke a scoped admin's college/department/operational
   scope, or manage credentials, from the dashboard itself. This is a real
   feature gap (the AdminScope model and its API are fully built per
   earlier phases, but administering it requires direct API calls, not a
   UI), not a bug — documented here rather than guessed at or silently
   built without your sign-off.
5. **Intentional, not-a-bug RBAC note**: room device toggles (AC/light/plug)
   are reachable by any authenticated role, not just admins — this matches
   the room-controls feature's original design intent (occupants control
   their own room), not an oversight.

No backend or frontend code was changed as part of this audit — Phase 9
was inspection and reporting only, as instructed.
