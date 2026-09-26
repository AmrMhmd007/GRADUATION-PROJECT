import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

// Global Search — Cmd/Ctrl+K palette over real, authorized backend data
// (GET /api/search, see routers/search.py). This component owns no
// authorization logic and no fake/local dataset of its own: every result it
// shows came back from that one endpoint, which already applies the exact
// same RBAC/scope rules every underlying entity's own screen enforces.
// Navigation reuses Dashboard.jsx's existing hash-based deep-link state via
// the `onSelectResult` callback it's given — this component never touches
// window.location.hash itself, matching the single-navigation-owner rule
// the rest of the app shell already follows (see Sidebar.jsx's own note).
//
// Icons below are small hand-drawn inline SVGs (stroke-only, no fill) in the
// same style as Sidebar.jsx's HomeIcon/DomainIcon — not copied from any
// icon library.
const CATEGORY_ORDER = ["Academic", "Security", "Infrastructure", "Automation"];
const DEBOUNCE_MS = 250;
const MIN_QUERY_LEN = 2;

function EntityIcon({ type }) {
  const common = { viewBox: "0 0 24 24", width: "16", height: "16", fill: "none", stroke: "currentColor", strokeWidth: "1.8", "aria-hidden": true };
  switch (type) {
    case "college":
      return (
        <svg {...common}>
          <path d="M2.5 9 12 4.5 21.5 9 12 13.5 2.5 9Z" strokeLinejoin="round" />
          <path d="M6.5 11v4.2c0 1.6 2.5 3.3 5.5 3.3s5.5-1.7 5.5-3.3V11" strokeLinejoin="round" />
        </svg>
      );
    case "department":
      return (
        <svg {...common}>
          <rect x="4" y="4" width="16" height="16" rx="1.2" />
          <path d="M8 9h8M8 13h8M8 17h5" strokeLinecap="round" />
        </svg>
      );
    case "course":
      return (
        <svg {...common}>
          <path d="M4 5.5c2-.8 5-.8 8 0 3-.8 6-.8 8 0v13c-2-.8-5-.8-8 0-3-.8-6-.8-8 0v-13Z" strokeLinejoin="round" />
          <path d="M12 5.5v13" />
        </svg>
      );
    case "staff":
      return (
        <svg {...common}>
          <circle cx="12" cy="8.5" r="3.2" />
          <path d="M4.8 19.5c1.2-3.6 4-5.5 7.2-5.5s6 1.9 7.2 5.5" strokeLinecap="round" />
        </svg>
      );
    case "door":
      return (
        <svg {...common}>
          <rect x="6" y="3" width="12" height="18" rx="1" />
          <circle cx="14.3" cy="12" r="0.9" fill="currentColor" stroke="none" />
        </svg>
      );
    case "building":
      return (
        <svg {...common}>
          <rect x="5" y="3" width="14" height="18" rx="1" />
          <path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1" strokeLinecap="round" />
        </svg>
      );
    case "zone":
      return (
        <svg {...common}>
          <rect x="3.5" y="4" width="17" height="16" rx="1.2" />
          <path d="M3.5 10h17M10 10v10" />
        </svg>
      );
    case "automation_rule":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 3v2.4M12 18.6V21M4.2 12H6.6M17.4 12h2.4M6.3 6.3l1.7 1.7M16 16l1.7 1.7M17.7 6.3 16 8M8 16l-1.7 1.7" strokeLinecap="round" />
        </svg>
      );
    case "alert":
      return (
        <svg {...common}>
          <path d="M12 3.5 21 19H3L12 3.5Z" strokeLinejoin="round" />
          <path d="M12 10v4M12 16.5h.01" strokeLinecap="round" />
        </svg>
      );
    case "emergency_override":
      return (
        <svg {...common}>
          <path d="M12 3.5 21 19H3L12 3.5Z" strokeLinejoin="round" />
          <path d="M12 9.5v3.5" strokeLinecap="round" />
        </svg>
      );
    case "access_event":
    case "investigation":
      return (
        <svg {...common}>
          <circle cx="10.5" cy="10.5" r="6" />
          <path d="M15 15l5 5" strokeLinecap="round" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

export default function GlobalSearch({ onSelectResult }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const debounceRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
    setErr(null);
    setActiveIndex(-1);
  }, []);

  // Cmd/Ctrl+K opens the palette from anywhere in the app shell.
  useEffect(() => {
    function onKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape" && open) {
        close();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, close]);

  useEffect(() => {
    if (open) {
      // Focus on open, same pattern as Sidebar's mobile-drawer focus effect.
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Click-outside-to-close.
  useEffect(() => {
    if (!open) return;
    function onClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) close();
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open, close]);

  // Debounced, submit-based search — never one request per keystroke without
  // a debounce, never a client-side filter over a fetched-everything dataset.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const q = query.trim();
    if (q.length < MIN_QUERY_LEN) {
      setResults([]);
      setLoading(false);
      setErr(null);
      return;
    }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const resp = await api.globalSearch(q, 8);
        setResults(resp.results || []);
        setErr(null);
      } catch (e) {
        setErr(e.message);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  useEffect(() => setActiveIndex(results.length > 0 ? 0 : -1), [results]);

  const grouped = CATEGORY_ORDER.map((cat) => ({
    category: cat,
    items: results.filter((r) => r.category === cat),
  })).filter((g) => g.items.length > 0);

  function selectResult(result) {
    onSelectResult?.(result);
    close();
  }

  function handleKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && results[activeIndex]) selectResult(results[activeIndex]);
    }
  }

  const trimmed = query.trim();
  // Each result's position in the flat `results` array is its stable
  // keyboard-nav index — grouping only reorders for display, so looking it
  // up via indexOf (no mutable counter reassigned during render) keeps
  // activeIndex/aria-activedescendant in sync with the flat list Enter/Arrow
  // keys operate over.
  const groupedIndexed = grouped.map((group) => ({
    category: group.category,
    items: group.items.map((r) => ({ result: r, idx: results.indexOf(r) })),
  }));

  return (
    <>
      <button
        type="button"
        className="global-search-trigger"
        onClick={() => setOpen(true)}
        aria-label="Open global search"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <path d="M15.5 15.5 21 21" strokeLinecap="round" />
        </svg>
        <span className="global-search-trigger-label">Search&hellip;</span>
        <span className="global-search-trigger-kbd">&#8984;K</span>
      </button>

      <button
        type="button"
        className="global-search-mobile-btn"
        onClick={() => setOpen(true)}
        aria-label="Open search"
      >
        <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5" />
          <path d="M15.5 15.5 21 21" strokeLinecap="round" />
        </svg>
      </button>

      {open && (
        <div className="global-search-overlay" role="presentation">
          <div className="global-search-panel" ref={containerRef} role="dialog" aria-modal="true" aria-label="Global search">
            <div className="global-search-input-row">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <circle cx="10.5" cy="10.5" r="6.5" />
                <path d="M15.5 15.5 21 21" strokeLinecap="round" />
              </svg>
              <input
                ref={inputRef}
                type="text"
                placeholder="Search colleges, staff, doors, buildings, zones&hellip;"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                aria-label="Search"
                aria-activedescendant={activeIndex >= 0 ? `gs-result-${activeIndex}` : undefined}
                role="combobox"
                aria-expanded={results.length > 0}
                aria-controls="gs-results-list"
              />
              {query && (
                <button type="button" className="global-search-clear" aria-label="Clear search" onClick={() => setQuery("")}>
                  &times;
                </button>
              )}
              <button type="button" className="global-search-close" aria-label="Close search" onClick={close}>
                Esc
              </button>
            </div>

            <div className="global-search-results" id="gs-results-list">
              {trimmed.length < MIN_QUERY_LEN && (
                <p className="global-search-hint">Type at least {MIN_QUERY_LEN} characters to search.</p>
              )}
              {trimmed.length >= MIN_QUERY_LEN && loading && (
                <p className="global-search-hint">Searching&hellip;</p>
              )}
              {trimmed.length >= MIN_QUERY_LEN && !loading && err && (
                <p className="global-search-hint global-search-error">Search failed: {err}</p>
              )}
              {trimmed.length >= MIN_QUERY_LEN && !loading && !err && results.length === 0 && (
                <p className="global-search-hint">No results for &ldquo;{trimmed}&rdquo;.</p>
              )}
              {groupedIndexed.map((group) => (
                <div className="global-search-group" key={group.category}>
                  <div className="global-search-group-label">{group.category}</div>
                  {group.items.map(({ result: r, idx }) => (
                    <button
                      type="button"
                      key={`${r.type}-${r.id}`}
                      id={`gs-result-${idx}`}
                      className={idx === activeIndex ? "global-search-result active" : "global-search-result"}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => selectResult(r)}
                    >
                      <span className="global-search-result-icon"><EntityIcon type={r.type} /></span>
                      <span className="global-search-result-body">
                        <span className="global-search-result-title">{r.title}</span>
                        {r.subtitle && <span className="global-search-result-subtitle">{r.subtitle}</span>}
                      </span>
                      {r.meta && <span className="global-search-result-meta">{r.meta}</span>}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
