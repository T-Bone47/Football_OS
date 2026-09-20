import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, Database, GitCompare, Radar, ShieldAlert,
  Sparkles, Target, TrendingUp,
} from "lucide-react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import PerformanceRadar from "@/components/PerformanceRadar";
import AddToShortlistButton from "@/components/AddToShortlistButton";
import {
  apiErrorMessage, BACKEND_GAPS, getPlayer, getPlayerFeatures,
  getPlayerRole, getPlayerRoleProfile, getSimilarPlayers,
} from "@/lib/footballApi";

const TABS = [
  { id: "overview", label: "Overview" },
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

  const player = useQuery({ queryKey: ["player", playerId], queryFn: () => getPlayer(playerId), retry: false });
  const role = useQuery({ queryKey: ["player-role", playerId], queryFn: () => getPlayerRole(playerId), enabled: !!player.data, retry: false });
  const roleProfile = useQuery({ queryKey: ["player-role-profile", playerId], queryFn: () => getPlayerRoleProfile(playerId), enabled: !!player.data, retry: false });
  const features = useQuery({ queryKey: ["player-features", playerId], queryFn: () => getPlayerFeatures(playerId), enabled: !!player.data, retry: false });
  const similar = useQuery({ queryKey: ["player-similar", playerId], queryFn: () => getSimilarPlayers(playerId), enabled: !!player.data, retry: false });

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
              {similar.data?.embedding_version && (
                <span className="badge model">EMBEDDING · {similar.data.embedding_version}</span>
              )}
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
          <DependencyPanel
            eyebrow="TACTICAL FIT"
            title="Team-system fit not yet exposed"
            message={BACKEND_GAPS.tacticalFit}
            testId="tactical-fit-dependency-section"
          />
          <div className="section-copy">
            Configure a team and role in the <Link to={`/tactical/fit?player=${item.id}`} className="row-action">Tactical fit workspace</Link>.
          </div>
        </div>
      )}

      {tab === "market" && (
        <div className="stack-14" data-testid="profile-tab-market-content">
          <DependencyPanel
            eyebrow="VALUATION"
            title="Valuation model not exposed"
            message={BACKEND_GAPS.valuation}
            testId="valuation-market-dependency-section"
          />
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
