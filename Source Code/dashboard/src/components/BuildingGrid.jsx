// Stage B (Master UX pass) — Building-first step for the Access Service tab.
// Every number here is derived from the same `doors`/`alerts` arrays
// Dashboard.jsx already polls from the real backend (GET /api/doors,
// GET /api/alerts) — no new endpoint, no invented metric. A building with
// no access_service doors yet doesn't get a card (nothing to show).
export default function BuildingGrid({ buildings, doors, alerts, onSelect }) {
  const cards = buildings
    .map((b) => {
      const buildingDoors = doors.filter((d) => d.building === b.name);
      const rooms = buildingDoors.filter((d) => d.category === "access_service");
      const criticalDoors = buildingDoors.filter((d) => d.category === "critical");
      if (rooms.length === 0) return null; // nothing this tab would show for this building
      const doorIds = new Set(buildingDoors.map((d) => d.door_id));
      const buildingAlerts = alerts.filter((a) => a.door_id != null && doorIds.has(a.door_id));
      const onlineRooms = rooms.filter((d) => d.online).length;
      const unlockedRooms = rooms.filter((d) => d.online && !d.locked).length;
      return {
        building: b,
        roomCount: rooms.length,
        criticalDoorCount: criticalDoors.length,
        onlineRooms,
        unlockedRooms,
        alertCount: buildingAlerts.length,
      };
    })
    .filter(Boolean);

  if (cards.length === 0) {
    return <p className="muted">No rooms have been added yet — use "+ Add Room" above, or add a building first from the account menu.</p>;
  }

  return (
    <section className="building-grid">
      {cards.map(({ building, roomCount, criticalDoorCount, onlineRooms, unlockedRooms, alertCount }) => (
        <button
          type="button"
          key={building.building_id}
          className="building-card"
          onClick={() => onSelect(building.name)}
        >
          <h3>{building.name}</h3>
          <div className="building-card-stats">
            <div><span className="value">{roomCount}</span><span className="label">Room{roomCount === 1 ? "" : "s"}</span></div>
            <div><span className="value">{onlineRooms}</span><span className="label">Online</span></div>
            <div><span className="value">{unlockedRooms}</span><span className="label">Unlocked</span></div>
            {criticalDoorCount > 0 && (
              <div><span className="value">{criticalDoorCount}</span><span className="label">Main door{criticalDoorCount === 1 ? "" : "s"}</span></div>
            )}
          </div>
          {alertCount > 0 && (
            <div className="building-card-alert">{alertCount} unresolved alert{alertCount === 1 ? "" : "s"}</div>
          )}
        </button>
      ))}
    </section>
  );
}
