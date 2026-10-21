import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, LogOut, Menu, Search, ShieldCheck } from "lucide-react";
import Sidebar, { readSidebarCollapsed, writeSidebarCollapsed } from "@/components/Sidebar";
import CommandPalette from "@/components/CommandPalette";
import { DEMO_ONLY_EVENT, getDataStatus, getLLMStatus, logout } from "@/lib/footballApi";
import { useSession } from "@/lib/session";

const TRAILS = [
  [/^\/dashboard/, ["Overview", "Dashboard"]],
  [/^\/players\/compare/, ["Intelligence", "Comparison"]],
  [/^\/players\/similarity/, ["Intelligence", "Similarity"]],
  [/^\/players\/roles/, ["Intelligence", "Roles"]],
  [/^\/players\/[^/]+$/, ["Intelligence", "Players", "Player profile"]],
  [/^\/players$/, ["Intelligence", "Players"]],
  [/^\/tactical\/fit/, ["Intelligence", "Tactical fit"]],
  [/^\/market\/valuation/, ["Recruitment", "Valuation"]],
  [/^\/market\/opportunities/, ["Recruitment", "Opportunities"]],
  [/^\/market\/replacements/, ["Recruitment", "Replacements"]],
  [/^\/market\/risk/, ["Recruitment", "Transfer risk"]],
  [/^\/market$/, ["Recruitment", "Market"]],
  [/^\/recruitment\/projects/, ["Recruitment", "Projects"]],
  [/^\/watchlists/, ["Recruitment", "Watchlists & alerts"]],
  [/^\/decisions\/recruitment/, ["Recruitment", "Decision engine", "Recruitment"]],
  [/^\/decisions\/replacement/, ["Recruitment", "Decision engine", "Replacement"]],
  [/^\/decisions\/scenarios/, ["Recruitment", "Decision engine", "Scenarios"]],
  [/^\/decisions/, ["Recruitment", "Decision engine"]],
  [/^\/shortlists\/[^/]+$/, ["Recruitment", "Shortlists", "Board"]],
  [/^\/shortlists/, ["Recruitment", "Shortlists"]],
  [/^\/matches\/[^/]+$/, ["Match intelligence", "Match detail"]],
  [/^\/matches/, ["Match intelligence", "Matches"]],
  [/^\/squad\/builder/, ["Squad", "Builder"]],
  [/^\/squad\/simulator/, ["Squad", "Transfer simulator"]],
  [/^\/squad\/scenarios/, ["Squad", "Scenario lab"]],
  [/^\/scenarios/, ["Squad", "Multi-alternative scenarios"]],
  [/^\/research\/models/, ["Research", "Models"]],
  [/^\/research\/data/, ["Research", "Data sources"]],
  [/^\/research\/experiments/, ["Research", "Experiments"]],
  [/^\/research/, ["Research", "Lab"]],
  [/^\/system\/data-quality/, ["System", "Data quality"]],
  [/^\/copilot/, ["AI", "Scout copilot"]],
  [/^\/operations\/global/, ["System", "Global operations"]],
  [/^\/operations/, ["System", "Live operations"]],
  [/^\/intelligence\/continuous/, ["System", "Continuous learning"]],
  [/^\/decision-lab/, ["Squad", "Decision Lab 2.0"]],
  [/^\/outcome-intelligence/, ["Research", "Outcome intelligence"]],
];

function Breadcrumbs({ pathname }) {
  const match = TRAILS.find(([pattern]) => pattern.test(pathname));
  const trail = match ? match[1] : ["Football Intelligence OS"];
  return (
    <nav className="fio-breadcrumbs" aria-label="Breadcrumb" data-testid="topbar-breadcrumb">
      {trail.map((label, index) => {
        const current = index === trail.length - 1;
        return (
          <span key={`${label}-${index}`} className={`fio-crumb ${current ? "current" : ""}`.trim()}>
            {current ? (
              <span aria-current="page" title={label}>{label}</span>
            ) : (
              <span>{label}</span>
            )}
            {!current ? <span className="fio-crumb-sep" aria-hidden="true">/</span> : null}
          </span>
        );
      })}
    </nav>
  );
}

function ProviderPill({ llm }) {
  const active = llm.data?.active || {};
  const status = active.status || (llm.isError ? "UNAVAILABLE" : llm.isPending ? "CHECKING" : "NOT_CONFIGURED");
  const provider = active.provider || "Provider";
  const model = active.model || "model not reported";
  const tone = status === "AVAILABLE" ? "success" : status === "CHECKING" ? "" : status === "NOT_CONFIGURED" ? "" : "warn";
  const title = [
    `${provider} · ${model}`,
    `Status: ${status}`,
    `Streaming: ${active.streaming_verified ? "verified" : "unverified"}`,
    `Fallback used: ${active.fallback_used ? "yes" : "no"}`,
  ].join("\n");
  return (
    <span className={`fio-status-pill`} title={title} data-testid="topbar-provider-status">
      <span className={`fio-dot ${tone}`.trim()} aria-hidden="true" />
      <span className="fio-status-text">{provider} · {status}</span>
      <span className="fio-visually-hidden">{title}</span>
    </span>
  );
}

function DataPill({ dataStatus }) {
  const hours = dataStatus.data?.metrics?.last_successful_ingestion_age_hours;
  const status = dataStatus.data?.status || (dataStatus.isError ? "UNAVAILABLE" : dataStatus.isPending ? "CHECKING" : "UNKNOWN");
  const tone = status === "OK" ? "success" : status === "CHECKING" ? "" : "warn";
  const age = typeof hours === "number"
    ? hours < 1 ? `${Math.round(hours * 60)}m` : hours < 48 ? `${hours.toFixed(1)}h` : `${Math.round(hours / 24)}d`
    : "—";
  const title = status === "OK"
    ? `Last successful ingestion ${age} ago · schema ${dataStatus.data?.schema_version || "unknown"}`
    : `Data layer ${status}`;
  return (
    <Link className="fio-status-pill" to="/system/data-quality" title={title} data-testid="topbar-data-status">
      <span className={`fio-dot ${tone}`.trim()} aria-hidden="true" />
      <span className="fio-status-text">Data · {age}</span>
      <span className="fio-visually-hidden">{title}</span>
    </Link>
  );
}

function UserMenu({ user }) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event) => {
      if (wrapper.current && !wrapper.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = user?.name || "Local scout";
  const email = user?.email || "session not reported";
  const role = user?.role || "Scout";
  const initials = name.split(/\s+/).map((part) => part[0]).filter(Boolean).slice(0, 2).join("").toUpperCase() || "FI";

  const signOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div ref={wrapper} style={{ position: "relative" }}>
      <button
        type="button"
        className="fio-user-button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        data-testid="user-menu-button"
      >
        <span className="fio-avatar" aria-hidden="true">{initials}</span>
        <span className="fio-user-copy">
          <strong>{name}</strong>
          <span>{role}</span>
        </span>
      </button>
      {open ? (
        <div className="fio-user-menu" role="menu" data-testid="user-menu">
          <div className="fio-user-menu-head">
            <strong>{name}</strong>
            <span>{email}</span>
          </div>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); navigate("/system/data-quality"); }}>
            <ShieldCheck size={14} /> Data quality &amp; provenance
          </button>
          <button type="button" role="menuitem" onClick={signOut} data-testid="logout-button">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function AppShell({ children }) {
  const user = useSession();
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readSidebarCollapsed);
  const [demoOnly, setDemoOnly] = useState(false);
  const location = useLocation();

  const llm = useQuery({ queryKey: ["llm-status"], queryFn: getLLMStatus, retry: false, staleTime: 30000 });
  const dataStatus = useQuery({ queryKey: ["data-status"], queryFn: getDataStatus, retry: false, staleTime: 30000 });

  const toggleSidebar = useCallback(() => {
    setCollapsed((previous) => {
      const next = !previous;
      writeSidebarCollapsed(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const onKey = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
      }
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onDemoOnly = () => setDemoOnly(true);
    window.addEventListener(DEMO_ONLY_EVENT, onDemoOnly);
    return () => window.removeEventListener(DEMO_ONLY_EVENT, onDemoOnly);
  }, []);
  useEffect(() => { setDemoOnly(false); }, [location.pathname]);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [mobileOpen]);

  const closeCommand = useCallback(() => setCommandOpen(false), []);

  const active = llm.data?.active || {};
  const providerStatus = active.status || (llm.isError ? "UNAVAILABLE" : llm.isPending ? "CHECKING" : "NOT_CONFIGURED");
  const providerTone = providerStatus === "AVAILABLE" ? "success" : providerStatus === "CHECKING" ? "" : providerStatus === "NOT_CONFIGURED" ? "" : "warn";
  const providerLabel = active.provider ? `${active.provider} · ${providerStatus}` : providerStatus;

  return (
    <div className={`fio-shell ${collapsed ? "is-collapsed" : ""}`.trim()} data-testid="application-shell">
      <a className="fio-skip-link" href="#main-content">Skip to main content</a>
      <Sidebar
        collapsed={collapsed}
        onToggle={toggleSidebar}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        providerLabel={providerLabel}
        providerTone={providerTone}
        providerTitle={`${active.provider || "Provider"} · ${active.model || "model not reported"} · streaming ${active.streaming_verified ? "verified" : "unverified"}`}
        dataStatus={dataStatus.data}
        dataLoading={dataStatus.isPending}
        dataError={dataStatus.isError}
      />
      {mobileOpen ? <div className="fio-drawer-backdrop" onClick={() => setMobileOpen(false)} aria-hidden="true" /> : null}

      <div className="fio-main">
        <header className="fio-topbar" data-testid="topbar">
          <button
            type="button"
            className="fio-icon-btn fio-menu-btn"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            data-testid="mobile-nav-open"
          >
            <Menu size={17} />
          </button>
          <Breadcrumbs pathname={location.pathname} />
          <span className="fio-topbar-spacer" />
          <button
            type="button"
            className="fio-search-trigger"
            onClick={() => setCommandOpen(true)}
            aria-label="Open global search"
            data-testid="global-command-button"
          >
            <Search size={14} aria-hidden="true" />
            <span>Search players, clubs, pages…</span>
            <kbd>⌘K</kbd>
          </button>
          <ProviderPill llm={llm} />
          <DataPill dataStatus={dataStatus} />
          <UserMenu user={user} />
        </header>

        {demoOnly ? (
          <div className="fio-demo-wrap">
            <div className="fio-notice warn" data-testid="demo-only-banner" role="status">
              <AlertTriangle size={15} aria-hidden="true" />
              <div>
                <strong>Demonstration module disabled</strong>
                <p>This module runs on built-in demonstration figures, not on your data, so it is disabled in this deployment until it is rebuilt on verified data.</p>
              </div>
            </div>
          </div>
        ) : null}

        <main className="fio-content" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>

      <CommandPalette open={commandOpen} onClose={closeCommand} />
    </div>
  );
}
