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

Room devices (AC / light / plugs) extend the same pattern for
category == 'access_service' doors ("Rooms") — not in the original spec,
added for the doctor-controlled room devices feature:

  site/{code}/ac/status          -> "on"/"off", updates Door.ac_on
  site/{code}/light/status       -> "on"/"off", updates Door.light_on
  site/{code}/plug/{plug_id}/status -> JSON {"on": bool, "current_amps": num},
                                        updates that Plug row — this is where
                                        a real plug's built-in current sensor
                                        would report in once that hardware
                                        exists.
  site/{code}/occupancy/status       -> JSON {"occupied": bool}, updates
                                        Door.occupied — this is where a real
                                        per-room occupancy sensor reports in,
                                        once that hardware exists. There is no
                                        publish_occupancy(): the backend never
                                        commands this, it only ever listens.

publish_ac() / publish_light() / publish_plug() mirror publish_override(),
sending commands down to site/{code}/ac/cmd, .../light/cmd, and
.../plug/{plug_id}/cmd respectively, each as {"cmd": "on"/"off"}.

Runs as a background thread started from main.py's startup event, kept
deliberately separate from the request/response cycle so a broker outage
doesn't take the REST API down with it.

--------------------------------------------------------------------------
Phase 2 — new topic hierarchy (Smart Building hardware groundwork)
--------------------------------------------------------------------------
Everything above (site/{code}/...) is untouched and keeps working exactly
as before — every existing door node's firmware, and the legacy Door/Plug
control path bridge.py wraps, needs zero changes. This is a pure ADDITION
alongside it, for the new Zone/Sensor/Device model:

  university/{university_id}/building/{building_id}/zone/{zone_id}/sensor/{sensor_id}/telemetry
      -> one Telemetry-shaped JSON reading for a specific Sensor row.
         {"metric": "occupancy", "value": true, "unit": null,
          "quality": "good", "sequence_number": 42}
         Any message that actually arrives here is, by definition, real
         hardware — see _handle_v2_telemetry, which is the ONLY place in
         this codebase allowed to mark a Sensor's data as hardware-sourced.

  university/.../zone/{zone_id}/device/{device_id}/state
      -> a real node reporting its own current state, same shape as the
         legacy plug/status topic: {"on": bool, "current_power": number}.

  university/.../zone/{zone_id}/device/{device_id}/command
      -> backend -> node, published by publish_device_command() (called
         from hardware/bridge.py's GenericDeviceController). Not
         subscribed to here — this is the outgoing side.

  university/.../zone/{zone_id}/occupancy
      -> a zone-level composite reading, for a node doing its own onboard
         sensor fusion for a whole room rather than reporting per-sensor.
         {"occupied": bool}. Recorded against an auto-provisioned Sensor
         row (sensor_type='ESP32') for that zone, rather than adding a
         second, competing "zone occupancy" concept next to the Sensor
         table that already exists.

  university/.../zone/{zone_id}/health
      -> a node's heartbeat (battery/RSSI/uptime/firmware version, plus a
         "node_id" field identifying which physical node this is — one
         node can drive several Sensors/Devices). Persisted via
         services/hardware_health_service.py's HardwareHealth model
         (Phase 5). See _handle_v2_health.

  automation/{zone_id}/decision
      -> backend -> world, broadcast (not subscribed to) every time
         automation_engine.py writes an AutomationLog row. Lets any
         listening node/dashboard mirror the exact same decision without
         polling the REST API. See publish_automation_decision(), called
         from automation_engine.py's _log().

Migration strategy: the two hierarchies coexist indefinitely. A site/{code}
door node never has to be reflashed. A new Sensor/Device only ever talks
the university/... hierarchy. The one place they overlap is the AC/light/
plug devices that already exist as Doors/Plugs today — those keep speaking
site/{code}/... forever, mirrored into the newer Device rows only inside
the database (see hardware/bridge.py's legacy bridge), never re-published
onto the new topic tree. There is nothing to "cut over": nothing currently
deployed will ever need to change topics.
"""
from __future__ import annotations

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
TOPIC_AC_STATUS = "site/+/ac/status"
TOPIC_LIGHT_STATUS = "site/+/light/status"
TOPIC_PLUG_STATUS = "site/+/plug/+/status"
TOPIC_OCCUPANCY_STATUS = "site/+/occupancy/status"

# Phase 2 — new hierarchy, additive only (see module docstring above).
_V2_ROOT = f"university/{settings.MQTT_UNIVERSITY_ID}/building/+/zone/+"
TOPIC_V2_SENSOR_TELEMETRY = f"{_V2_ROOT}/sensor/+/telemetry"
TOPIC_V2_DEVICE_STATE = f"{_V2_ROOT}/device/+/state"
TOPIC_V2_OCCUPANCY = f"{_V2_ROOT}/occupancy"
TOPIC_V2_HEALTH = f"{_V2_ROOT}/health"

_client: mqtt.Client | None = None


def _door_code_from_topic(topic: str) -> str:
    # topics look like site/{code}/status|event|alert|ac/status|light/status
    return topic.split("/")[1]


def _plug_id_from_topic(topic: str) -> str | None:
    # site/{code}/plug/{plug_id}/status
    parts = topic.split("/")
    return parts[3] if len(parts) >= 5 else None


def _parse_v2_topic(topic: str) -> dict | None:
    """Splits university/{uid}/building/{bid}/zone/{zid}/<rest...> into its
    parts. building_id is carried for firmware-side bookkeeping only — the
    lookup below always resolves by zone_id (globally unique), so a zone
    that gets reassigned to a different Building row in the dashboard never
    orphans a node that hasn't been reconfigured yet."""
    parts = topic.split("/")
    if len(parts) < 6 or parts[0] != "university" or parts[2] != "building" or parts[4] != "zone":
        return None
    return {"university_id": parts[1], "building_id": parts[3], "zone_id": parts[5], "rest": parts[6:]}


def _on_connect(client, userdata, flags, rc, properties=None):
    logger.info("MQTT connected, rc=%s", rc)
    client.subscribe([
        (TOPIC_STATUS, 0), (TOPIC_EVENT, 0), (TOPIC_ALERT, 0),
        (TOPIC_AC_STATUS, 0), (TOPIC_LIGHT_STATUS, 0), (TOPIC_PLUG_STATUS, 0),
        (TOPIC_OCCUPANCY_STATUS, 0),
        (TOPIC_V2_SENSOR_TELEMETRY, 0), (TOPIC_V2_DEVICE_STATE, 0),
        (TOPIC_V2_OCCUPANCY, 0), (TOPIC_V2_HEALTH, 0),
    ])


def _on_message(client, userdata, msg):
    if msg.topic.startswith("university/"):
        _on_v2_message(msg)
        return

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
            # Anomaly-evidence hardening (Feature #7 follow-up): the door
            # node itself is authoritative for whether someone actually got
            # in (that's data.get("result") below, unchanged) — but for
            # later anomaly analysis to stay correct even after an
            # AccessWindow is edited/deleted, this system's OWN
            # authorization computation at this exact moment is frozen onto
            # evidence_snapshot now, at ingestion time, rather than being
            # re-derived later from whatever AccessWindow rows happen to
            # still exist. See access_authorization_service.
            from ..services import access_authorization_service, emergency_override_service

            data = json.loads(msg.payload)
            credential_id = None
            resolved_user_id = None
            card_uid = data.get("card_uid")
            if card_uid:
                # Phase 5: card_uid is encrypted at rest, so lookup goes
                # through the blind index rather than comparing plaintext.
                cred = db.query(models.Credential).filter(
                    models.Credential.card_uid_index == crypto.uid_index(card_uid)
                ).first()
                if cred:
                    credential_id = cred.credential_id
                    resolved_user_id = cred.user_id

            # Feature #8 (emergency override): if this door currently has an
            # ACTIVE emergency override, that's a separate, clearly-labeled
            # reason this access may be granted even with no permanent
            # assignment or window — attach it to the evidence rather than
            # letting the physical event misleadingly read as an
            # unexplained WHO/WHEN authorization gap. This never touches
            # DoorAssignment/AccessWindow or evaluate_door_authorization's
            # own "authorized" verdict — emergency authorization stays a
            # distinct, additional fact recorded alongside it.
            active_override = emergency_override_service.active_override_for_door(db, door.door_id)
            override_context = None
            if active_override is not None:
                override_context = {
                    "override_id": active_override.override_id,
                    "action": active_override.action,
                    "reason": active_override.reason,
                    "created_by_id": active_override.created_by_id,
                    "expires_at": active_override.expires_at,
                }

            evidence = None
            resolved_user = db.get(models.User, resolved_user_id) if resolved_user_id else None
            if resolved_user is not None:
                evaluation = access_authorization_service.evaluate_door_authorization(db, resolved_user, door)
                evidence = access_authorization_service.build_authorization_evidence(
                    evaluation, source=access_authorization_service.EVIDENCE_SOURCE_PHYSICAL_DOOR_NODE,
                )
                evidence["door_node_result"] = data.get("result", "unknown")
            elif card_uid:
                evidence = {
                    "authorization_source": access_authorization_service.EVIDENCE_SOURCE_PHYSICAL_DOOR_NODE,
                    "authorized": None,
                    "reason": "Card UID did not resolve to any known credential/user — no authorization evidence available",
                    "door_node_result": data.get("result", "unknown"),
                }
            if evidence is not None:
                evidence["emergency_override_active"] = override_context

            event = models.AccessEvent(
                door_id=door.door_id,
                credential_id=credential_id,
                method=data.get("method", "unknown"),
                result=data.get("result", "unknown"),
                user_id=resolved_user_id,
                evidence_snapshot=json.dumps(evidence, default=str) if evidence else None,
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

        elif msg.topic.endswith("/ac/status"):
            # A real message on this topic is, by definition, the physical
            # AC unit itself reporting in — this is DEVICE_STATE_CONFIRMED
            # (hardening constraint #6) for whatever Device mirrors this
            # door's AC, and REAL provenance (constraint #2) for its power
            # reading once real current-sensing hardware exists.
            payload = msg.payload.decode("utf-8", errors="ignore").strip().lower()
            door.ac_on = (payload == "on")
            _mark_state_confirmed(db, door_ref_id=door.door_id, device_type="AC")
            db.commit()

        elif msg.topic.endswith("/light/status"):
            payload = msg.payload.decode("utf-8", errors="ignore").strip().lower()
            door.light_on = (payload == "on")
            _mark_state_confirmed(db, door_ref_id=door.door_id, device_type="LIGHT")
            db.commit()

        elif "/plug/" in msg.topic and msg.topic.endswith("/status"):
            plug_id = _plug_id_from_topic(msg.topic)
            plug = db.query(models.Plug).filter(
                models.Plug.plug_id == plug_id, models.Plug.door_id == door.door_id
            ).first()
            if plug is None:
                logger.warning("Status for unknown plug '%s' on door '%s'", plug_id, code)
                return
            data = json.loads(msg.payload)
            if "on" in data:
                plug.on = bool(data["on"])
            if "current_amps" in data:
                plug.current_amps = data["current_amps"]
            plug.last_seen = _utcnow()
            _mark_state_confirmed(db, plug_ref_id=plug.plug_id, power_source="REAL" if "current_amps" in data else None)
            db.commit()

        elif msg.topic.endswith("/occupancy/status"):
            data = json.loads(msg.payload)
            if "occupied" in data:
                door.occupied = bool(data["occupied"])
                door.occupancy_updated_at = _utcnow()
                db.commit()

    except Exception:
        logger.exception("Failed to process MQTT message on %s", msg.topic)
    finally:
        db.close()


def _utcnow():
    import datetime
    return datetime.datetime.utcnow()


def _mark_state_confirmed(db, *, door_ref_id: int | None = None, plug_ref_id: int | None = None,
                           device_type: str | None = None, power_source: str | None = None) -> None:
    """Hardening constraint #6: a real status/state message arriving on any
    of these topics is exactly the DEVICE_STATE_CONFIRMED moment — the one
    thing a synchronous MQTT publish call can never itself prove. Finds the
    Device row (if any) that mirrors this door/plug and stamps it. A silent
    no-op when no Device row exists yet (e.g. before migrate_zones_and_
    automation.py has run) — this is a best-effort audit enrichment, never
    something the legacy control path depends on."""
    query = db.query(models.Device)
    device = None
    if plug_ref_id is not None:
        device = query.filter(models.Device.plug_ref_id == plug_ref_id).first()
    elif door_ref_id is not None:
        q = query.filter(models.Device.door_ref_id == door_ref_id)
        if device_type is not None:
            q = q.filter(models.Device.type == device_type)
        device = q.first()
    if device is not None:
        device.last_command_status = "STATE_CONFIRMED"
        device.last_command_at = _utcnow()
        if power_source is not None:
            device.power_source = power_source


# ---------------------------------------------------------------------------
# Phase 2 — new hierarchy handlers (see module docstring)
# ---------------------------------------------------------------------------
def _on_v2_message(msg):
    db = SessionLocal()
    try:
        parsed = _parse_v2_topic(msg.topic)
        if parsed is None:
            logger.warning("Malformed university/... topic, ignoring: %s", msg.topic)
            return
        zone = db.query(models.Zone).filter(models.Zone.zone_id == parsed["zone_id"]).first()
        if zone is None:
            logger.warning("Message for unknown zone_id '%s' on %s", parsed["zone_id"], msg.topic)
            return

        rest = parsed["rest"]
        try:
            if len(rest) == 3 and rest[0] == "sensor" and rest[2] == "telemetry":
                _handle_v2_telemetry(db, zone, sensor_id=rest[1], payload=msg.payload)
            elif len(rest) == 3 and rest[0] == "device" and rest[2] == "state":
                _handle_v2_device_state(db, zone, device_id=rest[1], payload=msg.payload)
            elif len(rest) == 1 and rest[0] == "occupancy":
                _handle_v2_occupancy(db, zone, payload=msg.payload)
            elif len(rest) == 1 and rest[0] == "health":
                _handle_v2_health(db, zone, payload=msg.payload)
            else:
                logger.warning("Unrecognized university/... topic shape, ignoring: %s", msg.topic)
        except (ValueError, KeyError) as exc:
            logger.warning("Bad payload on %s: %s", msg.topic, exc)
    except Exception:
        logger.exception("Failed to process MQTT message on %s", msg.topic)
    finally:
        db.close()


def _handle_v2_telemetry(db, zone: models.Zone, sensor_id: str, payload: bytes) -> None:
    """A real node reporting one Telemetry-shaped reading for one of the
    zone's Sensor rows. This is the only code path in the project allowed
    to say a Sensor's data came from real hardware — it only runs when an
    actual MQTT message arrived, never from a simulation/manual write."""
    from ..hardware.telemetry import Telemetry

    data = json.loads(payload)
    telemetry = Telemetry(
        sensor_id=int(sensor_id), zone_id=zone.zone_id,
        sensor_type=data.get("sensor_type", "OTHER"),
        metric=data.get("metric", "occupancy"),
        value=data.get("value"),
        unit=data.get("unit"),
        quality=data.get("quality", "good"),
        source="real",
        sequence_number=data.get("sequence_number"),
    )

    sensor = db.query(models.Sensor).filter(
        models.Sensor.sensor_id == telemetry.sensor_id, models.Sensor.zone_id == zone.zone_id
    ).first()
    if sensor is None:
        logger.warning("Telemetry for unknown sensor_id '%s' in zone %s", sensor_id, zone.zone_id)
        return

    sensor.last_seen = _utcnow()
    sensor.status = "online"
    sensor.data_source = "REAL"  # this handler only ever runs for an actually-received MQTT message
    # quality/source/sequence_number don't have dedicated Sensor columns yet
    # (Phase 5's HardwareHealth is where that richer per-node bookkeeping
    # belongs) — stashed into last_reading, already surfaced by
    # SensorPanel.jsx, so nothing about this reading is silently dropped.
    sensor.last_reading = json.dumps({
        "metric": telemetry.metric, "value": telemetry.value, "unit": telemetry.unit,
        "quality": telemetry.quality, "source": telemetry.source,
        "sequence_number": telemetry.sequence_number,
    })
    if telemetry.metric == "occupancy":
        occupied = bool(telemetry.value)
        sensor.occupancy_state = occupied
        db.add(models.OccupancyEvent(
            zone_id=zone.zone_id, sensor_id=sensor.sensor_id,
            occupancy_state=occupied, source="sensor",
        ))
    db.commit()


def _handle_v2_device_state(db, zone: models.Zone, device_id: str, payload: bytes) -> None:
    """A real node acknowledging a Device's actual state — same shape as the
    legacy plug/status topic. Once a real node exists for a given Device,
    this becomes the sole writer of status/current_power for it; until
    then hardware/bridge.py's GenericDeviceController mirror is what keeps
    the row current (see that module's docstring)."""
    device = db.query(models.Device).filter(
        models.Device.device_id == int(device_id), models.Device.zone_id == zone.zone_id
    ).first()
    if device is None:
        logger.warning("State for unknown device_id '%s' in zone %s", device_id, zone.zone_id)
        return
    data = json.loads(payload)
    if "on" in data:
        device.status = bool(data["on"])
    if "current_power" in data:
        device.current_power = data["current_power"]
        device.power_source = "REAL"
        from . import energy_timeseries_service  # local import: avoids a circular import at module load time
        energy_timeseries_service.record_reading(
            db, zone_id=zone.zone_id, device_id=device.device_id, power=data["current_power"],
            voltage=data.get("voltage"), current=data.get("current"),
            energy_kwh=data.get("energy_kwh"), power_factor=data.get("power_factor"), source="REAL",
        )
    # Hardening constraint #6: this message IS the DEVICE_STATE_CONFIRMED
    # signal — the node itself reporting what it actually did, as opposed
    # to GenericDeviceController's own optimistic mirror (see bridge.py).
    device.last_command_status = "STATE_CONFIRMED"
    device.last_command_at = _utcnow()
    db.commit()


def _handle_v2_occupancy(db, zone: models.Zone, payload: bytes) -> None:
    """A node doing its own onboard fusion for a whole zone rather than
    reporting per-sensor. Recorded against an auto-provisioned Sensor row
    (sensor_type='ESP32') instead of inventing a second, competing
    "zone occupancy" field alongside the Sensor table that already exists —
    the fused Zone.occupancy_state the dashboard shows is still computed by
    automation_engine.sense_zone_occupancy from this same Sensor row, same
    as any other sensor."""
    data = json.loads(payload)
    if "occupied" not in data:
        return
    occupied = bool(data["occupied"])

    sensor = db.query(models.Sensor).filter(
        models.Sensor.zone_id == zone.zone_id, models.Sensor.sensor_type == "ESP32"
    ).first()
    if sensor is None:
        sensor = models.Sensor(zone_id=zone.zone_id, sensor_type="ESP32", status="online")
        db.add(sensor)
        db.flush()

    sensor.occupancy_state = occupied
    sensor.status = "online"
    sensor.last_seen = _utcnow()
    sensor.data_source = "REAL"
    sensor.last_reading = json.dumps({"metric": "occupancy", "value": occupied, "source": "real"})
    db.add(models.OccupancyEvent(
        zone_id=zone.zone_id, sensor_id=sensor.sensor_id, occupancy_state=occupied, source="sensor",
    ))
    db.commit()


def _handle_v2_health(db, zone: models.Zone, payload: bytes) -> None:
    """Phase 5: persists a node's heartbeat via hardware_health_service.
    Requires a "node_id" field in the payload (a node can host several
    Sensors/Devices, so the zone_id in the topic alone isn't a unique key
    for it) — falls back to a synthetic per-zone id and logs a warning
    rather than dropping the heartbeat outright, since a real node omitting
    its own id is exactly the kind of firmware bug this table should help
    surface, not hide."""
    from . import hardware_health_service  # local import: avoids a circular import at module load time

    try:
        data = json.loads(payload)
    except ValueError:
        data = {"raw": payload.decode("utf-8", errors="ignore")}

    node_id = data.get("node_id")
    if not node_id:
        node_id = f"zone-{zone.zone_id}-unnamed-node"
        logger.warning("Health heartbeat for zone %s has no node_id — using synthetic id '%s'", zone.zone_id, node_id)

    hardware_health_service.record_heartbeat(db, node_id=node_id, payload=data, zone_id=zone.zone_id)


def publish_override(door_code: str, action: str) -> bool:
    """Publishes a lock/unlock command to site/{code}/cmd. Returns False if
    the MQTT client isn't connected (e.g. broker unavailable in dev/tests)."""
    if _client is None or not _client.is_connected():
        logger.warning("MQTT not connected — override for %s not sent", door_code)
        return False
    topic = f"site/{door_code}/cmd"
    _client.publish(topic, json.dumps({"cmd": action}), qos=1)
    return True


def publish_ac(door_code: str, action: str) -> bool:
    """Publishes an AC on/off command to site/{code}/ac/cmd."""
    if _client is None or not _client.is_connected():
        logger.warning("MQTT not connected — AC command for %s not sent", door_code)
        return False
    _client.publish(f"site/{door_code}/ac/cmd", json.dumps({"cmd": action}), qos=1)
    return True


def publish_light(door_code: str, action: str) -> bool:
    """Publishes a light on/off command to site/{code}/light/cmd."""
    if _client is None or not _client.is_connected():
        logger.warning("MQTT not connected — light command for %s not sent", door_code)
        return False
    _client.publish(f"site/{door_code}/light/cmd", json.dumps({"cmd": action}), qos=1)
    return True


def publish_plug(door_code: str, plug_id: int, action: str) -> bool:
    """Publishes a plug on/off command to site/{code}/plug/{plug_id}/cmd —
    this is also the channel that would eventually carry a remote cutoff for
    a plug whose current sensor reports something left switched on, once that
    hardware exists."""
    if _client is None or not _client.is_connected():
        logger.warning("MQTT not connected — plug command for %s/%s not sent", door_code, plug_id)
        return False
    _client.publish(f"site/{door_code}/plug/{plug_id}/cmd", json.dumps({"cmd": action}), qos=1)
    return True


def publish_device_command(building_id, zone_id: int, device_id: int, action: str) -> bool:
    """Publishes to university/.../zone/{zone_id}/device/{device_id}/command
    — the Phase 2 counterpart of publish_ac/publish_light/publish_plug, for
    a freestanding Device with no legacy door/plug behind it. Called from
    hardware/bridge.py's GenericDeviceController, never directly by
    routers/automation_engine — same "one place issues commands" shape as
    the legacy path."""
    building_segment = building_id if building_id is not None else "unassigned"
    topic = f"university/{settings.MQTT_UNIVERSITY_ID}/building/{building_segment}/zone/{zone_id}/device/{device_id}/command"
    if _client is None or not _client.is_connected():
        logger.warning("MQTT not connected — device command for zone %s device %s not sent", zone_id, device_id)
        return False
    _client.publish(topic, json.dumps({"cmd": action}), qos=1)
    return True


def publish_automation_decision(zone_id: int | None, payload: dict) -> bool:
    """Broadcasts every AutomationLog entry to automation/{zone_id}/decision
    so any listening node or dashboard can mirror the engine's decision
    without polling the REST API. Called from automation_engine.py's _log()
    right after the row is committed. A building-wide entry (zone_id is
    None) broadcasts under automation/building/decision instead."""
    topic = f"automation/{zone_id if zone_id is not None else 'building'}/decision"
    if _client is None or not _client.is_connected():
        logger.info("MQTT not connected — automation decision for %s not broadcast", topic)
        return False
    _client.publish(topic, json.dumps(payload, default=str), qos=0)
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
