# Security limitations register

*As of 2026-11-15, repository HEAD `e078a20` (local, not pushed). This lists what the system does **not** protect against today, so that nobody relies on a control that is not there. Items were read from the code; "mitigation" names only what exists in the code and the tests that cover it. No external penetration test has been done. Nothing was verified on a live MQTT broker, on hardware, on PostgreSQL, in a browser or in production.*

Severity is the author's judgement for a **shared or deployed** instance, not a score from a standard.

## 1. Messaging and devices

| ID | Limitation | Impact | What exists today | Severity |
|---|---|---|---|---|
| SEC-01 | **MQTT authentication is warn-only.** `MQTT_AUTH_MODE=warn` (default) verifies signed messages and records findings but still processes everything exactly as before. `enforce` is implemented and unit tested but is off, and has never been run against a live broker. | A forged, replayed or unsigned message is accepted and acted on (a security event is recorded). Warn mode protects nothing yet. | HMAC-SHA256 envelope, constant-time compare, timestamp window, persisted nonces, per-device scope, `device_security_events`. 34 tests (`test_device_auth`). Unknown values of the setting fall back to `warn`, never to `enforce`. | High |
| SEC-02 | **Shared broker credentials.** The backend and every node use the single `MQTT_USERNAME`/`MQTT_PASSWORD` pair (or none: the default broker setup in the docs is unauthenticated). There are no per-device broker logins and no topic ACLs in the repository. | Anyone who can connect can publish to or read any topic, including other rooms'. TLS protects the wire, not who is publishing. | Optional TLS flag (`MQTT_USE_TLS`); firmware has a CA-certificate slot. Application-level device scope exists only in warn mode (SEC-01). | High |
| SEC-03 | **Backend commands and decisions are unsigned.** Door overrides (`site/{code}/cmd`), AC/light/plug commands, device commands, the Face ID decision (`face/decision`) and automation decisions are published as plain JSON. | A node cannot tell a genuine command or GRANT from a forged one. A node that unlocks on a forged `GRANT` would open a door. | Node-side logic is a prototype; the backend still makes the decision. Nothing in this repository verifies commands on the device side. | High |
| SEC-04 | **The MQTT `face/verify` and `face/ack` path has no node credential at all.** Only the HTTP route uses the shared `X-Node-Key`; the MQTT path identifies the door by the topic only. | Anyone able to publish on that topic can submit a probe or an unlock confirmation for a door. `decide()` still applies the full authorization check, but the probe and the "physically unlocked" confirmation are unauthenticated. | `face_service.decide` is unchanged and denies on every failure path. Device-auth scope would cover `face_verify`/`face_ack` once enforced. | High |
| SEC-05 | **Shared door-node key.** One `FACE_NODE_API_KEY` is used by all nodes for the HTTP node endpoints (empty = endpoints disabled with 403). | A leaked key works for every door; no per-node revocation. | Constant-time compare; disabled by default. The device registry is the intended replacement and is not wired to these routes. | Medium |
| SEC-06 | **The backend trusts the door node's reported result.** For `site/{code}/event`, the node's `result` ("granted"/"denied") is recorded and a granted event unlocks the door's state; the backend's own authorization is stored as evidence beside it, not used to overrule it. | A compromised or forged node message can record a grant. | The evidence snapshot shows when the node's result and the backend's evaluation disagree. | Medium |
| SEC-07 | **Forged sensor data can influence automation.** While SEC-01 and SEC-02 stand, a forged occupancy or telemetry message is accepted. | A forged "empty" can start a shutdown verification; a forged "occupied" can block one. | Automation never switches off critical devices, treats stale or missing data as UNKNOWN, lets any fresh OCCUPIED win, and uses a verification window. These limit but do not remove the impact. | Medium |
| SEC-08 | **Device secrets are reversibly encrypted.** HMAC needs the raw secret, so it is stored Fernet-encrypted, not hashed. | A database copy together with `CREDENTIAL_ENCRYPTION_KEY` exposes every device secret. | Secrets are shown once, never logged or returned; encrypted at rest; rotation and revocation exist (rotation is immediate, no grace period). | Medium |
| SEC-09 | **Replay protection depends on device clocks.** Messages outside `MQTT_AUTH_MAX_SKEW_SECONDS` (120 s) are rejected, so a node with no reliable clock cannot authenticate yet. | Availability risk when `enforce` is eventually enabled. | Skew is configurable; findings are logged. | Low |
| SEC-10 | **Security events are recorded but not acted on.** Repeated identical findings are throttled into one row with a count; there is no alerting, no automatic revocation and no intrusion-detection logic. | An attack can run unnoticed unless someone reads `/api/device-security/events`. | Admin-only feed and summary endpoint. | Medium |

## 2. Cryptographic keys and stored secrets

| ID | Limitation | Impact | What exists today | Severity |
|---|---|---|---|---|
| SEC-11 | **Encryption key rotation is not supported.** One `CREDENTIAL_ENCRYPTION_KEY` encrypts card UIDs, Face ID templates and device secrets. There is no multi-key (key id) scheme and no re-encryption tool. Changing the key makes existing ciphertext unreadable. `CREDENTIAL_INDEX_KEY` is likewise fixed once credentials exist. | Cannot rotate after a suspected leak without losing stored credentials and templates; device secrets would have to be re-issued. | Invalid keys stop start-up with a secret-free message; an unset key only warns (a temporary key is used and data is lost on restart); a start-up check reports device secrets that cannot be decrypted. Procedure and warnings in `CONFIGURATION.md`. | Medium |
| SEC-12 | **Development fallbacks exist.** With no keys set, the code uses fixed development keys or a per-start key, and the default `JWT_SECRET` is a known string. | A deployment that skips configuration is insecure; only start-up warnings flag it. | Warnings that never print values. Not blocked. | Medium |

## 3. Face ID

| ID | Limitation | Impact | What exists today | Severity |
|---|---|---|---|---|
| SEC-13 | **Legacy REAL Face ID credentials need manual review.** Before Phase 1A, any logged-in user could submit their own embedding and have it stored as `REAL`. Such rows were not changed, downgraded or deleted by Phase 1C and **still count at the door** if their status is ENROLLED. | A user may hold a credential built from a vector of their own choosing, labelled REAL. | `review_face_credentials.py` lists them read-only (metadata only; highlights REAL and still ENROLLED, and self-enrolled). An admin can revoke through `POST /api/face/users/{id}/revoke` (audited). No automatic action. The real database has **not** been inspected. | High, until reviewed |
| SEC-14 | **SIMULATED Face ID enrolment is still open to any logged-in user.** `/api/face/me/enroll` now records only `SIMULATED` credentials (default and only accepted value), but they are still honoured by `face_service.decide`. The quality and liveness values are supplied by the client. | A user can enrol a vector they choose for themselves. Using it needs a probe delivered through a node endpoint (SEC-04, SEC-05), and access still requires the full authorization check. | REAL enrolment is refused with 403; `face_service.enroll` raises unless a (non-existent) trusted pipeline flag is passed; a test guards the list of write routes. No setting yet blocks SIMULATED credentials in production. | Medium |
| SEC-15 | **No liveness or anti-spoofing, and no real enrolment pipeline.** There is no server-side detection, embedding or capture; the embedding provider is `none`; no Raspberry Pi code exists. The YuNet and SFace models were examined but not integrated. | Face ID cannot be treated as secure identity verification. | Face ID is never a grant on its own. The threshold `FACE_MATCH_THRESHOLD=0.80` has not been calibrated on real faces. | High for any real use |

## 4. Accounts and web

| ID | Limitation | Impact | What exists today | Severity |
|---|---|---|---|---|
| SEC-16 | **Tokens cannot be revoked.** HS256 JWT with a shared secret, 60-minute life, `/refresh` re-issues; the token is kept in `localStorage`. No MFA. | A stolen token works until it expires; script injection into the dashboard could read it. | Short life; role and scope enforced on the server for every request. | Medium |
| SEC-17 | **Login lockout is in memory and per process.** | Resets on restart; not shared across processes; there is no general API rate limiting. | Lockout after repeated failures (`test_auth`). | Medium |
| SEC-18 | **CORS defaults to `*`.** Credentials are disabled, which limits the effect. | Any web origin can call the API with a token it holds. | Start-up warning; setting `ALLOWED_ORIGINS`. | Low |
| SEC-19 | **Sample accounts with known passwords.** `scripts/seed_db.py` creates documented sample users. | A deployment that keeps them is open. | Docs say to replace them. Not enforced. | Medium |

## 5. Platform

| ID | Limitation | Impact | What exists today | Severity |
|---|---|---|---|---|
| SEC-20 | **Backend dependencies use lower bounds only** (`>=`) with no lock file (the dashboard has `package-lock.json`), no vulnerability scanning and no external security review. | Builds are not reproducible; known-vulnerable versions are not detected. | None. | Low to Medium |
| SEC-21 | **Single-process design.** Background workers and the lockout state live inside the API process. | Running several processes duplicates workers and splits lockout state. | None. | Low |

## 6. What is and is not protected today (summary)

- **Protected, with tests (SQLite):** user authentication and scoped authorization, door authorization (who, where, when), audit logging, credential encryption at rest, the decision rule that Face ID never grants alone, and the refusal to create REAL Face ID credentials from client data.
- **Detected but not blocked:** unsigned, forged, replayed or out-of-scope device messages (warn mode).
- **Not protected:** the broker, backend-to-device messages, key rotation, token revocation, and anything that depends on hardware or on a real face pipeline.
