import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Search } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import CommandPalette from "@/components/CommandPalette";
import { AnimatePresence, fadeUp, motion } from "@/lib/motion";

const BREADCRUMBS = [
  { pattern: /^\/dashboard/, trail: ["Overview", "Dashboard"] },
  { pattern: /^\/players\/compare/, trail: ["Intelligence", "Comparison"] },
  { pattern: /^\/players\/similarity/, trail: ["Intelligence", "Similarity"] },
  { pattern: /^\/players\/roles/, trail: ["Intelligence", "Roles"] },
  { pattern: /^\/players\/[^/]+/, trail: ["Intelligence", "Players", "Profile"] },
  { pattern: /^\/players/, trail: ["Intelligence", "Players"] },
  { pattern: /^\/tactical\/fit/, trail: ["Intelligence", "Tactical fit"] },
  { pattern: /^\/market\/valuation/, trail: ["Recruitment", "Valuation"] },
  { pattern: /^\/market\/opportunities/, trail: ["Recruitment", "Opportunities"] },
  { pattern: /^\/market\/replacements/, trail: ["Recruitment", "Replacements"] },
  { pattern: /^\/market\/risk/, trail: ["Recruitment", "Transfer risk"] },
  { pattern: /^\/market/, trail: ["Recruitment", "Market"] },
  { pattern: /^\/matches\/[^/]+/, trail: ["Match intelligence", "Match"] },
  { pattern: /^\/matches/, trail: ["Match intelligence", "Matches"] },
  { pattern: /^\/squad\/builder/, trail: ["Squad", "Builder"] },
  { pattern: /^\/squad\/simulator/, trail: ["Squad", "Transfer simulator"] },
  { pattern: /^\/squad\/scenarios/, trail: ["Squad", "Scenario lab"] },
  { pattern: /^\/research\/models/, trail: ["Research", "Models"] },
  { pattern: /^\/research\/data/, trail: ["Research", "Data sources"] },
  { pattern: /^\/research\/experiments/, trail: ["Research", "Experiments"] },
  { pattern: /^\/research/, trail: ["Research", "Lab"] },
  { pattern: /^\/system\/data-quality/, trail: ["System", "Data quality"] },
  { pattern: /^\/copilot/, trail: ["AI", "Scout copilot"] },
  { pattern: /^\/shortlists\/[^/]+/, trail: ["Recruitment", "Shortlists", "Board"] },
  { pattern: /^\/shortlists/, trail: ["Recruitment", "Shortlists"] },
];

function Breadcrumb({ pathname }) {
  const match = BREADCRUMBS.find((b) => b.pattern.test(pathname));
  const trail = match?.trail || ["Football Intelligence OS"];
  return (
    <div className="topbar-breadcrumb" data-testid="topbar-breadcrumb">
      {trail.map((label, i) => (
        <span key={i} className={i === trail.length - 1 ? "current" : ""}>
          {label}
          {i < trail.length - 1 && <span className="sep" style={{ marginLeft: 8 }}>/</span>}
        </span>
      ))}
    </div>
  );
}

export default function AppShell({ children }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const close = useCallback(() => setOpen(false), []);
  useEffect(() => {
    const onKey = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app-shell" data-testid="application-shell">
      <Sidebar />
      <main className="workspace">
        <div className="topbar" data-testid="topbar">
          <Breadcrumb pathname={location.pathname} />
          <span className="topbar-spacer" />
          <button
            className="global-command-button"
            onClick={() => setOpen(true)}
            data-testid="global-command-button"
          >
            <span style={{ display: "inline-flex", alignItems: "center" }}>
              <Search size={13} className="cmd-icon" />
              <span>Search players, clubs, actions</span>
            </span>
            <kbd>⌘K</kbd>
          </button>
        </div>
        {/* Route change: the new page fades in. Enter-only on purpose: an
            exit-then-enter ("wait") transition held whole pages in the DOM and
            could leave the workspace blank. */}
        <motion.div key={location.pathname} className="page-transition" variants={fadeUp}
                    initial="initial" animate="animate">
          {children}
        </motion.div>
      </main>
      <AnimatePresence>
        {open && <CommandPalette open={open} onClose={close} />}
      </AnimatePresence>
    </div>
  );
}
