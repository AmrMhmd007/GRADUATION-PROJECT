// Stage D / D6, D10 — surfaces the REAL HardwareHealth rows (Phase 5:
// services/hardware_health_service.py) that already existed on the backend
// but had no dashboard view at all. Every value here is exactly what the
// node last reported (or explicitly hasn't) — nothing is invented:
//   - UNKNOWN: no heartbeat has ever arrived for this node_id.
//   - OFFLINE: no heartbeat within the stale window (this IS this project's
//     "stale" state — HardwareHealth has no separate STALE value, see its
//     model docstring, so this label is used rather than inventing a fifth
//     status the backend doesn't produce).
//   - DEGRADED: heartbeat on time, but the node itself reported a problem.
//   - ONLINE: heartbeat on time, nothing wrong reported.
// This table is purely informational (never an occupancy input) — see
// models.HardwareHealth's own docstring.
const STATUS_STYLE = {
  ONLINE: { className: "ok", label: "ONLINE" },
  DEGRADED: { className: "pending", label: "DEGRADED" },
  OFFLINE: { className: "bad", label: "OFFLINE (stale/no heartbeat)" },
  UNKNOWN: { className: "muted", label: "UNKNOWN (never reported)" },
};

export default function HardwareHealthPanel({ nodes, zonesById }) {
  if (!nodes || nodes.length === 0) {
    return (
      <p className="sb-empty-state">
        No hardware nodes have ever reported a heartbeat yet — this section will populate once real
        ESP32/gateway hardware starts sending telemetry (see HARDWARE_INTEGRATION.md).
      </p>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Node</th>
          <th>Zone</th>
          <th>Status</th>
          <th>Last seen</th>
          <th>Firmware</th>
          <th>Signal</th>
          <th>Reported issue</th>
        </tr>
      </thead>
      <tbody>
        {nodes.map((n) => {
          const style = STATUS_STYLE[n.status] || STATUS_STYLE.UNKNOWN;
          const zone = n.zone_id != null ? zonesById.get(n.zone_id) : null;
          return (
            <tr key={n.health_id}>
              <td>{n.node_id}</td>
              <td>{zone ? zone.name : n.zone_name || <span className="muted">Unassigned</span>}</td>
              <td className={style.className}>{style.label}</td>
              <td>{n.last_seen ? new Date(`${n.last_seen}Z`).toLocaleString() : <span className="muted">Never</span>}</td>
              <td>{n.firmware_version || <span className="muted">—</span>}</td>
              <td>{n.rssi != null ? `${n.rssi} dBm` : <span className="muted">—</span>}</td>
              <td>{n.error_state || (n.sensor_healthy === false ? "Sensor unhealthy" : <span className="muted">None</span>)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
