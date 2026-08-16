#pragma once
// Copy this file to "secrets.h" (already gitignored) and fill in real values.
// Never commit real Wi-Fi or broker credentials to version control.

#define WIFI_SSID       "your-wifi-ssid"
#define WIFI_PASSWORD   "your-wifi-password"

#define MQTT_BROKER_HOST  "192.168.1.10"
#define MQTT_BROKER_PORT  8883          // TLS port
#define MQTT_CLIENT_ID    "door-node-A101"
#define MQTT_USERNAME     "door-node-A101"
#define MQTT_PASSWORD     "per-device-password-not-shared"

// Root CA of the broker, PEM format (Mosquitto/HiveMQ). Placeholder only —
// replace with the real certificate before deploying.
static const char *MQTT_ROOT_CA = R"EOF(
-----BEGIN CERTIFICATE-----
REPLACE_WITH_REAL_BROKER_ROOT_CA
-----END CERTIFICATE-----
)EOF";
