import { useMemo } from "react";

/**
 * Regulation pitch: 105m x 68m (UEFA category 1). The SVG uses those units
 * directly so line weights and penalty areas keep the correct proportions at
 * every container width. Formation rows drive the marker coordinates; no
 * hard-coded per-formation pixel layouts.
 */
export const PITCH_LENGTH = 105;
export const PITCH_WIDTH = 68;

const ROW_LABELS = {
  1: ["ST"],
  2: ["ST", "ST"],
  3: ["LW", "ST", "RW"],
  4: ["LW", "ST", "ST", "RW"],
  5: ["LWB", "LCB", "CB", "RCB", "RWB"],
};

const DEFENCE_LABELS = {
  2: ["LCB", "RCB"],
  3: ["LCB", "CB", "RCB"],
  4: ["LB", "LCB", "RCB", "RB"],
  5: ["LWB", "LCB", "CB", "RCB", "RWB"],
};

export function parseFormation(formation) {
  const rows = String(formation || "4-3-3")
    .split("-")
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => Number.isFinite(value) && value > 0);
  return rows.length > 0 ? rows : [4, 3, 3];
}

export function getFormationSlots(formation) {
  const rows = parseFormation(formation);
  const slots = [{ slot: "GK", x: PITCH_LENGTH / 2, y: 61.5, row: -1 }];
  const rowCount = rows.length;
  const top = 14.5;
  const bottom = 54;
  rows.forEach((count, rowIndex) => {
    const y = rowCount === 1 ? 34 : bottom - ((bottom - top) * rowIndex) / (rowCount - 1);
    const margin = count >= 5 ? 10 : 13;
    const span = PITCH_LENGTH - margin * 2;
    const labels = rowIndex === 0
      ? (DEFENCE_LABELS[count] || Array.from({ length: count }, (_, i) => `D${i + 1}`))
      : (ROW_LABELS[count] || Array.from({ length: count }, (_, i) => `M${i + 1}`));
    for (let index = 0; index < count; index += 1) {
      const x = count === 1 ? PITCH_LENGTH / 2 : margin + (span * index) / (count - 1);
      slots.push({ slot: labels[index] || `P${index + 1}`, x, y, row: rowIndex });
    }
  });
  return slots;
}

function PitchLines() {
  const line = "rgba(226, 255, 246, 0.4)";
  const thin = "rgba(226, 255, 246, 0.26)";
  return (
    <g fill="none" stroke={line} strokeWidth="0.34">
      <rect x="1" y="1" width="103" height="66" rx="0.4" />
      <line x1="1" y1="34" x2="104" y2="34" />
      <circle cx="52.5" cy="34" r="9.15" />
      <circle cx="52.5" cy="34" r="0.5" fill={line} stroke="none" />
      {/* Penalty areas: 40.32m wide, 16.5m deep. */}
      <rect x="22.34" y="1" width="40.32" height="16.5" />
      <rect x="22.34" y="50.5" width="40.32" height="16.5" />
      {/* Six-yard boxes: 18.32m wide, 5.5m deep. */}
      <rect x="30.84" y="1" width="18.32" height="5.5" />
      <rect x="30.84" y="61.5" width="18.32" height="5.5" />
      {/* Penalty spots 11m from the goal line. */}
      <circle cx="52.5" cy="12" r="0.45" fill={line} stroke="none" />
      <circle cx="52.5" cy="56" r="0.45" fill={line} stroke="none" />
      {/* Penalty arcs (radius 9.15m around the spot, clipped by the box). */}
      <path d="M 44.53 16.5 A 9.15 9.15 0 0 1 60.47 16.5" stroke={thin} />
      <path d="M 44.53 51.5 A 9.15 9.15 0 0 0 60.47 51.5" stroke={thin} />
      {/* Corner arcs. */}
      <path d="M 1 2.2 A 1.2 1.2 0 0 0 2.2 1" stroke={thin} />
      <path d="M 102.8 1 A 1.2 1.2 0 0 0 104 2.2" stroke={thin} />
      <path d="M 1 65.8 A 1.2 1.2 0 0 1 2.2 67" stroke={thin} />
      <path d="M 102.8 67 A 1.2 1.2 0 0 1 104 65.8" stroke={thin} />
      {/* Goals, drawn outside the touchline. */}
      <rect x="44.5" y="-1.2" width="16" height="2.2" stroke={thin} />
      <rect x="44.5" y="67" width="16" height="2.2" stroke={thin} />
    </g>
  );
}

function PlayerMarker({ slot, player, index, system = false }) {
  if (system) {
    return (
      <g>
        <title>{slot.slot}</title>
        <circle cx={slot.x} cy={slot.y} r="3.55" fill="rgba(5, 19, 16, 0.9)" stroke="rgba(69, 224, 212, 0.45)" strokeWidth="0.35" />
        <text x={slot.x} y={slot.y + 0.85} textAnchor="middle" fill="#6ff0e6" fontSize={slot.slot.length > 2 ? "2.05" : "2.4"} fontFamily="JetBrains Mono, monospace" fontWeight="600">{slot.slot}</text>
      </g>
    );
  }
  const name = player?.name || "Unassigned";
  const number = player?.number ?? player?.shirt_number ?? index + 1;
  const position = player?.position || player?.slot || slot.slot;
  const status = player?.status;
  const stroke = status === "missing" || !player
    ? "rgba(255, 138, 138, 0.45)"
    : status === "partial"
      ? "rgba(242, 194, 107, 0.55)"
      : "rgba(69, 224, 212, 0.6)";
  const fill = status === "missing" || !player ? "rgba(24, 12, 12, 0.88)" : "rgba(5, 19, 16, 0.92)";
  const shortName = name.length > 16 ? `${name.slice(0, 15)}…` : name;
  const labelWidth = Math.max(11, Math.min(25, shortName.length * 1.16));
  return (
    <g>
      <title>{`${slot.slot} · ${name}${player?.position ? ` · ${player.position}` : ""}${status ? ` · ${status}` : ""}`}</title>
      <circle cx={slot.x} cy={slot.y} r="3.35" fill={fill} stroke={stroke} strokeWidth="0.4" />
      <text x={slot.x} y={slot.y + 1.05} textAnchor="middle" fill={status === "missing" || !player ? "#ff8a8a" : "#6ff0e6"} fontSize="2.7" fontFamily="JetBrains Mono, monospace" fontWeight="600">{number}</text>
      <rect x={slot.x - labelWidth / 2} y={slot.y + 4.1} width={labelWidth} height="3.6" rx="1" fill="rgba(3, 10, 9, 0.78)" stroke="rgba(255,255,255,0.06)" strokeWidth="0.12" />
      <text x={slot.x} y={slot.y + 6.6} textAnchor="middle" fill="rgba(242, 245, 247, 0.92)" fontSize="1.95" fontFamily="Inter, sans-serif" fontWeight="500">{shortName}</text>
      <text x={slot.x} y={slot.y - 4.6} textAnchor="middle" fill="rgba(167, 178, 190, 0.75)" fontSize="1.55" fontFamily="JetBrains Mono, monospace" letterSpacing="0.08">{position}</text>
    </g>
  );
}

export default function FormationPitch({
  formation = "4-3-3",
  players = [],
  title,
  caption,
  testId = "formation-pitch",
  showLegend = true,
  variant = "squad",
}) {
  const system = variant === "system";
  const slots = useMemo(() => getFormationSlots(formation), [formation]);
  const bySlot = useMemo(() => {
    const map = new Map();
    players.forEach((player) => {
      if (player?.slot) map.set(String(player.slot).toUpperCase(), player);
    });
    return map;
  }, [players]);

  const orderedPlayers = useMemo(() => {
    if (players.length === 0) return slots.map(() => null);
    if (bySlot.size > 0) return slots.map((slot) => bySlot.get(slot.slot.toUpperCase()) || null);
    return slots.map((slot, index) => players[index] || null);
  }, [bySlot, players, slots]);

  const assigned = orderedPlayers.filter(Boolean).length;
  const label = system
    ? `${formation} structural formation map with ${slots.length} role slots`
    : `${formation} formation pitch with ${assigned} of ${slots.length} positions assigned`;

  return (
    <figure className="fio-pitch" style={{ margin: 0 }} data-testid={testId}>
      <svg viewBox={`0 -2 ${PITCH_LENGTH} 72`} role="img" aria-label={label} preserveAspectRatio="xMidYMid meet">
        <desc>{title || label}</desc>
        <defs>
          <linearGradient id="fio-pitch-grass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0b2b22" />
            <stop offset="100%" stopColor="#071d18" />
          </linearGradient>
          <pattern id="fio-pitch-stripes" width="10.5" height="68" patternUnits="userSpaceOnUse">
            <rect width="5.25" height="68" fill="rgba(255,255,255,0.018)" />
          </pattern>
        </defs>
        <rect x="0" y="-2" width="105" height="72" fill="url(#fio-pitch-grass)" />
        <rect x="0" y="-2" width="105" height="72" fill="url(#fio-pitch-stripes)" />
        <PitchLines />
        {slots.map((slot, index) => (
          <PlayerMarker key={`${slot.slot}-${index}`} slot={slot} player={orderedPlayers[index]} index={index} system={system} />
        ))}
      </svg>
      {(caption || (showLegend && !system)) ? (
        <figcaption className="fio-pitch-caption">
          <span>{caption || title || (system ? `${formation} · structural role map` : `${formation} · ${assigned} of ${slots.length} slots assigned`)}</span>
          {showLegend && !system ? (
            <span className="fio-pitch-legend" aria-hidden="true">
              <span><i style={{ background: "#45e0d4" }} />Assigned</span>
              <span><i style={{ background: "#f2c26b" }} />Partial</span>
              <span><i style={{ background: "#ff8a8a" }} />Unassigned</span>
            </span>
          ) : null}
        </figcaption>
      ) : null}
    </figure>
  );
}
