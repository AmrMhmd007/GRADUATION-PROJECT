import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import StaffProfile from "./StaffProfile";

const ACADEMIC_TITLES = [
  "Professor", "Associate Professor", "Assistant Professor",
  "Lecturer", "Instructor", "Teaching Assistant",
];

// Shared global staff directory for BOTH Doctors/Instructors and Teaching
// Assistants — the two are the same underlying User rows (role "doctor" vs
// "instructor"; see models.py's User docstring), so this one component,
// parameterized by `role`, avoids duplicating the same list/filter/CRUD
// logic twice. This is the dedicated management view requested for each:
// unlike StaffScopeView (which only ever shows one department's staff),
// this lists EVERY doctor/TA the acting admin is authorized to see —
// GET /api/staff already returns exactly that when called with no
// department_id/faculty_id (backend applies the admin's own scope
// automatically; see app/routers/academic.py::list_staff).
export default function StaffManagement({ role, roleLabel, roleLabelPlural, colleges, suggestEmail, onChanged, onOpenCollegeContext, initialStaffId, onProfileOpen }) {
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [profileStaff, setProfileStaff] = useState(null);
  const openedInitialRef = useRef(false);

  // Deep-linking: a hash like #tab=academic&aa_section=tas&aa_staff=17
  // should open that TA's profile directly once the list has loaded —
  // reflects into Dashboard.jsx's existing hash mechanism via onProfileOpen,
  // no new navigation system.
  useEffect(() => {
    if (openedInitialRef.current || !initialStaffId || staff.length === 0) return;
    const match = staff.find((s) => s.user_id === Number(initialStaffId));
    if (match) {
      setProfileStaff(match);
      openedInitialRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staff, initialStaffId]);

  function openProfile(s) {
    setProfileStaff(s);
    onProfileOpen?.(s.user_id);
  }
  function closeProfile() {
    setProfileStaff(null);
    onProfileOpen?.(null);
  }

  const [collegeFilter, setCollegeFilter] = useState("");
  const [departments, setDepartments] = useState([]);
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [titleFilter, setTitleFilter] = useState("all");
  const [search, setSearch] = useState("");

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", faculty_id: "", department_id: "" });
  const [addErr, setAddErr] = useState(null);
  const [addBusy, setAddBusy] = useState(false);
  const [addDepts, setAddDepts] = useState([]);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const rows = await api.listStaff({
        role,
        facultyId: departmentFilter ? undefined : (collegeFilter || undefined),
        departmentId: departmentFilter || undefined,
      });
      setStaff(rows);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, collegeFilter, departmentFilter]);

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

  const visible = staff
    .filter((s) => statusFilter === "all" || (s.status || "active") === statusFilter)
    .filter((s) => titleFilter === "all" || s.academic_title === titleFilter)
    .filter((s) => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return s.name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q) || (s.staff_id || "").toLowerCase().includes(q);
    });

  async function handleAdd(e) {
    e.preventDefault();
    setAddErr(null);
    if (!form.name.trim() || !form.email.trim() || !form.password) {
      setAddErr("Name, email, and password are all required.");
      return;
    }
    setAddBusy(true);
    try {
      await api.createUser({
        name: form.name.trim(),
        email: form.email.trim(),
        role,
        password: form.password,
        faculty_id: form.faculty_id ? Number(form.faculty_id) : null,
        department_id: form.department_id ? Number(form.department_id) : null,
      });
      setForm({ name: "", email: "", password: "", faculty_id: "", department_id: "" });
      setShowAdd(false);
      await load();
      onChanged?.();
    } catch (e) {
      setAddErr(e.message);
    } finally {
      setAddBusy(false);
    }
  }

  function collegeOf(s) {
    return colleges.find((c) => c.faculty_id === s.faculty_id) || null;
  }
  function departmentOf(s) {
    // Only meaningful together with a college — a staff member's own
    // faculty_name/department_name (from the User model's @property) is
    // already denormalized onto each row, so we don't need a second fetch.
    return s.department_id ? { department_id: s.department_id, name: s.department_name } : null;
  }

  return (
    <div>
      <div className="aa-section-header">
        <div>
          <h2 className="aa-title">{roleLabelPlural}</h2>
          <p className="aa-subtitle">Every {roleLabel.toLowerCase()} you're authorized to manage, across every college and department.</p>
        </div>
        <button className="secondary" type="button" onClick={() => setShowAdd((v) => !v)}>
          {showAdd ? "Cancel" : `+ Add ${roleLabel}`}
        </button>
      </div>

      {showAdd && (
        <form className="aa-inline-form aa-inline-form-wide" onSubmit={handleAdd} style={{ flexWrap: "wrap" }}>
          <input
            placeholder="Full name"
            value={form.name}
            onChange={(e) => {
              const name = e.target.value;
              setForm((prev) => ({ ...prev, name, email: prev.email === suggestEmail(prev.name) ? suggestEmail(name) : prev.email }));
            }}
          />
          <input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input placeholder="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <select value={form.faculty_id} onChange={(e) => setForm({ ...form, faculty_id: e.target.value, department_id: "" })}>
            <option value="">— No college (unassigned) —</option>
            {colleges.map((c) => <option key={c.faculty_id} value={c.faculty_id}>{c.name}</option>)}
          </select>
          <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })} disabled={!form.faculty_id}>
            <option value="">— No specific department —</option>
            {addDepts.map((d) => <option key={d.department_id} value={d.department_id}>{d.name}</option>)}
          </select>
          <button type="submit" disabled={addBusy}>{addBusy ? "Saving…" : "Save"}</button>
          {addErr && <div className="form-error" style={{ width: "100%" }}>{addErr}</div>}
        </form>
      )}

      <div className="aa-toolbar">
        <input
          className="aa-search"
          placeholder={`Search ${roleLabel.toLowerCase()}s by name, email, or staff ID…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={collegeFilter} onChange={(e) => setCollegeFilter(e.target.value)}>
          <option value="">All colleges</option>
          {colleges.map((c) => <option key={c.faculty_id} value={c.faculty_id}>{c.name}</option>)}
        </select>
        <select value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)} disabled={!collegeFilter}>
          <option value="">All departments</option>
          {departments.map((d) => <option key={d.department_id} value={d.department_id}>{d.name}</option>)}
        </select>
        <select value={titleFilter} onChange={(e) => setTitleFilter(e.target.value)}>
          <option value="all">All academic titles</option>
          {ACADEMIC_TITLES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {err && <div className="form-error">{err}</div>}
      {loading ? (
        <p className="muted">Loading&hellip;</p>
      ) : visible.length === 0 ? (
        <p className="muted">No {roleLabel.toLowerCase()}s match your search/filter.</p>
      ) : (
        <table className="aa-data-table">
          <thead>
            <tr>
              <th>Name</th><th>College</th><th>Department</th><th>Academic Title</th>
              <th>Courses</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((s) => {
              const college = collegeOf(s);
              return (
                <tr key={s.user_id} className="aa-clickable-row" onClick={() => openProfile(s)}>
                  <td>
                    <strong>{s.name}</strong>{s.staff_id ? <span className="aa-code-badge">{s.staff_id}</span> : null}
                    <div className="muted" style={{ fontSize: 12 }}>{s.email}</div>
                  </td>
                  <td>
                    {college ? (
                      <button
                        type="button"
                        className="link-button"
                        style={{ padding: 0 }}
                        onClick={(e) => { e.stopPropagation(); onOpenCollegeContext(college, s.department_id ? { department_id: s.department_id, name: s.department_name, faculty_id: s.faculty_id } : null); }}
                      >
                        {college.name}
                      </button>
                    ) : <span className="muted">Unassigned</span>}
                  </td>
                  <td>{s.department_name || (college ? "—" : "Unassigned")}</td>
                  <td>{s.academic_title || "—"}</td>
                  <td>{(s.assigned_courses || []).length}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className={`aa-status-pill ${s.status === "inactive" ? "expired" : "active"}`}>
                      {s.status === "inactive" ? "Inactive" : "Active"}
                    </span>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button type="button" className="link-button" onClick={() => openProfile(s)}>View / Manage</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {profileStaff && (
        <StaffProfile
          staff={profileStaff}
          college={collegeOf(profileStaff)}
          department={departmentOf(profileStaff)}
          onClose={closeProfile}
          onStaffRemoved={async () => { await load(); onChanged?.(); }}
          onStaffUpdated={async () => {
            await load();
            onChanged?.();
            setProfileStaff((prev) => {
              if (!prev) return prev;
              const fresh = staff.find((s) => s.user_id === prev.user_id);
              return fresh ? { ...prev, ...fresh } : prev;
            });
          }}
        />
      )}
    </div>
  );
}
