"""
Hardware abstraction layer for the Smart Building platform.

Nothing in here talks to real hardware yet — no ESP32 firmware, no relay
wiring, no power meter has been built or purchased. What this package
provides is the *contract* the decision engine (services/automation_engine.py)
programs against, so that when real hardware does arrive, it plugs in behind
one of these interfaces instead of requiring the engine to be rewritten.

Two concrete implementations exist today, both in bridge.py:

- The "legacy bridge": wraps this project's original, already-working
  Door.ac_on/light_on and Plug.on control path (services/mqtt_service.py's
  publish_ac/publish_light/publish_plug) — unchanged from before this
  package existed. A Device row with door_ref_id/plug_ref_id set resolves
  to this bridge.
- The "generic bridge": for a freestanding Device/Sensor with no legacy
  door/plug behind it — commands go out over the new
  university/.../device/{id}/command MQTT topic (see services/mqtt_service.py
  Phase 2 additions), and today, with no real node listening, that command
  is also mirrored directly onto the Device row so the software stack stays
  internally consistent even with zero physical hardware attached.

See HARDWARE_INTEGRATION.md (project root) for how a real ESP32 node is
expected to satisfy these interfaces once it exists.
"""
