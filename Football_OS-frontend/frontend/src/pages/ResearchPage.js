import { useQuery } from "@tanstack/react-query";
import { Beaker, Database, Layers } from "lucide-react";
import { apiErrorMessage, BACKEND_GAPS, getFeatureRegistry } from "@/lib/footballApi";

const CONFIG = {
  overview: { eyebrow: "RESEARCH / LAB", title: "Research workspace", description: "Datasets, features, and models — inspect provenance and analytical lineage." },
  models: { eyebrow: "RESEARCH / MODELS", title: "Model registry", description: "Model versions, training windows, and metric summaries surfaced from the backend." },
  data: { eyebrow: "RESEARCH / DATA", title: "Data sources", description: "Provider status, ingestion cadence, and canonical coverage." },
  experiments: { eyebrow: "RESEARCH / EXPERIMENTS", title: "Experiments", description: "Training runs, hypotheses, and outcomes." },
};

export default function ResearchPage({ variant = "overview" }) {
  const config = CONFIG[variant] || CONFIG.overview;
  const registry = useQuery({ queryKey: ["feature-registry"], queryFn: getFeatureRegistry, retry: false });

  return (
    <section className="intelligence-page" data-testid={`research-page-${variant}`}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{config.eyebrow}</p>
          <h1 data-testid="page-title">{config.title}</h1>
          <p className="workspace-subtitle" data-testid="page-description">{config.description}</p>
        </div>
        <span className="contract-badge">/api/v1/features/registry</span>
      </div>

      {variant !== "overview" ? (
        <div className="empty-workspace" data-testid={`research-dependency-${variant}`}>
          <div className="empty-icon"><Beaker size={22} /></div>
          <p className="eyebrow">BACKEND DEPENDENCY</p>
          <h2>Registry endpoints for {variant} are not yet exposed.</h2>
          <p>{BACKEND_GAPS.research}</p>
        </div>
      ) : (
        <>
          <div className="dashboard-grid three" style={{ marginTop: 24 }} data-testid="research-summary">
            <article className="intelligence-card">
              <span className="badge info"><Layers size={11} /> FEATURES</span>
              <div className="metric-value">{registry.data ? registry.data.length : "—"}</div>
              <p>Feature definitions currently registered in the backend.</p>
            </article>
            <article className="intelligence-card">
              <span className="badge model"><Beaker size={11} /> MODELS</span>
              <div className="metric-value">—</div>
              <p>Model registry endpoint not yet exposed.</p>
            </article>
            <article className="intelligence-card">
              <span className="badge warn"><Database size={11} /> DATA</span>
              <div className="metric-value">—</div>
              <p>Data source health surfacing planned. See Data quality workspace.</p>
            </article>
          </div>

          <div className="data-block" style={{ marginTop: 20 }} data-testid="research-features-block">
            <div className="section-heading">
              <div>
                <p className="eyebrow">FEATURE REGISTRY</p>
                <h3>Live definitions from the backend</h3>
              </div>
            </div>
            {registry.isLoading && <p className="section-copy">Loading feature registry…</p>}
            {registry.isError && <p className="section-copy error-state">{apiErrorMessage(registry.error)}</p>}
            {registry.data && registry.data.length === 0 && (
              <p className="section-copy">No feature definitions returned by the backend yet.</p>
            )}
            {registry.data && registry.data.length > 0 && (
              <div className="player-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>FEATURE</th>
                      <th>VERSION</th>
                      <th>OWNER</th>
                      <th>DESCRIPTION</th>
                    </tr>
                  </thead>
                  <tbody>
                    {registry.data.slice(0, 30).map((f, i) => (
                      <tr key={f.id || f.name || i}>
                        <td>{f.name || f.id || "—"}</td>
                        <td>{f.version || "—"}</td>
                        <td>{f.owner || "—"}</td>
                        <td>{f.description || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
