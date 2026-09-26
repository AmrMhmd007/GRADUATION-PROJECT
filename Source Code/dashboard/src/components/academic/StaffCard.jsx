// Professional staff card — Name / Role / Academic Title / Courses / Status
// at a glance, deliberately not a spreadsheet-style table row (feature #3:
// "Professional Doctor/TA Profiles"). System ROLE (doctor/instructor, which
// drives RBAC and door assignment) is shown separately from ACADEMIC TITLE
// (Professor/Lecturer/Teaching Assistant/etc, which is purely descriptive —
// see User.academic_title in models.py) per Phase 8's explicit requirement
// that these never be conflated.
export default function StaffCard({ staff, onOpenProfile }) {
  const roleLabel = staff.role === "doctor" ? "Doctor" : "Teaching Assistant";
  const courseNames = (staff.assigned_courses || []).map((c) => c.code);

  return (
    <button type="button" className="aa-staff-card" onClick={onOpenProfile}>
      <div className="aa-staff-card-avatar" aria-hidden="true">
        {staff.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
      </div>
      <div className="aa-staff-card-body">
        <h4>{staff.name}{staff.staff_id ? <span className="aa-code-badge">{staff.staff_id}</span> : null}</h4>
        <p className="aa-staff-card-role">
          {roleLabel}{staff.academic_title ? ` · ${staff.academic_title}` : ""}
        </p>
        <p className="aa-staff-card-courses">
          {courseNames.length > 0 ? `Courses: ${courseNames.join(", ")}` : "No courses assigned"}
        </p>
      </div>
      <span className={`aa-status-pill ${staff.status === "inactive" ? "expired" : "active"}`}>
        {staff.status === "inactive" ? "Inactive" : "Active"}
      </span>
    </button>
  );
}
