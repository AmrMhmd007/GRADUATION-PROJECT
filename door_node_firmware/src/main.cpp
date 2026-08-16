// ============================================================================
// Smart Building Access Control — Door Node Firmware
// Phase 2: Single Door-Node Prototype
//
// Implements the state machine from Figure 3 of the Phase 1 System Design
// Document (BOOT -> IDLE -> CARD_SCAN -> [BIOMETRIC_CHECK] -> ACCESS_DECISION
// -> GRANTED/DENIED -> MONITOR_DOOR -> RELOCK -> IDLE), plus a tamper
// interrupt that can fire from any state and a network watchdog task.
//
// SCOPE NOTE FOR THIS PROTOTYPE (read before flashing):
//  - Credential authentication reads the PN532's UID only. MIFARE DESFire's
//    AES mutual authentication (the actual clone-resistance mechanism from
//    the proposal's security section) is NOT implemented yet — that is a
//    Phase 5 (Security & Fail-Safe) deliverable. Treat this build as
//    "reads a card ID", not "cryptographically verifies a card".
//  - The credential allow-list is a small hardcoded array (below) standing
//    in for the real backend/database lookup, which arrives in Phase 3.
//  - The RS-485 backbone / building gateway does not exist yet at this
//    phase (that is Phase 6, multi-node scaling). This firmware talks
//    directly to the MQTT broker over Wi-Fi so the credential -> unlock ->
//    log loop can be tested end to end on a single node. The RS-485 path
//    is stubbed behind rs485Send()/networkWatchdogTask() so swapping in the
//    real primary/fallback logic later does not require restructuring the
//    state machine.
// ============================================================================

#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_PN532.h>
#include <Adafruit_Fingerprint.h>

#include "config.h"
#include "secrets.h"   // copy include/secrets_example.h -> include/secrets.h and fill in

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
Adafruit_PN532 nfc(PIN_PN532_SS);
HardwareSerial fpSerial(2);
Adafruit_Fingerprint finger(&fpSerial);
HardwareSerial rs485Serial(1);

WiFiClientSecure tlsClient;
PubSubClient mqtt(tlsClient);

enum State {
  BOOT,
  IDLE,
  CARD_SCAN,
  BIOMETRIC_CHECK,
  ACCESS_DECISION,
  GRANTED,
  DENIED,
  MONITOR_DOOR,
  RELOCK
};
volatile State currentState = BOOT;

volatile bool tamperFlag = false;
volatile unsigned long lastTamperIsrMs = 0;

volatile bool networkLinkUp = false;   // updated by networkWatchdogTask on core 0
TaskHandle_t networkTaskHandle = nullptr;

uint8_t cardUid[7];
uint8_t cardUidLen = 0;
bool biometricOk = false;
bool accessGranted = false;
unsigned long stateEnteredAt = 0;

// Stand-in for the real credential lookup (Phase 3 replaces this with a
// backend/API + local cache). UIDs are illustrative, not real card values.
struct AllowListEntry { uint8_t uid[7]; uint8_t len; const char *label; };
AllowListEntry allowList[] = {
  { {0xDE, 0xAD, 0xBE, 0xEF, 0, 0, 0}, 4, "test-card-01" },
  { {0x12, 0x34, 0x56, 0x78, 0, 0, 0}, 4, "test-card-02" },
};

// ---------------------------------------------------------------------------
// Tamper interrupt — fires from any state, per Figure 3
// ---------------------------------------------------------------------------
void IRAM_ATTR onTamperIsr() {
  unsigned long now = millis();
  if (now - lastTamperIsrMs > TAMPER_DEBOUNCE_MS) {
    tamperFlag = true;
    lastTamperIsrMs = now;
  }
}

// ---------------------------------------------------------------------------
// MQTT helpers
// ---------------------------------------------------------------------------
void publishJson(const char *topic, JsonDocument &doc) {
  char buf[256];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(topic, (const uint8_t *)buf, n, false);
}

void publishEvent(const char *method, const char *result) {
  JsonDocument doc;
  doc["door_id"] = DOOR_ID;
  doc["method"] = method;
  doc["result"] = result;
  doc["uptime_ms"] = millis();
  publishJson(TOPIC_EVENT, doc);
}

void publishAlert(const char *type) {
  JsonDocument doc;
  doc["door_id"] = DOOR_ID;
  doc["type"] = type;
  doc["uptime_ms"] = millis();
  publishJson(TOPIC_ALERT, doc);
}

void mqttReconnect() {
  static unsigned long lastAttempt = 0;
  if (mqtt.connected()) return;
  unsigned long now = millis();
  if (now - lastAttempt < MQTT_RECONNECT_INTERVAL_MS) return;
  lastAttempt = now;

  Serial.println("[MQTT] Connecting...");
  if (mqtt.connect(MQTT_CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD,
                    TOPIC_STATUS, 1, true, "offline")) {
    Serial.println("[MQTT] Connected");
    mqtt.publish(TOPIC_STATUS, "online", true);
    mqtt.subscribe(TOPIC_CMD);
  } else {
    Serial.printf("[MQTT] Failed, rc=%d\n", mqtt.state());
  }
}

void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  // Handles backend override commands: {"cmd":"unlock"} / {"cmd":"lock"}
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;
  const char *cmd = doc["cmd"] | "";
  if (strcmp(cmd, "unlock") == 0 && currentState == IDLE) {
    accessGranted = true;
    currentState = GRANTED;
    stateEnteredAt = millis();
  } else if (strcmp(cmd, "lock") == 0) {
    digitalWrite(PIN_LOCK_RELAY, LOW);
  }
  JsonDocument ack;
  ack["door_id"] = DOOR_ID;
  ack["cmd"] = cmd;
  ack["ack"] = true;
  publishJson(TOPIC_CMD_ACK, ack);
}

// ---------------------------------------------------------------------------
// RS-485 stub — Phase 6 replaces this with the real gateway protocol.
// Kept as a separate function so the primary/fallback swap doesn't touch
// the state machine logic above.
// ---------------------------------------------------------------------------
void rs485Send(const char *msg) {
  digitalWrite(PIN_RS485_DE, HIGH);  // driver enable
  rs485Serial.println(msg);
  rs485Serial.flush();
  digitalWrite(PIN_RS485_DE, LOW);   // back to listen mode
}

// ---------------------------------------------------------------------------
// Network watchdog task — runs on core 0, independent of the state machine
// on core 1. In this single-node prototype there is no RS-485 gateway to
// ping yet, so this only tracks Wi-Fi/MQTT reachability; Phase 6 adds the
// real RS-485-active / Wi-Fi-fallback decision described in Figure 3.
// ---------------------------------------------------------------------------
void networkWatchdogTask(void *param) {
  for (;;) {
    bool up = (WiFi.status() == WL_CONNECTED) && mqtt.connected();
    networkLinkUp = up;
    vTaskDelay(pdMS_TO_TICKS(NETWORK_CHECK_INTERVAL_MS));
  }
}

// ---------------------------------------------------------------------------
// Credential helpers
// ---------------------------------------------------------------------------
bool uidMatchesAllowList(uint8_t *uid, uint8_t len, const char **labelOut) {
  for (auto &entry : allowList) {
    if (entry.len == len && memcmp(entry.uid, uid, len) == 0) {
      *labelOut = entry.label;
      return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n[BOOT] Door node %s starting\n", DOOR_ID);

  pinMode(PIN_REED_SWITCH, INPUT);      // external pull-up on breadboard
  pinMode(PIN_REX_BUTTON, INPUT);       // external pull-up on breadboard
  pinMode(PIN_TAMPER, INPUT_PULLUP);
  pinMode(PIN_LOCK_RELAY, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);
  pinMode(PIN_RS485_DE, OUTPUT);
  digitalWrite(PIN_LOCK_RELAY, LOW);    // fail-secure default: de-energized = locked
  digitalWrite(PIN_RS485_DE, LOW);

  attachInterrupt(digitalPinToInterrupt(PIN_TAMPER), onTamperIsr, FALLING);

  // PN532 (SPI)
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("[ERR] PN532 not found — check wiring");
  } else {
    nfc.SAMConfig();
    Serial.println("[OK] PN532 ready");
  }

  // Fingerprint (UART2)
  fpSerial.begin(57600, SERIAL_8N1, PIN_FP_RX, PIN_FP_TX);
  if (finger.verifyPassword()) {
    Serial.println("[OK] Fingerprint sensor ready");
  } else {
    Serial.println("[ERR] Fingerprint sensor not found — check wiring");
  }

  // RS-485 (remapped UART1) — not actively used until Phase 6, initialized
  // so the hardware path can be validated during bench testing (P2.9).
  rs485Serial.begin(9600, SERIAL_8N1, PIN_RS485_RX, PIN_RS485_TX);

  // Wi-Fi + MQTT
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] Connecting");
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected" : " FAILED (continuing offline)");

  tlsClient.setCACert(MQTT_ROOT_CA);
  mqtt.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
  mqtt.setCallback(onMqttMessage);

  xTaskCreatePinnedToCore(networkWatchdogTask, "netWatchdog", 4096, nullptr, 1, &networkTaskHandle, 0);

  currentState = IDLE;
  stateEnteredAt = millis();
  Serial.println("[BOOT] Complete, entering IDLE");
}

// ---------------------------------------------------------------------------
// Main loop — the access state machine (core 1)
// ---------------------------------------------------------------------------
void loop() {
  mqtt.loop();
  if (!mqtt.connected()) mqttReconnect();

  // Tamper interrupt takes priority over whatever state we're in.
  if (tamperFlag) {
    tamperFlag = false;
    Serial.println("[TAMPER] Case-open detected");
    publishAlert("tamper");
    digitalWrite(PIN_STATUS_LED, HIGH);
  }

  switch (currentState) {

    case IDLE: {
      digitalWrite(PIN_STATUS_LED, LOW);
      uint8_t success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, cardUid, &cardUidLen, 100);
      if (success) {
        Serial.println("[CARD] UID read");
        currentState = CARD_SCAN;
        stateEnteredAt = millis();
      }
      // REX button: local egress request, always allowed, no credential check
      if (digitalRead(PIN_REX_BUTTON) == LOW) {
        Serial.println("[REX] Request-to-exit pressed");
        accessGranted = true;
        currentState = GRANTED;
        stateEnteredAt = millis();
      }
      break;
    }

    case CARD_SCAN: {
      const char *label = nullptr;
      bool known = uidMatchesAllowList(cardUid, cardUidLen, &label);
      if (!known) {
        currentState = DENIED;
        stateEnteredAt = millis();
        break;
      }
      if (DOOR_REQUIRES_BIO) {
        currentState = BIOMETRIC_CHECK;
      } else {
        accessGranted = true;
        currentState = ACCESS_DECISION;
      }
      stateEnteredAt = millis();
      break;
    }

    case BIOMETRIC_CHECK: {
      uint8_t p = finger.getImage();
      if (p == FINGERPRINT_OK && finger.image2Tz() == FINGERPRINT_OK &&
          finger.fingerFastSearch() == FINGERPRINT_OK) {
        biometricOk = true;
        accessGranted = true;
      } else if (millis() - stateEnteredAt > 5000) {
        // timeout waiting for a finger
        accessGranted = false;
      } else {
        break; // keep waiting
      }
      currentState = ACCESS_DECISION;
      stateEnteredAt = millis();
      break;
    }

    case ACCESS_DECISION: {
      currentState = accessGranted ? GRANTED : DENIED;
      stateEnteredAt = millis();
      break;
    }

    case GRANTED: {
      Serial.println("[ACCESS] Granted, unlocking");
      digitalWrite(PIN_LOCK_RELAY, HIGH);   // energize strike
      publishEvent(biometricOk ? "card+fingerprint" : "card", "granted");
      currentState = MONITOR_DOOR;
      stateEnteredAt = millis();
      biometricOk = false;
      break;
    }

    case DENIED: {
      Serial.println("[ACCESS] Denied");
      publishEvent("card", "denied");
      publishAlert("access_denied");
      currentState = IDLE;
      stateEnteredAt = millis();
      accessGranted = false;
      biometricOk = false;
      break;
    }

    case MONITOR_DOOR: {
      bool doorOpen = digitalRead(PIN_REED_SWITCH) == HIGH; // wiring-dependent; verify polarity on bench
      unsigned long held = millis() - stateEnteredAt;

      if (held > UNLOCK_HOLD_MS) {
        digitalWrite(PIN_LOCK_RELAY, LOW);  // de-energize, back to secure
        currentState = RELOCK;
        stateEnteredAt = millis();
      } else if (doorOpen && held > DOOR_OPEN_GRACE_MS) {
        publishAlert("propped_open");
      }
      break;
    }

    case RELOCK: {
      Serial.println("[ACCESS] Relocked");
      currentState = IDLE;
      stateEnteredAt = millis();
      accessGranted = false;
      break;
    }

    case BOOT:
    default:
      currentState = IDLE;
      break;
  }
}
