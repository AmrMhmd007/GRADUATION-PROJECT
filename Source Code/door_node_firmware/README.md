# Door Node Firmware — Phase 2 Prototype

Implements the state machine from the Phase 1 System Design Document (Figure 3)
for a single access-controlled door: card scan, optional biometric check,
lock actuation, door-state monitoring, tamper interrupt, and MQTT reporting.

## Setup

1. Install [PlatformIO](https://platformio.org/) (VS Code extension or CLI).
2. Copy `include/secrets_example.h` to `include/secrets.h` and fill in your
   Wi-Fi credentials, MQTT broker address, and broker root CA certificate.
   `secrets.h` is gitignored — never commit real credentials.
3. Set `DOOR_ID`, `DOOR_REQUIRES_BIO`, and `DOOR_FAIL_MODE_SAFE` in
   `include/config.h` for this specific door.
4. Wire the hardware per the pin map in `include/config.h` (matches the
   Breadboard Wiring & Pin-Map Guide document).
5. Build and upload: `pio run --target upload`
6. Monitor serial output: `pio device monitor`

## What this build does and does not do

This is a Phase 2 prototype scoped to prove the credential → unlock → log
loop on one node, not a finished security implementation:

- Reads a card's UID via the PN532. It does **not** yet perform MIFARE
  DESFire's AES mutual authentication — that is real security work deferred
  to Phase 5. Right now, cloning a card's UID would fool this build.
- Checks the UID against a small hardcoded allow-list in `main.cpp`. Phase 3
  replaces this with a real backend/database lookup.
- Talks to the MQTT broker directly over Wi-Fi. The RS-485 backbone and
  building gateway from the System Design Document don't exist yet — that
  arrives in Phase 6 (multi-node scaling). The RS-485 UART is initialized
  and `rs485Send()` is stubbed so the primary/fallback logic can be dropped
  in later without restructuring the state machine.
- The network watchdog task tracks Wi-Fi/MQTT reachability only, for the
  same reason.

## Bench testing

See the accompanying Bench Test Checklist document for the P2.8–P2.10
test procedure (lock actuation timing, power/isolation validation, and
single-node end-to-end integration).
