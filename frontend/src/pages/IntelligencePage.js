import { Search, SlidersHorizontal, ArrowUpRight, Database, ChevronRight } from "lucide-react";

const pageConfig = {
  "/players": { eyebrow: "INTELLIGENCE / PLAYERS", title: "Player discovery", description: "Search the connected player universe by role, context, and evidence.", action: "Add filters", icon: Search },
  "/players/similarity": { eyebrow: "INTELLIGENCE / SIMILARITY", title: "Similarity explorer", description: "Compare role and statistical context when the embedding service is connected.", action: "Select player", icon: SlidersHorizontal },
  "/market": { eyebrow: "RECRUITMENT / MARKET", title: "Market intelligence", description: "Bring valuation, availability, and opportunity signals into one decision surface.", action: "Set market view", icon: ArrowUpRight },
  "/market/risk": { eyebrow: "RECRUITMENT / RISK", title: "Transfer risk", description: "Review evidence behind performance, adaptation, and financial risk classifications.", action: "Choose player", icon: SlidersHorizontal },
  "/tactical/fit": { eyebrow: "TACTICAL / FIT", title: "Tactical fit", description: "Test a player against a team, formation, and role using backend feature definitions.", action: "Configure fit", icon: SlidersHorizontal },
  "/matches": { eyebrow: "MATCH INTELLIGENCE", title: "Match center", description: "A calm view of upcoming fixtures, model context, and team evidence.", action: "Select match", icon: ArrowUpRight },
  "/research": { eyebrow: "RESEARCH LAB", title: "Research workspace", description: "Inspect datasets, models, and experiments without losing analytical provenance.", action: "View data sources", icon: Database },
  "/copilot": { eyebrow: "AI / SCOUT COPILOT", title: "Scout copilot", description: "Ask the analytical system a question and keep every answer attached to its evidence.", action: "Connect copilot", icon: Search },
};

export default function IntelligencePage({ path }) {
  const config = pageConfig[path] || pageConfig["/players"];
  const Icon = config.icon;
  return <section className="intelligence-page" data-testid="intelligence-page">
    <div className="page-heading"><div><p className="eyebrow" data-testid="page-eyebrow">{config.eyebrow}</p><h1 data-testid="page-title">{config.title}</h1><p className="workspace-subtitle" data-testid="page-description">{config.description}</p></div><button className="outline-button" data-testid="page-action-button"><Icon size={16} /> {config.action}</button></div>
    <div className="workspace-toolbar" data-testid="workspace-toolbar"><div className="command-input" data-testid="workspace-search"><Search size={16} /><span>Search this workspace</span><kbd>⌘ K</kbd></div><button className="toolbar-button" data-testid="workspace-filter-button"><SlidersHorizontal size={16} /> Filters</button></div>
    <div className="empty-workspace" data-testid="backend-dependency-state"><div className="empty-icon"><Database size={22} /></div><p className="eyebrow" data-testid="empty-state-label">BACKEND DEPENDENCY</p><h2 data-testid="empty-state-heading">Connect the intelligence layer to populate this view.</h2><p data-testid="empty-state-description">This screen is ready for the existing API contract. No analytical values are shown until the source provides them.</p><button className="text-button" data-testid="empty-state-details-button">View dependency details <ChevronRight size={16} /></button></div>
  </section>;
}