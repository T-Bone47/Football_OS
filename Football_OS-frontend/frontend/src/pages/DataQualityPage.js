import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, Database, ShieldAlert } from "lucide-react";
import {
  apiErrorMessage,
  getClubs,
  getDataStatus,
  getMatchesPage,
  getModelStatus,
  getPlayerCoverage,
  getPlayerPage,
} from "@/lib/footballApi";

const TONE = {
  OK: "pos",
  AVAILABLE: "pos",
  READY: "pos",
  DEGRADED: "warn",
  PARTIAL: "warn",
  UNKNOWN: "warn",
  STALE: "warn",
  UNAVAILABLE: "risk",
  ERROR: "risk",
  FAILED: "risk",
};

function StatusPill({ status }) {
  const key = String(status || "UNKNOWN").toUpperCase();
  const tone = TONE[key] || "warn";
  return (
    <span className={`badge ${tone}`} data-testid={`dq-status-${key.toLowerCase()}`}>
      {tone === "pos" ? <CheckCircle2 size={11} /> : <ShieldAlert size={11} />} {key}
    </span>
  );
}

function CoverageRow({ label, endpoint, query, testId, value, detail }) {
  const status = query.isLoading ? "LOADING" : query.isError ? "ERROR" : value != null ? "OK" : "UNKNOWN";
  return (
    <div data-testid={testId}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <strong>{label}</strong>
          <small style={{ display: "block", color: "var(--muted)", fontSize: 11, marginTop: 2 }}>{endpoint}</small>
        </div>
        <StatusPill status={status} />
      </div>
      <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 6 }}>
        {query.isLoading && "Measuring…"}
        {query.isError && apiErrorMessage(query.error)}
        {!query.isLoading && !query.isError && (detail || `${value ?? "—"} records`)}
      </p>
    </div>
  );
}

function formatWhen(value) {
  if (!value) return "never recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

export default function DataQualityPage() {
  const dataStatus = useQuery({ queryKey: ["dq-data-status"], queryFn: getDataStatus, retry: false });
  const players = useQuery({
    queryKey: ["dq-players-total"],
    queryFn: () => getPlayerPage({ page: 1, page_size: 1 }),
    retry: false,
  });
  const matches = useQuery({
    queryKey: ["dq-matches-total"],
    queryFn: () => getMatchesPage({ page: 1, page_size: 1 }),
    retry: false,
  });
  const clubs = useQuery({ queryKey: ["dq-clubs"], queryFn: getClubs, retry: false });
  const coverage = useQuery({ queryKey: ["dq-player-coverage"], queryFn: getPlayerCoverage, retry: false });
  const models = useQuery({ queryKey: ["dq-model-status"], queryFn: getModelStatus, retry: false });

  const metrics = dataStatus.data?.metrics || {};
  const dataState = dataStatus.data?.status || "UNKNOWN";
  const playerTotal = players.data?.total;
  const matchTotal = matches.data?.total;
  const clubTotal = Array.isArray(clubs.data) ? clubs.data.length : undefined;
  const coverageState = coverage.data?.status || "UNKNOWN";
  const modelState = models.data?.status || "UNKNOWN";

  return (
    <section className="intelligence-page" data-testid="data-quality-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SYSTEM / DATA QUALITY</p>
          <h1 data-testid="page-title">Data quality</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Measured canonical counts, ingestion freshness, provider coverage and model status. A reachable endpoint is
            not treated as proof of complete data.
          </p>
        </div>
        <StatusPill status={dataState} />
      </div>

      <div className="dashboard-grid" style={{ marginTop: 24 }} data-testid="dq-census">
        <article className="intelligence-card">
          <span className="card-label"><Database size={12} /> Canonical players</span>
          <div className="metric-value" data-testid="dq-players-total">{playerTotal?.toLocaleString() ?? "—"}</div>
          <p className="metric-foot">server-side count · /players/search total</p>
        </article>
        <article className="intelligence-card">
          <span className="card-label"><Database size={12} /> Fixtures</span>
          <div className="metric-value" data-testid="dq-matches-total">{matchTotal?.toLocaleString() ?? "—"}</div>
          <p className="metric-foot">/matches/search total</p>
        </article>
        <article className="intelligence-card">
          <span className="card-label"><Database size={12} /> Transfers</span>
          <div className="metric-value" data-testid="dq-transfers-total">
            {metrics.canonical_transfers_count != null ? metrics.canonical_transfers_count.toLocaleString() : "—"}
          </div>
          <p className="metric-foot">provider transfer records</p>
        </article>
        <article className="intelligence-card">
          <span className="card-label"><Database size={12} /> Indexed clubs</span>
          <div className="metric-value" data-testid="dq-clubs-total">{clubTotal?.toLocaleString() ?? "—"}</div>
          <p className="metric-foot">club directory (not squad coverage)</p>
        </article>
      </div>

      <div className="status-strip" data-testid="dq-freshness" style={{ marginTop: 18 }}>
        <span className={`live-dot ${dataState === "OK" ? "" : "warn"}`} />
        <strong>Last successful ingestion</strong>
        <span>{formatWhen(metrics.last_successful_ingestion_at)}</span>
        <span className="divider">·</span>
        <span>
          {metrics.last_successful_ingestion_age_hours != null
            ? `${metrics.last_successful_ingestion_age_hours}h ago`
            : "age not measured"}
        </span>
        <span className="divider">·</span>
        <span>schema {dataStatus.data?.schema_version || "unknown"}</span>
      </div>

      <div className="dashboard-grid" style={{ marginTop: 24 }} data-testid="dq-endpoints">
        <div className="data-block">
          <CoverageRow
            label="Players"
            endpoint="/api/v1/players/search"
            query={players}
            testId="dq-players"
            value={playerTotal}
            detail={`${playerTotal ?? "—"} canonical players (server total)`}
          />
        </div>
        <div className="data-block">
          <CoverageRow
            label="Clubs"
            endpoint="/api/v1/clubs"
            query={clubs}
            testId="dq-clubs"
            value={clubTotal}
            detail={`${clubTotal ?? "—"} club rows returned`}
          />
        </div>
        <div className="data-block">
          <CoverageRow
            label="Matches"
            endpoint="/api/v1/matches/search"
            query={matches}
            testId="dq-matches"
            value={matchTotal}
            detail={`${matchTotal ?? "—"} fixtures (server total)`}
          />
        </div>
        <div className="data-block">
          <CoverageRow
            label="Model artifacts"
            endpoint="/model-status"
            query={models}
            testId="dq-models"
            value={models.data?.artifacts?.length ?? null}
            detail={`${modelState} · ${models.data?.governance_records_validated ?? 0} validated governance record(s)`}
          />
        </div>
      </div>

      <div className="data-block" style={{ marginTop: 24 }} data-testid="dq-coverage">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div>
            <p className="eyebrow">PROVIDER COVERAGE</p>
            <h2>Player scope completeness</h2>
          </div>
          <StatusPill status={coverageState} />
        </div>
        {coverage.isLoading && <p className="section-copy">Reading coverage…</p>}
        {coverage.isError && <p className="section-copy error-state">{apiErrorMessage(coverage.error)}</p>}
        {coverage.data && (
          <>
            <div className="kv-list" style={{ marginTop: 12 }}>
              <div><span>League / season</span><b>{coverage.data.scope?.league ?? "—"} · {coverage.data.scope?.season ?? "—"}</b></div>
              <div><span>Provider-declared pages</span><b>{coverage.data.declared_total_pages ?? "—"}</b></div>
              <div><span>Completed pages</span><b>{coverage.data.completed_pages ?? "—"}</b></div>
              <div><span>Accessible pages</span><b>{coverage.data.accessible_pages ?? "—"}</b></div>
              <div><span>Failed runs</span><b>{coverage.data.failed_runs ?? 0}</b></div>
            </div>
            {coverage.data.provider_plan_limit && (
              <p className="section-copy" style={{ marginTop: 10 }} data-testid="dq-plan-limit">
                <CircleAlert size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
                Provider plan caps this scope at page {coverage.data.provider_plan_limit.page_max}. The canonical
                index is partial, not complete.
              </p>
            )}
            {coverage.data.status === "COMPLETE" && (
              <p className="section-copy" style={{ marginTop: 10 }}>
                Every provider-declared page was ingested for this scope.
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
