import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, ArrowUpRight, Bot, Compass, Database, Layers, ShieldAlert,
  Sparkles, TrendingUp, Users,
} from "lucide-react";
import {
  apiErrorMessage,
  getClubs,
  getDataStatus,
  getLLMStatus,
  getMatchesPage,
  getModelStatus,
  getPlayerPage,
} from "@/lib/footballApi";
import {
  DataFreshnessIndicator, ErrorState, LoadingSkeleton, MetricCard, PageHeader,
  PlayerIdentity, SectionHeading, StatusBadge, formatUnknown,
} from "@/components/ui";

function relativeAge(hours) {
  if (hours == null) return "age not measured";
  if (hours < 1) return `${Math.round(hours * 60)} min ago`;
  if (hours < 48) return `${hours.toFixed(1)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

function surfaceTone(status) {
  if (status === "AVAILABLE" || status === "OK" || status === "COMPLETE") return "success";
  if (status === "NOT_CONFIGURED" || status === "UNKNOWN") return "neutral";
  return "warn";
}

export default function DashboardPage({ user }) {
  const navigate = useNavigate();
  const players = useQuery({
    queryKey: ["dashboard-players"],
    queryFn: () => getPlayerPage({ page: 1, page_size: 6, sort_by: "name" }),
    retry: false,
  });
  const clubs = useQuery({ queryKey: ["dashboard-clubs"], queryFn: getClubs, retry: false });
  const matches = useQuery({
    queryKey: ["dashboard-matches"],
    queryFn: () => getMatchesPage({ page: 1, page_size: 5 }),
    retry: false,
  });
  const llm = useQuery({ queryKey: ["llm-status"], queryFn: getLLMStatus, retry: false, staleTime: 30000 });
  const dataStatus = useQuery({ queryKey: ["data-status"], queryFn: getDataStatus, retry: false, staleTime: 30000 });
  const modelStatus = useQuery({ queryKey: ["model-status"], queryFn: getModelStatus, retry: false, staleTime: 60000 });

  const backendConnected = !players.isError && !!players.data;
  const dataMetrics = dataStatus.data?.metrics || {};
  const dataLayerState = dataStatus.data?.status || (backendConnected ? "UNKNOWN" : "UNAVAILABLE");
  const modelState = modelStatus.data?.status || (modelStatus.isError ? "UNAVAILABLE" : "UNKNOWN");
  const lastIngestion = dataMetrics.last_successful_ingestion_at
    ? relativeAge(dataMetrics.last_successful_ingestion_age_hours)
    : "no successful ingestion recorded";
  const firstName = user?.name?.split(" ")[0] || "there";
  const hour = new Date().getHours();
  const greeting = hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const llmActive = llm.data?.active || {};
  const llmProvider = llmActive.provider || "—";
  const llmModel = llmActive.model || "—";
  const llmStatus = llmActive.status || (llm.isError ? "UNAVAILABLE" : "NOT_CONFIGURED");
  const llmStreaming = llmActive.streaming_verified ? "verified" : "unverified";

  const matchItems = matches.data?.items || [];
  const matchTotal = matches.data?.total ?? null;

  const activeArtifact = (modelStatus.data?.artifacts || []).find((artifact) => artifact.active)
    || (modelStatus.data?.artifacts || [])[0];
  const blockingReasons = activeArtifact?.blocking_reasons || [];

  return (
    <section data-testid="dashboard-page">
      <PageHeader
        eyebrow="Football Intelligence OS · Overview"
        title={<span data-testid="dashboard-heading">{greeting}, {firstName}.</span>}
        description="Decision surface for the connected data layer — evidence, models, and market context in one workspace."
        testId="dashboard-header"
        meta={(
          <>
            <span className={`fio-status-pill`} data-testid="session-status" title={`Data layer ${dataLayerState}`}>
              <span className={`fio-dot ${dataLayerState === "OK" ? "success" : "warn"}`} aria-hidden="true" />
              <strong data-testid="session-status-label">DATA LAYER {dataLayerState}</strong>
            </span>
            <span className="fio-freshness" data-testid="dashboard-last-ingestion">
              <span className="fio-dot success" aria-hidden="true" />
              last ingestion <strong>{lastIngestion}</strong>
            </span>
            <span className="fio-freshness">
              schema <strong>{dataStatus.data?.schema_version || "unknown"}</strong>
            </span>
            <span className="fio-freshness" data-testid="session-user-email">{user?.email}</span>
          </>
        )}
        actions={(
          <>
            <Link className="primary-button" to="/players" data-testid="dashboard-open-discovery">
              <Users size={14} /> Open discovery
            </Link>
            <Link className="outline-button" to="/copilot">
              <Sparkles size={14} /> Ask copilot
            </Link>
          </>
        )}
      />

      <div className="dashboard-grid" data-testid="dashboard-signals">
        <MetricCard
          icon={Users}
          label="Players in scope"
          value={backendConnected ? (players.data.total ?? 0).toLocaleString() : "—"}
          sub={backendConnected ? <><strong>canonical index</strong> · server total</> : "awaiting backend"}
          badge={backendConnected ? "MEASURED" : "PENDING"}
          tone={backendConnected ? undefined : "warn"}
          testId="signal-players"
          valueTestId="signal-players-value"
          badgeTestId="signal-players-badge"
        />
        <MetricCard
          icon={Compass}
          label="Clubs indexed"
          value={clubs.data ? clubs.data.length.toLocaleString() : "—"}
          sub={clubs.data ? <><strong>club directory</strong> · returned rows</> : "awaiting backend"}
          badge={clubs.data ? "MEASURED" : "PENDING"}
          tone={clubs.data ? undefined : "warn"}
          testId="signal-clubs"
          valueTestId="signal-clubs-value"
          badgeTestId="signal-clubs-badge"
        />
        <MetricCard
          icon={Activity}
          label="Matches available"
          value={typeof matchTotal === "number" ? matchTotal.toLocaleString() : "—"}
          sub={matches.data ? <><strong>fixtures</strong> · server total</> : "awaiting backend"}
          badge={typeof matchTotal === "number" && matchTotal > 0 ? "MEASURED" : "PENDING"}
          tone={typeof matchTotal === "number" && matchTotal > 0 ? undefined : "warn"}
          testId="signal-matches"
          valueTestId="signal-matches-value"
          badgeTestId="signal-matches-badge"
        />
        <MetricCard
          icon={Bot}
          label="Copilot model"
          value={llmProvider}
          sub={<><strong>{llmModel}</strong> · {llmStatus} · streaming {llmStreaming}</>}
          badge={llmStatus === "AVAILABLE" ? "VERIFIED" : llmStatus}
          tone={llmStatus === "AVAILABLE" ? "accent" : "warn"}
          testId="signal-copilot"
          valueTestId="signal-copilot-value"
          badgeTestId="signal-copilot-badge"
        />
      </div>

      <section className="evidence-strip" data-testid="dashboard-evidence-strip">
        <div>
          <strong>Evidence chain</strong>
          <p className="section-copy">
            Every number above is a measured row from the canonical layer. Copilot text, role
            models and valuations never overwrite measured data — follow the links to inspect
            their coverage before trusting an analysis.
          </p>
        </div>
        <nav className="evidence-strip-links" aria-label="Evidence and coverage shortcuts">
          <Link to="/system/data-quality">Data quality →</Link>
          <Link to="/research/models">Models →</Link>
          <Link to="/research/data">Providers →</Link>
        </nav>
      </section>

      <div className="dashboard-columns">
        <div className="dashboard-block" data-testid="dashboard-players-block">
          <h3>
            Player universe
            <Link to="/players">Open discovery →</Link>
          </h3>
          {players.isLoading ? (
            <div style={{ padding: 16 }} data-testid="dashboard-players-loading">
              <LoadingSkeleton rows={5} label="Loading player data" />
            </div>
          ) : null}
          {players.isError ? (
            <div style={{ padding: 16 }}>
              <ErrorState
                compact
                title="Player index unavailable"
                message={apiErrorMessage(players.error)}
                onRetry={() => players.refetch()}
                testId="dashboard-players-error"
              />
            </div>
          ) : null}
          {backendConnected ? (
            <div className="row-list" data-testid="dashboard-players-list">
              {(players.data.items || []).map((player) => (
                <div key={player.id} data-testid={`dashboard-player-${player.id}`}>
                  <PlayerIdentity player={player} />
                  <button
                    type="button"
                    className="row-action"
                    onClick={() => navigate(`/players/${player.id}`)}
                    data-testid={`dashboard-player-open-${player.id}`}
                    style={{ background: "transparent", border: 0, cursor: "pointer" }}
                  >
                    Open <ArrowUpRight size={12} />
                  </button>
                </div>
              ))}
              {players.data.total === 0 ? (
                <div style={{ padding: "16px", color: "var(--muted)", fontSize: 12 }} data-testid="dashboard-players-empty">
                  The connected index returned no players.
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="stack-14">
          <div className="dashboard-block" data-testid="dashboard-actions-block">
            <h3>Decision surfaces</h3>
            <div className="row-list">
              {[
                { icon: Bot, label: "Ask Scout copilot", hint: "Natural-language scouting", path: "/copilot" },
                { icon: Compass, label: "Similarity explorer", hint: "Comparable players", path: "/players/similarity" },
                { icon: TrendingUp, label: "Tactical fit workspace", hint: "Team × system × role", path: "/tactical/fit" },
                { icon: Layers, label: "Role discovery", hint: "Archetype coverage", path: "/players/roles" },
                { icon: Database, label: "Data quality", hint: "Endpoint health & provenance", path: "/system/data-quality" },
              ].map((surface) => (
                <div key={surface.path} data-testid={`dashboard-action-${surface.label.toLowerCase().replaceAll(" ", "-")}`}>
                  <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <surface.icon size={14} style={{ color: "var(--muted-strong)" }} aria-hidden="true" />
                    <div>
                      <strong>{surface.label}</strong>
                      <small>{surface.hint}</small>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="row-action"
                    onClick={() => navigate(surface.path)}
                    aria-label={`Open ${surface.label}`}
                    style={{ background: "transparent", border: 0, cursor: "pointer" }}
                  >
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="data-block" data-testid="dashboard-model-block">
            <div className="block-head">
              <h3>Model readiness</h3>
              <StatusBadge status={modelState}>{modelState}</StatusBadge>
            </div>
            {modelStatus.isLoading ? <LoadingSkeleton rows={3} label="Loading model status" /> : null}
            {modelStatus.isError ? (
              <p className="section-copy error-state"><ShieldAlert size={12} /> {apiErrorMessage(modelStatus.error)}</p>
            ) : null}
            {activeArtifact ? (
              <dl className="kv-list">
                <div><dt>Active artifact</dt><dd className="fio-mono">{activeArtifact.model_id}</dd></div>
                <div><dt>Domain</dt><dd>{formatUnknown(activeArtifact.domain)}</dd></div>
                <div><dt>Release</dt><dd><StatusBadge status={activeArtifact.release_status}>{activeArtifact.release_status}</StatusBadge></dd></div>
                <div><dt>Serving allowed</dt><dd>{activeArtifact.serving_allowed ? "Yes" : "No"}</dd></div>
              </dl>
            ) : null}
            {blockingReasons.length > 0 ? (
              <p className="confidence-note" style={{ marginTop: 10 }}>
                Blocking reason: {blockingReasons[0]}
              </p>
            ) : null}
            <Link className="text-button" to="/research/models" style={{ marginTop: 8 }}>
              Inspect model registry →
            </Link>
          </div>
        </div>
      </div>

      <div className="dashboard-columns" style={{ marginTop: 14 }}>
        <div className="dashboard-block" data-testid="dashboard-matches-block">
          <h3>
            Upcoming fixtures
            <Link to="/matches">Match center →</Link>
          </h3>
          {matches.isLoading ? <div style={{ padding: 16 }}><LoadingSkeleton rows={4} label="Loading fixtures" /></div> : null}
          {matches.isError ? (
            <div style={{ padding: 16 }}>
              <ErrorState compact title="Fixtures unavailable" message={apiErrorMessage(matches.error)} onRetry={() => matches.refetch()} />
            </div>
          ) : null}
          {matches.data && matchItems.length === 0 ? (
            <p className="section-copy" style={{ padding: 16 }}>No fixtures returned by the connected backend yet.</p>
          ) : null}
          {matchItems.length > 0 ? (
            <div className="row-list">
              {matchItems.map((match) => (
                <div key={match.id} data-testid={`dashboard-match-${match.id}`}>
                  <div>
                    <strong>{match.home_club_name || match.home_club_id || "TBD"} vs {match.away_club_name || match.away_club_id || "TBD"}</strong>
                    <small>{match.competition_name || match.competition_id || "Competition unknown"} · {match.kickoff_time || match.date || "Kick-off unknown"}</small>
                  </div>
                  <button
                    type="button"
                    className="row-action"
                    onClick={() => navigate(`/matches/${match.id}`)}
                    style={{ background: "transparent", border: 0, cursor: "pointer" }}
                  >
                    Open →
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="dashboard-block" data-testid="dashboard-provenance-block">
          <h3>Data freshness</h3>
          <div className="row-list">
            <div data-testid="dashboard-freshness-players">
              <div><strong>/api/v1/players</strong><small>Player universe</small></div>
              <StatusBadge tone={backendConnected ? "success" : "warn"} dot>{backendConnected ? "OK" : "PENDING"}</StatusBadge>
            </div>
            <div data-testid="dashboard-freshness-clubs">
              <div><strong>/api/v1/clubs</strong><small>Club directory</small></div>
              <StatusBadge tone={clubs.data ? "success" : clubs.isError ? "danger" : "warn"} dot>{clubs.data ? "OK" : clubs.isError ? "ERROR" : "PENDING"}</StatusBadge>
            </div>
            <div data-testid="dashboard-freshness-matches">
              <div><strong>/api/v1/matches</strong><small>Fixture list</small></div>
              <StatusBadge tone={matches.data ? "success" : matches.isError ? "danger" : "warn"} dot>{matches.data ? "OK" : matches.isError ? "ERROR" : "PENDING"}</StatusBadge>
            </div>
            <div data-testid="dashboard-freshness-copilot">
              <div><strong>LLM provider</strong><small>{llmProvider} ({llmModel})</small></div>
              <StatusBadge tone={surfaceTone(llmStatus)} dot>{llmStatus}</StatusBadge>
            </div>
            <div>
              <div><strong>Last successful ingestion</strong><small>{lastIngestion}</small></div>
              <DataFreshnessIndicator hours={dataMetrics.last_successful_ingestion_age_hours} label="" testId="dashboard-freshness-age" />
            </div>
          </div>
        </div>
      </div>

      <p className="section-copy" style={{ marginTop: 18, fontSize: 11 }}>
        Context: {formatUnknown(players.data?.total)} players · {formatUnknown(clubs.data?.length)} clubs · {formatUnknown(matchTotal)} matches · LLM: {llmProvider} ({llmStatus})
      </p>
    </section>
  );
}
