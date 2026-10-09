import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { SourceBadge } from "./Badges";
import { fmtDateTime } from "./util";

export default function DeviceFaultsAdmin() {
  const [rows, setRows] = useState(null);
  const [maint, setMaint] = useState([]);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState(null);

  const [tick, setTick] = useState(0);
  const load = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    Promise.all([api.deviceFaults(filter), api.deviceMaintenance()])
      .then(([r, m]) => { if (live) { setRows(r); setMaint(m); setErr(null); } })
      .catch((e) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, [filter, tick]);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, []);

  async function act(id, action, body) {
    try { await api.deviceFaultAction(id, action, body); load(); } catch (e) { setErr(e.message); }
  }

  return (
    <div>
      {err && <div className="form-error">{err}</div>}
      {maint.length > 0 && (
        <section className="ph-card" aria-labelledby="mr-h">
          <h3 id="mr-h">Maintenance recommended</h3>
          <ul className="ph-small">
            {maint.map((m) => <li key={m.device_id}>{m.device}: {m.fault_count} faults in {m.window_days} days, currently {m.current_abnormal.join(", ")}. <em>{m.basis}</em></li>)}
          </ul>
        </section>
      )}
      <label className="ph-small">Status{" "}
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option><option value="OPEN">Open</option>
          <option value="ACKNOWLEDGED">Acknowledged</option><option value="RESOLVED">Resolved</option>
        </select>
      </label>
      {rows && rows.length === 0 && <p className="muted">No device faults recorded. Devices without a reporting sensor are not monitored.</p>}
      {rows && rows.length > 0 && (
        <div className="ph-table-wrap">
          <table>
            <thead><tr><th>Severity</th><th>Room</th><th>Device</th><th>Expected</th><th>Observed</th><th>Detected</th><th>Status</th><th>Source</th><th>Actions</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.fault_id}>
                  <td><span className="ph-pill" data-sev={r.severity}>{r.severity}</span></td>
                  <td>{r.building ? `${r.building} · ` : ""}{r.room}</td>
                  <td>{r.device}<div className="ph-small muted">{r.kind}</div></td>
                  <td>{r.expected_value}</td>
                  <td>{r.observed_value}</td>
                  <td>{fmtDateTime(r.detected_at)}</td>
                  <td>{r.status}{r.reported_issue ? " · reported" : ""}</td>
                  <td><SourceBadge source={r.source} /></td>
                  <td className="ph-actions">
                    {r.status === "OPEN" && <button type="button" className="secondary" onClick={() => act(r.fault_id, "acknowledge")}>Acknowledge</button>}
                    {r.status !== "RESOLVED" && <button type="button" className="secondary" onClick={() => act(r.fault_id, "resolve", { note: "Resolved by admin" })}>Resolve</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
