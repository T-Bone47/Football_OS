import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight, BarChart3, CheckCircle2, Database, Filter, Layers,
  Radio, ShieldAlert, Sprout, Target, XCircle, TrendingDown, TrendingUp,
  AlertTriangle, Shield, Activity, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import {
  BACKEND_GAPS,
  apiErrorMessage,
  getMarketBenchmarks,
  getMarketCoverage,
  getMarketReadiness,
  getMarketTransfers,
  getMarketOpportunities,
  findMarketReplacements,
  getMarketRiskBatch,
} from "@/lib/footballApi";

const CONFIG = {
  overview: {
    eyebrow: "RECRUITMENT / MARKET",
    title: "Market intelligence",
    description: "Transfer market data foundation, deterministic valuation baselines, and historical comparables.",
    icon: BarChart3,
    surfaces: [
      { label: "Valuation", path: "/market/valuation", icon: Target, hint: "Deterministic baseline valuation with sample-gated IQR bounds." },
      { label: "Opportunities", path: "/market/opportunities", icon: Sprout, hint: "Market gaps flagged against role coverage." },
      { label: "Replacements", path: "/market/replacements", icon: Radio, hint: "Candidate replacements ranked by fit and risk." },
      { label: "Transfer risk", path: "/market/risk", icon: ShieldAlert, hint: "Performance, adaptation, and financial risk." },
    ],
  },
  valuation: {
    eyebrow: "RECRUITMENT / VALUATION",
    title: "Player valuation foundation",
    description: "Deterministic comparable-median baseline and statistical dispersion — surfaced directly from verified transactions, never from an LLM.",
    icon: Target,
  },
  opportunities: {
    eyebrow: "RECRUITMENT / OPPORTUNITIES",
    title: "Market opportunities",
    description: 'A calm alternative to "hidden gems" — players where estimated value diverges from reference value, with evidence attached.',
    icon: Sprout,
  },
  replacements: {
    eyebrow: "RECRUITMENT / REPLACEMENTS",
    title: "Replacement finder",
    description: "Candidate replacements for a role or a departing player, ranked by role fit, tactical fit, value, and risk.",
    icon: Radio,
  },
  risk: {
    eyebrow: "RECRUITMENT / RISK",
    title: "Transfer risk",
    description: "Performance, availability, adaptation, financial, and league-translation risk — classified only when backend evidence is sufficient.",
    icon: ShieldAlert,
  },
};

// ─── Opportunity Class Color Mapping ──────────────────────
function oppClassColor(cls) {
  switch (cls) {
    case "UNDERVALUED": return "var(--teal)";
    case "PREMIUM": return "var(--amber)";
    case "FAIRLY_VALUED": return "var(--text-secondary)";
    default: return "var(--muted)";
  }
}

function oppClassBadge(cls) {
  switch (cls) {
    case "UNDERVALUED": return "pos";
    case "PREMIUM": return "warn";
    case "FAIRLY_VALUED": return "model";
    default: return "info";
  }
}

function riskBadge(level) {
  switch (level) {
    case "LOW": return "pos";
    case "MEDIUM": return "model";
    case "HIGH": return "warn";
    case "CRITICAL": return "warn";
    default: return "info";
  }
}

function riskColor(level) {
  switch (level) {
    case "LOW": return "var(--teal)";
    case "MEDIUM": return "var(--amber)";
    case "HIGH": return "#ef4444";
    case "CRITICAL": return "#dc2626";
    default: return "var(--muted)";
  }
}

export default function MarketPage({ variant = "overview" }) {
  const config = CONFIG[variant] || CONFIG.overview;
  const Icon = config.icon;

  const [positionCohort, setPositionCohort] = useState("ALL");
  const [transferFilterPos, setTransferFilterPos] = useState("");
  const [transferFilterFee, setTransferFilterFee] = useState("");
  const [oppFilterPos, setOppFilterPos] = useState("");
  const [oppFilterClass, setOppFilterClass] = useState("");
  const [replTargetRole, setReplTargetRole] = useState("");
  const [replTargetPos, setReplTargetPos] = useState("");
  const [riskFilterPos, setRiskFilterPos] = useState("");

  const coverage = useQuery({
    queryKey: ["market-coverage"],
    queryFn: () => getMarketCoverage(),
    retry: false,
  });

  const benchmarks = useQuery({
    queryKey: ["market-benchmarks", positionCohort],
    queryFn: () => getMarketBenchmarks({ position_group: positionCohort }),
    retry: false,
  });

  const transfers = useQuery({
    queryKey: ["market-transfers", transferFilterPos, transferFilterFee],
    queryFn: () => getMarketTransfers({
      position_group: transferFilterPos || undefined,
      fee_status: transferFilterFee || undefined,
      limit: 50,
    }),
    retry: false,
  });

  const readiness = useQuery({
    queryKey: ["market-readiness"],
    queryFn: () => getMarketReadiness(),
    retry: false,
  });

  // Opportunities query
  const opportunities = useQuery({
    queryKey: ["market-opportunities", oppFilterPos, oppFilterClass],
    queryFn: () => getMarketOpportunities({
      position_group: oppFilterPos || undefined,
      opportunity_class: oppFilterClass || undefined,
      limit: 25,
    }),
    retry: false,
    enabled: variant === "opportunities",
  });

  // Replacements query
  const replacements = useQuery({
    queryKey: ["market-replacements", replTargetRole, replTargetPos],
    queryFn: () => findMarketReplacements({
      target_role: replTargetRole || undefined,
      target_position_group: replTargetPos || undefined,
      limit: 20,
    }),
    retry: false,
    enabled: variant === "replacements",
  });

  // Risk query
  const riskBatch = useQuery({
    queryKey: ["market-risk-batch", riskFilterPos],
    queryFn: () => getMarketRiskBatch({
      position_group: riskFilterPos || undefined,
      limit: 25,
    }),
    retry: false,
    enabled: variant === "risk",
  });

  const showMarketData = variant === "overview" || variant === "valuation";

  return (
    <section className="intelligence-page" data-testid={`market-page-${variant}`}>
      <div className="page-heading">
        <div>
          <p className="eyebrow" data-testid="page-eyebrow">{config.eyebrow}</p>
          <h1 data-testid="page-title">{config.title}</h1>
          <p className="workspace-subtitle" data-testid="page-description">{config.description}</p>
        </div>
        <div className="badges">
          {readiness.data ? (
            <span
              className={`badge ${readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "pos" : "warn"}`}
              data-testid="market-readiness-badge"
            >
              {readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "READY FOR VALUATION MODEL" : "HARD GATE: INSUFFICIENT DATA"}
            </span>
          ) : coverage.data && (
            <span
              className={`badge ${coverage.data.readiness_status === "READY_FOR_VALUATION_MODEL" ? "pos" : "warn"}`}
              data-testid="market-readiness-badge"
            >
              {coverage.data.readiness_status === "READY_FOR_VALUATION_MODEL" ? "READY FOR VALUATION MODEL" : "HARD GATE: INSUFFICIENT DATA"}
            </span>
          )}
          <span className="badge model">PHASE 5B MARKET INTELLIGENCE</span>
        </div>
      </div>

      {variant === "overview" && (
        <div className="dashboard-grid" data-testid="market-surfaces" style={{ marginBottom: 20 }}>
          {config.surfaces.map((surface) => (
            <Link
              key={surface.path}
              to={surface.path}
              className="intelligence-card"
              data-testid={`market-surface-${surface.label.toLowerCase()}`}
              style={{ textDecoration: "none" }}
            >
              <span className="badge info"><surface.icon size={11} /> {surface.label}</span>
              <h2>{surface.hint.split(".")[0]}.</h2>
              <p>{surface.hint}</p>
              <span className="metric-delta"><ArrowUpRight size={12} /> Open workspace</span>
            </Link>
          ))}
        </div>
      )}

      {showMarketData && (
        <div className="stack-14" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Phase 4.1D Model Readiness & Subgroup Representation Card */}
          <div className="data-block" data-testid="market-readiness-card">
            <div className="block-head">
              <div>
                <h3>Phase 4.1D Model Readiness &amp; Subgroup Representation</h3>
                <small style={{ color: "var(--muted)" }}>
                  Multi-source audited transfer coverage, fee semantics, and deterministic ML gating
                </small>
              </div>
              {readiness.data && (
                <span className={`badge ${readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "pos" : "warn"}`}>
                  {readiness.data.status}
                </span>
              )}
            </div>

            {readiness.isLoading && <p className="section-copy">Auditing transfer universe and subgroup representation…</p>}
            {readiness.isError && <p className="section-copy error-state">{apiErrorMessage(readiness.error)}</p>}

            {readiness.data && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
                  <div className="profile-metric">
                    <span>Total Transactions</span>
                    <strong>{readiness.data.total_transactions}</strong>
                    <small>Multi-source merged universe</small>
                  </div>
                  <div className="profile-metric">
                    <span>Usable Fee Targets</span>
                    <strong style={{ color: readiness.data.usable_fee_targets >= 500 ? "var(--teal)" : "var(--amber)" }}>
                      {readiness.data.usable_fee_targets} <span style={{ fontSize: 11, color: "var(--muted)" }}>/ 500</span>
                    </strong>
                    <small>Known / Verified Reported</small>
                  </div>
                  <div className="profile-metric">
                    <span>Remaining Gap</span>
                    <strong style={{ color: readiness.data.usable_fee_targets >= 500 ? "var(--teal)" : "var(--amber)" }}>
                      {readiness.data.usable_fee_targets >= 500
                        ? `0 (+${readiness.data.usable_fee_targets - 500})`
                        : (500 - readiness.data.usable_fee_targets)}
                    </strong>
                    <small>{readiness.data.usable_fee_targets >= 500 ? "Threshold Met" : "Deficit to 500"}</small>
                  </div>
                  <div className="profile-metric">
                    <span>Unique Players</span>
                    <strong style={{ color: readiness.data.unique_players >= 100 ? "var(--teal)" : "var(--amber)" }}>
                      {readiness.data.unique_players} <span style={{ fontSize: 11, color: "var(--muted)" }}>/ 100</span>
                    </strong>
                    <small>Transferred player entities</small>
                  </div>
                  <div className="profile-metric">
                    <span>Unique Clubs</span>
                    <strong>{readiness.data.unique_clubs}</strong>
                    <small>Selling / buying entities</small>
                  </div>
                  <div className="profile-metric">
                    <span>Fee Coverage</span>
                    <strong style={{ color: readiness.data.fee_coverage_pct >= 90.0 ? "var(--teal)" : "var(--amber)" }}>
                      {readiness.data.fee_coverage_pct}%
                    </strong>
                    <small>Known / Verified ratio</small>
                  </div>
                  <div className="profile-metric">
                    <span>Position Coverage</span>
                    <strong style={{ color: readiness.data.subgroups_adequate ? "var(--teal)" : "var(--amber)" }}>
                      {readiness.data.subgroups_adequate ? "4/4 Met" : "Deficits"}
                    </strong>
                    <small>GK &ge; 15, Outfield &ge; 50</small>
                  </div>
                  <div className="profile-metric">
                    <span>Temporal Range</span>
                    <strong style={{ fontSize: 11 }}>{readiness.data.temporal_span}</strong>
                    <small>Span: {readiness.data.seasons_count} seasons</small>
                  </div>
                  <div className="profile-metric">
                    <span>Player Intel Coverage</span>
                    <strong style={{ color: "var(--teal)" }}>{readiness.data.player_intelligence_coverage_pct}%</strong>
                    <small>Historical context links</small>
                  </div>
                </div>

                {/* Subgroup breakdown */}
                {readiness.data.subgroups && (
                  <div style={{ marginTop: 14, padding: "12px", background: "rgba(255,255,255,0.02)", borderRadius: 6, border: "1px solid var(--border)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
                        Subgroup Sample Representation:
                      </span>
                      <span className={`badge ${readiness.data.subgroups_adequate ? "pos" : "warn"}`} style={{ fontSize: 10 }}>
                        {readiness.data.subgroups_adequate ? "Subgroups Adequate" : "Deficits Present"}
                      </span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, fontSize: 12 }}>
                      <div>
                        <span style={{ color: "var(--muted)", display: "block", marginBottom: 4 }}>Position Groups (Target: &ge;50, GK &ge;15):</span>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {Object.entries(readiness.data.subgroups.positions || {}).map(([pos, cnt]) => (
                            <span key={pos} className="badge info" style={{ fontSize: 11 }}>
                              {pos}: <strong>{cnt}</strong>
                            </span>
                          ))}
                        </div>
                      </div>

                      <div>
                        <span style={{ color: "var(--muted)", display: "block", marginBottom: 4 }}>Fee Bands:</span>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {Object.entries(readiness.data.subgroups.fee_bands || {}).map(([band, cnt]) => (
                            <span key={band} className="badge model" style={{ fontSize: 11 }}>
                              {band}: <strong>{cnt}</strong>
                            </span>
                          ))}
                        </div>
                      </div>

                      <div>
                        <span style={{ color: "var(--muted)", display: "block", marginBottom: 4 }}>Age Bands:</span>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {Object.entries(readiness.data.subgroups.age_bands || {}).map(([band, cnt]) => (
                            <span key={band} className="badge model" style={{ fontSize: 11 }}>
                              {band}: <strong>{cnt}</strong>
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Readiness reasons and actions */}
                {readiness.data.reasons?.length > 0 && (
                  <div style={{ marginTop: 14, padding: "10px 14px", background: readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "rgba(45, 212, 191, 0.08)" : "rgba(245, 158, 11, 0.08)", borderRadius: 6, border: readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "1px solid rgba(45, 212, 191, 0.2)" : "1px solid rgba(245, 158, 11, 0.2)" }}>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "var(--teal)" : "var(--amber)" }}>
                      {readiness.data.status === "READY_FOR_VALUATION_MODEL" ? "MODEL READINESS VERIFIED" : "HARD GATE STATUS: PHASE 4.2 ML MODEL TRAINING HELD"}:
                    </p>
                    <ul style={{ margin: "6px 0 0 0", paddingLeft: 18, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                      {readiness.data.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                    {readiness.data.required_actions?.length > 0 && (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px dashed rgba(255,255,255,0.1)" }}>
                        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>Required Engineering Actions:</span>
                        <ul style={{ margin: "4px 0 0 0", paddingLeft: 18, fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
                          {readiness.data.required_actions.map((act, i) => (
                            <li key={i}>{act}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Data Coverage & Raw Transfer Universe Card */}
          <div className="data-block" data-testid="market-coverage-card">
            <div className="block-head">
              <div>
                <h3>Transfer Universe &amp; Raw Source Breakdown</h3>
                <small style={{ color: "var(--muted)" }}>
                  Audited historical transfer coverage (strictly verified provider records, zero synthetic data)
                </small>
              </div>
              {coverage.data && (
                <span className={`badge ${coverage.data.readiness_status === "READY_FOR_VALUATION_MODEL" ? "pos" : "warn"}`}>
                  {coverage.data.readiness_status}
                </span>
              )}
            </div>

            {coverage.isLoading && <p className="section-copy">Auditing transfer universe coverage…</p>}
            {coverage.isError && <p className="section-copy error-state">{apiErrorMessage(coverage.error)}</p>}

            {coverage.data && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
                  <div className="profile-metric">
                    <span>Total Transfers</span>
                    <strong>{coverage.data.total_transfers}</strong>
                    <small>Verified transactions</small>
                  </div>
                  <div className="profile-metric">
                    <span>Reported / Known Fees</span>
                    <strong>{coverage.data.known_fees_count + coverage.data.reported_fees_count}</strong>
                    <small>Usable for modeling</small>
                  </div>
                  <div className="profile-metric">
                    <span>Free Transfers</span>
                    <strong>{coverage.data.free_transfers_count}</strong>
                    <small>Explicit free deals</small>
                  </div>
                  <div className="profile-metric">
                    <span>Loans</span>
                    <strong>{coverage.data.loans_count}</strong>
                    <small>Temporary moves</small>
                  </div>
                  <div className="profile-metric">
                    <span>Unknown / Undisclosed</span>
                    <strong>{coverage.data.unknown_fees_count}</strong>
                    <small>Excluded from pricing</small>
                  </div>
                  <div className="profile-metric">
                    <span>Fee Coverage</span>
                    <strong>{coverage.data.fee_coverage_pct}%</strong>
                    <small>Known / Total ratio</small>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Market Cohort Benchmarks Card */}
          <div className="data-block" data-testid="market-benchmarks-card">
            <div className="block-head">
              <div>
                <h3>Position Cohort Fee Benchmarks</h3>
                <small style={{ color: "var(--muted)" }}>
                  Sample-gated empirical percentiles and IQR dispersion across verified permanent transfers
                </small>
              </div>
              <span className="badge model">STATISTICAL COHORT</span>
            </div>

            {/* Position group selector */}
            <div style={{ display: "flex", gap: 6, margin: "10px 0", flexWrap: "wrap" }}>
              {["ALL", "DEF", "MID", "ATT", "GK"].map((cohort) => (
                <button
                  key={cohort}
                  className="outline-button"
                  style={{
                    fontSize: 12,
                    padding: "4px 12px",
                    background: positionCohort === cohort ? "rgba(45, 212, 191, 0.15)" : "transparent",
                    borderColor: positionCohort === cohort ? "var(--teal)" : "var(--border)",
                    color: positionCohort === cohort ? "var(--teal)" : "var(--text-secondary)",
                    cursor: "pointer",
                  }}
                  onClick={() => setPositionCohort(cohort)}
                  data-testid={`cohort-btn-${cohort}`}
                >
                  {cohort}
                </button>
              ))}
            </div>

            {benchmarks.isLoading && <p className="section-copy">Calculating cohort benchmarks…</p>}
            {benchmarks.isError && <p className="section-copy error-state">{apiErrorMessage(benchmarks.error)}</p>}

            {benchmarks.data && (
              <div>
                {benchmarks.data.data_status === "EVALUATED" ? (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10, marginTop: 10 }}>
                    <div className="profile-metric">
                      <span>Median Fee</span>
                      <strong style={{ color: "var(--teal)" }}>
                        €{(benchmarks.data.median_fee_eur / 1_000_000).toFixed(1)}M
                      </strong>
                      <small>Sample size: n={benchmarks.data.sample_size}</small>
                    </div>
                    <div className="profile-metric">
                      <span>Q1 (25th percentile)</span>
                      <strong>€{(benchmarks.data.q1_fee_eur / 1_000_000).toFixed(1)}M</strong>
                      <small>Lower quartile</small>
                    </div>
                    <div className="profile-metric">
                      <span>Q3 (75th percentile)</span>
                      <strong>€{(benchmarks.data.q3_fee_eur / 1_000_000).toFixed(1)}M</strong>
                      <small>Upper quartile</small>
                    </div>
                    <div className="profile-metric">
                      <span>IQR Dispersion</span>
                      <strong>€{(benchmarks.data.iqr_fee_eur / 1_000_000).toFixed(1)}M</strong>
                      <small>Interquartile range</small>
                    </div>
                    <div className="profile-metric">
                      <span>Min – Max Range</span>
                      <strong>
                        €{(benchmarks.data.min_fee_eur / 1_000_000).toFixed(1)}M – €{(benchmarks.data.max_fee_eur / 1_000_000).toFixed(1)}M
                      </strong>
                      <small>Observed bounds</small>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: "8px 12px", background: "rgba(255,255,255,0.03)", borderRadius: 6, color: "var(--muted)", fontSize: 12 }}>
                    Cohort sample size (n={benchmarks.data.sample_size}) is below minimum threshold (n &ge; 3). Benchmarks withheld to prevent misleading tiny-sample estimates.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Historical Transfer Explorer Card */}
          <div className="data-block" data-testid="market-explorer-card">
            <div className="block-head">
              <div>
                <h3>Historical Transfer Explorer</h3>
                <small style={{ color: "var(--muted)" }}>Search verified deals with semantic fee preservation</small>
              </div>
              <span className="badge model">
                {transfers.data?.length || 0} RECORDS
              </span>
            </div>

            {/* Filter controls */}
            <div style={{ display: "flex", gap: 10, margin: "10px 0", flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
                <Filter size={12} /> Filters:
              </div>
              <select
                value={transferFilterPos}
                onChange={(e) => setTransferFilterPos(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
                data-testid="filter-position-group"
              >
                <option value="">All Positions</option>
                <option value="DEF">Defenders</option>
                <option value="MID">Midfielders</option>
                <option value="ATT">Attackers</option>
                <option value="GK">Goalkeepers</option>
              </select>

              <select
                value={transferFilterFee}
                onChange={(e) => setTransferFilterFee(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
                data-testid="filter-fee-status"
              >
                <option value="">All Fee Statuses</option>
                <option value="REPORTED_FEE">Reported Fee</option>
                <option value="KNOWN_FEE">Known Fee</option>
                <option value="FREE_TRANSFER">Free Transfer</option>
                <option value="LOAN">Loan</option>
                <option value="UNKNOWN_FEE">Unknown Fee</option>
                <option value="UNDISCLOSED">Undisclosed</option>
              </select>
            </div>

            {transfers.isLoading && <p className="section-copy">Loading transfer records…</p>}
            {transfers.isError && <p className="section-copy error-state">{apiErrorMessage(transfers.error)}</p>}

            {transfers.data && transfers.data.length === 0 && (
              <p className="section-copy" style={{ margin: "10px 0" }}>No transfer records match the selected filters.</p>
            )}

            {transfers.data && transfers.data.length > 0 && (
              <div className="evidence-table-wrap" style={{ marginTop: 8 }}>
                <table className="evidence-table" style={{ width: "100%", textAlign: "left", fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Date</th>
                      <th>From Club</th>
                      <th>To Club</th>
                      <th>Type</th>
                      <th>Normalized Fee</th>
                      <th>Fee Status</th>
                      <th>Quality</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transfers.data.map((t) => {
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
                          <td>
                            {t.player_id ? (
                              <Link to={`/players/${t.player_id}`} className="player-link" style={{ fontWeight: 600 }}>
                                {t.player_name || "Unknown Player"}
                              </Link>
                            ) : (
                              <span>{t.player_name || "Unknown"}</span>
                            )}
                          </td>
                          <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{t.transfer_date || "—"}</td>
                          <td>{t.from_club_name || "—"}</td>
                          <td><strong>{t.to_club_name || "—"}</strong></td>
                          <td><span className="badge info">{t.transfer_type || "Transfer"}</span></td>
                          <td style={{ fontFamily: "JetBrains Mono, monospace", color: isUnknown ? "var(--muted)" : isFree ? "var(--teal)" : "var(--text-primary)", fontWeight: isUnknown ? 400 : 600 }}>
                            {feeDisplay}
                          </td>
                          <td>
                            <span className={`badge ${isFree ? "pos" : isUnknown ? "warn" : "model"}`} style={{ fontSize: 10 }}>
                              {t.fee_status}
                            </span>
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
        </div>
      )}

      {/* ─── OPPORTUNITIES VIEW ──────────────────────────────── */}
      {variant === "opportunities" && (
        <div className="stack-14" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="data-block" data-testid="market-opportunities-card">
            <div className="block-head">
              <div>
                <h3>Value Gap Analysis</h3>
                <small style={{ color: "var(--muted)" }}>
                  Players where estimated value diverges from comparable market median — with transparent evidence
                </small>
              </div>
              <span className="badge model">
                {opportunities.data?.total_candidates || 0} CANDIDATES
              </span>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", gap: 10, margin: "10px 0", flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
                <Filter size={12} /> Filters:
              </div>
              <select
                value={oppFilterPos}
                onChange={(e) => setOppFilterPos(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
                data-testid="opp-filter-position"
              >
                <option value="">All Positions</option>
                <option value="DEF">Defenders</option>
                <option value="MID">Midfielders</option>
                <option value="ATT">Attackers</option>
                <option value="GK">Goalkeepers</option>
              </select>
              <select
                value={oppFilterClass}
                onChange={(e) => setOppFilterClass(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
                data-testid="opp-filter-class"
              >
                <option value="">All Classes</option>
                <option value="UNDERVALUED">Undervalued</option>
                <option value="FAIRLY_VALUED">Fairly Valued</option>
                <option value="PREMIUM">Premium</option>
              </select>
            </div>

            {opportunities.isLoading && <p className="section-copy">Scanning value gaps across player universe…</p>}
            {opportunities.isError && <p className="section-copy error-state">{apiErrorMessage(opportunities.error)}</p>}

            {opportunities.data && opportunities.data.opportunities.length === 0 && (
              <p className="section-copy" style={{ margin: "10px 0" }}>No market opportunities match the selected filters.</p>
            )}

            {opportunities.data && opportunities.data.opportunities.length > 0 && (
              <div className="evidence-table-wrap" style={{ marginTop: 8 }}>
                <table className="evidence-table" style={{ width: "100%", textAlign: "left", fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Age</th>
                      <th>Position</th>
                      <th>Role</th>
                      <th>Est. Value</th>
                      <th>Comparable Median</th>
                      <th>Gap</th>
                      <th>Class</th>
                      <th>Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {opportunities.data.opportunities.map((opp) => (
                      <tr key={opp.player_id}>
                        <td>
                          <Link to={`/players/${opp.player_id}`} className="player-link" style={{ fontWeight: 600 }}>
                            {opp.player_name}
                          </Link>
                        </td>
                        <td>{opp.age ? `${opp.age.toFixed(1)}` : "—"}</td>
                        <td>{opp.position_group || "—"}</td>
                        <td style={{ fontSize: 11 }}>{opp.role_archetype || "—"}</td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 600 }}>
                          {opp.estimated_value_eur != null ? `€${(opp.estimated_value_eur / 1_000_000).toFixed(1)}M` : "—"}
                        </td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                          {opp.comparable_median_eur != null ? `€${(opp.comparable_median_eur / 1_000_000).toFixed(1)}M` : "—"}
                        </td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace", color: oppClassColor(opp.opportunity_class), fontWeight: 600 }}>
                          {opp.value_gap_pct != null ? `${(opp.value_gap_pct * 100).toFixed(1)}%` : "—"}
                        </td>
                        <td>
                          <span className={`badge ${oppClassBadge(opp.opportunity_class)}`} style={{ fontSize: 10 }}>
                            {opp.opportunity_class}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${opp.confidence === "HIGH" ? "pos" : opp.confidence === "MEDIUM" ? "model" : "warn"}`} style={{ fontSize: 10 }}>
                            {opp.confidence}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── REPLACEMENTS VIEW ──────────────────────────────── */}
      {variant === "replacements" && (
        <div className="stack-14" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="data-block" data-testid="market-replacements-card">
            <div className="block-head">
              <div>
                <h3>Replacement Candidate Ranking</h3>
                <small style={{ color: "var(--muted)" }}>
                  Candidates ranked by composite fit score — role, age, and value dimensions
                </small>
              </div>
              <span className="badge model">
                {replacements.data?.total_candidates || 0} CANDIDATES
              </span>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", gap: 10, margin: "10px 0", flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
                <Filter size={12} /> Target profile:
              </div>
              <select
                value={replTargetPos}
                onChange={(e) => setReplTargetPos(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
                data-testid="repl-filter-position"
              >
                <option value="">Any Position</option>
                <option value="DEF">Defenders</option>
                <option value="MID">Midfielders</option>
                <option value="ATT">Attackers</option>
                <option value="GK">Goalkeepers</option>
              </select>
              <input
                type="text"
                placeholder="Target role (e.g. deep_playmaker)"
                value={replTargetRole}
                onChange={(e) => setReplTargetRole(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12, width: 200 }}
                data-testid="repl-filter-role"
              />
            </div>

            {replacements.isLoading && <p className="section-copy">Ranking replacement candidates…</p>}
            {replacements.isError && <p className="section-copy error-state">{apiErrorMessage(replacements.error)}</p>}

            {replacements.data && replacements.data.candidates.length === 0 && (
              <p className="section-copy" style={{ margin: "10px 0" }}>No replacement candidates match the target profile.</p>
            )}

            {replacements.data && replacements.data.candidates.length > 0 && (
              <div className="evidence-table-wrap" style={{ marginTop: 8 }}>
                <table className="evidence-table" style={{ width: "100%", textAlign: "left", fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Age</th>
                      <th>Position</th>
                      <th>Role</th>
                      <th>Role Fit</th>
                      <th>Age Fit</th>
                      <th>Value Fit</th>
                      <th>Composite</th>
                      <th>Est. Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {replacements.data.candidates.map((c) => (
                      <tr key={c.player_id}>
                        <td>
                          <Link to={`/players/${c.player_id}`} className="player-link" style={{ fontWeight: 600 }}>
                            {c.player_name}
                          </Link>
                        </td>
                        <td>{c.age ? `${c.age.toFixed(1)}` : "—"}</td>
                        <td>{c.position_group || "—"}</td>
                        <td style={{ fontSize: 11 }}>{c.role_archetype || "—"}</td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                          <span style={{ color: c.role_fit_score >= 0.7 ? "var(--teal)" : c.role_fit_score >= 0.4 ? "var(--amber)" : "var(--muted)" }}>
                            {(c.role_fit_score * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                          <span style={{ color: c.age_fit_score >= 0.7 ? "var(--teal)" : c.age_fit_score >= 0.4 ? "var(--amber)" : "var(--muted)" }}>
                            {(c.age_fit_score * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                          <span style={{ color: c.value_fit_score >= 0.7 ? "var(--teal)" : c.value_fit_score >= 0.4 ? "var(--amber)" : "var(--muted)" }}>
                            {(c.value_fit_score * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 600 }}>
                          <span style={{ color: c.composite_fit_score >= 0.7 ? "var(--teal)" : c.composite_fit_score >= 0.4 ? "var(--amber)" : "var(--muted)" }}>
                            {(c.composite_fit_score * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                          {c.estimated_value_eur != null ? `€${(c.estimated_value_eur / 1_000_000).toFixed(1)}M` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── TRANSFER RISK VIEW ──────────────────────────────── */}
      {variant === "risk" && (
        <div className="stack-14" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="data-block" data-testid="market-risk-card">
            <div className="block-head">
              <div>
                <h3>Transfer Risk Assessment</h3>
                <small style={{ color: "var(--muted)" }}>
                  Multi-dimensional risk profiles — performance, adaptation, financial, and availability
                </small>
              </div>
              <span className="badge model">
                {riskBatch.data?.total_assessed || 0} ASSESSED
              </span>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", gap: 10, margin: "10px 0", flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
                <Filter size={12} /> Filters:
              </div>
              <select
                value={riskFilterPos}
                onChange={(e) => setRiskFilterPos(e.target.value)}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
                data-testid="risk-filter-position"
              >
                <option value="">All Positions</option>
                <option value="DEF">Defenders</option>
                <option value="MID">Midfielders</option>
                <option value="ATT">Attackers</option>
                <option value="GK">Goalkeepers</option>
              </select>
            </div>

            {riskBatch.isLoading && <p className="section-copy">Assessing transfer risk across player universe…</p>}
            {riskBatch.isError && <p className="section-copy error-state">{apiErrorMessage(riskBatch.error)}</p>}

            {riskBatch.data && riskBatch.data.profiles.length === 0 && (
              <p className="section-copy" style={{ margin: "10px 0" }}>No risk profiles available for the selected filters.</p>
            )}

            {riskBatch.data && riskBatch.data.profiles.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                {riskBatch.data.profiles.map((profile) => (
                  <div
                    key={profile.player_id}
                    style={{
                      padding: "14px 16px",
                      background: "rgba(255,255,255,0.02)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      borderLeft: `3px solid ${riskColor(profile.overall_risk_level)}`,
                    }}
                    data-testid={`risk-profile-${profile.player_id}`}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <div>
                        <Link to={`/players/${profile.player_id}`} className="player-link" style={{ fontWeight: 600, fontSize: 14 }}>
                          {profile.player_name}
                        </Link>
                        <span style={{ marginLeft: 8, fontSize: 11, color: "var(--muted)" }}>
                          {profile.position_group} · {profile.age ? `${profile.age.toFixed(1)} yrs` : ""} {profile.current_club_name ? `· ${profile.current_club_name}` : ""}
                        </span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 600, color: riskColor(profile.overall_risk_level) }}>
                          {(profile.overall_risk_score * 100).toFixed(0)}%
                        </span>
                        <span className={`badge ${riskBadge(profile.overall_risk_level)}`} style={{ fontSize: 10 }}>
                          {profile.overall_risk_level}
                        </span>
                      </div>
                    </div>

                    <p style={{ margin: "0 0 8px 0", fontSize: 12, color: "var(--text-secondary)" }}>
                      {profile.risk_summary}
                    </p>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                      {profile.dimensions.map((dim) => (
                        <div
                          key={dim.dimension}
                          style={{
                            padding: "8px 10px",
                            background: "rgba(255,255,255,0.02)",
                            borderRadius: 6,
                            border: "1px solid var(--border)",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)", textTransform: "capitalize" }}>
                              {dim.dimension.toLowerCase()}
                            </span>
                            <span className={`badge ${riskBadge(dim.risk_level)}`} style={{ fontSize: 9 }}>
                              {dim.risk_level}
                            </span>
                          </div>
                          <div style={{ height: 4, borderRadius: 2, background: "var(--border)", overflow: "hidden", marginBottom: 4 }}>
                            <div
                              style={{
                                height: "100%",
                                width: `${dim.score * 100}%`,
                                background: riskColor(dim.risk_level),
                                borderRadius: 2,
                                transition: "width 0.5s ease",
                              }}
                            />
                          </div>
                          {dim.evidence.length > 0 && (
                            <p style={{ margin: 0, fontSize: 10, color: "var(--muted)", lineHeight: 1.4 }}>
                              {dim.evidence[0]}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
