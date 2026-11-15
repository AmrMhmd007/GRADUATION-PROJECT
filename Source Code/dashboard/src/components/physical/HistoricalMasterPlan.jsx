import { useState } from "react";
import schematicRaw from "../../data/aiu-master-plan-schematic.json?raw";
import inventoryRaw from "../../data/aiu-master-plan-inventory.json?raw";

// Abstract sketch of the October 2020 master plan. Units are page units, NOT
// geographic coordinates; nothing here feeds the campus map or the GeoJSON.
const schematic = JSON.parse(schematicRaw);
const inventory = JSON.parse(inventoryRaw);
const NAME = Object.fromEntries(inventory.facilities.map((f) => [f.id, f.original_name]));

export default function HistoricalMasterPlan() {
  const [sel, setSel] = useState(null);
  const block = schematic.blocks.find((b) => b.id === sel) || null;
  const outline = schematic.site_outline_page_units.map((p) => p.join(",")).join(" ");
  return (
    <div className="hmp">
      <div className="hmp-banner" role="note">{schematic.banner}</div>
      <p className="hmp-sub">
        Sketch of the October 2020 master plan (printed page 6). Not current, not surveyed, no scale or north. Facilities shown are planned; none is confirmed built.
      </p>
      <div className="hmp-body">
        <svg viewBox="0 0 100 100" className="hmp-svg" role="img" aria-label="Schematic of the historical master plan, not geographically verified">
          <polygon points={outline} className="hmp-site" />
          {schematic.blocks.map((b) => (
            <rect
              key={b.id} x={b.x - b.w / 2} y={b.y - b.h / 2} width={b.w} height={b.h} rx="0.8"
              fill={b.fill} fillOpacity={b.labels.length ? 0.85 : 0.35}
              className={b.id === sel ? "hmp-block sel" : "hmp-block"}
              strokeDasharray={b.placement_confidence === "LOW" ? "1.2 0.8" : undefined}
              onClick={() => b.labels.length && setSel(b.id)}
            >
              <title>{b.labels.length ? b.labels.map((l) => NAME[l]).join(" / ") : "No label on the plan"}</title>
            </rect>
          ))}
          <text x="50" y="6" className="hmp-mark" textAnchor="middle">HISTORICAL — NOT GEOGRAPHICALLY VERIFIED</text>
        </svg>
        <aside className="hmp-side">
          <div className="twin-ctl-title">Labels as printed (23)</div>
          <ul className="hmp-list">
            {inventory.facilities.map((f) => (
              <li key={f.id}>
                <button type="button" className={block?.labels.includes(f.id) ? "twin-row active" : "twin-row"} onClick={() => setSel(f.schematic_block)}>
                  <span>{f.original_name}</span>
                </button>
              </li>
            ))}
          </ul>
          {block && (
            <p className="twin-notes">
              Block placement confidence: {block.placement_confidence}.
              {block.placement_confidence === "LOW" && " Several labels point into this cluster; the split between them is not recoverable (dashed outline)."}
            </p>
          )}
          <p className="twin-note">Dashed outline = uncertain label-to-block reading. Pale blocks had no label.</p>
        </aside>
      </div>
    </div>
  );
}
