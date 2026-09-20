import { NavLink } from "react-router-dom";
import { Activity, BarChart3, Bot, Database, GitCompare, LayoutDashboard, Radar, Search, ShieldAlert, Users } from "lucide-react";

const groups = [
  { label: "Overview", items: [{ label: "Dashboard", path: "/dashboard", icon: LayoutDashboard }] },
  { label: "Intelligence", items: [{ label: "Players", path: "/players", icon: Users }, { label: "Similarity", path: "/players/similarity", icon: GitCompare }, { label: "Tactical fit", path: "/tactical/fit", icon: Radar }] },
  { label: "Recruitment", items: [{ label: "Market", path: "/market", icon: BarChart3 }, { label: "Transfer risk", path: "/market/risk", icon: ShieldAlert }] },
  { label: "Match intelligence", items: [{ label: "Matches", path: "/matches", icon: Activity }] },
  { label: "Research", items: [{ label: "Research lab", path: "/research", icon: Database }, { label: "Scout copilot", path: "/copilot", icon: Bot }] },
];

export default function Sidebar() {
  return <aside className="sidebar" data-testid="app-sidebar">
    <div className="sidebar-brand" data-testid="sidebar-brand"><span className="brand-mark small">FI</span><span>FOOTBALL<br />INTELLIGENCE OS</span></div>
    <nav aria-label="Primary navigation" data-testid="primary-navigation">
      {groups.map((group) => <div className="nav-group" key={group.label} data-testid={`nav-group-${group.label.toLowerCase().replaceAll(" ", "-")}`}>
        <p className="nav-label" data-testid={`nav-label-${group.label.toLowerCase().replaceAll(" ", "-")}`}>{group.label}</p>
        {group.items.map(({ label, path, icon: Icon }) => <NavLink key={path} to={path} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"} data-testid={`nav-link-${label.toLowerCase().replaceAll(" ", "-")}`}><Icon size={16} aria-hidden="true" /><span>{label}</span></NavLink>)}
      </div>)}
    </nav>
    <div className="sidebar-foot" data-testid="sidebar-data-status"><span className="live-dot" /> Data layer ready to connect</div>
  </aside>;
}

export function MobileSearchButton({ onClick }) {
  return <button className="mobile-search" onClick={onClick} data-testid="mobile-search-button" aria-label="Open global search"><Search size={18} /></button>;
}