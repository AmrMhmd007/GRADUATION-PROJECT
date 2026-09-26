import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import AutomationLogFeed from "./AutomationLogFeed";
import { formatElapsedSince, formatWatts, OCCUPANCY_LABELS, pickBestSchedule } from "./sbUtils";
import useEscapeKey from "../../hooks/useEscapeKey";

const POLL_MS = 5000;
const SENSOR_TYPES = ["PIR", "MMWAVE", "ESP32", "DOOR_EVENT", "RFID_EVENT", "OTHER"];
const DEVICE_TYPES = [
  "LIGHT", "AC", "NON_CRITICAL_SOCKET", "LAB_EQUIPMENT",
  "SERVER", "NETWORK_EQUIPMENT", "SECURITY_EQUIPMENT", "OTHER",
];

function deviceControlTarget(device) {
  // Figures out which existing, already-working control endpoint a device
  // maps to (see backend app/models.py's Device docstring) — the automation
  // engine and this modal both reuse the same control paths rather than
  // each inventing their own.
  if (device.door_ref_id && device.type === "AC") return { kind: "ac", doorId: device.door_ref_id };
  if (device.door_ref_id && device.type === "LIGHT") return { kind: "light", doorId: device.door_ref_id };
  if (device.plug_ref_id) return { kind: "plug", doorId: device.plug_door_id, plugId: device.plug_ref_id };
  return { kind: "freestanding" };
}

function DeviceRow({ device, canControl, onToggleOn, onToggleAuto, busy }) {
  const target = deviceControlTarget(device);
  const controllable = device.controllable && (target.kind !== "plug" || target.doorId != null);
  return (
    <div className="sb-detail-device-row">
      <div>
        <div className="name">{device.name}</div>
        <div className="meta">
          {device.type} · {formatWatts(device.current_power)}
          {device.rated_power != null && ` (rated ${formatWatts(device.rated_power)})`}
          {" · "}
          {device.automatic_control_enabled ? "AUTO" : "MANUAL OVERRIDE"}
        </div>
      </div>
      <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
        {canControl && (
          <>
            <button
              className={device.status ? "" : "secondary"}
              disabled={busy || !controllable}
              onClick={() => onToggleOn(device, !device.status)}
            >
              {device.status ? "On" : "Off"}
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => onToggleAuto(device, !device.automatic_control_enabled)}
              title={device.automatic_control_enabled ? "Switch to manual override (automation engine will leave it alone)" : "Return to automatic control"}
            >
              {device.automatic_control_enabled ? "Set manual" : "Set auto"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function ZoneDetailModal({ zoneId, onClose, canControl }) {
  useEscapeKey(onClose);
  const [zone, setZone] = useState(null);
  const [schedules, setSchedules] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const [showAddSensor, setShowAddSensor] = useState(false);
  const [newSensorType, setNewSensorType] = useState("PIR");
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [newDevice, setNewDevice] = useState({ name: "", type: "LIGHT", criticality: "NON_CRITICAL" });

  const load = useCallback(async () => {
    try {
      const [detail, sched] = await Promise.all([
        api.getZone(zoneId),
        api.listZoneSchedules(zoneId),
      ]);
      setZone(detail);
      setSchedules(sched);
      setErr(null);
    } catch (e) {
      setErr(e.message);
    }
  }, [zoneId]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  async function run(fn) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleOn(device, on) {
    const target = deviceControlTarget(device);
    await run(async () => {
      if (target.kind === "ac") await api.toggleAc(target.doorId, on);
      else if (target.kind === "light") await api.toggleLight(target.doorId, on);
      else if (target.kind === "plug") await api.togglePlug(target.doorId, target.plugId, on);
      else await api.setDeviceStatus(device.device_id, on);
    });
  }

  async function handleToggleAuto(device, enabled) {
    await run(() => api.updateDevice(device.device_id, { automatic_control_enabled: enabled }));
  }

  async function handleAddSensor(e) {
    e.preventDefault();
    await run(() => api.createSensor(zoneId, newSensorType));
    setShowAddSensor(false);
  }

  async function handleSimulateReading(sensor, occupied) {
    await run(() => api.reportSensorReading(sensor.sensor_id, occupied, occupied ? "simulated: motion" : "simulated: clear"));
  }

  async function handleAddDevice(e) {
    e.preventDefault();
    if (!newDevice.name.trim()) return;
    await run(() => api.createDevice(zoneId, newDevice));
    setNewDevice({ name: "", type: "LIGHT", criticality: "NON_CRITICAL" });
    setShowAddDevice(false);
  }

  if (!zone) {
    return (
      <div className="room-profile-overlay" onClick={onClose}>
        <div className="room-profile-card" onClick={(e) => e.stopPropagation()}>
          <p className="muted">{err || "Loading zone…"}</p>
        </div>
      </div>
    );
  }

  const state = zone.occupancy_state || "UNKNOWN";
  const criticalDevices = (zone.devices || []).filter((d) => d.criticality === "CRITICAL");
  const nonCriticalDevices = (zone.devices || []).filter((d) => d.criticality !== "CRITICAL");
  const bestSchedule = pickBestSchedule(schedules, zone.zone_id);

  return (
    <div className="room-profile-overlay" onClick={onClose}>
      <div className="room-profile-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: "680px" }}>
        <div className="room-profile-header">
          <div>
            <h2>{zone.name}</h2>
            <div className="muted">
              {zone.zone_type}{zone.building_name ? ` · ${zone.building_name}` : ""}{zone.floor ? ` · Floor ${zone.floor}` : ""}
              {zone.door_code ? ` · Door ${zone.door_code}` : ""}
            </div>
          </div>
          <button className="secondary" onClick={onClose}>Close</button>
        </div>

        <div className="door-status" style={{ margin: "12px 0 4px" }}>
          <span className="dot sb-dot" data-state={state} />
          <span className="sb-occupancy-state" data-state={state} style={{ fontWeight: 700 }}>
            {OCCUPANCY_LABELS[state] || state}
          </span>
          {state === "VERIFYING" && zone.verification_started_at && (
            <span className="muted">
              — verifying for {formatElapsedSince(zone.verification_started_at)}
              {bestSchedule ? ` of a ${bestSchedule.verification_minutes}min window` : ""}
            </span>
          )}
        </div>
        {err && <div className="form-error" style={{ marginTop: "10px" }}>{err}</div>}

        <section className="room-profile-section">
          <h3>Schedule</h3>
          {bestSchedule ? (
            <p style={{ margin: 0, fontSize: "13px" }}>
              Open {bestSchedule.open_time}–{bestSchedule.close_time}, verify for {bestSchedule.verification_minutes} min
              before acting ({bestSchedule.grace_minutes} min grace after closing).
              {bestSchedule.zone_id == null && <span className="muted"> (building-wide default)</span>}
            </p>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              No schedule configured — this zone will never be auto-shut-down (uncertainty is fail-safe by design).
            </p>
          )}
        </section>

        <section className="room-profile-section">
          <h3>
            Sensors ({zone.sensors?.length || 0})
            {canControl && (
              <button className="secondary" disabled={busy} onClick={() => setShowAddSensor((v) => !v)}>
                {showAddSensor ? "Cancel" : "+ Add sensor"}
              </button>
            )}
          </h3>
          {showAddSensor && (
            <form onSubmit={handleAddSensor} style={{ display: "flex", gap: "8px", marginBottom: "10px" }}>
              <select value={newSensorType} onChange={(e) => setNewSensorType(e.target.value)}>
                {SENSOR_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <button type="submit" disabled={busy}>Add</button>
            </form>
          )}
          {(zone.sensors || []).length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>No sensors in this zone yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {zone.sensors.map((s) => {
                const stale = s.status !== "online";
                return (
                  <div key={s.sensor_id} className="sb-detail-device-row">
                    <div>
                      <div className="name">{s.sensor_type} sensor #{s.sensor_id}</div>
                      <div className="meta">
                        {s.last_seen ? `seen ${formatElapsedSince(s.last_seen)} ago` : "never reported"}
                        {s.last_reading ? ` · "${s.last_reading}"` : ""}
                      </div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span className={stale ? "bad" : "ok"} style={{ fontSize: "12px", fontWeight: 600 }}>
                        {stale ? "Offline" : "Online"}
                      </span>
                      {canControl && (
                        <>
                          <button className="secondary" disabled={busy} onClick={() => handleSimulateReading(s, true)}
                                  title="Testing aid until real hardware reports over MQTT">
                            Simulate occupied
                          </button>
                          <button className="secondary" disabled={busy} onClick={() => handleSimulateReading(s, false)}>
                            Simulate empty
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {canControl && (
          <section className="room-profile-section">
            <h3>
              Devices
              <button className="secondary" disabled={busy} onClick={() => setShowAddDevice((v) => !v)}>
                {showAddDevice ? "Cancel" : "+ Add device"}
              </button>
            </h3>
            {showAddDevice && (
              <form onSubmit={handleAddDevice} style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <input
                  placeholder="Device name"
                  value={newDevice.name}
                  onChange={(e) => setNewDevice({ ...newDevice, name: e.target.value })}
                />
                <select value={newDevice.type} onChange={(e) => setNewDevice({ ...newDevice, type: e.target.value })}>
                  {DEVICE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <select value={newDevice.criticality} onChange={(e) => setNewDevice({ ...newDevice, criticality: e.target.value })}>
                  <option value="NON_CRITICAL">Non-critical</option>
                  <option value="CRITICAL">Critical</option>
                </select>
                <button type="submit" disabled={busy}>Add</button>
              </form>
            )}
          </section>
        )}

        <section className="room-profile-section">
          <h3>Critical loads</h3>
          {criticalDevices.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>No critical devices registered for this zone.</p>
          ) : (
            <div className="sb-detail-devices">
              {criticalDevices.map((d) => (
                <DeviceRow key={d.device_id} device={d} canControl={canControl} busy={busy}
                           onToggleOn={handleToggleOn} onToggleAuto={handleToggleAuto} />
              ))}
            </div>
          )}
        </section>

        <section className="room-profile-section">
          <h3>Non-critical loads</h3>
          {nonCriticalDevices.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>No non-critical devices registered for this zone.</p>
          ) : (
            <div className="sb-detail-devices">
              {nonCriticalDevices.map((d) => (
                <DeviceRow key={d.device_id} device={d} canControl={canControl} busy={busy}
                           onToggleOn={handleToggleOn} onToggleAuto={handleToggleAuto} />
              ))}
            </div>
          )}
        </section>

        <section className="room-profile-section">
          <h3>Recent automation decisions</h3>
          <AutomationLogFeed logs={zone.recent_automation} />
        </section>
      </div>
    </div>
  );
}
