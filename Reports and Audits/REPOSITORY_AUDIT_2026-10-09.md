# Repository audit — 2026-10-09

Scope: full first-time review of `GRADUATION PROJECT` (AIU Smart Campus). This report is **new**; older Phase 9–11 reports are historical and were not edited.

## 1. Initial condition (baseline, verified)
- Branch `main`, remote `origin` = github.com/AmrMhmd007/GRADUATION-PROJECT. Working tree was clean; **6 local commits ahead of origin/main** (confirmed). Recoverable baseline: tag `backup-before-audit-2026-10-09` and a git bundle of all refs (kept outside the repo).
- 403 tracked files. Ignored/untracked (not in git): `.env` files, `*.db`, `venv/`, `node_modules/`, `dist/`, `.pio/`, `secrets.h`, `__pycache__`, `backend.log` (root log confirmed ignored by `*.log`), trailer media.
- Secret scan of tracked files (key/token/password patterns, private keys, AWS ids): **no matches**.

## 2. Architecture discovered
See [`Documents/ARCHITECTURE.md`](../Documents/ARCHITECTURE.md): FastAPI backend (24 routers, 17 services), SQLAlchemy models, React/Vite dashboard, MQTT `site/{code}/…` and `university/…` topic trees, hardware abstraction layer, ESP32 firmware, RS-485 gateway, Face ID backend, simulated occupancy/energy.

## 3. Checks actually run
| Check | Result |
|---|---|
| Backend pytest, all 40 test files, serial, isolated copy, Python 3.10 | **All passed** (≈595 tests). Parallel runs (xdist) fail because every test shares one SQLite file — a test-design limitation, not a product defect |
| New tests `test_config_hardening.py` + `test_auth.py` after changes | 13 passed |
| Migration scripts: `create_all` on a temp DB, then all 22 `migrate_*.py`, twice | All succeed and are idempotent on a current-schema DB. **Not tested** against a legacy-schema database or PostgreSQL |
| Dashboard `npm ci`, `oxlint`, `vite build` (Node 22) | 0 errors, 14 warnings (React set-state-in-effect), build OK; main chunk 518 kB (>500 kB warning) |
| Gateway Python compile | OK |
| Firmware compile | **Not run** (PlatformIO unavailable) |
| Live MQTT / hardware / Raspberry Pi / browser flows | **Not run** |
| README relative-link check | Run (see section 7) |

## 4. Findings
**Confirmed**
1. Gateway source existed only inside `Archive/gateway_phase6.zip` — not in the working tree although the README described a gateway. *Fixed:* extracted to `Source Code/gateway/` (archive untouched).
2. README "Getting started" omitted creating the backend `venv` that `start.sh` requires. *Fixed.*
3. CORS hard-coded to `*`; JWT secret has a dev default; encryption key regenerates each start if unset. *Mitigated (backward compatible):* `ALLOWED_ORIGINS` env var; start-up warnings for insecure defaults (no secret values logged); documented in `.env.example` and README. Defaults unchanged.
4. All `migrate_*.py` hard-code `sqlite3.connect("access_control.db")` relative to the working directory and ignore `DATABASE_URL`. *Not changed* (22 scripts; documented).
5. `Trailer and Media/.../assets/ASSET_LICENSES.md` (third-party licence record) was swallowed by an ignore rule. *Fixed:* unignored.
6. `start.sh` kills any process on port 8000 and requires `venv`; `dashboard/package.json` has a macOS-only optional dependency (`@rolldown/binding-darwin-arm64`).
7. Four dashboard images (`campus-bg.jpg`, `campus-bg.png` — byte-identical, 6.9 MB each — `campus-building-bg.png`, `corridor-bg.png`) are not referenced by `src`; only `campus-building-bg2.png` is. *Retained* (not deleted without confirmation).
8. `Source Code/gateway/README.md` points to `door_node_firmware/include/rs485_protocol.h` and `door_node_firmware/tests/test_cross_lang.py`; neither exists in the tree (the firmware directory holds `config.h`, `secrets_example.h`, `src/main.cpp` only), so the RS-485 framing is not cross-checkable from this repository. *Documented; files not invented.*
9. Trailer tooling contains absolute `/Users/amrmohamed/...` paths (Blender bridge, recording tools); they need path updates after the folder moves.

**Unverified concerns / recommendations** (not confirmed defects): authorization-bypass review beyond the passing RBAC tests; MQTT payload validation depth; dependency CVE scan (no tool run); face-template handling under load; schema parity of old production databases.

## 5. Improvements made (files)
`Source Code/backend/app/config.py`, `app/main.py`, `.env.example`, `tests/test_config_hardening.py` (new), `Source Code/gateway/` (new, extracted), `.gitignore`, `README.md` (rebuilt), `Documents/ARCHITECTURE.md` (new), `Documents/SETUP.md` (new, manual setup verified from a clean `git archive`), this report.
Earlier in this session: folders reorganised (Reports and Audits, Hardware, Energy Impact Study, Trailer and Media, Archive).

## 6. Prioritised backlog
- **P0** — none confirmed. (Before any shared deployment: set real `JWT_SECRET`, keep encryption keys persisted, restrict `ALLOWED_ORIGINS`, enable MQTT auth/TLS.)
- **P1** — Restore or locate `rs485_protocol.h` and the cross-language test. No Raspberry Pi code in repo (Face ID edge). Firmware + gateway + backend never run together; add an automated end-to-end simulation using `gateway/tests/fake_node_sim.py` against a local broker. Adopt a real migration tool (Alembic) and make scripts honour `DATABASE_URL`.
- **P2** — Make tests parallel-safe (per-worker DB). Fix 14 oxlint warnings; code-split the 518 kB bundle. Make `start.sh` avoid killing unrelated processes and create the venv when missing. Remove the macOS-only optional dependency or make it platform-conditional. Update absolute paths in trailer tooling. Tighten API title/description ("Smart Building Access Control API v0.1.0").
- **P3** — Remove or reference the four unused 2–7 MB images (and consider Git LFS for large binaries — no history rewrite without approval). Add CI (GitHub Actions) for pytest, lint, build. Add directory index files.

## 7. Limits of this audit
Run in a Linux sandbox on a copy of the code; no Mac-side services, browser, hardware or broker. Passing tests show the tested behaviour, not overall security. Nothing was pushed to GitHub.

## 8. Follow-up changes (same day)
- Added `.github/workflows/ci.yml` (backend pytest serial on Python 3.10, dashboard lint+build on Node 22, gateway syntax check). YAML parsed locally; the workflow itself has **not run** yet — it runs after the first push.
- `start.sh` / `start_lan.sh`: create the venv and `.env` on first run; stop only a previous uvicorn on port 8000 and refuse to kill unrelated processes (backlog P2 item addressed; dry-run verified).
- Updated hard-coded `Desktop/AIU_SMART_CAMPUS_FINAL` paths in 20 Python scripts under `Trailer and Media/` (Blender bridge, recording tools, trailer builders) to the new location `Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL`, and quoted the path in the `cd` of `blender/human_entry/bridge/cmd.py` because the new path contains spaces. Syntax of all 20 files checked; the scripts themselves were **not re-run**. Markdown run-books and historical logs still show the old paths on purpose (they record what was run). Not changed and expected to need attention on the Mac: the git-ignored `recordings/software/.venv` embeds absolute paths and must be recreated; a running Blender session still watches the old bridge folder until `bridge.py` is reloaded from the new location.
- Migration/maintenance scripts (22 `migrate_*.py`, `seed_buildings.py`, `reset_admin_password.py`) now resolve the database through the new `Source Code/backend/db_path.py` instead of a hard-coded `access_control.db`: default behaviour unchanged, a `sqlite:///` `DATABASE_URL` is honoured, other URLs are refused with a message. Verified on temp databases: custom path run twice (0 failures), default path (0 failures), PostgreSQL URL refused. Not verified against a legacy-schema database. Finding 4 above is therefore fixed for SQLite; PostgreSQL still needs a real migration tool.
- Added `Source Code/gateway/tests/run_e2e_simulation.sh` and ran it (PASS): gateway publishes node status, backend marks A101/A102 seen; `POST /api/doors/{id}/override` (unlock) is delivered over MQTT, relayed by the gateway across a virtual RS-485 pair (socat) to a Python fake node, which applied it; the node's `card/granted` event and ack came back and the backend recorded both the override (`override/sent`) and the node event in `access_events`. Broker: pure-Python `amqtt` (mosquitto unavailable). **Limits:** fake node is Python, not ESP32 firmware; no real serial timing, TLS or authenticated MQTT; the backend's reaction to the ack topic was not checked beyond MQTT visibility. P1 backlog item 'end-to-end simulation' is therefore done; firmware-in-the-loop remains open.
- On the owner's explicit approval, removed the four unreferenced dashboard images (`campus-bg.jpg`, `campus-bg.png`, `campus-building-bg.png`, `corridor-bg.png`, ~17 MB) with `git rm`; they remain in git history and can be restored with `git checkout <earlier-commit> -- <path>`. The dashboard production build still succeeds afterwards (`campus-building-bg2.png`, the one referenced by `App.css`, was kept). Finding 7 is closed.
- `tests/conftest.py` now gives each pytest-xdist worker its own SQLite file (`test_access_control_<worker>.db`; unchanged name when run serially). With `pytest-xdist` installed the full suite (41 files) passed in parallel with `-n 4` (282 + 308 + 10 = 600 tests, run in three batches because of the sandbox time limit) and matches the serial count of 600 collected tests. `pytest-xdist` is optional and was not added to `requirements.txt`; CI stays serial. Backlog P2 'make tests parallel-safe' is done.
- Rewrote `Documents/SETUP.md` as a complete manual-setup guide and added `Documents/CONFIGURATION.md` (all 52 backend variables with defaults, secrets never shown). `.env.example` now lists the security keys and Face ID settings it was missing (as commented placeholders, no values). README quick start replaced with the verified commands. **Verification:** the quick start was run from a clean `git archive` (new venv, install, seed, API start, `npm install`, Vite dev server): backend `/docs` 200, dashboard `/` 200, login 200 with CORS headers. Not verified: Windows, PostgreSQL, `start.sh` end to end, mosquitto-based run.
