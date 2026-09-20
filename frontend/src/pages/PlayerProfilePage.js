import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Database, GitCompare, ShieldAlert, Sparkles, Target } from "lucide-react";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import PerformanceRadar from "@/components/PerformanceRadar";
import {
  apiErrorMessage, BACKEND_GAPS, getPlayer, getPlayerFeatures,
  getPlayerRole, getPlayerRoleProfile, getSimilarPlayers,
} from "@/lib/footballApi";

const Metric = ({ label, value, sub, testId }) => (
  <div className="profile-metric" data-testid={testId}>
    <span>{label}</span>
    <strong>{value !== null && value !== undefined && value !== "" ? value : "—"}</strong>
    {sub && <small>{sub}</small>}
  </div>
);

const DependencyCard = ({ eyebrow, title, message, testId }) => (
  <section className="profile-section dependency-section" data-testid={testId}>
    <ShieldAlert size={18} />
    <div>
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p className="section-copy">{message}</p>
      <span className="badge warn">BACKEND DEPENDENCY</span>
    </div>
  </section>
);

export default function PlayerProfilePage() {
  const { playerId } = useParams();
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
      .map(([label, value]) => ({ label: label.replaceAll("_", " "), value: Math.max(0, Math.min(1, Number(value) || 0)) }));
  }, [roleProfile.data]);

  if (player.isLoading) return <p className="inline-state" data-testid="player-profile-loading">Loading player intelligence…</p>;
  if (player.isError) return (
    <div className="inline-state error-state" data-testid="player-profile-error">
      <Database size={18} /> {apiErrorMessage(player.error)}
    </div>
  );

  const item = player.data;
  const latest = item.season_stats?.[0];

  return (
    <section className="intelligence-page profile-page" data-testid="player-profile-page">
      <Link to="/players" className="back-link" data-testid="player-profile-back">
        <ArrowLeft size={14} /> Player discovery
      </Link>

      <header className="profile-header">
        <div className="profile-avatar" data-testid="player-profile-avatar">{item.name.slice(0, 2).toUpperCase()}</div>
        <div>
          <p className="eyebrow" data-testid="profile-eyebrow">PLAYER INTELLIGENCE</p>
          <h1 data-testid="player-profile-name">{item.name}</h1>
          <p className="workspace-subtitle" data-testid="player-profile-meta">
            {item.primary_position || "Position unavailable"} · {item.nationality || "Nationality unavailable"} · {item.preferred_foot || "Foot unknown"}
          </p>
        </div>
        <div className="profile-header-actions" data-testid="profile-actions">
          <Link to={`/players/compare?ids=${item.id}`} className="outline-button" data-testid="profile-action-compare">
            <GitCompare size={14} /> Compare
          </Link>
          <Link to={`/players/similarity?player=${item.id}`} className="outline-button" data-testid="profile-action-similar">
            <Sparkles size={14} /> Similar
          </Link>
          <Link to={`/tactical/fit?player=${item.id}`} className="outline-button" data-testid="profile-action-fit">
            <Target size={14} /> Tactical fit
          </Link>
        </div>
      </header>

      <div className="metric-grid" data-testid="player-snapshot-grid">
        <Metric label="Minutes" value={latest?.minutes} testId="player-metric-minutes" />
        <Metric label="Goals" value={latest?.goals} testId="player-metric-goals" />
        <Metric label="Assists" value={latest?.assists} testId="player-metric-assists" />
        <Metric label="Rating" value={latest?.rating} sub={latest?.competition_id ? `Comp ${latest.competition_id}` : null} testId="player-metric-rating" />
      </div>

      <div className="profile-sections">
        <section className="profile-section" data-testid="role-profile-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">ROLE PROFILE</p>
              <h2>{role.data?.primary_archetype || (role.isError ? "Role unavailable" : "Loading role…")}</h2>
              {role.data?.confidence != null && (
                <span className="badge model" data-testid="role-confidence-badge">
                  MODEL · {(role.data.confidence * 100).toFixed(0)}% CONFIDENCE
                </span>
              )}
            </div>
            {roleProfile.data?.provenance && (
              <button className="evidence-button" onClick={() => setEvidence(roleProfile.data.provenance)} data-testid="role-evidence-button">
                <Database size={13} /> Evidence
              </button>
            )}
          </div>
          <p className="section-copy" data-testid="role-profile-summary">
            {role.data?.summary || (role.isError ? apiErrorMessage(role.error) : "Fetching role evidence from the connected backend…")}
          </p>
          <div className="dimension-list" data-testid="role-dimensions">
            {Object.entries(roleProfile.data?.profile_scores || {}).slice(0, 8).map(([key, value]) => (
              <div key={key}>
                <span>{key.replaceAll("_", " ")}</span>
                <div className="dimension-track pos"><i style={{ width: `${Math.max(2, Math.round(value * 100))}%` }} /></div>
                <b>{Math.round(value * 100)}</b>
              </div>
            ))}
          </div>
        </section>

        <section className="profile-section" data-testid="performance-radar-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">PERFORMANCE PROFILE</p>
              <h2>Role percentile view</h2>
              <span className="confidence-note">Categories driven by backend feature definitions</span>
            </div>
          </div>
          {radarData.length > 0 ? (
            <PerformanceRadar data={radarData} testId="player-performance-radar" />
          ) : (
            <p className="section-copy" data-testid="radar-empty-state">
              Role profile data not yet available for this player from the connected backend.
            </p>
          )}
        </section>

        <section className="profile-section" data-testid="similarity-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SIMILARITY</p>
              <h2>Comparable players</h2>
              <span className="confidence-note" data-testid="similarity-contract-note">Multi-dimensional similarity output</span>
            </div>
          </div>
          {similar.isLoading && <p className="section-copy">Loading similarity evidence…</p>}
          {similar.isError && <p className="section-copy error-state">{apiErrorMessage(similar.error)}</p>}
          <div className="similar-list" data-testid="similar-player-list">
            {(similar.data?.results || []).slice(0, 6).map((candidate) => (
              <div className="similar-row" key={candidate.player_id} data-testid={`similar-player-${candidate.player_id}`}>
                <div>
                  <Link to={`/players/${candidate.player_id}`} className="player-link">{candidate.player_name}</Link>
                  <small>{candidate.primary_archetype || candidate.position_group || "Role unavailable"}</small>
                </div>
                <b>{Math.round((candidate.overall_similarity ?? 0) * 100)}%</b>
                <button
                  className="evidence-button"
                  onClick={() => setEvidence({
                    overall_similarity: candidate.overall_similarity,
                    statistical_similarity: candidate.statistical_similarity,
                    role_similarity: candidate.role_similarity,
                    contextual_similarity: candidate.contextual_similarity,
                    why_similar: candidate.why_similar,
                    why_different: candidate.why_different,
                  })}
                  data-testid={`similar-evidence-${candidate.player_id}`}
                >
                  Why?
                </button>
              </div>
            ))}
            {similar.data?.results?.length === 0 && (
              <p className="section-copy" data-testid="similarity-empty-state">Similarity engine returned no candidates for this player yet.</p>
            )}
          </div>
        </section>

        <section className="profile-section" data-testid="feature-evidence-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">FEATURE SNAPSHOT</p>
              <h2>Backend feature vector</h2>
              <span className="confidence-note">Feature version and snapshot are surfaced from provenance</span>
            </div>
            {features.data?.provenance && (
              <button className="evidence-button" onClick={() => setEvidence(features.data.provenance)} data-testid="feature-evidence-button">
                <Database size={13} /> Feature evidence
              </button>
            )}
          </div>
          {features.isLoading && <p className="section-copy">Loading feature snapshot…</p>}
          {features.isError && <p className="section-copy error-state">{apiErrorMessage(features.error)}</p>}
          {features.data?.features && (
            <div className="dimension-list" data-testid="feature-list">
              {Object.entries(features.data.features).slice(0, 8).map(([key, value]) => (
                <div key={key}>
                  <span>{key.replaceAll("_", " ")}</span>
                  <div className="dimension-track"><i style={{ width: `${Math.min(100, Math.max(2, Math.abs(Number(value) || 0) * 100))}%` }} /></div>
                  <b>{typeof value === "number" ? value.toFixed(2) : String(value).slice(0, 6)}</b>
                </div>
              ))}
            </div>
          )}
        </section>

        <DependencyCard
          eyebrow="VALUATION"
          title="Valuation model not yet exposed"
          message={BACKEND_GAPS.valuation + " When exposed, this card will display estimated value, uncertainty interval, and model version."}
          testId="valuation-dependency-section"
        />
        <DependencyCard
          eyebrow="TACTICAL FIT"
          title="Team-system fit not yet exposed"
          message={BACKEND_GAPS.tacticalFit + " No fit score is fabricated in this view."}
          testId="tactical-fit-dependency-section"
        />
        <DependencyCard
          eyebrow="TRANSFER RISK"
          title="Risk classification not yet exposed"
          message={BACKEND_GAPS.transferRisk + " Performance, adaptation, and financial risk will surface here once the backend exposes them."}
          testId="risk-dependency-section"
        />
      </div>

      <EvidenceDrawer title={`${item.name} · evidence`} evidence={evidence} onClose={() => setEvidence(null)} />
    </section>
  );
}
