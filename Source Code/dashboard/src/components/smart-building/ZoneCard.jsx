import { formatWatts, OCCUPANCY_LABELS } from "./sbUtils";

// One tile in the zone grid / building map (Step 9). Deliberately not a
// literal floor-plan — a card grid, same as the rest of this dashboard's
// door-grid — but every state is communicated the same way a floor-plan
// would: color + a clear label, not just a color alone (the sensor-warning
// line below is text, not just a red dot, so it isn't color-only signaling).
export default function ZoneCard({ zone, onOpen }) {
  const state = zone.occupancy_state || "UNKNOWN";
  const devices = zone.devices || [];
  const sensors = zone.sensors || [];
  const onlineSensors = sensors.filter((s) => s.status === "online").length;
  const anyOffline = sensors.length > 0 && onlineSensors < sensors.length;
  const currentPower = devices.reduce((sum, d) => sum + (d.status ? d.current_power || 0 : 0), 0);
  const criticalOn = devices.filter((d) => d.criticality === "CRITICAL" && d.status).length;
  const nonCriticalOn = devices.filter((d) => d.criticality === "NON_CRITICAL" && d.status).length;

  return (
    <button type="button" className="sb-zone-card" data-state={state} onClick={() => onOpen(zone.zone_id)}>
      <div className="sb-zone-card-header">
        <div>
          <h4>{zone.name}</h4>
          <span className="sb-zone-type">{zone.zone_type}{zone.floor ? ` · Floor ${zone.floor}` : ""}</span>
        </div>
        <span className="dot sb-dot" data-state={state} />
      </div>

      <div className="sb-occupancy-state" data-state={state} style={{ fontSize: "13px", fontWeight: 700, marginTop: "8px" }}>
        {OCCUPANCY_LABELS[state] || state}
      </div>

      <div className="sb-zone-metrics">
        <span className="sb-zone-metric">
          Sensors: <strong>{onlineSensors}/{sensors.length}</strong>
        </span>
        <span className="sb-zone-metric">
          Power: <strong>{formatWatts(currentPower)}</strong>
        </span>
        <span className="sb-zone-metric">
          On: <strong>{criticalOn + nonCriticalOn}/{devices.length}</strong>
        </span>
      </div>

      {devices.length > 0 && (
        <div className="sb-zone-devices">
          {devices.map((d) => (
            <span
              key={d.device_id}
              className={`sb-device-chip${d.status ? " on" : ""}${d.criticality === "CRITICAL" ? " critical" : ""}`}
            >
              {d.name}: {d.status ? "ON" : "OFF"}
            </span>
          ))}
        </div>
      )}

      {anyOffline && (
        <div className="sb-zone-sensor-warning">
          {sensors.length - onlineSensors} sensor{sensors.length - onlineSensors > 1 ? "s" : ""} offline
        </div>
      )}
    </button>
  );
}
