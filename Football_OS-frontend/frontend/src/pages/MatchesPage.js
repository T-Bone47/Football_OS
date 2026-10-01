import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Database, ShieldAlert } from "lucide-react";
import { apiErrorMessage, BACKEND_GAPS, getMatch, getMatches, getMatchEvents, getMatchLineups, getMatchPrediction, getMatchStatistics } from "@/lib/footballApi";

function MatchList() {
  const matches = useQuery({ queryKey: ["matches"], queryFn: () => getMatches({ limit: 50 }), retry: false });
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MATCH INTELLIGENCE</p>
          <h1 data-testid="page-title">Match center</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            A calm view of the connected fixture universe. Prediction and model context appear once the backend exposes them.
          </p>
        </div>
        <span className="contract-badge">/api/v1/matches</span>
      </div>

      {matches.isLoading && <p className="inline-state" data-testid="matches-loading">Loading fixture list…</p>}
      {matches.isError && (
        <div className="inline-state error-state" data-testid="matches-error"><Database size={17} /> {apiErrorMessage(matches.error)}</div>
      )}
      {matches.data && (
        <div className="player-table-wrap" data-testid="matches-table">
          <table>
            <thead>
              <tr>
                <th>HOME</th>
                <th>AWAY</th>
                <th>COMPETITION</th>
                <th>DATE</th>
                <th>STATUS</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {matches.data.map((m) => (
                <tr key={m.id} data-testid={`match-row-${m.id}`}>
                  <td>{m.home_club_name || m.home_club_id || "—"}</td>
                  <td>{m.away_club_name || m.away_club_id || "—"}</td>
                  <td>{m.competition_name || m.competition_id || "—"}</td>
                  <td>{m.kickoff_time || m.date || "—"}</td>
                  <td>{m.status || "—"}</td>
                  <td><Link to={`/matches/${m.id}`} className="row-action">Open →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
          {matches.data.length === 0 && <div className="table-empty">No matches surfaced by the connected backend yet.</div>}
        </div>
      )}
    </>
  );
}

function MatchDetail() {
  const { matchId } = useParams();
  const match = useQuery({ queryKey: ["match", matchId], queryFn: () => getMatch(matchId), retry: false });
  const events = useQuery({ queryKey: ["match-events", matchId], queryFn: () => getMatchEvents(matchId), enabled: !!match.data, retry: false });
  const lineups = useQuery({ queryKey: ["match-lineups", matchId], queryFn: () => getMatchLineups(matchId), enabled: !!match.data, retry: false });
  const stats = useQuery({ queryKey: ["match-stats", matchId], queryFn: () => getMatchStatistics(matchId), enabled: !!match.data, retry: false });

  if (match.isLoading) return <p className="inline-state" data-testid="match-loading">Loading match…</p>;
  if (match.isError) return <div className="inline-state error-state" data-testid="match-error"><Database size={17} /> {apiErrorMessage(match.error)}</div>;

  const m = match.data;
  return (
    <>
      <Link to="/matches" className="back-link" data-testid="match-back"><ArrowLeft size={13} /> Match center</Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MATCH · {m.competition_name || m.competition_id || "Competition"}</p>
          <h1 data-testid="match-heading">{m.home_club_name || m.home_club_id} vs {m.away_club_name || m.away_club_id}</h1>
          <p className="workspace-subtitle">{m.kickoff_time || m.date || "Kickoff unavailable"} · {m.status || "Status unknown"}</p>
        </div>
        <span className="badge model">MODEL · CONTEXT</span>
      </div>

      <div className="split-columns" style={{ marginTop: 24 }}>
        <div className="data-block" data-testid="match-stats-block">
          <h3>Team statistics</h3>
          {stats.isLoading && <p className="section-copy">Loading team statistics…</p>}
          {stats.isError && <p className="section-copy error-state">{apiErrorMessage(stats.error)}</p>}
          {stats.data && stats.data.length > 0 ? (
            <div className="kv-list">
              {stats.data.slice(0, 8).map((s, i) => (
                <div key={i}><span>{s.name || s.type || "Metric"}</span><b>{s.value ?? "—"}</b></div>
              ))}
            </div>
          ) : stats.data ? (
            <p className="section-copy">No statistics returned by the backend for this match.</p>
          ) : null}
        </div>

        <div className="data-block" data-testid="match-lineups-block">
          <h3>Lineups</h3>
          {lineups.isLoading && <p className="section-copy">Loading lineups…</p>}
          {lineups.isError && <p className="section-copy error-state">{apiErrorMessage(lineups.error)}</p>}
          {lineups.data && lineups.data.length > 0 ? (
            <div className="kv-list">
              {lineups.data.slice(0, 10).map((l, i) => (
                <div key={i}><span>{l.player_name || l.player_id}</span><b>{l.position || "—"}</b></div>
              ))}
            </div>
          ) : lineups.data ? (
            <p className="section-copy">Lineups not yet published for this match.</p>
          ) : null}
        </div>
      </div>

      <div className="data-block" style={{ marginTop: 20 }} data-testid="match-events-block">
        <h3>Timeline</h3>
        {events.isLoading && <p className="section-copy">Loading events…</p>}
        {events.isError && <p className="section-copy error-state">{apiErrorMessage(events.error)}</p>}
        {events.data && events.data.length > 0 ? (
          <div className="kv-list">
            {events.data.slice(0, 20).map((ev, i) => (
              <div key={i}>
                <span>{ev.minute != null ? `${ev.minute}'` : "—"} · {ev.event_type || "Event"}</span>
                <b>{ev.player_name || ev.player_id || "—"}</b>
              </div>
            ))}
          </div>
        ) : events.data ? (
          <p className="section-copy">No events returned by the backend for this match.</p>
        ) : null}
      </div>

      <MatchPredictionPanel
        matchId={matchId}
        homeName={m.home_club_name || "Home"}
        awayName={m.away_club_name || "Away"}
      />
    </>
  );
}

function MatchPredictionPanel({ matchId, homeName, awayName }) {
  const prediction = useQuery({
    queryKey: ["match-prediction", matchId],
    queryFn: () => getMatchPrediction(matchId),
    retry: false,
  });

  if (prediction.isLoading) {
    return (
      <div className="data-block" style={{ marginTop: 24 }} data-testid="match-prediction-loading">
        <p className="eyebrow">MATCH INTELLIGENCE</p>
        <p className="section-copy">Computing temporally valid pre-match feature snapshot and calibrated outcome probabilities…</p>
      </div>
    );
  }

  if (prediction.isError) {
    return (
      <div className="data-block dependency-section" style={{ marginTop: 24 }} data-testid="match-prediction-error">
        <ShieldAlert size={18} />
        <div>
          <p className="eyebrow">MATCH PREDICTION ENGINE</p>
          <h3>Prediction Unavailable</h3>
          <p className="section-copy">{apiErrorMessage(prediction.error)}</p>
        </div>
      </div>
    );
  }

  const p = prediction.data;
  if (!p) return null;

  const pHome = Math.round((p.probabilities?.home_win || 0) * 100);
  const pDraw = Math.round((p.probabilities?.draw || 0) * 100);
  const pAway = Math.round((p.probabilities?.away_win || 0) * 100);

  const xgHome = p.expected_goals?.home?.toFixed(2) ?? "—";
  const xgAway = p.expected_goals?.away?.toFixed(2) ?? "—";
  const xgTotal = p.expected_goals?.total?.toFixed(2) ?? "—";

  const isLowConfidence = p.data_status === "LOW_CONFIDENCE";
  const isInsufficient = p.data_status === "INSUFFICIENT_DATA";
  const isOod = p.data_status === "OUT_OF_DISTRIBUTION";

  return (
    <div className="data-block" style={{ marginTop: 24 }} data-testid="match-prediction-panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div>
          <p className="eyebrow">PROBABILISTIC MATCH INTELLIGENCE</p>
          <h2>Pre-Match Prediction &amp; Expected Goals</h2>
          <p className="section-copy" style={{ margin: "4px 0 0" }}>
            Model {p.model_version} · Features: {p.feature_version} · As of: {p.as_of ? new Date(p.as_of).toLocaleDateString() : "Kickoff"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span
            className={`contract-badge ${isInsufficient ? "badge-danger" : isLowConfidence ? "badge-warning" : "badge-success"}`}
            style={{
              padding: "4px 8px",
              borderRadius: 4,
              fontSize: "0.75rem",
              fontWeight: 600,
              background: isInsufficient ? "#ef444422" : isLowConfidence ? "#f59e0b22" : "#10b98122",
              color: isInsufficient ? "#ef4444" : isLowConfidence ? "#f59e0b" : "#10b981",
              border: `1px solid ${isInsufficient ? "#ef444444" : isLowConfidence ? "#f59e0b44" : "#10b98144"}`,
            }}
          >
            {p.data_status}
          </span>
          <span
            className="contract-badge"
            style={{
              padding: "4px 8px",
              borderRadius: 4,
              fontSize: "0.75rem",
              background: "rgba(59, 130, 246, 0.12)",
              color: "#60a5fa",
              border: "1px solid rgba(59, 130, 246, 0.25)",
            }}
          >
            {p.calibration?.status || "CALIBRATED"} ({p.calibration?.method || "TEMP_SCALING"})
          </span>
        </div>
      </div>

      {/* 1X2 Probabilities Bar & Breakdown */}
      <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.07)", borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <p className="eyebrow" style={{ marginBottom: 12 }}>1X2 OUTCOME PROBABILITIES (P_H + P_D + P_A = 100%)</p>
        <div style={{ display: "flex", width: "100%", height: 28, borderRadius: 6, overflow: "hidden", marginBottom: 16 }}>
          <div
            style={{
              width: `${pHome}%`,
              background: "#3b82f6",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "0.75rem",
              fontWeight: 700,
              color: "#fff",
              transition: "width 0.3s ease",
            }}
            title={`Home Win: ${pHome}%`}
          >
            {pHome > 12 ? `${pHome}%` : ""}
          </div>
          <div
            style={{
              width: `${pDraw}%`,
              background: "#64748b",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "0.75rem",
              fontWeight: 700,
              color: "#fff",
              transition: "width 0.3s ease",
            }}
            title={`Draw: ${pDraw}%`}
          >
            {pDraw > 12 ? `${pDraw}%` : ""}
          </div>
          <div
            style={{
              width: `${pAway}%`,
              background: "#8b5cf6",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "0.75rem",
              fontWeight: 700,
              color: "#fff",
              transition: "width 0.3s ease",
            }}
            title={`Away Win: ${pAway}%`}
          >
            {pAway > 12 ? `${pAway}%` : ""}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
          <div style={{ padding: 12, borderRadius: 6, background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
            <span style={{ fontSize: "0.75rem", color: "#93c5fd", textTransform: "uppercase", display: "block" }}>{homeName} Win</span>
            <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>{pHome}%</span>
            <span style={{ fontSize: "0.7rem", color: "#94a3b8", display: "block" }}>P = {p.probabilities?.home_win?.toFixed(3)}</span>
          </div>
          <div style={{ padding: 12, borderRadius: 6, background: "rgba(100, 116, 139, 0.08)", border: "1px solid rgba(100, 116, 139, 0.2)" }}>
            <span style={{ fontSize: "0.75rem", color: "#cbd5e1", textTransform: "uppercase", display: "block" }}>Draw</span>
            <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>{pDraw}%</span>
            <span style={{ fontSize: "0.7rem", color: "#94a3b8", display: "block" }}>P = {p.probabilities?.draw?.toFixed(3)}</span>
          </div>
          <div style={{ padding: 12, borderRadius: 6, background: "rgba(139, 92, 246, 0.08)", border: "1px solid rgba(139, 92, 246, 0.2)" }}>
            <span style={{ fontSize: "0.75rem", color: "#c4b5fd", textTransform: "uppercase", display: "block" }}>{awayName} Win</span>
            <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff" }}>{pAway}%</span>
            <span style={{ fontSize: "0.7rem", color: "#94a3b8", display: "block" }}>P = {p.probabilities?.away_win?.toFixed(3)}</span>
          </div>
        </div>
      </div>

      {/* Expected Goals & Scoreline Distribution */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginBottom: 20 }}>
        <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.07)", borderRadius: 8, padding: 16 }}>
          <p className="eyebrow" style={{ marginBottom: 8 }}>PRE-MATCH EXPECTED GOALS (xG)</p>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
            <div>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>{homeName}</span>
              <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "#38bdf8" }}>{xgHome}</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <span style={{ fontSize: "0.75rem", color: "#64748b" }}>TOTAL xG</span>
              <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "#e2e8f0" }}>{xgTotal}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>{awayName}</span>
              <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "#a78bfa" }}>{xgAway}</div>
            </div>
          </div>
          {p.goal_distribution && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: "0.75rem", color: "#94a3b8", borderTop: "1px solid rgba(255, 255, 255, 0.06)", paddingTop: 10 }}>
              <span>Over 2.5: <b>{Math.round((p.goal_distribution.over_2_5 || 0) * 100)}%</b></span>
              <span>·</span>
              <span>Under 2.5: <b>{Math.round((p.goal_distribution.under_2_5 || 0) * 100)}%</b></span>
              <span>·</span>
              <span>BTTS: <b>{Math.round((p.goal_distribution.both_teams_to_score || 0) * 100)}%</b></span>
            </div>
          )}
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.07)", borderRadius: 8, padding: 16 }}>
          <p className="eyebrow" style={{ marginBottom: 8 }}>TOP PROBABLE SCORELINE OUTCOMES</p>
          {p.goal_distribution?.top_scorelines?.length > 0 ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
              {p.goal_distribution.top_scorelines.slice(0, 6).map((sc) => (
                <div key={sc.score} style={{ background: "rgba(255, 255, 255, 0.04)", borderRadius: 6, padding: "8px 10px", textAlign: "center" }}>
                  <div style={{ fontSize: "1rem", fontWeight: 700, color: "#f8fafc" }}>{sc.score}</div>
                  <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>{(sc.probability * 100).toFixed(1)}%</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="section-copy">Scoreline distribution unavailable.</p>
          )}
        </div>
      </div>

      {/* Why the Model Thinks This: Explainability & Evidence */}
      {p.explanation && (
        <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.07)", borderRadius: 8, padding: 16 }}>
          <p className="eyebrow" style={{ marginBottom: 8 }}>WHY THE MODEL THINKS THIS (NON-CAUSAL FEATURE ATTRIBUTION)</p>
          <p className="section-copy" style={{ marginBottom: 16, color: "#e2e8f0" }}>{p.explanation.summary}</p>

          {p.explanation.key_factors?.length > 0 && (
            <div style={{ display: "grid", gap: 10, marginBottom: 16 }}>
              {p.explanation.key_factors.map((factor, idx) => {
                const isHome = factor.direction === "FAVORS_HOME";
                const isAway = factor.direction === "FAVORS_AWAY";
                const badgeColor = isHome ? "#38bdf8" : isAway ? "#a78bfa" : "#94a3b8";
                const badgeBg = isHome ? "rgba(56, 189, 248, 0.1)" : isAway ? "rgba(167, 139, 250, 0.1)" : "rgba(148, 163, 184, 0.1)";

                return (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 12px",
                      borderRadius: 6,
                      background: "rgba(255, 255, 255, 0.03)",
                      border: "1px solid rgba(255, 255, 255, 0.05)",
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 600, color: "#f1f5f9", fontSize: "0.85rem" }}>{factor.feature_name}</span>
                      <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "#94a3b8" }}>{factor.description}</p>
                    </div>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: 4,
                        fontSize: "0.7rem",
                        fontWeight: 600,
                        background: badgeBg,
                        color: badgeColor,
                        whiteSpace: "nowrap",
                        marginLeft: 12,
                      }}
                    >
                      {factor.direction}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {p.data_sufficiency_reasons?.length > 0 && (
            <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)", paddingTop: 10 }}>
              <p className="eyebrow" style={{ marginBottom: 4 }}>DATA SUFFICIENCY AUDIT</p>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.75rem", color: "#94a3b8" }}>
                {p.data_sufficiency_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


export default function MatchesPage({ detail }) {
  return (
    <section className="intelligence-page" data-testid={detail ? "match-detail-page" : "matches-page"}>
      {detail ? <MatchDetail /> : <MatchList />}
    </section>
  );
}
