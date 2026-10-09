"""
Building Gateway — Phase 6 (multi-node scaling).

Bridges the RS-485 multi-drop backbone (see ../door_node_firmware/include/
rs485_protocol.h for the wire format) to the MQTT broker the backend already
speaks to. This is the "Building Gateway" box in the System Design
Document's architecture diagram (Figure 1) — through Phase 5 it existed only
as a diagram; this is the real implementation.

Responsibilities:
  - Bus master: polls each configured door node in round-robin order and
    reads back its DATA response (status + queued events/alerts).
  - Republishes what each node reports onto the exact same MQTT topics a
    node would use if it were talking to the broker directly over Wi-Fi
    (site/{code}/status, /event, /alert) — so backend/app/services/
    mqtt_service.py needs zero changes to ingest gateway-relayed nodes
    alongside directly-connected ones.
  - Subscribes to site/{code}/cmd for every configured node and queues the
    command to be embedded in that node's next poll, since a node on the
    RS-485 path isn't itself subscribed to MQTT.

Run: python rs485_gateway.py --config gateway_config.yaml
"""
import argparse
import logging
import sys
import threading
import time
import json
from pathlib import Path

import serial
import yaml
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).parent))
import protocol

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gateway")


class NodeState:
    def __init__(self, addr: int, code: str):
        self.addr = addr
        self.code = code
        self.online = False
        self.consecutive_misses = 0
        self.pending_cmd = None  # set by MQTT on_message, consumed by next poll


class BuildingGateway:
    def __init__(self, config: dict):
        self.config = config
        self.nodes = [NodeState(n["addr"], n["code"]) for n in config["nodes"]]
        self.nodes_by_code = {n.code: n for n in self.nodes}
        self._cmd_lock = threading.Lock()
        self._stop = threading.Event()

        ser_cfg = config["serial"]
        self.ser = serial.Serial(ser_cfg["port"], ser_cfg["baud"], timeout=0.02)

        mqtt_cfg = config["mqtt"]
        self.mqtt = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=mqtt_cfg.get("client_id", "building-gateway"),
        )
        if mqtt_cfg.get("username"):
            self.mqtt.username_pw_set(mqtt_cfg["username"], mqtt_cfg.get("password"))
        if mqtt_cfg.get("use_tls"):
            self.mqtt.tls_set()
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_message = self._on_mqtt_message

    # --- MQTT side ----------------------------------------------------

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        logger.info("MQTT connected, rc=%s", rc)
        for node in self.nodes:
            topic = f"site/{node.code}/cmd"
            client.subscribe(topic)
            logger.info("Subscribed %s (relays to RS-485 addr %d)", topic, node.addr)

    def _on_mqtt_message(self, client, userdata, msg):
        # topic looks like site/{code}/cmd
        code = msg.topic.split("/")[1]
        node = self.nodes_by_code.get(code)
        if node is None:
            logger.warning("cmd for unknown door code '%s'", code)
            return
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.warning("bad JSON on %s: %r", msg.topic, msg.payload)
            return
        cmd = data.get("cmd")
        if not cmd:
            return
        with self._cmd_lock:
            node.pending_cmd = cmd
        logger.info("Queued cmd '%s' for node addr=%d (%s), will ride the next poll", cmd, node.addr, code)

    def _take_pending_cmd(self, node: NodeState):
        with self._cmd_lock:
            cmd = node.pending_cmd
            node.pending_cmd = None
            return cmd

    def _publish_status(self, code: str, online: bool):
        self.mqtt.publish(f"site/{code}/status", "online" if online else "offline", retain=True)

    def _publish_event(self, code: str, event: dict):
        payload = dict(event)
        payload["door_id"] = code
        payload["via"] = "rs485"
        self.mqtt.publish(f"site/{code}/event", json.dumps(payload))

    def _publish_alert(self, code: str, alert: dict):
        payload = dict(alert)
        payload["door_id"] = code
        payload["via"] = "rs485"
        self.mqtt.publish(f"site/{code}/alert", json.dumps(payload))

    def _publish_cmd_ack(self, code: str, cmd: str):
        self.mqtt.publish(f"site/{code}/cmd/ack", json.dumps({"door_id": code, "cmd": cmd, "ack": True}))

    # --- RS-485 side ----------------------------------------------------

    def _poll_node(self, node: NodeState):
        cmd = self._take_pending_cmd(node)
        payload = json.dumps({"cmd": cmd} if cmd else {}).encode()
        frame = protocol.encode_frame(node.addr, protocol.TYPE_POLL, payload)

        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()

        if cmd:
            logger.info("Polled addr=%d (%s) with cmd='%s'", node.addr, node.code, cmd)

        parser = protocol.FrameParser()
        deadline = time.monotonic() + self.config["polling"]["poll_timeout_ms"] / 1000.0
        while time.monotonic() < deadline:
            chunk = self.ser.read(64)
            if chunk:
                for frame_out in parser.feed_bytes(chunk):
                    if frame_out.addr == node.addr and frame_out.type == protocol.TYPE_DATA:
                        self._handle_data(node, frame_out.payload, cmd)
                        return True
        # Timeout — no response from this node this cycle.
        node.consecutive_misses += 1
        offline_after = self.config["polling"]["offline_after_misses"]
        if node.consecutive_misses == offline_after:
            logger.warning("addr=%d (%s) missed %d consecutive polls — marking offline",
                            node.addr, node.code, offline_after)
            node.online = False
            self._publish_status(node.code, False)
        return False

    def _handle_data(self, node: NodeState, payload: bytes, cmd_sent):
        node.consecutive_misses = 0
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("addr=%d sent unparseable DATA payload: %r", node.addr, payload)
            return

        if not node.online:
            node.online = True
            self._publish_status(node.code, True)

        for event in data.get("events", []):
            self._publish_event(node.code, event)
        for alert in data.get("alerts", []):
            self._publish_alert(node.code, alert)
        if cmd_sent:
            self._publish_cmd_ack(node.code, cmd_sent)

    def run(self):
        self.mqtt.connect(self.config["mqtt"]["host"], self.config["mqtt"]["port"], keepalive=30)
        self.mqtt.loop_start()
        inter_poll_s = self.config["polling"]["inter_poll_delay_ms"] / 1000.0
        logger.info("Gateway polling %d node(s) on %s", len(self.nodes), self.config["serial"]["port"])
        try:
            while not self._stop.is_set():
                for node in self.nodes:
                    self._poll_node(node)
                    time.sleep(inter_poll_s)
        except KeyboardInterrupt:
            pass
        finally:
            self.mqtt.loop_stop()
            self.ser.close()

    def stop(self):
        self._stop.set()


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="gateway_config.yaml")
    args = parser.parse_args()
    gw = BuildingGateway(load_config(args.config))
    gw.run()


if __name__ == "__main__":
    main()
