import { useEffect, useMemo, useState } from "react";
import { Command, Search, Sparkles, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getClubs, getPlayers } from "@/lib/footballApi";
import { fade, motion, pop } from "@/lib/motion";

const pages = [
  { label: "Player discovery", path: "/players", hint: "Filter the connected player universe" },
  { label: "Player comparison", path: "/players/compare", hint: "Compare 2–5 players side by side" },
  { label: "Similarity explorer", path: "/players/similarity", hint: "Find comparable players" },
  { label: "Role discovery", path: "/players/roles", hint: "Explore role clusters" },
  { label: "Tactical fit", path: "/tactical/fit", hint: "Fit players to teams and systems" },
  { label: "Market intelligence", path: "/market", hint: "Recruitment context" },
  { label: "Transfer risk", path: "/market/risk", hint: "Review risk classifications" },
  { label: "Match intelligence", path: "/matches", hint: "Match center" },
  { label: "Squad builder", path: "/squad/builder", hint: "Construct squads" },
  { label: "Scenario lab", path: "/squad/scenarios", hint: "Run what-if analyses" },
  { label: "Scout copilot", path: "/copilot", hint: "Ask the analytical system" },
  { label: "Data quality", path: "/system/data-quality", hint: "Ingestion & coverage" },
];

const suggestedQueries = [
  "Find a left-footed progressive CB under €30M",
  "Compare Wirtz vs Musiala",
  "Show midfielders similar to Rodri",
];

export default function CommandPalette({ open, onClose }) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const players = useQuery({ queryKey: ["command-players"], queryFn: () => getPlayers(), enabled: open, staleTime: 120000, retry: false });
  const clubs = useQuery({ queryKey: ["command-clubs"], queryFn: getClubs, enabled: open, staleTime: 120000, retry: false });
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const normalized = query.trim().toLowerCase();
  const results = useMemo(() => ({
    players: (players.data || []).filter((item) => item.name?.toLowerCase().includes(normalized)).slice(0, 5),
    clubs: (clubs.data || []).filter((item) => item.name?.toLowerCase().includes(normalized)).slice(0, 4),
    pages: pages.filter((item) => item.label.toLowerCase().includes(normalized) || !normalized).slice(0, 6),
  }), [clubs.data, normalized, players.data]);

  if (!open) return null;
  const go = (path) => { setQuery(""); onClose(); navigate(path); };
  const goCopilot = (prefill) => { setQuery(""); onClose(); navigate("/copilot", { state: { prefill } }); };
  const backendUnavailable = players.isError || clubs.isError;

  return (
    <motion.div className="command-backdrop" role="presentation" onClick={onClose} data-testid="command-palette-backdrop"
                variants={fade} initial="initial" animate="animate" exit="exit">
      <motion.section
        variants={pop}
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Global command search"
        onClick={(event) => event.stopPropagation()}
        data-testid="command-palette"
      >
        <div className="command-search">
          <Search size={17} />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find players, clubs, pages, or ask the copilot"
            data-testid="command-search-input"
          />
          <button className="icon-button" onClick={onClose} aria-label="Close command search" data-testid="command-palette-close">
            <X size={16} />
          </button>
        </div>
        <div className="command-hint" data-testid="command-search-hint">
          <Command size={12} /> Global search · press <kbd>Enter</kbd> on a copilot prompt to ask
        </div>
        <div className="command-results" data-testid="command-results">
          {normalized && (
            <div>
              <p className="command-label">ASK COPILOT</p>
              <button
                className="command-result"
                onClick={() => goCopilot(query)}
                data-testid="command-ask-copilot"
              >
                <span><Sparkles size={14} style={{ verticalAlign: "-2px", marginRight: 6, color: "var(--purple)" }} /> Ask: “{query}”</span>
                <small>Open Scout copilot</small>
              </button>
            </div>
          )}
          {results.players.length > 0 && (
            <div>
              <p className="command-label">PLAYERS</p>
              {results.players.map((player) => (
                <button
                  className="command-result"
                  key={player.id}
                  onClick={() => go(`/players/${player.id}`)}
                  data-testid={`command-player-${player.id}`}
                >
                  <span>{player.name}</span>
                  <small>{player.primary_position || "Position unavailable"}</small>
                </button>
              ))}
            </div>
          )}
          {results.clubs.length > 0 && (
            <div>
              <p className="command-label">CLUBS</p>
              {results.clubs.map((club) => (
                <div className="command-result read-only" key={club.id} data-testid={`command-club-${club.id}`}>
                  <span>{club.name}</span>
                  <small>{club.country || "Country unknown"}</small>
                </div>
              ))}
            </div>
          )}
          <div>
            <p className="command-label">PAGES & ACTIONS</p>
            {results.pages.map((item) => (
              <button
                className="command-result"
                key={item.path}
                onClick={() => go(item.path)}
                data-testid={`command-page-${item.path.replaceAll("/", "-")}`}
              >
                <span>{item.label}</span>
                <small>{item.hint}</small>
              </button>
            ))}
          </div>
          {!normalized && (
            <div>
              <p className="command-label">TRY ASKING</p>
              {suggestedQueries.map((suggestion) => (
                <button
                  key={suggestion}
                  className="command-result"
                  onClick={() => goCopilot(suggestion)}
                  data-testid={`command-suggestion-${suggestion.slice(0, 20).replaceAll(" ", "-")}`}
                >
                  <span>{suggestion}</span>
                  <small>Open in copilot</small>
                </button>
              ))}
            </div>
          )}
          {backendUnavailable && !normalized && (
            <p className="command-empty" data-testid="command-backend-warning">
              Live player &amp; club results will appear once the Football Intelligence OS API is connected.
            </p>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
