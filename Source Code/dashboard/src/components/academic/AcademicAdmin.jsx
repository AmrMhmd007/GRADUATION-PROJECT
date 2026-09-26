import { useEffect, useState } from "react";
import { api } from "../../api/client";
import WorkspaceHeader from "../WorkspaceHeader";
import CollegeGrid from "./CollegeGrid";
import DepartmentGrid from "./DepartmentGrid";
import StaffScopeView from "./StaffScopeView";
import ManageOrgModal from "./ManageOrgModal";
import AcademicOverview from "./AcademicOverview";
import StaffManagement from "./StaffManagement";
import CoursesManagement from "./CoursesManagement";
import DepartmentsManagement from "./DepartmentsManagement";

// Exported so Dashboard.jsx's Sidebar can list these same six destinations
// as its Academic Administration contextual modules — one source of truth
// for the label set, instead of the sidebar re-typing them and risking drift.
export const NAV_SECTIONS = [
  { key: "overview", label: "Overview" },
  { key: "colleges", label: "Colleges" },
  { key: "departments", label: "Departments" },
  { key: "doctors", label: "Doctors / Instructors" },
  { key: "tas", label: "Teaching Assistants" },
  { key: "courses", label: "Courses" },
];
const SECTION_KEYS = NAV_SECTIONS.map((s) => s.key);

// Academic Administration — a proper hierarchical admin module rather than
// one screen with everything on it:
//
//   Overview (clickable rollup stats, the entry point)
//     -> Colleges (existing College -> Department -> Staff drill-down)
//     -> Departments (every department, any college, one list)
//     -> Doctors / Instructors (every doctor/instructor, any college)
//     -> Teaching Assistants (every TA, any college — same component as
//                             Doctors/Instructors, parameterized by role)
//     -> Courses (every course, any college)
//
// All five reuse the exact same backend endpoints the original single-screen
// version did — GET /api/staff, /api/courses, /api/departments,
// /api/faculties already support scope-filtered *global* listing with no
// department_id (see app/routers/academic.py).
//
// Deep-linking: this component owns no URL/hash logic itself — it accepts
// the current academic navigation state as a plain prop (`navState`, read
// once on mount by Dashboard.jsx from its existing hash mechanism — see
// Dashboard.jsx's own "Stage E / E1-E2: lightweight deep-linking" comment)
// and reports every change back up via `onNavStateChange`. Dashboard.jsx is
// the ONLY place that reads/writes window.location.hash — this component
// never touches it directly, so there is exactly one navigation/URL system
// in the app, not two. College/department are tracked here as plain IDs
// (not objects) specifically so they round-trip through a URL param and a
// page refresh cleanly; the actual Faculty/Department objects are derived
// from `colleges`/`departments` by ID wherever a child component needs one.
export default function AcademicAdmin({ suggestEmail, navState, navRevision, onNavStateChange, onHome }) {
  const [colleges, setColleges] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  const initialNav = navState || {};
  const [section, setSection] = useState(SECTION_KEYS.includes(initialNav.section) ? initialNav.section : "overview");
  const [selectedCollegeId, setSelectedCollegeId] = useState(initialNav.collegeId ? Number(initialNav.collegeId) : null);
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(initialNav.departmentId ? Number(initialNav.departmentId) : null);
  const [openStaffId, setOpenStaffId] = useState(initialNav.staffId ? Number(initialNav.staffId) : null);
  const [openCourseId, setOpenCourseId] = useState(initialNav.courseId ? Number(initialNav.courseId) : null);
  const [showManage, setShowManage] = useState(false);

  const selectedCollege = selectedCollegeId ? colleges.find((c) => c.faculty_id === selectedCollegeId) || null : null;
  const selectedDepartment = selectedDepartmentId ? departments.find((d) => d.department_id === selectedDepartmentId) || null : null;

  async function loadAll() {
    setLoading(true);
    setErr(null);
    try {
      const [collegeList, deptList] = await Promise.all([
        api.listFaculties(),
        api.listDepartments(),
      ]);
      setColleges(collegeList);
      setDepartments(deptList);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  // Browser back/forward: Dashboard.jsx's popstate handler updates navState
  // and bumps navRevision. Plain useState(initialNav...) above only reads
  // navState once, at mount — it does NOT re-run when the parent passes new
  // props later, so without this, clicking the browser Back button changed
  // the URL hash but left this component's own view exactly where it was
  // (a real bug found during manual browser verification of this feature).
  // Gated on navRevision specifically — that value only changes from
  // popstate, never from the effect below that echoes our own state back up
  // to Dashboard — so this can't loop with that one.
  useEffect(() => {
    if (navRevision === undefined || navRevision === 0) return;
    const n = navState || {};
    setSection(SECTION_KEYS.includes(n.section) ? n.section : "overview");
    setSelectedCollegeId(n.collegeId ? Number(n.collegeId) : null);
    setSelectedDepartmentId(n.departmentId ? Number(n.departmentId) : null);
    setOpenStaffId(n.staffId ? Number(n.staffId) : null);
    setOpenCourseId(n.courseId ? Number(n.courseId) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navRevision]);

  // Reflect every navigation-relevant state change up to Dashboard.jsx so it
  // can fold it into the URL hash. Fires on mount too — harmless, since
  // Dashboard.jsx's own hash-writing effect already skips writes before it
  // has hydrated from the hash, and otherwise this is a same-value no-op.
  useEffect(() => {
    onNavStateChange?.({
      section,
      collegeId: selectedCollegeId,
      departmentId: selectedDepartmentId,
      staffId: openStaffId,
      courseId: openCourseId,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, selectedCollegeId, selectedDepartmentId, openStaffId, openCourseId]);

  const departmentsForCollege = selectedCollegeId
    ? departments.filter((d) => d.faculty_id === selectedCollegeId)
    : [];

  function goToSection(key) {
    setSection(key);
    if (key !== "colleges") {
      setSelectedCollegeId(null);
      setSelectedDepartmentId(null);
    }
    if (key !== "doctors" && key !== "tas") setOpenStaffId(null);
    if (key !== "courses") setOpenCourseId(null);
  }

  // Used by the Departments/Doctors/TAs/Courses management views' "open in
  // context" links — jumps into the existing College -> Department drill-down
  // (StaffScopeView) instead of duplicating that view, preserving context
  // the way the app's existing navigation already does elsewhere.
  function openCollegeContext(college, department) {
    setSection("colleges");
    setSelectedCollegeId(college?.faculty_id ?? null);
    setSelectedDepartmentId(department?.department_id ?? null);
  }

  const crumbs = [{ label: "Academic Administration", onClick: () => goToSection("overview") }];
  if (section !== "overview") {
    const navLabel = NAV_SECTIONS.find((s) => s.key === section)?.label;
    crumbs.push({
      label: navLabel,
      onClick: section === "colleges" ? () => { setSelectedCollegeId(null); setSelectedDepartmentId(null); } : undefined,
    });
  }
  if (section === "colleges" && selectedCollege) {
    crumbs.push({ label: selectedCollege.name, onClick: selectedDepartment ? () => setSelectedDepartmentId(null) : undefined });
  }
  if (section === "colleges" && selectedDepartment) {
    crumbs.push({ label: selectedDepartment.name });
  }

  if (loading) return <p className="muted">Loading academic organization&hellip;</p>;
  if (err) return <div className="form-error">{err}</div>;

  return (
    <div className="aa-root">
      <WorkspaceHeader
        title="Academic Administration"
        subtitle="Academic organization & resources"
        crumbs={crumbs}
        onHome={onHome}
      />

      {/* The Overview/Colleges/Departments/Doctors/TAs/Courses tab strip that
          used to live here is now the sidebar's Academic Administration
          contextual module list (see Dashboard.jsx's sidebarItems /
          goToAcademicSection) — keeping both would have been exactly the
          duplicated navigation this pass exists to remove. AcademicOverview's
          own summary cards below still link into these same sections, which
          is normal in-page content (like SystemHome's domain cards), not a
          second nav bar. */}

      {section === "overview" && (
        <AcademicOverview colleges={colleges} onNavigate={goToSection} />
      )}

      {section === "departments" && (
        <DepartmentsManagement colleges={colleges} onChanged={loadAll} onOpenCollegeContext={openCollegeContext} />
      )}

      {section === "doctors" && (
        <StaffManagement
          role="doctor" roleLabel="Doctor" roleLabelPlural="Doctors / Instructors"
          colleges={colleges} suggestEmail={suggestEmail} onChanged={loadAll} onOpenCollegeContext={openCollegeContext}
          initialStaffId={openStaffId} onProfileOpen={setOpenStaffId}
        />
      )}

      {section === "tas" && (
        <StaffManagement
          role="instructor" roleLabel="Teaching Assistant" roleLabelPlural="Teaching Assistants"
          colleges={colleges} suggestEmail={suggestEmail} onChanged={loadAll} onOpenCollegeContext={openCollegeContext}
          initialStaffId={openStaffId} onProfileOpen={setOpenStaffId}
        />
      )}

      {section === "courses" && (
        <CoursesManagement
          colleges={colleges} onChanged={loadAll} onOpenCollegeContext={openCollegeContext}
          initialCourseId={openCourseId} onAssignmentsOpen={setOpenCourseId}
        />
      )}

      {section === "colleges" && !selectedCollege && (
        <CollegeGrid
          colleges={colleges}
          onSelect={(c) => setSelectedCollegeId(c.faculty_id)}
          onCreated={loadAll}
          onManage={() => setShowManage(true)}
        />
      )}

      {showManage && (
        <ManageOrgModal onClose={() => setShowManage(false)} onChanged={loadAll} />
      )}

      {section === "colleges" && selectedCollege && !selectedDepartment && (
        <DepartmentGrid
          college={selectedCollege}
          departments={departmentsForCollege}
          onSelect={(d) => setSelectedDepartmentId(d.department_id)}
          onBack={() => setSelectedCollegeId(null)}
          onCreated={loadAll}
        />
      )}

      {section === "colleges" && selectedCollege && selectedDepartment && (
        <StaffScopeView
          college={selectedCollege}
          department={selectedDepartment}
          onBack={() => setSelectedDepartmentId(null)}
          suggestEmail={suggestEmail}
          onStaffChanged={loadAll}
        />
      )}
    </div>
  );
}
