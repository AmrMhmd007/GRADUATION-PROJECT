"""
Phase 7 — full-system scenario test.

Runs a realistic admin session against the LIVE stack (real backend, real
MQTT broker, real Building Gateway relaying real simulated door nodes over
a virtual RS-485 link) and checks the outcome at each step through the
actual REST API a real dashboard would use — login, door status, tamper
alert intake + resolution, remote override, and login rate-limiting.

This intentionally reuses REST endpoints exactly as the dashboard
(dashboard/src/api/client.js) calls them, so a pass here is evidence the
whole chain works together, not just that each piece works in isolation
(which Phases 3-6 already covered separately).

Usage: python full_scenario_test.py --base-url http://127.0.0.1:8000 --mqtt-host 127.0.0.1 --mqtt-port 1883
"""
import argparse
import json
import sys
import time

import httpx
import paho.mqtt.client as mqtt


def login(base_url, email, password):
    r = httpx.post(f"{base_url}/api/auth/login", json={"email": email, "password": password},
                    timeout=10, trust_env=False)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--mqtt-host", default="127.0.0.1")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    args = ap.parse_args()

    failures = []

    def check(label, cond):
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {label}")
        if not cond:
            failures.append(label)

    # --- 1. Login ---------------------------------------------------
    r = login(args.base_url, "admin@example.edu", "admin123")
    check("admin login succeeds", r.status_code == 200)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # --- 2. Door status reflects the live gateway-relayed nodes ------
    r = httpx.get(f"{args.base_url}/api/doors", headers=headers, timeout=10, trust_env=False)
    doors = {d["code"]: d for d in r.json()}
    check("GET /api/doors returns 200", r.status_code == 200)
    for code in ("A101", "A102", "MAIN", "SRV1"):
        check(f"door {code} is online (relayed via gateway)", doors.get(code, {}).get("online") is True)
    a101_id = doors["A101"]["door_id"]

    # --- 3. Tamper alert intake ---------------------------------------
    mqc = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="scenario-test-publisher")
    mqc.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
    mqc.loop_start()
    mqc.publish("site/A101/alert", json.dumps({"type": "tamper"}), qos=1)
    time.sleep(0.5)

    r = httpx.get(f"{args.base_url}/api/alerts", params={"resolved": "false"}, headers=headers, timeout=10, trust_env=False)
    unresolved = r.json()
    tamper_alerts = [a for a in unresolved if a["type"] == "tamper" and a["door_id"] == a101_id]
    check("tamper alert ingested and visible unresolved", len(tamper_alerts) >= 1)

    if tamper_alerts:
        alert_id = tamper_alerts[0]["alert_id"]
        r = httpx.put(f"{args.base_url}/api/alerts/{alert_id}/resolve", headers=headers, timeout=10, trust_env=False)
        check("resolve tamper alert succeeds", r.status_code == 200 and r.json()["resolved"] is True)

        r = httpx.get(f"{args.base_url}/api/alerts", params={"resolved": "false"}, headers=headers, timeout=10, trust_env=False)
        still_unresolved_ids = [a["alert_id"] for a in r.json()]
        check("resolved alert no longer in unresolved list", alert_id not in still_unresolved_ids)

    # --- 4. Remote override round-trip (REST -> MQTT -> gateway -> node -> event -> DB) ---
    r = httpx.post(f"{args.base_url}/api/doors/{a101_id}/override", json={"action": "unlock"},
                    headers=headers, timeout=10, trust_env=False)
    check("override request accepted", r.status_code == 200)
    check("override delivered over MQTT", r.json().get("mqtt_delivered") is True)

    time.sleep(1.0)
    r = httpx.get(f"{args.base_url}/api/doors/{a101_id}/logs", headers=headers, timeout=10, trust_env=False)
    methods = [e["method"] for e in r.json()]
    check("override event logged", "override" in methods)

    # --- 5. Login rate limiting on the live server ---------------------
    last_status = None
    for i in range(6):
        r = login(args.base_url, "instructor@example.edu", "wrong-password")
        last_status = r.status_code
    check("6th consecutive bad login is rate-limited (429)", last_status == 429)

    # --- Summary ---------------------------------------------------
    print()
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    else:
        print("=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
