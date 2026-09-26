import { useEffect, useState } from "react";
import { api } from "../../api/client";

// Feature #8 — Emergency Access / Override.
//
// Deliberately visually distinct from the plain Lock/Unlock button in
// RoomProfile's "Door" section (that stays the ordinary, no-audit-trail
// instant action): this panel is for a REASONED, TIME-BOUNDED, AUDITED
// override — creating one always goes through the real backend endpoint
// (app/services/emergency_override_service.py), never a local/mock state.
// Admin-only, same as the plain override and the anomaly panel.
export default function EmergencyOverridePanel({ doorId, currentlyLocked, onInvestigateEvent }) {
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [tick, setTick] = useState(0);

  // Stage C — "Override Details -> Related Access Events" (C1/C8): fetched
  // on demand, not eagerly, since most overrides are never investigated.
  const [relatedEvents, setRelatedEvents] = useState(null);
  const [relatedErr, setRelatedErr] = useState(null);
  const [showRelated, setShowRelated] = useState(false);

  const [action, setAction] = useState(currentlyLocked ? "unlock" : "lock");
  const [reason, setReason] = useState("");
  const [duration, setDuration] = useState(30);

  function load() {
    setLoading(true);
    api.getActiveEmergencyOverride(doorId)
      .then((r) => setActive(r))
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [doorId]);

  // Live countdown — re-renders every second while an override is active so
  // the expiration time reads as a real countdown, not a static timestamp.
  useEffect(() => {
    if (!active || active.effective_status !== "ACTIVE") return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [active]);

  const secondsRemaining = active?.seconds_remaining != null
    ? Math.max(0, active.seconds_remaining - tick)
    : null;

  async function handleCreate() {
    setErr(null);
    setBusy(true);
    try {
      const created = await api.createEmergencyOverride(doorId, {
        action, reason: reason.trim(), duration_minutes: Number(duration),
      });
      setActive(created);
      setShowForm(false);
      setConfirming(false);
      setReason("");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke() {
    setErr(null);
    setBusy(true);
    try {
      const updated = await api.revokeEmergencyOverride(active.override_id, "Cancelled by admin");
      setActive(updated);
      setRevoking(false);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleRelated() {
    if (showRelated) {
      setShowRelated(false);
      return;
    }
    setShowRelated(true);
    if (relatedEvents === null) {
      setRelatedErr(null);
      api.getRelatedEventsForOverride(active.override_id)
        .then((rows) => setRelatedEvents(rows))
        .catch((e) => setRelatedErr(e.message));
    }
  }

  function formatCountdown(seconds) {
    if (seconds == null) return "—";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  const isActive = active && active.effective_status === "ACTIVE";

  return (
    <section className="room-profile-section emergency-override-panel">
      <h3>
        <span className="emergency-override-badge" aria-hidden="true">⚠</span> Emergency Override
      </h3>

      {loading && <p className="muted">Checking override status&hellip;</p>}
      {err && <div className="form-error">{err}</div>}

      {!loading && isActive && (
        <div className="emergency-override-active">
          <div className="emergency-override-row">
            <span className="aa-status-pill expired">ACTIVE EMERGENCY {active.action.toUpperCase()}</span>
            <span className="emergency-override-countdown">Expires in {formatCountdown(secondsRemaining)}</span>
          </div>
          <dl className="aa-profile-grid" style={{ marginTop: "8px" }}>
            <div><dt>Created by</dt><dd>{active.created_by_name || `Admin #${active.created_by_id}`}</dd></div>
            <div><dt>Reason</dt><dd>{active.reason}</dd></div>
            <div><dt>Started</dt><dd>{new Date(active.created_at).toLocaleString()}</dd></div>
            <div><dt>Expires</dt><dd>{new Date(active.expires_at).toLocaleString()}</dd></div>
          </dl>

          <button type="button" className="link-button" style={{ marginTop: "8px" }} onClick={toggleRelated}>
            {showRelated ? "Hide related access events" : "View related access events"}
          </button>
          {showRelated && (
            <div style={{ marginTop: "6px" }}>
              {relatedErr && <div className="form-error">{relatedErr}</div>}
              {relatedEvents === null && !relatedErr && <p className="muted">Loading&hellip;</p>}
              {relatedEvents?.length === 0 && <p className="muted">No related record.</p>}
              {relatedEvents && relatedEvents.length > 0 && (
                <ul className="aa-access-window-list">
                  {relatedEvents.map((e) => (
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
            </div>
          )}

          {!revoking ? (
            <button type="button" className="aa-danger-button" disabled={busy} onClick={() => setRevoking(true)}>
              Revoke Override
            </button>
          ) : (
            <div className="emergency-override-confirm">
              <p className="aa-subtitle">
                Revoke this emergency override now? The door will revert to locked unless another
                override or normal authorization applies.
              </p>
              <div className="aa-confirm-actions">
                <button type="button" className="secondary" disabled={busy} onClick={() => setRevoking(false)}>Cancel</button>
                <button type="button" className="aa-danger-button" disabled={busy} onClick={handleRevoke}>
                  {busy ? "Revoking…" : "Confirm Revoke"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && !isActive && !showForm && (
        <>
          <p className="muted">No active emergency override for this door.</p>
          <button type="button" className="aa-danger-button" onClick={() => setShowForm(true)}>
            Create Emergency Override
          </button>
        </>
      )}

      {!loading && !isActive && showForm && !confirming && (
        <div className="emergency-override-form">
          <label>
            Action
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="unlock">Unlock</option>
              <option value="lock">Lock</option>
            </select>
          </label>
          <label>
            Reason / justification (required)
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Fire drill evacuation — unlocking main exit"
              rows={2}
            />
          </label>
          <label>
            Duration (minutes)
            <input
              type="number"
              min={1}
              max={240}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
            />
          </label>
          <div className="aa-confirm-actions">
            <button type="button" className="secondary" onClick={() => setShowForm(false)}>Cancel</button>
            <button
              type="button"
              className="aa-danger-button"
              disabled={!reason.trim() || !duration}
              onClick={() => setConfirming(true)}
            >
              Review &amp; Confirm
            </button>
          </div>
        </div>
      )}

      {!loading && !isActive && showForm && confirming && (
        <div className="emergency-override-confirm">
          <p className="aa-subtitle">
            This will immediately <strong>{action}</strong> this door for <strong>{duration} minute(s)</strong>,
            bypassing normal scheduled authorization. This action is fully audited. Confirm?
          </p>
          <blockquote className="emergency-override-reason-preview">"{reason.trim()}"</blockquote>
          <div className="aa-confirm-actions">
            <button type="button" className="secondary" disabled={busy} onClick={() => setConfirming(false)}>Back</button>
            <button type="button" className="aa-danger-button" disabled={busy} onClick={handleCreate}>
              {busy ? "Activating…" : "Confirm Emergency Override"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
