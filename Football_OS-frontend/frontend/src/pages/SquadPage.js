import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, ArrowRight, ArrowUpRight, Beaker, CheckCircle2,
  Database, Filter, GitCompare, Layers, Play, RefreshCw, ShieldAlert,
  Target, TrendingDown, TrendingUp, Trophy, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  apiErrorMessage,
  getClubs,
  getPlayers,
  getSquadBuild,
  simulateTransfer,
} from "@/lib/footballApi";
import PitchHeatmap from "@/components/PitchHeatmap";

const CONFIG = {
  builder: {
    eyebrow: "SQUAD / BUILDER",
    title: "Squad builder & depth chart",
    description: "Construct tactical line-ups against formations, identify role coverage gaps, and evaluate roster depth.",
    icon: Trophy,
  },
  simulator: {
    eyebrow: "SQUAD / TRANSFER SIMULATOR",
    title: "Transfer simulator",
    description: "Model incoming and outgoing transfers. Before / after quantitative impact on squad quality, age, role coverage, and risk.",
    icon: GitCompare,
  },
  scenarios: {
    eyebrow: "SQUAD / SCENARIO LAB",
    title: "Scenario lab & hypothesis testing",
    description: "Compose multi-player strategic hypotheses. Systemic before/after impact attribution with actionable scouting recommendations.",
    icon: Beaker,
  },
};

function covStatusBadge(status) {
  switch (status) {
    case "SOLID": return "pos";
    case "ADEQUATE": return "model";
    case "THIN": return "warn";
    case "CRITICAL_GAP": return "warn";
    default: return "info";
  }
}

function covStatusColor(status) {
  switch (status) {
    case "SOLID": return "var(--teal)";
    case "ADEQUATE": return "var(--cyan)";
    case "THIN": return "var(--amber)";
    case "CRITICAL_GAP": return "#ef4444";
    default: return "var(--muted)";
  }
}

function riskBadge(level) {
  switch (level) {
    case "LOW": return "pos";
    case "MODERATE": return "model";
    case "HIGH": return "warn";
    case "CRITICAL": return "warn";
    default: return "info";
  }
}

function riskColor(level) {
  switch (level) {
    case "LOW": return "var(--teal)";
    case "MODERATE": return "var(--cyan)";
    case "HIGH": return "var(--amber)";
    case "CRITICAL": return "#ef4444";
    default: return "var(--muted)";
  }
}

export default function SquadPage({ variant = "builder" }) {
  const config = CONFIG[variant] || CONFIG.builder;
  const Icon = config.icon;

  // Local state
  const [formation, setFormation] = useState("4-3-3");
  const [selectedClubId, setSelectedClubId] = useState("");

  // Simulator state
  const [outgoingPlayerId, setOutgoingPlayerId] = useState("");
  const [incomingPlayerId, setIncomingPlayerId] = useState("");
  const [simResult, setSimResult] = useState(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simError, setSimError] = useState(null);

  // Scenario lab presets
  const [selectedPreset, setSelectedPreset] = useState("rejuvenation");

  // Queries
  const squadQuery = useQuery({
    queryKey: ["squad-build", formation, selectedClubId],
    queryFn: () => getSquadBuild({ formation, club_id: selectedClubId || undefined }),
  });

  const clubsQuery = useQuery({
    queryKey: ["clubs"],
    queryFn: getClubs,
  });

  const playersQuery = useQuery({
    queryKey: ["players-universe"],
    queryFn: () => getPlayers({ limit: 100 }),
  });

  const squad = squadQuery.data;
  const starters = squad?.positions?.filter((p) => p.starter).map((p) => p.starter) || [];
  const allPlayers = playersQuery.data?.items || playersQuery.data || [];

  // Handle transfer simulation
  const handleRunSimulation = async (outId = outgoingPlayerId, inId = incomingPlayerId) => {
    if (!outId && !inId) return;
    setIsSimulating(true);
    setSimError(null);
    try {
      const payload = {
        club_id: selectedClubId || undefined,
        current_player_ids: squad?.positions?.map((p) => p.starter?.player_id).filter(Boolean) || [],
        formation,
        outgoing_player_ids: outId ? [outId] : [],
        incoming_player_ids: inId ? [inId] : [],
      };
      const res = await simulateTransfer(payload);
      setSimResult(res);
    } catch (err) {
      setSimError(apiErrorMessage(err));
    } finally {
      setIsSimulating(false);
    }
  };

  // Run scenario preset
  const handlePresetSelect = (presetKey) => {
    setSelectedPreset(presetKey);
    if (!starters.length || !allPlayers.length) return;

    if (presetKey === "rejuvenation") {
      // Pick oldest starter as outgoing, youngest non-starter player as incoming
      const sortedByAgeDesc = [...starters].filter((p) => p.age).sort((a, b) => b.age - a.age);
      const oldest = sortedByAgeDesc[0];
      const youngCandidates = allPlayers.filter((p) => p.age && p.age < 23 && !starters.some((s) => s.player_id === p.id));
      const young = youngCandidates[0];

      if (oldest) setOutgoingPlayerId(oldest.player_id);
      if (young) setIncomingPlayerId(young.id);
      if (oldest && young) {
        handleRunSimulation(oldest.player_id, young.id);
      }
    } else if (presetKey === "reinforcement") {
      // Pick position with lowest depth/coverage quality and add a compatible reinforcement
      const thinSlot = squad?.positions?.find((p) => p.coverage_status === "CRITICAL_GAP" || p.coverage_status === "THIN");
      const cand = allPlayers.find((p) => !starters.some((s) => s.player_id === p.id));
      setOutgoingPlayerId("");
      if (cand) {
        setIncomingPlayerId(cand.id);
        handleRunSimulation("", cand.id);
      }
    }
  };

  return (
    <section className="intelligence-page" data-testid={`squad-page-${variant}`}>
      {/* ─── PAGE HEADING ────────────────────────────────────── */}
      <div className="page-heading">
        <div>
          <p className="eyebrow">{config.eyebrow}</p>
          <h1 data-testid="page-title">{config.title}</h1>
          <p className="workspace-subtitle" data-testid="page-description">{config.description}</p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <select
            value={formation}
            onChange={(e) => setFormation(e.target.value)}
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "6px 12px",
              fontSize: 13,
              fontWeight: 600,
            }}
            data-testid="formation-select"
          >
            <option value="4-3-3">Formation 4-3-3</option>
            <option value="4-2-3-1">Formation 4-2-3-1</option>
            <option value="3-5-2">Formation 3-5-2</option>
          </select>

          {clubsQuery.data && (
            <select
              value={selectedClubId}
              onChange={(e) => setSelectedClubId(e.target.value)}
              style={{
                background: "var(--bg-elevated)",
                color: "var(--text-primary)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "6px 12px",
                fontSize: 13,
              }}
              data-testid="club-select"
            >
              <option value="">All Clubs / Active Universe</option>
              {clubsQuery.data.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}

          <span className="badge model">PHASE 5A LIVE</span>
        </div>
      </div>

      {/* ─── SUB-NAVIGATION SURFACES ─────────────────────────── */}
      <div className="tab-row" style={{ display: "flex", gap: 8, margin: "16px 0 24px 0", borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
        <Link
          to="/squad/builder"
          className={`tab-btn ${variant === "builder" ? "active" : ""}`}
          style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 6, fontSize: 13, fontWeight: 500, background: variant === "builder" ? "var(--accent-glow)" : "transparent", color: variant === "builder" ? "var(--teal)" : "var(--text-secondary)" }}
        >
          <Trophy size={14} /> Squad Builder
        </Link>
        <Link
          to="/squad/simulator"
          className={`tab-btn ${variant === "simulator" ? "active" : ""}`}
          style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 6, fontSize: 13, fontWeight: 500, background: variant === "simulator" ? "var(--accent-glow)" : "transparent", color: variant === "simulator" ? "var(--teal)" : "var(--text-secondary)" }}
        >
          <GitCompare size={14} /> Transfer Simulator
        </Link>
        <Link
          to="/squad/scenarios"
          className={`tab-btn ${variant === "scenarios" ? "active" : ""}`}
          style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 6, fontSize: 13, fontWeight: 500, background: variant === "scenarios" ? "var(--accent-glow)" : "transparent", color: variant === "scenarios" ? "var(--teal)" : "var(--text-secondary)" }}
        >
          <Beaker size={14} /> Scenario Lab
        </Link>
      </div>

      {/* ─── LOADING / ERROR STATES ───────────────────────────── */}
      {squadQuery.isLoading && <p className="section-copy">Constructing tactical squad model from canonical database…</p>}
      {squadQuery.isError && <p className="section-copy error-state">{apiErrorMessage(squadQuery.error)}</p>}

      {/* ─── KPI SUMMARY ROW ─────────────────────────────────── */}
      {squad && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 14, marginBottom: 24 }}>
          <div className="data-block" style={{ padding: 14 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Squad Quality</span>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--teal)", marginTop: 4 }}>
              {(squad.squad_quality_score * 100).toFixed(0)}%
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>Composite role + tactical fit</small>
          </div>

          <div className="data-block" style={{ padding: 14 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Role Coverage</span>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--cyan)", marginTop: 4 }}>
              {(squad.role_coverage_score * 100).toFixed(0)}%
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>{squad.starters_count} of {squad.positions.length} slots filled</small>
          </div>

          <div className="data-block" style={{ padding: 14 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Tactical Fit</span>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text-primary)", marginTop: 4 }}>
              {(squad.tactical_fit_score * 100).toFixed(0)}%
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>Formation {squad.formation} harmony</small>
          </div>

          <div className="data-block" style={{ padding: 14 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Depth Risk</span>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
              <span style={{ fontSize: 24, fontWeight: 700, color: riskColor(squad.depth_risk_level) }}>
                {(squad.depth_risk_score * 100).toFixed(0)}%
              </span>
              <span className={`badge ${riskBadge(squad.depth_risk_level)}`} style={{ fontSize: 10 }}>
                {squad.depth_risk_level}
              </span>
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>Bench cover & vacancy risk</small>
          </div>

          <div className="data-block" style={{ padding: 14 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Average Age</span>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text-primary)", marginTop: 4 }}>
              {squad.average_age > 0 ? `${squad.average_age.toFixed(1)} yrs` : "—"}
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>Roster demographics</small>
          </div>

          <div className="data-block" style={{ padding: 14 }}>
            <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Estimated Value</span>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--teal)", marginTop: 4 }}>
              {squad.total_estimated_value_eur > 0 ? `€${(squad.total_estimated_value_eur / 1_000_000).toFixed(1)}M` : "—"}
            </div>
            <small style={{ color: "var(--muted)", fontSize: 11 }}>Active squad market baseline</small>
          </div>
        </div>
      )}

      {/* ─── VARIANT 1: SQUAD BUILDER ────────────────────────── */}
      {variant === "builder" && squad && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* Main formation & pitch split */}
          <div className="split-columns" style={{ display: "grid", gridTemplateColumns: "minmax(340px, 1fr) minmax(420px, 1.3fr)", gap: 20 }}>
            {/* Pitch + Starting XI */}
            <div className="data-block" data-testid="squad-pitch-panel">
              <div className="block-head" style={{ marginBottom: 12 }}>
                <div>
                  <h3>Tactical Formation: {squad.formation}</h3>
                  <small style={{ color: "var(--muted)" }}>Greedy optimal role and positional fit allocation</small>
                </div>
                <span className="badge model">{squad.starters_count} STARTERS</span>
              </div>

              <PitchHeatmap formation={squad.formation} caption={`${squad.formation} · Starting XI`} testId="squad-pitch" />

              {/* Starting XI List */}
              <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8 }}>
                <h4 style={{ fontSize: 13, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)", margin: "8px 0 4px 0" }}>
                  Selected Starting XI
                </h4>
                {squad.positions.map((p) => (
                  <div
                    key={p.slot_name}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 12px",
                      background: p.starter ? "rgba(255,255,255,0.02)" : "rgba(239,68,68,0.06)",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, width: 36, color: "var(--cyan)", fontSize: 12 }}>
                        {p.slot_name}
                      </span>
                      {p.starter ? (
                        <div>
                          <Link to={`/players/${p.starter.player_id}`} className="player-link" style={{ fontWeight: 600, fontSize: 13 }}>
                            {p.starter.player_name}
                          </Link>
                          <span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 6 }}>
                            {p.starter.primary_role || p.starter.primary_position}
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: "#ef4444", fontSize: 12, fontStyle: "italic" }}>
                          No starter allocated (Gap)
                        </span>
                      )}
                    </div>
                    {p.starter && (
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--teal)" }}>
                          Fit: {(p.starter.tactical_fit_score * 100).toFixed(0)}%
                        </span>
                        {p.starter.estimated_value_eur && (
                          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--muted)" }}>
                            €{(p.starter.estimated_value_eur / 1_000_000).toFixed(1)}M
                          </span>
                        )}
                        <span className={`badge ${riskBadge(p.starter.transfer_risk_level)}`} style={{ fontSize: 9 }}>
                          {p.starter.transfer_risk_level}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Position Depth Chart & Gaps */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="data-block" data-testid="squad-depth-panel">
                <div className="block-head" style={{ marginBottom: 12 }}>
                  <div>
                    <h3>Position Depth & Coverage</h3>
                    <small style={{ color: "var(--muted)" }}>Roster backup capacity and vacancy risk</small>
                  </div>
                </div>

                <div className="table-wrap">
                  <table className="data-table" data-testid="squad-depth-table">
                    <thead>
                      <tr>
                        <th>Slot</th>
                        <th>Starter</th>
                        <th>Backup Depth</th>
                        <th>Count</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {squad.positions.map((pos) => (
                        <tr key={pos.slot_name}>
                          <td style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: "var(--cyan)" }}>
                            {pos.slot_name}
                          </td>
                          <td>
                            {pos.starter ? (
                              <Link to={`/players/${pos.starter.player_id}`} className="player-link" style={{ fontWeight: 600 }}>
                                {pos.starter.player_name}
                              </Link>
                            ) : (
                              <span style={{ color: "#ef4444" }}>—</span>
                            )}
                          </td>
                          <td>
                            {pos.backups.length > 0 ? (
                              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                                {pos.backups.map((b) => b.player_name).join(", ")}
                              </span>
                            ) : (
                              <span style={{ fontSize: 11, color: "var(--muted)", fontStyle: "italic" }}>No direct cover</span>
                            )}
                          </td>
                          <td style={{ fontFamily: "JetBrains Mono, monospace", textAlign: "center" }}>
                            {pos.depth_count}
                          </td>
                          <td>
                            <span className={`badge ${covStatusBadge(pos.coverage_status)}`} style={{ fontSize: 10 }}>
                              {pos.coverage_status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Key Gaps & Strengths */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div className="data-block" style={{ padding: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, color: "#ef4444", fontWeight: 600, fontSize: 13 }}>
                    <AlertTriangle size={15} /> Depth Gaps & Alerts
                  </div>
                  {squad.key_gaps.length === 0 ? (
                    <p style={{ fontSize: 12, color: "var(--teal)", margin: 0 }}>Roster depth is well-balanced across all slots.</p>
                  ) : (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)" }}>
                      {squad.key_gaps.map((gap, i) => (
                        <li key={i} style={{ marginBottom: 4 }}>{gap}</li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="data-block" style={{ padding: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, color: "var(--teal)", fontWeight: 600, fontSize: 13 }}>
                    <CheckCircle2 size={15} /> System Strengths
                  </div>
                  {squad.key_strengths.length === 0 ? (
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>Add high-fit starters to unlock structural strengths.</p>
                  ) : (
                    <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)" }}>
                      {squad.key_strengths.map((str, i) => (
                        <li key={i} style={{ marginBottom: 4 }}>{str}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── VARIANT 2: TRANSFER SIMULATOR ───────────────────── */}
      {variant === "simulator" && squad && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Transfer Setup Block */}
          <div className="data-block" data-testid="simulation-setup-panel">
            <div className="block-head" style={{ marginBottom: 16 }}>
              <div>
                <h3>Configure Prospective Transfer</h3>
                <small style={{ color: "var(--muted)" }}>Select a departure and/or arrival to model systemic squad impact</small>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 16, alignItems: "center" }}>
              {/* Outgoing selector */}
              <div style={{ padding: 16, background: "rgba(239,68,68,0.03)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#ef4444", fontWeight: 600, fontSize: 13, marginBottom: 10 }}>
                  <TrendingDown size={15} /> Outgoing Player (Departure)
                </div>
                <select
                  value={outgoingPlayerId}
                  onChange={(e) => setOutgoingPlayerId(e.target.value)}
                  style={{ width: "100%", padding: "8px 12px", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 13 }}
                  data-testid="outgoing-player-select"
                >
                  <option value="">-- No outgoing player --</option>
                  {starters.map((p) => (
                    <option key={p.player_id} value={p.player_id}>
                      {p.player_name} ({p.slot_name} · {p.primary_position} · {p.age ? `${p.age.toFixed(0)}y` : ""})
                    </option>
                  ))}
                </select>
              </div>

              {/* Arrow */}
              <div style={{ display: "flex", justifyContent: "center", color: "var(--muted)" }}>
                <ArrowRight size={24} />
              </div>

              {/* Incoming selector */}
              <div style={{ padding: 16, background: "rgba(20,184,166,0.03)", border: "1px solid rgba(20,184,166,0.2)", borderRadius: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--teal)", fontWeight: 600, fontSize: 13, marginBottom: 10 }}>
                  <TrendingUp size={15} /> Incoming Target (Arrival)
                </div>
                <select
                  value={incomingPlayerId}
                  onChange={(e) => setIncomingPlayerId(e.target.value)}
                  style={{ width: "100%", padding: "8px 12px", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 13 }}
                  data-testid="incoming-player-select"
                >
                  <option value="">-- No incoming target --</option>
                  {allPlayers
                    .filter((p) => !starters.some((s) => s.player_id === p.id))
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.primary_position || "CM"}{p.nationality ? ` · ${p.nationality}` : ""})
                      </option>
                    ))}
                </select>
              </div>
            </div>

            <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                onClick={() => handleRunSimulation()}
                disabled={(!outgoingPlayerId && !incomingPlayerId) || isSimulating}
                className="btn primary"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 16px", borderRadius: 6, fontWeight: 600 }}
                data-testid="run-simulation-btn"
              >
                {isSimulating ? <RefreshCw size={14} className="spin" /> : <Play size={14} />}
                Run Transfer Simulation
              </button>
            </div>

            {simError && <p className="error-state" style={{ marginTop: 10 }}>{simError}</p>}
          </div>

          {/* Simulation Results Display */}
          {simResult && (
            <div className="data-block" data-testid="simulation-results-panel">
              <div className="block-head" style={{ marginBottom: 16 }}>
                <div>
                  <h3>Simulation Impact Attribution</h3>
                  <small style={{ color: "var(--muted)" }}>Pre- and post-transfer squad delta comparison</small>
                </div>
                <span className="badge model">
                  NET SPEND: {simResult.net_spend_eur >= 0 ? `+€${(simResult.net_spend_eur / 1_000_000).toFixed(1)}M` : `-€${(Math.abs(simResult.net_spend_eur) / 1_000_000).toFixed(1)}M`}
                </span>
              </div>

              {/* Delta Cards Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 18 }}>
                <div style={{ padding: 12, background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Squad Quality</span>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4, color: simResult.impact.delta_squad_quality >= 0 ? "var(--teal)" : "#ef4444" }}>
                    {simResult.impact.delta_squad_quality >= 0 ? "+" : ""}{(simResult.impact.delta_squad_quality * 100).toFixed(1)}%
                  </div>
                  <small style={{ fontSize: 10, color: "var(--muted)" }}>{(simResult.before.squad_quality_score * 100).toFixed(0)}% → {(simResult.after.squad_quality_score * 100).toFixed(0)}%</small>
                </div>

                <div style={{ padding: 12, background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Depth Risk</span>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4, color: simResult.impact.delta_depth_risk <= 0 ? "var(--teal)" : "#ef4444" }}>
                    {simResult.impact.delta_depth_risk >= 0 ? "+" : ""}{(simResult.impact.delta_depth_risk * 100).toFixed(1)}%
                  </div>
                  <small style={{ fontSize: 10, color: "var(--muted)" }}>{(simResult.before.depth_risk_score * 100).toFixed(0)}% → {(simResult.after.depth_risk_score * 100).toFixed(0)}%</small>
                </div>

                <div style={{ padding: 12, background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Average Age</span>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4, color: simResult.impact.delta_average_age <= 0 ? "var(--teal)" : "var(--amber)" }}>
                    {simResult.impact.delta_average_age >= 0 ? "+" : ""}{simResult.impact.delta_average_age.toFixed(1)} yrs
                  </div>
                  <small style={{ fontSize: 10, color: "var(--muted)" }}>{simResult.before.average_age.toFixed(1)}y → {simResult.after.average_age.toFixed(1)}y</small>
                </div>

                <div style={{ padding: 12, background: "rgba(255,255,255,0.02)", border: "1px solid var(--border)", borderRadius: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Tactical Fit</span>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4, color: simResult.impact.delta_tactical_fit >= 0 ? "var(--teal)" : "#ef4444" }}>
                    {simResult.impact.delta_tactical_fit >= 0 ? "+" : ""}{(simResult.impact.delta_tactical_fit * 100).toFixed(1)}%
                  </div>
                  <small style={{ fontSize: 10, color: "var(--muted)" }}>{(simResult.before.tactical_fit_score * 100).toFixed(0)}% → {(simResult.after.tactical_fit_score * 100).toFixed(0)}%</small>
                </div>
              </div>

              {/* Narrative Summary & Recommendations */}
              <div style={{ padding: 16, background: "rgba(20,184,166,0.03)", border: "1px solid rgba(20,184,166,0.2)", borderRadius: 8, marginBottom: 16 }}>
                <h4 style={{ margin: "0 0 6px 0", fontSize: 13, color: "var(--teal)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Systemic Assessment
                </h4>
                <p style={{ margin: "0 0 10px 0", fontSize: 13, color: "var(--text-primary)", lineHeight: 1.5 }}>
                  {simResult.impact.summary}
                </p>
                <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 10 }}>
                  <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 600 }}>SCOUTING RECOMMENDATIONS:</span>
                  <ul style={{ margin: "6px 0 0 0", paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)" }}>
                    {simResult.impact.recommendations.map((rec, i) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── VARIANT 3: SCENARIO LAB ─────────────────────────── */}
      {variant === "scenarios" && squad && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="data-block" data-testid="scenario-lab-panel">
            <div className="block-head" style={{ marginBottom: 16 }}>
              <div>
                <h3>Strategic Roster Scenarios</h3>
                <small style={{ color: "var(--muted)" }}>Hypothesis testing across recruitment and squad planning initiatives</small>
              </div>
            </div>

            {/* Scenario Presets Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
              <div
                onClick={() => handlePresetSelect("rejuvenation")}
                style={{
                  padding: 16,
                  borderRadius: 8,
                  border: selectedPreset === "rejuvenation" ? "1px solid var(--teal)" : "1px solid var(--border)",
                  background: selectedPreset === "rejuvenation" ? "rgba(20,184,166,0.05)" : "rgba(255,255,255,0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <h4 style={{ margin: "0 0 6px 0", fontSize: 14, color: "var(--text-primary)" }}>
                  Demographic Rejuvenation
                </h4>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>
                  Replace the senior-most starter with a high-potential under-23 prospect to reduce long-term demographic risk.
                </p>
              </div>

              <div
                onClick={() => handlePresetSelect("reinforcement")}
                style={{
                  padding: 16,
                  borderRadius: 8,
                  border: selectedPreset === "reinforcement" ? "1px solid var(--teal)" : "1px solid var(--border)",
                  background: selectedPreset === "reinforcement" ? "rgba(20,184,166,0.05)" : "rgba(255,255,255,0.02)",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                <h4 style={{ margin: "0 0 6px 0", fontSize: 14, color: "var(--text-primary)" }}>
                  Depth Gap Reinforcement
                </h4>
                <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>
                  Target vulnerable positions flagged as THIN or CRITICAL_GAP without losing any core starters.
                </p>
              </div>
            </div>
          </div>

          {/* Active Scenario Simulation Results */}
          {simResult && (
            <div className="data-block" data-testid="scenario-results-panel">
              <div className="block-head" style={{ marginBottom: 14 }}>
                <div>
                  <h3>Hypothesis Evaluation Output</h3>
                  <small style={{ color: "var(--muted)" }}>Provenance-grounded impact calculation</small>
                </div>
                <span className="badge model">SCENARIO TESTED</span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 12 }}>
                {simResult.impact.summary}
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
                <div style={{ padding: 10, background: "rgba(255,255,255,0.02)", borderRadius: 6, border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Quality Trajectory:</span>
                  <div style={{ fontWeight: 600, fontSize: 14, color: simResult.impact.delta_squad_quality >= 0 ? "var(--teal)" : "#ef4444" }}>
                    {simResult.impact.delta_squad_quality >= 0 ? "+" : ""}{(simResult.impact.delta_squad_quality * 100).toFixed(1)}%
                  </div>
                </div>
                <div style={{ padding: 10, background: "rgba(255,255,255,0.02)", borderRadius: 6, border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Demographic Shift:</span>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
                    {simResult.impact.delta_average_age >= 0 ? "+" : ""}{simResult.impact.delta_average_age.toFixed(1)} years
                  </div>
                </div>
                <div style={{ padding: 10, background: "rgba(255,255,255,0.02)", borderRadius: 6, border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>Depth Risk Impact:</span>
                  <div style={{ fontWeight: 600, fontSize: 14, color: simResult.impact.delta_depth_risk <= 0 ? "var(--teal)" : "#ef4444" }}>
                    {simResult.impact.delta_depth_risk >= 0 ? "+" : ""}{(simResult.impact.delta_depth_risk * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
