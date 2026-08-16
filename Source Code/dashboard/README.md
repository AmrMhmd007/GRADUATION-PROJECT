# Access Control Dashboard — Phase 4

React (Vite) admin dashboard implementing the wireframe from the Phase 1
System Design Document (Figure 5), wired to the real Phase 3 backend — not
a mockup with fake data.

## Setup

```bash
npm install
cp .env.example .env      # point VITE_API_BASE_URL at your backend if not localhost:8000
npm run dev
```

Requires the Phase 3 backend running (see backend/README.md) and seeded
with `python -m scripts.seed_db` so there's data to show. Login with the
seeded accounts: `admin@example.edu` / `admin123` (full access, including
door override and alert resolution) or `instructor@example.edu` /
`instructor123` (read-only — override/resolve controls are hidden, matching
the backend's role-based 403s).

## What's implemented

- Login against `POST /api/auth/login`, JWT stored in localStorage and
  decoded client-side to read the user's role (no separate "/me" endpoint
  exists yet — if one gets added, swap the decode for a real call).
- Door status grid polling `GET /api/doors` every 5s, styled per the
  wireframe (green/blue/amber status dots).
- Lock/unlock override calling `POST /api/doors/{id}/override`, admin-only
  in the UI (mirrors the backend's actual 403 behavior, not just cosmetic).
- Per-door history table calling `GET /api/doors/{id}/logs`.
- Alert banner from `GET /api/alerts?resolved=false` with a resolve action
  for admins (`PUT /api/alerts/{id}/resolve`).

## What's been verified

This was built against a running instance of the Phase 3 backend, not
developed against assumptions about its behavior:

- `npm run build` succeeds with no errors (checked in this environment).
- With the backend running locally and CORS enabled (see the note below),
  the exact request sequence the UI makes — login → list doors → override
  → fetch logs → list alerts → list doors again to confirm the status
  changed — was replayed directly against the live server and returned the
  expected data at every step.
- The JWT payload shape the login response actually returns was decoded
  and confirmed to match what `AuthContext.jsx`'s `decodeJwtRole()` expects
  (`{sub, role, exp}`).

Not yet verified: an actual rendered screenshot in a browser (no browser
automation was available in the build environment) and behavior against a
broker-connected backend (MQTT was disabled for these tests, same as
Phase 3's own test suite).

## Backend CORS

The Phase 3 backend now has `CORSMiddleware` enabled (permissive
`allow_origins=["*"]` for local development) — added specifically so this
dashboard, running on a different port/origin, can call it. Tighten that to
the real deployed dashboard origin before this goes anywhere near
production.

## Known scope limitations

- No client-side route protection beyond "is there a token" — an expired
  token shows API errors rather than redirecting cleanly to login. Fine for
  a Phase 4 prototype, worth hardening later.
- Schedule and user management screens aren't built yet; the backend
  endpoints exist (`/api/schedules`, `/api/users`) but there's no UI for
  them in this phase — only the dashboard's door/alert/log views from the
  wireframe were in scope here.
- No charts yet for historical trends (the wireframe's "Recent Access
  Events" is a table, matching what's built; a charted trend view would be
  a reasonable Phase 4 follow-up rather than a gap in what was asked for).
