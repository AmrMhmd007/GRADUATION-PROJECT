// Persistent context indicator: "AIU SMART CAMPUS / Academic Administration
// / Engineering College / ECE Department" — so the admin always knows what
// operational scope they're currently managing (feature #2 of the
// organizational-scoping request).
//
// `onRootClick` is optional and additive — WorkspaceHeader.jsx (the shared
// System Home -> Workspace -> Module -> Entity navigation shell) passes it
// so the root segment becomes a real "back to Home" control; every existing
// call site (Dashboard.jsx's Access Service drill-down, InvestigationPanel's
// modal breadcrumb) omits it and keeps behaving exactly as before — the root
// stays a plain label, not a button.
export default function Breadcrumb({ crumbs, onRootClick, rootLabel = "AIU SMART CAMPUS" }) {
  return (
    <nav className="aa-breadcrumb" aria-label="Breadcrumb">
      {onRootClick ? (
        <button type="button" className="aa-breadcrumb-root aa-breadcrumb-root-link" onClick={onRootClick}>
          {rootLabel}
        </button>
      ) : (
        <span className="aa-breadcrumb-root">{rootLabel}</span>
      )}
      {crumbs.map((c, i) => (
        <span key={i} className="aa-breadcrumb-item">
          <span className="aa-breadcrumb-sep" aria-hidden="true">/</span>
          {c.onClick ? (
            <button type="button" className="aa-breadcrumb-link" onClick={c.onClick}>
              {c.label}
            </button>
          ) : (
            <span className="aa-breadcrumb-current" aria-current={i === crumbs.length - 1 ? "page" : undefined}>
              {c.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
