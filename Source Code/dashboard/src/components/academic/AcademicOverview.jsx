// High-level entry point for Academic Administration — clickable rollup
// stats only, no CRUD here (per the requested redesign: "the dashboard
// should be a high-level overview; the dedicated management views should
// contain the actual CRUD operations"). All counts come straight from the
// same backend rollups CollegeGrid already used (FacultyOut), so this adds
// no new aggregation logic.
//
// Icons below are small hand-drawn inline SVGs (stroke-only, no fill) —
// the same "college"/"department"/"staff"/"course" glyphs GlobalSearch.jsx's
// EntityIcon already draws for these exact entity types, redrawn here rather
// than imported so this file doesn't reach into a component built for a
// different purpose; kept pixel-for-pixel identical so the icon language
// reads as one system across Global Search and Academic Administration.
// Doctors/Instructors and Teaching Assistants intentionally share the same
// "staff" glyph — Global Search's own entity-icon set doesn't distinguish
// them either.
function ScopeIcon({ type }) {
  const common = { viewBox: "0 0 24 24", width: "20", height: "20", fill: "none", stroke: "currentColor", strokeWidth: "1.8", "aria-hidden": true };
  switch (type) {
    case "colleges":
      return (
        <svg {...common}>
          <path d="M2.5 9 12 4.5 21.5 9 12 13.5 2.5 9Z" strokeLinejoin="round" />
          <path d="M6.5 11v4.2c0 1.6 2.5 3.3 5.5 3.3s5.5-1.7 5.5-3.3V11" strokeLinejoin="round" />
        </svg>
      );
    case "departments":
      return (
        <svg {...common}>
          <rect x="4" y="4" width="16" height="16" rx="1.2" />
          <path d="M8 9h8M8 13h8M8 17h5" strokeLinecap="round" />
        </svg>
      );
    case "doctors":
    case "tas":
      return (
        <svg {...common}>
          <circle cx="12" cy="8.5" r="3.2" />
          <path d="M4.8 19.5c1.2-3.6 4-5.5 7.2-5.5s6 1.9 7.2 5.5" strokeLinecap="round" />
        </svg>
      );
    case "courses":
    default:
      return (
        <svg {...common}>
          <path d="M4 5.5c2-.8 5-.8 8 0 3-.8 6-.8 8 0v13c-2-.8-5-.8-8 0-3-.8-6-.8-8 0v-13Z" strokeLinejoin="round" />
          <path d="M12 5.5v13" />
        </svg>
      );
  }
}

export default function AcademicOverview({ colleges, onNavigate }) {
  const totals = {
    colleges: colleges.length,
    departments: colleges.reduce((s, c) => s + (c.departments_count || 0), 0),
    doctors: colleges.reduce((s, c) => s + (c.doctors_count || 0), 0),
    tas: colleges.reduce((s, c) => s + (c.tas_count || 0), 0),
    courses: colleges.reduce((s, c) => s + (c.courses_count || 0), 0),
  };

  const cards = [
    { key: "colleges", label: "Colleges", value: totals.colleges, section: "colleges" },
    { key: "departments", label: "Departments", value: totals.departments, section: "departments" },
    { key: "doctors", label: "Doctors/Instructors", value: totals.doctors, section: "doctors" },
    { key: "tas", label: "Teaching Assistants", value: totals.tas, section: "tas" },
    { key: "courses", label: "Courses", value: totals.courses, section: "courses" },
  ];

  return (
    <div>
      {/* Title/subtitle now live in the shared WorkspaceHeader (AcademicAdmin.jsx)
          — this used to repeat "Academic Administration" here too, which was
          the exact kind of duplicated navigation/heading this pass removes. */}
      <p className="aa-subtitle" style={{ marginBottom: 16 }}>
        Pick a category below to manage it.
      </p>

      <div className="aa-summary-row">
        {cards.map((c) => (
          <button key={c.key} type="button" className="aa-summary-stat aa-summary-stat-clickable" onClick={() => onNavigate(c.section)}>
            <span className="value">{c.value}</span>
            <span className="label">{c.label}</span>
          </button>
        ))}
      </div>

      <div className="aa-card-grid">
        {[
          { section: "colleges", title: "Colleges", desc: "Add colleges, and drill into their departments, staff, and courses." },
          { section: "departments", title: "Departments", desc: "Manage every department across every college in one list." },
          { section: "doctors", title: "Doctors / Instructors", desc: "Add, edit, assign, reassign, or remove doctors from the academic org." },
          { section: "tas", title: "Teaching Assistants", desc: "Add, edit, assign, reassign, or remove TAs from the academic org." },
          { section: "courses", title: "Courses", desc: "Add, edit, and manage courses and their staff assignments." },
        ].map((s) => (
          <button key={s.section} type="button" className="aa-scope-card aa-scope-card-block aa-scope-card-nav" onClick={() => onNavigate(s.section)}>
            <div className="aa-scope-card-clickzone" style={{ width: "100%" }}>
              <div className="aa-scope-card-icon"><ScopeIcon type={s.section} /></div>
              <div className="aa-scope-card-body">
                <h3>{s.title}</h3>
                <p className="aa-scope-card-desc">{s.desc}</p>
              </div>
              <div className="aa-scope-card-arrow" aria-hidden="true">→</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
