import { useEffect, useState } from "react";
import { api } from "../../api/client";
import RoomIntelPanel from "./RoomIntelPanel";
import { HealthPill } from "./Badges";

// Abstract schematic of the REAL Building -> Floor -> Room hierarchy. Every
// tile is a Zone that exists in the database; tile colour is the derived
// Room Health (never an invented value). Clicking opens the room detail.
export default function CampusMap({ onOpenRoomProfile }) {
  const [map, setMap] = useState(null);
  const [err, setErr] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let live = true;
    const load = () => api.campusMap().then((m) => live && (setMap(m), setErr(null))).catch((e) => live && setErr(e.message));
    load();
    const id = setInterval(load, 30000);
    return () => { live = false; clearInterval(id); };
  }, []);

  if (err) return <div className="form-error">{err}</div>;
  if (!map) return <p className="muted">Loading campus map…</p>;
  if (map.buildings.length === 0) return <p className="muted">No rooms (zones) exist yet — create zones in Smart Building to populate the map.</p>;

  return (
    <div className="ph-map">
      <div className="ph-legend" aria-label="Legend">
        {["HEALTHY", "WARNING", "DEGRADED", "CRITICAL", "OFFLINE", "UNKNOWN"].map((s) => <HealthPill key={s} state={s} />)}
      </div>
      {map.buildings.map((b) => (
        <section key={b.name} className="ph-card" aria-label={`Building ${b.name}`}>
          <h3>{b.name}</h3>
          {b.floors.map((f) => (
            <div key={f.floor} className="ph-floor">
              <div className="ph-floor-label">Floor {f.floor}</div>
              <div className="ph-rooms">
                {f.rooms.map((r) => (
                  <button
                    type="button" key={r.zone_id} className="ph-room" data-state={r.health}
                    onClick={() => setSelected(r)}
                    aria-label={`${r.name}, ${r.health}, ${r.occupancy_state === "UNAVAILABLE" ? "occupancy unavailable" : `${r.occupancy} people`}`}
                  >
                    <span className="ph-room-name">{r.name}</span>
                    <span className="ph-room-sub">
                      {r.health} · {r.occupancy_state === "UNAVAILABLE" ? "occ. n/a" : `${r.occupancy}${r.capacity != null ? `/${r.capacity}` : ""}`}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}
      {selected && <RoomIntelPanel room={selected} onClose={() => setSelected(null)} onOpenRoomProfile={onOpenRoomProfile} />}
    </div>
  );
}
