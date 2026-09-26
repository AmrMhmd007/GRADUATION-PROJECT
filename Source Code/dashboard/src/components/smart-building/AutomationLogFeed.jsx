import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { DECISION_LABELS, timeOfDay } from "./sbUtils";

// Professional timeline/activity feed over GET /api/automation/logs — the
// audit trail the spec calls for (Step 18): every decision the engine made,
// what it saw, and why, not just a bare "device turned off."
//
// Stage D / D3, D8: a decision is flagged as needing attention when the
// command lifecycle itself reports a real failure (a device's command_status
// came back COMMAND_FAILED — never inferred from "device stayed on"), when
// the engine explicitly refused to act (SHUTDOWN_SKIPPED_UNCERTAIN), or when
// critical-load protection blocked something. For those rows, "View related
// context" fetches the real device/zone/door/access-event/alert chain
// (GET /api/automation/logs/{id}/related) — never a guessed correlation.
function hasFailedCommand(devices) {
  return devices.some((d) => d.command_status && d.command_status !== "COMMAND_SENT" && d.command_status !== "STATE_CONFIRMED");
}

function RelatedContext({ logId, onInvestigateEvent }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.getAutomationLogRelated(logId)
      .then((r) => { if (!cancelled) setData(r); })
      .catch((e) => { if (!cancelled) setErr(e.message); });
    return () => { cancelled = true; };
  }, [logId]);

  if (err) return <div className="form-error">{err}</div>;
  if (!data) return <p className="muted">Loading related context&hellip;</p>;

  return (
    <div className="sb-log-related">
      {!data.door_available && <p className="muted">{data.door_unavailable_reason}</p>}
      {data.door_available && (
        <>
          <p className="muted" style={{ margin: "4px 0" }}>
            Door: <strong>{data.door_name}</strong> (zone: {data.zone_name})
          </p>
          {data.related_access_events.length === 0 ? (
            <p className="muted">No related access event within ±30 minutes.</p>
          ) : (
            <ul className="aa-access-window-list">
              {data.related_access_events.map((e) => (
                <li key={e.event_id} className="aa-access-window-row">
                  <div>
                    {new Date(`${e.event_time}Z`).toLocaleTimeString()} &mdash; {e.result} ({e.method})
                    {e.user_name ? ` — ${e.user_name}` : ""}
                  </div>
                  {onInvestigateEvent && (
                    <button type="button" className="link-button" onClick={() => onInvestigateEvent(e.event_id)}>
                      Investigate
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {data.alerts.length > 0 && (
        <div style={{ marginTop: "6px" }}>
          <span className="muted">Related alerts:</span>
          <ul className="cc-list">
            {data.alerts.map((a) => (
              <li key={a.alert_id} className="cc-list-row">
                <div>
                  {a.severity === "CRITICAL" && <span className="aa-status-pill expired" style={{ marginRight: "8px" }}>CRITICAL</span>}
                  {a.type.replace(/_/g, " ")} {a.resolved ? "(resolved)" : "(unresolved)"}
                </div>
                <span className="muted" style={{ fontSize: "12px" }}>{new Date(`${a.alert_time}Z`).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.door_available && data.related_access_events.length === 0 && data.alerts.length === 0 && (
        <p className="muted">No related record.</p>
      )}
    </div>
  );
}

export default function AutomationLogFeed({ logs, onInvestigateEvent }) {
  const [expandedId, setExpandedId] = useState(null);

  if (!logs || logs.length === 0) {
    return <p className="sb-empty-state">No automation decisions yet — the engine only logs a zone once something actually happens (verification starting, being cancelled, or a confirmed shutdown).</p>;
  }

  return (
    <ul className="sb-log-feed">
      {logs.map((log) => {
        let devices = [];
        try {
          devices = log.devices_changed ? JSON.parse(log.devices_changed) : [];
        } catch {
          devices = [];
        }
        let blocked = [];
        try {
          blocked = log.blocked_actions ? JSON.parse(log.blocked_actions) : [];
        } catch {
          blocked = [];
        }
        const needsAttention = log.decision === "SHUTDOWN_SKIPPED_UNCERTAIN" || blocked.length > 0 || hasFailedCommand(devices);
        return (
          <li className="sb-log-item" key={log.log_id}>
            <div className="sb-log-top">
              <span className="sb-log-time">{timeOfDay(log.created_at)}</span>
              <span className="sb-log-zone">{log.zone_name || "Building-wide"}</span>
              <span className="sb-log-decision" data-decision={log.decision}>
                {DECISION_LABELS[log.decision] || log.decision}
              </span>
              {needsAttention && <span className="aa-status-pill expired">Needs attention</span>}
            </div>
            <div className="sb-log-reason">
              {log.occupancy_snapshot && <>Occupancy: <strong>{log.occupancy_snapshot}</strong> · </>}
              {log.schedule_state && <>Schedule: <strong>{log.schedule_state}</strong> · </>}
              {log.verification_result && log.verification_result !== "N/A" && (
                <>Verification: <strong>{log.verification_result}</strong> · </>
              )}
              {log.reason}
            </div>
            {devices.length > 0 && (
              <div className="sb-log-devices">
                Devices affected: {devices.map((d) => `${d.name} (${d.from}→${d.to}, ${d.command_status || "unknown"})`).join(", ")}
              </div>
            )}
            {blocked.length > 0 && (
              <div className="sb-log-devices bad">
                Blocked: {blocked.map((b) => `${b.name} (${b.reason})`).join(", ")}
              </div>
            )}
            {needsAttention && (
              <button type="button" className="link-button" onClick={() => setExpandedId(expandedId === log.log_id ? null : log.log_id)}>
                {expandedId === log.log_id ? "Hide related context" : "View related context"}
              </button>
            )}
            {expandedId === log.log_id && <RelatedContext logId={log.log_id} onInvestigateEvent={onInvestigateEvent} />}
          </li>
        );
      })}
    </ul>
  );
}
