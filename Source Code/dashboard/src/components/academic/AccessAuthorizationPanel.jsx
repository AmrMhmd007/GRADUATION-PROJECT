import { useEffect, useState } from "react";
import { api } from "../../api/client";

// Stage B — "Access Decision UX" / "Authorization Source" (admin-only,
// shown from RoomProfile for ANY door, critical or room). This deliberately
// distinguishes three separate, real things rather than blending them into
// one vague "access" concept:
//   1. WHO has permanent access — DoorAssignment rows (GET /api/doors/{id}/assignments)
//   2. WHO has scheduled/temporary access right now — AccessWindow rows
//      (GET /api/access-windows?door_id=), each already evaluated server-side
//      for active/expired/upcoming.
//   3. A live, on-demand authorization CHECK for a specific person — the
//      exact WHO+WHEN decision the physical door itself would apply, via
//      GET /api/doors/{id}/authorization?user_id=. Running this is not
//      cosmetic: the backend records a real AccessEvent (method=
//      "schedule_check") for it, so it becomes part of that door's real
//      history, not a throwaway UI action.
// Everything here is existing, already-tested backend surface — the only
// new endpoint is #1 (list_assignments_for_door), which mirrors the
// existing per-staff GET /api/users/{id}/doors from the other direction.
//
// Hardening pass (Stage B): `door` is now passed in so the panel can show
// the door's own physical state (locked/online) right next to an
// authorization decision — these are two different questions (see
// PHYSICAL_STATE below) and were previously easy to conflate since the
// authorization result alone doesn't say anything about the lock. `onChecked`
// is an optional callback (Dashboard wires it to refreshRoomLogs) so the
// real AccessEvent a check creates shows up in the History section below
// this panel without a manual reopen — the actual proof a check happened,
// not just a claim in this panel's own state.
export default function AccessAuthorizationPanel({ doorId, door, onChecked }) {
  const [assignments, setAssignments] = useState(null);
  const [windows, setWindows] = useState(null);
  const [users, setUsers] = useState([]);
  const [err, setErr] = useState(null);

  const [checkUserId, setCheckUserId] = useState("");
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);
  const [checkedJustNow, setCheckedJustNow] = useState(false);
  const [checkErr, setCheckErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setErr(null);
    Promise.all([
      api.listAssignmentsForDoor(doorId),
      api.listAccessWindows({ doorId }),
      api.listUsers(),
    ])
      .then(([a, w, u]) => {
        if (cancelled) return;
        setAssignments(a);
        setWindows(w);
        setUsers(u.filter((x) => x.role === "instructor" || x.role === "doctor"));
      })
      .catch((e) => { if (!cancelled) setErr(e.message); });
    return () => { cancelled = true; };
  }, [doorId]);

  function userLabel(userId) {
    const u = users.find((x) => x.user_id === userId);
    return u ? `${u.name} (${u.role === "doctor" ? "Doctor" : "TA"})` : `User #${userId}`;
  }

  // Changing who's selected invalidates the last result — showing a stale
  // decision for a person no longer selected would be misleading, so it's
  // cleared rather than left on screen next to a different name.
  function handleSelectUser(value) {
    setCheckUserId(value);
    setCheckResult(null);
    setCheckErr(null);
  }

  async function runCheck() {
    if (!checkUserId) {
      setCheckErr("Pick a person to check first.");
      return;
    }
    // Guards against a double-click/double-submit firing two real
    // authorization checks (and thus two AccessEvents) for one click —
    // `checking` already disables the button, this is the belt-and-braces
    // re-entrancy guard for the async gap before the state update commits.
    if (checking) return;
    setChecking(true);
    setCheckErr(null);
    setCheckedJustNow(false);
    try {
      const result = await api.checkDoorAuthorization(doorId, Number(checkUserId));
      setCheckResult(result);
      setCheckedJustNow(true);
      window.setTimeout(() => setCheckedJustNow(false), 4000);
      onChecked?.();
    } catch (e) {
      setCheckErr(e.message);
      setCheckResult(null);
    } finally {
      setChecking(false);
    }
  }

  function windowStatus(w) {
    // Mirrors the server's own is_window_active() logic just for a quick
    // glance here — the authoritative answer for any real decision is
    // always the live "Check Authorization" result below, never this.
    const now = new Date();
    if (w.recurring) {
      if (w.valid_until && new Date(`${w.valid_until}Z`) < now) return { label: "Expired", kind: "expired" };
      if (w.valid_from && new Date(`${w.valid_from}Z`) > now) return { label: "Upcoming", kind: "pending" };
      return { label: "Recurring", kind: "active" };
    }
    const start = new Date(`${w.start_at}Z`);
    const end = new Date(`${w.end_at}Z`);
    if (now < start) return { label: "Upcoming", kind: "pending" };
    if (now > end) return { label: "Expired", kind: "expired" };
    return { label: "Active now", kind: "active" };
  }

  const loading = assignments === null || windows === null;

  // Authorization SOURCE — which of the two real, independent grants (if
  // either) actually produced the decision. Derived only from fields the
  // backend evaluation itself returned (has_permanent_access / windows),
  // never guessed.
  function authorizationSource(result) {
    if (result.has_permanent_access) return "Permanent assignment (DoorAssignment)";
    const activeWindow = result.windows.find((w) => w.active);
    if (activeWindow) {
      return activeWindow.recurring
        ? `Scheduled recurring window${activeWindow.course_code ? ` — ${activeWindow.course_code}` : ""}`
        : `Temporary access window${activeWindow.course_code ? ` — ${activeWindow.course_code}` : ""}`;
    }
    return "None — no permanent assignment or active window";
  }

  return (
    <section className="room-profile-section">
      <h3>Access &amp; Authorization</h3>
      {err && <div className="form-error">{err}</div>}
      {loading && !err && <p className="muted">Loading&hellip;</p>}

      {!loading && !err && (
        <>
          <div style={{ marginBottom: "14px" }}>
            <strong style={{ fontSize: "13px" }}>Permanent access (assigned)</strong>
            {assignments.length === 0 ? (
              <p className="muted" style={{ margin: "4px 0 0" }}>No one has permanent assignment to this door.</p>
            ) : (
              <ul className="aa-access-window-list">
                {assignments.map((a) => (
                  <li key={a.assignment_id} className="aa-access-window-row">
                    <div>{a.instructor_name || `User #${a.instructor_id}`}</div>
                    <span className="aa-status-pill active">Permanent</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div style={{ marginBottom: "14px" }}>
            <strong style={{ fontSize: "13px" }}>Scheduled &amp; temporary windows</strong>
            {windows.length === 0 ? (
              <p className="muted" style={{ margin: "4px 0 0" }}>No scheduled or temporary access windows for this door.</p>
            ) : (
              <ul className="aa-access-window-list">
                {windows.map((w) => {
                  const status = windowStatus(w);
                  return (
                    <li key={w.access_window_id} className="aa-access-window-row">
                      <div>
                        {userLabel(w.user_id)}
                        {w.recurring ? (
                          <span className="muted"> &middot; weekly, {w.start_time?.slice(0, 5)}–{w.end_time?.slice(0, 5)} UTC</span>
                        ) : (
                          <span className="muted"> &middot; {new Date(`${w.start_at}Z`).toLocaleString()} – {new Date(`${w.end_at}Z`).toLocaleString()}</span>
                        )}
                      </div>
                      <span className={`aa-status-pill ${status.kind}`}>{status.label}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div>
            <strong style={{ fontSize: "13px" }}>Check authorization now</strong>
            <p className="muted" style={{ margin: "4px 0 8px", fontSize: "12px" }}>
              This is a real WHO+WHEN authorization check, not a preview — it evaluates the same rule the physical
              door itself would apply, and the backend permanently records it as a new Access Event
              (method = <code>schedule_check</code>) in this door's history. It does not lock, unlock, or change the
              door in any way.
            </p>
            {door && (
              <p className="muted" style={{ margin: "0 0 8px", fontSize: "12px" }}>
                Current physical door state: <strong>{door.online ? (door.locked ? "Locked" : "Unlocked") : "Offline"}</strong> — unaffected by this check either way.
              </p>
            )}
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              <select value={checkUserId} onChange={(e) => handleSelectUser(e.target.value)}>
                <option value="">Select a Doctor/TA&hellip;</option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>{u.name} ({u.role === "doctor" ? "Doctor" : "TA"})</option>
                ))}
              </select>
              <button type="button" className="secondary" disabled={checking || checkedJustNow || !checkUserId} onClick={runCheck}>
                {checking ? "Checking…" : checkedJustNow ? "Checked ✓" : "Check Authorization"}
              </button>
            </div>
            {checkErr && <div className="form-error" style={{ marginTop: "8px" }}>{checkErr}</div>}
            {checkResult && (
              <dl className="room-profile-plug-row" style={{ marginTop: "10px", flexDirection: "column", alignItems: "flex-start", gap: "6px", display: "flex" }}>
                <div>
                  <span className={`aa-status-pill ${checkResult.authorized ? "active" : "expired"}`}>
                    {checkResult.authorized ? "GRANTED" : "DENIED"}
                  </span>
                  <span className="muted" style={{ fontSize: "11px", marginLeft: "8px" }}>
                    for {userLabel(checkResult.user_id)}
                  </span>
                </div>
                <div style={{ fontSize: "13px" }}>{checkResult.reason}</div>
                <div style={{ fontSize: "12px" }}>
                  <strong>Authorization source:</strong> {authorizationSource(checkResult)}
                </div>
                <div className="muted" style={{ fontSize: "11px" }}>
                  Evaluated at {new Date(`${checkResult.evaluated_at}Z`).toLocaleString()}
                </div>
                <div className="muted" style={{ fontSize: "11px" }}>
                  Recorded as a new Access Event on this door (method: schedule_check, result:{" "}
                  {checkResult.authorized ? "granted" : "denied"}) — see History below to confirm.
                </div>
              </dl>
            )}
          </div>
        </>
      )}
    </section>
  );
}
