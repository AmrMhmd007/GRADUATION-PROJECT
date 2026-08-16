"""
MQTT ingestion service.

Subscribes to the door-node topics defined in Section 6 of the System
Design Document and writes what it receives into the database:

  site/{code}/status  -> updates Door.online / Door.last_seen
  site/{code}/event   -> inserts an AccessEvent row
  site/{code}/alert   -> inserts an Alert row

Also exposes publish_override(), used by the /api/doors/{id}/override
endpoint to send a lock/unlock command down to a door node, matching
site/{code}/cmd from the same spec.

Runs as a background thread started from main.py's startup event, kept
deliberately separate from the request/response cycle so a broker outage
doesn't take the REST API down with it.
"""
import json
import logging
import threading

import paho.mqtt.client as mqtt

from ..config import settings
from ..database import SessionLocal
from .. import models, crypto

logger = logging.getLogger("mqtt_service")

TOPIC_STATUS = "site/+/status"
TOPIC_EVENT = "site/+/event"
TOPIC_ALERT = "site/+/alert"

_client: mqtt.Client | None = None


def _door_code_from_topic(topic: str) -> str:
    # topics look like site/{code}/status|event|alert
    return topic.split("/")[1]


def _on_connect(client, userdata, flags, rc, properties=None):
    logger.info("MQTT connected, rc=%s", rc)
    client.subscribe([(TOPIC_STATUS, 0), (TOPIC_EVENT, 0), (TOPIC_ALERT, 0)])


def _on_message(client, userdata, msg):
    db = SessionLocal()
    try:
        code = _door_code_from_topic(msg.topic)
        door = db.query(models.Door).filter(models.Door.code == code).first()
        if door is None:
            logger.warning("Message from unknown door code '%s' on %s", code, msg.topic)
            return

        if msg.topic.endswith("/status"):
            payload = msg.payload.decode("utf-8", errors="ignore")
            door.online = (payload == "online")
            door.last_seen = _utcnow()
            db.commit()

        elif msg.topic.endswith("/event"):
            data = json.loads(msg.payload)
            credential_id = None
            card_uid = data.get("card_uid")
            if card_uid:
                # Phase 5: card_uid is encrypted at rest, so lookup goes
                # through the blind index rather than comparing plaintext.
                cred = db.query(models.Credential).filter(
                    models.Credential.card_uid_index == crypto.uid_index(card_uid)
                ).first()
                credential_id = cred.credential_id if cred else None
            event = models.AccessEvent(
                door_id=door.door_id,
                credential_id=credential_id,
                method=data.get("method", "unknown"),
                result=data.get("result", "unknown"),
            )
            db.add(event)
            if data.get("result") == "granted":
                door.locked = False
            db.commit()

        elif msg.topic.endswith("/alert"):
            data = json.loads(msg.payload)
            alert = models.Alert(door_id=door.door_id, type=data.get("type", "unknown"))
            db.add(alert)
            db.commit()

    except Exception:
        logger.exception("Failed to process MQTT message on %s", msg.topic)
    finally:
        db.close()


def _utcnow():
    import datetime
    return datetime.datetime.utcnow()


def publish_override(door_code: str, action: str) -> bool:
    """Publishes a lock/unlock command to site/{code}/cmd. Returns False if
    the MQTT client isn't connected (e.g. broker unavailable in dev/tests)."""
    if _client is None or not _client.is_connected():
        logger.warning("MQTT not connected — override for %s not sent", door_code)
        return False
    topic = f"site/{door_code}/cmd"
    _client.publish(topic, json.dumps({"cmd": action}), qos=1)
    return True


def start():
    global _client
    if settings.DISABLE_MQTT:
        logger.info("MQTT disabled via DISABLE_MQTT — skipping broker connection")
        return

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="access-control-backend",
        protocol=mqtt.MQTTv311,
    )
    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
    if settings.MQTT_USE_TLS:
        client.tls_set()
    client.on_connect = _on_connect
    client.on_message = _on_message

    try:
        client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=30)
    except Exception:
        logger.exception("Could not connect to MQTT broker at %s:%s — running without live updates",
                          settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT)
        return

    _client = client
    thread = threading.Thread(target=client.loop_forever, daemon=True)
    thread.start()


def stop():
    if _client is not None:
        _client.disconnect()
