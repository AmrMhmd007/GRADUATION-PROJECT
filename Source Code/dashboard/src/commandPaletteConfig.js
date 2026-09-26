// Command Palette v1 — command registry (the single source of truth).
//
// Every command below maps to a real, pre-existing destination or a real,
// pre-existing admin-gated backend operation — nothing here invents a route
// or a handler. Navigate commands call the exact same selectTab /
// goToAcademicSection functions Sidebar.jsx and Dashboard.jsx's own tab bar
// already call. Execute commands call the exact same api.* methods
// SmartBuildingDashboard.jsx ("Run pass now") and AccountMenu.jsx
// ("Run checkout sweep now") already call — this file does not duplicate
// their authorization logic; the backend remains the only authority on
// whether an execute command is actually allowed to run.
//
// See the accepted Command Palette action audit for the full list of
// existing actions deliberately excluded from v1 (destructive, target-
// dependent, or lacking a safe existing confirmation/authentication
// workflow) — none of those are represented here, and none should be added
// without a fresh audit.

export function buildNavigationCommands({ selectTab, goToAcademicSection }) {
  const toTab = (key) => () => selectTab(key);
  const toAcademic = (sectionKey) => () => {
    selectTab("academic");
    goToAcademicSection(sectionKey);
  };

  return [
    { id: "nav-home", label: "Home", keywords: "home system start overview", category: "Navigation", type: "navigate", run: toTab("home") },
    { id: "nav-command-center", label: "Command Center", keywords: "command center live status overview", category: "Navigation", type: "navigate", run: toTab("command") },
    { id: "nav-main-doors", label: "Main Doors", keywords: "security critical main doors", category: "Navigation", type: "navigate", run: toTab("critical") },
    { id: "nav-access-service", label: "Access Service", keywords: "security access service requests", category: "Navigation", type: "navigate", run: toTab("access") },
    { id: "nav-access-events", label: "Access Events", keywords: "security access events log investigate investigation", category: "Navigation", type: "navigate", run: toTab("events") },
    { id: "nav-smart-building", label: "Smart Building Overview", keywords: "smart building rooms zones automation overview", category: "Navigation", type: "navigate", run: toTab("smart") },
    { id: "nav-academic-overview", label: "Academic Administration Overview", keywords: "academic administration overview", category: "Navigation", type: "navigate", run: toTab("academic") },
    { id: "nav-academic-colleges", label: "Open Colleges", keywords: "college colleges academic", category: "Navigation", type: "navigate", run: toAcademic("colleges") },
    { id: "nav-academic-departments", label: "Open Departments", keywords: "department departments academic", category: "Navigation", type: "navigate", run: toAcademic("departments") },
    { id: "nav-academic-doctors", label: "Open Doctors / Instructors", keywords: "doctor doctors instructor instructors staff academic", category: "Navigation", type: "navigate", run: toAcademic("doctors") },
    { id: "nav-academic-tas", label: "Open Teaching Assistants", keywords: "ta tas teaching assistants staff academic", category: "Navigation", type: "navigate", run: toAcademic("tas") },
    { id: "nav-academic-courses", label: "Open Courses", keywords: "course courses academic", category: "Navigation", type: "navigate", run: toAcademic("courses") },
  ];
}

// Exactly two safe, target-less, admin-gated execute commands — no more are
// added in v1. `run` must return the same backend response the existing
// buttons already surface, so the palette can show a real result rather than
// a bare "done".
export function buildExecuteCommands({ runAutomationOnce, runCheckoutSweep }) {
  return [
    {
      id: "exec-automation-pass",
      label: "Run automation pass now",
      keywords: "run automation pass engine smart building execute",
      category: "Execute",
      type: "execute",
      run: runAutomationOnce,
      describeResult: (r) =>
        r && typeof r.zones_with_activity === "number"
          ? `Automation pass complete — ${r.zones_with_activity} zone(s) had activity.`
          : "Automation pass complete.",
    },
    {
      id: "exec-checkout-sweep",
      label: "Run checkout sweep now",
      keywords: "run checkout sweep energy rooms execute",
      category: "Execute",
      type: "execute",
      run: runCheckoutSweep,
      describeResult: (r) =>
        r && r.rooms_swept === 0
          ? "Nothing was on — no rooms needed shutting down."
          : r && typeof r.rooms_swept === "number"
          ? `Swept ${r.rooms_swept} room(s)${r.door_codes?.length ? `: ${r.door_codes.join(", ")}.` : "."}`
          : "Checkout sweep complete.",
    },
  ];
}
