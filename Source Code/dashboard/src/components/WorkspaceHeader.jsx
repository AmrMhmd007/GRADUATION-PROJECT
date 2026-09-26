import Breadcrumb from "./academic/Breadcrumb";

// Shared navigation shell for the System Home -> Workspace -> Module ->
// Entity hierarchy. One component, reused by every workspace (Academic
// Administration, Security, Smart Building — Command Center is a single
// screen and doesn't need one) instead of each screen inventing its own
// title/breadcrumb markup. Wraps the existing Breadcrumb component (already
// shared across Dashboard.jsx, InvestigationPanel.jsx, and Academic) rather
// than replacing it — the root segment becomes a real "back to Home" link
// via `onHome`, which is additive and doesn't change any of Breadcrumb's
// other call sites.
//
// Deliberately minimal for this pass: title, subtitle, breadcrumb crumbs,
// and an optional actions slot. No metrics row here — a workspace's own
// content (e.g. AcademicOverview's summary stats) already owns real
// backend-derived numbers where they exist; duplicating them in the header
// would risk two sources of truth for the same figure.
export default function WorkspaceHeader({ title, subtitle, crumbs = [], onHome, actions }) {
  return (
    <div className="workspace-header">
      <Breadcrumb crumbs={crumbs} onRootClick={onHome} rootLabel="Home" />
      <div className="workspace-header-row">
        <div>
          <h1 className="workspace-title">{title}</h1>
          {subtitle && <p className="workspace-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="workspace-header-actions">{actions}</div>}
      </div>
    </div>
  );
}
