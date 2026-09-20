import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { ArrowRight, Bot, Database, LogOut, ShieldAlert, Sparkles } from "lucide-react";
import { getPlayers, getClubs, getMatches, apiErrorMessage } from "@/lib/footballApi";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function Signal({ label, value, hint, tone = "neutral", testId }) {
  return (
    <article className="intelligence-card" data-testid={testId}>
      <span className={`badge ${tone}`} data-testid={`${testId}-badge`}>{label}</span>
      <h2 data-testid={`${testId}-heading`}>{hint}</h2>
      <div className="metric-value" data-testid={`${testId}-value`}>{value}</div>
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
          <p className="eyebrow" data-testid="dashboard-eyebrow">FOOTBALL INTELLIGENCE OS / OVERVIEW</p>
          <h1 data-testid="dashboard-heading">{greeting}, {firstName}.</h1>
          <p className="workspace-subtitle" data-testid="dashboard-subtitle">Your decision room — evidence, models, and market context in one calm view.</p>
        </div>
        <button className="logout-button" data-testid="logout-button" onClick={logout}>
          <LogOut size={15} /> Sign out
        </button>
      </header>

      <section className="status-strip" data-testid="session-status">
        <span className={`live-dot ${backendConnected ? "" : "warn"}`} />
        <strong data-testid="session-status-label">{backendConnected ? "DATA LAYER CONNECTED" : "DATA LAYER PENDING"}</strong>
        <span data-testid="session-user-email">{user?.email}</span>
      </section>

      <div className="dashboard-grid" data-testid="dashboard-signals">
        <Signal
          label={backendConnected ? "LIVE" : "PENDING"}
          tone={backendConnected ? "pos" : "warn"}
          hint="Players in scope"
          value={backendConnected ? players.data.length.toLocaleString() : "—"}
          testId="signal-players"
        />
        <Signal
          label={clubs.data ? "LIVE" : "PENDING"}
          tone={clubs.data ? "pos" : "warn"}
          hint="Clubs indexed"
          value={clubs.data ? clubs.data.length.toLocaleString() : "—"}
          testId="signal-clubs"
        />
        <Signal
          label={matches.data ? "LIVE" : "PENDING"}
          tone={matches.data ? "pos" : "warn"}
          hint="Matches available"
          value={matches.data ? matches.data.length.toLocaleString() : "—"}
          testId="signal-matches"
        />
        <Signal
          label="MODEL"
          tone="model"
          hint="Copilot model"
          value="Claude Sonnet 5"
          testId="signal-copilot"
        />
      </div>

      <div className="dashboard-columns">
        <div className="dashboard-block" data-testid="dashboard-players-block">
          <div className="section-heading">
            <div>
              <p className="eyebrow">RECENT PLAYERS</p>
              <h3>From the connected canonical index</h3>
            </div>
            <button className="text-button" onClick={() => navigate("/players")} data-testid="dashboard-open-players">
              Open discovery <ArrowRight size={14} />
            </button>
          </div>
          {players.isLoading && <p className="section-copy" data-testid="dashboard-players-loading">Loading player data…</p>}
          {players.isError && (
            <p className="section-copy error-state" data-testid="dashboard-players-error">
              <ShieldAlert size={14} style={{ verticalAlign: "-2px", marginRight: 6 }} />
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
                  <button className="row-action" onClick={() => navigate(`/players/${player.id}`)} data-testid={`dashboard-player-open-${player.id}`}>
                    Open <ArrowRight size={12} />
                  </button>
                </div>
              ))}
              {players.data.length === 0 && (
                <div style={{ padding: "18px 0", color: "var(--muted)" }} data-testid="dashboard-players-empty">
                  The connected index returned no players. Trigger a canonical ingestion run to populate this view.
                </div>
              )}
            </div>
          )}
        </div>

        <div className="dashboard-block" data-testid="dashboard-actions-block">
          <div className="section-heading">
            <div>
              <p className="eyebrow">DECISION SURFACES</p>
              <h3>Where to go next</h3>
            </div>
          </div>
          <div className="row-list">
            <button className="row-action" onClick={() => navigate("/copilot")} data-testid="dashboard-action-copilot" style={{ background: "transparent", border: 0, textAlign: "left", padding: "10px 0", cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", color: "var(--text)" }}>
                <span><Bot size={14} style={{ verticalAlign: "-2px", marginRight: 8, color: "var(--cyan)" }} />Ask Scout copilot</span>
                <ArrowRight size={13} />
              </div>
            </button>
            <button className="row-action" onClick={() => navigate("/players/similarity")} data-testid="dashboard-action-similarity" style={{ background: "transparent", border: 0, textAlign: "left", padding: "10px 0", cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", color: "var(--text)" }}>
                <span><Sparkles size={14} style={{ verticalAlign: "-2px", marginRight: 8, color: "var(--purple)" }} />Similarity explorer</span>
                <ArrowRight size={13} />
              </div>
            </button>
            <button className="row-action" onClick={() => navigate("/tactical/fit")} data-testid="dashboard-action-tactical" style={{ background: "transparent", border: 0, textAlign: "left", padding: "10px 0", cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", color: "var(--text)" }}>
                <span><Database size={14} style={{ verticalAlign: "-2px", marginRight: 8, color: "var(--cyan)" }} />Tactical fit workspace</span>
                <ArrowRight size={13} />
              </div>
            </button>
            <button className="row-action" onClick={() => navigate("/system/data-quality")} data-testid="dashboard-action-quality" style={{ background: "transparent", border: 0, textAlign: "left", padding: "10px 0", cursor: "pointer" }}>
              <div style={{ display: "flex", justifyContent: "space-between", width: "100%", color: "var(--text)" }}>
                <span><ShieldAlert size={14} style={{ verticalAlign: "-2px", marginRight: 8, color: "var(--amber)" }} />Data quality</span>
                <ArrowRight size={13} />
              </div>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
