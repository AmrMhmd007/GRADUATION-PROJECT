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
//  - Phase 5 update: card authentication now runs a real AES-128 mutual
//    challenge-response handshake against the card (see desfire_auth.h/.cpp)
//    instead of trusting the UID alone. Read desfire_auth.h's header
//    comment before relying on this — it's implemented against the public
//    DESFire EV1 spec but has not been run against real hardware here.
//  - The credential allow-list is still a small hardcoded array (below)
//    standing in for the real backend/database lookup from Phase 3 — the
//    allow-list now only decides *which* key/label a UID maps to, it is no
//    longer the security boundary by itself (the AES handshake is).
//  - Tamper detection now does more than alert: it forces an immediate
//    relock and enters a lockout that blocks further card-based entry
//    until an admin clears it via MQTT (see TAMPER_LOCKOUT handling below).
//    REX (local egress) still works during lockout — tamper lockout is
//    about blocking suspicious *entry*, not trapping people inside.
//  - Access events now queue locally when MQTT is down and flush once the
//    connection returns, instead of being silently dropped (see
//    offlineEventQueue below).
//  - Phase 6 update: the RS-485 backbone is now real. networkWatchdogTask
//    (core 0) listens for POLL frames from the Building Gateway
//    (rs485_protocol.h) addressed to RS485_NODE_ADDR; when the bus is
//    responsive, queued events/alerts and any command carried in the poll
//    are exchanged over RS-485 instead of direct Wi-Fi/MQTT. If no poll
//    arrives within RS485_POLL_TIMEOUT_MS, the node falls back to talking
//    to the broker directly over Wi-Fi — the hybrid primary/fallback
//    behavior from Figure 3 of the System Design Document. See
//    gateway/rs485_gateway.py for the other end of this link and
//    door_node_firmware/tests/ for the wire-format cross-check (the ESP32
//    toolchain itself still could not be run in this sandbox — see the
//    README for exactly what is and isn't verified).
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
#include "desfire_auth.h"
#include "rs485_protocol.h"

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
volatile bool tamperLockout = false;   // Phase 5: blocks card-based entry until admin-cleared

volatile bool networkLinkUp = false;   // updated by networkWatchdogTask on core 0
TaskHandle_t networkTaskHandle = nullptr;

// --- Phase 6: RS-485 backbone state (written by networkWatchdogTask on
// core 0, read/acted-on from loop() on core 1) ------------------------------
// Only simple volatile flags/buffers cross the core boundary here, the same
// pattern already used for tamperFlag — the network task never touches
// currentState or the event queues directly.
Rs485Parser rs485Parser;
volatile bool rs485LinkUp = false;              // gateway polled us recently
volatile unsigned long lastRs485PollMs = 0;
volatile bool rs485PollAwaitingResponse = false; // loop() owes the gateway a DATA frame
char rs485PendingCmd[16] = "";                   // cmd carried in the most recent poll, "" if none
// (rs485PendingCmd is only written by the network task right before setting
// rs485PollAwaitingResponse, and only read by loop() after observing that
// flag true then clearing it — a single-slot mailbox, not a queue; adequate
// given the gateway polls slowly (hundreds of ms) relative to loop()'s rate.)

// --- Phase 5/6: outbound event+alert buffering -----------------------------
// Queues access events and alerts locally instead of sending them
// immediately, and drains them into whichever transport (RS-485 poll
// response, or direct MQTT) is actually available. RAM-only (not persisted
// across a reboot) — persisting to flash (e.g. LittleFS) would be the next
// hardening step if a node needs to survive a power cycle while offline
// without losing queued events.
enum QueuedKind : uint8_t { QK_EVENT, QK_ALERT };
struct QueuedEvent { QueuedKind kind; char method[24]; char result[16]; unsigned long queuedAtMs; };
QueuedEvent offlineEventQueue[OFFLINE_EVENT_BUFFER_SIZE];
uint8_t offlineQueueHead = 0, offlineQueueCount = 0;

void queueOutbound(QueuedKind kind, const char *method, const char *result) {
  uint8_t writeIdx = (offlineQueueHead + offlineQueueCount) % OFFLINE_EVENT_BUFFER_SIZE;
  if (offlineQueueCount == OFFLINE_EVENT_BUFFER_SIZE) {
    // Buffer full — drop the oldest rather than the newest event.
    offlineQueueHead = (offlineQueueHead + 1) % OFFLINE_EVENT_BUFFER_SIZE;
  } else {
    offlineQueueCount++;
  }
  offlineEventQueue[writeIdx].kind = kind;
  strlcpy(offlineEventQueue[writeIdx].method, method, sizeof(offlineEventQueue[writeIdx].method));
  strlcpy(offlineEventQueue[writeIdx].result, result ? result : "", sizeof(offlineEventQueue[writeIdx].result));
  offlineEventQueue[writeIdx].queuedAtMs = millis();
  Serial.printf("[QUEUE] Buffered outbound %s (%u/%u queued)\n",
                kind == QK_EVENT ? "event" : "alert", offlineQueueCount, OFFLINE_EVENT_BUFFER_SIZE);
}

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

// Phase 6: RS-485 (when the gateway is polling us) is preferred over a
// direct Wi-Fi/MQTT hop — that's the "backbone primary, Wi-Fi fallback"
// design from the System Design Document. When RS-485 is up, events/alerts
// are queued and drained into the next DATA response (see
// buildRs485DataPayload()) instead of published directly.
void publishEvent(const char *method, const char *result) {
  if (rs485LinkUp || !mqtt.connected()) {
    queueOutbound(QK_EVENT, method, result);
    return;
  }
  JsonDocument doc;
  doc["door_id"] = DOOR_ID;
  doc["method"] = method;
  doc["result"] = result;
  doc["uptime_ms"] = millis();
  publishJson(TOPIC_EVENT, doc);
}

void publishAlert(const char *type) {
  if (rs485LinkUp || !mqtt.connected()) {
    queueOutbound(QK_ALERT, type, "");
    return;
  }
  JsonDocument doc;
  doc["door_id"] = DOOR_ID;
  doc["type"] = type;
  doc["uptime_ms"] = millis();
  publishJson(TOPIC_ALERT, doc);
}

// Drains the outbound queue over direct MQTT — used when the node is on
// its Wi-Fi fallback path (RS-485 down) and the broker connection has just
// come back. When RS-485 is up, draining instead happens into a DATA frame
// (see buildRs485DataPayload()), not through this function.
void flushOfflineEvents() {
  while (offlineQueueCount > 0 && mqtt.connected() && !rs485LinkUp) {
    QueuedEvent &qe = offlineEventQueue[offlineQueueHead];
    JsonDocument doc;
    doc["door_id"] = DOOR_ID;
    doc["queued"] = true;
    doc["queued_for_ms"] = millis() - qe.queuedAtMs;
    if (qe.kind == QK_EVENT) {
      doc["method"] = qe.method;
      doc["result"] = qe.result;
      publishJson(TOPIC_EVENT, doc);
    } else {
      doc["type"] = qe.method;  // alert type was stored in the shared `method` field
      publishJson(TOPIC_ALERT, doc);
    }

    offlineQueueHead = (offlineQueueHead + 1) % OFFLINE_EVENT_BUFFER_SIZE;
    offlineQueueCount--;
  }
  if (offlineQueueCount == 0) {
    Serial.println("[QUEUE] Offline event buffer flushed");
  }
}

// Phase 6: builds the JSON body of a DATA frame (status + every currently
// queued event/alert) and empties the queue — sent back to the gateway in
// response to a POLL. Best-effort, no per-item ack/retry: once handed to
// rs485SendFrame() an item is considered delivered, matching the same
// "send then drop" trade-off the MQTT path already makes.
void buildRs485DataPayload(JsonDocument &doc) {
  doc["online"] = true;
  doc["locked"] = (currentState != GRANTED && currentState != MONITOR_DOOR);
  JsonArray events = doc["events"].to<JsonArray>();
  JsonArray alerts = doc["alerts"].to<JsonArray>();
  while (offlineQueueCount > 0) {
    QueuedEvent &qe = offlineEventQueue[offlineQueueHead];
    if (qe.kind == QK_EVENT) {
      JsonObject e = events.add<JsonObject>();
      e["method"] = qe.method;
      e["result"] = qe.result;
    } else {
      JsonObject a = alerts.add<JsonObject>();
      a["type"] = qe.method;
    }
    offlineQueueHead = (offlineQueueHead + 1) % OFFLINE_EVENT_BUFFER_SIZE;
    offlineQueueCount--;
  }
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
    flushOfflineEvents();
  } else {
    Serial.printf("[MQTT] Failed, rc=%d\n", mqtt.state());
  }
}

// Shared command dispatch for both transports: MQTT ({"cmd":...} on
// TOPIC_CMD, Wi-Fi fallback path) and an RS-485 POLL's embedded cmd (Phase
// 6, primary path when the gateway is reachable). Runs only on core 1 (the
// main loop) — the RS-485 receive side (core 0) never calls this directly,
// it just stashes the command string and lets loop() apply it, avoiding any
// cross-core write to currentState/tamperLockout.
void applyRemoteCmd(const char *cmd) {
  if (strcmp(cmd, "unlock") == 0 && currentState == IDLE && !tamperLockout) {
    accessGranted = true;
    currentState = GRANTED;
    stateEnteredAt = millis();
  } else if (strcmp(cmd, "lock") == 0) {
    digitalWrite(PIN_LOCK_RELAY, LOW);
  } else if (strcmp(cmd, TOPIC_CMD_CLEAR_TAMPER_VALUE) == 0) {
    tamperLockout = false;
    digitalWrite(PIN_STATUS_LED, LOW);
    Serial.println("[TAMPER] Lockout cleared by admin");
  }
}

void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  // Handles backend override commands: {"cmd":"unlock"} / {"cmd":"lock"} /
  // {"cmd":"clear_tamper"} (Phase 5 — the only way tamper lockout clears).
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;
  const char *cmd = doc["cmd"] | "";
  applyRemoteCmd(cmd);
  JsonDocument ack;
  ack["door_id"] = DOOR_ID;
  ack["cmd"] = cmd;
  ack["ack"] = true;
  publishJson(TOPIC_CMD_ACK, ack);
}

// ---------------------------------------------------------------------------
// Phase 6 — RS-485 frame transmit. Half-duplex turnaround: assert the
// MAX485 driver-enable pin, write the fully framed+stuffed bytes, wait for
// the UART to actually finish shifting them out, then release the bus back
// to listen mode. Used only for POLL->DATA responses (node never initiates
// a send unprompted — the gateway is bus master).
// ---------------------------------------------------------------------------
void rs485SendFrame(uint8_t addr, uint8_t type, const uint8_t *payload, uint8_t payloadLen) {
  uint8_t frame[RS485_MAX_FRAME_RAW];
  size_t n = rs485_encode_frame(addr, type, payload, payloadLen, frame, sizeof(frame));
  if (n == 0) {
    Serial.println("[RS485] Frame encode failed (payload too large?) — dropped");
    return;
  }
  digitalWrite(PIN_RS485_DE, HIGH);  // driver enable
  rs485Serial.write(frame, n);
  rs485Serial.flush();
  digitalWrite(PIN_RS485_DE, LOW);   // back to listen mode
}

// ---------------------------------------------------------------------------
// Network watchdog task — runs on core 0, independent of the state machine
// on core 1.
//
// Phase 6: this now also drives the RS-485 receive side. It reads bytes
// from rs485Serial as they arrive, feeds them through the streaming frame
// parser (rs485_protocol.h), and when a complete POLL frame addressed to
// this node (or a broadcast) is found: updates rs485LinkUp/lastRs485PollMs,
// and — if the poll carried a command — stashes it in rs485PendingCmd and
// sets rs485PollAwaitingResponse so loop() (core 1) applies the command and
// sends the DATA response. This task never touches currentState or the
// event queues itself; it only writes those few volatile handoff variables,
// same discipline as the tamper ISR.
//
// If no poll arrives within RS485_POLL_TIMEOUT_MS, rs485LinkUp drops back
// to false and the node's publishEvent()/publishAlert() calls fall back to
// talking to the MQTT broker directly over Wi-Fi — the hybrid primary
// (RS-485) / fallback (Wi-Fi) behavior from Figure 3.
// ---------------------------------------------------------------------------
void networkWatchdogTask(void *param) {
  for (;;) {
    while (rs485Serial.available()) {
      uint8_t addr, type, payloadLen;
      uint8_t payload[RS485_MAX_PAYLOAD + 1];
      uint8_t b = (uint8_t)rs485Serial.read();
      if (rs485_parser_feed(&rs485Parser, b, &addr, &type, payload, &payloadLen)) {
        if (type == RS485_TYPE_POLL && (addr == RS485_NODE_ADDR || addr == 0)) {
          lastRs485PollMs = millis();
          rs485LinkUp = true;
          payload[payloadLen] = '\0';
          // Small, fixed-shape payload ({} or {"cmd":"..."}) — a lightweight
          // manual scan avoids pulling ArduinoJson's parser onto core 0
          // alongside its use on core 1, keeping this task's footprint small.
          const char *cmdKey = strstr((const char *)payload, "\"cmd\"");
          rs485PendingCmd[0] = '\0';
          if (cmdKey) {
            const char *q1 = strchr(cmdKey + 5, '"');
            if (q1) {
              const char *q2 = strchr(q1 + 1, '"');
              if (q2 && (size_t)(q2 - q1 - 1) < sizeof(rs485PendingCmd)) {
                memcpy(rs485PendingCmd, q1 + 1, q2 - q1 - 1);
                rs485PendingCmd[q2 - q1 - 1] = '\0';
              }
            }
          }
          rs485PollAwaitingResponse = true;
        }
        // Frames not addressed to us (another node's poll on the shared
        // bus) are simply ignored — every node sees every byte on a
        // multi-drop line, addressing is a filter, not a routing mechanism.
      }
    }

    if (rs485LinkUp && (millis() - lastRs485PollMs > RS485_POLL_TIMEOUT_MS)) {
      rs485LinkUp = false;
      Serial.println("[RS485] Gateway poll timeout — falling back to Wi-Fi/MQTT");
    }

    bool up = (WiFi.status() == WL_CONNECTED) && mqtt.connected();
    networkLinkUp = up || rs485LinkUp;
    vTaskDelay(pdMS_TO_TICKS(20));  // fast enough to not miss RS-485 bytes at 9600 baud
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

  // RS-485 (remapped UART1) — Phase 6: now actively used as the primary
  // backbone link to the Building Gateway, with Wi-Fi/MQTT as fallback.
  rs485Serial.begin(RS485_BAUD, SERIAL_8N1, PIN_RS485_RX, PIN_RS485_TX);
  rs485_parser_init(&rs485Parser);

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

  // Phase 6: service any RS-485 poll the network task (core 0) flagged.
  // Applying the command and building the response here (core 1) keeps
  // every read/write of currentState, tamperLockout, and the event queue
  // on the same core that owns them.
  if (rs485PollAwaitingResponse) {
    rs485PollAwaitingResponse = false;
    if (rs485PendingCmd[0] != '\0') {
      applyRemoteCmd(rs485PendingCmd);
      rs485PendingCmd[0] = '\0';
    }
    JsonDocument doc;
    buildRs485DataPayload(doc);
    char buf[256];
    size_t n = serializeJson(doc, buf, sizeof(buf));
    rs485SendFrame(RS485_NODE_ADDR, RS485_TYPE_DATA, (const uint8_t *)buf, (uint8_t)n);
  }

  // Tamper interrupt takes priority over whatever state we're in. Phase 5:
  // this now does more than alert — it forces an immediate relock and
  // enters a lockout that blocks further card-based entry until an admin
  // clears it (see onMqttMessage's "clear_tamper" handling). A case-open
  // event means someone may be physically attacking the reader/lock, so
  // the door should not keep trusting credentials just because the
  // firmware's own state machine hasn't caught up yet.
  if (tamperFlag) {
    tamperFlag = false;
    tamperLockout = true;
    Serial.println("[TAMPER] Case-open detected — forcing relock, entering lockout");
    publishAlert("tamper");
    digitalWrite(PIN_STATUS_LED, HIGH);
    digitalWrite(PIN_LOCK_RELAY, LOW);  // force secure regardless of current state
    if (currentState == GRANTED || currentState == MONITOR_DOOR) {
      currentState = RELOCK;
      stateEnteredAt = millis();
    }
  }

  switch (currentState) {

    case IDLE: {
      digitalWrite(PIN_STATUS_LED, tamperLockout ? HIGH : LOW);

      // REX button: local egress request. Always allowed, even during
      // tamper lockout — lockout blocks suspicious entry, not egress.
      if (digitalRead(PIN_REX_BUTTON) == LOW) {
        Serial.println("[REX] Request-to-exit pressed");
        accessGranted = true;
        currentState = GRANTED;
        stateEnteredAt = millis();
        break;
      }

      if (tamperLockout) break;  // ignore card reads entirely until cleared

      uint8_t success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, cardUid, &cardUidLen, 100);
      if (success) {
        Serial.println("[CARD] UID read");
        currentState = CARD_SCAN;
        stateEnteredAt = millis();
      }
      break;
    }

    case CARD_SCAN: {
      const char *label = nullptr;
      bool known = uidMatchesAllowList(cardUid, cardUidLen, &label);
      // Phase 5: the allow-list only tells us which card this claims to
      // be — desfireAuthenticateAES() is what actually proves the card
      // holds the shared key, closing the "UID-only" gap from Phase 2.
      bool cryptoOk = known && desfireAuthenticateAES(nfc, DESFIRE_AES_KEY, DESFIRE_KEY_NO);
      if (!cryptoOk) {
        if (known) {
          Serial.println("[CARD] Known UID but AES authentication FAILED — possible clone/emulation");
          publishAlert("auth_failed");
        }
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
