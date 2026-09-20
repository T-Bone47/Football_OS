import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, CircleAlert, Compass, Database, Radar, Target } from "lucide-react";
import {
  apiErrorMessage,
  getClubs,
  getPlayer,
  getPlayers,
  getPlayerTacticalFit,
  getTacticalContexts,
} from "@/lib/footballApi";
import PerformanceRadar from "@/components/PerformanceRadar";
import PitchHeatmap from "@/components/PitchHeatmap";

export default function TacticalFitPage() {
  const [params] = useSearchParams();
  const [playerId, setPlayerId] = useState(params.get("player") || "");
  const [clubId, setClubId] = useState("");
  const [contextId, setContextId] = useState("433_dm_deep_distributor");

  const roster = useQuery({
    queryKey: ["tactical-roster"],
    queryFn: () => getPlayers({ limit: 100 }),
    retry: false,
  });

  const clubs = useQuery({
    queryKey: ["tactical-clubs"],
    queryFn: getClubs,
    retry: false,
  });

  const contexts = useQuery({
    queryKey: ["tactical-contexts"],
    queryFn: getTacticalContexts,
    retry: false,
  });

  const player = useQuery({
    queryKey: ["tactical-player", playerId],
    queryFn: () => getPlayer(playerId),
    enabled: !!playerId,
    retry: false,
  });

  const tacticalFit = useQuery({
    queryKey: ["tactical-fit", playerId, contextId, clubId],
    queryFn: () =>
      getPlayerTacticalFit(playerId, {
        context_id: contextId,
        team_id: clubId || undefined,
      }),
    enabled: !!playerId && !!contextId,
    retry: false,
  });

  const activeContext = useMemo(() => {
    return (contexts.data || []).find((c) => c.context_id === contextId);
  }, [contexts.data, contextId]);

  const formation = activeContext?.formation || "4-3-3";
  const role = activeContext?.target_role || "Deep Distributor";

  const fit = tacticalFit.data;
  const isInsufficient = fit?.fit_status === "INSUFFICIENT_DATA" || fit?.confidence === "INSUFFICIENT_DATA";

  const radarData = useMemo(() => {
    if (!fit?.dimension_breakdown) return [];
    return Object.entries(fit.dimension_breakdown).map(([dim, data]) => ({
      label: dim.charAt(0).toUpperCase() + dim.slice(1),
      value: Math.max(0, Math.min(1, data.fit_score ?? 0)),
    }));
  }, [fit]);

  return (
    <section className="intelligence-page" data-testid="tactical-fit-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TACTICAL / SYSTEM FIT</p>
          <h1 data-testid="page-title">Tactical fit workspace</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Evaluate empirical player compatibility against team tactical systems, formations, and functional role requirements.
          </p>
        </div>
        {fit ? (
          <span className={`badge ${isInsufficient ? "warn" : fit.fit_score >= 0.75 ? "pos" : "neutral"}`} data-testid="tactical-fit-badge">
            {isInsufficient ? "INSUFFICIENT SAMPLE" : `${fit.fit_status} · ${(fit.fit_score * 100).toFixed(0)}%`}
          </span>
        ) : (
          <span className="badge info" data-testid="tactical-status-badge">CANONICAL FIT ENGINE</span>
        )}
      </div>

      <div className="workspace-toolbar" data-testid="tactical-toolbar">
        <label className="select-control">
          <Target size={14} />
          <select
            value={playerId}
            onChange={(e) => setPlayerId(e.target.value)}
            aria-label="Player"
            data-testid="tactical-player-select"
          >
            <option value="">Select player</option>
            {(roster.data || []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.primary_position ? `(${p.primary_position})` : ""}
              </option>
            ))}
          </select>
        </label>

        <label className="select-control">
          <Radar size={14} />
          <select
            value={clubId}
            onChange={(e) => setClubId(e.target.value)}
            aria-label="Team"
            data-testid="tactical-club-select"
          >
            <option value="">Select team context (optional)</option>
            {(clubs.data || []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>

        <label className="select-control">
          <Compass size={14} />
          <select
            value={contextId}
            onChange={(e) => setContextId(e.target.value)}
            aria-label="Tactical System"
            data-testid="tactical-context-select"
          >
            {(contexts.data || []).map((c) => (
              <option key={c.context_id} value={c.context_id}>
                {c.formation} · {c.target_position} ({c.target_role})
              </option>
            ))}
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
          <p className="section-copy" style={{ marginTop: 12 }}>
            {activeContext?.description || `Structural alignment for ${formation} ${role}.`}
          </p>
        </div>

        <div className="data-block" data-testid="tactical-fit-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">FIT EVALUATION</p>
              <h3>
                {fit ? `${player.data?.name} · ${(fit.fit_score * 100).toFixed(0)}% Compatibility` : "Select player to calculate fit"}
              </h3>
            </div>
            {fit && (
              <span className={`badge ${fit.confidence === "HIGH" ? "pos" : fit.confidence === "MEDIUM" ? "info" : "warn"}`}>
                CONFIDENCE: {fit.confidence}
              </span>
            )}
          </div>

          {tacticalFit.isLoading && (
            <p className="inline-state" data-testid="tactical-fit-loading">
              Calculating tactical suitability against {activeContext?.target_role}…
            </p>
          )}

          {tacticalFit.isError && (
            <div className="inline-state error-state" data-testid="tactical-fit-error">
              <Database size={14} />
              <span>{apiErrorMessage(tacticalFit.error)}</span>
            </div>
          )}

          {fit && (
            <div className="dimension-list" data-testid="tactical-dimensions">
              <div>
                <span>Position fit ({fit.target_position})</span>
                <div className="dimension-track pos">
                  <i style={{ width: `${Math.round(fit.position_fit * 100)}%` }} />
                </div>
                <b>{Math.round(fit.position_fit * 100)}%</b>
              </div>

              <div>
                <span>Role fit ({fit.target_role})</span>
                <div className="dimension-track pos">
                  <i style={{ width: `${Math.round(fit.role_fit * 100)}%` }} />
                </div>
                <b>{Math.round(fit.role_fit * 100)}%</b>
              </div>

              <div>
                <span>Dimension requirement fit</span>
                <div className="dimension-track pos">
                  <i style={{ width: `${Math.round(fit.dimension_fit * 100)}%` }} />
                </div>
                <b>{Math.round(fit.dimension_fit * 100)}%</b>
              </div>

              {fit.style_fit !== null && (
                <div>
                  <span>Style alignment ({activeContext?.possession_style || "System"})</span>
                  <div className="dimension-track pos">
                    <i style={{ width: `${Math.round(fit.style_fit * 100)}%` }} />
                  </div>
                  <b>{Math.round(fit.style_fit * 100)}%</b>
                </div>
              )}

              {fit.contextual_fit !== null && (
                <div>
                  <span>Exposure maturity</span>
                  <div className="dimension-track pos">
                    <i style={{ width: `${Math.round(fit.contextual_fit * 100)}%` }} />
                  </div>
                  <b>{Math.round(fit.contextual_fit * 100)}%</b>
                </div>
              )}
            </div>
          )}

          {!playerId && (
            <p className="section-copy">Select a player from the dropdown to run point-in-time tactical fit calculation.</p>
          )}

          {fit && (
            <div style={{ marginTop: 20, display: "grid", gap: 14 }}>
              {fit.why_fit?.length > 0 && (
                <div className="data-block" style={{ background: "var(--bg-elevated)", border: "1px solid var(--line)" }}>
                  <div className="block-head" style={{ marginBottom: 8 }}>
                    <h4 style={{ fontSize: 12, color: "var(--teal)", display: "flex", alignItems: "center", gap: 6 }}>
                      <CheckCircle2 size={13} /> Why Fit (Tactical Strengths)
                    </h4>
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {fit.why_fit.map((reason, idx) => (
                      <li key={idx}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}

              {fit.why_not_fit?.length > 0 && (
                <div className="data-block" style={{ background: "var(--bg-elevated)", border: "1px solid var(--line)" }}>
                  <div className="block-head" style={{ marginBottom: 8 }}>
                    <h4 style={{ fontSize: 12, color: "var(--amber)", display: "flex", alignItems: "center", gap: 6 }}>
                      <CircleAlert size={13} /> Tactical Caveats & Bottlenecks
                    </h4>
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {fit.why_not_fit.map((reason, idx) => (
                      <li key={idx}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {radarData.length > 0 && (
        <div className="data-block" style={{ marginTop: 20 }}>
          <div className="section-heading">
            <div>
              <p className="eyebrow">DIMENSION BREAKDOWN</p>
              <h3>Requirement Compatibility Radar</h3>
            </div>
          </div>
          <PerformanceRadar data={radarData} testId="tactical-radar" />
        </div>
      )}
    </section>
  );
}
