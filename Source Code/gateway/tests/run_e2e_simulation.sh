#!/usr/bin/env bash
# End-to-end simulation WITHOUT hardware:
#   backend (REST + MQTT) <-> local broker <-> gateway <-> virtual RS-485 serial pair <-> fake door nodes
# Checks: gateway publishes node status; an admin "unlock" override travels
# backend -> MQTT -> gateway -> RS-485 -> node, and the node's access event + ack come back.
#
# Requirements: socat, Python 3.10+, and a throw-away virtualenv with:
#   pip install amqtt pyserial PyYAML "paho-mqtt==2.1.0"      (pure-Python MQTT broker, no mosquitto needed)
# The backend venv (Source Code/backend/venv) must already exist, or set E2E_BE_PY to any Python that has the backend requirements installed.
# Seeded demo admin credentials are read from the environment (never hard-coded here):
#   E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD   (see Source Code/backend/scripts/seed_db.py for the sample values)
# Usage:  E2E_PY=/path/to/gateway-venv/bin/python E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... ./run_e2e_simulation.sh
# Uses a temp copy of the backend DB; nothing in the repository is modified. Ports: MQTT 18830, API 8766.
set -u
: "${E2E_PY:?set E2E_PY to the python of a venv with amqtt/pyserial/PyYAML/paho-mqtt}"
: "${E2E_ADMIN_EMAIL:?}"; : "${E2E_ADMIN_PASSWORD:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"; GW="$(dirname "$HERE")"; BE="$(cd "$GW/../backend" && pwd)"
W="$(mktemp -d)"; trap 'kill $(jobs -p) 2>/dev/null; pkill -P $$ 2>/dev/null; rm -rf "$W"' EXIT
BIN="$(dirname "$E2E_PY")"
cat > "$W/broker.yaml" <<Y
listeners:
  default: {type: tcp, bind: 127.0.0.1:18830}
plugins:
  amqtt.plugins.authentication.AnonymousAuthPlugin: {allow_anonymous: true}
Y
cat > "$W/gw.yaml" <<Y
serial: {port: $W/gw_end, baud: 9600}
polling: {poll_timeout_ms: 300, offline_after_misses: 3, inter_poll_delay_ms: 50}
nodes: [{addr: 1, code: A101}, {addr: 2, code: A102}]
mqtt: {host: 127.0.0.1, port: 18830, use_tls: false, username: null, password: null, client_id: building-gateway}
Y
"$BIN/amqtt" -c "$W/broker.yaml" > "$W/broker.log" 2>&1 & sleep 4
socat pty,raw,echo=0,link="$W/gw_end" pty,raw,echo=0,link="$W/node_end" > /dev/null 2>&1 & sleep 1
"$E2E_PY" "$GW/tests/fake_node_sim.py" --port "$W/node_end" --addrs 1:A101,2:A102 > "$W/node.log" 2>&1 &
# throw-away backend DB seeded from the repo's seed script (copy of the code, original untouched)
mkdir "$W/be"; cp -r "$BE/app" "$BE/scripts" "$BE/requirements.txt" "$W/be/"; cd "$W/be"
PYBE="${E2E_BE_PY:-$BE/venv/bin/python}"; "$PYBE" -m scripts.seed_db > /dev/null 2>&1
DISABLE_MQTT=false MQTT_BROKER_HOST=127.0.0.1 MQTT_BROKER_PORT=18830 "$PYBE" -m uvicorn app.main:app --port 8766 > "$W/backend.log" 2>&1 & sleep 6
(cd "$GW" && "$E2E_PY" rs485_gateway.py --config "$W/gw.yaml" > "$W/gateway.log" 2>&1 &) ; sleep 12
api() { curl -s --max-time 6 "$@"; }
TOK=$(api -X POST http://127.0.0.1:8766/api/auth/login -H 'Content-Type: application/json' \
  -d "{\"email\":\"$E2E_ADMIN_EMAIL\",\"password\":\"$E2E_ADMIN_PASSWORD\"}" | "$PYBE" -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
[ -n "$TOK" ] || { echo "FAIL: login"; exit 1; }
api http://127.0.0.1:8766/api/doors -H "Authorization: Bearer $TOK" > "$W/doors.json"
"$PYBE" - "$W/doors.json" <<'P' || exit 1
import json,sys
d={x["code"]:x for x in json.load(open(sys.argv[1]))}
ok=all(d[c]["last_seen"] for c in ("A101","A102"))
print("status via gateway (A101,A102 last_seen set):","PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
P
DID=$("$PYBE" -c "import json,sys;print([x['door_id'] for x in json.load(open(sys.argv[1])) if x['code']=='A101'][0])" "$W/doors.json")
R=$(api -X POST "http://127.0.0.1:8766/api/doors/$DID/override" -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{"action":"unlock"}')
echo "override response: $R"; sleep 6
grep -q "applying cmd='unlock'" "$W/node.log" && echo "command reached node over RS-485: PASS" || { echo "command reached node: FAIL"; exit 1; }
"$PYBE" - <<'P'
import sqlite3
c=sqlite3.connect("access_control.db")
rows=c.execute("select method,result from access_events order by event_id").fetchall()
print("access_events:",rows)
ok=("override","sent") in rows and any(m=="card" and r=="granted" for m,r in rows)
print("override logged + node event ingested:","PASS" if ok else "FAIL")
P
