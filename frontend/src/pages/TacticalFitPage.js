import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Compass, Database, Radar, Target } from "lucide-react";
import { apiErrorMessage, getClubs, getPlayer, getPlayers, BACKEND_GAPS } from "@/lib/footballApi";
import PerformanceRadar from "@/components/PerformanceRadar";
import PitchHeatmap from "@/components/PitchHeatmap";

const FORMATIONS = ["4-3-3", "4-2-3-1", "3-5-2", "4-4-2", "3-4-3"];
const ROLES = ["Progressive 8", "Ball-winning DM", "Inverted FB", "Target 9", "Pressing 10", "Wide creator"];

export default function TacticalFitPage() {
  const [params] = useSearchParams();
  const [playerId, setPlayerId] = useState(params.get("player") || "");
  const [clubId, setClubId] = useState("");
  const [formation, setFormation] = useState(FORMATIONS[0]);
  const [role, setRole] = useState(ROLES[0]);

  const roster = useQuery({ queryKey: ["tactical-roster"], queryFn: () => getPlayers({ limit: 200 }), retry: false });
  const clubs = useQuery({ queryKey: ["tactical-clubs"], queryFn: getClubs, retry: false });
  const player = useQuery({ queryKey: ["tactical-player", playerId], queryFn: () => getPlayer(playerId), enabled: !!playerId, retry: false });

  const radarData = useMemo(() => {
    if (!player.data) return [];
    // Only derive labels from real feature vector; do NOT fabricate scores.
    return [];
  }, [player.data]);

  return (
    <section className="intelligence-page" data-testid="tactical-fit-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TACTICAL / FIT</p>
          <h1 data-testid="page-title">Tactical fit workspace</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Test a player against a team, formation, and role. Fit scores are only rendered when the backend exposes team-system evidence.
          </p>
        </div>
        <span className="badge warn" data-testid="tactical-dependency-badge">BACKEND DEPENDENCY</span>
      </div>

      <div className="workspace-toolbar" data-testid="tactical-toolbar">
        <label className="select-control">
          <Target size={14} />
          <select value={playerId} onChange={(e) => setPlayerId(e.target.value)} aria-label="Player" data-testid="tactical-player-select">
            <option value="">Select player</option>
            {(roster.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label className="select-control">
          <Radar size={14} />
          <select value={clubId} onChange={(e) => setClubId(e.target.value)} aria-label="Team" data-testid="tactical-club-select">
            <option value="">Select team</option>
            {(clubs.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="select-control">
          <Compass size={14} />
          <select value={formation} onChange={(e) => setFormation(e.target.value)} aria-label="Formation" data-testid="tactical-formation-select">
            {FORMATIONS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label className="select-control">
          <Radar size={14} />
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" data-testid="tactical-role-select">
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      </div>

      <div className="split-columns" style={{ marginTop: 24 }}>
        <div className="data-block" data-testid="tactical-pitch-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SYSTEM VISUALIZATION</p>
              <h3>{formation} · {role}</h3>
            </div>
            <span className="badge neutral">STRUCTURAL</span>
          </div>
          <PitchHeatmap
            formation={formation}
            caption={`${formation} · ${role}`}
            testId="tactical-pitch"
          />
          <p className="section-copy">
            Position markers show the {formation} structural layout. Positional intensity heatmap will render on this same pitch when the backend supplies role-conditioned tactical vectors.
          </p>
        </div>

        <div className="data-block" data-testid="tactical-fit-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">FIT DIMENSIONS</p>
              <h3>Waiting for backend evidence</h3>
            </div>
          </div>
          {roster.isError && (
            <p className="section-copy error-state">
              <Database size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              {apiErrorMessage(roster.error)}
            </p>
          )}
          {player.data ? (
            <div className="dimension-list" data-testid="tactical-dimensions">
              {["Overall fit", "Role fit", "Possession fit", "Pressing fit", "Defensive fit", "Transition fit"].map((label) => (
                <div key={label}>
                  <span>{label}</span>
                  <div className="dimension-track"><i style={{ width: "0%" }} /></div>
                  <b>—</b>
                </div>
              ))}
            </div>
          ) : (
            <p className="section-copy">Select a player from the connected index to prepare the fit workspace.</p>
          )}
          <div className="dependency-section" data-testid="tactical-dependency-panel">
            <Database size={16} />
            <div>
              <p className="eyebrow">DEPENDENCY</p>
              <h2>Fit scoring not yet exposed</h2>
              <p className="section-copy">{BACKEND_GAPS.tacticalFit}</p>
            </div>
          </div>
        </div>
      </div>

      {radarData.length > 0 && (
        <div className="data-block" style={{ marginTop: 20 }}>
          <PerformanceRadar data={radarData} testId="tactical-radar" />
        </div>
      )}
    </section>
  );
}
