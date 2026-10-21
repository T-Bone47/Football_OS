import { useDeferredValue, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, Search, SlidersHorizontal, Users, X } from "lucide-react";
import {
  apiErrorMessage,
  getPlayerFacets,
  getPlayerPage,
} from "@/lib/footballApi";
import { describePlayerPage } from "@/lib/playerPagination";
import {
  DataTable, ErrorState, LoadingSkeleton, PageHeader, Pagination,
  PositionBadge, SafeLink, StatusBadge, initials,
} from "@/components/ui";

const POSITIONS = [
  { value: "", label: "All positions" },
  { value: "GK", label: "Goalkeepers" },
  { value: "D", label: "Defenders" },
  { value: "M", label: "Midfielders" },
  { value: "F", label: "Forwards" },
];

const PAGE_SIZES = [10, 25, 50, 100];

function PlayerCell({ player }) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <div className="fio-player-cell">
      {player.photo_url && !imageFailed ? (
        <img
          className="fio-player-avatar"
          src={player.photo_url}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <span className="fio-player-avatar fallback" aria-hidden="true">{initials(player.name)}</span>
      )}
      <span className="fio-player-copy">
        <SafeLink to={`/players/${player.id}`} className="player-link" data-testid={`player-link-${player.id}`}>
          {player.name}
        </SafeLink>
        <span>{player.club?.name || "Club not recorded"}</span>
      </span>
    </div>
  );
}

export default function PlayerSearchPage() {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [position, setPosition] = useState("");
  const [nationality, setNationality] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    setPage(1);
  }, [deferredSearch, position, nationality, pageSize]);

  const players = useQuery({
    queryKey: [
      "player-page",
      deferredSearch,
      position,
      nationality,
      page,
      pageSize,
    ],
    queryFn: () =>
      getPlayerPage({
        q: deferredSearch || undefined,
        position: position || undefined,
        nationality: nationality || undefined,
        page,
        page_size: pageSize,
      }),
    staleTime: 30000,
    retry: false,
  });

  const facets = useQuery({
    queryKey: ["player-facets"],
    queryFn: getPlayerFacets,
    staleTime: 300000,
    retry: false,
  });

  const items = players.data?.items ?? [];
  const {
    page: dataPage,
    total,
    totalPages,
    start,
    end,
    hasNext,
  } = describePlayerPage(players.data, page, pageSize);
  const nationalities = facets.data?.nationalities ?? [];

  const goToPage = (next) => {
    const bounded = Math.min(Math.max(1, next), Math.max(1, totalPages));
    setPage(bounded);
  };

  const hasFilters = Boolean(search || position || nationality);
  const clearFilters = () => {
    setSearch("");
    setPosition("");
    setNationality("");
  };

  const countLabel = players.isPending
    ? "Loading…"
    : players.isError
      ? "Unavailable"
      : `${total === 0 ? "0" : `${start}–${end}`} / ${total}`;

  const columns = [
    {
      key: "position",
      header: "Pos",
      width: 58,
      render: (player) => (
        <span data-testid={`player-position-${player.id}`}>
          <PositionBadge position={player.primary_position} />
        </span>
      ),
    },
    {
      key: "player",
      header: "Player",
      render: (player) => <PlayerCell player={player} />,
    },
    {
      key: "nationality",
      header: "Nationality",
      render: (player) => <span data-testid={`player-nationality-${player.id}`}>{player.nationality || "—"}</span>,
    },
    {
      key: "foot",
      header: "Foot",
      render: (player) => <span data-testid={`player-foot-${player.id}`}>{player.preferred_foot || "—"}</span>,
    },
    {
      key: "dob",
      header: "Date of birth",
      render: (player) => <span data-testid={`player-dob-${player.id}`}>{player.date_of_birth || "—"}</span>,
    },
    {
      key: "seasons",
      header: "Seasons",
      align: "right",
      width: 82,
      render: (player) => (
        <span data-testid={`player-seasons-${player.id}`}>
          {Array.isArray(player.season_stats) ? player.season_stats.length : "—"}
        </span>
      ),
    },
    {
      key: "open",
      header: "",
      width: 112,
      render: (player) => (
        <SafeLink to={`/players/${player.id}`} className="row-action" data-testid={`player-open-${player.id}`}>
          Open profile →
        </SafeLink>
      ),
    },
  ];

  return (
    <section className="intelligence-page" data-testid="player-search-page">
      <PageHeader
        eyebrow={<span data-testid="page-eyebrow">Intelligence · Players</span>}
        title={<span data-testid="page-title">Player discovery</span>}
        description={(
          <span data-testid="page-description">
            Search the full canonical player universe. The backend applies filters before
            pagination and returns the true matching total; missing values render as “—”,
            never fabricated.
          </span>
        )}
        meta={(
          <>
            <StatusBadge tone="neutral" testId="player-count-badge">{countLabel}</StatusBadge>
            <span className="contract-badge" data-testid="api-contract-badge">GET /players/search</span>
            <span className="fio-freshness">server-side pagination · stable name order</span>
          </>
        )}
        actions={(
          <>
            <SafeLink className="outline-button" to="/players/compare">Compare players</SafeLink>
            <SafeLink className="primary-button" to="/players/similarity">Find similar</SafeLink>
          </>
        )}
      />

      <div className="fio-toolbar" data-testid="player-filter-bar">
        <label className="fio-input" style={{ flex: "1 1 260px" }}>
          <Search size={14} aria-hidden="true" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search player name across the full index"
            aria-label="Search player name"
            data-testid="player-search-input"
          />
          {search ? (
            <button type="button" className="fio-icon-action" style={{ width: 22, height: 22, border: 0 }} onClick={() => setSearch("")} aria-label="Clear search">
              <X size={12} />
            </button>
          ) : null}
        </label>
        <label className="fio-input" style={{ flex: "0 1 190px" }}>
          <SlidersHorizontal size={14} aria-hidden="true" />
          <select
            value={position}
            onChange={(event) => setPosition(event.target.value)}
            aria-label="Filter by position"
            data-testid="player-position-select"
          >
            {POSITIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label className="fio-input" style={{ flex: "0 1 220px" }}>
          <Users size={14} aria-hidden="true" />
          <select
            value={nationality}
            onChange={(event) => setNationality(event.target.value)}
            aria-label="Filter by nationality"
            data-testid="player-nationality-filter"
          >
            <option value="">All nationalities</option>
            {nationalities.map((entry) => (
              <option key={entry} value={entry}>{entry}</option>
            ))}
          </select>
        </label>
        {hasFilters ? (
          <button type="button" className="ghost-button" onClick={clearFilters}>
            <X size={13} /> Clear
          </button>
        ) : null}
        <span className="fio-status-pill" style={{ marginLeft: "auto" }}>
          <Database size={11} aria-hidden="true" /> Filters before pagination
        </span>
      </div>

      {hasFilters ? (
        <div className="fio-page-meta" style={{ marginTop: -4, marginBottom: 12 }} aria-label="Active filters">
          <span className="micro">Active filters</span>
          {search ? <span className="fio-filter-chip">Name: {search}<button type="button" onClick={() => setSearch("")} aria-label="Remove name filter"><X size={10} /></button></span> : null}
          {position ? <span className="fio-filter-chip">Position: {POSITIONS.find((entry) => entry.value === position)?.label || position}<button type="button" onClick={() => setPosition("")} aria-label="Remove position filter"><X size={10} /></button></span> : null}
          {nationality ? <span className="fio-filter-chip">Nationality: {nationality}<button type="button" onClick={() => setNationality("")} aria-label="Remove nationality filter"><X size={10} /></button></span> : null}
        </div>
      ) : null}

      {players.isPending ? (
        <div className="fio-table-wrap" style={{ padding: 18 }} data-testid="players-loading-state">
          <p className="fio-visually-hidden">Loading connected player data…</p>
          <LoadingSkeleton rows={8} label="Loading connected player data" />
        </div>
      ) : null}

      {players.isError ? (
        <div data-testid="players-error-state">
          <ErrorState
            title="Player index could not be loaded"
            message={apiErrorMessage(players.error)}
            onRetry={() => players.refetch()}
            testId="players-error-panel"
          />
        </div>
      ) : null}

      {!players.isPending && !players.isError ? (
        <DataTable
          columns={columns}
          rows={items}
          rowKey={(player) => player.id}
          rowTestId={(player) => `player-row-${player.id}`}
          testId="player-table"
          emptyTestId="players-empty-state"
          empty={(
            <span>
              No players matched the current filters.{" "}
              {hasFilters ? <button type="button" className="text-button" onClick={clearFilters}>Clear filters</button> : null}
            </span>
          )}
          caption={`${items.length} player${items.length === 1 ? "" : "s"} on this page. Filters run on the server before pagination.`}
        />
      ) : null}

      {!players.isPending && !players.isError && total > 0 ? (
        <Pagination
          page={dataPage}
          totalPages={totalPages}
          onPage={goToPage}
          pageSize={pageSize}
          onPageSize={setPageSize}
          pageSizes={PAGE_SIZES}
          total={total}
          start={start}
          end={end}
          hasNext={hasNext}
          isFetching={players.isFetching && !players.isPending}
          testIdPrefix="players"
          label="Player result pages"
        />
      ) : null}
    </section>
  );
}
