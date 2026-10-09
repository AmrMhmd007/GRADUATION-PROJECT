# Manual Demo / Smoke Test Checklist

Purpose: final runtime verification of the actual running application, on
your own machine, in a real browser. This is the one layer Phase 10 could
not reach (see `PHASE_10_FINAL_SYSTEM_AUDIT.md`, §11 — no browser
automation could reach your running instance from that session).

This document makes **no code changes** and requires none to use. Check
each box as you verify it. Where a box can't be checked, note what you saw
instead — that's a real finding, not a failure of the checklist.

**Before you start:**
- [ ] Backend running (`uvicorn`) with no startup errors in the terminal
- [ ] Frontend running (`npm run dev`) with no build errors in the terminal
- [ ] Browser DevTools Console open and visible for the entire session (you're watching for "no console errors" on every step below)
- [ ] Browser DevTools Network tab open (lets you confirm each action actually fires a request, and see its real status code)
- [ ] You have at least: one unrestricted admin login, one scoped-admin login (an admin with at least one AdminScope row — if you don't have one set up, create one via the API/DB directly, since there's no UI for it — see item 18 note), one doctor login, one instructor login

**Generic checks — apply these to EVERY numbered flow below, not just where repeated:**
- UI action works (click/submit does what it visually claims)
- Backend request actually fires (Network tab shows it) and succeeds (2xx) when it should
- Success or error message appears, and matches what actually happened (no success message on a failed request, no silent failure)
- Refreshing the page (hard reload) preserves the change — this is the real persistence test, not just "the UI updated"
- Unauthorized/scoped access behaves correctly where applicable (see each section's specific RBAC checks)
- Any dropdown/select only offers valid, real options (no placeholder/demo entries, no options that would 404 or 409 if picked)
- 409/403/422 errors show the backend's actual message, not a generic "Something went wrong"
- No new console errors appear (warnings from React dev mode itself are expected and fine — an actual red error is not)
- No fake/demo/hardcoded data appears anywhere (every number, name, and status on screen should trace back to something you actually created or that's genuinely in the database)

---

## 1. Login / Authentication

- [ ] Valid admin login succeeds, lands on the dashboard
- [ ] Wrong password shows a real error (not a blank screen or crash)
- [ ] Unknown email shows the same generic "incorrect email or password" (should NOT reveal whether the email exists)
- [ ] After ~5 failed attempts on the same account, a lockout message appears (rate limiting) — try the correct password during lockout and confirm it's still rejected until the lockout window passes
- [ ] A different account can still log in while the first is locked out (lockout is per-account)
- [ ] Refresh the page after login — session persists (token in localStorage), you're not bounced back to login
- [ ] Log out, confirm you're returned to the login screen and can't navigate back into the dashboard via browser back-button

## 2. Command Center

- [ ] Loads with real, current numbers (not zeros-that-look-fake or obviously stale data)
- [ ] Data refreshes automatically every ~5s (watch the Network tab for repeated polling requests)
- [ ] As a doctor or instructor, Command Center is not accessible (admin-only) — confirm you get blocked, not a broken/blank admin view
- [ ] As a **scoped** admin, confirm what actually renders — Phase 10 found Command Center is `require_admin` only with no further org-scope filtering, so a scoped admin should see the same full summary as an unrestricted admin. Confirm this matches what you see (if it doesn't, that's a real finding to report back, not something to fix yourself)

## 3. Academic Admin (landing page)

- [ ] Landing view shows real colleges with real rollup counts (departments/doctors/TAs/courses) — cross-check one college's numbers against what you know is actually in the DB
- [ ] Search box filters colleges by name/code correctly, with no lag or stale results
- [ ] Status filter (Active/Inactive/All) actually filters — create or toggle one college to Inactive and confirm it disappears/appears correctly under each filter option
- [ ] "+ Add College" form: submit with empty name → validation error, no college created (check Network tab confirms no 201, or a 400 with a proper message)
- [ ] Add a real college, confirm it appears immediately (no manual refresh needed) and persists after a hard reload
- [ ] Edit a college's name/code/description inline, confirm it persists after hard reload
- [ ] Toggle Activate/Deactivate, confirm the status pill updates and persists after hard reload
- [ ] Try creating a duplicate college name (if that's blocked server-side) or any other known conflict — confirm the 409 message is the real backend text, not generic

## 4. College → Department

- [ ] Clicking a college drills into its departments — confirm the college's own name/code/description header is correct (not the wrong college's data)
- [ ] Department cards show real counts (doctors/TAs/courses) matching what's actually assigned
- [ ] Add/Edit/Activate-Deactivate a department — same persistence checks as College (§3)
- [ ] Delete a department that has staff/courses in it — confirm you get a 409 with the real dependency message ("still has N staff, N courses..."), and the department is NOT deleted
- [ ] Delete an empty department — confirm it succeeds and disappears after refresh
- [ ] "← All colleges" back-navigation returns to the correct, unfiltered college list

## 5. Department → Staff

- [ ] Doctors/Instructors tab and Teaching Assistants tab are clearly separate (not one mixed list) — confirm the tab you're on only shows the correct role
- [ ] Search by name/email/staff_id works on the staff list
- [ ] Academic-title filter dropdown only lists the 6 real titles (Professor, Associate Professor, Assistant Professor, Lecturer, Instructor, Teaching Assistant) — no extra/fake options
- [ ] Status filter (Active/Inactive) works
- [ ] "+ Add Doctor"/"+ Add TA" creates a real user — confirm it appears in the correct tab only, and that the OTHER department's staff list is unaffected
- [ ] Staff card shows role AND academic title as visibly separate pieces of information (not conflated into one label)

## 6. Staff Profile edit

- [ ] Opening a staff profile shows real data: name, email, staff_id, academic_title, specialization, phone, status, assigned courses, assigned doors
- [ ] "Edit profile" form lets you change staff_id/academic_title/specialization/phone/status
- [ ] Academic-title dropdown in the edit form is restricted to the same 6 real values — try to confirm there's no way to type/select a 7th
- [ ] Save, confirm the profile reflects the change immediately, and after a hard reload
- [ ] Try setting a staff_id that's already used by another staff member — confirm a 409 with a real message, and the value is NOT saved
- [ ] "Remove Doctor/TA" shows a confirmation dialog before deleting (not an instant delete)
- [ ] Confirm deletion actually removes the user — reopen the department's staff list and confirm they're gone after refresh
- [ ] If you delete a staff member who has course assignments or door assignments, confirm the app doesn't crash and those related rows are handled sensibly (cascaded/nullified, not left dangling in a way that breaks other screens)

## 7. Courses

- [ ] Course table shows real courses with code/name/credit hours/level/semester/status
- [ ] Search by code/name works; status filter works
- [ ] "+ Add Course": try credit_hours = 0 or a negative number — confirm it's rejected (both by the form itself AND if you bypass the form via Network tab replay, by the backend with a 422/400)
- [ ] Add a valid course, confirm it appears and persists after reload
- [ ] Edit a course's fields, confirm persistence
- [ ] Try creating a duplicate course code within the same department — confirm the real 409 message
- [ ] Delete a course that has assignments — confirm the 409 dependency message, course NOT deleted
- [ ] Delete a course with no assignments — confirm it succeeds

## 8. Course Assignment

- [ ] Opening "Assignments" on a course shows a real, correctly-scoped table (only assignments for THIS course)
- [ ] "+ Add Assignment" staff dropdown shows enough detail to disambiguate (name, staff_id, role, academic_title, department) and only lists real staff — not staff from unrelated departments/colleges (if it does list them, confirm what happens next, since the backend is supposed to reject a cross-department assignment)
- [ ] Deliberately try to assign a staff member from a DIFFERENT department to this course — confirm you get the real backend 409 text (something like "...belongs to a different department...") displayed as-is, not swallowed or genericized
- [ ] Same test for a different COLLEGE (staff with no department set but a different faculty_id)
- [ ] Assign a valid, same-department staff member — confirm success, and the assignment appears with section/semester/academic_year as entered
- [ ] Edit an assignment (section/semester/status), confirm persistence
- [ ] Delete an assignment, confirm it disappears and persists after reload
- [ ] Confirm the assignment's Room/Schedule column shows real room info ONLY when a schedule was actually linked — otherwise shows "—", not a fake placeholder room

## 9. Schedule filtering

- [ ] In the Course Assignment add/edit form, the Schedule dropdown lists real schedules with real day/time/room labels (e.g. "Monday 09:00–10:00 · Room 101 (R101)")
- [ ] **Known limitation to specifically confirm, not fix**: per Phase 10.1/9.1, there is currently no UI path to actually LINK a schedule to a course (`course_ref_id` can only be set directly in the DB today) — so expect every schedule in the dropdown to show up regardless of course, since none of them will have a real `course_ref_id` set yet unless you've set one directly in the DB. Confirm this matches what you see (all schedules appear, none pre-filtered) rather than being surprised by it.
- [ ] If you DO have a schedule with `course_ref_id` set (e.g. via direct DB edit for testing), confirm that when viewing a DIFFERENT course's assignment form, that schedule is correctly excluded from the dropdown
- [ ] Deliberately pick a schedule already linked to a different course (if one exists) and confirm the backend still rejects it with a 409 even if it somehow appeared in the dropdown

## 10. Doors

- [ ] Main Doors list shows real doors with correct online/offline, locked/unlocked status
- [ ] Add a door (with/without AC, light, plugs enabled) — confirm it appears and persists
- [ ] Lock/Unlock a door — confirm the status visibly changes and persists after reload
- [ ] Mark a door Online/Offline manually — confirm persistence
- [ ] Delete a door, confirm it's gone after reload
- [ ] View door History/logs — confirm entries are real recorded events, not placeholder rows
- [ ] As a doctor/instructor: confirm you CAN toggle AC/light/plug on a room (this is intentional per Phase 10 — not a bug if it works), but CANNOT create/delete a door or lock/unlock it (admin-only) — confirm the blocked actions show a 403, not a silently-ignored click
- [ ] **Known limitation to confirm, not fix**: as a scoped admin, doors have no organizational scope model — confirm a scoped admin sees/controls the SAME full door list as an unrestricted admin (this is documented as intentional in Phase 10, not something to expect to be restricted)

## 11. Access Windows

- [ ] From a staff profile, view their Scheduled Access / Access Windows section — confirm entries are real, not placeholders
- [ ] Add a recurring window (day/time) and a temporary/one-off window (start/end datetime) — confirm both save correctly and the form doesn't let you mix recurring + one-off fields incoherently
- [ ] Edit and delete a window, confirm persistence
- [ ] As a doctor/instructor, confirm you can only ever see YOUR OWN access windows, never another staff member's, if there's any self-service view of this
- [ ] As a scoped admin, confirm you can only manage windows for staff within your authorized scope — try (if possible) to access a window for a staff member outside your scope and confirm a 403/404, not silent success

## 12. Emergency Override

- [ ] Create an emergency override on a door (lock or unlock) — confirm it requires the two-step confirm (not a single accidental click)
- [ ] Confirm the override actually changes the door's real-time state
- [ ] Try creating a SECOND active override on the same door before revoking the first — confirm the backend blocks this (one-active-override-per-door) with a real message
- [ ] Revoke the override, confirm the door returns to normal automated control and the override no longer shows as active after reload
- [ ] As a doctor/instructor, confirm this entire feature is inaccessible (admin-only)
- [ ] **Known limitation to confirm, not fix**: per Phase 10, emergency overrides have NO organizational scope check at all — confirm a scoped admin can create/revoke an override on ANY door, not just ones in their scope. This is documented as intentional (doors have no scope model), not something to expect blocked.

## 13. Alerts

- [ ] Real alerts appear (from actual door/sensor/automation events) — not fabricated demo alerts
- [ ] Resolve an alert, confirm it moves out of the active list and stays resolved after reload
- [ ] As a **scoped** admin, confirm the alerts list is genuinely EMPTY (`[]`) — this is documented as intentional in Phase 10 (no safe scope mapping exists for alerts), not a bug if the list is blank
- [ ] As a scoped admin, try to resolve an alert anyway (e.g. by replaying a Network request if you have alert IDs from elsewhere) — confirm you get a 403
- [ ] As a doctor/instructor, confirm Alerts aren't accessible at all

## 14. Audit Logs

- [ ] As an **unrestricted** admin, confirm the audit log list loads with real entries (logins, creates, updates, deletes you've actually performed during this test session should show up)
- [ ] Spot-check a few entries: actor name/email/role, action, resource type/id/label, result (success/failure), timestamp all look correct and match something you actually did
- [ ] Confirm there is NO way to edit or delete an audit log entry from the UI (no edit/delete controls should exist on this screen at all)
- [ ] As a **scoped** admin, confirm Audit Logs are completely inaccessible (403) — this is documented as intentional (unrestricted-admin-only), not a bug
- [ ] As a doctor/instructor, confirm Audit Logs aren't accessible at all
- [ ] Trigger a failed login on purpose, then check as unrestricted admin that a `login_failed` entry appears with no actor name attached (since the login itself failed) but the attempted email is visible

## 15. Password Reset

- [ ] From the login screen, use "Forgot password" with a real registered email — confirm you land on a waiting screen with no password shown to you
- [ ] As admin, open the pending password-reset requests panel — confirm the request appears
- [ ] Approve it — confirm the waiting browser (poll it or refresh the status) now shows the "set new password" step
- [ ] Set a new password — confirm you can then log in with the NEW password and NOT the old one
- [ ] Try reusing the same reset link/token again after it's been used — confirm it's rejected, not silently accepted
- [ ] Start a new forgot-password request and have an admin DENY it — confirm the requesting browser reflects the denial and cannot set a new password
- [ ] As a doctor/instructor, confirm you cannot approve/deny anyone's reset request (403)
- [ ] **Known limitation to confirm, not fix**: password reset approve/deny has no organizational scope check — confirm a scoped admin can approve/deny ANY user's reset request, not just staff in their scope. Documented as intentional in Phase 10.

## 16. Buildings

- [ ] Buildings list (from the account menu's "Manage Buildings") shows real buildings
- [ ] Add a building, confirm it appears in the Add-Door building dropdown immediately
- [ ] Try adding a duplicate-named building — confirm it doesn't create a second row (returns the existing one)
- [ ] Try deleting a building that has doors assigned to it — confirm a 400 with the real dependency message ("N doors still use..."), and it's NOT deleted
- [ ] Delete an unused building, confirm it's gone after reload
- [ ] As a doctor/instructor, confirm you can view but not create/delete buildings

## 17. Smart Building

- [ ] Zones list shows real zones with correct occupancy state (Occupied/Empty/Verifying/Unknown) — confirm this isn't stuck on a fake/placeholder state
- [ ] Add a zone, confirm it appears and persists
- [ ] Open a zone's detail modal — confirm sensors/devices listed are real, and "Simulate occupied/empty" actually changes the zone's state over the next automation pass (or immediately, depending on implementation)
- [ ] Add a sensor and a device to a zone, confirm both persist
- [ ] Toggle a device on/off, confirm it persists
- [ ] "Run pass now" triggers a real automation pass — check the Automation Log feed for a new real entry afterward, not a stale one
- [ ] Delete a zone that has sensors/devices — confirm they're cascaded away too (not left orphaned causing errors elsewhere)
- [ ] As a doctor/instructor, confirm you can view but not mutate zones/sensors/devices
- [ ] **Known limitation to confirm, not fix**: Zones/Sensors/Devices/Buildings have no organizational scope model — confirm a scoped admin has the same full access as an unrestricted admin here. Documented as intentional in Phase 10.

## 18. Account / Profile Settings

- [ ] Update your own name — confirm it persists and reflects everywhere your name is shown (topbar, audit log actor name on your next action, etc.)
- [ ] Update your own email — confirm you're prompted/forced through a token refresh (or automatically handled) and that logging in with the OLD email now fails while the NEW one works
- [ ] Change your own password — confirm old password no longer works, new one does
- [ ] Upload a profile photo — confirm it displays immediately and after reload; try an invalid file type (e.g. a .txt renamed to look like an upload) and confirm it's rejected; try an oversized file (>5MB) and confirm it's rejected
- [ ] Confirm none of these self-service actions affected any OTHER user's account (spot check another account's name/email/password is unchanged)
- [ ] **Known feature gap to confirm, not fix**: there is currently no dashboard screen to manage AdminScope/OperationalScope grants (i.e., no UI to make an admin "scoped" to a college/department, or to grant infrastructure scopes) — this has to be done via direct API/DB access today. Confirm this is indeed missing from the Account menu / anywhere else in the UI, matching Phase 10's documented finding, rather than assuming it's hidden somewhere you haven't looked.

---

## After completing all 18 sections

- [ ] Note every checkbox you could NOT check, and why (blocked by a real bug vs. blocked by a known/documented limitation above)
- [ ] Note any console error you saw that isn't accounted for in this checklist
- [ ] Note any screen where a number/label looked suspicious (e.g. always zero, always the same value regardless of what you did) — that's worth flagging even if you can't tell yet whether it's fake data or just correctly quiet

Report back what you find — genuine bugs found this way should be fixed
deliberately (Phase 11+), not folded into this checklist. This document
only tells you what to look at; it doesn't fix anything on its own.
