import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../../api/client";
import { SOURCES, buildBuildingIndex, drawableFootprints, referencePoint, summariseLive } from "./campusGeo";

// Basemaps are optional and licensed by the deployer, never bundled. With
// neither configured the map shows a plain dark canvas.
const SAT_URL = import.meta.env.VITE_SATELLITE_TILE_URL || "";
const SAT_ATTR = import.meta.env.VITE_SATELLITE_ATTRIBUTION || "";
const CLEAN_URL = import.meta.env.VITE_CLEAN_TILE_URL || "";
const CLEAN_ATTR = import.meta.env.VITE_CLEAN_ATTRIBUTION || "";

const STATUS_LABEL = { VERIFIED: "Verified", APPROXIMATE: "Approximate", UNMAPPED: "Unmapped" };

export default function CampusTwinMap() {
  const el = useRef(null);
  const mapRef = useRef(null);
  const layers = useRef({});
  const [buildings, setBuildings] = useState(null);
  const [campusMap, setCampusMap] = useState(null);
  const [liveErr, setLiveErr] = useState(null);
  const [err, setErr] = useState(null);
  const [query, setQuery] = useState("");
  const [selectedKey, setSelectedKey] = useState(null);
  const [base, setBase] = useState(CLEAN_URL ? "clean" : "none");
  const [showFootprints, setShowFootprints] = useState(true);
  const [showRef, setShowRef] = useState(true);

  const footprints = useMemo(() => drawableFootprints(), []);
  const ref = useMemo(() => referencePoint(), []);
  const rows = useMemo(() => buildBuildingIndex(buildings), [buildings]);
  const selected = rows.find((r) => r.key === selectedKey) || null;
  const matches = rows.filter((r) => r.name.toLowerCase().includes(query.trim().toLowerCase()));
  const live = selected?.backendName ? summariseLive(campusMap, selected.backendName) : null;

  useEffect(() => {
    let alive = true;
    api.listBuildings().then((b) => alive && setBuildings(b)).catch((e) => alive && (setErr(e.message), setBuildings([])));
    api.campusMap().then((m) => alive && setCampusMap(m)).catch((e) => alive && setLiveErr(e.message));
    return () => { alive = false; };
  }, []);

  // Create the map once.
  useEffect(() => {
    const center = ref ? [ref.lat, ref.lng] : [30.8116875, 28.9298125];
    const map = L.map(el.current, { center, zoom: 16, minZoom: 3, maxZoom: 20, zoomControl: true, attributionControl: true, preferCanvas: true });
    map.attributionControl.setPrefix("Leaflet");
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; layers.current = {}; };
  }, [ref]);

  // Basemap: only a configured, licensed provider is ever loaded.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layers.current.base?.remove();
    layers.current.base = null;
    const cfg = base === "satellite" ? [SAT_URL, SAT_ATTR] : base === "clean" ? [CLEAN_URL, CLEAN_ATTR] : null;
    if (cfg && cfg[0]) {
      layers.current.base = L.tileLayer(cfg[0], { attribution: cfg[1], maxZoom: 20 }).addTo(map);
    }
  }, [base]);

  // Footprint overlay (VERIFIED polygons only) and selection highlight.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layers.current.fp?.remove();
    layers.current.fp = null;
    if (!showFootprints || footprints.length === 0) return;
    const group = L.geoJSON(footprints, {
      style: (f) => {
        const sel = selected?.feature?.id === f.id;
        return { color: sel ? "#ffffff" : "#8fa8ff", weight: sel ? 3 : 1.5, fillColor: sel ? "#a81a1f" : "#4c5cc4", fillOpacity: sel ? 0.55 : 0.3 };
      },
      onEachFeature: (f, layer) => {
        layer.bindTooltip(f.properties.name, { sticky: true, className: "twin-tip" });
        layer.on("click", () => setSelectedKey(rows.find((r) => r.feature?.id === f.id)?.key ?? f.id));
      },
    }).addTo(map);
    layers.current.fp = group;
  }, [footprints, showFootprints, selected, rows]);

  // Campus reference marker (approximate, clearly styled as such).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ref) return;
    layers.current.ref?.remove();
    layers.current.ref = null;
    if (!showRef) return;
    layers.current.ref = L.circleMarker([ref.lat, ref.lng], { radius: 7, color: "#f2c14e", weight: 2, dashArray: "3 3", fillOpacity: 0.15 })
      .bindTooltip("Approximate campus reference (not surveyed)", { className: "twin-tip" })
      .addTo(map);
  }, [ref, showRef]);

  const choose = (row) => {
    setSelectedKey(row.key);
    if (row.mapped && mapRef.current) {
      mapRef.current.flyToBounds(L.geoJSON(row.feature).getBounds(), { maxZoom: 19, duration: 0.6 });
    }
  };

  const unmappedCount = rows.filter((r) => !r.mapped).length;
  const satOn = !!SAT_URL;

  return (
    <div className="twin">
      <aside className="twin-side" aria-label="Buildings">
        <input
          type="search" className="twin-search" placeholder="Search buildings…" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Search buildings by name"
        />
        <div className="twin-count">{rows.length} building{rows.length === 1 ? "" : "s"} · {unmappedCount} unmapped</div>
        <ul className="twin-list">
          {matches.map((r) => (
            <li key={r.key}>
              <button type="button" className={r.key === selectedKey ? "twin-row active" : "twin-row"} onClick={() => choose(r)}>
                <span>{r.name}</span>
                <span className={`twin-badge ${r.status.toLowerCase()}`}>{r.mapped ? "Mapped" : STATUS_LABEL[r.status] === "Approximate" ? "Approximate" : "Unmapped"}</span>
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="twin-empty">No building matches “{query}”.</li>}
        </ul>
        {err && <div className="twin-note">Backend buildings unavailable: {err}</div>}
      </aside>

      <div className="twin-stage">
        <div ref={el} className="twin-map" role="application" aria-label="Campus map" />
        {footprints.length === 0 && (
          <div className="twin-banner" role="status">
            No verified building outlines yet. The map shows only an approximate campus reference point; buildings are listed as unmapped until outlines are verified from an official source.
          </div>
        )}
        <div className="twin-controls" aria-label="Layers">
          <div className="twin-ctl-title">Basemap</div>
          <label><input type="radio" name="base" checked={base === "none"} onChange={() => setBase("none")} /> Plain (no tiles)</label>
          <label className={CLEAN_URL ? "" : "disabled"} title={CLEAN_URL ? "" : "Set VITE_CLEAN_TILE_URL to a licensed provider"}>
            <input type="radio" name="base" disabled={!CLEAN_URL} checked={base === "clean"} onChange={() => setBase("clean")} /> Clean map
          </label>
          <label className={satOn ? "" : "disabled"} title={satOn ? "" : "Set VITE_SATELLITE_TILE_URL and VITE_SATELLITE_ATTRIBUTION for a licensed provider"}>
            <input type="radio" name="base" disabled={!satOn} checked={base === "satellite"} onChange={() => setBase("satellite")} /> Satellite
          </label>
          {!satOn && <div className="twin-hint">Satellite disabled: no licensed provider configured.</div>}
          <div className="twin-ctl-title">Overlays</div>
          <label><input type="checkbox" checked={showFootprints} onChange={(e) => setShowFootprints(e.target.checked)} /> Building footprints ({footprints.length})</label>
          <label><input type="checkbox" checked={showRef} onChange={(e) => setShowRef(e.target.checked)} /> Reference point</label>
          <div className="twin-legend" aria-label="Legend">
            <span><i className="sw verified" /> Verified footprint</span>
            <span><i className="sw approx" /> Approximate point</span>
            <span><i className="sw unmapped" /> Unmapped (not drawn)</span>
          </div>
        </div>

        {selected && (
          <section className="twin-detail" aria-label={`Details for ${selected.name}`}>
            <button type="button" className="twin-close" onClick={() => setSelectedKey(null)} aria-label="Close details">×</button>
            <h3>{selected.name}</h3>
            <div className="twin-kv"><span>Geometry</span><b>{STATUS_LABEL[selected.status]}{selected.feature ? ` · confidence ${selected.feature.properties.confidence}` : ""}</b></div>
            <div className="twin-kv"><span>Backend record</span><b>{selected.backendId != null ? `Building #${selected.backendId}` : "none linked"}</b></div>
            {selected.feature?.properties.notes && <p className="twin-notes">{selected.feature.properties.notes}</p>}
            {!selected.mapped && <p className="twin-notes">Location not mapped — no verified outline exists, so nothing is drawn.</p>}
            <div className="twin-live">
              <div className="twin-ctl-title">Live status</div>
              {selected.backendName == null && <p className="twin-unavail">Unavailable — not linked to a backend building.</p>}
              {live && !live.available && <p className="twin-unavail">Unavailable — {liveErr ? `${liveErr}` : live.reason}</p>}
              {live?.available && (
                <>
                  <div className="twin-kv"><span>Rooms</span><b>{live.rooms}</b></div>
                  <div className="twin-kv"><span>Occupancy</span><b>{live.occupancy == null ? "Unavailable" : `${live.occupancy} (${live.reporting}/${live.rooms} rooms reporting)`}</b></div>
                  <div className="twin-kv"><span>Room health</span><b>{Object.entries(live.health).map(([k, v]) => `${k} ${v}`).join(" · ")}</b></div>
                  <div className="twin-note">Energy: unavailable here (not part of this read model).</div>
                </>
              )}
            </div>
          </section>
        )}
        <details className="twin-sources">
          <summary>Sources &amp; attribution</summary>
          <ul>
            {SOURCES.map((s) => (
              <li key={s.id}><b>{s.title}</b>{s.accessed ? ` (accessed ${s.accessed})` : " (not retrieved)"} — {s.provides}</li>
            ))}
            <li>Basemap tiles: {SAT_URL || CLEAN_URL ? "provider attribution shown on the map" : "none configured"}.</li>
          </ul>
        </details>
      </div>
    </div>
  );
}
