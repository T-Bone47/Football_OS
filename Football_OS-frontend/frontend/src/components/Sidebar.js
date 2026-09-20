import { NavLink } from "react-router-dom";
import {
  Activity, BarChart3, Beaker, Bookmark, Bot, Compass, Database, GitCompare,
  LayoutDashboard, Layers, Radar, Radio, ShieldAlert,
  Trophy, Users,
} from "lucide-react";

const groups = [
  { label: "Overview", items: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
  ]},
  { label: "Intelligence", items: [
    { label: "Players", path: "/players", icon: Users },
    { label: "Comparison", path: "/players/compare", icon: GitCompare },
    { label: "Similarity", path: "/players/similarity", icon: Compass },
    { label: "Roles", path: "/players/roles", icon: Layers },
    { label: "Tactical fit", path: "/tactical/fit", icon: Radar },
  ]},
  { label: "Recruitment", items: [
    { label: "Market", path: "/market", icon: BarChart3 },
    { label: "Shortlists", path: "/shortlists", icon: Bookmark },
    { label: "Opportunities", path: "/market/opportunities", icon: Radio },
    { label: "Replacements", path: "/market/replacements", icon: Radio },
    { label: "Transfer risk", path: "/market/risk", icon: ShieldAlert },
  ]},
  { label: "Match intelligence", items: [
    { label: "Matches", path: "/matches", icon: Activity },
  ]},
  { label: "Squad", items: [
    { label: "Squad builder", path: "/squad/builder", icon: Trophy },
    { label: "Transfer simulator", path: "/squad/simulator", icon: GitCompare },
    { label: "Scenario lab", path: "/squad/scenarios", icon: Beaker },
  ]},
  { label: "Research", items: [
    { label: "Research lab", path: "/research", icon: Beaker },
    { label: "Data sources", path: "/research/data", icon: Database },
  ]},
  { label: "AI", items: [
    { label: "Scout copilot", path: "/copilot", icon: Bot },
  ]},
  { label: "System", items: [
    { label: "Data quality", path: "/system/data-quality", icon: Database },
  ]},
];

export default function Sidebar() {
  return (
    <aside className="sidebar" data-testid="app-sidebar">
      <div className="sidebar-brand" data-testid="sidebar-brand">
        <span className="brand-mark small" aria-hidden="true">FI</span>
        <span>FOOTBALL<br />INTELLIGENCE OS</span>
      </div>
      <nav aria-label="Primary navigation" data-testid="primary-navigation">
        {groups.map((group) => (
          <div className="nav-group" key={group.label} data-testid={`nav-group-${group.label.toLowerCase().replaceAll(" ", "-")}`}>
            <p className="nav-label" data-testid={`nav-label-${group.label.toLowerCase().replaceAll(" ", "-")}`}>{group.label}</p>
            {group.items.map(({ label, path, icon: Icon }) => (
              <NavLink
                key={path}
                to={path}
                end={path === "/dashboard"}
                className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}
                data-testid={`nav-link-${label.toLowerCase().replaceAll(" ", "-")}`}
              >
                <Icon size={13} aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-foot" data-testid="sidebar-data-status">
        <span className="live-dot warn" />
        <span>Backend pending</span>
      </div>
    </aside>
  );
}
