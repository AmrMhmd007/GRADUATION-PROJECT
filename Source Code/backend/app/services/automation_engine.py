"""
Smart Building automation engine.

This is deliberately NOT "if empty, turn everything off." Every pass follows
the same cycle for every zone:

    SENSE -> ANALYZE -> VERIFY -> DECIDE -> ACT -> MONITOR

SENSE (sense_zone_occupancy): gather every *fresh* occupancy signal available
for a zone — its linked Door's own occupancy sensor (if any), every Sensor
row attached to the zone, and any recent RFID/access-grant event at that
door. A signal that hasn't reported within SENSOR_STALE_AFTER_SECONDS is
never trusted — a stale or missing sensor produces UNKNOWN, not EMPTY. This
is the fail-safe backbone the rest of the engine depends on: uncertainty
never gets treated as "confirmed empty."

ANALYZE: fuse those fresh signals into one raw verdict for the zone —
OCCUPIED if anything fresh says so, EMPTY if everything fresh agrees nobody's
there, UNKNOWN if there's nothing fresh to go on at all — and read the
applicable ZoneSchedule to know whether this zone is even supposed to be
open right now.

VERIFY: an EMPTY reading past closing time does not act immediately. It
starts (or continues) a VERIFYING countdown (Zone.verification_started_at,
length = the schedule's verification_minutes). Only once that window has
fully elapsed AND the zone is *still* reading EMPTY on a fresh re-check does
the engine treat the zone as confirmed empty. Any OCCUPIED reading at any
point immediately cancels a running verification, no matter how much of the
window had already elapsed.

DECIDE / ACT: once confirmed empty, only NON_CRITICAL devices with
automatic_control_enabled=True get switched off — CRITICAL devices (servers,
networking, security/access-control equipment, the MQTT gateway, emergency
systems) are never touched, and a device an admin/doctor has flagged for
manual-only control is left alone too. Shutdown reuses this project's
existing, already-working control paths (see Device.door_ref_id/plug_ref_id
below) — it does not invent a second, parallel way to command hardware.

MONITOR: every decision that isn't a silent no-op (verification starting,
being cancelled by real occupancy, a confirmed shutdown, or the engine
refusing to act because occupancy is uncertain) is written to AutomationLog
— the audit trail Step 18 of the spec asks for.

Phase 3 note: sense_zone_occupancy's OCCUPIED/EMPTY/UNKNOWN verdict — and
therefore every VERIFY/DECIDE/ACT rule above — is completely unchanged by
confidence scoring. Confidence is additional, informational output computed
from the same fresh signals: a configurable per-source-type reliability
weight (config.OCCUPANCY_SOURCE_WEIGHTS) turned into "what fraction of the
evidence, by weight, actually supports this verdict." It never overrides
the safety-first verdict rule (any fresh OCCUPIED signal wins outright,
regardless of weight) — it only reports how strongly that verdict is
corroborated, for the dashboard/audit trail to show alongside it.
"""
from __future__ import annotations

import datetime
import json
import logging
import threading

from ..config import settings
from ..database import SessionLocal
from .. import models
from . import mqtt_service
from ..hardware.bridge import get_relay_controller
from ..hardware import interfaces
from ..hardware.interfaces import PowerMeter

logger = logging.getLogger("automation_engine")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


# ---------------------------------------------------------------------------
# SENSE + ANALYZE
# ---------------------------------------------------------------------------
def _fresh(ts: datetime.datetime | None, max_age_seconds: int) -> bool:
    if ts is None:
        return False
    return (datetime.datetime.utcnow() - ts).total_seconds() <= max_age_seconds


_SENSOR_TYPE_WEIGHT_KEY = {
    "PIR": "sensor_pir",
    "MMWAVE": "sensor_mmwave",
    "ESP32": "sensor_esp32",
    "DOOR_EVENT": "sensor_door_event",
    "RFID_EVENT": "sensor_rfid_event",
    "OTHER": "sensor_other",
}


def _signal_weight(source_key: str) -> float:
    return settings.OCCUPANCY_SOURCE_WEIGHTS.get(source_key, 0.3)


def sense_zone_occupancy(db, zone: models.Zone) -> tuple[str, float, list[str], list[dict]]:
    """Fuses every fresh occupancy signal available for a zone into one
    verdict, plus (Phase 3) a confidence score for that verdict. Returns
    (verdict, confidence, evidence_text, evidence_detail):

    - verdict: 'OCCUPIED' | 'EMPTY' | 'UNKNOWN' — exactly as before. Any
      fresh OCCUPIED signal wins outright regardless of its weight; this is
      the fail-safe rule and confidence scoring never changes it.
    - confidence: 0.0-1.0, the weighted fraction of evidence, by
      config.OCCUPANCY_SOURCE_WEIGHTS reliability, that agrees with the
      verdict. 0.0 when verdict is UNKNOWN (no data -> no confidence, not a
      guess). One lone signal that agrees with itself is 1.0; a verdict
      reached over a disagreeing signal is pulled below 1.0 in proportion
      to how much weight that disagreement carries.
    - evidence_text: short human-readable strings, unchanged shape, used to
      build the audit-log reason text.
    - evidence_detail: the same evidence with its source key/weight/state
      attached, for Zone.occupancy_evidence (what the dashboard/audit trail
      can show to explain exactly how confidence was computed).
    """
    signals: list[dict] = []  # {source, weight, state, text}

    if zone.door_id:
        door = db.query(models.Door).filter(models.Door.door_id == zone.door_id).first()
        if door is not None:
            if door.occupied is not None and _fresh(door.occupancy_updated_at, settings.SENSOR_STALE_AFTER_SECONDS):
                signals.append({
                    "source": "door_sensor", "weight": _signal_weight("door_sensor"),
                    "state": door.occupied,
                    "text": f"door occupancy sensor reports {'occupied' if door.occupied else 'empty'}",
                })
            recent_grant = (
                db.query(models.AccessEvent)
                .filter(models.AccessEvent.door_id == door.door_id, models.AccessEvent.result == "granted")
                .order_by(models.AccessEvent.event_time.desc())
                .first()
            )
            if recent_grant and _fresh(recent_grant.event_time, settings.RFID_OCCUPANCY_WINDOW_SECONDS):
                signals.append({
                    "source": "rfid_grant", "weight": _signal_weight("rfid_grant"), "state": True,
                    "text": "recent access grant at this zone's door",
                })

    for sensor in zone.sensors:
        if sensor.occupancy_state is not None and _fresh(sensor.last_seen, settings.SENSOR_STALE_AFTER_SECONDS):
            source_key = _SENSOR_TYPE_WEIGHT_KEY.get(sensor.sensor_type, "sensor_other")
            signals.append({
                "source": source_key, "weight": _signal_weight(source_key), "state": sensor.occupancy_state,
                "text": f"{sensor.sensor_type} sensor #{sensor.sensor_id} reports "
                        f"{'occupied' if sensor.occupancy_state else 'empty'}",
            })

    if not signals:
        return "UNKNOWN", 0.0, ["no fresh occupancy signal available for this zone"], []

    verdict = "OCCUPIED" if any(s["state"] for s in signals) else "EMPTY"
    total_weight = sum(s["weight"] for s in signals)
    agreeing_weight = sum(s["weight"] for s in signals if s["state"] == (verdict == "OCCUPIED"))
    confidence = round(agreeing_weight / total_weight, 3) if total_weight > 0 else 0.0

    evidence_text = [s["text"] for s in signals if s["state"] == (verdict == "OCCUPIED")]
    evidence_detail = [
        {"source": s["source"], "state": s["state"], "weight": s["weight"], "text": s["text"]} for s in signals
    ]
    return verdict, confidence, evidence_text, evidence_detail


def get_schedule_state(db, zone_id: int, now: datetime.datetime | None = None) -> tuple[str, int]:
    """Returns (schedule_state, verification_minutes) for a zone right now.

    schedule_state is 'OPEN' | 'CLOSED' | 'UNKNOWN'. UNKNOWN means no
    schedule at all is configured for this zone (or building-wide) — the
    engine treats that the same as "don't know if it's safe to act," so it
    never starts a shutdown countdown without an explicit schedule telling
    it the zone is supposed to be closed. A zone-specific row always wins
    over the building-wide default (zone_id IS NULL); a day-specific row
    always wins over an every-day one.

    Handles a schedule that crosses midnight (open_time > close_time, e.g.
    open 22:00 / close 02:00 for an overnight-access building) as well as
    the ordinary same-day case (open_time < close_time) — see the
    "midnight-wrap" branch below. This was previously a documented
    simplification ("does not handle a schedule that crosses midnight") and
    the root cause of a real, reproducible bug: any schedule whose window
    happened to straddle local midnight (including one constructed
    relative to `now`, as several tests do) was silently misread as
    CLOSED, because comparing bare `time()` values with `<=`/`<` assumes
    open_time is always earlier in the day than close_time. Fixed here at
    the source rather than in the tests' own helpers.
    """
    now = now or datetime.datetime.now()
    dow = now.weekday()
    rows = (
        db.query(models.ZoneSchedule)
        .filter(
            (models.ZoneSchedule.zone_id == zone_id) | (models.ZoneSchedule.zone_id.is_(None)),
            (models.ZoneSchedule.day_of_week == dow) | (models.ZoneSchedule.day_of_week.is_(None)),
        )
        .all()
    )
    if not rows:
        return "UNKNOWN", settings.DEFAULT_VERIFICATION_MINUTES

    def score(row):
        return (2 if row.zone_id == zone_id else 0) + (1 if row.day_of_week == dow else 0)

    best = max(rows, key=score)
    t = now.time()

    if best.open_time <= best.close_time:
        # Ordinary same-day window (e.g. open 08:00 / close 18:00).
        if best.open_time <= t < best.close_time:
            return "OPEN", best.verification_minutes
        if t >= best.close_time:
            close_dt = datetime.datetime.combine(now.date(), best.close_time)
            grace_end = close_dt + datetime.timedelta(minutes=best.grace_minutes)
            return ("OPEN" if now < grace_end else "CLOSED"), best.verification_minutes
        return "CLOSED", best.verification_minutes  # before today's open_time

    # Midnight-wrap window (open_time > close_time, e.g. open 22:00 / close
    # 02:00): "open" is everything from open_time through midnight AND from
    # midnight through close_time the next calendar day. The only truly
    # "closed" stretch is the daytime gap between close_time and open_time.
    if t >= best.open_time or t < best.close_time:
        return "OPEN", best.verification_minutes
    # In the gap: close_time <= t < open_time. close_time already happened
    # earlier THIS calendar day (that's what makes it a wrap: closing time
    # is numerically before opening time), so grace is measured from today's
    # close_time exactly like the non-wrapping case.
    close_dt = datetime.datetime.combine(now.date(), best.close_time)
    grace_end = close_dt + datetime.timedelta(minutes=best.grace_minutes)
    return ("OPEN" if now < grace_end else "CLOSED"), best.verification_minutes


# ---------------------------------------------------------------------------
# Phase 4 — database-backed automation rules
# ---------------------------------------------------------------------------
TRIGGER_CONFIRMED_EMPTY = "CONFIRMED_EMPTY"
ACTION_SHUTDOWN_NON_CRITICAL = "SHUTDOWN_NON_CRITICAL"

# Used only when no enabled AutomationRule row matches a zone at all (a
# fresh install before migrate_automation_rules.py has run, or every
# matching rule has been disabled). Reproduces this project's pre-Phase-4
# hardcoded behavior exactly — see that migration script's own docstring.
# Deliberately never added to a session/committed; it's a plain in-memory
# stand-in, not a real row.
_FALLBACK_RULE = models.AutomationRule(
    name="(fallback — no automation rule configured)", zone_id=None, enabled=True, priority=-1,
    conditions=json.dumps({"trigger": TRIGGER_CONFIRMED_EMPTY}),
    actions=json.dumps({"action": ACTION_SHUTDOWN_NON_CRITICAL}),
    grace_period_minutes=None, verification_required=True, minimum_confidence=0.0,
    criticality_restriction="NON_CRITICAL_ONLY",
)


def get_applicable_rules(db, zone_id: int, trigger: str) -> list[models.AutomationRule]:
    """Every enabled rule whose condition matches `trigger` and whose
    zone_id is either this zone or None (building-wide), most specific and
    highest-priority first: a zone-specific rule always outranks a
    building-wide one; within the same specificity, higher `priority` wins."""
    rows = db.query(models.AutomationRule).filter(models.AutomationRule.enabled.is_(True)).all()
    matching = []
    for rule in rows:
        try:
            conditions = json.loads(rule.conditions)
        except (ValueError, TypeError):
            logger.warning("Automation rule %s has unparseable conditions, skipping", rule.rule_id)
            continue
        if conditions.get("trigger") != trigger:
            continue
        if rule.zone_id is not None and rule.zone_id != zone_id:
            continue
        matching.append(rule)
    matching.sort(key=lambda r: (0 if r.zone_id == zone_id else 1, -r.priority))
    return matching


def resolve_rule(db, zone_id: int, trigger: str) -> models.AutomationRule:
    matches = get_applicable_rules(db, zone_id, trigger)
    return matches[0] if matches else _FALLBACK_RULE


# ---------------------------------------------------------------------------
# ACT — reuses the existing, already-working control paths
# ---------------------------------------------------------------------------
def _sync_device_power(db, device: models.Device) -> None:
    """Mirrors a Device's status/current_power from whatever real control
    path it's backed by, before each analysis pass, so the engine (and the
    dashboard) always sees a fresh number without duplicating state.

    Goes through the hardware abstraction (app/hardware/bridge.py) instead
    of branching on door_ref_id/plug_ref_id here directly — same behavior,
    but the engine no longer needs to know Door and Plug exist at all."""
    controller = get_relay_controller(db, device)
    if controller is None:
        return
    is_on = controller.is_on()
    if is_on is not None:
        device.status = is_on
    if isinstance(controller, PowerMeter):
        device.current_power = controller.read_power_watts()


def _turn_device_off(db, device: models.Device) -> str:
    """The one place in the engine that actually commands a device off.
    Returns the command-lifecycle status (see hardware/interfaces.py) —
    never a bare bool — and persists it onto the device so the audit trail
    and dashboard can show it, distinct from `status` (this project's
    optimistic best-guess of the device's actual state)."""
    controller = get_relay_controller(db, device)
    if controller is None:
        status = interfaces.COMMAND_FAILED
    else:
        status = controller.turn_off()
    device.status = False
    device.current_power = None
    device.last_command_status = status
    device.last_command_at = datetime.datetime.utcnow()
    return status


def shutdown_non_critical(db, zone: models.Zone) -> tuple[list[dict], list[dict]]:
    """DECIDE+ACT once a zone is confirmed empty: switches off every
    NON_CRITICAL, automatically-controlled device that's currently on.

    Hardening constraint #3: CRITICAL-load protection is enforced HERE, in
    the engine itself, unconditionally — never delegated to AutomationRule
    configuration. Even a rule that somehow ends up implying a CRITICAL
    device should be touched cannot make this function act on it; every
    such device is explicitly refused and recorded in the returned
    `blocked` list with reason "Critical load protection," not silently
    skipped. Returns (changed, blocked).
    """
    changed = []
    blocked = []
    already_alerted_this_call = False
    for device in zone.devices:
        if not device.status:
            continue
        if device.criticality == "CRITICAL":
            blocked.append({"device_id": device.device_id, "name": device.name, "reason": "Critical load protection"})
            logger.warning(
                "ACTION BLOCKED — device %s ('%s') is CRITICAL; automation refuses to turn it off "
                "(Reason: Critical load protection)", device.device_id, device.name,
            )
            continue
        if not device.automatic_control_enabled:
            continue  # manual override — not a protection concern, no need to log as blocked
        before_watts = device.current_power
        command_status = _turn_device_off(db, device)
        changed.append({
            "device_id": device.device_id, "name": device.name, "from": "on", "to": "off",
            "watts": before_watts, "command_status": command_status,
        })
        # Real, persisted alert (final hardening pass, Phase 7) for a genuine
        # automation failure — the engine tried to shut a device off and the
        # command itself failed (no controller, or the controller reported
        # failure), not merely a UI indicator. Deduped per zone/type like the
        # other new alert sources above.
        if command_status == interfaces.COMMAND_FAILED and not already_alerted_this_call:
            already = (
                db.query(models.Alert)
                .filter(models.Alert.zone_id == zone.zone_id, models.Alert.type == "device_failed",
                        models.Alert.resolved.is_(False))
                .first()
            )
            if not already:
                db.add(models.Alert(zone_id=zone.zone_id, type="device_failed", severity="CRITICAL"))
                already_alerted_this_call = True
    return changed, blocked


# ---------------------------------------------------------------------------
# MONITOR — audit log
# ---------------------------------------------------------------------------
def _log(db, zone: models.Zone | None, decision: str, occupancy_snapshot: str | None,
          schedule_state: str | None, verification_result: str | None, power_snapshot: float | None,
          devices_changed: list[dict] | None = None, reason: str = "",
          trigger: str | None = None, confidence: float | None = None,
          evidence_detail: list[dict] | None = None, matched_rule: "models.AutomationRule | None" = None,
          requested_action: str | None = None, blocked_actions: list[dict] | None = None) -> dict:
    entry = models.AutomationLog(
        zone_id=zone.zone_id if zone else None,
        decision=decision,
        occupancy_snapshot=occupancy_snapshot,
        schedule_state=schedule_state,
        verification_result=verification_result,
        power_snapshot=power_snapshot,
        devices_changed=json.dumps(devices_changed) if devices_changed is not None else None,
        reason=reason,
        trigger=trigger,
        confidence=confidence,
        evidence_snapshot=json.dumps(evidence_detail) if evidence_detail is not None else None,
        matched_rule_id=matched_rule.rule_id if matched_rule is not None and matched_rule.rule_id else None,
        matched_rule_name=matched_rule.name if matched_rule is not None else None,
        requested_action=requested_action,
        blocked_actions=json.dumps(blocked_actions) if blocked_actions is not None else None,
    )
    db.add(entry)
    db.flush()
    logger.info("Zone %s: %s — %s", zone.zone_id if zone else "building", decision, reason)
    # Phase 2: broadcast so any listening node/dashboard sees the same
    # decision without polling the REST API. Best-effort — a disconnected
    # broker must never block or fail the actual decision being recorded.
    try:
        mqtt_service.publish_automation_decision(zone.zone_id if zone else None, {
            "log_id": entry.log_id, "decision": decision, "occupancy_snapshot": occupancy_snapshot,
            "schedule_state": schedule_state, "verification_result": verification_result,
            "power_snapshot": power_snapshot, "devices_changed": devices_changed, "reason": reason,
            "trigger": trigger, "confidence": confidence, "matched_rule": entry.matched_rule_name,
            "requested_action": requested_action, "blocked_actions": blocked_actions,
            "created_at": entry.created_at,
        })
    except Exception:
        logger.exception("Failed to broadcast automation decision for zone %s", zone.zone_id if zone else None)
    return {"log_id": entry.log_id, "decision": decision, "zone_id": zone.zone_id if zone else None}


# ---------------------------------------------------------------------------
# The per-zone state machine — one SENSE->ANALYZE->VERIFY->DECIDE->ACT->MONITOR pass
# ---------------------------------------------------------------------------
def process_zone_once(db, zone: models.Zone) -> dict | None:
    now = datetime.datetime.utcnow()

    for device in zone.devices:
        _sync_device_power(db, device)

    raw_state, confidence, evidence, evidence_detail = sense_zone_occupancy(db, zone)
    schedule_state, verification_minutes = get_schedule_state(db, zone.zone_id)
    prev_state = zone.occupancy_state
    evidence_text = "; ".join(evidence)
    result = None

    # Phase 4: an applicable AutomationRule can override how long the
    # verification window lasts for this zone (grace_period_minutes) — used
    # for both the UNKNOWN-branch's "give up waiting" check below and the
    # EMPTY-branch's "confirmed" check, so both agree on the same window.
    rule = resolve_rule(db, zone.zone_id, TRIGGER_CONFIRMED_EMPTY)
    if rule.grace_period_minutes is not None:
        verification_minutes = rule.grace_period_minutes

    # Phase 3: recorded every pass, transition or not — this is "how fresh
    # is our confidence right now," independent of occupancy_state_changed_at
    # (which only moves when the verdict itself changes).
    zone.occupancy_confidence = confidence
    zone.occupancy_evidence = json.dumps(evidence_detail)
    zone.occupancy_computed_at = now

    if raw_state == "OCCUPIED":
        if prev_state != "OCCUPIED":
            if prev_state == "VERIFYING":
                result = _log(db, zone, "VERIFICATION_CANCELLED", raw_state, schedule_state, "N/A", None,
                              reason=f"Occupancy detected during verification — {evidence_text}",
                              trigger="OCCUPANCY_DETECTED", confidence=confidence, evidence_detail=evidence_detail)
            zone.occupancy_state = "OCCUPIED"
            zone.occupancy_state_changed_at = now
            zone.verification_started_at = None

    elif raw_state == "UNKNOWN":
        # Fail-safe: uncertain data never causes a transition on its own.
        if prev_state == "VERIFYING" and zone.verification_started_at:
            elapsed_min = (now - zone.verification_started_at).total_seconds() / 60.0
            if elapsed_min >= verification_minutes:
                result = _log(db, zone, "SHUTDOWN_SKIPPED_UNCERTAIN", raw_state, schedule_state, "FAILED", None,
                              reason="Verification window elapsed but occupancy is uncertain (no fresh "
                                     f"sensor data) — refusing to shut down. {evidence_text}",
                              trigger=TRIGGER_CONFIRMED_EMPTY, confidence=confidence, evidence_detail=evidence_detail,
                              matched_rule=rule, requested_action=json.loads(rule.actions).get("action"))
                zone.verification_started_at = now  # restart the window rather than log-spam every pass

    elif raw_state == "EMPTY":
        if schedule_state != "CLOSED":
            # Normal daytime empty room (between classes, etc.) — reflect
            # it, but no verification/shutdown machinery engages.
            if prev_state not in ("EMPTY", "VERIFYING"):
                zone.occupancy_state = "EMPTY"
                zone.occupancy_state_changed_at = now
        else:
            if prev_state in ("OCCUPIED", "UNKNOWN"):
                zone.occupancy_state = "VERIFYING"
                zone.occupancy_state_changed_at = now
                zone.verification_started_at = now
                result = _log(db, zone, "VERIFICATION_STARTED", raw_state, schedule_state, "N/A", None,
                              reason=f"Zone reads empty after scheduled closing time — {evidence_text}",
                              trigger=TRIGGER_CONFIRMED_EMPTY, confidence=confidence, evidence_detail=evidence_detail)
            elif prev_state == "VERIFYING" and zone.verification_started_at:
                elapsed_min = (now - zone.verification_started_at).total_seconds() / 60.0
                if elapsed_min >= verification_minutes:
                    # Re-check: raw_state was just recomputed fresh above,
                    # right now, and is still EMPTY -> confirmed. The verdict
                    # itself always finalizes here; whether an action fires,
                    # and which, is now decided by `rule` (Phase 4) rather
                    # than being unconditional.
                    zone.occupancy_state = "EMPTY"
                    zone.occupancy_state_changed_at = now
                    zone.verification_started_at = None
                    requested_action = json.loads(rule.actions).get("action")

                    if confidence < rule.minimum_confidence:
                        result = _log(db, zone, "SHUTDOWN_SKIPPED_UNCERTAIN", raw_state, schedule_state, "FAILED", None,
                                      reason=f"Zone confirmed empty after {verification_minutes}min verification, "
                                             f"but confidence {confidence:.2f} is below rule '{rule.name}' "
                                             f"minimum {rule.minimum_confidence:.2f} — refusing to act. {evidence_text}",
                                      trigger=TRIGGER_CONFIRMED_EMPTY, confidence=confidence,
                                      evidence_detail=evidence_detail, matched_rule=rule,
                                      requested_action=requested_action)
                    else:
                        if requested_action == ACTION_SHUTDOWN_NON_CRITICAL:
                            power_before = sum((d.current_power or 0) for d in zone.devices)
                            changed, blocked = shutdown_non_critical(db, zone)
                            result = _log(db, zone, "SHUTDOWN_NON_CRITICAL", raw_state, schedule_state, "PASSED",
                                          power_before, devices_changed=changed,
                                          reason=f"Zone confirmed empty after {verification_minutes}min "
                                                 f"verification (rule '{rule.name}') — {evidence_text}",
                                          trigger=TRIGGER_CONFIRMED_EMPTY, confidence=confidence,
                                          evidence_detail=evidence_detail, matched_rule=rule,
                                          requested_action=requested_action, blocked_actions=blocked or None)
                        else:
                            logger.warning("Automation rule '%s' has unsupported action '%s' — no-op",
                                           rule.name, requested_action)
                            result = _log(db, zone, "NO_ACTION", raw_state, schedule_state, "PASSED", None,
                                          reason=f"Zone confirmed empty but rule '{rule.name}' has an unsupported "
                                                 f"action ('{requested_action}') — no device action taken. {evidence_text}",
                                          trigger=TRIGGER_CONFIRMED_EMPTY, confidence=confidence,
                                          evidence_detail=evidence_detail, matched_rule=rule,
                                          requested_action=requested_action)
                # else: still waiting — no-op, no log spam.
            # prev_state == "EMPTY": already handled, nothing to do.

    db.commit()
    return result


def run_automation_pass(db) -> int:
    """One pass across every zone. Returns how many zones produced an
    AutomationLog entry this pass (most zones, most passes, produce none —
    that's the expected steady state, not a bug)."""
    count = 0
    for zone in db.query(models.Zone).all():
        if process_zone_once(db, zone):
            count += 1
    return count


def building_occupancy_state(db) -> str:
    """Fuses every zone's occupancy_state into one building-wide verdict —
    Step 12's OCCUPIED/EMPTY/VERIFYING/UNKNOWN. Any zone still OCCUPIED
    means the building is OCCUPIED; failing that, any zone still VERIFYING
    means the building is VERIFYING; only if every zone agrees EMPTY is the
    building EMPTY; anything else (e.g. a zone with no data at all) is
    UNKNOWN rather than a guess.
    """
    states = [z.occupancy_state for z in db.query(models.Zone).all()]
    if not states:
        return "UNKNOWN"
    if "OCCUPIED" in states:
        return "OCCUPIED"
    if "VERIFYING" in states:
        return "VERIFYING"
    if all(s == "EMPTY" for s in states):
        return "EMPTY"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------
def _loop():
    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            run_automation_pass(db)
        except Exception:
            logger.exception("Automation pass failed")
        finally:
            db.close()
        _stop_event.wait(settings.AUTOMATION_INTERVAL_SECONDS)


def start():
    global _thread
    if settings.DISABLE_MQTT:
        logger.info("DISABLE_MQTT set — automation engine not started")
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    logger.info("Automation engine started (pass every %ss)", settings.AUTOMATION_INTERVAL_SECONDS)


def stop():
    _stop_event.set()
