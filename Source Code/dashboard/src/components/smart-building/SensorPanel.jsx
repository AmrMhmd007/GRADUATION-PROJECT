import { formatElapsedSince } from "./sbUtils";

// Sensor Monitoring (Step 11) — the automation engine's fail-safe behavior
// (never treat a stale/offline sensor as "confirms empty") depends entirely
// on sensor health, so this table exists to make that health visible on its
// own, separate from any one zone's card.
export default function SensorPanel({ sensors, zonesById }) {
  if (!sensors || sensors.length === 0) {
    return <p className="sb-empty-state">No sensors configured yet. Add one from a zone's detail view.</p>;
  }

  return (
    // Same horizontal-overflow containment as Access Events (see .table-scroll
    // in App.css) — the table can stay full-width and readable, and only its
    // own container scrolls sideways on narrow viewports, not the page.
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Sensor</th>
            <th>Type</th>
            <th>Zone</th>
            <th>Status</th>
            <th>Last reading</th>
            <th>Last seen</th>
            <th>Occupancy</th>
          </tr>
        </thead>
        <tbody>
          {sensors.map((s) => {
            const zone = zonesById.get(s.zone_id);
            const stale = s.status === "offline" || !s.last_seen;
            return (
              <tr key={s.sensor_id} style={stale ? { background: "var(--red-tint)" } : undefined}>
                <td>#{s.sensor_id}</td>
                <td>{s.sensor_type}</td>
                <td>{zone ? zone.name : `Zone #${s.zone_id}`}</td>
                <td className={stale ? "bad" : "ok"}>{s.status === "online" ? "Online" : "Offline"}</td>
                <td>{s.last_reading || "—"}</td>
                <td>{s.last_seen ? `${formatElapsedSince(s.last_seen)} ago` : "Never"}</td>
                <td>
                  {s.occupancy_state === true ? "Occupied" : s.occupancy_state === false ? "Clear" : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
