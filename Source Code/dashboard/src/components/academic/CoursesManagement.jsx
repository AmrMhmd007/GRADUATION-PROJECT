import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import CourseAssignmentsModal from "./CourseAssignmentsModal";
import ConfirmDialog from "./ConfirmDialog";

// Global Courses Management — every course across every college/department
// the acting admin is authorized to see (GET /api/courses with no filter
// already applies the admin's own scope server-side; see
// app/routers/academic.py::list_courses). Add/Edit/Delete reuse the exact
// same endpoints the per-department "Courses" tab (StaffScopeView.jsx's
// CoursesTab) already used — nothing new on the backend.
export default function CoursesManagement({ colleges, onChanged, onOpenCollegeContext, initialCourseId, onAssignmentsOpen }) {
  const [courses, setCourses] = useState([]);
  const [allStaff, setAllStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const [collegeFilter, setCollegeFilter] = useState("");
  const [departments, setDepartments] = useState([]);
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ faculty_id: "", department_id: "", code: "", name: "", credit_hours: "", level: "", semester: "", description: "" });
  const [addDepts, setAddDepts] = useState([]);
  const [addErr, setAddErr] = useState(null);
  const [addBusy, setAddBusy] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [editErr, setEditErr] = useState(null);
  const [editBusy, setEditBusy] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleteErr, setDeleteErr] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [assignmentsCourse, setAssignmentsCourse] = useState(null);
  const openedInitialRef = useRef(false);

  // Deep-linking: #tab=academic&aa_section=courses&aa_course=42 opens that
  // course's assignments modal once the list has loaded — same hash
  // mechanism Dashboard.jsx already uses, no new navigation system.
  useEffect(() => {
    if (openedInitialRef.current || !initialCourseId || courses.length === 0) return;
    const match = courses.find((c) => c.course_id === Number(initialCourseId));
    if (match) {
      setAssignmentsCourse(match);
      openedInitialRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courses, initialCourseId]);

  function openAssignments(c) {
    setAssignmentsCourse(c);
    onAssignmentsOpen?.(c.course_id);
  }
  function closeAssignments() {
    setAssignmentsCourse(null);
    onAssignmentsOpen?.(null);
  }

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [courseList, staffList] = await Promise.all([
        api.listCourses(departmentFilter ? { departmentId: departmentFilter } : (collegeFilter ? { facultyId: collegeFilter } : undefined)),
        api.listStaff(),
      ]);
      setCourses(courseList);
      setAllStaff(staffList);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collegeFilter, departmentFilter]);

  useEffect(() => {
    if (!collegeFilter) { setDepartments([]); setDepartmentFilter(""); return; }
    let cancelled = false;
    api.listDepartments(collegeFilter).then((rows) => { if (!cancelled) setDepartments(rows); }).catch(() => {});
    return () => { cancelled = true; };
  }, [collegeFilter]);

  useEffect(() => {
    if (!form.faculty_id) { setAddDepts([]); return; }
    let cancelled = false;
    api.listDepartments(form.faculty_id).then((rows) => { if (!cancelled) setAddDepts(rows); }).catch(() => {});
    return () => { cancelled = true; };
  }, [form.faculty_id]);

  function validateCreditHours(value) {
    if (value === "" || value === null) return null;
    const n = Number(value);
    if (!Number.isInteger(n) || n <= 0) return "Credit hours must be a positive whole number.";
    return null;
  }

  async function handleAdd(e) {
    e.preventDefault();
    setAddErr(null);
    if (!form.department_id) { setAddErr("Choose a college and department."); return; }
    if (!form.code.trim() || !form.name.trim()) { setAddErr("Course code and name are required."); return; }
    const creditErr = validateCreditHours(form.credit_hours);
    if (creditErr) { setAddErr(creditErr); return; }
    setAddBusy(true);
    try {
      await api.createCourse(Number(form.department_id), {
        code: form.code.trim(), name: form.name.trim(),
        credit_hours: form.credit_hours ? Number(form.credit_hours) : null,
        level: form.level.trim() || null, semester: form.semester.trim() || null,
        description: form.description.trim() || null,
      });
      setForm({ faculty_id: "", department_id: "", code: "", name: "", credit_hours: "", level: "", semester: "", description: "" });
      setShowAdd(false);
      await load();
      onChanged?.();
    } catch (e) {
      setAddErr(e.message);
    } finally {
      setAddBusy(false);
    }
  }

  function startEdit(c) {
    setEditingId(c.course_id);
    setEditForm({
      code: c.code, name: c.name, credit_hours: c.credit_hours ?? "", level: c.level || "",
      semester: c.semester || "", description: c.description || "", status: c.status || "active",
    });
    setEditErr(null);
  }

  async function saveEdit(courseId) {
    const creditErr = validateCreditHours(editForm.credit_hours);
    if (creditErr) { setEditErr(creditErr); return; }
    setEditBusy(true);
    setEditErr(null);
    try {
      await api.updateCourse(courseId, {
        code: editForm.code.trim(), name: editForm.name.trim(),
        credit_hours: editForm.credit_hours === "" ? null : Number(editForm.credit_hours),
        level: editForm.level.trim() || null, semester: editForm.semester.trim() || null,
        description: editForm.description.trim() || null, status: editForm.status,
      });
      setEditingId(null);
      await load();
      onChanged?.();
    } catch (e) {
      setEditErr(e.message);
    } finally {
      setEditBusy(false);
    }
  }

  async function handleDelete(course) {
    setDeleteBusy(true);
    setDeleteErr(null);
    try {
      await api.deleteCourse(course.course_id);
      setConfirmDelete(null);
      await load();
      onChanged?.();
    } catch (e) {
      setDeleteErr(e.message);
      setConfirmDelete(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const visible = courses
    .filter((c) => statusFilter === "all" || (c.status || "active") === statusFilter)
    .filter((c) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q);
    });

  function collegeOf(c) {
    // CourseOut now exposes faculty_id (computed via Course -> Department ->
    // Faculty, no schema change) — match by ID, not display name, so a
    // college rename or a name collision can't misroute this lookup.
    return colleges.find((col) => col.faculty_id === c.faculty_id) || null;
  }

  return (
    <div>
      <div className="aa-section-header">
        <div>
          <h2 className="aa-title">Courses</h2>
          <p className="aa-subtitle">Every course you're authorized to manage, across every college and department.</p>
        </div>
        <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : "+ Add Course"}
        </button>
      </div>

      {showAdd && (
        <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd} style={{ flexWrap: "wrap" }}>
          <select value={form.faculty_id} onChange={(e) => setForm({ ...form, faculty_id: e.target.value, department_id: "" })}>
            <option value="">— Choose college —</option>
            {colleges.map((c) => <option key={c.faculty_id} value={c.faculty_id}>{c.name}</option>)}
          </select>
          <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })} disabled={!form.faculty_id}>
            <option value="">— Choose department —</option>
            {addDepts.map((d) => <option key={d.department_id} value={d.department_id}>{d.name}</option>)}
          </select>
          <input placeholder="Code (e.g. ECE301)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} style={{ maxWidth: 140 }} />
          <input placeholder="Course name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Credit hours" type="number" min="1" value={form.credit_hours} onChange={(e) => setForm({ ...form, credit_hours: e.target.value })} style={{ maxWidth: 110 }} />
          <input placeholder="Level (e.g. 300)" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} style={{ maxWidth: 110 }} />
          <input placeholder="Semester (e.g. Fall)" value={form.semester} onChange={(e) => setForm({ ...form, semester: e.target.value })} style={{ maxWidth: 140 }} />
          <input placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <button type="submit" disabled={addBusy}>{addBusy ? "Saving…" : "Save"}</button>
          {addErr && <div className="form-error" style={{ width: "100%" }}>{addErr}</div>}
        </form>
      )}

      <div className="aa-toolbar">
        <input className="aa-search" placeholder="Search courses by code or name…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={collegeFilter} onChange={(e) => setCollegeFilter(e.target.value)}>
          <option value="">All colleges</option>
          {colleges.map((c) => <option key={c.faculty_id} value={c.faculty_id}>{c.name}</option>)}
        </select>
        <select value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)} disabled={!collegeFilter}>
          <option value="">All departments</option>
          {departments.map((d) => <option key={d.department_id} value={d.department_id}>{d.name}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {err && <div className="form-error">{err}</div>}
      {deleteErr && <div className="form-error">{deleteErr}</div>}

      {loading ? (
        <p className="muted">Loading&hellip;</p>
      ) : visible.length === 0 ? (
        <p className="muted">No courses match your search/filter.</p>
      ) : (
        <table className="aa-data-table">
          <thead>
            <tr>
              <th>Code</th><th>Name</th><th>College</th><th>Department</th>
              <th>Credit Hrs</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((c) => (
              editingId === c.course_id ? (
                <tr key={c.course_id}>
                  <td colSpan={7}>
                    <div className="aa-inline-edit">
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <input value={editForm.code} onChange={(e) => setEditForm({ ...editForm, code: e.target.value })} placeholder="Code" style={{ maxWidth: 120 }} />
                        <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Name" style={{ flex: 1, minWidth: 180 }} />
                        <input type="number" min="1" value={editForm.credit_hours} onChange={(e) => setEditForm({ ...editForm, credit_hours: e.target.value })} placeholder="Credit hours" style={{ maxWidth: 110 }} />
                        <input value={editForm.level} onChange={(e) => setEditForm({ ...editForm, level: e.target.value })} placeholder="Level" style={{ maxWidth: 100 }} />
                        <input value={editForm.semester} onChange={(e) => setEditForm({ ...editForm, semester: e.target.value })} placeholder="Semester" style={{ maxWidth: 130 }} />
                        <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}>
                          <option value="active">Active</option>
                          <option value="inactive">Inactive</option>
                        </select>
                      </div>
                      <input value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="Description" />
                      {editErr && <div className="form-error">{editErr}</div>}
                      <div className="aa-confirm-actions">
                        <button type="button" className="secondary" onClick={() => setEditingId(null)} disabled={editBusy}>Cancel</button>
                        <button type="button" onClick={() => saveEdit(c.course_id)} disabled={editBusy}>{editBusy ? "Saving…" : "Save"}</button>
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={c.course_id} className="aa-clickable-row" onClick={() => openAssignments(c)}>
                  <td><strong>{c.code}</strong></td>
                  <td>{c.name}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    {collegeOf(c) ? (
                      <button type="button" className="link-button" style={{ padding: 0 }}
                              onClick={() => onOpenCollegeContext(collegeOf(c), { department_id: c.department_id, name: c.department_name })}>
                        {c.faculty_name}
                      </button>
                    ) : (c.faculty_name || "—")}
                  </td>
                  <td>{c.department_name || "—"}</td>
                  <td>{c.credit_hours ?? "—"}</td>
                  <td><span className={`aa-status-pill ${c.status === "inactive" ? "expired" : "active"}`}>{c.status === "inactive" ? "Inactive" : "Active"}</span></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className="aa-card-footer-actions">
                      <button type="button" className="link-button" onClick={() => openAssignments(c)}>Assignments</button>
                      <button type="button" className="link-button" onClick={() => startEdit(c)}>Edit</button>
                      <button type="button" className="link-button aa-danger-text" onClick={() => setConfirmDelete(c)}>Delete</button>
                    </span>
                  </td>
                </tr>
              )
            ))}
          </tbody>
        </table>
      )}

      {assignmentsCourse && (
        <CourseAssignmentsModal
          course={assignmentsCourse}
          staffOptions={allStaff}
          onClose={closeAssignments}
          onChanged={load}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title={`Delete ${confirmDelete.code}?`}
          message="This can't be undone. If this course still has staff assignments or linked schedules, deletion will be blocked until those are removed first."
          confirmLabel="Delete"
          busy={deleteBusy}
          onConfirm={() => handleDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
