# Door Node Firmware — Phase 2 Prototype + Phase 5 Security + Phase 6 Multi-Node

Implements the state machine from the Phase 1 System Design Document (Figure 3)
for a single access-controlled door: card scan, optional biometric check,
lock actuation, door-state monitoring, tamper interrupt, and MQTT reporting.

## Setup

1. Install [PlatformIO](https://platformio.org/) (VS Code extension or CLI).
2. Copy `include/secrets_example.h` to `include/secrets.h` and fill in your
   Wi-Fi credentials, MQTT broker address, and broker root CA certificate.
   `secrets.h` is gitignored — never commit real credentials.
3. Set `DOOR_ID`, `DOOR_REQUIRES_BIO`, and `DOOR_FAIL_MODE_SAFE` in
   `include/config.h` for this specific door. Also replace
   `DESFIRE_AES_KEY` with a real per-site key before provisioning real
   cards — the shipped value is a placeholder.
4. Wire the hardware per the pin map in `include/config.h` (matches the
   Breadboard Wiring & Pin-Map Guide document).
5. Build and upload: `pio run --target upload`
6. Monitor serial output: `pio device monitor`

## What's new in Phase 5 (security hardening)

- **Real cryptographic card authentication.** `desfire_auth.h`/`.cpp`
  implement the DESFire EV1 native AES-128 mutual-authentication handshake
  using mbedTLS (bundled with the ESP32 Arduino core — no new dependency).
  `CARD_SCAN` now requires this to succeed, not just a UID match against
  the allow-list. **Read `desfire_auth.h`'s header comment before trusting
  this** — it's implemented against the public DESFire spec but has not
  been run against a real card; there was no hardware available to test
  against here, the same limitation noted for the rest of this firmware.
- **Tamper lockout.** A case-open event now forces an immediate relock and
  blocks further card-based entry (`tamperLockout`) until an admin sends
  `{"cmd":"clear_tamper"}` over MQTT. REX (local egress) still works during
  lockout — this blocks suspicious entry, not exit.
- **Offline event buffering.** `queueOfflineEvent()`/`flushOfflineEvents()`
  hold access events in a small RAM ring buffer when MQTT is unreachable
  and flush them once the connection returns, instead of dropping them.
  Not persisted across a reboot — that would be the next hardening step.

## What this build still does and does not do

- The credential allow-list is still a small hardcoded array in `main.cpp`
  standing in for the real backend/database lookup from Phase 3 — it now
  only decides *which* card a UID claims to be; the AES handshake is what
  actually proves it.
- All cards at a site currently share one AES key (`DESFIRE_AES_KEY`), not
  per-card diversified keys — a reasonable scope boundary for this project,
  flagged in `desfire_auth.h` as a real hardening item before production
  (compromising one card's key would compromise all of them).
- Phase 6 update: the RS-485 backbone and Building Gateway now exist and
  are the primary path when a gateway is polling this node; direct Wi-Fi/
  MQTT is the fallback (see "What's new in Phase 6" above).
- Even on Phase 6's RS-485 path, this firmware itself has still never run
  on real ESP32 hardware in this environment — the wire protocol is
  verified (see tests/), the firmware's use of it is reviewed but not
  hardware-tested, same caveat as the DESFire handshake since Phase 5.

## What's new in Phase 6 (multi-node scaling)

- **Real RS-485 backbone.** `include/rs485_protocol.h` defines the frame
  format shared with the new Building Gateway (`../gateway/`); the network
  watchdog task now listens for the gateway's polls and, when they're
  arriving on schedule, routes events/alerts/commands over RS-485 instead
  of Wi-Fi/MQTT directly. Set a unique `RS485_NODE_ADDR` per node in
  `include/config.h` before flashing.
- **Wi-Fi fallback, unchanged behavior.** If no poll arrives within
  `RS485_POLL_TIMEOUT_MS`, the node falls back to talking to the broker
  directly — the same Wi-Fi/MQTT path from Phases 2–5, now demoted from
  "the only path" to "the fallback path."
- **Wire-format correctness, verified a different way.** The ESP32
  toolchain still couldn't be compiled here, so `rs485_protocol.h`'s
  framing/checksum/stuffing logic was instead compiled standalone with
  plain gcc and cross-checked byte-for-byte against an independent Python
  implementation — see `tests/README.md`. This is real, executed
  verification of the protocol definition; it is not a substitute for
  bench-testing the actual RS-485 electrical layer on real hardware.

## Bench testing

See the accompanying Bench Test Checklist document for the P2.8–P2.10
test procedure (lock actuation timing, power/isolation validation, and
single-node end-to-end integration). Phase 5 adds three more things worth
bench-testing specifically once real DESFire cards are available:
authenticate with the correct key (should grant), present a card with the
right UID but wrong key/emulated card (should deny + publish `auth_failed`),
and trigger the tamper switch mid-session (should force relock and block a
subsequent valid card until `clear_tamper` is sent).
