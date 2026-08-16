# Building Gateway — Phase 6 (Multi-Node Scaling)

The RS-485-to-MQTT bridge referenced as a box in the Phase 1 System Design
Document's architecture diagram (Figure 1), and left unbuilt through Phase 5
while the single door-node prototype talked to the broker directly over
Wi-Fi. This is the real implementation.

## What it does

`rs485_gateway.py` is the RS-485 bus master: it polls each configured door
node in round-robin order (`site/{code}/...` topics use the same door
`code` your backend already knows about — see `gateway_config.example.yaml`),
and republishes whatever a node reports (status/events/alerts) onto the
exact MQTT topics a directly-connected node would use. `backend/app/
services/mqtt_service.py` needed **zero changes** to ingest gateway-relayed
nodes alongside directly-connected ones — from the backend's point of view
there is no difference.

It also subscribes to `site/{code}/cmd` for every configured node (the same
topic `POST /api/doors/{id}/override` already publishes to) and embeds the
command into that node's next poll, since a node reachable only over RS-485
isn't itself subscribed to MQTT.

## Wire protocol

See `../door_node_firmware/include/rs485_protocol.h` for the full frame
format (SOF/ADDR/TYPE/LEN/PAYLOAD/CHECKSUM/EOF with byte stuffing) and
`protocol.py` for this side's independent re-implementation of it. The two
are cross-checked byte-for-byte in `../door_node_firmware/tests/
test_cross_lang.py` — see that directory's README for how to run it.

## Setup

1. `pip install -r requirements.txt`
2. Copy `gateway_config.example.yaml` to `gateway_config.yaml` and edit:
   - `serial.port` — the RS-485 USB adapter's device path on the gateway host
   - `nodes` — each node's bus address (must match `RS485_NODE_ADDR` in that
     node's `include/config.h`) mapped to its door `code`
   - `mqtt` — broker connection details (same broker the backend uses)
3. `python rs485_gateway.py --config gateway_config.yaml`

## Testing without real hardware

There is no physical RS-485 bus or building available in this environment.
`tests/fake_node_sim.py` is a Python stand-in for real door-node firmware —
it speaks the same wire protocol and can simulate several node addresses
sharing one bus connection (a faithful model of a real multi-drop line,
since every node's transceiver sits on the same two wires regardless of how
many boards there are). Paired with a `socat` virtual serial port pair and
a real local MQTT broker, this lets the gateway be exercised end to end —
polling, command relay, event/alert forwarding — for real, without
pretending the ESP32 firmware itself has been hardware-tested (it hasn't;
see the firmware README).

`tests/load_test.py` drives a concurrent-node load test against a live
backend instance — see `Phase6_Multi_Node_Deployment_Guide.docx` for the
methodology and actual results from running it.

## Known limitations

- No real RS-485 electrical layer was available to test against — bus
  contention, noise, and transceiver turnaround timing are unverified
  (the wire *protocol* is verified, per above; the *physical bus* is not).
- Command delivery to an RS-485 node is best-effort: the gateway embeds a
  command in the next poll and immediately publishes a `cmd/ack`, but that
  ack means "handed to the node's poll response," not "the node confirmed
  it executed the command" — the actual confirmation is whatever the node
  reports in its next status/event.
- Single bus master, no redundancy: if the gateway process or host goes
  down, every RS-485-only node loses its primary path and falls back to
  direct Wi-Fi/MQTT (by design — see the firmware's hybrid fallback logic)
  but the gateway itself has no failover.
