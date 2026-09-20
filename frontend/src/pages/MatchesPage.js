import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Database, ShieldAlert } from "lucide-react";
import { apiErrorMessage, BACKEND_GAPS, getMatch, getMatches, getMatchEvents, getMatchLineups, getMatchStatistics } from "@/lib/footballApi";

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

      <div className="data-block dependency-section" style={{ marginTop: 20 }} data-testid="match-prediction-dependency">
        <ShieldAlert size={18} />
        <div>
          <p className="eyebrow">MATCH PREDICTION</p>
          <h2>Prediction endpoint not yet exposed</h2>
          <p className="section-copy">{BACKEND_GAPS.matchPrediction} Home / draw / away probabilities, model confidence, and feature as-of dates will surface here once available.</p>
        </div>
      </div>
    </>
  );
}

export default function MatchesPage({ detail }) {
  return (
    <section className="intelligence-page" data-testid={detail ? "match-detail-page" : "matches-page"}>
      {detail ? <MatchDetail /> : <MatchList />}
    </section>
  );
}
