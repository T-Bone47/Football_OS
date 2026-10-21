import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Activity, BarChart3, Beaker, Bookmark, Bot, Compass, Cpu, Database, Eye,
  GitCompare, GitFork, Globe, LayoutDashboard, Layers, PanelLeftClose,
  PanelLeftOpen, Radar, Radio, RefreshCw, Server, ShieldAlert, Target,
  TrendingUp, Trophy, Users, Briefcase,
} from "lucide-react";
import { DataFreshnessIndicator, StatusBadge } from "@/components/ui";

const GROUPS = [
  {
    label: "Overview",
    items: [
      { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { label: "Players", path: "/players", icon: Users, matchPrefix: "/players/" },
      { label: "Comparison", path: "/players/compare", icon: GitCompare },
      { label: "Similarity", path: "/players/similarity", icon: Compass },
      { label: "Roles", path: "/players/roles", icon: Layers },
      { label: "Tactical fit", path: "/tactical/fit", icon: Radar },
    ],
  },
  {
    label: "Recruitment",
    items: [
      { label: "Recruitment projects", path: "/recruitment/projects", icon: Briefcase },
      { label: "Watchlists & alerts", path: "/watchlists", icon: Eye },
      { label: "Decision engine", path: "/decisions", icon: Target, matchPrefix: "/decisions/" },
      { label: "Market", path: "/market", icon: BarChart3 },
      { label: "Valuation", path: "/market/valuation", icon: TrendingUp },
      { label: "Shortlists", path: "/shortlists", icon: Bookmark, matchPrefix: "/shortlists/" },
      { label: "Opportunities", path: "/market/opportunities", icon: Radio },
      { label: "Replacements", path: "/market/replacements", icon: Radio },
      { label: "Transfer risk", path: "/market/risk", icon: ShieldAlert },
    ],
  },
  {
    label: "Match intelligence",
    items: [
      { label: "Matches", path: "/matches", icon: Activity, matchPrefix: "/matches/" },
    ],
  },
  {
    label: "Squad",
    items: [
      { label: "Decision Lab 2.0", path: "/decision-lab", icon: Cpu },
      { label: "Squad builder", path: "/squad/builder", icon: Trophy },
      { label: "Scenarios (Multi-Alt)", path: "/scenarios", icon: GitFork },
      { label: "Transfer simulator", path: "/squad/simulator", icon: GitCompare },
      { label: "Scenario lab", path: "/squad/scenarios", icon: Beaker },
    ],
  },
  {
    label: "Research",
    items: [
      { label: "Outcome intelligence", path: "/outcome-intelligence", icon: Activity },
      { label: "Research lab", path: "/research", icon: Beaker },
      { label: "Models", path: "/research/models", icon: Cpu },
      { label: "Data sources", path: "/research/data", icon: Database },
      { label: "Experiments", path: "/research/experiments", icon: GitFork },
    ],
  },
  {
    label: "AI",
    items: [
      { label: "Scout copilot", path: "/copilot", icon: Bot },
    ],
  },
  {
    label: "System",
    items: [
      { label: "Live operations", path: "/operations", icon: Server },
      { label: "Global operations", path: "/operations/global", icon: Globe },
      { label: "Continuous learning", path: "/intelligence/continuous", icon: RefreshCw },
      { label: "Data quality", path: "/system/data-quality", icon: Database },
    ],
  },
];

export const NAV_GROUPS = GROUPS;

const STORAGE_KEY = "fios.sidebar.closed-groups";
const COLLAPSE_KEY = "fios.sidebar.collapsed";

function loadClosedGroups() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    return [];
  }
}

function itemIsActive(item, pathname) {
  if (item.path === "/dashboard") return pathname === "/dashboard" || pathname === "/";
  if (pathname === item.path) return true;
  if (!item.matchPrefix) return false;
  return pathname.startsWith(item.matchPrefix);
}

export function readSidebarCollapsed() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(COLLAPSE_KEY) === "1";
}

export function writeSidebarCollapsed(collapsed) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
}

export default function Sidebar({
  collapsed = false,
  onToggle,
  mobileOpen = false,
  onClose,
  providerLabel = "Provider",
  providerTone = "neutral",
  providerTitle = "",
  dataStatus = null,
  dataLoading = false,
  dataError = false,
}) {
  const location = useLocation();
  const navRef = useRef(null);
  const [closedGroups, setClosedGroups] = useState(loadClosedGroups);

  const toggleGroup = (label) => {
    setClosedGroups((previous) => {
      const next = previous.includes(label)
        ? previous.filter((entry) => entry !== label)
        : [...previous, label];
      try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch (error) { /* storage is optional */ }
      return next;
    });
  };

  useEffect(() => {
    if (mobileOpen) onClose?.();
    // Only close when the route changes, not when the drawer is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const freshnessHours = dataStatus?.metrics?.last_successful_ingestion_age_hours;
  const dataLabel = dataLoading
    ? "Checking data layer…"
    : dataError
      ? "Data layer unavailable"
      : dataStatus?.status || "Data layer unknown";

  const onNavKeyDown = (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = Array.from(navRef.current?.querySelectorAll("a[data-nav-item]") || []);
    if (items.length === 0) return;
    const index = items.indexOf(document.activeElement);
    if (index === -1) return;
    event.preventDefault();
    let next = index;
    if (event.key === "ArrowDown") next = (index + 1) % items.length;
    if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = items.length - 1;
    items[next]?.focus();
  };

  const groups = useMemo(() => GROUPS, []);

  return (
    <aside
      className={`fio-sidebar ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-open" : ""}`.trim()}
      data-testid="app-sidebar"
      aria-label="Workspace navigation"
    >
      <div className="fio-sidebar-brand" data-testid="sidebar-brand">
        <span className="fio-brand-mark" aria-hidden="true">FI</span>
        <span className="fio-brand-text">
          <span className="fio-brand-name">FOOTBALL INTELLIGENCE</span>
          <span className="fio-brand-sub">OPERATING SYSTEM</span>
        </span>
        {onToggle ? (
          <button
            type="button"
            className="fio-sidebar-toggle"
            onClick={onToggle}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            aria-pressed={collapsed}
            title={collapsed ? "Expand navigation" : "Collapse navigation"}
            data-testid="sidebar-collapse-toggle"
          >
            {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
          </button>
        ) : null}
      </div>

      <nav
        className="fio-sidebar-nav"
        aria-label="Primary navigation"
        data-testid="primary-navigation"
        ref={navRef}
        onKeyDown={onNavKeyDown}
      >
        {groups.map((group) => {
          const groupId = group.label.toLowerCase().replaceAll(" ", "-");
          const closed = closedGroups.includes(group.label) && !collapsed;
          return (
            <div className="fio-nav-group" key={group.label} data-testid={`nav-group-${groupId}`}>
              <button
                type="button"
                className="fio-nav-group-toggle"
                aria-expanded={!closed}
                aria-controls={`fio-nav-group-${groupId}`}
                onClick={() => toggleGroup(group.label)}
                data-testid={`nav-label-${groupId}`}
              >
                <span>{group.label}</span>
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
                  <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <div id={`fio-nav-group-${groupId}`} hidden={closed}>
                {group.items.map(({ label, path, icon: Icon, matchPrefix }) => {
                  const active = itemIsActive({ path, matchPrefix }, location.pathname);
                  return (
                    <NavLink
                      key={path}
                      to={path}
                      end
                      className={`fio-nav-item ${active ? "is-active" : ""}`.trim()}
                      aria-current={active ? "page" : undefined}
                      data-nav-item
                      data-tooltip={collapsed ? label : undefined}
                      title={collapsed ? label : undefined}
                      data-testid={`nav-link-${label.toLowerCase().replaceAll(" ", "-")}`}
                    >
                      <Icon size={15} aria-hidden="true" />
                      <span>{label}</span>
                    </NavLink>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      <div className="fio-sidebar-foot" data-testid="sidebar-data-status">
        <div className="fio-foot-row" title={providerTitle}>
          <span className={`fio-dot ${providerTone}`.trim()} aria-hidden="true" />
          <span className="fio-foot-text"><strong>AI</strong> · {providerLabel}</span>
        </div>
        <div className="fio-foot-row" title={dataLabel}>
          <span className={`fio-dot ${dataError ? "danger" : dataStatus?.status === "OK" ? "success" : "warn"}`.trim()} aria-hidden="true" />
          <span className="fio-foot-text">
            {dataLoading ? "Checking data…" : dataError ? "Data unavailable" : (
              <DataFreshnessIndicator hours={freshnessHours} label="Data" testId="sidebar-freshness" />
            )}
          </span>
        </div>
        {!collapsed ? (
          <StatusBadge tone={dataStatus?.status === "OK" ? "success" : dataError ? "danger" : "warn"} dot>
            {dataLabel}
          </StatusBadge>
        ) : null}
      </div>
    </aside>
  );
}
