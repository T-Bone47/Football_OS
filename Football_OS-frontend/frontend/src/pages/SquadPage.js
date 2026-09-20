import { Beaker, Database, GitCompare, Layers, Trophy } from "lucide-react";
import { BACKEND_GAPS } from "@/lib/footballApi";
import PitchHeatmap from "@/components/PitchHeatmap";

const CONFIG = {
  builder: {
    eyebrow: "SQUAD / BUILDER",
    title: "Squad builder",
    description: "Construct a squad against a formation, identify role coverage gaps, and prepare candidate targets.",
    icon: Trophy,
    dependency: BACKEND_GAPS.squadBuilder,
  },
  simulator: {
    eyebrow: "SQUAD / TRANSFER SIMULATOR",
    title: "Transfer simulator",
    description: "Model incoming and outgoing transfers. Before / after impact on squad quality, age, role coverage, and risk.",
    icon: GitCompare,
    dependency: BACKEND_GAPS.scenario,
  },
  scenarios: {
    eyebrow: "SQUAD / SCENARIO LAB",
    title: "Scenario lab",
    description: "Compose baselines and scenarios. Every result carries provenance for the underlying calculation.",
    icon: Beaker,
    dependency: BACKEND_GAPS.scenario,
  },
};

export default function SquadPage({ variant = "builder" }) {
  const config = CONFIG[variant] || CONFIG.builder;
  const Icon = config.icon;
  return (
    <section className="intelligence-page" data-testid={`squad-page-${variant}`}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{config.eyebrow}</p>
          <h1 data-testid="page-title">{config.title}</h1>
          <p className="workspace-subtitle" data-testid="page-description">{config.description}</p>
        </div>
        <span className="badge warn">BACKEND DEPENDENCY</span>
      </div>

      <div className="split-columns" style={{ marginTop: 24 }}>
        <div className="data-block" data-testid="squad-pitch-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SYSTEM PREVIEW</p>
              <h3>Formation ready for backend feed</h3>
            </div>
          </div>
          <PitchHeatmap formation="4-3-3" caption="4-3-3 · reference" testId="squad-pitch" />
        </div>

        <div className="data-block" data-testid="squad-summary-panel">
          <div className="section-heading">
            <div><p className="eyebrow">SQUAD SUMMARY</p><h3>Waiting for evidence</h3></div>
          </div>
          <div className="kv-list">
            <div><span>Squad quality</span><b>—</b></div>
            <div><span>Median age</span><b>—</b></div>
            <div><span>Wage bill</span><b>—</b></div>
            <div><span>Transfer spend</span><b>—</b></div>
            <div><span>Role coverage</span><b>—</b></div>
            <div><span>Tactical fit</span><b>—</b></div>
            <div><span>Depth risk</span><b>—</b></div>
          </div>
        </div>
      </div>

      <div className="empty-workspace" data-testid={`squad-dependency-${variant}`} style={{ marginTop: 24 }}>
        <div className="empty-icon"><Icon size={22} /></div>
        <p className="eyebrow">BACKEND DEPENDENCY</p>
        <h2>Connect squad construction endpoints to activate this workspace.</h2>
        <p>{config.dependency}</p>
        <p style={{ marginTop: 12, color: "var(--muted-strong)", fontSize: 12 }}>
          <Database size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
          Expected contract: <code style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--cyan)" }}>/api/v1/squads · /api/v1/scenarios</code>
        </p>
      </div>
    </section>
  );
}
