import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import ConfirmDialog from "./ConfirmDialog";

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function fmtTime(t) {
  // Schedule.start_time/end_time come back as "HH:MM:SS" strings from the API.
  return typeof t === "string" ? t.slice(0, 5) : t;
}

// Course Assignments sub-view — who teaches/assists this course, on which
// section/semester, tied to an existing Schedule row for room+timing per
// the user's explicit instruction: reuse Schedule's room_name/room_code,
// never add a new door_id relationship on CourseAssignment. All business
// rules (same-department/same-college, schedule-belongs-to-this-course) are
// enforced server-side (app/routers/academic.py) — this UI just surfaces
// the real backend 409 text verbatim, never a generic "Something went wrong".
export default function CourseAssignmentsModal({ course, staffOptions, onClose, onChanged }) {
  const [assignments, setAssignments] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [doors, setDoors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ user_id: "", section: "", semester: "", academic_year: "", schedule_id: "" });
  const [addErr, setAddErr] = useState(null);
  const [addBusy, setAddBusy] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ section: "", semester: "", academic_year: "", schedule_id: "", status: "active" });
  const [editErr, setEditErr] = useState(null);
  const [editBusy, setEditBusy] = useState(false);

  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deleteErr, setDeleteErr] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  // Phase 12: Schedule <-> Course linking (Schedule.course_ref_id). Kept in
  // this same modal rather than a separate screen since there is no
  // standalone Schedule management UI elsewhere in the app — schedules have
  // always only ever been read here (see `load` below), never
  // created/edited from the frontend until now. This adds real API calls
  // to the pre-existing POST/PUT /api/schedules endpoints (Phase 11), it
  // does not fake anything client-side.
  const [showNewSchedule, setShowNewSchedule] = useState(false);
  const [newSchedule, setNewSchedule] = useState({ door_id: "", day_of_week: "0", start_time: "09:00", end_time: "10:00" });
  const [linkScheduleId, setLinkScheduleId] = useState("");
  const [scheduleLinkErr, setScheduleLinkErr] = useState(null);
  const [scheduleLinkOk, setScheduleLinkOk] = useState(null);
  const [scheduleLinkBusy, setScheduleLinkBusy] = useState(false);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [assignmentList, scheduleList, doorList] = await Promise.all([
        api.listCourseAssignments(course.course_id),
        api.listSchedules(),
        api.listDoors(),
      ]);
      setAssignments(assignmentList);
      setSchedules(scheduleList);
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
  }, [course.course_id]);

  const doorById = useMemo(() => Object.fromEntries(doors.map((d) => [d.door_id, d])), [doors]);

  // ScheduleOut now exposes the existing Schedule.course_ref_id column
  // (schemas.py), so the dropdown can be pre-filtered to schedules that
  // either belong to THIS course already or aren't linked to any course yet
  // — matching exactly what the backend's _validate_assignment_schedule
  // would accept. That backend check remains the sole authoritative
  // enforcement (its 409 text is shown verbatim below) — this filter is
  // only a UX convenience so the list isn't cluttered with schedules that
  // would always be rejected.
  const availableSchedules = schedules.filter(
    (s) => s.course_ref_id === null || s.course_ref_id === undefined || s.course_ref_id === course.course_id
  );

  function scheduleLabel(s) {
    const door = doorById[s.door_id];
    const roomLabel = door ? `${door.name} (${door.code})` : `Door #${s.door_id}`;
    return `${DAY_NAMES[s.day_of_week] || `Day ${s.day_of_week}`} ${fmtTime(s.start_time)}–${fmtTime(s.end_time)} · ${roomLabel}`;
  }

  function staffLabel(s) {
    const roleLabel = s.role === "doctor" ? "Doctor" : "TA";
    const bits = [s.name];
    if (s.staff_id) bits.push(`(${s.staff_id})`);
    bits.push(`— ${roleLabel}`);
    if (s.academic_title) bits.push(`· ${s.academic_title}`);
    if (s.department_name) bits.push(`· ${s.department_name}`);
    return bits.join(" ");
  }

  // Schedules currently linked (course_ref_id) to THIS course — the
  // "display the currently linked Course" + editable list requirement.
  const linkedSchedules = schedules.filter((s) => s.course_ref_id === course.course_id);
  // Unlinked schedules (course_ref_id null/undefined) not already linked to
  // some other course — same predicate `availableSchedules` above uses,
  // just excluding the ones already linked here (those are shown above).
  const unlinkedSchedules = schedules.filter((s) => s.course_ref_id === null || s.course_ref_id === undefined);

  async function handleCreateLinkedSchedule(e) {
    e.preventDefault();
    setScheduleLinkErr(null);
    setScheduleLinkOk(null);
    if (!newSchedule.door_id) {
      setScheduleLinkErr("Choose a room/door for the new schedule.");
      return;
    }
    setScheduleLinkBusy(true);
    try {
      await api.createSchedule({
        door_id: Number(newSchedule.door_id),
        day_of_week: Number(newSchedule.day_of_week),
        start_time: `${newSchedule.start_time}:00`,
        end_time: `${newSchedule.end_time}:00`,
        course_ref_id: course.course_id,
      });
      setScheduleLinkOk("Schedule created and linked to this course.");
      setNewSchedule({ door_id: "", day_of_week: "0", start_time: "09:00", end_time: "10:00" });
      setShowNewSchedule(false);
      await load();
    } catch (e) {
      // Surfaced verbatim — e.g. a 404 for an unknown door, or a 403 if this
      // admin isn't authorized for the course's department (schedules.py's
      // _validate_course_ref, Phase 11).
      setScheduleLinkErr(e.message);
    } finally {
      setScheduleLinkBusy(false);
    }
  }

  async function handleLinkExistingSchedule() {
    setScheduleLinkErr(null);
    setScheduleLinkOk(null);
    if (!linkScheduleId) {
      setScheduleLinkErr("Choose a schedule to link.");
      return;
    }
    setScheduleLinkBusy(true);
    try {
      await api.updateSchedule(Number(linkScheduleId), { course_ref_id: course.course_id });
      setScheduleLinkOk("Schedule linked to this course.");
      setLinkScheduleId("");
      await load();
    } catch (e) {
      // e.g. 409 if this schedule is already used by a CourseAssignment for
      // a different course (schedules.py::_validate_course_ref).
      setScheduleLinkErr(e.message);
    } finally {
      setScheduleLinkBusy(false);
    }
  }

  async function handleUnlinkSchedule(scheduleId) {
    setScheduleLinkErr(null);
    setScheduleLinkOk(null);
    setScheduleLinkBusy(true);
    try {
      await api.updateSchedule(scheduleId, { course_ref_id: null });
      setScheduleLinkOk("Schedule unlinked from this course.");
      await load();
    } catch (e) {
      setScheduleLinkErr(e.message);
    } finally {
      setScheduleLinkBusy(false);
    }
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!form.user_id) {
      setAddErr("Choose a staff member.");
      return;
    }
    setAddBusy(true);
    setAddErr(null);
    try {
      await api.assignStaffToCourse(course.course_id, {
        user_id: Number(form.user_id),
        section: form.section.trim() || null,
        semester: form.semester.trim() || null,
        academic_year: form.academic_year.trim() || null,
        schedule_id: form.schedule_id ? Number(form.schedule_id) : null,
      });
      setForm({ user_id: "", section: "", semester: "", academic_year: "", schedule_id: "" });
      setShowAdd(false);
      await load();
      await onChanged?.();
    } catch (e) {
      setAddErr(e.message);
    } finally {
      setAddBusy(false);
    }
  }

  function startEdit(a) {
    setEditingId(a.assignment_id);
    setEditForm({
      section: a.section || "", semester: a.semester || "", academic_year: a.academic_year || "",
      schedule_id: a.schedule_id || "", status: a.status || "active",
    });
    setEditErr(null);
  }

  async function saveEdit(assignmentId) {
    setEditBusy(true);
    setEditErr(null);
    try {
      await api.updateCourseAssignment(course.course_id, assignmentId, {
        section: editForm.section.trim() || null,
        semester: editForm.semester.trim() || null,
        academic_year: editForm.academic_year.trim() || null,
        schedule_id: editForm.schedule_id ? Number(editForm.schedule_id) : null,
        status: editForm.status,
      });
      setEditingId(null);
      await load();
      await onChanged?.();
    } catch (e) {
      setEditErr(e.message);
    } finally {
      setEditBusy(false);
    }
  }

  async function handleDelete(assignmentId) {
    setDeleteBusy(true);
    setDeleteErr(null);
    try {
      await api.removeCourseAssignment(course.course_id, assignmentId);
      setConfirmDeleteId(null);
      await load();
      await onChanged?.();
    } catch (e) {
      // Real backend dependency-block text, verbatim — never a generic message.
      setDeleteErr(e.message);
      setConfirmDeleteId(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="aa-modal-backdrop" onClick={onClose}>
      <div className="aa-modal aa-modal-wide" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="aa-modal-close" onClick={onClose} aria-label="Close">×</button>
        <h2 className="aa-title">{course.code} — {course.name}</h2>
        <p className="aa-subtitle">Course Assignments &mdash; instructor, section, semester, and room/schedule.</p>

        {err && <div className="form-error">{err}</div>}
        {deleteErr && <div className="form-error">{deleteErr}</div>}
        {loading && <p className="muted">Loading&hellip;</p>}

        {!loading && (
          <>
            <div className="aa-toolbar">
              <span className="muted">{assignments.length} assignment{assignments.length === 1 ? "" : "s"}</span>
              <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
                {showAdd ? "Cancel" : "+ Add Assignment"}
              </button>
            </div>

            {showAdd && (
              <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd} style={{ flexDirection: "column", alignItems: "stretch" }}>
                <select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })}>
                  <option value="">— Choose staff member —</option>
                  {staffOptions.map((s) => (
                    <option key={s.user_id} value={s.user_id}>{staffLabel(s)}</option>
                  ))}
                </select>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input placeholder="Section (e.g. A1)" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} style={{ maxWidth: 140 }} />
                  <input placeholder="Semester (e.g. Fall)" value={form.semester} onChange={(e) => setForm({ ...form, semester: e.target.value })} style={{ maxWidth: 140 }} />
                  <input placeholder="Academic year (e.g. 2026/2027)" value={form.academic_year} onChange={(e) => setForm({ ...form, academic_year: e.target.value })} style={{ maxWidth: 180 }} />
                </div>
                <select value={form.schedule_id} onChange={(e) => setForm({ ...form, schedule_id: e.target.value })}>
                  <option value="">— No schedule/room linked yet —</option>
                  {availableSchedules.map((s) => (
                    <option key={s.schedule_id} value={s.schedule_id}>{scheduleLabel(s)}</option>
                  ))}
                </select>
                {addErr && <div className="form-error">{addErr}</div>}
                <div className="aa-confirm-actions">
                  <button type="submit" disabled={addBusy}>{addBusy ? "Saving…" : "Save assignment"}</button>
                </div>
              </form>
            )}

            {assignments.length === 0 ? (
              <p className="muted">No one is assigned to this course yet.</p>
            ) : (
              <table className="aa-data-table">
                <thead>
                  <tr>
                    <th>Instructor</th>
                    <th>Section</th>
                    <th>Semester</th>
                    <th>Academic Year</th>
                    <th>Room / Schedule</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {assignments.map((a) => {
                    const staff = staffOptions.find((s) => s.user_id === a.user_id);
                    return editingId === a.assignment_id ? (
                      <tr key={a.assignment_id}>
                        <td colSpan={7}>
                          <div className="aa-inline-edit">
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              <input placeholder="Section" value={editForm.section} onChange={(e) => setEditForm({ ...editForm, section: e.target.value })} style={{ maxWidth: 140 }} />
                              <input placeholder="Semester" value={editForm.semester} onChange={(e) => setEditForm({ ...editForm, semester: e.target.value })} style={{ maxWidth: 140 }} />
                              <input placeholder="Academic year" value={editForm.academic_year} onChange={(e) => setEditForm({ ...editForm, academic_year: e.target.value })} style={{ maxWidth: 180 }} />
                              <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                                <option value="active">Active</option>
                                <option value="inactive">Inactive</option>
                              </select>
                            </div>
                            <select value={editForm.schedule_id} onChange={(e) => setEditForm({ ...editForm, schedule_id: e.target.value })}>
                              <option value="">— No schedule/room linked —</option>
                              {availableSchedules.map((s) => (
                                <option key={s.schedule_id} value={s.schedule_id}>{scheduleLabel(s)}</option>
                              ))}
                            </select>
                            {editErr && <div className="form-error">{editErr}</div>}
                            <div className="aa-confirm-actions">
                              <button type="button" className="secondary" onClick={() => setEditingId(null)} disabled={editBusy}>Cancel</button>
                              <button type="button" onClick={() => saveEdit(a.assignment_id)} disabled={editBusy}>{editBusy ? "Saving…" : "Save"}</button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      <tr key={a.assignment_id}>
                        <td>{staff ? staff.name : `User #${a.user_id}`}</td>
                        <td>{a.section || "—"}</td>
                        <td>{a.semester || "—"}</td>
                        <td>{a.academic_year || "—"}</td>
                        <td>{a.room_name ? `${a.room_name} (${a.room_code})` : "—"}</td>
                        <td><span className={`aa-status-pill ${a.status === "inactive" ? "expired" : "active"}`}>{a.status === "inactive" ? "Inactive" : "Active"}</span></td>
                        <td>
                          <span className="aa-card-footer-actions">
                            <button type="button" className="link-button" onClick={() => startEdit(a)}>Edit</button>
                            <button type="button" className="link-button aa-danger-text" onClick={() => setConfirmDeleteId(a.assignment_id)}>Remove</button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}

            <div style={{ borderTop: "1px solid var(--border)", margin: "16px 0" }} />
            <h3 className="aa-subtitle" style={{ marginBottom: 6 }}>Schedules linked to this course</h3>
            <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
              Schedule.course_ref_id — separate from the room/schedule an individual assignment above points at.
              Linking/unlinking here doesn't change any existing assignment.
            </p>

            {linkedSchedules.length === 0 ? (
              <p className="muted">No schedules are linked to this course yet.</p>
            ) : (
              <table className="aa-data-table">
                <thead>
                  <tr><th>Day</th><th>Time</th><th>Room</th><th></th></tr>
                </thead>
                <tbody>
                  {linkedSchedules.map((s) => (
                    <tr key={s.schedule_id}>
                      <td>{DAY_NAMES[s.day_of_week] || `Day ${s.day_of_week}`}</td>
                      <td>{fmtTime(s.start_time)}–{fmtTime(s.end_time)}</td>
                      <td>{doorById[s.door_id] ? `${doorById[s.door_id].name} (${doorById[s.door_id].code})` : `Door #${s.door_id}`}</td>
                      <td>
                        <button type="button" className="link-button" disabled={scheduleLinkBusy}
                                onClick={() => handleUnlinkSchedule(s.schedule_id)}>
                          Unlink
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
              <select value={linkScheduleId} onChange={(e) => setLinkScheduleId(e.target.value)} style={{ flex: 1, minWidth: 220 }}>
                <option value="">— Link an existing unlinked schedule —</option>
                {unlinkedSchedules.map((s) => (
                  <option key={s.schedule_id} value={s.schedule_id}>{scheduleLabel(s)}</option>
                ))}
              </select>
              <button type="button" className="secondary" disabled={scheduleLinkBusy || !linkScheduleId} onClick={handleLinkExistingSchedule}>
                Link
              </button>
            </div>

            {!showNewSchedule ? (
              <button type="button" className="secondary" style={{ marginTop: 8 }} onClick={() => setShowNewSchedule(true)}>
                + New schedule for this course
              </button>
            ) : (
              <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleCreateLinkedSchedule}
                    style={{ flexDirection: "column", alignItems: "stretch", marginTop: 8 }}>
                <select value={newSchedule.door_id} onChange={(e) => setNewSchedule({ ...newSchedule, door_id: e.target.value })}>
                  <option value="">— Choose room/door —</option>
                  {doors.map((d) => (
                    <option key={d.door_id} value={d.door_id}>{d.name} ({d.code})</option>
                  ))}
                </select>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <select value={newSchedule.day_of_week} onChange={(e) => setNewSchedule({ ...newSchedule, day_of_week: e.target.value })}>
                    {DAY_NAMES.map((name, idx) => (
                      <option key={name} value={idx}>{name}</option>
                    ))}
                  </select>
                  <input type="time" value={newSchedule.start_time} onChange={(e) => setNewSchedule({ ...newSchedule, start_time: e.target.value })} />
                  <input type="time" value={newSchedule.end_time} onChange={(e) => setNewSchedule({ ...newSchedule, end_time: e.target.value })} />
                </div>
                <div className="aa-confirm-actions">
                  <button type="button" className="secondary" onClick={() => setShowNewSchedule(false)} disabled={scheduleLinkBusy}>Cancel</button>
                  <button type="submit" disabled={scheduleLinkBusy}>{scheduleLinkBusy ? "Saving…" : "Create & link"}</button>
                </div>
              </form>
            )}

            {scheduleLinkErr && <div className="form-error">{scheduleLinkErr}</div>}
            {scheduleLinkOk && <div className="form-success">{scheduleLinkOk}</div>}
          </>
        )}

        {confirmDeleteId && (
          <ConfirmDialog
            title="Remove this assignment?"
            message="This unassigns the staff member from this course. This can't be undone."
            confirmLabel="Remove"
            busy={deleteBusy}
            onConfirm={() => handleDelete(confirmDeleteId)}
            onCancel={() => setConfirmDeleteId(null)}
          />
        )}
      </div>
    </div>
  );
}
