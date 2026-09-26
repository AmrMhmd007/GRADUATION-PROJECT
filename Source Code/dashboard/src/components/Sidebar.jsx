import { useEffect, useRef } from "react";

// Fixed left navigation shell — Level 1 (Home / Workspaces) and Level 2
// (the active workspace's own contextual modules) in one place, replacing
// the old top-of-page domain-subnav row so there is exactly one canonical
// spot for workspace/module switching (see App.css's .app-sidebar rules and
// the removal of .domain-subnav's render site in Dashboard.jsx).
//
// This component owns no navigation state itself: `domains` and
// `contextualItems` are computed by Dashboard.jsx (still the only place
// that reads/writes the URL hash), and every click here just calls back
// into functions Dashboard.jsx already had (selectTab / goToAcademicSection
// / selectTab("home")). It renders only real, already-existing destinations
// — nothing here is a route invented just to fill space.
//
// Icons are small hand-drawn inline SVGs (stroke-only, no fill) — not
// copied from any third-party icon set or the AIU portal itself.
function HomeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M4 11.5 12 4l8 7.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 10v9h12v-9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 19v-5h4v5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DomainIcon({ domainKey }) {
  const common = { viewBox: "0 0 24 24", width: "18", height: "18", fill: "none", stroke: "currentColor", strokeWidth: "1.8", "aria-hidden": true };
  if (domainKey === "command") {
    return (
      <svg {...common}>
        <rect x="4" y="4" width="7" height="7" rx="1.2" />
        <rect x="13" y="4" width="7" height="7" rx="1.2" />
        <rect x="4" y="13" width="7" height="7" rx="1.2" />
        <rect x="13" y="13" width="7" height="7" rx="1.2" />
      </svg>
    );
  }
  if (domainKey === "security") {
    return (
      <svg {...common}>
        <path d="M12 3.5 5 6v5.5c0 4.5 3 7.6 7 9 4-1.4 7-4.5 7-9V6l-7-2.5Z" strokeLinejoin="round" />
        <path d="M9.3 12.2l1.9 1.9 3.5-3.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (domainKey === "smart") {
    return (
      <svg {...common}>
        <path d="M5 21V6l7-3 7 3v15" strokeLinejoin="round" />
        <path d="M9 21v-6h6v6" strokeLinejoin="round" />
        <path d="M9 10h.01M12 10h.01M15 10h.01" strokeLinecap="round" />
      </svg>
    );
  }
  // academic
  return (
    <svg {...common}>
      <path d="M2.5 9 12 4.5 21.5 9 12 13.5 2.5 9Z" strokeLinejoin="round" />
      <path d="M6.5 11v4.2c0 1.6 2.5 3.3 5.5 3.3s5.5-1.7 5.5-3.3V11" strokeLinejoin="round" />
    </svg>
  );
}

export default function Sidebar({
  domains,
  activeDomain,
  contextualItems,
  isHome,
  onHome,
  onSelectDomain,
  mobileOpen,
  onCloseMobile,
}) {
  const homeButtonRef = useRef(null);

  // Mobile drawer accessibility: Escape closes it (same as clicking the
  // backdrop), and opening it moves focus onto the drawer's first item so
  // keyboard users land inside the nav they just opened rather than staying
  // on the now-hidden-behind-overlay menu button. Desktop is unaffected —
  // this only runs while mobileOpen is true, which CSS only ever lets
  // happen below the drawer breakpoint (see .app-sidebar/.open in App.css).
  useEffect(() => {
    if (!mobileOpen) return;
    homeButtonRef.current?.focus();
    function onKeyDown(e) {
      if (e.key === "Escape") onCloseMobile();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mobileOpen]);

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={onCloseMobile}
        />
      )}
      <aside id="app-sidebar-nav" className={mobileOpen ? "app-sidebar open" : "app-sidebar"} aria-label="Primary navigation">
        <button
          ref={homeButtonRef}
          type="button"
          className={isHome ? "sidebar-home active" : "sidebar-home"}
          onClick={onHome}
          aria-current={isHome ? "page" : undefined}
        >
          <HomeIcon />
          <span>Home</span>
        </button>

        <div className="sidebar-section-label">Workspaces</div>

        <nav className="sidebar-workspaces">
          {domains.map((d) => {
            const isActive = activeDomain?.key === d.key;
            return (
              <div key={d.key} className={isActive ? "sidebar-workspace active" : "sidebar-workspace"}>
                <button
                  type="button"
                  className="sidebar-workspace-btn"
                  onClick={() => {
                    if (!isActive) onSelectDomain(d);
                  }}
                  aria-current={isActive ? "page" : undefined}
                >
                  <DomainIcon domainKey={d.key} />
                  <span>{d.label}</span>
                </button>

                {isActive && contextualItems.length > 0 && (
                  <div className="sidebar-modules">
                    {contextualItems.map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        className={item.active ? "sidebar-module active" : "sidebar-module"}
                        onClick={item.onClick}
                        aria-current={item.active ? "page" : undefined}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
