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
#define NETWORK_CHECK_INTERVAL_MS  3000
#define MQTT_RECONNECT_INTERVAL_MS 5000

// ============================================================================
// MQTT topics — matches Section 6 of the System Design Document
// ============================================================================
#define TOPIC_STATUS   "site/" DOOR_ID "/status"
#define TOPIC_EVENT    "site/" DOOR_ID "/event"
#define TOPIC_ALERT    "site/" DOOR_ID "/alert"
#define TOPIC_CMD      "site/" DOOR_ID "/cmd"
#define TOPIC_CMD_ACK  "site/" DOOR_ID "/cmd/ack"
