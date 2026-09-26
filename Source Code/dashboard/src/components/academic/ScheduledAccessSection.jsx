import { useEffect, useState } from "react";
import { api } from "../../api/client";
import ConfirmDialog from "./ConfirmDialog";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// All window timestamps from the backend are UTC naive datetimes (no
// trailing "Z") — see AccessWindow's docstring in models.py for why. Force
// them to be parsed as UTC here rather than letting the browser assume
// local time.
function parseUtc(iso) {
  if (!iso) return null;
  return new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
}

function nowUtcParts() {
  const now = new Date();
  return { weekday: (now.getUTCDay() + 6) % 7, hm: now.getUTCHours() * 60 + now.getUTCMinutes(), date: now };
}

// Formats a Date as the local "YYYY-MM-DDTHH:mm" string <input type=
// "datetime-local"> expects, so editing a temporary window pre-populates
// with the correct local wall-clock equivalent of its stored UTC instant.
function toDatetimeLocalValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function timeToMinutes(t) {
  if (!t) return null;
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

// Client-side-only status label for display — purely informational. The
// backend (access_authorization_service.py) is the only authority on
// whether access is actually granted; this never gates any real decision.
function computeStatus(w) {
  const { weekday, hm, date } = nowUtcParts();
  if (w.recurring) {
    if (w.valid_until && parseUtc(w.valid_until) < date) return { label: "Expired", kind: "expired" };
    if (w.valid_from && parseUtc(w.valid_from) > date) return { label: "Upcoming", kind: "upcoming" };
    const start = timeToMinutes(w.start_time?.slice(0, 5));
    const end = timeToMinutes(w.end_time?.slice(0, 5));
    if (weekday === w.day_of_week && hm >= start && hm < end) return { label: "Active now", kind: "active" };
    return { label: "Recurring", kind: "recurring" };
  }
  const start = parseUtc(w.start_at);
  const end = parseUtc(w.end_at);
  if (date < start) return { label: "Upcoming", kind: "upcoming" };
  if (date > end) return { label: "Expired", kind: "expired" };
  return { label: "Active now", kind: "active" };
}

export default function ScheduledAccessSection({ staff }) {
  const [windows, setWindows] = useState([]);
  const [doors, setDoors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editingWindow, setEditingWindow] = useState(null); // the AccessWindow being edited, or null when adding new
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const emptyForm = {
    door_id: "", recurring: "true", day_of_week: "0", start_time: "09:00", end_time: "10:00",
    start_at: "", end_at: "", reason: "",
  };
  const [form, setForm] = useState(emptyForm);
  const [formErr, setFormErr] = useState(null);
  const [notice, setNotice] = useState(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [windowList, doorList] = await Promise.all([
        api.listAccessWindows({ userId: staff.user_id }),
        api.listDoors(),
      ]);
      setWindows(windowList);
      setDoors(doorList);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staff.user_id]);

  function flash(text) {
    setNotice(text);
    window.clearTimeout(flash._t);
    flash._t = window.setTimeout(() => setNotice(null), 4000);
  }

  function handleEditClick(w) {
    setEditingWindow(w);
    setFormErr(null);
    if (w.recurring) {
      setForm({
        door_id: String(w.door_id), recurring: "true", day_of_week: String(w.day_of_week),
        start_time: w.start_time?.slice(0, 5) || "09:00", end_time: w.end_time?.slice(0, 5) || "10:00",
        start_at: "", end_at: "", reason: w.reason || "",
      });
    } else {
      setForm({
        door_id: String(w.door_id), recurring: "false", day_of_week: "0", start_time: "09:00", end_time: "10:00",
        start_at: toDatetimeLocalValue(parseUtc(w.start_at)), end_at: toDatetimeLocalValue(parseUtc(w.end_at)),
        reason: w.reason || "",
      });
    }
    setShowAdd(true);
  }

  function handleCancelForm() {
    setShowAdd(false);
    setEditingWindow(null);
    setForm(emptyForm);
    setFormErr(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormErr(null);
    const isEditing = Boolean(editingWindow);

    if (!isEditing && !form.door_id) {
      setFormErr("Pick a room/door first.");
      return;
    }

    const recurring = form.recurring === "true";
    const timeFields = recurring
      ? { day_of_week: Number(form.day_of_week), start_time: `${form.start_time}:00`, end_time: `${form.end_time}:00` }
      : (() => {
          if (!form.start_at || !form.end_at) return null;
          // datetime-local inputs are interpreted as local wall-clock time
          // by `new Date(...)`, then .toISOString() converts that to true
          // UTC — the server re-validates the range regardless (never
          // trusts this, per Feature #5's security requirements).
          return {
            start_at: new Date(form.start_at).toISOString().slice(0, 19),
            end_at: new Date(form.end_at).toISOString().slice(0, 19),
          };
        })();

    if (!recurring && !timeFields) {
      setFormErr("Pick both a start and end date/time for temporary access.");
      return;
    }

    try {
      if (isEditing) {
        // AccessWindowUpdate only accepts the time/reason fields — a
        // window's door, staff member, and recurring/temporary shape are
        // fixed at creation (see app/schemas.py::AccessWindowUpdate); to
        // change those, delete and recreate.
        await api.updateAccessWindow(editingWindow.access_window_id, { ...timeFields, reason: form.reason.trim() || null });
        flash("Access window updated.");
      } else {
        await api.createAccessWindow({
          door_id: Number(form.door_id), user_id: staff.user_id, recurring,
          reason: form.reason.trim() || undefined, ...timeFields,
        });
        flash("Access window added.");
      }
      handleCancelForm();
      await load();
    } catch (e) {
      setFormErr(e.message);
    }
  }

  async function handleDelete() {
    setDeleteBusy(true);
    try {
      await api.deleteAccessWindow(confirmDelete.access_window_id);
      setConfirmDelete(null);
      await load();
    } catch (e) {
      setErr(e.message);
      setConfirmDelete(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <section className="aa-profile-section">
      <h3>Scheduled &amp; Temporary Access</h3>
      {notice && <div className="form-success">{notice}</div>}
      {loading && <p className="muted">Loading&hellip;</p>}
      {err && <div className="form-error">{err}</div>}

      {!loading && !err && (
        <>
          {windows.length === 0 && !showAdd && (
            <p className="muted">No scheduled or temporary access windows — only permanent room assignments above apply.</p>
          )}
          {windows.length > 0 && (
            <ul className="aa-access-window-list">
              {windows.map((w) => {
                const status = computeStatus(w);
                return (
                  <li key={w.access_window_id} className="aa-access-window-row">
                    <div>
                      <strong>{w.door_name || w.door_code}</strong>
                      {w.recurring ? (
                        <span className="muted"> &middot; {DAY_LABELS[w.day_of_week]} {w.start_time?.slice(0, 5)}–{w.end_time?.slice(0, 5)} UTC, recurring</span>
                      ) : (
                        <span className="muted"> &middot; Temporary: {new Date(`${w.start_at}Z`).toLocaleString()} – {new Date(`${w.end_at}Z`).toLocaleString()}</span>
                      )}
                      {w.reason && <div className="muted" style={{ fontSize: "12px" }}>{w.reason}</div>}
                    </div>
                    <span className={`aa-status-pill ${status.kind === "active" ? "active" : status.kind === "expired" ? "expired" : "pending"}`}>
                      {status.label}
                    </span>
                    <button type="button" className="link-button" onClick={() => handleEditClick(w)}>Edit</button>
                    <button type="button" className="link-button" onClick={() => setConfirmDelete(w)}>Delete</button>
                  </li>
                );
              })}
            </ul>
          )}

          {!showAdd && (
            <button type="button" className="secondary" style={{ marginTop: "10px" }} onClick={() => setShowAdd(true)}>
              + Add Access Window
            </button>
          )}

          {showAdd && (
            <form className="aa-inline-form" style={{ marginTop: "10px", flexDirection: "column", alignItems: "stretch" }} onSubmit={handleSubmit}>
              <strong style={{ fontSize: "13px" }}>{editingWindow ? "Edit access window" : "New access window"}</strong>

              <select value={form.door_id} onChange={(e) => setForm({ ...form, door_id: e.target.value })} disabled={Boolean(editingWindow)}>
                <option value="">Select room/door&hellip;</option>
                {doors.map((d) => (
                  <option key={d.door_id} value={d.door_id}>{d.name} ({d.code})</option>
                ))}
              </select>

              <div style={{ display: "flex", gap: "8px" }}>
                <label>
                  <input type="radio" checked={form.recurring === "true"} disabled={Boolean(editingWindow)} onChange={() => setForm({ ...form, recurring: "true" })} /> Recurring (weekly)
                </label>
                <label>
                  <input type="radio" checked={form.recurring === "false"} disabled={Boolean(editingWindow)} onChange={() => setForm({ ...form, recurring: "false" })} /> Temporary (one-off)
                </label>
              </div>
              {editingWindow && (
                <p className="muted" style={{ fontSize: "11px", margin: 0 }}>
                  Room and access type can't be changed here — delete and re-add if those need to change.
                </p>
              )}

              {form.recurring === "true" ? (
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <select value={form.day_of_week} onChange={(e) => setForm({ ...form, day_of_week: e.target.value })}>
                    {DAY_LABELS.map((label, i) => (
                      <option key={i} value={i}>{label}</option>
                    ))}
                  </select>
                  <input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
                  <span>to</span>
                  <input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
                </div>
              ) : (
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <input type="datetime-local" value={form.start_at} onChange={(e) => setForm({ ...form, start_at: e.target.value })} />
                  <span>to</span>
                  <input type="datetime-local" value={form.end_at} onChange={(e) => setForm({ ...form, end_at: e.target.value })} />
                </div>
              )}

              <input placeholder="Reason (optional, e.g. External Lecturer — network maintenance)" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
              {formErr && <div className="form-error">{formErr}</div>}
              <div style={{ display: "flex", gap: "8px" }}>
                <button type="submit">{editingWindow ? "Save changes" : "Save"}</button>
                <button type="button" className="secondary" onClick={handleCancelForm}>Cancel</button>
              </div>
            </form>
          )}
        </>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete this access window?"
          message="This can't be undone. Any permanent room assignment is unaffected."
          busy={deleteBusy}
          onCancel={() => setConfirmDelete(null)}
          onConfirm={handleDelete}
        />
      )}
    </section>
  );
}
