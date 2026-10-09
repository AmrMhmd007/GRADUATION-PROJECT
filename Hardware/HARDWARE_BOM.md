# Hardware Bill of Materials (BOM)

**Nothing on this list has been purchased, sourced, or tested.** This is a
planning reference — the components a typical ESP32-based occupancy/relay/
power-metering node would use, based on standard, widely-documented parts
this class of project usually uses — not a certified or vendor-quoted spec.
Prices, exact part numbers, and availability must be verified before
purchase. Anything marked OPTIONAL/FUTURE is not required for a first
working demo node.

Existing, already-built hardware (door nodes: ESP32 + RFID/DESFire reader +
lock relay + RS-485 transceiver) is **not** repeated here — see the
original System Design Document for that BOM.

---

## REQUIRED — first occupancy sensor node (proof of concept)

| Item | Purpose | Notes |
|---|---|---|
| ESP32 dev board (e.g. ESP32-WROOM-32) | Compute + Wi-Fi/MQTT | Same family already used for door nodes — keeps firmware/tooling consistent |
| PIR motion sensor (e.g. HC-SR501) | Cheapest, most standard occupancy signal | Maps to `sensor_type: "PIR"`, weight 0.80 in the confidence model |
| 5V/3.3V power supply for the node | Power | A USB supply is fine for a bench prototype |
| Breadboard + jumper wires | Prototyping | Bench/demo only, not for permanent install |
| Enclosure | Physical protection | Any generic project box for a demo unit |

## REQUIRED — first relay/contactor node (proof of concept)

| Item | Purpose | Notes |
|---|---|---|
| ESP32 dev board | Compute + Wi-Fi/MQTT | |
| Relay module (e.g. a single-channel 5V relay board, opto-isolated) | ESP32 GPIO → relay coil | **Never wire the GPIO to mains directly — see HARDWARE_INTEGRATION.md §2** |
| Contactor rated for the actual load, if switching more than a small lamp/fan | Mains-rated switching | Required for anything beyond a trivial low-current demo load; a bare relay module is only appropriate for genuinely small loads within its rating |
| Low-voltage demo load (e.g. a 12V/24V fan or LED strip) for bench testing | Safe proof-of-concept load | Recommended before ever switching a real 230V circuit |

## OPTIONAL / FUTURE — power metering

| Item | Purpose | Notes |
|---|---|---|
| Non-invasive current transformer clamp (e.g. SCT-013 series) | Current sensing without breaking the circuit | Pairs with an ADC or a dedicated energy-metering IC |
| Dedicated energy-metering IC (e.g. a single-phase energy monitoring chip) | Accurate voltage/current/power/power-factor in one part | Significantly more accurate than a bare CT + ESP32 ADC; recommended over DIY CT+ADC if budget allows |
| Mains-rated smart plug hardware (if retrofitting rather than building from CT+relay) | Combined relay+metering in one enclosure | Only if a suitable pre-built module can be sourced and safely opened/flashed |

## OPTIONAL / FUTURE — better occupancy sensing

| Item | Purpose | Notes |
|---|---|---|
| mmWave presence sensor module | Detects stationary occupants PIR misses | Maps to `sensor_type: "MMWAVE"`, weight 0.90 — the highest-trust source in the confidence model |
| Door reed switch | Open/closed signal as a secondary evidence source | Maps to `door_sensor`, weight 0.60 |

## OPTIONAL / FUTURE — RS-485 extension (matches existing gateway pattern)

| Item | Purpose | Notes |
|---|---|---|
| RS-485 transceiver module (e.g. MAX485-based) | Same transport the door nodes already use | Only needed if a new node joins the existing RS-485 bus rather than talking Wi-Fi/MQTT directly |

## Safety-critical, non-negotiable

| Item | Purpose | Notes |
|---|---|---|
| Relay/contactor correctly rated for the actual load's voltage AND current | Prevents fire/equipment damage | This is the single most important line on this BOM — verify against the actual load's nameplate rating, not an estimate |
| A qualified person's review of any mains wiring before energizing | Electrical safety | Out of scope for this document and for this software team's own expertise — required regardless of anything else here |

---

## What this BOM deliberately does not include

- Any specific vendor, price, or purchase link — sourcing decisions belong
  to whoever actually buys the parts, with current pricing and local
  availability in hand.
- A full building-scale rollout quantity — this BOM is sized for a single
  proof-of-concept node of each type, to validate the software integration
  points in HARDWARE_INTEGRATION.md before any larger purchase.
- PostgreSQL/server infrastructure — unrelated to physical hardware and
  already addressed separately (see the backend's own configuration
  documentation).
