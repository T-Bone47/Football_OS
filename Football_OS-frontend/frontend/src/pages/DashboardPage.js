import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  ArrowUpRight, Bot, Compass, Database, LogOut,
  ShieldAlert, TrendingUp, Users, Activity, Beaker,
} from "lucide-react";
import { getPlayers, getClubs, getMatches, apiErrorMessage } from "@/lib/footballApi";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function Signal({ label, value, sub, icon: Icon, tone = "neutral", testId }) {
  return (
    <article className="intelligence-card" data-testid={testId}>
      <span className="card-label"><Icon size={12} /> {label}</span>
      <div className="metric-value" data-testid={`${testId}-value`}>{value}</div>
      <div className="metric-foot">
        <span className={`badge ${tone}`} data-testid={`${testId}-badge`}>
          {tone === "pos" ? "LIVE" : tone === "warn" ? "PENDING" : tone === "model" ? "MODEL" : "—"}
        </span>
        <span>{sub}</span>
      </div>
    </article>
  );
}

export default function DashboardPage({ user }) {
  const navigate = useNavigate();
  const players = useQuery({ queryKey: ["dashboard-players"], queryFn: () => getPlayers({ limit: 50 }), retry: false });
  const clubs = useQuery({ queryKey: ["dashboard-clubs"], queryFn: getClubs, retry: false });
  const matches = useQuery({ queryKey: ["dashboard-matches"], queryFn: () => getMatches({ limit: 20 }), retry: false });

  const logout = async () => {
    await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    navigate("/login", { replace: true });
  };

  const backendConnected = !players.isError && !!players.data;
  const firstName = user?.name?.split(" ")[0] || "there";
  const hour = new Date().getHours();
  const greeting = hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <section data-testid="dashboard-page">
      <header className="workspace-header">
        <div>
          <p className="eyebrow" data-testid="dashboard-eyebrow">FOOTBALL INTELLIGENCE OS · OVERVIEW</p>
          <h1 data-testid="dashboard-heading">{greeting}, {firstName}.</h1>
          <p className="workspace-subtitle" data-testid="dashboard-subtitle">
            Decision surface for the connected data layer — evidence, models, and market context.
          </p>
        </div>
        <button className="logout-button" data-testid="logout-button" onClick={logout}>
          <LogOut size={13} /> Sign out
        </button>
      </header>

      <section className="status-strip" data-testid="session-status">
        <span className={`live-dot ${backendConnected ? "" : "warn"}`} />
        <strong data-testid="session-status-label">
          {backendConnected ? "DATA LAYER CONNECTED" : "DATA LAYER PENDING"}
        </strong>
        <span className="divider">·</span>
        <span data-testid="session-user-email">{user?.email}</span>
        <span className="divider">·</span>
        <span>Canonical contract <code style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--cyan)" }}>/api/v1/*</code></span>
      </section>

      <div className="dashboard-grid" data-testid="dashboard-signals">
        <Signal
          icon={Users}
          label="Players in scope"
          value={backendConnected ? players.data.length.toLocaleString() : "—"}
          sub={backendConnected ? "canonical index" : "awaiting backend"}
          tone={backendConnected ? "pos" : "warn"}
          testId="signal-players"
        />
        <Signal
          icon={Compass}
          label="Clubs indexed"
          value={clubs.data ? clubs.data.length.toLocaleString() : "—"}
          sub={clubs.data ? "provider coverage" : "awaiting backend"}
          tone={clubs.data ? "pos" : "warn"}
          testId="signal-clubs"
        />
        <Signal
          icon={Activity}
          label="Matches available"
          value={matches.data ? matches.data.length.toLocaleString() : "—"}
          sub={matches.data ? "in fixture window" : "awaiting backend"}
          tone={matches.data ? "pos" : "warn"}
          testId="signal-matches"
        />
        <Signal
          icon={Bot}
          label="Copilot model"
          value="Sonnet 5"
          sub="Anthropic · streaming"
          tone="model"
          testId="signal-copilot"
        />
      </div>

      <div className="dashboard-columns">
        <div className="dashboard-block" data-testid="dashboard-players-block">
          <h3>
            Recent players
            <a onClick={(e) => { e.preventDefault(); navigate("/players"); }} href="/players">Open discovery →</a>
          </h3>
          {players.isLoading && <p className="section-copy" data-testid="dashboard-players-loading">Loading player data…</p>}
          {players.isError && (
            <p className="section-copy error-state" data-testid="dashboard-players-error">
              <ShieldAlert size={12} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              {apiErrorMessage(players.error)}
            </p>
          )}
          {backendConnected && (
            <div className="row-list" data-testid="dashboard-players-list">
              {players.data.slice(0, 6).map((player) => (
                <div key={player.id} data-testid={`dashboard-player-${player.id}`}>
                  <div>
                    <strong>{player.name}</strong>
                    <small>{player.primary_position || "Position unknown"} · {player.nationality || "Nationality unknown"}</small>
                  </div>
                  <button
                    className="row-action"
                    onClick={() => navigate(`/players/${player.id}`)}
                    data-testid={`dashboard-player-open-${player.id}`}
                    style={{ background: "transparent", border: 0, cursor: "pointer" }}
                  >
                    Open →
                  </button>
                </div>
              ))}
              {players.data.length === 0 && (
                <div style={{ padding: "12px 0", color: "var(--muted)", fontSize: 12 }} data-testid="dashboard-players-empty">
                  The connected index returned no players.
                </div>
              )}
            </div>
          )}
        </div>

        <div className="dashboard-block" data-testid="dashboard-actions-block">
          <h3>Decision surfaces</h3>
          <div className="row-list">
            {[
              { icon: Bot, label: "Ask Scout copilot", hint: "Natural-language scouting", path: "/copilot" },
              { icon: Compass, label: "Similarity explorer", hint: "Comparable players", path: "/players/similarity" },
              { icon: TrendingUp, label: "Tactical fit workspace", hint: "Team × system × role", path: "/tactical/fit" },
              { icon: Beaker, label: "Research lab", hint: "Feature registry & models", path: "/research" },
              { icon: Database, label: "Data quality", hint: "Endpoint health", path: "/system/data-quality" },
            ].map((s) => (
              <div key={s.path} data-testid={`dashboard-action-${s.label.toLowerCase().replaceAll(" ", "-")}`}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <s.icon size={13} style={{ color: "var(--muted-strong)" }} />
                  <div>
                    <strong>{s.label}</strong>
                    <small>{s.hint}</small>
                  </div>
                </div>
                <button
                  className="row-action"
                  onClick={() => navigate(s.path)}
                  style={{ background: "transparent", border: 0, cursor: "pointer" }}
                >
                  <ArrowUpRight size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="dashboard-columns" style={{ marginTop: 14 }}>
        <div className="dashboard-block" data-testid="dashboard-matches-block">
          <h3>
            Upcoming matches
            <a onClick={(e) => { e.preventDefault(); navigate("/matches"); }} href="/matches">Match center →</a>
          </h3>
          {matches.isLoading && <p className="section-copy">Loading fixtures…</p>}
          {matches.isError && <p className="section-copy error-state">{apiErrorMessage(matches.error)}</p>}
          {matches.data && matches.data.length === 0 && (
            <p className="section-copy">No fixtures returned by the connected backend yet.</p>
          )}
          {matches.data && matches.data.length > 0 && (
            <div className="row-list">
              {matches.data.slice(0, 5).map((m) => (
                <div key={m.id} data-testid={`dashboard-match-${m.id}`}>
                  <div>
                    <strong>{m.home_club_name || m.home_club_id || "TBD"} vs {m.away_club_name || m.away_club_id || "TBD"}</strong>
                    <small>{m.competition_name || m.competition_id || "—"} · {m.kickoff_time || m.date || "TBD"}</small>
                  </div>
                  <button
                    className="row-action"
                    onClick={() => navigate(`/matches/${m.id}`)}
                    style={{ background: "transparent", border: 0, cursor: "pointer" }}
                  >
                    Open →
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="dashboard-block" data-testid="dashboard-provenance-block">
          <h3>Data freshness</h3>
          <div className="row-list">
            <div>
              <div><strong>/api/v1/players</strong><small>Player universe</small></div>
              <span className={`badge ${backendConnected ? "pos" : "risk"}`}>{backendConnected ? "OK" : "ERROR"}</span>
            </div>
            <div>
              <div><strong>/api/v1/clubs</strong><small>Club directory</small></div>
              <span className={`badge ${clubs.data ? "pos" : "risk"}`}>{clubs.data ? "OK" : "ERROR"}</span>
            </div>
            <div>
              <div><strong>/api/v1/matches</strong><small>Fixture list</small></div>
              <span className={`badge ${matches.data ? "pos" : "risk"}`}>{matches.data ? "OK" : "ERROR"}</span>
            </div>
            <div>
              <div><strong>Copilot</strong><small>Claude Sonnet 5</small></div>
              <span className="badge model">READY</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
