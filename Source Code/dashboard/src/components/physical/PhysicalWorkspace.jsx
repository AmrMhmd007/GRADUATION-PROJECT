import { useState } from "react";
import CampusMap from "./CampusMap";
import OccupancyOverview from "./OccupancyOverview";
import DeviceFaultsAdmin from "./DeviceFaultsAdmin";
import FaceIdAdmin from "./FaceIdAdmin";

const TABS = [
  { key: "map", label: "Campus Map" },
  { key: "occupancy", label: "Occupancy" },
  { key: "faults", label: "Device Faults" },
  { key: "face", label: "Face ID" },
];

export default function PhysicalWorkspace({ onOpenRoomProfile }) {
  const [tab, setTab] = useState("map");
  return (
    <div className="ph-workspace">
      <div role="tablist" aria-label="Campus intelligence" className="ph-tabs">
        {TABS.map((t) => (
          <button
            key={t.key} type="button" role="tab" id={`ph-tab-${t.key}`} aria-selected={tab === t.key}
            aria-controls="ph-panel" className={tab === t.key ? "ph-tab active" : "ph-tab"} onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="ph-panel" role="tabpanel" aria-labelledby={`ph-tab-${tab}`}>
        {tab === "map" && <CampusMap onOpenRoomProfile={onOpenRoomProfile} />}
        {tab === "occupancy" && <OccupancyOverview />}
        {tab === "faults" && <DeviceFaultsAdmin />}
        {tab === "face" && <FaceIdAdmin />}
      </div>
    </div>
  );
}
