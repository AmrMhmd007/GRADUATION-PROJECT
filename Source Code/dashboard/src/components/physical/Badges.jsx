// REAL / SIMULATED / UNAVAILABLE badge — the UI never presents simulator
// output as real, nor an absent sensor as a zero.
export function SourceBadge({ source }) {
  const s = source || "UNAVAILABLE";
  return <span className="ph-badge" data-kind={s}>{s}</span>;
}

export function HealthPill({ state }) {
  return <span className="ph-pill" data-state={state}>{state}</span>;
}

export function Sparkline({ points, label }) {
  // points: [{t, v}] with v possibly null (gaps are NOT drawn as zero).
  const vals = points.filter((p) => p.v != null);
  if (vals.length < 2) return <p className="muted ph-small">Not enough readings for a chart yet.</p>;
  const w = 320;
  const h = 70;
  const max = Math.max(...vals.map((p) => p.v), 1);
  const t0 = points[0].t;
  const span = Math.max(points[points.length - 1].t - t0, 1);
  const segs = [];
  let cur = [];
  points.forEach((p) => {
    if (p.v == null) {
      if (cur.length) segs.push(cur);
      cur = [];
    } else {
      cur.push(`${(((p.t - t0) / span) * (w - 8) + 4).toFixed(1)},${(h - 6 - (p.v / max) * (h - 12)).toFixed(1)}`);
    }
  });
  if (cur.length) segs.push(cur);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="ph-spark" role="img" aria-label={label}>
      {segs.map((s, i) => (
        <polyline key={i} points={s.join(" ")} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      ))}
    </svg>
  );
}
