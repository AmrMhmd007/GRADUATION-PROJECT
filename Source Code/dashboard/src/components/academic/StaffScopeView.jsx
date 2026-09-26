import { useEffect, useState } from "react";
import { api } from "../../api/client";
import StaffCard from "./StaffCard";
import StaffProfile from "./StaffProfile";
import CourseAssignmentsModal from "./CourseAssignmentsModal";
import ConfirmDialog from "./ConfirmDialog";

const ACADEMIC_TITLES = [
  "Professor", "Associate Professor", "Assistant Professor",
  "Lecturer", "Instructor", "Teaching Assistant",
];

const TABS = [
  { key: "doctors", label: "Doctors/Instructors", role: "doctor" },
  { key: "tas", label: "Teaching Assistants", role: "instructor" },
  { key: "courses", label: "Courses", role: null },
];

// The Doctors|TAs|Courses tabs for one Department — this is the bottom of
// the College -> Department -> Staff hierarchy. Nothing here shows staff
// from any other department: everything is fetched with department_id set,
// which the backend enforces server-side regardless of what the frontend
// asks for (see app/routers/academic.py::list_staff). "Doctors/Instructors"
// (system role "doctor") and "Teaching Assistants" (system role
// "instructor") are kept as clearly separate tabs/views per Phase 8's
// explicit role-vs-title distinction requirement.
export default function StaffScopeView({ college, department, onBack, suggestEmail, onStaffChanged }) {
  const [activeTab, setActiveTab] = useState("doctors");
  const [staff, setStaff] = useState([]);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [profileStaff, setProfileStaff] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [titleFilter, setTitleFilter] = useState("all");
  const [search, setSearch] = useState("");

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [doctors, tas, courseList] = await Promise.all([
        api.listStaff({ departmentId: department.department_id, role: "doctor" }),
        api.listStaff({ departmentId: department.department_id, role: "instructor" }),
        api.listCourses(department.department_id),
      ]);
      setStaff([...doctors, ...tas]);
      setCourses(courseList);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department.department_id]);

  const tab = TABS.find((t) => t.key === activeTab);
  const visibleStaff = staff
    .filter((s) => (tab.role ? s.role === tab.role : false))
    .filter((s) => statusFilter === "all" || (s.status || "active") === statusFilter)
    .filter((s) => titleFilter === "all" || s.academic_title === titleFilter)
    .filter((s) => (search.trim() ? s.name.toLowerCase().includes(search.trim().toLowerCase()) || s.email.toLowerCase().includes(search.trim().toLowerCase()) || (s.staff_id || "").toLowerCase().includes(search.trim().toLowerCase()) : true));

  const doctorCount = staff.filter((s) => s.role === "doctor").length;
  const taCount = staff.filter((s) => s.role === "instructor").length;

  async function handleStaffAdded() {
    await load();
    onStaffChanged?.();
  }

  return (
    <div>
      <div className="aa-section-header">
        <div>
          <button type="button" className="link-button" style={{ paddingLeft: 0 }} onClick={onBack}>
            &larr; {college.name} departments
          </button>
          <h2 className="aa-title">{department.name}{department.code ? <span className="aa-code-badge">{department.code}</span> : null}</h2>
          <p className="aa-subtitle">{college.name}</p>
        </div>
      </div>

      <div className="aa-dept-summary">
        <div className="aa-dept-stat"><span className="value">{doctorCount}</span><span className="label">Doctors/Instructors</span></div>
        <div className="aa-dept-stat"><span className="value">{taCount}</span><span className="label">Teaching Assistants</span></div>
        <div className="aa-dept-stat"><span className="value">{doctorCount + taCount}</span><span className="label">Total Staff</span></div>
        <div className="aa-dept-stat"><span className="value">{courses.length}</span><span className="label">Courses</span></div>
      </div>

      <div className="aa-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={activeTab === t.key ? "aa-tab active" : "aa-tab"}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {err && <div className="form-error">{err}</div>}
      {loading && <p className="muted">Loading&hellip;</p>}

      {!loading && activeTab !== "courses" && (
        <StaffTabContent
          role={tab.role}
          roleLabel={tab.key === "doctors" ? "Doctor" : "TA"}
          department={department}
          college={college}
          staffList={visibleStaff}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          titleFilter={titleFilter}
          setTitleFilter={setTitleFilter}
          search={search}
          setSearch={setSearch}
          suggestEmail={suggestEmail}
          onAdded={handleStaffAdded}
          onOpenProfile={setProfileStaff}
        />
      )}

      {!loading && activeTab === "courses" && (
        <CoursesTab department={department} courses={courses} staff={staff} onChanged={load} />
      )}

      {profileStaff && (
        <StaffProfile
          staff={profileStaff}
          college={college}
          department={department}
          onClose={() => setProfileStaff(null)}
          onStaffRemoved={async () => {
            await load();
            onStaffChanged?.();
          }}
          onStaffUpdated={async () => {
            await load();
            onStaffChanged?.();
            // Keep the open profile modal in sync with the freshly-saved fields.
            setProfileStaff((prev) => {
              if (!prev) return prev;
              const fresh = [...staff].find((s) => s.user_id === prev.user_id);
              return fresh ? { ...prev, ...fresh } : prev;
            });
          }}
        />
      )}
    </div>
  );
}

function StaffTabContent({ role, roleLabel, department, staffList, statusFilter, setStatusFilter, titleFilter, setTitleFilter, search, setSearch, suggestEmail, onAdded, onOpenProfile }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [err, setErr] = useState(null);

  async function handleAdd(e) {
    e.preventDefault();
    setErr(null);
    if (!form.name.trim() || !form.email.trim() || !form.password) {
      setErr("Name, email, and password are all required.");
      return;
    }
    try {
      await api.createUser({
        name: form.name.trim(),
        email: form.email.trim(),
        role,
        password: form.password,
        faculty_id: department.faculty_id,
        department_id: department.department_id,
      });
      setForm({ name: "", email: "", password: "" });
      setShowAdd(false);
      await onAdded();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div>
      <div className="aa-toolbar">
        <input
          className="aa-search"
          placeholder={`Search ${roleLabel}s by name, email, or staff ID…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={titleFilter} onChange={(e) => setTitleFilter(e.target.value)}>
          <option value="all">All academic titles</option>
          {ACADEMIC_TITLES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : `+ Add ${roleLabel}`}
        </button>
      </div>

      {showAdd && (
        <form className="aa-inline-form" onSubmit={handleAdd}>
          <input
            placeholder="Full name"
            value={form.name}
            onChange={(e) => {
              const name = e.target.value;
              setForm((prev) => ({
                ...prev,
                name,
                email: prev.email === suggestEmail(prev.name) ? suggestEmail(name) : prev.email,
              }));
            }}
          />
          <input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input placeholder="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <button type="submit">Save</button>
        </form>
      )}
      {err && <div className="form-error">{err}</div>}

      {staffList.length === 0 ? (
        <p className="muted">No {roleLabel}s match this department/filter.</p>
      ) : (
        <div className="aa-staff-grid">
          {staffList.map((s) => (
            <StaffCard key={s.user_id} staff={s} onOpenProfile={() => onOpenProfile(s)} />
          ))}
        </div>
      )}
    </div>
  );
}

// Full Courses management for this department — a table (per Phase 8's
// explicit "tables, not cards, for administrative data" instruction), each
// row exposing Edit / Manage Assignments / Delete. Credit-hours validation
// mirrors the backend's positive-integer CheckConstraint client-side too,
// but the backend remains the authoritative check.
function CoursesTab({ department, courses, staff, onChanged }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", credit_hours: "", level: "", semester: "", description: "" });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [editErr, setEditErr] = useState(null);
  const [editBusy, setEditBusy] = useState(false);

  const [confirmDeleteCourse, setConfirmDeleteCourse] = useState(null);
  const [deleteErr, setDeleteErr] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [assignmentsCourse, setAssignmentsCourse] = useState(null);

  function validateCreditHours(value) {
    if (value === "" || value === null) return null;
    const n = Number(value);
    if (!Number.isInteger(n) || n <= 0) return "Credit hours must be a positive whole number.";
    return null;
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!form.code.trim() || !form.name.trim()) {
      setErr("Course code and name are required.");
      return;
    }
    const creditErr = validateCreditHours(form.credit_hours);
    if (creditErr) {
      setErr(creditErr);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.createCourse(department.department_id, {
        code: form.code.trim(),
        name: form.name.trim(),
        credit_hours: form.credit_hours ? Number(form.credit_hours) : null,
        level: form.level.trim() || null,
        semester: form.semester.trim() || null,
        description: form.description.trim() || null,
      });
      setForm({ code: "", name: "", credit_hours: "", level: "", semester: "", description: "" });
      setShowAdd(false);
      await onChanged();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
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
    if (creditErr) {
      setEditErr(creditErr);
      return;
    }
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
      await onChanged();
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
      setConfirmDeleteCourse(null);
      await onChanged();
    } catch (e) {
      // Real backend dependency-block text ("still has N staff assignments,
      // M schedules"), shown verbatim rather than a generic message.
      setDeleteErr(e.message);
      setConfirmDeleteCourse(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const staffOptions = staff; // doctors + TAs of this department, already loaded by the parent

  const visible = courses
    .filter((c) => statusFilter === "all" || c.status === statusFilter)
    .filter((c) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q);
    });

  return (
    <div>
      <div className="aa-toolbar">
        <input className="aa-search" placeholder="Search courses by code or name…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : "+ Add Course"}
        </button>
      </div>

      {showAdd && (
        <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd} style={{ flexWrap: "wrap" }}>
          <input placeholder="Code (e.g. ECE301)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} style={{ maxWidth: 140 }} />
          <input placeholder="Course name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Credit hours" type="number" min="1" value={form.credit_hours} onChange={(e) => setForm({ ...form, credit_hours: e.target.value })} style={{ maxWidth: 110 }} />
          <input placeholder="Level (e.g. 300)" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} style={{ maxWidth: 110 }} />
          <input placeholder="Semester (e.g. Fall)" value={form.semester} onChange={(e) => setForm({ ...form, semester: e.target.value })} style={{ maxWidth: 140 }} />
          <input placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </form>
      )}
      {err && <div className="form-error">{err}</div>}
      {deleteErr && <div className="form-error">{deleteErr}</div>}

      {courses.length === 0 && !showAdd && (
        <p className="muted">No courses in this department yet &mdash; add one above.</p>
      )}
      {courses.length > 0 && visible.length === 0 && (
        <p className="muted">No courses match your search/filter.</p>
      )}

      {visible.length > 0 && (
        <table className="aa-data-table">
          <thead>
            <tr>
              <th>Code</th><th>Name</th><th>Credit Hrs</th><th>Level</th><th>Semester</th><th>Status</th><th></th>
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
                <tr key={c.course_id} className="aa-clickable-row" onClick={() => setAssignmentsCourse(c)}>
                  <td><strong className="link-button" style={{ padding: 0 }}>{c.code}</strong></td>
                  <td>{c.name}</td>
                  <td>{c.credit_hours ?? "—"}</td>
                  <td>{c.level || "—"}</td>
                  <td>{c.semester || "—"}</td>
                  <td><span className={`aa-status-pill ${c.status === "inactive" ? "expired" : "active"}`}>{c.status === "inactive" ? "Inactive" : "Active"}</span></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className="aa-card-footer-actions">
                      <button type="button" className="link-button" onClick={() => setAssignmentsCourse(c)}>Assignments</button>
                      <button type="button" className="link-button" onClick={() => startEdit(c)}>Edit</button>
                      <button type="button" className="link-button aa-danger-text" onClick={() => setConfirmDeleteCourse(c)}>Delete</button>
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
          staffOptions={staffOptions}
          onClose={() => setAssignmentsCourse(null)}
          onChanged={onChanged}
        />
      )}

      {confirmDeleteCourse && (
        <ConfirmDialog
          title={`Delete ${confirmDeleteCourse.code}?`}
          message="This can't be undone. If this course still has staff assignments or linked schedules, deletion will be blocked until those are removed first."
          confirmLabel="Delete"
          busy={deleteBusy}
          onConfirm={() => handleDelete(confirmDeleteCourse)}
          onCancel={() => setConfirmDeleteCourse(null)}
        />
      )}
    </div>
  );
}
