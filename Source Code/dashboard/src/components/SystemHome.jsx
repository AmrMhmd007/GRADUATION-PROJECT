import { useEffect, useState } from "react";
import { api } from "../api/client";

// Level 1 of the navigation hierarchy — System Home / Command Hub. The first
// thing an admin sees after login: a real-data operational overview, plus
// the same domain choice as before (now "workspace cards"), plus a handful
// of quick actions to specific real destinations. Dashboard.jsx is still the
// only place that reads/writes the URL hash — `domains`, `onSelect`, and
// `onSelectTab` are the same navigation functions it already had; this
// component owns no navigation state of its own.
//
// Every number/timestamp/status here comes from a real backend endpoint —
// never invented, never hardcoded:
//   - GET /api/command-center/summary  -> door status, recent access events,
//     active overrides, anomaly indicators, alerts (same endpoint
//     CommandCenter.jsx already uses)
//   - GET /api/faculties                -> academic org totals (same
//     aggregation AcademicOverview.jsx already does over the same list)
//   - GET /api/automation/summary       -> zone occupancy (same endpoint
//     SmartBuildingDashboard.jsx's own header already uses)
//   - GET /api/hardware-health          -> device health buckets (same
//     endpoint + bucket logic CommandCenter.jsx's Device Health section uses)
// Fetched once when Home mounts (React unmounts this component when
// navigating away, per Dashboard.jsx's `activeTab === "home"` guard) rather
// than polled on an interval — Home is a landing/overview screen, not a
// live operations console like Command Center, so a fresh snapshot on every
// visit is enough and avoids adding a fifth interval timer to the app.
// doors/alerts/buildings are NOT re-fetched here — Dashboard.jsx already
// polls/loads those for the rest of the app, so they arrive as props.
function timeAgo(iso) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

const INVESTIGATION_LABEL = { open: "Open", under_review: "Under review", resolved: "Resolved" };

export default function SystemHome({
  domains,
  onSelect,
  onSelectTab,
  onInvestigateEvent,
  doorCount,
  unresolvedAlertCount,
  buildingCount,
}) {
  const [summary, setSummary] = useState(null); // command-center summary
  const [faculties, setFaculties] = useState(null);
  const [automation, setAutomation] = useState(null);
  const [health, setHealth] = useState(null);
  const [loadErr, setLoadErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [summaryData, facultyList, automationSummary, healthList] = await Promise.all([
          api.getCommandCenterSummary(),
          api.listFaculties(),
          api.getAutomationSummary(),
          api.listHardwareHealth(),
        ]);
        if (cancelled) return;
        setSummary(summaryData);
        setFaculties(facultyList);
        setAutomation(automationSummary);
        setHealth(healthList);
        setLoadErr(null);
      } catch (e) {
        if (!cancelled) setLoadErr(e.message);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const ds = summary?.door_status;
  const alertItems = summary?.alerts?.available ? summary.alerts.items : [];
  const underInvestigation = summary
    ? summary.recent_events.filter((e) => e.investigation_status && e.investigation_status !== "resolved").length
    : null;

  const collegeCount = faculties ? faculties.length : null;
  const departmentCount = faculties ? faculties.reduce((sum, c) => sum + (c.departments_count || 0), 0) : null;

  const healthBuckets = health
    ? { ONLINE: 0, OFFLINE: 0, DEGRADED: 0, UNKNOWN: 0, ...Object.fromEntries(
        ["ONLINE", "OFFLINE", "DEGRADED", "UNKNOWN"].map((s) => [s, health.filter((h) => h.status === s).length]),
      ) }
    : null;

  // System Overview — a compact strip of real, clickable rollups. Each one
  // routes to the workspace that actually owns that data; none of these are
  // decorative. Skipped entirely (not padded with placeholders) if its
  // source hasn't loaded yet or the number wouldn't be meaningful.
  const overviewMetrics = [
    { key: "doors", label: "Doors monitored", value: doorCount, onClick: () => onSelectTab("critical") },
    { key: "alerts", label: "Unresolved alerts", value: unresolvedAlertCount, onClick: () => onSelectTab("command") },
    {
      key: "investigations",
      label: "Open investigations",
      value: underInvestigation,
      onClick: () => onSelectTab("events"),
    },
    { key: "buildings", label: "Buildings", value: buildingCount, onClick: () => onSelectTab("smart") },
    { key: "colleges", label: "Colleges", value: collegeCount, onClick: () => onSelectTab("academic") },
  ];

  function workspaceMeta(key) {
    if (key === "command") {
      if (!summary) return null;
      const hasCriticalSignal = summary.active_overrides.length > 0 || summary.anomaly_indicators.length > 0 || alertItems.length > 0;
      return hasCriticalSignal ? "Attention required" : "Nominal";
    }
    if (key === "security") return `${doorCount} door${doorCount === 1 ? "" : "s"}${unresolvedAlertCount > 0 ? ` · ${unresolvedAlertCount} unresolved alert${unresolvedAlertCount === 1 ? "" : "s"}` : ""}`;
    if (key === "smart") return automation ? `${automation.zones_occupied}/${automation.zones_total} zones occupied` : null;
    if (key === "academic") return collegeCount != null ? `${collegeCount} college${collegeCount === 1 ? "" : "s"} · ${departmentCount} department${departmentCount === 1 ? "" : "s"}` : null;
    return null;
  }

  return (
    <div className="system-home">
      <div className="home-hero">
        <h2 className="home-hero-title">Smart Campus Command Hub</h2>
        <p className="home-hero-subtitle">
          A real-time operational overview of access control, smart building automation, and academic administration across campus.
        </p>
      </div>

      {loadErr && (
        <div className="form-error" style={{ marginBottom: "16px" }}>
          Some overview data couldn't be loaded: {loadErr}
        </div>
      )}

      {/* ---------------- System Overview ---------------- */}
      <h3 className="cc-group-title">System Overview</h3>
      <div className="cc-metric-row">
        {overviewMetrics.map((m) => (
          <button
            key={m.key}
            type="button"
            className="cc-metric-tile home-metric-clickable"
            onClick={m.onClick}
            disabled={m.value == null}
          >
            <span className="value">{m.value != null ? m.value : "—"}</span>
            <span className="label">{m.label}</span>
          </button>
        ))}
      </div>

      {/* ---------------- Workspaces ---------------- */}
      <h3 className="cc-group-title">Workspaces</h3>
      <div className="aa-card-grid">
        {domains.map((d) => (
          <button key={d.key} type="button" className="aa-scope-card aa-scope-card-block aa-scope-card-nav" onClick={() => onSelect(d)}>
            <div className="aa-scope-card-clickzone" style={{ width: "100%" }}>
              <div className="aa-scope-card-body">
                <h3>{d.label}</h3>
                <p className="aa-scope-card-desc">{d.description}</p>
                {workspaceMeta(d.key) && <p className="aa-scope-card-meta">{workspaceMeta(d.key)}</p>}
              </div>
              <div className="aa-scope-card-arrow" aria-hidden="true">→</div>
            </div>
          </button>
        ))}
      </div>

      <div className="home-split">
        {/* ---------------- Recent Activity ---------------- */}
        <section className="home-panel sb-section">
          <h3 className="cc-group-title" style={{ marginTop: 0 }}>Recent Activity</h3>
          {!summary ? (
            <p className="muted">{loadErr ? "Recent activity unavailable." : "Loading recent activity…"}</p>
          ) : summary.recent_events.length === 0 ? (
            <p className="muted">No access events recorded yet.</p>
          ) : (
            <ul className="cc-list">
              {summary.recent_events.slice(0, 6).map((e) => (
                <li key={e.event_id} className="cc-list-row">
                  <div>
                    <span className={e.result === "granted" ? "ok" : "bad"} style={{ fontWeight: 600 }}>
                      {e.door_name || `Door #${e.door_id}`}
                    </span>{" "}
                    <span className="muted">— {e.user_name || "Unresolved credential"} · {e.method} · {e.result}</span>
                    {e.investigation_status && (
                      <span className="aa-status-pill pending" style={{ marginLeft: "8px" }}>
                        {INVESTIGATION_LABEL[e.investigation_status] || e.investigation_status}
                      </span>
                    )}
                  </div>
                  <span style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                    <span className="muted" style={{ fontSize: "12px" }}>{timeAgo(e.event_time)}</span>
                    {onInvestigateEvent && (
                      <button type="button" className="link-button" style={{ padding: 0 }} onClick={() => onInvestigateEvent(e.event_id)}>
                        Investigate
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ---------------- System Status ---------------- */}
        <section className="home-panel sb-section">
          <h3 className="cc-group-title" style={{ marginTop: 0 }}>System Status</h3>
          <ul className="home-status-list">
            <li>
              <span className="home-status-label">Access control</span>
              <span className={ds?.available ? "aa-status-pill active" : "aa-status-pill"}>
                {ds ? (ds.available ? "Available" : ds.reason || "Unavailable") : "Loading…"}
              </span>
            </li>
            <li>
              <span className="home-status-label">Hardware health</span>
              {!health ? (
                <span className="aa-status-pill">{loadErr ? "Unknown" : "Loading…"}</span>
              ) : health.length === 0 ? (
                <span className="aa-status-pill">No data</span>
              ) : (
                <span className="aa-status-pill active">
                  {healthBuckets.ONLINE} online / {health.length} reporting
                </span>
              )}
            </li>
            <li>
              <span className="home-status-label">Automation engine</span>
              <span className={automation ? "aa-status-pill active" : "aa-status-pill"}>
                {automation ? `Active — ${automation.zones_total} zone${automation.zones_total === 1 ? "" : "s"} monitored` : "Loading…"}
              </span>
            </li>
          </ul>
          {health && health.length === 0 && (
            <p className="muted" style={{ fontSize: "12px", marginTop: "8px" }}>
              No hardware node has ever reported a heartbeat yet — this populates once real ESP32/gateway hardware sends telemetry.
            </p>
          )}
        </section>
      </div>

      {/* ---------------- Quick Actions ---------------- */}
      <h3 className="cc-group-title">Quick Actions</h3>
      <div className="home-quick-actions">
        <button type="button" className="secondary" onClick={() => onSelectTab("command")}>Open Command Center</button>
        <button type="button" className="secondary" onClick={() => onSelectTab("events")}>View Access Events</button>
        <button type="button" className="secondary" onClick={() => onSelectTab("smart")}>Open Smart Building</button>
        <button type="button" className="secondary" onClick={() => onSelectTab("academic")}>Manage Academic Administration</button>
      </div>
    </div>
  );
}
