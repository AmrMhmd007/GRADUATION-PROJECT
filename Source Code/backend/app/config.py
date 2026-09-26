import os
from pathlib import Path

# Minimal .env loader so the project doesn't need an extra dependency.
def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./access_control.db")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_USE_TLS: bool = os.getenv("MQTT_USE_TLS", "false").lower() == "true"
    MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "")

    DISABLE_MQTT: bool = os.getenv("DISABLE_MQTT", "false").lower() == "true"

    # Phase 5: at-rest encryption for credential data (card UIDs). Must be a
    # Fernet key (32 url-safe base64 bytes) — generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # A dev-only fallback is generated at import time if unset, so local
    # runs and tests don't require touching .env — but every real
    # deployment MUST set a real, persisted key, or previously encrypted
    # data becomes unreadable the moment the process restarts.
    CREDENTIAL_ENCRYPTION_KEY: str = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")

    # HMAC key for the blind index used to look up credentials by UID
    # without decrypting every row. Must also be stable across restarts.
    CREDENTIAL_INDEX_KEY: str = os.getenv("CREDENTIAL_INDEX_KEY", "")

    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_SECONDS: int = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "300"))

    # Phase 7 (full system testing) — found during integration testing: a
    # door's `online` flag was only ever set False by an explicit "offline"
    # status message (either the node's own MQTT last-will, or the gateway
    # explicitly publishing it after missed polls). A gateway process that
    # dies outright — killed, crashed, host power loss — never gets to
    # publish anything for the RS-485 nodes it was relaying, so those doors
    # stayed "online" in the DB forever. This is a transport-agnostic fix:
    # a periodic sweep marks any door stale (online -> offline) if it hasn't
    # been heard from in DOOR_STALE_AFTER_SECONDS, regardless of whether it
    # talks directly or through a gateway. See app/services/staleness_watchdog.py.
    DOOR_STALE_AFTER_SECONDS: int = int(os.getenv("DOOR_STALE_AFTER_SECONDS", "30"))
    DOOR_STALENESS_CHECK_INTERVAL_SECONDS: int = int(os.getenv("DOOR_STALENESS_CHECK_INTERVAL_SECONDS", "10"))

    # Energy/occupancy feature (see app/services/energy_service.py). No
    # current-sensor hardware exists yet, so current_amps for the AC/plugs is
    # simulated at this interval — real hardware would just publish over MQTT
    # instead, same as the door/plug status topics already do, and this loop
    # would simply have nothing left to simulate.
    ENERGY_SIM_INTERVAL_SECONDS: int = int(os.getenv("ENERGY_SIM_INTERVAL_SECONDS", "20"))
    # A device drawing at or above this many watts counts as "high power" for
    # the empty-room alert (an AC unit or a kettle/heater on a plug, not a
    # phone charger).
    HIGH_POWER_WATTS_THRESHOLD: float = float(os.getenv("HIGH_POWER_WATTS_THRESHOLD", "300"))
    # How often the checkout-time clock is checked. A minute is plenty since
    # checkout_time itself only has minute resolution ("HH:MM").
    CHECKOUT_CHECK_INTERVAL_SECONDS: int = int(os.getenv("CHECKOUT_CHECK_INTERVAL_SECONDS", "30"))
    # Fallback used the very first time the backend runs, before an admin has
    # ever saved a checkout time from the dashboard (see SystemSetting).
    DEFAULT_CHECKOUT_TIME: str = os.getenv("DEFAULT_CHECKOUT_TIME", "18:00")

    # Smart Building automation engine (see app/services/automation_engine.py).
    # How often the SENSE->ANALYZE->VERIFY->DECIDE->ACT->MONITOR pass runs
    # across every zone.
    AUTOMATION_INTERVAL_SECONDS: int = int(os.getenv("AUTOMATION_INTERVAL_SECONDS", "30"))
    # A sensor (or a Door's own occupancy field) that hasn't reported within
    # this many seconds is never trusted — treated as no signal at all
    # rather than as "confirms empty." This is the fail-safe backbone: a
    # dead sensor can never cause a shutdown.
    SENSOR_STALE_AFTER_SECONDS: int = int(os.getenv("SENSOR_STALE_AFTER_SECONDS", "120"))
    # A granted RFID/card access event at a zone's door counts as a positive
    # occupancy signal for this long afterward, even with no dedicated
    # occupancy sensor confirming it yet.
    RFID_OCCUPANCY_WINDOW_SECONDS: int = int(os.getenv("RFID_OCCUPANCY_WINDOW_SECONDS", "900"))
    # Used only when a zone has no ZoneSchedule row at all yet (schedule
    # state comes back UNKNOWN, so this number is never actually applied to
    # a real verification countdown — it's just a sane default to display).
    DEFAULT_VERIFICATION_MINUTES: int = int(os.getenv("DEFAULT_VERIFICATION_MINUTES", "5"))

    # Phase 2 (MQTT redesign, see services/mqtt_service.py): this project is
    # single-tenant (one deployment = one university), so university_id in
    # the new topic hierarchy is a fixed slug rather than a database row —
    # there is no University table, only Building. Change this per real
    # deployment; it only has to be unique enough to not collide with another
    # campus sharing the same broker.
    MQTT_UNIVERSITY_ID: str = os.getenv("MQTT_UNIVERSITY_ID", "aiu")

    # Phase 3 (confidence-scored occupancy fusion, see
    # services/automation_engine.py's sense_zone_occupancy). Each occupancy
    # signal source gets a reliability weight in [0, 1] used to turn "how
    # many fresh signals agree, and how reliable are they" into one
    # occupancy_confidence number — never a random or guessed figure.
    #
    # These defaults are reasoned starting points, NOT measured/certified
    # sensor accuracy figures (no real occupancy hardware has been tested on
    # this project yet — see HARDWARE_INTEGRATION.md): a dedicated mmWave or
    # ESP32-fused presence sensor is generally more reliable than a basic PIR,
    # and an RFID grant or a door reed switch only implies presence
    # indirectly (someone could badge in and immediately leave), so they're
    # weighted lower. Override via OCCUPANCY_SOURCE_WEIGHTS_JSON (a JSON
    # object merged over these defaults, e.g. '{"sensor_pir": 0.7}') once
    # real hardware gives grounds to tune specific numbers — nothing here is
    # hardcoded into the engine itself.
    OCCUPANCY_SOURCE_WEIGHTS: dict = {
        "door_sensor": 0.6,
        "rfid_grant": 0.5,
        "sensor_pir": 0.8,
        "sensor_mmwave": 0.9,
        "sensor_esp32": 0.85,
        "sensor_door_event": 0.4,
        "sensor_rfid_event": 0.5,
        "sensor_other": 0.3,
    }
    _weights_override = os.getenv("OCCUPANCY_SOURCE_WEIGHTS_JSON", "")
    if _weights_override:
        import json as _json
        try:
            OCCUPANCY_SOURCE_WEIGHTS = {**OCCUPANCY_SOURCE_WEIGHTS, **_json.loads(_weights_override)}
        except ValueError:
            pass  # malformed override — keep defaults rather than crash startup


    # Phase 5 (hardware health, see services/hardware_health_service.py). A
    # node that hasn't sent a heartbeat within this window is marked
    # OFFLINE by the periodic sweep — the same staleness-watchdog pattern
    # already used for Door.online.
    HARDWARE_HEALTH_STALE_AFTER_SECONDS: int = int(os.getenv("HARDWARE_HEALTH_STALE_AFTER_SECONDS", "120"))
    HARDWARE_HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.getenv("HARDWARE_HEALTH_CHECK_INTERVAL_SECONDS", "30"))

    # Feature #7 (access anomaly indicators, see
    # services/anomaly_detection_service.py). All deterministic thresholds —
    # no scoring model, no randomness. How far back a report looks by
    # default when no ?since_days= is given.
    ANOMALY_DEFAULT_LOOKBACK_DAYS: int = int(os.getenv("ANOMALY_DEFAULT_LOOKBACK_DAYS", "30"))
    # "Repeated denied attempts": this many denied events at the same door
    # within this many minutes of each other is flagged as one indicator.
    ANOMALY_DENIED_BURST_THRESHOLD: int = int(os.getenv("ANOMALY_DENIED_BURST_THRESHOLD", "3"))
    ANOMALY_DENIED_BURST_WINDOW_MINUTES: int = int(os.getenv("ANOMALY_DENIED_BURST_WINDOW_MINUTES", "15"))
    # "Repeated attempts in a short window": same idea but counts ALL
    # attempts (granted+denied) at one door — a much tighter window, since
    # this is meant to catch rapid repeat/probing behavior rather than a
    # slower pattern of separate denied tries.
    ANOMALY_RAPID_BURST_THRESHOLD: int = int(os.getenv("ANOMALY_RAPID_BURST_THRESHOLD", "5"))
    ANOMALY_RAPID_BURST_WINDOW_MINUTES: int = int(os.getenv("ANOMALY_RAPID_BURST_WINDOW_MINUTES", "5"))
    # "Unusual access time": events outside this UTC hour range are flagged
    # as unusual timing — informational only, not a claim of wrongdoing.
    ANOMALY_UNUSUAL_HOUR_START_UTC: int = int(os.getenv("ANOMALY_UNUSUAL_HOUR_START_UTC", "6"))
    ANOMALY_UNUSUAL_HOUR_END_UTC: int = int(os.getenv("ANOMALY_UNUSUAL_HOUR_END_UTC", "22"))
    # How long after a temporary AccessWindow's end_at an access attempt at
    # that same door still counts as "after expiration" for that rule,
    # rather than being treated as unrelated to the old grant.
    ANOMALY_POST_EXPIRY_FOLLOWUP_HOURS: int = int(os.getenv("ANOMALY_POST_EXPIRY_FOLLOWUP_HOURS", "24"))

    # Feature #8 (emergency access/override, see
    # services/emergency_override_service.py). A time-bounded, reasoned,
    # audited alternative to the plain instant lock/unlock in
    # routers/doors.py::override_door — this is what enforces "never
    # silently create permanent access": every override MUST have an
    # expiration no further out than this many minutes.
    EMERGENCY_OVERRIDE_MAX_DURATION_MINUTES: int = int(os.getenv("EMERGENCY_OVERRIDE_MAX_DURATION_MINUTES", "240"))
    # How often the background sweep checks for overrides whose expires_at
    # has passed, so it can revert the door and close out the audit trail —
    # same periodic-sweep shape as staleness_watchdog/energy_service's
    # checkout sweep.
    EMERGENCY_OVERRIDE_SWEEP_INTERVAL_SECONDS: int = int(os.getenv("EMERGENCY_OVERRIDE_SWEEP_INTERVAL_SECONDS", "15"))


settings = Settings()
