import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// Command Palette v1 — "Navigate or perform a safe global command."
//
// Deliberately distinct from GlobalSearch.jsx, which answers "find an
// entity" against real backend data. This component never calls the
// backend to search: it filters the static command registry it is given
// (see ../commandPaletteConfig.js) entirely in memory, and its two
// "execute" commands call the exact same admin-gated API methods the
// existing "Run pass now" / "Run checkout sweep now" buttons already call
// elsewhere in the app — this component duplicates neither their handler
// nor their authorization logic; the backend remains the sole authority on
// whether an execute command is allowed to run.
//
// Shortcut: Cmd/Ctrl+Shift+K, so it never competes with Global Search's
// existing Cmd/Ctrl+K.
//
// Icons are small hand-drawn inline SVGs (stroke-only) in the same style as
// GlobalSearch.jsx's EntityIcon / Sidebar.jsx's own icons — every icon-in-
// flex-button gets `flex-shrink: 0` in CSS from the start (see App.css),
// avoiding the sizing bug found and fixed in Global Search's mobile trigger.

function CategoryIcon({ category }) {
  const common = { viewBox: "0 0 24 24", width: "16", height: "16", fill: "none", stroke: "currentColor", strokeWidth: "1.8", "aria-hidden": true };
  if (category === "Execute") {
    return (
      <svg {...common}>
        <path d="M6 4.5v15l13-7.5-13-7.5Z" strokeLinejoin="round" />
      </svg>
    );
  }
  // Navigation
  return (
    <svg {...common}>
      <path d="M4 12h13" strokeLinecap="round" />
      <path d="M12 5.5 18.5 12 12 18.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function CommandPalette({ commands }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [busyId, setBusyId] = useState(null);
  const [result, setResult] = useState(null); // { id, ok, message }
  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const triggerRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
    setResult(null);
    // Focus returns to whatever opened the palette (the trigger button),
    // same "focus returns appropriately on close" contract GlobalSearch's
    // own close() implicitly satisfies by never stealing focus elsewhere.
    triggerRef.current?.focus();
  }, []);

  const openPalette = useCallback(() => setOpen(true), []);

  // Cmd/Ctrl+Shift+K opens the palette from anywhere in the app shell;
  // plain Cmd/Ctrl+K is left entirely alone for GlobalSearch to handle.
  useEffect(() => {
    function onKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "k") {
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
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Click-outside-to-close — same pattern as GlobalSearch.jsx.
  useEffect(() => {
    if (!open) return;
    function onClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) close();
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open, close]);

  const trimmed = query.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!trimmed) return commands;
    return commands.filter((c) => {
      const haystack = `${c.label} ${c.keywords || ""} ${c.category}`.toLowerCase();
      return haystack.includes(trimmed);
    });
  }, [commands, trimmed]);

  // Reset the highlighted command only when the filter text actually
  // changes — not on every parent re-render. `commands` is deliberately
  // excluded from these deps: Dashboard.jsx's 5s background poll (doors/
  // alerts) re-renders Dashboard and would otherwise hand this component a
  // new (but content-identical) commands array on a timer, silently
  // resetting whatever the user had just arrow-keyed to before they could
  // press Enter.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setActiveIndex(0), [trimmed]);

  const grouped = useMemo(() => {
    const cats = ["Navigation", "Execute"];
    return cats
      .map((cat) => ({ category: cat, items: filtered.filter((c) => c.category === cat) }))
      .filter((g) => g.items.length > 0);
  }, [filtered]);

  async function runCommand(cmd) {
    if (!cmd) return;
    if (cmd.type === "navigate") {
      cmd.run();
      close();
      return;
    }
    // execute — stay open, show a real result derived from the actual
    // backend response rather than closing the moment the request returns.
    setBusyId(cmd.id);
    setResult(null);
    try {
      const r = await cmd.run();
      setResult({ id: cmd.id, ok: true, message: cmd.describeResult ? cmd.describeResult(r) : "Done." });
    } catch (e) {
      setResult({ id: cmd.id, ok: false, message: e?.message || "The operation failed." });
    } finally {
      setBusyId(null);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && filtered[activeIndex]) runCommand(filtered[activeIndex]);
    }
  }

  // Each command's position in the flat `filtered` array is its stable
  // keyboard-nav index; grouping only reorders for display.
  const groupedIndexed = grouped.map((group) => ({
    category: group.category,
    items: group.items.map((c) => ({ cmd: c, idx: filtered.indexOf(c) })),
  }));

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        className="command-palette-trigger"
        onClick={openPalette}
        aria-label="Open command palette"
        title="Command palette (&#8984;&#8679;K)"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <rect x="3.5" y="5" width="17" height="14" rx="2" />
          <path d="M7.5 9.5 10 12l-2.5 2.5M12.5 14.5h4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="command-palette-trigger-kbd">&#8984;&#8679;K</span>
      </button>

      {open && (
        <div className="command-palette-overlay" role="presentation">
          <div
            className="command-palette-panel"
            ref={containerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
          >
            <div className="command-palette-input-row">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <rect x="3.5" y="5" width="17" height="14" rx="2" />
                <path d="M7.5 9.5 10 12l-2.5 2.5M12.5 14.5h4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <input
                ref={inputRef}
                type="text"
                placeholder="Type a command&hellip;"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                aria-label="Filter commands"
                aria-activedescendant={activeIndex >= 0 ? `cp-cmd-${activeIndex}` : undefined}
                role="combobox"
                aria-expanded={filtered.length > 0}
                aria-controls="cp-command-list"
              />
              {query && (
                <button type="button" className="command-palette-clear" aria-label="Clear filter" onClick={() => setQuery("")}>
                  &times;
                </button>
              )}
              <button type="button" className="command-palette-close" aria-label="Close command palette" onClick={close}>
                Esc
              </button>
            </div>

            <div className="command-palette-list" id="cp-command-list">
              {filtered.length === 0 && (
                <p className="command-palette-hint">No commands match &ldquo;{query.trim()}&rdquo;.</p>
              )}
              {groupedIndexed.map((group) => (
                <div className="command-palette-group" key={group.category}>
                  <div className="command-palette-group-label">{group.category}</div>
                  {group.items.map(({ cmd, idx }) => (
                    <button
                      type="button"
                      key={cmd.id}
                      id={`cp-cmd-${idx}`}
                      className={idx === activeIndex ? "command-palette-item active" : "command-palette-item"}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => runCommand(cmd)}
                      disabled={busyId === cmd.id}
                    >
                      <span className="command-palette-item-icon"><CategoryIcon category={cmd.category} /></span>
                      <span className="command-palette-item-label">{cmd.label}</span>
                      {busyId === cmd.id && <span className="command-palette-item-status">Running&hellip;</span>}
                    </button>
                  ))}
                </div>
              ))}
              {result && (
                <p className={result.ok ? "command-palette-result ok" : "command-palette-result error"}>
                  {result.message}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
