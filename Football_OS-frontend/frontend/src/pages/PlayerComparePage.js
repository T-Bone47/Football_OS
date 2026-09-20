import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Plus, Search, X } from "lucide-react";
import { apiErrorMessage, getPlayer, getPlayers } from "@/lib/footballApi";

const MAX_SLOTS = 5;
const METRIC_ROWS = [
  { key: "minutes", label: "Minutes" },
  { key: "goals", label: "Goals" },
  { key: "assists", label: "Assists" },
  { key: "rating", label: "Rating" },
  { key: "appearances", label: "Appearances" },
];

function Slot({ player, onClear, onOpen, slotIndex }) {
  if (!player) {
    return (
      <button className="compare-slot" onClick={onOpen} data-testid={`compare-slot-${slotIndex}-empty`}>
        <span className="eyebrow"><Plus size={11} style={{ verticalAlign: "-2px", marginRight: 4 }} /> Add player</span>
        <small>Pick from the connected index</small>
      </button>
    );
  }
  const latest = player.season_stats?.[0];
  return (
    <div className="compare-slot filled" data-testid={`compare-slot-${slotIndex}-filled`}>
      <button className="icon-button remove" onClick={onClear} aria-label="Remove player" data-testid={`compare-slot-${slotIndex}-remove`}>
        <X size={13} />
      </button>
      <strong>{player.name}</strong>
      <small>{player.primary_position || "—"} · {player.nationality || "—"}</small>
      <small>{latest ? `${latest.minutes ?? 0}′ · ${latest.goals ?? 0}G · ${latest.assists ?? 0}A` : "No season stats"}</small>
    </div>
  );
}

export default function PlayerComparePage() {
  const [params] = useSearchParams();
  const initialIds = (params.get("ids") || "").split(",").filter(Boolean).slice(0, MAX_SLOTS);
  const [slots, setSlots] = useState(() => {
    const arr = new Array(MAX_SLOTS).fill(null);
    initialIds.forEach((id, i) => { arr[i] = id; });
    return arr;
  });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSlot, setPickerSlot] = useState(null);
  const [search, setSearch] = useState("");

  const roster = useQuery({ queryKey: ["compare-roster"], queryFn: () => getPlayers({ limit: 200 }), retry: false });

  const results = useQueries({
    queries: slots.map((id) => ({
      queryKey: ["compare-player", id],
      queryFn: () => getPlayer(id),
      enabled: !!id,
      retry: false,
    })),
  });

  const filteredRoster = useMemo(() => {
    if (!roster.data) return [];
    const q = search.trim().toLowerCase();
    return roster.data.filter((p) => !q || p.name.toLowerCase().includes(q)).slice(0, 40);
  }, [roster.data, search]);

  const openPicker = (slotIndex) => { setPickerSlot(slotIndex); setPickerOpen(true); };
  const closePicker = () => { setPickerOpen(false); setPickerSlot(null); setSearch(""); };
  const pickPlayer = (playerId) => {
    setSlots((prev) => {
      const next = [...prev];
      if (pickerSlot != null) next[pickerSlot] = playerId;
      else {
        const idx = next.findIndex((s) => !s);
        if (idx >= 0) next[idx] = playerId;
      }
      return next;
    });
    closePicker();
  };
  const clearSlot = (slotIndex) => {
    setSlots((prev) => { const next = [...prev]; next[slotIndex] = null; return next; });
  };

  const filled = results.filter((q) => q.data).map((q) => q.data);

  return (
    <section className="intelligence-page" data-testid="player-compare-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">INTELLIGENCE / COMPARISON</p>
          <h1 data-testid="page-title">Player comparison</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Compare 2–5 players side by side. Facts only — the workspace does not declare a winner.
          </p>
        </div>
        <span className="contract-badge">/api/v1/players/&#123;id&#125;</span>
      </div>

      <div className="compare-picker" data-testid="compare-picker">
        {slots.map((_, slotIndex) => (
          <Slot
            key={slotIndex}
            slotIndex={slotIndex}
            player={results[slotIndex]?.data}
            onClear={() => clearSlot(slotIndex)}
            onOpen={() => openPicker(slotIndex)}
          />
        ))}
      </div>

      {filled.length >= 2 ? (
        <div className="player-table-wrap" data-testid="compare-results">
          <table className="compare-table">
            <thead>
              <tr>
                <th>METRIC</th>
                {filled.map((p) => <th key={p.id}>{p.name.split(" ").slice(-1)[0]}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Position</td>
                {filled.map((p) => <td key={p.id}>{p.primary_position || "—"}</td>)}
              </tr>
              <tr>
                <td>Nationality</td>
                {filled.map((p) => <td key={p.id}>{p.nationality || "—"}</td>)}
              </tr>
              <tr>
                <td>Preferred foot</td>
                {filled.map((p) => <td key={p.id}>{p.preferred_foot || "—"}</td>)}
              </tr>
              {METRIC_ROWS.map((row) => (
                <tr key={row.key}>
                  <td>{row.label}</td>
                  {filled.map((p) => <td key={p.id}>{p.season_stats?.[0]?.[row.key] ?? "—"}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-workspace" data-testid="compare-empty-state">
          <p className="eyebrow">READY TO COMPARE</p>
          <h2>Pick at least two players from the connected index.</h2>
          <p>Only fields available in the /api/v1/players contract are shown. Missing values render as “—”, never fabricated.</p>
        </div>
      )}

      {results.some((q) => q.isError) && (
        <div className="inline-state error-state" data-testid="compare-error">
          Some players could not be loaded from the connected backend.
        </div>
      )}

      {pickerOpen && (
        <div className="command-backdrop" role="presentation" onClick={closePicker} data-testid="compare-picker-modal">
          <section className="command-palette" onClick={(e) => e.stopPropagation()}>
            <div className="command-search">
              <Search size={16} />
              <input
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search player to add"
                data-testid="compare-picker-search"
              />
              <button className="icon-button" onClick={closePicker} aria-label="Close picker">
                <X size={15} />
              </button>
            </div>
            <div className="command-results">
              {roster.isLoading && <p className="command-empty">Loading roster…</p>}
              {roster.isError && <p className="command-empty error-state">{apiErrorMessage(roster.error)}</p>}
              {filteredRoster.map((player) => (
                <button
                  key={player.id}
                  className="command-result"
                  onClick={() => pickPlayer(player.id)}
                  data-testid={`compare-picker-option-${player.id}`}
                >
                  <span>{player.name}</span>
                  <small>{player.primary_position || "—"}</small>
                </button>
              ))}
              {filteredRoster.length === 0 && roster.data && (
                <p className="command-empty">No matches in the connected index.</p>
              )}
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
