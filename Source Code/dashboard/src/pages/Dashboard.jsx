import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../AuthContext";
import { api } from "../api/client";
import DoorCard from "../components/DoorCard";
import AlertBanner from "../components/AlertBanner";
import LogsTable from "../components/LogsTable";
import AccountMenu from "../components/AccountMenu";
import RoomProfile from "../components/RoomProfile";
import SmartBuildingDashboard from "../components/smart-building/SmartBuildingDashboard";
import AcademicAdmin, { NAV_SECTIONS as ACADEMIC_NAV_SECTIONS } from "../components/academic/AcademicAdmin";
import SystemHome from "../components/SystemHome";
import WorkspaceHeader from "../components/WorkspaceHeader";
import Sidebar from "../components/Sidebar";
import GlobalSearch from "../components/GlobalSearch";
import CommandPalette from "../components/CommandPalette";
import { buildNavigationCommands, buildExecuteCommands } from "../commandPaletteConfig";
import CommandCenter from "../components/CommandCenter";
import BuildingGrid from "../components/BuildingGrid";
import InvestigationPanel from "../components/academic/InvestigationPanel";
import AccessEventsPage from "../components/academic/AccessEventsPage";

const POLL_MS = 5000;

// Turns "Ahmed Mohamed Ali" into "ahmed.mohamed.ali@AIU.IS" — a starting
// point the admin can still edit by hand before saving, since real name
// collisions (two "Mohamed Ali"s) need a human to disambiguate anyway.
const STAFF_EMAIL_DOMAIN = "AIU.IS";
function suggestEmail(fullName) {
  const slug = fullName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s.]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .join(".");
  return slug ? `${slug}@${STAFF_EMAIL_DOMAIN}` : "";
}

const ADMIN_TABS = [
  { key: "command", label: "Command Center" },
  { key: "critical", label: "Main Doors" },
  { key: "access", label: "Access Service" },
  { key: "events", label: "Access Events" },
  { key: "smart", label: "Smart Building" },
  { key: "academic", label: "Academic Administration" },
];

// System-wide, two-level navigation. Every ADMIN_TABS entry above is still
// the one and only real destination/hash value — DOMAINS is purely a
// grouping layer on top of it (System Home -> Domain -> Module), not a
// second navigation system: a domain's `tabs` are just the existing tab keys
// that belong under it. Security groups the three access-control tabs that
// already existed as separate flat entries; Command Center/Smart
// Building/Academic Administration are single-tab domains (each already has
// its own internal navigation — CommandCenter, SmartBuildingDashboard's own
// tabs, and AcademicAdmin's own Overview/Colleges/.../Courses tab bar — so
// nothing is duplicated here). No "System Administration" domain is added:
// there is no existing standalone top-level function that would belong under
// it (admin-scope/building/audit-log management already live in AccountMenu,
// which stays exactly as it is).
const DOMAINS = [
  { key: "command", label: "Command Center", description: "Live operational overview.", tabs: ["command"] },
  { key: "security", label: "Security", description: "Doors, access service, and access events.", tabs: ["critical", "access", "events"] },
  { key: "smart", label: "Smart Building", description: "Buildings, rooms, zones, and automation.", tabs: ["smart"] },
  { key: "academic", label: "Academic Administration", description: "Colleges, departments, staff, and courses.", tabs: ["academic"] },
];

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [doors, setDoors] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedDoorId, setSelectedDoorId] = useState(null);
  const [err, setErr] = useState(null);
  // "home" is System Home (Level 1 of the nav hierarchy) — a valid activeTab
  // value alongside every ADMIN_TABS key, not a separate state machine; see
  // the isValidTab() helper and the hash effects below.
  const [activeTab, setActiveTab] = useState("home");
  // Sidebar's off-canvas (narrow-width) open/closed state — desktop ignores
  // this entirely (CSS keeps .app-sidebar always visible above the drawer
  // breakpoint). Closed by default and reset to closed on every navigation
  // (see selectTab / goToAcademicSection) so picking a destination on mobile
  // also dismisses the drawer, matching normal drawer-nav behavior.
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false);

  const [showAddDoor, setShowAddDoor] = useState(false);
  const [newDoor, setNewDoor] = useState({
    code: "", name: "", building: "", floor: "", fail_mode: "secure", category: "critical",
    ac_enabled: false, light_enabled: false,
  });
  // Plug labels for a new Room — a simple growable list of text inputs
  // ("Plug 1", "Projector outlet", ...), only shown for access_service.
  const [plugLabels, setPlugLabels] = useState([]);
  const [addDoorErr, setAddDoorErr] = useState(null);
  // Populated for the "Add Door" building select — building management
  // itself (add/remove) lives in the account menu now, not here.
  const [buildings, setBuildings] = useState([]);

  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importErr, setImportErr] = useState(null);
  const importInputRef = useRef(null);

  const [doorSearch, setDoorSearch] = useState("");
  // Which building to narrow the Access Service tab down to — "" means all
  // buildings. Only meaningful there (Main Doors is usually just a handful
  // of entrances/critical doors, not worth filtering by building).
  const [buildingFilter, setBuildingFilter] = useState("");

  // Which Room's profile is currently open (door lock + AC + light + plugs
  // + history, all in one place) — separate from selectedDoorId, which
  // still drives the plain History panel used by Main Doors.
  const [roomProfileId, setRoomProfileId] = useState(null);
  const [roomLogs, setRoomLogs] = useState([]);
  const roomProfileDoor = doors.find((d) => d.door_id === roomProfileId) || null;
  // Tracks whether `doors` reflects a real backend response yet — needed so
  // a deep-linked room id isn't flashed as "not found" during the brief
  // window before the first /api/doors response comes back.
  const [doorsLoaded, setDoorsLoaded] = useState(false);

  // Stage C — which AccessEvent is currently being investigated (Command
  // Center's recent events / anomaly indicators, or an Emergency Override's
  // related events). Independent of roomProfileId — an investigation can be
  // opened without a Room profile ever being open.
  const [investigatingEventId, setInvestigatingEventId] = useState(null);

  // Academic Administration deep-linking state — same lightweight hash
  // mechanism as the rest of this component (see the comment above the hash
  // effects below), just five more optional params that only apply when
  // activeTab === "academic". AcademicAdmin.jsx owns none of this directly:
  // it receives the current values as a plain `navState` prop and reports
  // every change back via `onNavStateChange`, so this file stays the single
  // place that reads/writes window.location.hash.
  const [aaSection, setAaSection] = useState("overview");
  const [aaCollegeId, setAaCollegeId] = useState(null);
  const [aaDepartmentId, setAaDepartmentId] = useState(null);
  const [aaStaffId, setAaStaffId] = useState(null);
  const [aaCourseId, setAaCourseId] = useState(null);
  // Bumped only by onPopState below — tells AcademicAdmin.jsx "the hash
  // changed out from under you (browser back/forward), re-sync your internal
  // state from navState" without also firing on every ordinary render where
  // navState is just AcademicAdmin echoing its own state back up (which
  // would be a no-op sync, but also an infinite-loop risk if it weren't
  // gated like this — see AcademicAdmin.jsx's matching effect).
  const [aaNavRevision, setAaNavRevision] = useState(0);

  // Stage E / E4: opened from RoomProfile's "Manage in Smart Building" —
  // switches to the Smart Building tab and asks it to open that zone's
  // detail modal. focusZoneToken changes on every click (even to the same
  // zone) so SmartBuildingDashboard's effect reliably re-fires.
  const [focusZoneId, setFocusZoneId] = useState(null);
  const [focusZoneToken, setFocusZoneToken] = useState(0);
  // Mirrors whichever zone SmartBuildingDashboard currently has open (via
  // its own onZoneOpenChange report — see its render below) so the zone can
  // be written into the hash the same way room/investigate already are.
  // focusZoneId/focusZoneToken above remain the one-shot "please open this
  // zone" trigger; this is the read-back "here's what's actually open now".
  const [smartZoneId, setSmartZoneId] = useState(null);
  function openZone(zoneId) {
    setFocusZoneId(zoneId);
    setFocusZoneToken((t) => t + 1);
    setSmartZoneId(zoneId);
    setActiveTab("smart");
    closeRoomProfile();
  }

  // Stage E / E1-E2: lightweight deep-linking. The app has never used a
  // routing library, and introducing one now (react-router + a full
  // /buildings/:id-style route tree) would mean re-plumbing every screen's
  // navigation on top of the tab/state model everything already relies on
  // — a rebuild, not a fix. Instead this reflects the same navigation state
  // that already exists (activeTab, buildingFilter, roomProfileId,
  // investigatingEventId) into the URL hash, so a link can be bookmarked or
  // shared, a refresh preserves context, and the browser back/forward
  // buttons work — without a second navigation architecture.
  // Deliberately React STATE, not a ref. The writer effect below guards on
  // this value — it must become visible to that effect on exactly the same
  // render where the hydrated activeTab/aaCollegeId/etc. values become
  // visible, or the writer can run once with the *old* defaults still in its
  // closure while a ref already reads as "true" (a ref mutates immediately,
  // synchronously, so a same-commit reader sees it flip before the state
  // updates scheduled alongside it have actually re-rendered). That mismatch
  // was the root cause of a real bug: on a hard reload of a deep link (e.g.
  // #tab=academic&aa_college=1&aa_department=1), the hydration effect and
  // the writer effect both run in the same initial commit; with a ref guard,
  // the writer saw "hydrated" already true but still read activeTab from
  // that commit's stale closure ("home", the initial default) and pushed
  // "#tab=home" over the real hash before the hydrated state had rendered —
  // and under StrictMode's double-invoked mount effects (dev only), the
  // second hydration pass then re-read that just-corrupted hash as ground
  // truth, permanently losing the deep link. Using state instead of a ref
  // fixes this deterministically (no timers, no StrictMode workaround):
  // React batches every setState call made inside one effect invocation
  // into a single next render, so `hydrated` and every other hydrated value
  // become visible to the writer effect on the exact same later render —
  // never in between.
  const [hydrated, setHydrated] = useState(false);

  function parseHash() {
    return Object.fromEntries(new URLSearchParams(window.location.hash.replace(/^#/, "")));
  }

  function isValidTab(key) {
    return key === "home" || ADMIN_TABS.some((t) => t.key === key);
  }

  useEffect(() => {
    const params = parseHash();
    if (params.tab && isValidTab(params.tab)) setActiveTab(params.tab);
    if (params.building) setBuildingFilter(params.building);
    if (params.room) setRoomProfileId(Number(params.room));
    if (params.investigate) setInvestigatingEventId(Number(params.investigate));
    if (params.zone) {
      const zid = Number(params.zone);
      setFocusZoneId(zid);
      setFocusZoneToken((t) => t + 1);
      setSmartZoneId(zid);
    }
    // Academic Administration deep-link context — only meaningful when
    // tab=academic, but harmless to hydrate unconditionally since
    // AcademicAdmin.jsx ignores navState it isn't currently showing.
    if (params.aa_section) setAaSection(params.aa_section);
    if (params.aa_college) setAaCollegeId(Number(params.aa_college));
    if (params.aa_department) setAaDepartmentId(Number(params.aa_department));
    if (params.aa_staff) setAaStaffId(Number(params.aa_staff));
    if (params.aa_course) setAaCourseId(Number(params.aa_course));
    setHydrated(true);

    function onPopState() {
      const p = parseHash();
      setActiveTab(p.tab && isValidTab(p.tab) ? p.tab : "home");
      setBuildingFilter(p.building || "");
      setRoomProfileId(p.room ? Number(p.room) : null);
      setInvestigatingEventId(p.investigate ? Number(p.investigate) : null);
      const zid = p.zone ? Number(p.zone) : null;
      setFocusZoneId(zid);
      setFocusZoneToken((t) => t + 1);
      setSmartZoneId(zid);
      setAaSection(p.aa_section || "overview");
      setAaCollegeId(p.aa_college ? Number(p.aa_college) : null);
      setAaDepartmentId(p.aa_department ? Number(p.aa_department) : null);
      setAaStaffId(p.aa_staff ? Number(p.aa_staff) : null);
      setAaCourseId(p.aa_course ? Number(p.aa_course) : null);
      setAaNavRevision((n) => n + 1);
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Skip every render before hydration has actually landed — otherwise
    // this can fire once with the pre-hydration defaults still in its
    // closure and stomp the very hash the hydration effect above is in the
    // middle of restoring (see the long comment on the `hydrated` state
    // declaration for the full mechanics of that race). `hydrated` is in
    // this effect's dependency array specifically so this re-runs (and
    // passes) on the render where it flips true, using that render's own —
    // now-correct — values, not stale ones.
    if (!hydrated) return;
    const params = new URLSearchParams();
    params.set("tab", activeTab);
    if (buildingFilter) params.set("building", buildingFilter);
    if (roomProfileId != null) params.set("room", String(roomProfileId));
    if (investigatingEventId != null) params.set("investigate", String(investigatingEventId));
    if (activeTab === "smart" && smartZoneId != null) params.set("zone", String(smartZoneId));
    if (activeTab === "academic") {
      if (aaSection && aaSection !== "overview") params.set("aa_section", aaSection);
      if (aaCollegeId != null) params.set("aa_college", String(aaCollegeId));
      if (aaDepartmentId != null) params.set("aa_department", String(aaDepartmentId));
      if (aaStaffId != null) params.set("aa_staff", String(aaStaffId));
      if (aaCourseId != null) params.set("aa_course", String(aaCourseId));
    }
    const next = `#${params.toString()}`;
    if (window.location.hash !== next) window.history.pushState(null, "", next);
  }, [hydrated, activeTab, buildingFilter, roomProfileId, investigatingEventId, smartZoneId, aaSection, aaCollegeId, aaDepartmentId, aaStaffId, aaCourseId]);

  const canOverride = user?.role === "admin";
  const canRequestAccess = user?.role === "instructor" || user?.role === "doctor";
  // AC/light/plugs — unlike the lock itself, a doctor can flip these
  // directly for a room they're assigned to (server checks the assignment).
  const canControlRoom = user?.role === "admin" || user?.role === "doctor";
  const isDoorTab = activeTab === "critical" || activeTab === "access";
  const isRoomTab = activeTab === "access";
  // Which domain the current tab belongs to — null while on System Home.
  // Purely derived from DOMAINS + activeTab, not separate navigation state,
  // so it can never drift out of sync with the single source of truth
  // (activeTab, which the hash effects above already own).
  const activeDomain = DOMAINS.find((d) => d.tabs.includes(activeTab)) || null;

  // Sidebar's Level-2 ("contextual modules") list for whichever workspace is
  // active — computed here, not inside Sidebar.jsx, so there is exactly one
  // place that decides what counts as a real destination. Each domain maps
  // to modules that already exist in the app; nothing here is invented:
  //   - Security has three real tabs (critical/access/events) -> three items.
  //   - Academic Administration has AcademicAdmin.jsx's own six real
  //     sections -> reuses its NAV_SECTIONS labels directly.
  //   - Command Center and Smart Building are each a single existing screen
  //     with no separate top-level destinations of their own (Smart
  //     Building's Building -> Room -> Zone/Device drill is internal state
  //     inside SmartBuildingDashboard, not a distinct route) -> one "Overview"
  //     item pointing at that one screen, so the sidebar still shows a
  //     workspace's current location without fabricating sub-pages that
  //     don't exist in the codebase.
  const sidebarItems = !activeDomain
    ? []
    : activeDomain.key === "academic"
      ? ACADEMIC_NAV_SECTIONS.map((s) => ({
          key: s.key,
          label: s.label,
          active: aaSection === s.key,
          onClick: () => goToAcademicSection(s.key),
        }))
      : activeDomain.tabs.length > 1
        ? activeDomain.tabs.map((key) => ({
            key,
            label: ADMIN_TABS.find((t) => t.key === key)?.label || key,
            active: activeTab === key,
            onClick: () => selectTab(key),
          }))
        : [{ key: activeDomain.tabs[0], label: "Overview", active: true, onClick: () => selectTab(activeDomain.tabs[0]) }];

  const refresh = useCallback(async () => {
    try {
      const [doorList, alertList] = await Promise.all([
        api.listDoors(),
        api.listAlerts(false),
      ]);
      setDoors(doorList);
      setAlerts(alertList);
      setErr(null);
      setDoorsLoaded(true);
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  const refreshLogs = useCallback(async (doorId) => {
    if (doorId == null) {
      setLogs([]);
      return;
    }
    try {
      const doorLogs = await api.doorLogs(doorId);
      setLogs(doorLogs);
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    refreshLogs(selectedDoorId);
  }, [selectedDoorId, refreshLogs]);

  const refreshRoomLogs = useCallback(async (doorId) => {
    // History is admin-only (see RoomProfile) — don't even fetch it for
    // TAs/doctors opening their own room's profile.
    if (doorId == null || !canOverride) {
      setRoomLogs([]);
      return;
    }
    try {
      setRoomLogs(await api.doorLogs(doorId));
    } catch (e) {
      setErr(e.message);
    }
  }, [canOverride]);

  useEffect(() => {
    refreshRoomLogs(roomProfileId);
  }, [roomProfileId, refreshRoomLogs]);

  function openRoomProfile(doorId) {
    setRoomProfileId(doorId);
  }

  function closeRoomProfile() {
    setRoomProfileId(null);
  }

  const loadBuildings = useCallback(async () => {
    try {
      const list = await api.listBuildings();
      setBuildings(list);
    } catch (e) {
      setAddDoorErr(e.message);
    }
  }, []);

  useEffect(() => {
    if (canOverride) loadBuildings();
  }, [canOverride, loadBuildings]);

  async function handleOverride(doorId, action) {
    try {
      await api.overrideDoor(doorId, action);
      await refresh();
      if (selectedDoorId === doorId) await refreshLogs(doorId);
      if (roomProfileId === doorId) await refreshRoomLogs(doorId);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleRequestAccess(doorId) {
    try {
      await api.requestDoorAccess(doorId);
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleSetStatus(doorId, online) {
    try {
      await api.setDoorStatus(doorId, online);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleDeleteDoor(doorId) {
    try {
      await api.deleteDoor(doorId);
      if (selectedDoorId === doorId) setSelectedDoorId(null);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleResolve(alertId) {
    try {
      await api.resolveAlert(alertId);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleAddDoor(e) {
    e.preventDefault();
    setAddDoorErr(null);
    if (!newDoor.code.trim() || !newDoor.name.trim() || !newDoor.building.trim()) {
      setAddDoorErr("Code, name, and building are all required.");
      return;
    }
    try {
      await api.createDoor({
        ...newDoor,
        plug_labels: newDoor.category === "access_service"
          ? plugLabels.map((l) => l.trim()).filter(Boolean)
          : [],
      });
      setNewDoor({
        code: "", name: "", building: "", floor: "", fail_mode: "secure",
        category: activeTab === "access" ? "access_service" : "critical",
        ac_enabled: false, light_enabled: false,
      });
      setPlugLabels([]);
      setShowAddDoor(false);
      await refresh();
    } catch (e) {
      setAddDoorErr(e.message);
    }
  }

  function addPlugLabelField() {
    setPlugLabels((labels) => [...labels, `Plug ${labels.length + 1}`]);
  }

  function updatePlugLabelField(index, value) {
    setPlugLabels((labels) => labels.map((l, i) => (i === index ? value : l)));
  }

  function removePlugLabelField(index) {
    setPlugLabels((labels) => labels.filter((_, i) => i !== index));
  }

  async function handleToggleAc(doorId, on) {
    try {
      await api.toggleAc(doorId, on);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleToggleLight(doorId, on) {
    try {
      await api.toggleLight(doorId, on);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleTogglePlug(doorId, plugId, on) {
    try {
      await api.togglePlug(doorId, plugId, on);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleAddPlug(doorId, label) {
    try {
      await api.addPlug(doorId, label);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleDeletePlug(doorId, plugId) {
    try {
      await api.deletePlug(doorId, plugId);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  // Admin-only manual/testing stand-in for a real occupancy sensor (see
  // api/client.js's setOccupancy) — once that hardware exists this button
  // goes away and Door.occupied only ever changes over MQTT.
  async function handleSetOccupancy(doorId, occupied) {
    try {
      await api.setOccupancy(doorId, occupied);
      await refresh();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function handleImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportErr(null);
    setImportResult(null);
    setImportBusy(true);
    try {
      const result = await api.importDoors(file);
      setImportResult(result);
      await refresh();
      await loadBuildings();
    } catch (e) {
      setImportErr(e.message);
    } finally {
      setImportBusy(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  function openAddDoor() {
    setShowAddDoor(true);
    setAddDoorErr(null);
    setPlugLabels([]);
    setNewDoor((d) => ({
      ...d,
      category: activeTab === "access" ? "access_service" : "critical",
      // Pre-fill with the building currently drilled into (Access Service
      // tab only) so "+ Add Room" from inside a building doesn't silently
      // drop back to "no building selected" — a real navigation-path gap
      // found during the Stage B hardening pass.
      building: activeTab === "access" && buildingFilter ? buildingFilter : d.building,
      ac_enabled: false, light_enabled: false,
    }));
  }

  function selectTab(key) {
    setActiveTab(key);
    setShowAddDoor(false);
    setAddDoorErr(null);
    setDoorSearch("");
    setBuildingFilter("");
    setPlugLabels([]);
    setSidebarMobileOpen(false);
  }

  // Sidebar's Academic Administration contextual module clicks. Deliberately
  // mirrors AcademicAdmin.jsx's own (now-removed) internal goToSection: reset
  // whichever deeper ids don't belong to the destination section, then bump
  // aaNavRevision so AcademicAdmin.jsx's existing browser-back/forward resync
  // effect (see its comment) picks up this "externally" driven change the
  // same way it already does for popstate — no new plumbing needed.
  function goToAcademicSection(key) {
    setAaSection(key);
    if (key !== "colleges") {
      setAaCollegeId(null);
      setAaDepartmentId(null);
    }
    if (key !== "doctors" && key !== "tas") setAaStaffId(null);
    if (key !== "courses") setAaCourseId(null);
    setAaNavRevision((n) => n + 1);
    setSidebarMobileOpen(false);
  }

  // Global Search result navigation — maps a SearchResultOut (see
  // routers/search.py) onto the exact same hash-based deep-link state every
  // other navigation path in this file already writes to. GlobalSearch.jsx
  // itself never touches window.location.hash; this is the one place that
  // translates "the user picked a search result" into real navigation,
  // consistent with every other onSelect-style callback in this component.
  function goToSearchResult(result) {
    if (result.nav_action === "open_zone" && result.nav_action_id != null) {
      // Zone focus has no persisted hash param of its own anywhere in this
      // app yet (see openZone above) — reusing that exact existing,
      // already-accepted non-persistent mechanism rather than inventing a
      // new one just for search.
      openZone(result.nav_action_id);
      return;
    }
    const p = result.nav_params || {};
    setActiveTab(result.nav_tab);
    setShowAddDoor(false);
    setAddDoorErr(null);
    setDoorSearch("");
    setBuildingFilter(p.building || "");
    setPlugLabels([]);
    setRoomProfileId(p.room ? Number(p.room) : null);
    setInvestigatingEventId(p.investigate ? Number(p.investigate) : null);
    if (result.nav_tab === "academic") {
      setAaSection(p.aa_section || "overview");
      setAaCollegeId(p.aa_college ? Number(p.aa_college) : null);
      setAaDepartmentId(p.aa_department ? Number(p.aa_department) : null);
      setAaStaffId(p.aa_staff ? Number(p.aa_staff) : null);
      setAaCourseId(p.aa_course ? Number(p.aa_course) : null);
      setAaNavRevision((n) => n + 1);
    }
    setSidebarMobileOpen(false);
  }

  // Command Palette v1 — the registry is rebuilt from the same selectTab /
  // goToAcademicSection functions above plus the two existing safe execute
  // API calls; this is not a second navigation or authorization system, just
  // a different rendering surface over the same handlers. Execute commands
  // are only ever included in the array for canOverride (admin) users —
  // matching every other admin-only affordance in this file — but the
  // backend's own require_admin dependency on both endpoints remains the
  // real enforcement point regardless of what this array contains.
  // Memoized so this array keeps a stable identity across Dashboard's own
  // frequent re-renders (e.g. the 5s doors/alerts poll) — CommandPalette
  // resets its keyboard selection on a genuine filter-text change only, and
  // a commands array that churned identity on every unrelated render would
  // undermine that. selectTab/goToAcademicSection/api.* are stable enough
  // (they only ever call setState setters, never read closed-over state) to
  // safely omit from the dependency array.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const commandPaletteCommands = useMemo(
    () =>
      canOverride
        ? [
            ...buildNavigationCommands({ selectTab, goToAcademicSection }),
            ...buildExecuteCommands({
              runAutomationOnce: api.runAutomationOnce,
              runCheckoutSweep: api.runCheckoutSweep,
            }),
          ]
        : [],
    [canOverride]
  );

  const visibleDoors = (canOverride
    ? doors.filter((d) => d.category === (activeTab === "access" ? "access_service" : "critical"))
    : doors // instructors/doctors only ever see the doors assigned to them
  )
    .filter((d) => (activeTab === "access" && buildingFilter ? d.building === buildingFilter : true))
    .filter((d) => {
      const q = doorSearch.trim().toLowerCase();
      if (!q) return true;
      return (
        d.name.toLowerCase().includes(q) ||
        d.code.toLowerCase().includes(q) ||
        d.building.toLowerCase().includes(q)
      );
    });

  return (
    <div className="dashboard">
      <header className="topbar">
        <div className="topbar-brand">
          {/* Narrow-width menu button — opens the sidebar drawer. Admin-only,
              same as the sidebar itself; hidden entirely above the drawer
              breakpoint via CSS (see .sidebar-menu-btn in App.css), so it
              never appears as a second way to do something the always-visible
              desktop sidebar already does. */}
          {canOverride && (
            <button
              type="button"
              className="sidebar-menu-btn"
              aria-label="Open navigation menu"
              aria-expanded={sidebarMobileOpen}
              aria-controls="app-sidebar-nav"
              onClick={() => setSidebarMobileOpen(true)}
            >
              <span />
              <span />
              <span />
            </button>
          )}
          <img src="/aiu-logo.png" alt="AIU" className="topbar-logo" />
          <h1>Smart Access Control &mdash; Admin Dashboard</h1>
        </div>
        <div className="topbar-user">
          {/* Global Search lives in the institutional header, next to
              account controls — admin-only because it navigates through the
              tab/hash-based app shell (Sidebar/System Home/WorkspaceHeader)
              that only renders for canOverride; the non-admin dashboard
              below (!canOverride) is a deliberately separate, simpler view
              with no tabs to search into. */}
          {canOverride && <GlobalSearch onSelectResult={goToSearchResult} />}
          {canOverride && <CommandPalette commands={commandPaletteCommands} />}
          <AccountMenu />
          <button className="secondary" onClick={logout}>Sign out</button>
        </div>
      </header>

      <div className={canOverride ? "shell-body" : undefined}>
        {canOverride && (
          <Sidebar
            domains={DOMAINS}
            activeDomain={activeDomain}
            contextualItems={sidebarItems}
            isHome={activeTab === "home"}
            onHome={() => selectTab("home")}
            onSelectDomain={(d) => selectTab(d.tabs[0])}
            mobileOpen={sidebarMobileOpen}
            onCloseMobile={() => setSidebarMobileOpen(false)}
          />
        )}

      <main>
        {err && <div className="form-error">{err}</div>}

        <AlertBanner alerts={alerts} onResolve={handleResolve} canResolve={canOverride} />

        {/* System Home IS the domain selector (its own cards, below) — the
            sidebar's workspace list is the same set, so the choice never
            appears twice (the old top-of-page domain button row this comment
            used to describe is gone; Sidebar.jsx replaced it). Once a domain
            is entered, this shared WorkspaceHeader is the "where am I / way
            back" control for title + breadcrumb — Academic Administration is
            excluded here because it renders its own WorkspaceHeader
            internally (AcademicAdmin.jsx); showing this one too would
            duplicate it. Module-level switching (Security's Main Doors /
            Access Service / Access Events, Academic's six sections) now
            lives solely in the sidebar's contextual module list — the
            .domain-subnav row that used to repeat it here has been removed. */}
        {canOverride && activeDomain && activeDomain.key !== "academic" && (
          <WorkspaceHeader
            title={activeDomain.label}
            subtitle={activeDomain.description}
            crumbs={[
              {
                label: ADMIN_TABS.find((t) => t.key === activeTab)?.label || activeDomain.label,
                // Only clickable once there's somewhere for it to go back to
                // (out of a building drill-down) — otherwise it's already
                // the current page, same rule Academic Administration's own
                // multi-level breadcrumb follows.
                onClick: isRoomTab && buildingFilter ? () => setBuildingFilter("") : undefined,
              },
              // Building-level context used to be its own separate
              // Breadcrumb with a different root ("Access Service" instead
              // of "Home"), which read as a second, disconnected breadcrumb
              // system. Folding it into this one — the same single
              // Home-rooted breadcrumb every other workspace already uses —
              // is the fix; the segment itself (which building) is unchanged.
              ...(isRoomTab && buildingFilter ? [{ label: buildingFilter }] : []),
            ]}
            onHome={() => selectTab("home")}
          />
        )}

        {canOverride && activeTab === "home" && (
          <SystemHome
            domains={DOMAINS}
            onSelect={(d) => selectTab(d.tabs[0])}
            onSelectTab={selectTab}
            onInvestigateEvent={setInvestigatingEventId}
            doorCount={doors.length}
            unresolvedAlertCount={alerts.length}
            buildingCount={buildings.length}
          />
        )}

        {canOverride && isDoorTab && (
          <>
            <section style={{ margin: "16px 0" }}>
              {!showAddDoor ? (
                <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                  <button className="secondary" onClick={openAddDoor}>
                    {isRoomTab ? "+ Add Room" : "+ Add Door"}
                  </button>
                  <label className="secondary" style={{ display: "inline-block", cursor: "pointer" }}>
                    {importBusy ? "Importing…" : "Import from Excel"}
                    <input
                      ref={importInputRef}
                      type="file"
                      accept=".xlsx,.xlsm"
                      onChange={handleImportFile}
                      disabled={importBusy}
                      style={{ display: "none" }}
                    />
                  </label>
                </div>
              ) : (
                <form
                  onSubmit={handleAddDoor}
                  style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "flex-start" }}
                >
                  <input
                    placeholder="Code (e.g. LAB1)"
                    value={newDoor.code}
                    onChange={(e) => setNewDoor({ ...newDoor, code: e.target.value.toUpperCase() })}
                  />
                  <input
                    placeholder="Name (e.g. Lab 1)"
                    value={newDoor.name}
                    onChange={(e) => setNewDoor({ ...newDoor, name: e.target.value })}
                  />
                  <select
                    value={newDoor.building}
                    onChange={(e) => setNewDoor({ ...newDoor, building: e.target.value })}
                  >
                    <option value="">Select a building&hellip;</option>
                    {buildings.map((b) => (
                      <option key={b.building_id} value={b.name}>{b.name}</option>
                    ))}
                  </select>
                  {buildings.length === 0 && (
                    <span className="hint" style={{ marginTop: 0 }}>
                      No buildings yet — use "Manage buildings" in the account menu first.
                    </span>
                  )}
                  <input
                    placeholder="Floor (e.g. Ground, 1, 2)"
                    value={newDoor.floor}
                    onChange={(e) => setNewDoor({ ...newDoor, floor: e.target.value })}
                    style={{ width: "120px" }}
                  />
                  <select
                    value={newDoor.fail_mode}
                    onChange={(e) => setNewDoor({ ...newDoor, fail_mode: e.target.value })}
                  >
                    <option value="secure">fail-secure</option>
                    <option value="safe">fail-safe</option>
                  </select>
                  <select
                    value={newDoor.category}
                    onChange={(e) => setNewDoor({ ...newDoor, category: e.target.value })}
                  >
                    <option value="critical">Main / critical door</option>
                    <option value="access_service">Access service (hall / section room)</option>
                  </select>
                  {newDoor.category === "access_service" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px", width: "100%" }}>
                      <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
                        <label style={{ display: "flex", gap: "6px", alignItems: "center", fontSize: "13px" }}>
                          <input
                            type="checkbox"
                            checked={newDoor.ac_enabled}
                            onChange={(e) => setNewDoor({ ...newDoor, ac_enabled: e.target.checked })}
                          />
                          AC control
                        </label>
                        <label style={{ display: "flex", gap: "6px", alignItems: "center", fontSize: "13px" }}>
                          <input
                            type="checkbox"
                            checked={newDoor.light_enabled}
                            onChange={(e) => setNewDoor({ ...newDoor, light_enabled: e.target.checked })}
                          />
                          Light control
                        </label>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                        <span className="hint" style={{ marginTop: 0 }}>
                          Plugs (each with its own current-sensor cutoff once wired up):
                        </span>
                        {plugLabels.map((label, i) => (
                          <div key={i} style={{ display: "flex", gap: "6px" }}>
                            <input
                              placeholder="Plug label"
                              value={label}
                              onChange={(e) => updatePlugLabelField(i, e.target.value)}
                            />
                            <button type="button" className="danger" onClick={() => removePlugLabelField(i)}>
                              Remove
                            </button>
                          </div>
                        ))}
                        <button type="button" className="secondary" onClick={addPlugLabelField} style={{ alignSelf: "flex-start" }}>
                          + Add plug
                        </button>
                      </div>
                    </div>
                  )}
                  <button type="submit">Save</button>
                  <button type="button" className="secondary" onClick={() => { setShowAddDoor(false); setAddDoorErr(null); setPlugLabels([]); }}>
                    Cancel
                  </button>
                  {addDoorErr && <div className="form-error">{addDoorErr}</div>}
                </form>
              )}
            </section>

            {importErr && <div className="form-error">{importErr}</div>}
            {importResult && (
              <div className="form-success" style={{ marginBottom: "16px" }}>
                Imported {importResult.created} door{importResult.created === 1 ? "" : "s"}.
                {importResult.skipped?.length > 0 && (
                  <> {importResult.skipped.length} skipped (already existed).</>
                )}
                {importResult.errors?.length > 0 && (
                  <> {importResult.errors.length} row{importResult.errors.length === 1 ? "" : "s"} had errors.</>
                )}
                {(importResult.skipped?.length > 0 || importResult.errors?.length > 0) && (
                  <ul style={{ margin: "6px 0 0", paddingLeft: "18px" }}>
                    {[...importResult.skipped, ...importResult.errors].map((line, i) => (
                      <li key={i} style={{ fontSize: "12px" }}>{line}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {isRoomTab && !buildingFilter ? (
              // Access Service is Building-first: pick a building, then see
              // its rooms — rather than one flat list of every room in every
              // building. All counts on the cards come from the same
              // doors/alerts this page already polls (see BuildingGrid.jsx).
              <BuildingGrid
                buildings={buildings}
                doors={doors}
                alerts={alerts}
                onSelect={(name) => setBuildingFilter(name)}
              />
            ) : (
              <>
                {/* Which building this is now lives in the WorkspaceHeader
                    breadcrumb above ("Home / Access Service / <Building>") —
                    see its crumbs — instead of a second, separately-rooted
                    breadcrumb repeating "Access Service" here. */}

                <div className="door-search">
                  <input
                    type="search"
                    placeholder="Search doors by name, code, or building…"
                    value={doorSearch}
                    onChange={(e) => setDoorSearch(e.target.value)}
                  />
                </div>

                <section className="door-grid">
                  {visibleDoors.map((door) => (
                    <DoorCard
                      key={door.door_id}
                      door={door}
                      canOverride={canOverride}
                      onOverride={handleOverride}
                      canRequestAccess={false}
                      onRequestAccess={handleRequestAccess}
                      onSetStatus={handleSetStatus}
                      onViewLogs={setSelectedDoorId}
                      onDelete={handleDeleteDoor}
                      onOpenRoom={openRoomProfile}
                    />
                  ))}
                  {visibleDoors.length === 0 && (
                    <p className="muted">
                      {doorSearch.trim()
                        ? "No doors match your search."
                        : isRoomTab
                          ? 'No rooms in this building yet — use "+ Add Room" above.'
                          : 'No doors in this category yet — use "+ Add Door" above.'}
                    </p>
                  )}
                </section>

                {!isRoomTab && (
                  <LogsTable
                    logs={logs}
                    title={selectedDoorId ? `Access Events — Door #${selectedDoorId}` : "Select a door to view history"}
                  />
                )}
              </>
            )}
          </>
        )}

        {canOverride && activeTab === "command" && (
          <CommandCenter onOpenDoor={openRoomProfile} onInvestigateEvent={setInvestigatingEventId} />
        )}

        {canOverride && activeTab === "events" && (
          <AccessEventsPage onInvestigateEvent={setInvestigatingEventId} />
        )}

        {canOverride && activeTab === "smart" && (
          <SmartBuildingDashboard
            canControl={canOverride}
            onInvestigateEvent={setInvestigatingEventId}
            focusZoneId={focusZoneId}
            focusZoneToken={focusZoneToken}
            onZoneOpenChange={setSmartZoneId}
          />
        )}

        {canOverride && activeTab === "academic" && (
          <AcademicAdmin
            suggestEmail={suggestEmail}
            navState={{ section: aaSection, collegeId: aaCollegeId, departmentId: aaDepartmentId, staffId: aaStaffId, courseId: aaCourseId }}
            navRevision={aaNavRevision}
            onNavStateChange={(s) => {
              setAaSection(s.section);
              setAaCollegeId(s.collegeId);
              setAaDepartmentId(s.departmentId);
              setAaStaffId(s.staffId);
              setAaCourseId(s.courseId);
            }}
            onHome={() => selectTab("home")}
          />
        )}

        {!canOverride && (
          <>
            {doors.length > 0 && (
              <div className="door-search">
                <input
                  type="search"
                  placeholder="Search doors by name, code, or building…"
                  value={doorSearch}
                  onChange={(e) => setDoorSearch(e.target.value)}
                />
              </div>
            )}
            <section className="door-grid">
              {visibleDoors.map((door) => (
                <DoorCard
                  key={door.door_id}
                  door={door}
                  canOverride={false}
                  onOverride={handleOverride}
                  canRequestAccess={canRequestAccess}
                  onRequestAccess={handleRequestAccess}
                  onSetStatus={handleSetStatus}
                  onViewLogs={setSelectedDoorId}
                  onOpenRoom={openRoomProfile}
                />
              ))}
              {doors.length === 0 && (
                <p className="muted">No doors have been assigned to you yet — ask an admin.</p>
              )}
              {doors.length > 0 && visibleDoors.length === 0 && (
                <p className="muted">No doors match your search.</p>
              )}
            </section>
          </>
        )}
      </main>
      </div>

      {roomProfileDoor && (
        <RoomProfile
          door={roomProfileDoor}
          logs={roomLogs}
          onClose={closeRoomProfile}
          canOverride={canOverride}
          canRequestAccess={canRequestAccess}
          onOverride={handleOverride}
          onRequestAccess={handleRequestAccess}
          canControlRoom={canControlRoom}
          onToggleAc={handleToggleAc}
          onToggleLight={handleToggleLight}
          onTogglePlug={handleTogglePlug}
          onAddPlug={canOverride ? handleAddPlug : undefined}
          onDeletePlug={canOverride ? handleDeletePlug : undefined}
          onSetOccupancy={canOverride ? handleSetOccupancy : undefined}
          onAuthorizationChecked={() => refreshRoomLogs(roomProfileId)}
          onInvestigateEvent={setInvestigatingEventId}
          onOpenZone={openZone}
        />
      )}

      {roomProfileId != null && !roomProfileDoor && doorsLoaded && (
        // A deep-linked/stale room id that doesn't resolve against this
        // user's own visible door list — could be deleted, or simply not
        // authorized for this account (the /api/doors response is already
        // scoped server-side, so "not in the list" covers both honestly
        // without a second lookup that could leak which reason applies).
        <div className="room-profile-overlay" onClick={closeRoomProfile}>
          <div className="room-profile-card" onClick={(e) => e.stopPropagation()}>
            <div className="room-profile-header">
              <h2>Room not available</h2>
              <button className="secondary" onClick={closeRoomProfile}>Close</button>
            </div>
            <p className="muted">
              This room doesn't exist, or you don't have access to it.
            </p>
          </div>
        </div>
      )}

      {investigatingEventId != null && (
        <InvestigationPanel
          eventId={investigatingEventId}
          canManageStatus={canOverride}
          onClose={() => setInvestigatingEventId(null)}
        />
      )}
    </div>
  );
}
