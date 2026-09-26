import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";

// Stage E / E5 — production-style Access Events browser over the Stage C
// investigation API (GET /api/access-events). This endpoint and its client
// method already existed; there was simply no dedicated page for it before
// now (every other entry point — Command Center, Room History, anomaly
// panels — only ever links to ONE event's investigation, never lets you
// search/filter across all of them). Backend remains fully authoritative:
// scope filtering (self-only for non-admins, authorized-scope-only for a
// restricted admin) already happens server-side in investigation_service.py
// — this page never re-filters or widens what the backend returns.
const RESULT_OPTIONS = ["", "granted", "denied"];
const PAGE_SIZE = 25;

const STATUS_LABEL = {
  open: "Open",
  under_review: "Under review",
  resolved: "Resolved",
};

export default function AccessEventsPage({ onInvestigateEvent }) {
  const [filters, setFilters] = useState({ result: "", method: "", door_id: "", since: "", until: "" });
  const [rows, setRows] = useState(null); // null = loading
  const [err, setErr] = useState(null);
  const [offset, setOffset] = useState(0);

  const load = useCallback(async (currentOffset) => {
    setErr(null);
    try {
      const params = { ...filters, limit: PAGE_SIZE, offset: currentOffset };
      const data = await api.listAccessEvents(params);
      setRows(data);
    } catch (e) {
      setErr(e.message);
      setRows(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  useEffect(() => {
    setOffset(0);
    load(0);
  }, [load]);

  function applyFilter(key, value) {
    setFilters((f) => ({ ...f, [key]: value }));
  }

  function goToPage(newOffset) {
    setOffset(newOffset);
    load(newOffset);
  }

  const isNetworkError = err && !/^\d{3}/.test(err);

  return (
    <div className="sb-section" style={{ marginTop: 0 }}>
      <h3>Access Events</h3>
      <p className="muted" style={{ marginTop: "-6px" }}>
        Every real, persisted access decision — search and filter across all doors, then open any event for full
        investigation detail (physical facts, authorization decision, evidence, timeline, related anomalies/audit).
      </p>

      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "12px 0" }}>
        <select value={filters.result} onChange={(e) => applyFilter("result", e.target.value)}>
          {RESULT_OPTIONS.map((r) => <option key={r} value={r}>{r ? r[0].toUpperCase() + r.slice(1) : "Any result"}</option>)}
        </select>
        <select value={filters.method} onChange={(e) => applyFilter("method", e.target.value)}>
          <option value="">Any method</option>
          <option value="card">Card</option>
          <option value="admin_override">Admin override</option>
          <option value="schedule">Schedule</option>
        </select>
        <input
          type="number" placeholder="Door ID" style={{ width: "100px" }}
          value={filters.door_id} onChange={(e) => applyFilter("door_id", e.target.value)}
        />
        <input
          type="datetime-local" value={filters.since} onChange={(e) => applyFilter("since", e.target.value)}
          title="Since"
        />
        <input
          type="datetime-local" value={filters.until} onChange={(e) => applyFilter("until", e.target.value)}
          title="Until"
        />
      </div>

      {rows === null && !err && <p className="muted">Loading access events&hellip;</p>}

      {err && (
        <div className="form-error">
          {isNetworkError
            ? "Can't reach the backend right now — check that the API is running."
            : `Couldn't load access events: ${err}`}
        </div>
      )}

      {rows !== null && rows.length === 0 && !err && (
        <p className="sb-empty-state">
          No access events match these filters{offset > 0 ? " on this page" : ""}.
        </p>
      )}

      {rows !== null && rows.length > 0 && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Door</th>
                  <th>Building</th>
                  <th>User</th>
                  <th>Method</th>
                  <th>Result</th>
                  <th>Evidence</th>
                  <th>Investigation</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.event_id}>
                    <td>{new Date(`${e.event_time}Z`).toLocaleString()}</td>
                    <td>{e.door_name || `Door #${e.door_id}`} {e.door_code ? `(${e.door_code})` : ""}</td>
                    <td>{e.building || <span className="muted">—</span>}</td>
                    <td>{e.user_name || <span className="muted">Unresolved credential</span>}</td>
                    <td>{e.method}</td>
                    <td className={e.result === "granted" ? "ok" : "bad"}>{e.result}</td>
                    <td>{e.has_evidence ? "Recorded" : <span className="muted">Not recorded</span>}</td>
                    <td>
                      {e.investigation_status
                        ? <span className="aa-status-pill pending">{STATUS_LABEL[e.investigation_status] || e.investigation_status}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td>
                      <button type="button" className="link-button" onClick={() => onInvestigateEvent(e.event_id)}>
                        Investigate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: "flex", gap: "8px", marginTop: "10px", alignItems: "center" }}>
            <button type="button" className="secondary" disabled={offset === 0} onClick={() => goToPage(Math.max(0, offset - PAGE_SIZE))}>
              &larr; Previous
            </button>
            <span className="muted" style={{ fontSize: "13px" }}>Showing {offset + 1}&ndash;{offset + rows.length}</span>
            <button type="button" className="secondary" disabled={rows.length < PAGE_SIZE} onClick={() => goToPage(offset + PAGE_SIZE)}>
              Next &rarr;
            </button>
          </div>
        </>
      )}
    </div>
  );
}
