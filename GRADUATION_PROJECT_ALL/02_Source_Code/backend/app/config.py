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


settings = Settings()
