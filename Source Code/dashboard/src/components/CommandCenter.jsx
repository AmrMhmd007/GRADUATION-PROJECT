import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

const POLL_MS = 5000;

const SEVERITY_CLASS = { ANOMALOUS: "pending", ELEVATED_RISK_INDICATOR: "expired" };
const INVESTIGATION_LABEL = { open: "Open", under_review: "Under review", resolved: "Resolved" };

function timeAgo(iso) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

// Phase 6 — Command Center: the single operational view expressing the
// real cyber-physical chain this whole system is built on —
//   People/Credential -> Authorization -> Door/Physical Node -> Access
//   Event -> Evidence -> Anomaly / Emergency State
// Every number and row here comes straight from real backend endpoints —
// GET /api/command-center/summary (doors, access_events, emergency_overrides,
// anomaly_detection_service, alerts), plus GET /api/buildings, /api/zones,
// /api/automation/rules, /api/automation/logs and /api/hardware-health for
// the System Overview / Automation / Device Health sections below (Stage
// E-hardening: same already-existing endpoints Smart Building uses — no
// second dashboard architecture, no invented metric). A value the backend
// doesn't have is shown as an explicit "Unavailable", never guessed.
// Stage C — an anomaly indicator's evidence carries either a single
// `event_id` (most rules) or an `event_ids` list (the two burst rules); this
// picks whichever one real id is available to investigate, or null if the
// evidence genuinely doesn't reference a specific event (never guessed).
function investigableEventId(indicator) {
  const ev = indicator.evidence || {};
  if (ev.event_id != null) return ev.event_id;
  if (Array.isArray(ev.event_ids) && ev.event_ids.length > 0) return ev.event_ids[ev.event_ids.length - 1];
  return null;
}

// Same "needs attention" rule AutomationLogFeed uses (Stage D) — a command
// status other than SENT/CONFIRMED is a real reported failure, never a guess.
function logNeedsAttention(log) {
  if (log.decision === "SHUTDOWN_SKIPPED_UNCERTAIN") return true;
  try {
    const blocked = log.blocked_actions ? JSON.parse(log.blocked_actions) : [];
    if (blocked.length > 0) return true;
  } catch { /* ignore */ }
  try {
    const devices = log.devices_changed ? JSON.parse(log.devices_changed) : [];
    if (devices.some((d) => d.command_status && d.command_status !== "COMMAND_SENT" && d.command_status !== "STATE_CONFIRMED")) return true;
  } catch { /* ignore */ }
  return false;
}

export default function CommandCenter({ onOpenDoor, onInvestigateEvent }) {
  const [summary, setSummary] = useState(null);
  const [ops, setOps] = useState(null); // { buildings, zones, rules, logs, health } — Automation/Device Health/System Overview data
  const [opsErr, setOpsErr] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getCommandCenterSummary();
      setSummary(data);
      setErr(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshOps = useCallback(async () => {
    try {
      const [buildings, zones, rules, logs, health] = await Promise.all([
        api.listBuildings(),
        api.listZones(),
        api.listAutomationRules(),
        api.listAutomationLogs(undefined, 50),
        api.listHardwareHealth(),
      ]);
      setOps({ buildings, zones, rules, logs, health });
      setOpsErr(null);
    } catch (e) {
      setOpsErr(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshOps();
    const id = setInterval(() => { refresh(); refreshOps(); }, POLL_MS);
    return () => clearInterval(id);
  }, [refresh, refreshOps]);

  if (loading) return <p className="muted">Loading command center&hellip;</p>;
  if (err) return <div className="form-error">{err}</div>;
  if (!summary) return null;

  const { door_status: ds, recent_events, active_overrides, anomaly_indicators, alerts, scope } = summary;
  const alertItems = alerts.items || [];
  const underInvestigation = recent_events.filter((e) => e.investigation_status && e.investigation_status !== "resolved").length;
  const hasCriticalSignal = active_overrides.length > 0 || anomaly_indicators.length > 0 || alertItems.length > 0;

  const deviceCount = ops ? ops.zones.reduce((sum, z) => sum + (z.devices || []).length, 0) : null;
  const failedExecutions = ops ? ops.logs.filter(logNeedsAttention) : [];
  const healthBuckets = ops
    ? { ONLINE: 0, OFFLINE: 0, DEGRADED: 0, UNKNOWN: 0, ...Object.fromEntries(
        ["ONLINE", "OFFLINE", "DEGRADED", "UNKNOWN"].map((s) => [s, ops.health.filter((h) => h.status === s).length]),
      ) }
    : null;

  // Header metric -> real, already-rendered section below on this same page
  // (there is no separate Doors/Overrides/Alerts route to navigate to, so
  // this scrolls to the real data rather than link to a page that doesn't
  // exist). Only wired for metrics that have an actual section id to jump
  // to; Locked/Unlocked/door totals have no such section here and are left
  // as plain numbers rather than a dead click target.
  function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="cc-root">
      {scope?.restricted && (
        <p className="hint" style={{ marginBottom: "12px" }}>
          You're viewing a scope-restricted Command Center — only data within your authorized college/department/operational
          scope is shown. Sections your scope can't be safely matched to (doors, alerts) are marked unavailable below.
        </p>
      )}

      {/* System status header — reuses the same navy status-header language
          as Smart Building's header (sb-header) rather than inventing a
          second "premium" visual style for the same kind of information. */}
      <div className={`sb-header cc-header ${hasCriticalSignal ? "cc-header-alert" : ""}`}>
        <div className="sb-header-state">
          <span className="sb-dot" style={{ background: hasCriticalSignal ? "#B45309" : "var(--green-dark)" }} aria-hidden="true" />
          <div>
            <h2>{hasCriticalSignal ? "Attention Required" : "Nominal"}</h2>
            <div className="sb-header-sub">
              {ds.available
                ? <>{ds.total} door{ds.total === 1 ? "" : "s"} monitored &middot; {ds.online} online &middot; </>
                : null}
              last updated {timeAgo(summary.evaluated_at)}
            </div>
            {!ds.available && (
              <div className="sb-header-sub" style={{ marginTop: "2px" }}>{ds.reason}</div>
            )}
          </div>
        </div>
        <div className="sb-header-metrics">
          {ds.available ? (
            <>
              <div className="sb-header-metric"><span className="value">{ds.locked}</span><span className="label">Locked</span></div>
              <div className="sb-header-metric"><span className="value">{ds.unlocked}</span><span className="label">Unlocked</span></div>
            </>
          ) : (
            <div className="sb-header-metric"><span className="value">&mdash;</span><span className="label">Doors N/A</span></div>
          )}
          <button
            type="button"
            className="sb-header-metric cc-metric-clickable"
            onClick={() => scrollToSection("cc-section-overrides")}
            disabled={active_overrides.length === 0}
          >
            <span className="value">{active_overrides.length}</span><span className="label">Active Overrides</span>
          </button>
          <button
            type="button"
            className="sb-header-metric cc-metric-clickable"
            onClick={() => scrollToSection("cc-section-anomalies")}
          >
            <span className="value">{anomaly_indicators.length}</span><span className="label">Anomalies</span>
          </button>
          <button
            type="button"
            className="sb-header-metric cc-metric-clickable"
            onClick={() => scrollToSection("cc-section-alerts")}
            disabled={!alerts.available}
          >
            <span className="value">{alerts.available ? alertItems.length : "—"}</span><span className="label">Alerts</span>
          </button>
        </div>
      </div>

      {/* ================= SYSTEM OVERVIEW ================= */}
      <h3 className="cc-group-title">System Overview</h3>
      <div className="cc-metric-row">
        <div className="cc-metric-tile"><span className="value">{ops ? ops.buildings.length : "—"}</span><span className="label">Buildings</span></div>
        <div className="cc-metric-tile"><span className="value">{ds.available ? ds.rooms : "—"}</span><span className="label">Rooms</span></div>
        <div className="cc-metric-tile"><span className="value">{ds.available ? ds.total : "—"}</span><span className="label">Doors</span></div>
        <div className="cc-metric-tile"><span className="value">{deviceCount != null ? deviceCount : "—"}</span><span className="label">Devices</span></div>
      </div>
      {opsErr && <div className="form-error" style={{ marginTop: "8px" }}>Couldn't load System Overview / Automation / Device Health data: {opsErr}</div>}

      {/* ================= SECURITY ================= */}
      <h3 className="cc-group-title">Security</h3>
      <div className="cc-grid">
        {active_overrides.length > 0 && (
          <section id="cc-section-overrides" className="sb-section cc-section-emergency">
            <h4>Active Emergency Overrides</h4>
            <ul className="cc-list">
              {active_overrides.map((o) => (
                <li key={o.override_id} className="cc-list-row">
                  <div>
                    <button type="button" className="link-button" style={{ padding: 0 }} onClick={() => onOpenDoor?.(o.door_id)}>
                      {o.door_name || `Door #${o.door_id}`}
                    </button>
                    <div className="muted" style={{ fontSize: "12px" }}>
                      {o.action.toUpperCase()} by {o.created_by_name || `Admin #${o.created_by_id}`} &mdash; "{o.reason}"
                    </div>
                  </div>
                  <span className="aa-status-pill expired">
                    {o.seconds_remaining != null ? `${Math.floor(o.seconds_remaining / 60)}m left` : "Active"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section id="cc-section-anomalies" className="sb-section">
          <h4>Active Anomaly Indicators</h4>
          {anomaly_indicators.length === 0 ? (
            <p className="muted">No anomalous or elevated-risk access patterns in the last 7 days.</p>
          ) : (
            <ul className="cc-list">
              {anomaly_indicators.map((ind, i) => {
                const eventId = investigableEventId(ind);
                return (
                  <li key={`${ind.user_id}-${i}`} className="cc-list-row">
                    <div>
                      <span className={`aa-status-pill ${SEVERITY_CLASS[ind.severity] || "pending"}`} style={{ marginRight: "8px" }}>
                        {ind.severity.replace(/_/g, " ")}
                      </span>
                      {ind.user_name} &mdash; {ind.explanation}
                    </div>
                    <span style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                      <button type="button" className="link-button" style={{ padding: 0 }} onClick={() => onOpenDoor?.(ind.door_id)}>
                        {ind.door_label}
                      </button>
                      {/* Only shown when the evidence actually names a real event — never a
                          link to nowhere. */}
                      {eventId != null && onInvestigateEvent && (
                        <button type="button" className="link-button" style={{ padding: 0 }} onClick={() => onInvestigateEvent(eventId)}>
                          Investigate
                        </button>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="sb-section">
          <h4>
            Recent Access Events
            {underInvestigation > 0 && (
              <span className="aa-status-pill pending" style={{ marginLeft: "8px" }}>
                {underInvestigation} under investigation
              </span>
            )}
          </h4>
          {recent_events.length === 0 ? (
            <p className="muted">No access events recorded yet.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Time</th><th>Door</th><th>Who</th><th>Method</th><th>Result</th><th>Investigation</th><th></th></tr>
              </thead>
              <tbody>
                {recent_events.map((e) => (
                  <tr key={e.event_id}>
                    <td>{timeAgo(e.event_time)}</td>
                    <td>
                      <button type="button" className="link-button" style={{ padding: 0 }} onClick={() => onOpenDoor?.(e.door_id)}>
                        {e.door_name || `Door #${e.door_id}`}
                      </button>
                    </td>
                    <td>{e.user_name || <span className="muted">Unresolved credential</span>}</td>
                    <td>{e.method}</td>
                    <td className={e.result === "granted" ? "ok" : "bad"}>{e.result}</td>
                    <td>
                      {e.investigation_status
                        ? <span className="aa-status-pill pending">{INVESTIGATION_LABEL[e.investigation_status] || e.investigation_status}</span>
                        : <span className="muted">—</span>}
                    </td>
                    <td>
                      {onInvestigateEvent && (
                        <button type="button" className="link-button" style={{ padding: 0 }} onClick={() => onInvestigateEvent(e.event_id)}>
                          Investigate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section id="cc-section-alerts" className="sb-section">
          <h4>Alerts</h4>
          {!alerts.available ? (
            <p className="muted">{alerts.reason}</p>
          ) : alertItems.length === 0 ? (
            <p className="muted">No unresolved alerts.</p>
          ) : (
            <ul className="cc-list">
              {alertItems.map((a) => (
                <li key={a.alert_id} className="cc-list-row">
                  <div>
                    {a.severity === "CRITICAL" && <span className="aa-status-pill expired" style={{ marginRight: "8px" }}>CRITICAL</span>}
                    {a.door_name || (a.door_id ? `Door #${a.door_id}` : "System")} &mdash; {a.type.replace(/_/g, " ")}
                  </div>
                  <span className="muted" style={{ fontSize: "12px" }}>{timeAgo(a.alert_time)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* ================= AUTOMATION ================= */}
      <h3 className="cc-group-title">Automation</h3>
      {!ops ? (
        <p className="muted">{opsErr ? "Automation data unavailable." : "Loading automation data…"}</p>
      ) : (
        <div className="cc-grid">
          <section className="sb-section">
            <h4>Rules</h4>
            <div className="cc-metric-row" style={{ marginBottom: "8px" }}>
              <div className="cc-metric-tile"><span className="value">{ops.rules.filter((r) => r.enabled).length}</span><span className="label">Active rules</span></div>
              <div className="cc-metric-tile"><span className="value">{ops.rules.filter((r) => !r.enabled).length}</span><span className="label">Disabled rules</span></div>
            </div>
            {ops.rules.length === 0 && (
              <p className="muted">No rules configured — the engine falls back to its built-in default. See Smart Building &rarr; Automation Rules.</p>
            )}
          </section>

          <section className="sb-section">
            <h4>Recent Executions &amp; Failed Actions</h4>
            <div className="cc-metric-row" style={{ marginBottom: "8px" }}>
              <div className="cc-metric-tile"><span className="value">{ops.logs.length}</span><span className="label">Recent executions</span></div>
              <div className="cc-metric-tile"><span className="value">{failedExecutions.length}</span><span className="label">Failed / blocked</span></div>
              <div className="cc-metric-tile">
                <span className="value" title="No async pending-command state is persisted yet — every command resolves synchronously to sent/failed (see hardware/interfaces.py).">
                  Unavailable
                </span>
                <span className="label">Pending commands</span>
              </div>
            </div>
            {failedExecutions.length === 0 ? (
              <p className="muted">No failed or blocked automation actions in the recent log window.</p>
            ) : (
              <ul className="cc-list">
                {failedExecutions.slice(0, 5).map((log) => (
                  <li key={log.log_id} className="cc-list-row">
                    <div>
                      <span className="aa-status-pill expired" style={{ marginRight: "8px" }}>Needs attention</span>
                      {log.zone_name || "Building-wide"} &mdash; {log.decision.replace(/_/g, " ")}
                    </div>
                    <span className="muted" style={{ fontSize: "12px" }}>{timeAgo(log.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="muted" style={{ fontSize: "12px", marginTop: "6px" }}>
              Full detail (device/door/related access events): Smart Building &rarr; Automation Decision Log.
            </p>
          </section>
        </div>
      )}

      {/* ================= DEVICE HEALTH ================= */}
      <h3 className="cc-group-title">Device Health</h3>
      {!ops ? (
        <p className="muted">{opsErr ? "Device health data unavailable." : "Loading device health data…"}</p>
      ) : ops.health.length === 0 ? (
        <p className="sb-empty-state">
          No hardware node has ever reported a heartbeat yet — this section populates once real ESP32/gateway
          hardware sends telemetry.
        </p>
      ) : (
        <div className="cc-metric-row">
          <div className="cc-metric-tile ok"><span className="value">{healthBuckets.ONLINE}</span><span className="label">Online</span></div>
          <div className="cc-metric-tile bad"><span className="value">{healthBuckets.OFFLINE}</span><span className="label">Offline / stale</span></div>
          <div className="cc-metric-tile pending"><span className="value">{healthBuckets.DEGRADED}</span><span className="label">Degraded</span></div>
          <div className="cc-metric-tile"><span className="value">{healthBuckets.UNKNOWN}</span><span className="label">Unknown</span></div>
        </div>
      )}
    </div>
  );
}
