"""
Tests for Phase 4 (database-backed automation rules): app/models.py's
AutomationRule, automation_engine.get_applicable_rules/resolve_rule, their
integration into process_zone_once, and the /api/automation/rules CRUD
endpoints. test_automation_engine.py's own suite (fallback-rule behavior,
unchanged) is the proof this is a pure addition — these tests focus on what
a rule can now change that hardcoded Python couldn't.
"""
import datetime
import json

from app import models
from app.services import automation_engine


def _zone(db, name="Rule Zone"):
    zone = models.Zone(name=name, zone_type="CLASSROOM", occupancy_state="UNKNOWN")
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def _sensor(db, zone_id, occupied):
    sensor = models.Sensor(
        zone_id=zone_id, sensor_type="PIR", status="online",
        occupancy_state=occupied, last_seen=datetime.datetime.utcnow(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def _device(db, zone_id, name, type_, criticality, status=False):
    device = models.Device(zone_id=zone_id, name=name, type=type_, criticality=criticality, status=status)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _closed_schedule(db, zone_id, verification_minutes=5):
    now = datetime.datetime.now()
    db.add(models.ZoneSchedule(
        zone_id=zone_id, day_of_week=None,
        open_time=(now - datetime.timedelta(hours=2)).time(),
        close_time=(now - datetime.timedelta(minutes=2)).time(),
        grace_minutes=0, verification_minutes=verification_minutes,
    ))
    db.commit()


def _rule(db, zone_id=None, priority=0, enabled=True, minimum_confidence=0.0,
          grace_period_minutes=None, action="SHUTDOWN_NON_CRITICAL", name="Test rule"):
    rule = models.AutomationRule(
        name=name, zone_id=zone_id, enabled=enabled, priority=priority,
        conditions=json.dumps({"trigger": "CONFIRMED_EMPTY"}),
        actions=json.dumps({"action": action}),
        grace_period_minutes=grace_period_minutes, minimum_confidence=minimum_confidence,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# Rule resolution
# ---------------------------------------------------------------------------
def test_resolve_rule_falls_back_when_no_rows_exist(db_session):
    zone = _zone(db_session)
    rule = automation_engine.resolve_rule(db_session, zone.zone_id, "CONFIRMED_EMPTY")
    assert rule.name.startswith("(fallback")
    assert rule.minimum_confidence == 0.0


def test_zone_specific_rule_outranks_building_wide(db_session):
    zone = _zone(db_session)
    _rule(db_session, zone_id=None, name="Building default", priority=100)
    specific = _rule(db_session, zone_id=zone.zone_id, name="This zone only", priority=0)

    resolved = automation_engine.resolve_rule(db_session, zone.zone_id, "CONFIRMED_EMPTY")
    assert resolved.rule_id == specific.rule_id  # specific wins even with lower priority


def test_higher_priority_wins_among_equally_specific_rules(db_session):
    zone = _zone(db_session)
    _rule(db_session, zone_id=zone.zone_id, name="Low priority", priority=1)
    high = _rule(db_session, zone_id=zone.zone_id, name="High priority", priority=5)

    resolved = automation_engine.resolve_rule(db_session, zone.zone_id, "CONFIRMED_EMPTY")
    assert resolved.rule_id == high.rule_id


def test_disabled_rule_is_never_returned(db_session):
    zone = _zone(db_session)
    _rule(db_session, zone_id=zone.zone_id, enabled=False, name="Disabled")

    resolved = automation_engine.resolve_rule(db_session, zone.zone_id, "CONFIRMED_EMPTY")
    assert resolved.name.startswith("(fallback")


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------
def test_rule_minimum_confidence_blocks_shutdown(db_session):
    zone = _zone(db_session)
    # A single fresh sensor -> confidence 1.0 normally, but this rule
    # demands more than any single signal alone can ever provide.
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    device = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)
    _rule(db_session, zone_id=zone.zone_id, minimum_confidence=1.5, name="Impossible bar")

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    db_session.refresh(device)
    assert zone.occupancy_state == "EMPTY"  # verdict still finalizes
    assert device.status is True  # but nothing was switched off
    assert result["decision"] == "SHUTDOWN_SKIPPED_UNCERTAIN"


def test_rule_grace_period_overrides_schedule_verification_minutes(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=30)  # long schedule window
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    device = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)
    # Rule shortens the window to 5 minutes -> 10 elapsed minutes is enough.
    _rule(db_session, zone_id=zone.zone_id, grace_period_minutes=5, name="Faster rule")

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(device)
    assert result["decision"] == "SHUTDOWN_NON_CRITICAL"
    assert device.status is False


def test_rule_with_unsupported_action_is_a_safe_no_op(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    device = _device(db_session, zone.zone_id, "Light", "LIGHT", "NON_CRITICAL", status=True)
    _rule(db_session, zone_id=zone.zone_id, action="SOMETHING_NOT_IMPLEMENTED", name="Future rule")

    result = automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(zone)
    db_session.refresh(device)
    assert zone.occupancy_state == "EMPTY"
    assert device.status is True  # never touched — unsupported action does nothing, doesn't crash
    assert result["decision"] == "NO_ACTION"


def test_critical_device_never_touched_even_with_a_permissive_rule(db_session):
    zone = _zone(db_session)
    _sensor(db_session, zone.zone_id, occupied=False)
    _closed_schedule(db_session, zone.zone_id, verification_minutes=5)
    zone.occupancy_state = "VERIFYING"
    zone.verification_started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    db_session.commit()
    server = _device(db_session, zone.zone_id, "Server", "SERVER", "CRITICAL", status=True)
    _rule(db_session, zone_id=zone.zone_id, minimum_confidence=0.0, name="Permissive")

    automation_engine.process_zone_once(db_session, zone)

    db_session.refresh(server)
    assert server.status is True  # hard invariant — no rule field can touch this


# ---------------------------------------------------------------------------
# CRUD API
# ---------------------------------------------------------------------------
def test_create_and_list_automation_rule(client, admin_token, db_session):
    zone = _zone(db_session)
    resp = client.post(
        "/api/automation/rules",
        json={
            "name": "API rule", "zone_id": zone.zone_id,
            "conditions": {"trigger": "CONFIRMED_EMPTY"},
            "actions": {"action": "SHUTDOWN_NON_CRITICAL"},
            "minimum_confidence": 0.5,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    rule_id = resp.json()["rule_id"]

    listed = client.get(f"/api/automation/rules?zone_id={zone.zone_id}",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert listed.status_code == 200
    assert any(r["rule_id"] == rule_id for r in listed.json())


def test_create_automation_rule_rejects_unimplemented_trigger(client, admin_token, db_session):
    zone = _zone(db_session)
    resp = client.post(
        "/api/automation/rules",
        json={
            "name": "Bad trigger", "zone_id": zone.zone_id,
            "conditions": {"trigger": "SOMETHING_ELSE"},
            "actions": {"action": "SHUTDOWN_NON_CRITICAL"},
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


def test_non_admin_cannot_create_automation_rule(client, instructor_token, db_session):
    zone = _zone(db_session)
    resp = client.post(
        "/api/automation/rules",
        json={
            "name": "Nope", "zone_id": zone.zone_id,
            "conditions": {"trigger": "CONFIRMED_EMPTY"},
            "actions": {"action": "SHUTDOWN_NON_CRITICAL"},
        },
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert resp.status_code == 403


def test_update_and_delete_automation_rule(client, admin_token, db_session):
    zone = _zone(db_session)
    rule = _rule(db_session, zone_id=zone.zone_id, name="To edit")

    upd = client.put(
        f"/api/automation/rules/{rule.rule_id}", json={"enabled": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert upd.status_code == 200
    assert upd.json()["enabled"] is False

    dele = client.delete(f"/api/automation/rules/{rule.rule_id}",
                          headers={"Authorization": f"Bearer {admin_token}"})
    assert dele.status_code == 204
    assert db_session.query(models.AutomationRule).filter(
        models.AutomationRule.rule_id == rule.rule_id
    ).first() is None


# ---------------------------------------------------------------------------
# Phase 11: additional persistence/API-level CRUD coverage the original
# suite above didn't exercise — fresh reads (not just the mutating
# response), 404s, and update/delete RBAC.
# ---------------------------------------------------------------------------
def test_automation_rule_update_persists_on_fresh_read(client, admin_token, db_session):
    zone = _zone(db_session)
    rule = _rule(db_session, zone_id=zone.zone_id, name="Fresh Read Rule")
    headers = {"Authorization": f"Bearer {admin_token}"}

    client.put(f"/api/automation/rules/{rule.rule_id}", json={"name": "Renamed Rule", "priority": 7}, headers=headers)

    # Fresh GET, not the PUT response.
    listed = client.get(f"/api/automation/rules?zone_id={zone.zone_id}", headers=headers)
    row = next(r for r in listed.json() if r["rule_id"] == rule.rule_id)
    assert row["name"] == "Renamed Rule"
    assert row["priority"] == 7


def test_automation_rule_delete_persists_on_fresh_read(client, admin_token, db_session):
    zone = _zone(db_session)
    rule = _rule(db_session, zone_id=zone.zone_id, name="To Delete Fresh")
    headers = {"Authorization": f"Bearer {admin_token}"}

    client.delete(f"/api/automation/rules/{rule.rule_id}", headers=headers)

    listed = client.get(f"/api/automation/rules?zone_id={zone.zone_id}", headers=headers)
    assert all(r["rule_id"] != rule.rule_id for r in listed.json())


def test_update_nonexistent_automation_rule_404(client, admin_token):
    resp = client.put("/api/automation/rules/999999", json={"enabled": False},
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_delete_nonexistent_automation_rule_404(client, admin_token):
    resp = client.delete("/api/automation/rules/999999", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_non_admin_cannot_update_or_delete_automation_rule(client, instructor_token, db_session):
    zone = _zone(db_session)
    rule = _rule(db_session, zone_id=zone.zone_id, name="RBAC Protected Rule")
    headers = {"Authorization": f"Bearer {instructor_token}"}

    upd = client.put(f"/api/automation/rules/{rule.rule_id}", json={"enabled": False}, headers=headers)
    assert upd.status_code == 403

    dele = client.delete(f"/api/automation/rules/{rule.rule_id}", headers=headers)
    assert dele.status_code == 403

    # Untouched by the rejected attempts.
    assert db_session.query(models.AutomationRule).filter(
        models.AutomationRule.rule_id == rule.rule_id
    ).first() is not None


def test_unauthenticated_cannot_create_update_or_delete_automation_rule(client, db_session):
    zone = _zone(db_session)
    rule = _rule(db_session, zone_id=zone.zone_id, name="Unauth Protected Rule")

    assert client.post("/api/automation/rules", json={
        "name": "X", "conditions": {"trigger": "CONFIRMED_EMPTY"}, "actions": {"action": "SHUTDOWN_NON_CRITICAL"},
    }).status_code == 401
    assert client.put(f"/api/automation/rules/{rule.rule_id}", json={"enabled": False}).status_code == 401
    assert client.delete(f"/api/automation/rules/{rule.rule_id}").status_code == 401


def test_list_automation_rules_is_readable_by_any_authenticated_role(client, instructor_token, db_session):
    zone = _zone(db_session)
    _rule(db_session, zone_id=zone.zone_id, name="Readable Rule")
    resp = client.get(f"/api/automation/rules?zone_id={zone.zone_id}",
                       headers={"Authorization": f"Bearer {instructor_token}"})
    assert resp.status_code == 200
    assert any(r["name"] == "Readable Rule" for r in resp.json())
