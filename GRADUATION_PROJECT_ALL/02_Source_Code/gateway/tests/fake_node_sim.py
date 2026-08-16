"""
Fake door-node simulator — stands in for real ESP32 firmware on the RS-485
bus for gateway integration testing.

IMPORTANT SCOPE NOTE: this is a Python stand-in, not the real firmware. The
ESP32 toolchain could not be compiled in this sandbox (no hardware, same
limitation noted throughout door_node_firmware/), so this script exists to
let rs485_gateway.py be tested against something that speaks the real wire
protocol (rs485_protocol.h / gateway/protocol.py) over a real serial link,
without needing real hardware. It reimplements the POLL/DATA exchange from
main.cpp's loop()/networkWatchdogTask() at the protocol level only — it does
not model timing, electrical behavior, or anything else about the real
firmware. See door_node_firmware/tests/README.md for what IS verified about
the wire format itself (the C/Python cross-check), which this script builds
on top of rather than replaces.

One instance of this script can simulate several node addresses sharing a
single bus connection, which is a faithful model of a real multi-drop
RS-485 line — electrically, every node's transceiver sits on the same two
wires regardless of how many separate ESP32 boards there are.

Usage:
  python fake_node_sim.py --port /tmp/rs485_node_end --addrs 1:A101,2:A102
"""
import argparse
import json
import sys
import time
from pathlib import Path

import serial

sys.path.insert(0, str(Path(__file__).parent.parent))
import protocol


class FakeNode:
    def __init__(self, addr: int, code: str):
        self.addr = addr
        self.code = code
        self.locked = True
        self.tamper_lockout = False
        self.pending_events = []
        self.pending_alerts = []
        self.polls_served = 0

    def apply_cmd(self, cmd):
        if cmd == "unlock" and not self.tamper_lockout:
            self.locked = False
            self.pending_events.append({"method": "card", "result": "granted"})
        elif cmd == "lock":
            self.locked = True
        elif cmd == "clear_tamper":
            self.tamper_lockout = False

    def build_data_payload(self) -> bytes:
        payload = {
            "online": True,
            "locked": self.locked,
            "events": self.pending_events,
            "alerts": self.pending_alerts,
        }
        self.pending_events = []
        self.pending_alerts = []
        return json.dumps(payload).encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--addrs", required=True, help="comma list of addr:code, e.g. 1:A101,2:A102")
    ap.add_argument("--auto-event-every", type=float, default=0,
                     help="seconds between synthetic 'card granted' events on the first node, 0=disabled")
    ap.add_argument("--duration", type=float, default=0, help="exit after N seconds, 0=run forever")
    args = ap.parse_args()

    nodes = {}
    for pair in args.addrs.split(","):
        addr_str, code = pair.split(":")
        nodes[int(addr_str)] = FakeNode(int(addr_str), code)

    ser = serial.Serial(args.port, args.baud, timeout=0.02)
    frame_parser = protocol.FrameParser()

    start = time.monotonic()
    last_auto_event = start
    first_node = next(iter(nodes.values()))

    print(f"[fake_node_sim] simulating nodes: {[(n.addr, n.code) for n in nodes.values()]}", flush=True)

    while True:
        if args.duration and (time.monotonic() - start) > args.duration:
            print("[fake_node_sim] duration elapsed, exiting", flush=True)
            break

        chunk = ser.read(64)
        if chunk:
            for frame in frame_parser.feed_bytes(chunk):
                if frame.type != protocol.TYPE_POLL:
                    continue
                node = nodes.get(frame.addr)
                if node is None:
                    continue  # poll for a different node on this shared bus
                node.polls_served += 1
                try:
                    poll_data = json.loads(frame.payload) if frame.payload else {}
                except json.JSONDecodeError:
                    poll_data = {}
                cmd = poll_data.get("cmd")
                if cmd:
                    print(f"[fake_node_sim] addr={node.addr} ({node.code}) applying cmd={cmd!r}", flush=True)
                    node.apply_cmd(cmd)

                response = node.build_data_payload()
                out_frame = protocol.encode_frame(node.addr, protocol.TYPE_DATA, response)
                ser.write(out_frame)
                ser.flush()

        if args.auto_event_every and (time.monotonic() - last_auto_event) > args.auto_event_every:
            first_node.pending_events.append({"method": "card", "result": "granted"})
            last_auto_event = time.monotonic()
            print(f"[fake_node_sim] queued synthetic event for addr={first_node.addr}", flush=True)


if __name__ == "__main__":
    main()
