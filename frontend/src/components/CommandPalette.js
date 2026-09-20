import { useEffect, useMemo, useState } from "react";
import { Command, Search, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getClubs, getPlayers } from "@/lib/footballApi";

const pages = [{ label: "Player search", path: "/players" }, { label: "Similarity explorer", path: "/players/similarity" }, { label: "Market intelligence", path: "/market" }, { label: "Tactical fit", path: "/tactical/fit" }, { label: "Scout copilot", path: "/copilot" }];

export default function CommandPalette({ open, onClose }) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const players = useQuery({ queryKey: ["command-players"], queryFn: () => getPlayers(), enabled: open, staleTime: 120000 });
  const clubs = useQuery({ queryKey: ["command-clubs"], queryFn: getClubs, enabled: open, staleTime: 120000 });
  useEffect(() => { if (!open) return undefined; const onKey = (event) => { if (event.key === "Escape") onClose(); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [open, onClose]);
  const normalized = query.toLowerCase();
  const results = useMemo(() => ({ players: (players.data || []).filter((item) => item.name.toLowerCase().includes(normalized)).slice(0, 5), clubs: (clubs.data || []).filter((item) => item.name.toLowerCase().includes(normalized)).slice(0, 4), pages: pages.filter((item) => item.label.toLowerCase().includes(normalized)) }), [clubs.data, normalized, players.data]);
  if (!open) return null;
  const go = (path) => { setQuery(""); onClose(); navigate(path); };
  return <div className="command-backdrop" role="presentation" onClick={onClose} data-testid="command-palette-backdrop"><section className="command-palette" role="dialog" aria-modal="true" aria-label="Global command search" onClick={(event) => event.stopPropagation()} data-testid="command-palette"><div className="command-search"><Search size={18} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find players, clubs, pages, or actions" data-testid="command-search-input" /><button className="icon-button" onClick={onClose} aria-label="Close command search" data-testid="command-palette-close"><X size={17} /></button></div><div className="command-hint" data-testid="command-search-hint"><Command size={13} /> Search the connected intelligence layer</div><div className="command-results" data-testid="command-results">{results.players.length > 0 && <div><p className="command-label">PLAYERS</p>{results.players.map((player) => <button className="command-result" key={player.id} onClick={() => go(`/players/${player.id}`)} data-testid={`command-player-${player.id}`}><span>{player.name}</span><small>{player.primary_position || "Position unavailable"}</small></button>)}</div>}{results.clubs.length > 0 && <div><p className="command-label">CLUBS</p>{results.clubs.map((club) => <div className="command-result read-only" key={club.id} data-testid={`command-club-${club.id}`}><span>{club.name}</span><small>{club.country}</small></div>)}</div>}{results.pages.length > 0 && <div><p className="command-label">PAGES & ACTIONS</p>{results.pages.map((item) => <button className="command-result" key={item.path} onClick={() => go(item.path)} data-testid={`command-page-${item.path.replaceAll("/", "-")}`}><span>{item.label}</span><small>Open workspace</small></button>)}</div>}{!results.players.length && !results.clubs.length && !results.pages.length && <p className="command-empty" data-testid="command-empty-state">No connected results found.</p>}</div></section></div>;
}