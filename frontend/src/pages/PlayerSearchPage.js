import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Database, Search, SlidersHorizontal, Users } from "lucide-react";
import { apiErrorMessage, getPlayers } from "@/lib/footballApi";

const POSITIONS = [
  { value: "", label: "All positions" },
  { value: "GK", label: "Goalkeepers" },
  { value: "D", label: "Defenders" },
  { value: "M", label: "Midfielders" },
  { value: "F", label: "Forwards" },
];

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

  return (
    <section className="intelligence-page" data-testid="player-search-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow" data-testid="page-eyebrow">INTELLIGENCE / PLAYERS</p>
          <h1 data-testid="page-title">Player discovery</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Search the connected player universe by identity, position, and available evidence — no analytical values are shown until the source returns them.
          </p>
        </div>
        <span className="contract-badge" data-testid="api-contract-badge">/api/v1/players</span>
      </div>

      <div className="workspace-toolbar player-toolbar" data-testid="player-filter-bar">
        <label className="command-input">
          <Search size={15} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search player name"
            aria-label="Search player name"
            data-testid="player-search-input"
          />
        </label>
        <label className="select-control">
          <SlidersHorizontal size={15} />
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
          <Users size={15} />
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
          <Database size={17} />
          <span>{apiErrorMessage(players.error)}</span>
        </div>
      )}
      {!players.isLoading && !players.isError && (
        <div className="player-table-wrap" data-testid="player-table">
          <table>
            <thead>
              <tr>
                <th>PLAYER</th>
                <th>POSITION</th>
                <th>NATIONALITY</th>
                <th>FOOT</th>
                <th>DOB</th>
                <th>SEASONS</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((player) => (
                <tr key={player.id} data-testid={`player-row-${player.id}`}>
                  <td>
                    <Link to={`/players/${player.id}`} className="player-link" data-testid={`player-link-${player.id}`}>
                      {player.name}
                    </Link>
                  </td>
                  <td data-testid={`player-position-${player.id}`}>{player.primary_position || "—"}</td>
                  <td data-testid={`player-nationality-${player.id}`}>{player.nationality || "—"}</td>
                  <td data-testid={`player-foot-${player.id}`}>{player.preferred_foot || "—"}</td>
                  <td data-testid={`player-dob-${player.id}`}>{player.date_of_birth || "—"}</td>
                  <td data-testid={`player-seasons-${player.id}`}>{player.season_stats?.length || 0}</td>
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
