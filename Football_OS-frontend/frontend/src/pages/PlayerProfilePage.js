import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Activity, ArrowLeft, Database, GitCompare, Radar, ShieldAlert,
  Sparkles, Target, TrendingUp, Zap,
} from "lucide-react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import PerformanceRadar from "@/components/PerformanceRadar";
import AddToShortlistButton from "@/components/AddToShortlistButton";
import {
  apiErrorMessage, BACKEND_GAPS, getPlayer, getPlayerFeatures,
  getPlayerRole, getPlayerRoleProfile, getSimilarPlayers, getPlayerTacticalFit,
  getPlayerContributions, getPlayerActionValues,
  getPlayerIntelligence, getPlayerTrajectory, getPlayerBenchmarks,
  getPlayerTransfers, getPlayerValuationBaseline, getPlayerTransferComparables, getPlayerMarketContext,
} from "@/lib/footballApi";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "contribution", label: "Contribution" },
  { id: "benchmarks", label: "Peer Benchmarks" },
  { id: "trajectory", label: "Trajectory" },
  { id: "performance", label: "Performance" },
  { id: "role", label: "Role" },
  { id: "similarity", label: "Similarity" },
  { id: "tactical", label: "Tactical fit" },
  { id: "market", label: "Market" },
  { id: "evidence", label: "Evidence" },
];

function Metric({ label, value, sub, testId }) {
  return (
    <div className="profile-metric" data-testid={testId}>
      <span>{label}</span>
      <strong>{value !== null && value !== undefined && value !== "" ? value : "—"}</strong>
      {sub && <small>{sub}</small>}
    </div>
  );
}

function DependencyPanel({ eyebrow, title, message, testId }) {
  return (
    <div className="dependency-section" data-testid={testId}>
      <ShieldAlert size={16} />
      <div>
        <p className="eyebrow" style={{ marginBottom: 4 }}>{eyebrow}</p>
        <h2>{title}</h2>
        <p className="section-copy">{message}</p>
      </div>
    </div>
  );
}

export default function PlayerProfilePage() {
  const { playerId } = useParams();
  const [tab, setTab] = useState("overview");
  const [evidence, setEvidence] = useState(null);
  const [similarityMode, setSimilarityMode] = useState("composite");

  const player = useQuery({ queryKey: ["player", playerId], queryFn: () => getPlayer(playerId), retry: false });
  const role = useQuery({ queryKey: ["player-role", playerId], queryFn: () => getPlayerRole(playerId), enabled: !!player.data, retry: false });
  const roleProfile = useQuery({ queryKey: ["player-role-profile", playerId], queryFn: () => getPlayerRoleProfile(playerId), enabled: !!player.data, retry: false });
  const features = useQuery({ queryKey: ["player-features", playerId], queryFn: () => getPlayerFeatures(playerId), enabled: !!player.data, retry: false });
  const similar = useQuery({ queryKey: ["player-similar", playerId, similarityMode], queryFn: () => getSimilarPlayers(playerId, { mode: similarityMode }), enabled: !!player.data, retry: false });
  const tacticalFit = useQuery({ queryKey: ["player-tactical-fit", playerId], queryFn: () => getPlayerTacticalFit(playerId, { formation: "4-3-3" }), enabled: !!player.data, retry: false });
  const contributions = useQuery({ queryKey: ["player-contributions", playerId], queryFn: () => getPlayerContributions(playerId), enabled: !!player.data, retry: false });
  const actionValues = useQuery({ queryKey: ["player-action-values", playerId], queryFn: () => getPlayerActionValues(playerId, { model: "impact" }), enabled: !!player.data, retry: false });
  const intelligence = useQuery({ queryKey: ["player-intelligence", playerId], queryFn: () => getPlayerIntelligence(playerId), enabled: !!player.data, retry: false });
  const trajectory = useQuery({ queryKey: ["player-trajectory", playerId], queryFn: () => getPlayerTrajectory(playerId), enabled: !!player.data, retry: false });
  const benchmarks = useQuery({ queryKey: ["player-benchmarks", playerId], queryFn: () => getPlayerBenchmarks(playerId), enabled: !!player.data, retry: false });
  const playerTransfers = useQuery({ queryKey: ["player-transfers", playerId], queryFn: () => getPlayerTransfers(playerId), enabled: !!player.data, retry: false });
  const valuationBaseline = useQuery({ queryKey: ["player-valuation", playerId], queryFn: () => getPlayerValuationBaseline(playerId), enabled: !!player.data, retry: false });
  const comparables = useQuery({ queryKey: ["player-comparables", playerId], queryFn: () => getPlayerTransferComparables(playerId), enabled: !!player.data, retry: false });
  const marketContext = useQuery({ queryKey: ["player-market-context", playerId], queryFn: () => getPlayerMarketContext(playerId), enabled: !!player.data, retry: false });

  const radarData = useMemo(() => {
    const scores = roleProfile.data?.profile_scores;
    if (!scores) return [];
    return Object.entries(scores)
      .slice(0, 8)
      .map(([label, value]) => ({
        label: label.replaceAll("_", " "),
        value: Math.max(0, Math.min(1, Number(value) || 0)),
      }));
  }, [roleProfile.data]);

  if (player.isLoading) return <p className="inline-state" data-testid="player-profile-loading">Loading player intelligence…</p>;
  if (player.isError) return (
    <div className="inline-state error-state" data-testid="player-profile-error">
      <Database size={15} /> {apiErrorMessage(player.error)}
    </div>
  );

  const item = player.data;
  const latest = item.season_stats?.[0];
  const tabCounts = {
    similarity: similar.data?.results?.length || 0,
    performance: item.season_stats?.length || 0,
    trajectory: trajectory.data?.timeline?.length || 0,
    market: playerTransfers.data?.length || 0,
  };

  return (
    <section className="intelligence-page profile-page" data-testid="player-profile-page">
      <Link to="/players" className="back-link" data-testid="player-profile-back">
        <ArrowLeft size={13} /> Player discovery
      </Link>

      <header className="profile-header">
        <div className="profile-avatar" data-testid="player-profile-avatar">{item.name.slice(0, 2).toUpperCase()}</div>
        <div>
          <p className="eyebrow" data-testid="profile-eyebrow">PLAYER INTELLIGENCE</p>
          <h1 data-testid="player-profile-name">{item.name}</h1>
          <div className="profile-tag-row" data-testid="player-profile-meta">
            {item.primary_position && <span className={`pos-pill ${item.primary_position?.toLowerCase().startsWith("gk") ? "gk" : ""}`}>{item.primary_position}</span>}
            <span>{item.nationality || "Nationality unknown"}</span>
            <span className="sep">·</span>
            <span>{item.preferred_foot || "Foot unknown"}</span>
            {item.date_of_birth && <><span className="sep">·</span><span>{item.date_of_birth}</span></>}
          </div>
        </div>
        <div className="profile-header-actions" data-testid="profile-actions">
          <AddToShortlistButton player={item} testId="profile-action-shortlist" />
          <Link to={`/players/compare?ids=${item.id}`} className="outline-button" data-testid="profile-action-compare">
            <GitCompare size={13} /> Compare
          </Link>
          <Link to={`/players/similarity?player=${item.id}`} className="outline-button" data-testid="profile-action-similar">
            <Sparkles size={13} /> Similar
          </Link>
          <Link to={`/tactical/fit?player=${item.id}`} className="outline-button" data-testid="profile-action-fit">
            <Target size={13} /> Tactical fit
          </Link>
        </div>
      </header>

      <nav className="tabbar" data-testid="profile-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => setTab(t.id)}
            data-testid={`profile-tab-${t.id}`}
          >
            {t.label}
            {tabCounts[t.id] > 0 && <span className="count">{tabCounts[t.id]}</span>}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <div className="stack-14" data-testid="profile-tab-overview-content">
          <div className="metric-grid" data-testid="player-snapshot-grid">
            <Metric label="Minutes" value={latest?.minutes} testId="player-metric-minutes" />
            <Metric label="Goals" value={latest?.goals} testId="player-metric-goals" />
            <Metric label="Assists" value={latest?.assists} testId="player-metric-assists" />
            <Metric label="Rating" value={latest?.rating} sub={latest?.competition_id ? `Comp ${latest.competition_id}` : null} testId="player-metric-rating" />
          </div>

          {/* Intelligence Engine Summary */}
          {intelligence.data && (
            <div className="data-block" data-testid="overview-intelligence-summary">
              <div className="block-head">
                <div>
                  <h3 style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <Sparkles size={14} color="var(--teal)" /> Player Intelligence Summary · {intelligence.data.position_group}
                  </h3>
                  <small style={{ color: "var(--muted)" }}>
                    Calculated as-of {new Date(intelligence.data.as_of).toLocaleDateString()} · v{intelligence.data.calculation_version}
                  </small>
                </div>
                <div className="badges">
                  <span className={`badge ${intelligence.data.data_status === "EVALUATED" ? "pos" : "warn"}`} data-testid="intel-status-badge">
                    {intelligence.data.data_status}
                  </span>
                  <span className={`badge ${intelligence.data.confidence === "HIGH" ? "pos" : intelligence.data.confidence === "MEDIUM" ? "model" : "warn"}`} data-testid="intel-confidence-badge">
                    CONFIDENCE · {intelligence.data.confidence}
                  </span>
                  {intelligence.data.provenance && (
                    <button className="evidence-button" onClick={() => setEvidence(intelligence.data.provenance)} data-testid="intel-evidence-button">
                      <Database size={12} /> Provenance
                    </button>
                  )}
                </div>
              </div>

              {/* Explanations */}
              <div className="analytics-grid" style={{ marginTop: 12 }}>
                <div>
                  <p className="eyebrow" style={{ color: "var(--teal)", marginBottom: 4 }}>WHY STRONG</p>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {intelligence.data.explanations?.why_strong?.map((exp, i) => <li key={i}>{exp}</li>)}
                  </ul>
                </div>
                <div>
                  <p className="eyebrow" style={{ color: "var(--amber)", marginBottom: 4 }}>
                    {intelligence.data.data_status !== "EVALUATED" ? "WHY LOW CONFIDENCE" : "WHY DIFFERENT"}
                  </p>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {(intelligence.data.data_status !== "EVALUATED"
                      ? intelligence.data.explanations?.why_low_confidence
                      : intelligence.data.explanations?.why_different
                    )?.map((exp, i) => <li key={i}>{exp}</li>)}
                  </ul>
                </div>
              </div>
            </div>
          )}

          <div className="analytics-grid">
            <div className="data-block" data-testid="overview-role-block">
              <div className="block-head">
                <h3>Role profile</h3>
                <div className="badges">
                  {role.data?.confidence != null && (
                    <span className="badge model" data-testid="role-confidence-badge">
                      MODEL · {(role.data.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                  {roleProfile.data?.provenance && (
                    <button className="evidence-button" onClick={() => setEvidence(roleProfile.data.provenance)} data-testid="role-evidence-button">
                      <Database size={12} /> Evidence
                    </button>
                  )}
                </div>
              </div>
              <p className="section-copy" data-testid="role-profile-summary">
                {role.data?.summary || (role.isError ? apiErrorMessage(role.error) : "Fetching role evidence from the connected backend…")}
              </p>
              {radarData.length > 0 ? (
                <PerformanceRadar data={radarData} testId="overview-role-radar" />
              ) : (
                <p className="section-copy" data-testid="overview-radar-empty">Role profile percentile data not yet available.</p>
              )}
            </div>

            <div className="stack-14">
              <div className="data-block" data-testid="overview-similarity-block">
                <div className="block-head">
                  <h3>Top similar</h3>
                  <span className="confidence-note">Multi-dimensional</span>
                </div>
                {similar.isLoading && <p className="section-copy">Loading similarity…</p>}
                {similar.isError && <p className="section-copy error-state">{apiErrorMessage(similar.error)}</p>}
                <div className="similar-list" data-testid="similar-player-list">
                  {(similar.data?.results || []).slice(0, 4).map((c) => (
                    <div className="similar-row" key={c.player_id} data-testid={`similar-player-${c.player_id}`}>
                      <div>
                        <Link to={`/players/${c.player_id}`} className="player-link">{c.player_name}</Link>
                        <small>{c.primary_archetype || c.position_group || "Role unavailable"}</small>
                      </div>
                      <b>{Math.round((c.overall_similarity ?? 0) * 100)}%</b>
                      <button
                        className="evidence-button"
                        onClick={() => setEvidence({
                          overall_similarity: c.overall_similarity,
                          statistical_similarity: c.statistical_similarity,
                          role_similarity: c.role_similarity,
                          contextual_similarity: c.contextual_similarity,
                          why_similar: c.why_similar,
                          why_different: c.why_different,
                        })}
                        data-testid={`similar-evidence-${c.player_id}`}
                      >
                        Why?
                      </button>
                    </div>
                  ))}
                  {similar.data?.results?.length === 0 && (
                    <p className="section-copy" data-testid="similarity-empty-state">Similarity engine returned no candidates yet.</p>
                  )}
                </div>
              </div>

              <DependencyPanel
                eyebrow="VALUATION"
                title="Valuation model not exposed"
                message={BACKEND_GAPS.valuation}
                testId="valuation-dependency-section"
              />
            </div>
          </div>
        </div>
      )}

      {tab === "contribution" && (
        <div className="stack-14" data-testid="profile-tab-contribution-content">
          {contributions.isLoading && (
            <p className="inline-state" data-testid="contributions-loading">Evaluating evidence-based player contributions…</p>
          )}
          {contributions.isError && (
            <div className="inline-state error-state" data-testid="contributions-error">
              <Database size={15} /> {apiErrorMessage(contributions.error)}
            </div>
          )}
          {contributions.data && (
            <>
              <div className="data-block" data-testid="contributions-summary-card">
                <div className="block-head">
                  <div>
                    <h3>Contribution Profile · {contributions.data.position_group} Benchmark</h3>
                    <small style={{ color: "var(--muted)" }}>
                      Evidence: {contributions.data.sample_minutes} mins across {contributions.data.sample_matches} matches (v{contributions.data.calculation_version})
                    </small>
                  </div>
                  <div className="badges">
                    <span
                      className={`badge ${
                        contributions.data.confidence === "HIGH"
                          ? "pos"
                          : contributions.data.confidence === "MEDIUM"
                          ? "model"
                          : contributions.data.confidence === "LOW"
                          ? "warn"
                          : "error"
                      }`}
                      data-testid="contribution-confidence-badge"
                    >
                      CONFIDENCE · {contributions.data.confidence}
                    </span>
                    {contributions.data.provenance && (
                      <button
                        className="evidence-button"
                        onClick={() => setEvidence(contributions.data.provenance)}
                        data-testid="contribution-evidence-button"
                      >
                        <Database size={12} /> Provenance
                      </button>
                    )}
                  </div>
                </div>

                {contributions.data.contribution_status === "INSUFFICIENT_SAMPLE" ||
                contributions.data.contribution_status === "INSUFFICIENT_DATA" ? (
                  <div className="dependency-section" style={{ marginTop: 12 }} data-testid="contribution-insufficient-gate">
                    <ShieldAlert size={18} />
                    <div>
                      <p className="eyebrow" style={{ marginBottom: 4, color: "var(--amber)" }}>DATA SUFFICIENCY GATE</p>
                      <h2>Insufficient Sample Evidence ({contributions.data.sample_minutes} mins)</h2>
                      <p className="section-copy">
                        A minimum of 270 competitive match minutes is required to reliably estimate per-90 rate metrics and dimensional percentiles without bias. Per Non-Negotiable Principle 2, scores are kept uncalculated rather than fabricated.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="analytics-grid" style={{ marginTop: 14 }}>
                    {/* Left: Dimension Bars */}
                    <div className="stack-14">
                      <div className="dimension-list" data-testid="contribution-dimensions-list">
                        {Object.entries(contributions.data.dimensions || {}).map(([dimKey, dim]) => (
                          <div key={dimKey} style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                              <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{dimKey}</span>
                              <b>{dim.score != null ? `${Math.round(dim.score * 100)} / 100` : "—"}</b>
                            </div>
                            <div className="dimension-track pos">
                              <i style={{ width: `${Math.max(2, Math.round((dim.score ?? 0) * 100))}%` }} />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <small style={{ color: "var(--muted)", fontSize: 11 }}>{dim.summary}</small>
                              {dim.percentile != null && (
                                <small style={{ color: "var(--teal)", fontWeight: 600, fontSize: 11 }}>
                                  P{dim.percentile}
                                </small>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Right: Explainable Strengths/Weaknesses & Action Value */}
                    <div className="stack-14">
                      <div className="data-block" style={{ background: "var(--surface-elevated)" }}>
                        <p className="eyebrow" style={{ color: "var(--teal)", marginBottom: 6 }}>DETERMINISTIC EVALUATION</p>
                        {contributions.data.strengths?.length > 0 && (
                          <div style={{ marginBottom: 12 }}>
                            <h4 style={{ fontSize: 12, color: "var(--text-primary)", marginBottom: 4 }}>Relative Strengths</h4>
                            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                              {contributions.data.strengths.map((s, i) => <li key={i}>{s}</li>)}
                            </ul>
                          </div>
                        )}
                        {contributions.data.weaknesses?.length > 0 && (
                          <div>
                            <h4 style={{ fontSize: 12, color: "var(--amber)", marginBottom: 4 }}>Relative Areas for Growth</h4>
                            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                              {contributions.data.weaknesses.map((w, i) => <li key={i}>{w}</li>)}
                            </ul>
                          </div>
                        )}
                      </div>

                      {/* Action Value & Threat Section */}
                      <div className="data-block" style={{ background: "var(--surface-elevated)" }} data-testid="action-value-summary">
                        <div className="block-head">
                          <p className="eyebrow" style={{ color: "var(--accent)", margin: 0 }}>ACTION VALUE FOUNDATION</p>
                          <span className="badge model">EMPIRICAL IMPACT</span>
                        </div>
                        {actionValues.data ? (
                          <div style={{ marginTop: 8 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                              <span>Net Action Impact / 90</span>
                              <strong style={{ color: "var(--teal)" }}>
                                {actionValues.data.action_value_per_90 != null
                                  ? `${actionValues.data.action_value_per_90 > 0 ? "+" : ""}${actionValues.data.action_value_per_90}`
                                  : actionValues.data.status === "INSUFFICIENT_SAMPLE"
                                  ? "INSUFFICIENT SAMPLE"
                                  : "—"}
                              </strong>
                            </div>
                            <small style={{ color: "var(--muted)", display: "block", marginBottom: 10 }}>
                              Status: {actionValues.data.status} · {actionValues.data.total_actions_evaluated} actions recorded.
                            </small>
                            <div style={{ padding: "8px 12px", background: "rgba(255,255,255,0.03)", borderRadius: 6, fontSize: 11, color: "var(--muted)" }}>
                              <strong style={{ color: "var(--text-secondary)" }}>Spatial Threat (xT) Gate: </strong>
                              {actionValues.data.data_limitation_reason || "2D pitch coordinates are preserved as NULL. Spatial transition threat modeling remains gated until tracking-grade data is connected."}
                            </div>
                          </div>
                        ) : (
                          <p className="section-copy">Action values loading…</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {tab === "benchmarks" && (
        <div className="stack-14" data-testid="profile-tab-benchmarks-content">
          {benchmarks.isLoading && <p className="inline-state">Loading peer benchmarks…</p>}
          {benchmarks.isError && (
            <div className="inline-state error-state">
              <Database size={15} /> {apiErrorMessage(benchmarks.error)}
            </div>
          )}
          {benchmarks.data && (
            <div className="data-block" data-testid="peer-benchmarks-block">
              <div className="block-head">
                <div>
                  <h3>Position Benchmark · {benchmarks.data.position_group} Group</h3>
                  <small style={{ color: "var(--muted)" }}>
                    Sample: {benchmarks.data.sample_minutes} mins · Peer population: {benchmarks.data.peer_sample_size} players
                  </small>
                </div>
                <span className={`badge ${benchmarks.data.benchmark_status === "EVALUATED" ? "pos" : "warn"}`} data-testid="benchmark-status-badge">
                  {benchmarks.data.benchmark_status}
                </span>
              </div>

              {benchmarks.data.benchmark_status === "INSUFFICIENT_SAMPLE" || benchmarks.data.benchmark_status === "INSUFFICIENT_DATA" ? (
                <div className="dependency-section" style={{ marginTop: 12 }} data-testid="benchmark-insufficient-gate">
                  <ShieldAlert size={18} />
                  <div>
                    <p className="eyebrow" style={{ marginBottom: 4, color: "var(--amber)" }}>DATA SUFFICIENCY GATE</p>
                    <h2>Insufficient Sample Minutes ({benchmarks.data.sample_minutes} mins)</h2>
                    <p className="section-copy">
                      Percentiles and Z-scores are withheld until the player reaches at least 270 competitive minutes.
                      This ensures that sample variances and single-match outliers do not skew peer percentiles.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="dimension-list" style={{ marginTop: 14 }} data-testid="benchmark-metrics-list">
                  {Object.entries(benchmarks.data.metrics || {}).map(([metricKey, bItem]) => (
                    <div key={metricKey} style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                        <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{metricKey.replaceAll("_", " ")}</span>
                        <b>
                          {bItem.value_p90 != null ? `${bItem.value_p90} / 90` : "—"}
                          {bItem.percentile != null && ` (P${bItem.percentile})`}
                        </b>
                      </div>
                      <div className="dimension-track pos">
                        <i style={{ width: `${Math.max(2, bItem.percentile ?? 0)}%` }} />
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
                        <span>Peer Mean: {bItem.peer_mean} (σ={bItem.peer_std})</span>
                        <span>Z-Score: {bItem.z_score != null ? (bItem.z_score > 0 ? `+${bItem.z_score}` : bItem.z_score) : "—"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === "trajectory" && (
        <div className="stack-14" data-testid="profile-tab-trajectory-content">
          {trajectory.isLoading && <p className="inline-state">Compiling chronological performance trajectory…</p>}
          {trajectory.isError && (
            <div className="inline-state error-state">
              <Database size={15} /> {apiErrorMessage(trajectory.error)}
            </div>
          )}
          {trajectory.data && (
            <div className="data-block" data-testid="player-trajectory-block">
              <div className="block-head">
                <div>
                  <h3>Longitudinal Performance Trajectory</h3>
                  <small style={{ color: "var(--muted)" }}>
                    {trajectory.data.total_recorded_matches} matches recorded · {trajectory.data.cumulative_minutes} cumulative minutes
                  </small>
                </div>
                <div className="badges">
                  <span className={`badge ${trajectory.data.trajectory_status === "EVALUATED" ? "pos" : "warn"}`} data-testid="trajectory-status-badge">
                    {trajectory.data.trajectory_status}
                  </span>
                  {trajectory.data.volatility_score != null && (
                    <span className="badge model">
                      VOLATILITY: {trajectory.data.volatility_score}
                    </span>
                  )}
                </div>
              </div>

              {trajectory.data.trajectory_status === "INSUFFICIENT_DATA" ? (
                <p className="section-copy" style={{ marginTop: 12 }}>
                  No competitive match records found to construct a longitudinal trajectory.
                </p>
              ) : (
                <>
                  <div className="player-table-wrap" style={{ border: 0, marginTop: 14 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>MATCH DATE</th>
                          <th className="num">MIN</th>
                          <th className="num">GOALS</th>
                          <th className="num">ASSISTS</th>
                          <th className="num">IMPACT</th>
                          <th className="num">RATING</th>
                          <th className="num">CUMULATIVE MIN</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(trajectory.data.timeline || []).map((t, idx) => (
                          <tr key={idx} data-testid={`trajectory-row-${idx}`}>
                            <td>{t.date ? new Date(t.date).toLocaleDateString() : "—"}</td>
                            <td className="num">{t.minutes}</td>
                            <td className="num">{t.goals}</td>
                            <td className="num">{t.assists}</td>
                            <td className="num" style={{ color: "var(--teal)", fontWeight: 600 }}>{t.match_impact}</td>
                            <td className="num">{t.rating ?? "—"}</td>
                            <td className="num">{t.cumulative_minutes}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {trajectory.data.seasonal_trend?.length > 0 && (
                    <div style={{ marginTop: 20 }}>
                      <p className="eyebrow" style={{ color: "var(--teal)", marginBottom: 8 }}>SEASONAL AGGREGATE PROGRESSION</p>
                      <div className="player-table-wrap" style={{ border: 0 }}>
                        <table>
                          <thead>
                            <tr>
                              <th>PERIOD / ROUND</th>
                              <th className="num">MATCHES</th>
                              <th className="num">MIN</th>
                              <th className="num">GOALS</th>
                              <th className="num">ASSISTS</th>
                              <th className="num">AVG RATING</th>
                            </tr>
                          </thead>
                          <tbody>
                            {trajectory.data.seasonal_trend.map((s, idx) => (
                              <tr key={idx}>
                                <td>{s.period}</td>
                                <td className="num">{s.matches}</td>
                                <td className="num">{s.minutes}</td>
                                <td className="num">{s.goals}</td>
                                <td className="num">{s.assists}</td>
                                <td className="num">{s.avg_rating ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {tab === "performance" && (
        <div className="stack-14" data-testid="profile-tab-performance-content">
          <div className="data-block">
            <div className="block-head"><h3>Season records</h3><span className="confidence-note">from /api/v1/players</span></div>
            {!item.season_stats || item.season_stats.length === 0 ? (
              <p className="section-copy">No season records returned by the connected backend.</p>
            ) : (
              <div className="player-table-wrap" style={{ border: 0 }}>
                <table>
                  <thead>
                    <tr>
                      <th>COMPETITION</th>
                      <th>SEASON</th>
                      <th className="num">MIN</th>
                      <th className="num">APP</th>
                      <th className="num">G</th>
                      <th className="num">A</th>
                      <th className="num">RATING</th>
                    </tr>
                  </thead>
                  <tbody>
                    {item.season_stats.map((s, i) => (
                      <tr key={i} data-testid={`season-row-${i}`}>
                        <td>{s.competition_name || s.competition_id || "—"}</td>
                        <td>{s.season || "—"}</td>
                        <td className="num">{s.minutes ?? "—"}</td>
                        <td className="num">{s.appearances ?? "—"}</td>
                        <td className="num">{s.goals ?? "—"}</td>
                        <td className="num">{s.assists ?? "—"}</td>
                        <td className="num">{s.rating ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <DependencyPanel
            eyebrow="ADVANCED METRICS"
            title="xG / xA / progressive events pending"
            message="Advanced per-90 features (xG, xA, progressive passes, defensive actions, pressures) will surface here once the backend exposes them per-competition."
            testId="performance-dependency-section"
          />
        </div>
      )}

      {tab === "role" && (
        <div className="stack-14" data-testid="profile-tab-role-content">
          <div className="analytics-grid">
            <div className="data-block">
              <div className="block-head">
                <h3>{role.data?.primary_archetype || "Role classification"}</h3>
                {role.data?.confidence != null && <span className="badge model">MODEL · {(role.data.confidence * 100).toFixed(0)}%</span>}
              </div>
              <p className="section-copy">
                {role.data?.summary || (role.isError ? apiErrorMessage(role.error) : "Fetching role evidence…")}
              </p>
              <div className="dimension-list" data-testid="role-dimensions">
                {Object.entries(roleProfile.data?.profile_scores || {}).slice(0, 12).map(([key, value]) => (
                  <div key={key}>
                    <span>{key.replaceAll("_", " ")}</span>
                    <div className="dimension-track pos"><i style={{ width: `${Math.max(2, Math.round(value * 100))}%` }} /></div>
                    <b>{Math.round(value * 100)}</b>
                  </div>
                ))}
              </div>
            </div>
            <div className="data-block">
              <div className="block-head"><h3>Percentile radar</h3><span className="badge model"><Radar size={10} /> ROLE MODEL</span></div>
              {radarData.length > 0 ? (
                <PerformanceRadar data={radarData} testId="role-tab-radar" />
              ) : (
                <p className="section-copy">Role profile scores not yet available for this player.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === "similarity" && (
        <div className="stack-14" data-testid="profile-tab-similarity-content">
          <div className="data-block">
            <div className="block-head">
              <h3>Comparable players</h3>
              <div className="badges">
                <span className="badge model" style={{ textTransform: "uppercase" }}>MODE · {similarityMode}</span>
                {similar.data?.embedding_version && (
                  <span className="badge model">EMBEDDING · {similar.data.embedding_version}</span>
                )}
              </div>
            </div>
            {/* Mode selection buttons */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }} data-testid="similarity-mode-selector">
              {["composite", "contribution", "role", "tactical", "replacement"].map((m) => (
                <button
                  key={m}
                  className="outline-button"
                  style={{
                    textTransform: "capitalize",
                    fontSize: 12,
                    padding: "4px 10px",
                    background: similarityMode === m ? "rgba(45, 212, 191, 0.15)" : "transparent",
                    borderColor: similarityMode === m ? "var(--teal)" : "var(--border)",
                    color: similarityMode === m ? "var(--teal)" : "var(--text-secondary)",
                    cursor: "pointer",
                  }}
                  onClick={() => setSimilarityMode(m)}
                  data-testid={`sim-mode-${m}`}
                >
                  {m}
                </button>
              ))}
            </div>
            {similar.isLoading && <p className="section-copy">Loading similarity evidence…</p>}
            {similar.isError && <p className="section-copy error-state">{apiErrorMessage(similar.error)}</p>}
            <div className="similar-list">
              {(similar.data?.results || []).map((c) => (
                <div className="similar-row" key={c.player_id}>
                  <div>
                    <Link to={`/players/${c.player_id}`} className="player-link">{c.player_name}</Link>
                    <small>{c.primary_archetype || c.position_group || "Role unavailable"}</small>
                  </div>
                  <b>{Math.round((c.overall_similarity ?? 0) * 100)}%</b>
                  <button className="evidence-button" onClick={() => setEvidence({
                    overall_similarity: c.overall_similarity,
                    statistical_similarity: c.statistical_similarity,
                    role_similarity: c.role_similarity,
                    contextual_similarity: c.contextual_similarity,
                    why_similar: c.why_similar,
                    why_different: c.why_different,
                  })}>
                    Why?
                  </button>
                </div>
              ))}
              {similar.data?.results?.length === 0 && (
                <p className="section-copy">The similarity engine returned no candidates.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === "tactical" && (
        <div className="stack-14" data-testid="profile-tab-tactical-content">
          {tacticalFit.isLoading && <p className="section-copy">Evaluating tactical fit…</p>}
          {tacticalFit.isError && (
            <div className="inline-state error-state">
              <Database size={14} /> {apiErrorMessage(tacticalFit.error)}
            </div>
          )}
          {tacticalFit.data && (
            <div className="data-block" data-testid="tactical-profile-block">
              <div className="block-head">
                <div>
                  <h3>System Compatibility · {tacticalFit.data.formation} ({tacticalFit.data.target_role})</h3>
                  <small style={{ color: "var(--muted)" }}>Target position: {tacticalFit.data.target_position} · Status: {tacticalFit.data.fit_status}</small>
                </div>
                <span className={`badge ${tacticalFit.data.fit_status === "INSUFFICIENT_DATA" ? "warn" : "pos"}`}>
                  {tacticalFit.data.fit_status === "INSUFFICIENT_DATA"
                    ? "INSUFFICIENT SAMPLE"
                    : `FIT: ${(tacticalFit.data.fit_score * 100).toFixed(0)}% (${tacticalFit.data.confidence})`}
                </span>
              </div>
              {tacticalFit.data.fit_status === "INSUFFICIENT_DATA" ? (
                <p className="section-copy" style={{ marginTop: 12 }}>
                  Insufficient competitive match minutes recorded to evaluate tactical compatibility dimensions without bias.
                </p>
              ) : (
                <div className="dimension-list" style={{ marginTop: 14 }}>
                  <div>
                    <span>Position fit</span>
                    <div className="dimension-track pos"><i style={{ width: `${Math.round((tacticalFit.data.position_fit ?? 0) * 100)}%` }} /></div>
                    <b>{tacticalFit.data.position_fit != null ? `${Math.round(tacticalFit.data.position_fit * 100)}%` : "—"}</b>
                  </div>
                  <div>
                    <span>Role archetype fit</span>
                    <div className="dimension-track pos"><i style={{ width: `${Math.round((tacticalFit.data.role_fit ?? 0) * 100)}%` }} /></div>
                    <b>{tacticalFit.data.role_fit != null ? `${Math.round(tacticalFit.data.role_fit * 100)}%` : "—"}</b>
                  </div>
                  <div>
                    <span>Dimension requirement fit</span>
                    <div className="dimension-track pos"><i style={{ width: `${Math.round((tacticalFit.data.dimension_fit ?? 0) * 100)}%` }} /></div>
                    <b>{tacticalFit.data.dimension_fit != null ? `${Math.round(tacticalFit.data.dimension_fit * 100)}%` : "—"}</b>
                  </div>
                </div>
              )}
              {tacticalFit.data.why_fit?.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <p className="eyebrow" style={{ color: "var(--teal)" }}>TACTICAL STRENGTHS</p>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    {tacticalFit.data.why_fit.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
          <div className="section-copy" style={{ marginTop: 10 }}>
            Deep-dive into team-specific scenarios in the <Link to={`/tactical/fit?player=${item.id}`} className="row-action">Tactical fit workspace →</Link>
          </div>
        </div>
      )}

      {tab === "market" && (
        <div className="stack-14" data-testid="profile-tab-market-content">
          {/* Baseline Valuation Card */}
          <div className="data-block" data-testid="market-valuation-baseline-card">
            <div className="block-head">
              <div>
                <h3 style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Target size={14} color="var(--teal)" /> Deterministic Valuation Baseline · {player.data?.name}
                </h3>
                <small style={{ color: "var(--muted)" }}>
                  {valuationBaseline.data?.methodology || "Deterministic Comparable Median with Empirical Age Curve"}
                </small>
              </div>
              <div className="badges">
                <span className={`badge ${valuationBaseline.data?.valuation_status === "VALUATION_AVAILABLE" ? "pos" : "warn"}`}>
                  {valuationBaseline.data?.valuation_status || "EVALUATING"}
                </span>
                {valuationBaseline.data?.confidence && (
                  <span className={`badge ${valuationBaseline.data.confidence === "HIGH" ? "pos" : valuationBaseline.data.confidence === "MEDIUM" ? "model" : "warn"}`}>
                    CONFIDENCE · {valuationBaseline.data.confidence}
                  </span>
                )}
              </div>
            </div>

            {valuationBaseline.isLoading && <p className="section-copy">Calculating deterministic valuation baseline…</p>}
            {valuationBaseline.isError && (
              <p className="section-copy error-state">{apiErrorMessage(valuationBaseline.error)}</p>
            )}

            {valuationBaseline.data && (
              <div style={{ marginTop: 12 }}>
                {valuationBaseline.data.valuation_status === "VALUATION_AVAILABLE" ? (
                  <div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap", marginBottom: 12 }}>
                      <span style={{ fontSize: 28, fontWeight: 700, color: "var(--teal)", fontFamily: "JetBrains Mono, monospace" }}>
                        €{(valuationBaseline.data.estimated_value_eur / 1_000_000).toFixed(1)}M
                      </span>
                      {valuationBaseline.data.range_status === "RANGE_AVAILABLE" ? (
                        <span style={{ fontSize: 14, color: "var(--text-secondary)", fontFamily: "JetBrains Mono, monospace" }}>
                          Range: €{(valuationBaseline.data.lower_bound_eur / 1_000_000).toFixed(1)}M – €{(valuationBaseline.data.upper_bound_eur / 1_000_000).toFixed(1)}M (IQR 50%)
                        </span>
                      ) : (
                        <span className="badge warn" style={{ fontSize: 11 }}>
                          RANGE NOT AVAILABLE (n &lt; 5 comps)
                        </span>
                      )}
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, fontSize: 12 }}>
                      <div className="profile-metric">
                        <span>Comparable Cohort Median</span>
                        <strong>€{(valuationBaseline.data.cohort_median_fee_eur / 1_000_000).toFixed(1)}M</strong>
                        <small>Based on {valuationBaseline.data.comparable_sample_size} verified transfers</small>
                      </div>
                      <div className="profile-metric">
                        <span>Age Curve Multiplier</span>
                        <strong>{valuationBaseline.data.adjustments?.age_curve_factor ? `×${valuationBaseline.data.adjustments.age_curve_factor}` : "—"}</strong>
                        <small>Age: {valuationBaseline.data.adjustments?.age_at_as_of ?? "—"} yrs ({valuationBaseline.data.adjustments?.position_group ?? "—"})</small>
                      </div>
                      <div className="profile-metric">
                        <span>Model Type</span>
                        <strong>Deterministic Non-ML</strong>
                        <small>Zero fabrication baseline (v{valuationBaseline.data.calculation_version})</small>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: "10px 14px", background: "rgba(245, 158, 11, 0.08)", borderRadius: 6, border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                    <p style={{ margin: 0, fontSize: 13, color: "var(--amber)", fontWeight: 600 }}>
                      Valuation Baseline Unavailable
                    </p>
                    <p style={{ margin: "4px 0 0 0", fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                      Insufficient verified comparable transfers (found {valuationBaseline.data.comparable_sample_size}, minimum required is 3). In accordance with Zero Fabrication principles, synthetic fees are never generated.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Historical Transfer Record */}
          <div className="data-block" data-testid="market-transfers-history-card">
            <div className="block-head">
              <div>
                <h3>Historical Transfer Record</h3>
                <small style={{ color: "var(--muted)" }}>Verified transaction envelopes with semantic fee categorization</small>
              </div>
              <span className="badge model">
                {playerTransfers.data?.length || 0} TRANSACTIONS
              </span>
            </div>

            {playerTransfers.isLoading && <p className="section-copy">Loading transfer history…</p>}
            {playerTransfers.isError && (
              <p className="section-copy error-state">{apiErrorMessage(playerTransfers.error)}</p>
            )}

            {playerTransfers.data && playerTransfers.data.length === 0 && (
              <p className="section-copy" style={{ margin: "10px 0" }}>No verified historical transfers recorded for this player in the database.</p>
            )}

            {playerTransfers.data && playerTransfers.data.length > 0 && (
              <div className="evidence-table-wrap" style={{ marginTop: 10 }}>
                <table className="evidence-table" style={{ width: "100%", textAlign: "left", fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>From</th>
                      <th>To</th>
                      <th>Type</th>
                      <th>Fee / Status</th>
                      <th>Data Quality</th>
                    </tr>
                  </thead>
                  <tbody>
                    {playerTransfers.data.map((t) => {
                      const isUnknown = t.fee_status === "UNKNOWN_FEE" || t.fee_status === "UNDISCLOSED";
                      const isFree = t.fee_status === "FREE_TRANSFER";
                      const isLoan = t.is_loan || (t.transfer_type && t.transfer_type.toLowerCase().includes("loan"));
                      let feeDisplay = "UNDISCLOSED / UNKNOWN";
                      if (isFree) feeDisplay = "FREE TRANSFER";
                      else if (t.fee_eur_normalized != null && t.fee_eur_normalized > 0) {
                        feeDisplay = `€${(t.fee_eur_normalized / 1_000_000).toFixed(1)}M`;
                      } else if (isLoan) feeDisplay = "LOAN";

                      return (
                        <tr key={t.id}>
                          <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{t.transfer_date || "—"}</td>
                          <td>{t.from_club_name || "—"}</td>
                          <td><strong>{t.to_club_name || "—"}</strong></td>
                          <td><span className="badge info">{t.transfer_type || "Transfer"}</span></td>
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{ fontWeight: isUnknown ? 400 : 600, color: isUnknown ? "var(--muted)" : isFree ? "var(--teal)" : "var(--text-primary)" }}>
                                {feeDisplay}
                              </span>
                              <span className={`badge ${isFree ? "pos" : isUnknown ? "warn" : "model"}`} style={{ fontSize: 10 }}>
                                {t.fee_status}
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className={`badge ${t.data_quality_status === "HIGH" ? "pos" : t.data_quality_status === "MEDIUM" ? "model" : "warn"}`} style={{ fontSize: 10 }}>
                              {t.data_quality_status}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Comparable Transactions Engine */}
          <div className="data-block" data-testid="market-comparables-card">
            <div className="block-head">
              <div>
                <h3>Comparable Transfer Transactions</h3>
                <small style={{ color: "var(--muted)" }}>Multi-dimensional similarity matching across role, age, contribution, and recency</small>
              </div>
              <span className="badge model">
                {comparables.data?.comparables_count || 0} MATCHES
              </span>
            </div>

            {comparables.isLoading && <p className="section-copy">Matching historical transactions…</p>}
            {comparables.isError && (
              <p className="section-copy error-state">{apiErrorMessage(comparables.error)}</p>
            )}

            {comparables.data?.comparables?.length === 0 && (
              <p className="section-copy" style={{ margin: "10px 0" }}>No comparable transactions meeting the similarity threshold were identified.</p>
            )}

            {comparables.data?.comparables && comparables.data.comparables.length > 0 && (
              <div className="similar-list" style={{ marginTop: 10 }}>
                {comparables.data.comparables.map((c) => (
                  <div className="similar-row" key={c.transfer_id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                        <Link to={`/players/${c.player_id}`} className="player-link" style={{ fontWeight: 600 }}>
                          {c.player_name}
                        </Link>
                        <span style={{ fontSize: 11, color: "var(--muted)" }}>
                          {c.transfer_date} · {c.from_club_name || "—"} → {c.to_club_name || "—"}
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap", fontSize: 11, color: "var(--text-secondary)" }}>
                        <span>Role: {c.role_archetype || c.position_group || "—"}</span>
                        <span>·</span>
                        <span>Age at transfer: {c.player_age_at_transfer ?? "—"} yrs</span>
                        <span>·</span>
                        <span style={{ fontWeight: 600, color: "var(--teal)" }}>
                          {c.fee_eur_normalized ? `€${(c.fee_eur_normalized / 1_000_000).toFixed(1)}M (${c.fee_status})` : c.fee_status}
                        </span>
                      </div>
                      {c.similarity_breakdown && (
                        <div style={{ display: "flex", gap: 6, marginTop: 4, fontSize: 10 }}>
                          <span className="badge model">Role: {Math.round((c.similarity_breakdown.role ?? 0) * 100)}%</span>
                          <span className="badge model">Age: {Math.round((c.similarity_breakdown.age ?? 0) * 100)}%</span>
                          <span className="badge model">Contrib: {Math.round((c.similarity_breakdown.contribution ?? 0) * 100)}%</span>
                          <span className="badge model">Recency: {Math.round((c.similarity_breakdown.recency ?? 0) * 100)}%</span>
                        </div>
                      )}
                    </div>
                    <div style={{ textAlign: "right", minWidth: 60 }}>
                      <strong style={{ fontSize: 16, color: "var(--teal)", fontFamily: "JetBrains Mono, monospace" }}>
                        {Math.round((c.similarity_score ?? 0) * 100)}%
                      </strong>
                      <div style={{ fontSize: 10, color: "var(--muted)" }}>SIMILARITY</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <DependencyPanel
            eyebrow="TRANSFER RISK"
            title="Risk classification pending"
            message={BACKEND_GAPS.transferRisk}
            testId="risk-dependency-section"
          />
        </div>
      )}

      {tab === "evidence" && (
        <div className="stack-14" data-testid="profile-tab-evidence-content">
          <div className="data-block">
            <div className="block-head">
              <h3>Feature snapshot</h3>
              {features.data?.provenance && (
                <button className="evidence-button" onClick={() => setEvidence(features.data.provenance)} data-testid="feature-evidence-button">
                  <Database size={12} /> Provenance
                </button>
              )}
            </div>
            {features.isLoading && <p className="section-copy">Loading feature snapshot…</p>}
            {features.isError && <p className="section-copy error-state">{apiErrorMessage(features.error)}</p>}
            {features.data?.features && (
              <div className="dimension-list" data-testid="feature-list">
                {Object.entries(features.data.features).slice(0, 16).map(([key, value]) => (
                  <div key={key}>
                    <span>{key.replaceAll("_", " ")}</span>
                    <div className="dimension-track"><i style={{ width: `${Math.min(100, Math.max(2, Math.abs(Number(value) || 0) * 100))}%` }} /></div>
                    <b>{typeof value === "number" ? value.toFixed(2) : String(value).slice(0, 6)}</b>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <EvidenceDrawer title={`${item.name} · evidence`} evidence={evidence} onClose={() => setEvidence(null)} />
    </section>
  );
}
