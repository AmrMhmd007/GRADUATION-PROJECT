# Device Identity and MQTT Message Authentication

Status: **Phase 1B, warn-only.** Implemented and unit/integration tested in
process. **Not** verified against a live MQTT broker, an ESP32, or a
Raspberry Pi. Enforcement mode exists in code but is **off by default and
not rolled out.**

## Purpose

Give every communicating node (ESP32, Raspberry Pi, gateway) its own
identity, secret, and explicit scope, so a message can be attributed to one
device and rejected if it is forged, altered, replayed, or outside that
device's scope. This is separate from user login (JWT) and from the shared
door-node `X-Node-Key` used by the Face ID HTTP routes.

## Registry

Table `device_identities` (new). `node_id` is the same id used by
`hardware_health` heartbeats. States: `ACTIVE`, `REVOKED`; an id with no
row is "unknown". Rows are never deleted.

Each identity lists, fail-closed (empty means nothing allowed):

- `message_types`: any of the kinds below
- `zone_ids`: zones it may publish into (university/... topics)
- `door_codes`: door codes it may publish for (site/... topics)

Message kinds: `door_status`, `door_event`, `door_alert`, `ac_status`,
`light_status`, `plug_status`, `legacy_occupancy_status`, `face_verify`,
`face_ack`, `sensor_telemetry`, `device_state`, `device_telemetry`,
`occupancy`, `occupancy_count`, `hvac_telemetry`, `health`.

Backend-to-device command topics (`.../cmd`, `.../command`) are never
authorized for a device and the backend does not subscribe to them.

Admin API (unrestricted admins only, audited, secrets never in audit text):

- `POST /api/device-identities` create (secret returned once)
- `GET /api/device-identities` and `GET /api/device-identities/{device_id}`
- `PUT /api/device-identities/{device_id}/scope`
- `POST /api/device-identities/{device_id}/rotate-secret` (secret returned once)
- `POST /api/device-identities/{device_id}/revoke`
- `GET /api/device-security/events` and `GET /api/device-security/summary`

## Wire format

JSON envelope as the MQTT payload (works with MQTT 3.1.1):

    {"auth":"aiu-hmac-v1","device_id":"esp-a1","ts":1731600000,
     "nonce":"<8-64 chars>","payload":"<original payload as string>",
     "sig":"<64 hex>"}

    sig = HMAC-SHA256(secret_bytes,
          "aiu-hmac-v1\n" + device_id + "\n" + topic + "\n" + ts + "\n"
          + nonce + "\n" + sha256_hex(payload_utf8))

The secret is 32 random bytes, delivered once as 64 hex characters. The
topic is part of the signature, so a captured message cannot be replayed on
another topic or zone. A message without the `aiu-hmac-v1` tag is a
**legacy** message and is never treated as authenticated.

Reference client: `device_auth_service.sign_message()`. An ESP32 or Pi client
must reproduce exactly this (mbedTLS or Python `hmac`).

## Checks, in order

1. Envelope well-formed, otherwise `MALFORMED_ENVELOPE`.
2. Known device, otherwise `UNKNOWN_DEVICE`.
3. Status `ACTIVE`, otherwise `REVOKED_DEVICE`.
4. Signature present (`MISSING_SIGNATURE`), then valid using a
   constant-time compare (`INVALID_SIGNATURE`; also covers a tampered
   payload or a wrong topic).
5. Timestamp within `MQTT_AUTH_MAX_SKEW_SECONDS` (`EXPIRED_TIMESTAMP`).
6. Authorization: message kind (`UNAUTHORIZED_TOPIC`), zone or door code
   (`UNAUTHORIZED_ZONE`), and any `node_id` in the payload must equal the
   registered one (`NODE_ID_MISMATCH`).
7. Nonce not seen before for this identity (`REPLAY_DETECTED`). The nonce is
   stored only after steps 1 to 6 pass, so unauthenticated traffic cannot
   fill the table.

Legacy messages are recorded as `LEGACY_UNSIGNED` (severity INFO).

## Modes

`MQTT_AUTH_MODE`:

- `off`: no inspection. Same as before Phase 1B.
- `warn` (default): verify and record structured events in
  `device_security_events`; process every message exactly as before. A failed
  or legacy message is handled like a legacy message always was. Nothing new
  is granted and every downstream control still runs (handler zone/sensor
  ownership checks, RBAC, automation safety rules, `face_service.decide`).
  A fault inside the screening code fails open in this mode.
- `enforce`: only verified, authorized messages are processed; everything
  else is dropped and recorded. A fault inside the screening fails closed.
  Any unrecognised value of the setting falls back to `warn`.

Other settings: `MQTT_AUTH_MAX_SKEW_SECONDS` (120),
`MQTT_AUTH_EVENT_THROTTLE_SECONDS` (300; repeated identical findings from one
source become one row with `suppressed_count`).

Events hold no payload, signature, nonce value, or secret.

## Suggested path to enforcement (not done)

1. Run in `warn`; register each real node; give it its secret.
2. Watch `/api/device-security/summary` until `LEGACY_UNSIGNED` and failures
   are zero for every registered source, over a period you choose.
3. Enable `enforce` on a staging broker first; test with real clients.
4. Add broker-level ACLs and per-device broker credentials (below).

## Known limitations

- Verified only in process; no live broker, no ESP32, no Raspberry Pi.
- The secret is stored Fernet-encrypted and must be decryptable by the
  backend. If `CREDENTIAL_ENCRYPTION_KEY` is unset, a temporary key is used
  and stored secrets become unreadable after a restart
  (`SECRET_UNAVAILABLE`). Set the key before registering devices.
- Rotation takes effect at once; there is no grace period, so a device must
  be updated at the same moment.
- Replay protection relies on device clocks being within the skew window; a
  node with no reliable clock cannot authenticate yet.
- Protects messages **to** the backend only. Backend-to-device commands and
  decisions are not signed, so a device cannot yet verify them.
- The broker itself still uses one shared username/password. Per-device
  broker credentials and topic ACLs are needed for real isolation and are not
  part of this change. TLS protects confidentiality on the wire, not
  identity of the publisher.
- An authenticated device is trusted only for what its scope allows; a
  compromised device can still send false but well-formed readings inside its
  own scope.
- No automatic revocation on repeated failures, and no alert routing yet.
- Face ID: this does not change `face_service.decide`; MQTT `face/verify` still
  goes through it unchanged.
