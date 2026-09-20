import { ArrowUpRight, BarChart3, Database, Radio, ShieldAlert, Sprout, Target } from "lucide-react";
import { Link } from "react-router-dom";
import { BACKEND_GAPS } from "@/lib/footballApi";

const CONFIG = {
  overview: {
    eyebrow: "RECRUITMENT / MARKET",
    title: "Market intelligence",
    description: "Bring valuation, availability, and opportunity signals into one decision surface.",
    icon: BarChart3,
    dependency: "The connected Football Intelligence OS build does not yet expose market intelligence endpoints. This workspace is ready to render live valuation, opportunity, replacement, and risk feeds when they arrive.",
    surfaces: [
      { label: "Valuation", path: "/market/valuation", icon: Target, hint: "Estimated value with uncertainty and model version." },
      { label: "Opportunities", path: "/market/opportunities", icon: Sprout, hint: "Market gaps flagged against role coverage." },
      { label: "Replacements", path: "/market/replacements", icon: Radio, hint: "Candidate replacements ranked by fit and risk." },
      { label: "Transfer risk", path: "/market/risk", icon: ShieldAlert, hint: "Performance, adaptation, and financial risk." },
    ],
  },
  valuation: {
    eyebrow: "RECRUITMENT / VALUATION",
    title: "Player valuation",
    description: "Estimated fair value with uncertainty interval and model version — surfaced from the backend, never from a heuristic in the browser.",
    icon: Target,
    dependency: BACKEND_GAPS.valuation,
  },
  opportunities: {
    eyebrow: "RECRUITMENT / OPPORTUNITIES",
    title: "Market opportunities",
    description: "A calm alternative to “hidden gems” — players where estimated value diverges from reference value, with evidence attached.",
    icon: Sprout,
    dependency: BACKEND_GAPS.marketOpportunities,
  },
  replacements: {
    eyebrow: "RECRUITMENT / REPLACEMENTS",
    title: "Replacement finder",
    description: "Candidate replacements for a role or a departing player, ranked by role fit, tactical fit, value, and risk.",
    icon: Radio,
    dependency: BACKEND_GAPS.replacements,
  },
  risk: {
    eyebrow: "RECRUITMENT / RISK",
    title: "Transfer risk",
    description: "Performance, availability, adaptation, financial, and league-translation risk — classified only when backend evidence is sufficient.",
    icon: ShieldAlert,
    dependency: BACKEND_GAPS.transferRisk,
  },
};

export default function MarketPage({ variant = "overview" }) {
  const config = CONFIG[variant] || CONFIG.overview;
  const Icon = config.icon;

  return (
    <section className="intelligence-page" data-testid={`market-page-${variant}`}>
      <div className="page-heading">
        <div>
          <p className="eyebrow" data-testid="page-eyebrow">{config.eyebrow}</p>
          <h1 data-testid="page-title">{config.title}</h1>
          <p className="workspace-subtitle" data-testid="page-description">{config.description}</p>
        </div>
        <span className="badge warn" data-testid="market-dependency-badge">BACKEND DEPENDENCY</span>
      </div>

      {variant === "overview" && (
        <div className="dashboard-grid" data-testid="market-surfaces">
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

      <div className="empty-workspace" data-testid={`market-dependency-${variant}`}>
        <div className="empty-icon"><Icon size={22} /></div>
        <p className="eyebrow">BACKEND DEPENDENCY</p>
        <h2>Connect the market intelligence layer to populate this view.</h2>
        <p>{config.dependency}</p>
        <p style={{ marginTop: 12, color: "var(--muted-strong)", fontSize: 12 }}>
          <Database size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
          Expected contract: <code style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--cyan)" }}>/api/v1/market/*</code>
        </p>
      </div>
    </section>
  );
}
