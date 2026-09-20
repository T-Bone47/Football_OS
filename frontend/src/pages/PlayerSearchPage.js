import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Database, Search, SlidersHorizontal, Users } from "lucide-react";
import { apiErrorMessage, getPlayers } from "@/lib/footballApi";

const POSITIONS = [
  { value: "", label: "All positions" },
  { value: "GK", label: "GK" },
  { value: "D", label: "Defenders" },
  { value: "M", label: "Midfielders" },
  { value: "F", label: "Forwards" },
];

function posClass(position) {
  const p = (position || "").toUpperCase();
  if (p.startsWith("GK")) return "gk";
  if (p.startsWith("D") || p.includes("B") || p.includes("CB") || p.includes("LB") || p.includes("RB")) return "d";
  if (p.startsWith("M") || p.includes("CM") || p.includes("DM") || p.includes("AM")) return "m";
  if (p.startsWith("F") || p.includes("ST") || p.includes("W")) return "f";
  return "";
}

export default function PlayerSearchPage() {
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState("");
  const [nationality, setNationality] = useState("");
  const players = useQuery({
    queryKey: ["players", position],
    queryFn: () => getPlayers(position ? { position } : {}),
    staleTime: 60000,
    retry: false,
  });

  const nationalities = useMemo(() => {
    const set = new Set();
    (players.data || []).forEach((p) => p.nationality && set.add(p.nationality));
    return Array.from(set).sort();
  }, [players.data]);

  const filtered = useMemo(() => (players.data || []).filter((player) => {
    if (search && !player.name?.toLowerCase().includes(search.toLowerCase())) return false;
    if (nationality && player.nationality !== nationality) return false;
    return true;
  }), [players.data, search, nationality]);

  const count = filtered.length;
  const total = players.data?.length ?? 0;

  return (
    <section className="intelligence-page" data-testid="player-search-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow" data-testid="page-eyebrow">INTELLIGENCE · PLAYERS</p>
          <h1 data-testid="page-title">Player discovery</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Scan the connected player universe. Only fields returned by <code style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--cyan)" }}>/api/v1/players</code> are shown — missing values render as “—”, never fabricated.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="badge neutral" data-testid="player-count-badge">
            {count.toString().padStart(2, "0")} / {total.toString().padStart(2, "0")}
          </span>
          <span className="contract-badge" data-testid="api-contract-badge">GET /players</span>
        </div>
      </div>

      <div className="workspace-toolbar player-toolbar" data-testid="player-filter-bar">
        <label className="command-input">
          <Search size={13} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search player name"
            aria-label="Search player name"
            data-testid="player-search-input"
          />
        </label>
        <label className="select-control">
          <SlidersHorizontal size={13} />
          <select
            value={position}
            onChange={(event) => setPosition(event.target.value)}
            aria-label="Filter by position"
            data-testid="player-position-filter"
          >
            {POSITIONS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </label>
        <label className="select-control">
          <Users size={13} />
          <select
            value={nationality}
            onChange={(event) => setNationality(event.target.value)}
            aria-label="Filter by nationality"
            data-testid="player-nationality-filter"
          >
            <option value="">All nationalities</option>
            {nationalities.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>

      {players.isLoading && <p className="inline-state" data-testid="players-loading-state">Loading connected player data…</p>}
      {players.isError && (
        <div className="inline-state error-state" data-testid="players-error-state">
          <Database size={15} />
          <span>{apiErrorMessage(players.error)}</span>
        </div>
      )}
      {!players.isLoading && !players.isError && (
        <div className="player-table-wrap" data-testid="player-table">
          <table>
            <thead>
              <tr>
                <th style={{ width: 40 }}>POS</th>
                <th>PLAYER</th>
                <th>NATIONALITY</th>
                <th>FOOT</th>
                <th>DOB</th>
                <th className="num">SEASONS</th>
                <th style={{ width: 90 }} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((player) => (
                <tr key={player.id} data-testid={`player-row-${player.id}`}>
                  <td data-testid={`player-position-${player.id}`}>
                    {player.primary_position ? (
                      <span className={`pos-pill ${posClass(player.primary_position)}`}>{player.primary_position}</span>
                    ) : <span className="pos-pill">—</span>}
                  </td>
                  <td>
                    <Link to={`/players/${player.id}`} className="player-link" data-testid={`player-link-${player.id}`}>
                      {player.name}
                    </Link>
                  </td>
                  <td data-testid={`player-nationality-${player.id}`}>{player.nationality || "—"}</td>
                  <td data-testid={`player-foot-${player.id}`}>{player.preferred_foot || "—"}</td>
                  <td data-testid={`player-dob-${player.id}`}>{player.date_of_birth || "—"}</td>
                  <td className="num" data-testid={`player-seasons-${player.id}`}>{player.season_stats?.length || 0}</td>
                  <td>
                    <Link to={`/players/${player.id}`} className="row-action" data-testid={`player-open-${player.id}`}>
                      Open profile →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="table-empty" data-testid="players-empty-state">
              No players matched the connected API response.
            </div>
          )}
        </div>
      )}
    </section>
  );
}
