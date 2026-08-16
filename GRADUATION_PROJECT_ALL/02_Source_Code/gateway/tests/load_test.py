"""
Phase 6 — backend concurrent-node load test (P6.3).

Simulates a scaled-up deployment against the REAL running backend (live
uvicorn process, real SQLite DB, real MQTT ingestion thread) rather than
mocking anything:

  - `N_NODES` independent MQTT client connections, each publishing access
    events at a steady rate for DURATION_S seconds — standing in for N
    concurrently-active door nodes (whether they reach the broker via the
    RS-485 gateway or directly over Wi-Fi is irrelevant to the backend,
    which is the point: the ingestion path is transport-agnostic).
  - `N_DASHBOARD_CLIENTS` threads concurrently polling GET /api/doors as
    fast as they can — standing in for multiple admins/dashboards open at
    once, plus the dashboard's own 5s poll loop from several sessions.

At the end it reports REST latency percentiles + error count, and compares
"events published" vs. "AccessEvent rows actually present in the DB" to
catch silently dropped writes under concurrency (a real risk with SQLite's
single-writer model, which is exactly why the proposal and backend README
already flag Postgres as the real-deployment recommendation — this test
produces the actual numbers behind that recommendation instead of leaving
it as an unverified claim).

Usage: python load_test.py --base-url http://127.0.0.1:8000 --node-codes NODE01,NODE02,... --duration 8
"""
import argparse
import json
import statistics
import sys
import threading
import time

import httpx
import paho.mqtt.client as mqtt


def login(base_url: str) -> str:
    r = httpx.post(f"{base_url}/api/auth/login", json={"email": "admin@example.edu", "password": "admin123"},
                   timeout=10, trust_env=False)
    r.raise_for_status()
    return r.json()["access_token"]


def node_publisher(code: str, mqtt_host: str, mqtt_port: int, duration_s: float, rate_hz: float, counters: dict, errors: list):
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"loadtest-{code}")
    try:
        client.connect(mqtt_host, mqtt_port, keepalive=30)
    except Exception as e:
        errors.append(f"{code}: connect failed: {e}")
        return
    client.loop_start()
    sent = 0
    deadline = time.monotonic() + duration_s
    interval = 1.0 / rate_hz
    while time.monotonic() < deadline:
        payload = json.dumps({"method": "card", "result": "granted"})
        client.publish(f"site/{code}/event", payload, qos=1)
        sent += 1
        time.sleep(interval)
    client.loop_stop()
    client.disconnect()
    counters[code] = sent


def dashboard_poller(base_url: str, token: str, duration_s: float, latencies: list, errors: list, stop_flag: list):
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=10, trust_env=False) as c:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline and not stop_flag[0]:
            t0 = time.monotonic()
            try:
                r = c.get(f"{base_url}/api/doors", headers=headers)
                elapsed_ms = (time.monotonic() - t0) * 1000
                if r.status_code == 200:
                    latencies.append(elapsed_ms)
                else:
                    errors.append(f"status={r.status_code}")
            except Exception as e:
                errors.append(str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--mqtt-host", default="127.0.0.1")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--node-codes", required=True, help="comma-separated door codes to simulate as publishing nodes")
    ap.add_argument("--duration", type=float, default=8.0)
    ap.add_argument("--rate-hz", type=float, default=2.0, help="events/sec per simulated node")
    ap.add_argument("--dashboard-clients", type=int, default=10)
    args = ap.parse_args()

    codes = args.node_codes.split(",")
    token = login(args.base_url)
    print(f"[load_test] logged in, simulating {len(codes)} nodes @ {args.rate_hz} Hz "
          f"and {args.dashboard_clients} concurrent dashboard pollers for {args.duration}s")

    node_counters = {}
    node_errors = []
    node_threads = [
        threading.Thread(target=node_publisher, args=(code, args.mqtt_host, args.mqtt_port, args.duration, args.rate_hz, node_counters, node_errors))
        for code in codes
    ]

    latencies = []
    rest_errors = []
    stop_flag = [False]
    dash_threads = [
        threading.Thread(target=dashboard_poller, args=(args.base_url, token, args.duration, latencies, rest_errors, stop_flag))
        for _ in range(args.dashboard_clients)
    ]

    t_start = time.monotonic()
    for t in node_threads + dash_threads:
        t.start()
    for t in node_threads + dash_threads:
        t.join()
    wall_s = time.monotonic() - t_start

    total_sent = sum(node_counters.values())
    print(f"\n=== MQTT ingestion (node -> backend) ===")
    print(f"nodes simulated: {len(codes)}  total events published: {total_sent}  wall time: {wall_s:.2f}s")
    print(f"publish errors: {len(node_errors)}")
    for e in node_errors:
        print("  ", e)

    print(f"\n=== REST load ({args.dashboard_clients} concurrent GET /api/doors) ===")
    print(f"requests completed: {len(latencies)}  errors: {len(rest_errors)}")
    if latencies:
        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95) - 1]
        print(f"latency ms: min={min(latencies):.1f} p50={p50:.1f} p95={p95:.1f} max={max(latencies):.1f}")
        print(f"throughput: {len(latencies) / wall_s:.1f} req/s")
    if rest_errors:
        print("sample errors:", rest_errors[:5])

    # Let the MQTT ingestion thread catch up on its queue before checking the DB.
    time.sleep(1.0)

    print(f"\n=== DB verification (were all published events actually ingested?) ===")
    r = httpx.get(f"{args.base_url}/api/doors", headers={"Authorization": f"Bearer {token}"}, timeout=10, trust_env=False)
    doors = {d["code"]: d["door_id"] for d in r.json()}
    total_logged = 0
    mismatches = []
    for code in codes:
        door_id = doors.get(code)
        if door_id is None:
            mismatches.append(f"{code}: not found in DB")
            continue
        logs = httpx.get(f"{args.base_url}/api/doors/{door_id}/logs", headers={"Authorization": f"Bearer {token}"}, timeout=10, trust_env=False).json()
        # logs endpoint caps at 200 rows — fine for this test's per-node volumes.
        got = len(logs)
        total_logged += got
        expected = node_counters.get(code, 0)
        if got < expected:
            mismatches.append(f"{code}: published {expected}, DB has {got} (capped at 200 by the logs endpoint if higher)")
    print(f"total published: {total_sent}  total rows found via /logs: {total_logged}")
    if mismatches:
        print("notes:")
        for m in mismatches:
            print("  ", m)
    else:
        print("every simulated node's published events are all accounted for in the DB.")


if __name__ == "__main__":
    sys.exit(main())
