import { useDeferredValue, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { GitCompare, Plus, Search, X } from "lucide-react";
import { apiErrorMessage, getPlayer, getPlayerPage } from "@/lib/footballApi";
import {
  EmptyState, ErrorState, LoadingSkeleton, PageHeader, PositionBadge,
  StatusBadge, UncertaintyNotice, formatUnknown, initials,
} from "@/components/ui";

const MAX_SLOTS = 5;
const METRIC_ROWS = [
  { key: "minutes", label: "Minutes" },
  { key: "goals", label: "Goals" },
  { key: "assists", label: "Assists" },
  { key: "rating", label: "Rating" },
  { key: "appearances", label: "Appearances" },
];

function Slot({ player, onClear, onOpen, slotIndex, loading }) {
  if (loading) {
    return (
      <div className="compare-slot filled" data-testid={`compare-slot-${slotIndex}-loading`}>
        <LoadingSkeleton rows={2} label="Loading player" />
      </div>
    );
  }
  if (!player) {
    return (
      <button type="button" className="compare-slot" onClick={onOpen} data-testid={`compare-slot-${slotIndex}-empty`}>
        <span className="fio-eyebrow" style={{ marginBottom: 2 }}>
          <Plus size={11} style={{ verticalAlign: "-1px", marginRight: 4 }} /> Add player
        </span>
        <small>Pick from the connected index</small>
      </button>
    );
  }
  const latest = player.season_stats?.[0];
  return (
    <div className="compare-slot filled" data-testid={`compare-slot-${slotIndex}-filled`}>
      <button type="button" className="icon-button remove" onClick={onClear} aria-label={`Remove ${player.name}`} data-testid={`compare-slot-${slotIndex}-remove`}>
        <X size={13} />
      </button>
      <div className="fio-player-cell">
        <span className="fio-player-avatar fallback" aria-hidden="true">{initials(player.name)}</span>
        <span className="fio-player-copy">
          <strong>{player.name}</strong>
          <span>{player.primary_position || "Position unknown"}</span>
        </span>
      </div>
      <div className="fio-page-meta" style={{ marginTop: 4 }}>
        <PositionBadge position={player.primary_position} />
        <span className="micro">{player.nationality || "Nationality unknown"}</span>
      </div>
      <small>
        {latest
          ? `${latest.minutes ?? "—"}′ · ${latest.goals ?? "—"}G · ${latest.assists ?? "—"}A`
          : "No season stats reported"}
      </small>
    </div>
  );
}

export default function PlayerComparePage() {
  const [params] = useSearchParams();
  const initialIds = (params.get("ids") || "").split(",").filter(Boolean).slice(0, MAX_SLOTS);
  const [slots, setSlots] = useState(() => {
    const arr = new Array(MAX_SLOTS).fill(null);
    initialIds.forEach((id, index) => { arr[index] = id; });
    return arr;
  });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSlot, setPickerSlot] = useState(null);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);

  const roster = useQuery({
    queryKey: ["compare-roster", deferredSearch],
    queryFn: () =>
      getPlayerPage({
        q: deferredSearch || undefined,
        page: 1,
        page_size: 40,
        sort_by: "name",
      }),
    enabled: pickerOpen,
    retry: false,
    placeholderData: (previous) => previous,
  });

  const results = useQueries({
    queries: slots.map((id) => ({
      queryKey: ["compare-player", id],
      queryFn: () => getPlayer(id),
      enabled: !!id,
      retry: false,
    })),
  });

  const filteredRoster = useMemo(() => roster.data?.items ?? [], [roster.data]);
  const filled = results.filter((query) => query.data).map((query) => query.data);

  const openPicker = (slotIndex) => { setPickerSlot(slotIndex); setPickerOpen(true); };
  const closePicker = () => { setPickerOpen(false); setPickerSlot(null); setSearch(""); };
  const pickPlayer = (playerId) => {
    setSlots((previous) => {
      const next = [...previous];
      if (pickerSlot != null) next[pickerSlot] = playerId;
      else {
        const index = next.findIndex((slot) => !slot);
        if (index >= 0) next[index] = playerId;
      }
      return next;
    });
    closePicker();
  };
  const clearSlot = (slotIndex) => {
    setSlots((previous) => { const next = [...previous]; next[slotIndex] = null; return next; });
  };
  const clearAll = () => setSlots(new Array(MAX_SLOTS).fill(null));

  const identityRows = [
    { label: "Position", render: (player) => <PositionBadge position={player.primary_position} /> },
    { label: "Nationality", render: (player) => player.nationality || "—" },
    { label: "Preferred foot", render: (player) => player.preferred_foot || "—" },
    { label: "Date of birth", render: (player) => player.date_of_birth || "—" },
    { label: "Height", render: (player) => formatUnknown(player.height_cm, " cm") },
    { label: "Weight", render: (player) => formatUnknown(player.weight_kg, " kg") },
  ];

  const coverageFor = (player) => {
    const stats = player.season_stats?.[0];
    if (!stats) return 0;
    return METRIC_ROWS.filter((row) => stats[row.key] != null).length;
  };

  return (
    <section className="intelligence-page" data-testid="player-compare-page">
      <PageHeader
        eyebrow="Intelligence · Comparison"
        title={<span data-testid="page-title">Player comparison</span>}
        description={(
          <span data-testid="page-description">
            Compare 2–5 players side by side. Facts only — the workspace does not declare a
            winner or synthesize a composite score.
          </span>
        )}
        meta={(
          <>
            <StatusBadge tone="neutral">{filled.length} of {MAX_SLOTS} slots filled</StatusBadge>
            <span className="contract-badge">/api/v1/players/&#123;id&#125;</span>
            <span className="fio-freshness">missing values remain “—”</span>
          </>
        )}
        actions={filled.length > 0 ? (
          <>
            <button type="button" className="ghost-button" onClick={clearAll}>Clear all</button>
            <button type="button" className="primary-button" onClick={() => openPicker(null)}>
              <Plus size={14} /> Add player
            </button>
          </>
        ) : null}
      />

      <div className="compare-picker" data-testid="compare-picker">
        {slots.map((id, slotIndex) => (
          <Slot
            key={slotIndex}
            slotIndex={slotIndex}
            player={results[slotIndex]?.data}
            loading={Boolean(id) && results[slotIndex]?.isPending}
            onClear={() => clearSlot(slotIndex)}
            onOpen={() => openPicker(slotIndex)}
          />
        ))}
      </div>

      {filled.length >= 2 ? (
        <div className="stack-14" data-testid="compare-results">
          <div className="fio-table-wrap">
            <table className="fio-table compare-table">
              <caption>
                Direct field comparison. {filled.length} players · {METRIC_ROWS.length} output metrics.
                Values are read from each player&apos;s latest season record.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  {filled.map((player) => (
                    <th key={player.id} scope="col">
                      <span style={{ display: "block", color: "var(--fio-text)" }}>{player.name.split(" ").slice(-1)[0]}</span>
                      <span style={{ display: "block", marginTop: 2 }}>{player.primary_position || "Position unknown"}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {identityRows.map((row) => (
                  <tr key={row.label}>
                    <th scope="row" style={{ position: "static", background: "transparent", textTransform: "none", letterSpacing: 0, fontSize: 11.5, color: "var(--fio-text-3)", fontFamily: "var(--fio-font)" }}>
                      {row.label}
                    </th>
                    {filled.map((player) => <td key={player.id}>{row.render(player)}</td>)}
                  </tr>
                ))}
                <tr>
                  <th scope="row" colSpan={filled.length + 1} style={{ position: "static", background: "rgba(255,255,255,.015)", color: "var(--fio-text-4)", letterSpacing: ".12em" }}>
                    Latest season output
                  </th>
                </tr>
                {METRIC_ROWS.map((row) => (
                  <tr key={row.key}>
                    <th scope="row" style={{ position: "static", background: "transparent", textTransform: "none", letterSpacing: 0, fontSize: 11.5, color: "var(--fio-text-3)", fontFamily: "var(--fio-font)" }}>
                      {row.label}
                    </th>
                    {filled.map((player) => (
                      <td key={player.id}>{formatUnknown(player.season_stats?.[0]?.[row.key])}</td>
                    ))}
                  </tr>
                ))}
                <tr>
                  <th scope="row" style={{ position: "static", background: "transparent", textTransform: "none", letterSpacing: 0, fontSize: 11.5, color: "var(--fio-text-3)", fontFamily: "var(--fio-font)" }}>
                    Metric coverage
                  </th>
                  {filled.map((player) => (
                    <td key={player.id}>
                      <StatusBadge tone={coverageFor(player) === METRIC_ROWS.length ? "success" : coverageFor(player) > 0 ? "warn" : "danger"}>
                        {coverageFor(player)} of {METRIC_ROWS.length} reported
                      </StatusBadge>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <UncertaintyNotice title="What this comparison does not tell you" tone="info">
            A player with more minutes or goals is not automatically a better recruitment target.
            Role, tactical context, age curve, contract and sample size all sit outside this table.
            Open a profile or the similarity explorer before making a decision.
          </UncertaintyNotice>
        </div>
      ) : (
        <EmptyState
          icon={GitCompare}
          eyebrow="Ready to compare"
          title="Pick at least two players from the connected index."
          description="Only fields available in the /api/v1/players contract are shown. Missing values render as “—”, never fabricated."
          action={<button type="button" className="primary-button" onClick={() => openPicker(null)}><Plus size={14} /> Add the first player</button>}
          testId="compare-empty-state"
        />
      )}

      {results.some((query) => query.isError) ? (
        <div style={{ marginTop: 14 }} data-testid="compare-error">
          <ErrorState
            compact
            title="Some players could not be loaded"
            message={results.find((query) => query.isError)?.error ? apiErrorMessage(results.find((query) => query.isError).error) : undefined}
          />
        </div>
      ) : null}

      {pickerOpen ? (
        <div className="command-backdrop" role="presentation" onClick={closePicker} data-testid="compare-picker-modal">
          <section className="command-palette" role="dialog" aria-modal="true" aria-label="Add player to comparison" onClick={(event) => event.stopPropagation()}>
            <div className="command-search">
              <Search size={16} aria-hidden="true" />
              <input
                autoFocus
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search player to add"
                aria-label="Search player to add"
                data-testid="compare-picker-search"
              />
              <button type="button" className="icon-button" onClick={closePicker} aria-label="Close picker">
                <X size={15} />
              </button>
            </div>
            <div className="command-results">
              {roster.isLoading ? <LoadingSkeleton rows={5} label="Loading roster" /> : null}
              {roster.isError ? <p className="command-empty error-state">{apiErrorMessage(roster.error)}</p> : null}
              {roster.data ? (
                <p className="command-empty" data-testid="compare-picker-total">
                  Showing {filteredRoster.length} of {roster.data.total} matching players
                </p>
              ) : null}
              {filteredRoster.map((player) => (
                <button
                  key={player.id}
                  type="button"
                  className="command-result"
                  onClick={() => pickPlayer(player.id)}
                  data-testid={`compare-picker-option-${player.id}`}
                >
                  <span>{player.name}</span>
                  <small>{player.primary_position || "—"} · {player.nationality || "—"}</small>
                </button>
              ))}
              {filteredRoster.length === 0 && roster.data ? (
                <p className="command-empty">No matches in the connected index.</p>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
