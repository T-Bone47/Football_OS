import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Database, ShieldAlert } from "lucide-react";
import { apiErrorMessage, BACKEND_GAPS, getClubs, getFeatureRegistry, getMatches, getPlayers } from "@/lib/footballApi";

function StatusRow({ label, endpoint, query, testId }) {
  const status = query.isLoading ? "loading" : query.isError ? "error" : "healthy";
  const badgeTone = status === "healthy" ? "pos" : status === "error" ? "risk" : "warn";
  const message = status === "loading"
    ? "Awaiting response"
    : status === "error"
    ? apiErrorMessage(query.error)
    : `${Array.isArray(query.data) ? query.data.length : "—"} records`;
  return (
    <div data-testid={testId}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <strong>{label}</strong>
          <small style={{ display: "block", color: "var(--muted)", fontSize: 11, marginTop: 2 }}>{endpoint}</small>
        </div>
        <span className={`badge ${badgeTone}`}>
          {status === "healthy" && <CheckCircle2 size={11} />}
          {status === "error" && <ShieldAlert size={11} />}
          {status === "loading" && <Database size={11} />}
          {status.toUpperCase()}
        </span>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 6 }}>{message}</p>
    </div>
  );
}

export default function DataQualityPage() {
  const players = useQuery({ queryKey: ["dq-players"], queryFn: () => getPlayers({ limit: 5 }), retry: false });
  const clubs = useQuery({ queryKey: ["dq-clubs"], queryFn: getClubs, retry: false });
  const matches = useQuery({ queryKey: ["dq-matches"], queryFn: () => getMatches({ limit: 5 }), retry: false });
  const registry = useQuery({ queryKey: ["dq-registry"], queryFn: getFeatureRegistry, retry: false });

  return (
    <section className="intelligence-page" data-testid="data-quality-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SYSTEM / DATA QUALITY</p>
          <h1 data-testid="page-title">Data quality</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Live health check of the connected Football Intelligence OS canonical endpoints. Failure states are surfaced honestly — no synthetic green ticks.
          </p>
        </div>
        <span className="badge info">LIVE CANONICAL CHECK</span>
      </div>

      <div className="dashboard-grid" style={{ marginTop: 24 }} data-testid="dq-endpoints">
        <div className="data-block">
          <StatusRow label="Players" endpoint="/api/v1/players" query={players} testId="dq-players" />
        </div>
        <div className="data-block">
          <StatusRow label="Clubs" endpoint="/api/v1/clubs" query={clubs} testId="dq-clubs" />
        </div>
        <div className="data-block">
          <StatusRow label="Matches" endpoint="/api/v1/matches" query={matches} testId="dq-matches" />
        </div>
        <div className="data-block">
          <StatusRow label="Feature registry" endpoint="/api/v1/features/registry" query={registry} testId="dq-features" />
        </div>
      </div>

      <div className="data-block dependency-section" style={{ marginTop: 24 }} data-testid="dq-summary-dependency">
        <ShieldAlert size={18} />
        <div>
          <p className="eyebrow">DATA QUALITY SUMMARY</p>
          <h2>Coverage & freshness endpoints pending</h2>
          <p className="section-copy">{BACKEND_GAPS.dataQuality} When exposed this view will surface provider coverage, missingness, ingestion cadence, and validation status per snapshot.</p>
        </div>
      </div>
    </section>
  );
}
