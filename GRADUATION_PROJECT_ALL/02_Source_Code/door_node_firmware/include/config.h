#pragma once

// ============================================================================
// Door identity — set uniquely per node before flashing
// ============================================================================
#define DOOR_ID              "A101"
#define DOOR_REQUIRES_BIO    false   // true for higher-security rooms (server rooms, labs)
#define DOOR_FAIL_MODE_SAFE  false   // false = fail-secure (default), true = fail-safe (egress doors)

// ============================================================================
// Pin map — matches Figure 2 (Door Node Wiring & Connection Diagram) in the
// Phase 1 System Design Document. Chosen to avoid ESP32 strapping pins
// (0, 2, 12, 15) where practical; GPIO5 (PN532 SS) is a strapping pin but is
// the standard VSPI CS0 default and does not affect boot in practice.
// ============================================================================

// PN532 NFC/RFID reader — VSPI bus
#define PIN_PN532_SCK   18
#define PIN_PN532_MISO  19
#define PIN_PN532_MOSI  23
#define PIN_PN532_SS    5

// R307 fingerprint module — hardware UART2
#define PIN_FP_RX  16
#define PIN_FP_TX  17

// MAX485 (RS-485 transceiver) — remapped UART1
#define PIN_RS485_RX  4
#define PIN_RS485_TX  32
#define PIN_RS485_DE  33   // driver-enable / receiver-enable, tied together

// Door position sensor (magnetic reed switch) — input only pin, external pull-up
#define PIN_REED_SWITCH  34

// Request-to-exit button — input only pin, external pull-up
#define PIN_REX_BUTTON  35

// Tamper (case-open) switch — interrupt-capable, internal pull-up
#define PIN_TAMPER  27

// Relay / MOSFET driver controlling the electric strike
#define PIN_LOCK_RELAY  26

// Status LED (onboard indicator, optional)
#define PIN_STATUS_LED  13

// ============================================================================
// Timing
// ============================================================================
#define UNLOCK_HOLD_MS         5000   // how long the strike stays energized
#define DOOR_OPEN_GRACE_MS     8000   // time allowed for the door to open/close before flagging propped-open
#define DEBOUNCE_MS            50
#define TAMPER_DEBOUNCE_MS     200
#define NETWORK_CHECK_INTERVAL_MS  3000  // Wi-Fi/MQTT connectivity re-check cadence;
                                          // the Phase 6 RS-485 byte-reader in
                                          // networkWatchdogTask runs its own
                                          // tighter loop so it doesn't miss bytes
#define MQTT_RECONNECT_INTERVAL_MS 5000

// ============================================================================
// MQTT topics — matches Section 6 of the System Design Document
// ============================================================================
#define TOPIC_STATUS   "site/" DOOR_ID "/status"
#define TOPIC_EVENT    "site/" DOOR_ID "/event"
#define TOPIC_ALERT    "site/" DOOR_ID "/alert"
#define TOPIC_CMD      "site/" DOOR_ID "/cmd"
#define TOPIC_CMD_ACK  "site/" DOOR_ID "/cmd/ack"

// ============================================================================
// Phase 5 — DESFire AES authentication key
//
// PLACEHOLDER KEY. Every node at a real site currently shares this one key
// (see the scope note in desfire_auth.h) — replace it before provisioning
// real cards, and treat this header as sensitive once it holds a real key
// (same handling as secrets.h: don't commit the real value).
// ============================================================================
#define DESFIRE_KEY_NO  0
static const uint8_t DESFIRE_AES_KEY[16] = {
  0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
  0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
};

// ============================================================================
// Phase 5 — tamper lockout
// ============================================================================
// Once tamper is detected, the node stops granting access (even to valid
// cards) until an admin clears it via MQTT ({"cmd":"clear_tamper"} on
// TOPIC_CMD) — a physical case-open event needs a human decision, not an
// automatic timeout, before the door trusts credentials again.
#define TOPIC_CMD_CLEAR_TAMPER_VALUE "clear_tamper"

// ============================================================================
// Phase 5 — offline event buffering
// ============================================================================
// Access events are queued locally when MQTT is unreachable and flushed
// once the connection returns, instead of being silently dropped.
#define OFFLINE_EVENT_BUFFER_SIZE 32

// ============================================================================
// Phase 6 — RS-485 multi-drop backbone (node side)
//
// Each node has a bus address (1-15, set uniquely per node before flashing,
// distinct from DOOR_ID which is the human-readable code the backend uses —
// the Building Gateway maps between the two, see gateway/gateway_config.yaml).
// The gateway is the bus master: it polls each node in turn, and a node only
// ever transmits in the short window right after being polled (see
// rs485_protocol.h for the framing details and why this avoids bus
// contention entirely).
// ============================================================================
#define RS485_NODE_ADDR  1

// If no POLL addressed to this node arrives within this window, the node
// treats the RS-485 backbone as down and falls back to talking to the MQTT
// broker directly over Wi-Fi — the "hybrid RS-485 backbone + Wi-Fi fallback"
// behavior from the System Design Document's network watchdog (Figure 3).
#define RS485_POLL_TIMEOUT_MS  2000

// Baud rate for the RS-485 bus. 9600 is conservative for a 3-5 node,
// short-run (single building) bus; matches rs485Serial.begin() in main.cpp.
#define RS485_BAUD 9600
