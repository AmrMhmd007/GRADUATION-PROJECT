import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { HealthPill, SourceBadge } from "./Badges";
import { fmtTime } from "./util";

export default function OccupancyOverview() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [leads, setLeads] = useState([]);
  useEffect(() => {
    let live = true;
    api.energyWasteCandidates().then((l) => live && setLeads(l)).catch(() => {});
    const load = () => api.occupancyOverview().then((d) => live && (setData(d), setErr(null))).catch((e) => live && setErr(e.message));
    load();
    const id = setInterval(load, 30000);
    return () => { live = false; clearInterval(id); };
  }, []);
  if (err) return <div className="form-error">{err}</div>;
  if (!data) return <p className="muted">Loading occupancy…</p>;
  const c = data.campus;
  return (
    <div>
      <div className="ph-metrics">
        <div className="ph-metric"><span>People (counted rooms)</span><strong>{c.total_people}</strong></div>
        <div className="ph-metric"><span>Occupied rooms</span><strong>{c.occupied_rooms}</strong></div>
        <div className="ph-metric"><span>Rooms with live count</span><strong>{c.rooms_with_live_count} / {c.rooms_total}</strong></div>
        <div className="ph-metric"><span>Avg per counted room</span><strong>{c.average_per_counted_room ?? "—"}</strong></div>
      </div>
      {leads.length > 0 && (
        <section className="ph-card" aria-labelledby="ew-h">
          <h3 id="ew-h">Potential energy waste (leads only)</h3>
          <p className="ph-small muted">Fresh count of 0 with equipment apparently on. No action is taken from a single reading; automation still requires its verification window and rules.</p>
          <ul className="ph-small">{leads.map((l) => <li key={l.zone_id}><strong>{l.room}</strong>: {l.findings.join("; ")}</li>)}</ul>
        </section>
      )}
      <div className="ph-legend" aria-label="Sensor health">
        {Object.entries(data.sensor_health).map(([k, v]) => <span key={k}><HealthPill state={k} /> {v}</span>)}
      </div>
      {data.buildings.map((b) => (
        <section key={b.name} className="ph-card">
          <div className="ph-card-head"><h3>{b.name}</h3><span className="ph-small">{b.people} people · {b.counted_rooms} rooms counted</span></div>
          {b.floors.map((f) => (
            <div key={f.floor} className="ph-table-wrap">
              <table>
                <caption className="ph-small">Floor {f.floor}</caption>
                <thead><tr><th>Room</th><th>People</th><th>Capacity</th><th>Sensor</th><th>Updated</th><th>Source</th></tr></thead>
                <tbody>
                  {f.rooms.map((r) => (
                    <tr key={r.zone_id}>
                      <td>{r.room}</td>
                      <td>{r.occupancy.state === "UNAVAILABLE" ? <em title={r.occupancy.reason}>Unavailable</em> : r.occupancy.count}</td>
                      <td>{r.occupancy.capacity ?? "—"}</td>
                      <td><HealthPill state={r.sensor_health} /></td>
                      <td>{fmtTime(r.occupancy.last_updated)}</td>
                      <td>{r.occupancy.source ? <SourceBadge source={r.occupancy.source} /> : <SourceBadge />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
