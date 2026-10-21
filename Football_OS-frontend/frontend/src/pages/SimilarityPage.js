import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { Compass, Search, Users } from "lucide-react";
import { apiErrorMessage, getPlayerPage, getSimilarPlayers } from "@/lib/footballApi";
import EvidenceDrawer from "@/components/EvidenceDrawer";
import {
  ConfidenceIndicator, EmptyState, ErrorState, LoadingSkeleton, PageHeader,
  PositionBadge, StatusBadge, UncertaintyNotice, initials,
} from "@/components/ui";

function similarityPct(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const normalised = value <= 1 ? value * 100 : value;
  return `${Math.round(normalised)}%`;
}

export default function SimilarityPage() {
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState(params.get("player") || "");
  const [search, setSearch] = useState("");
  const [evidence, setEvidence] = useState(null);

  const roster = useQuery({
    queryKey: ["similarity-roster"],
    queryFn: () => getPlayerPage({ page: 1, page_size: 100, sort_by: "name" }),
    retry: false,
  });
  const similar = useQuery({
    queryKey: ["similarity-results", selectedId],
    queryFn: () => getSimilarPlayers(selectedId, { limit: 12 }),
    enabled: !!selectedId,
    retry: false,
  });

  const rosterItems = roster.data?.items || [];
  const filteredRoster = useMemo(() => {
    const query = search.trim().toLowerCase();
    return rosterItems
      .filter((player) => !query || player.name.toLowerCase().includes(query))
      .slice(0, 60);
  }, [rosterItems, search]);

  const selectedPlayer = rosterItems.find((player) => player.id === selectedId);
  const results = similar.data?.results || [];

  return (
    <section className="intelligence-page" data-testid="similarity-page">
      <PageHeader
        eyebrow="Intelligence · Similarity"
        title={<span data-testid="page-title">Similarity explorer</span>}
        description={(
          <span data-testid="page-description">
            Pick a player from the connected index — the platform returns multi-dimensional
            similarity across statistical, role, and contextual axes.
          </span>
        )}
        meta={(
          <>
            <span className="contract-badge">/api/v1/players/&#123;id&#125;/similar</span>
            {similar.data?.embedding_version ? (
              <StatusBadge tone="model" testId="similarity-embedding-badge">Embedding · {similar.data.embedding_version}</StatusBadge>
            ) : null}
            <span className="fio-freshness">model output · not a recommendation</span>
          </>
        )}
      />

      <div className="similarity-layout">
        <div className="data-block" data-testid="similarity-picker">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Step 01</p>
              <h3>Choose a player</h3>
            </div>
            {roster.data ? <StatusBadge tone="neutral">{rosterItems.length} loaded</StatusBadge> : null}
          </div>

          <label className="fio-input" style={{ marginBottom: 10 }}>
            <Search size={14} aria-hidden="true" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter the loaded roster"
              aria-label="Filter roster"
              data-testid="similarity-picker-search"
            />
          </label>

          {roster.isLoading ? <LoadingSkeleton rows={6} label="Loading roster" /> : null}
          {roster.isError ? (
            <ErrorState
              compact
              title="Roster unavailable"
              message={apiErrorMessage(roster.error)}
              onRetry={() => roster.refetch()}
            />
          ) : null}

          <div style={{ maxHeight: 430, overflowY: "auto", display: "grid", gap: 3 }} role="listbox" aria-label="Player roster">
            {filteredRoster.map((player) => {
              const selected = player.id === selectedId;
              return (
                <button
                  key={player.id}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => setSelectedId(player.id)}
                  data-testid={`similarity-roster-${player.id}`}
                  className="command-result"
                  style={{
                    border: selected ? "1px solid var(--fio-accent-line)" : "1px solid transparent",
                    background: selected ? "var(--fio-accent-soft)" : "transparent",
                    padding: "8px 9px",
                  }}
                >
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                    <span className="fio-player-avatar fallback" style={{ width: 25, height: 25, fontSize: 8 }} aria-hidden="true">{initials(player.name)}</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{player.name}</span>
                  </span>
                  <small>{player.primary_position || "—"}</small>
                </button>
              );
            })}
            {filteredRoster.length === 0 && roster.data ? (
              <p className="command-empty">No players matched this filter.</p>
            ) : null}
          </div>

          {roster.data && roster.data.total > rosterItems.length ? (
            <p className="command-empty" data-testid="similarity-roster-sample-note" style={{ textAlign: "left", padding: "10px 0 0" }}>
              Showing {rosterItems.length} of {roster.data.total} canonical players. Search the
              full index in Player discovery.
            </p>
          ) : null}
        </div>

        <div className="data-block" data-testid="similarity-results">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Step 02</p>
              <h3>{selectedPlayer ? `Comparable to ${selectedPlayer.name}` : "Comparable players"}</h3>
              {selectedPlayer ? (
                <div className="fio-page-meta" style={{ marginTop: 6 }}>
                  <PositionBadge position={selectedPlayer.primary_position} />
                  <span className="micro">{selectedPlayer.nationality || "Nationality unknown"}</span>
                </div>
              ) : null}
            </div>
            {selectedPlayer ? <Link className="text-button" to={`/players/${selectedPlayer.id}`}>Open profile →</Link> : null}
          </div>

          {!selectedId ? (
            <EmptyState
              icon={Compass}
              compact
              eyebrow="Awaiting selection"
              title="Pick a player on the left."
              description="The similarity engine will return comparable candidates with statistical, role, and contextual axes. It does not rank recruitment suitability."
            />
          ) : null}

          {selectedId && similar.isLoading ? <LoadingSkeleton rows={6} label="Computing similarity" /> : null}

          {selectedId && similar.isError ? (
            <ErrorState
              title="Similarity could not be computed"
              message={apiErrorMessage(similar.error)}
              onRetry={() => similar.refetch()}
            />
          ) : null}

          {selectedId && similar.data ? (
            results.length > 0 ? (
              <div>
                <div className="fio-table-toolbar" style={{ border: "1px solid var(--fio-line)", borderRadius: 8, marginBottom: 10 }}>
                  <span>{results.length} comparable candidates returned</span>
                  <span className="fio-mono" style={{ fontSize: 9 }}>
                    {similar.data.embedding_version ? `embedding ${similar.data.embedding_version}` : "embedding version not reported"}
                  </span>
                </div>
                {results.map((candidate) => (
                  <article className="similar-card" key={candidate.player_id} data-testid={`similarity-result-${candidate.player_id}`}>
                    <div className="similar-card-head">
                      <div>
                        <strong>
                          <Link to={`/players/${candidate.player_id}`} className="player-link">{candidate.player_name}</Link>
                        </strong>
                        <small>{candidate.primary_archetype || candidate.position_group || "Role unavailable"}</small>
                      </div>
                      <div className="similar-score" title="Overall similarity">
                        {similarityPct(candidate.overall_similarity)}
                        <small>OVERALL</small>
                      </div>
                    </div>
                    <div className="similar-axes">
                      <ConfidenceIndicator value={candidate.statistical_similarity} label="Statistical" />
                      <ConfidenceIndicator value={candidate.role_similarity} label="Role" />
                      <ConfidenceIndicator value={candidate.contextual_similarity} label="Contextual" />
                    </div>
                    <div className="similar-card-foot">
                      <span className="micro">
                        {candidate.why_similar ? "Explanation available" : "No explanation returned"}
                      </span>
                      <button
                        type="button"
                        className="evidence-button"
                        onClick={() => setEvidence({
                          overall: candidate.overall_similarity,
                          statistical: candidate.statistical_similarity,
                          role: candidate.role_similarity,
                          contextual: candidate.contextual_similarity,
                          why_similar: candidate.why_similar,
                          why_different: candidate.why_different,
                        })}
                        data-testid={`similarity-why-${candidate.player_id}`}
                      >
                        <Compass size={13} /> Why similar?
                      </button>
                    </div>
                  </article>
                ))}
                <div style={{ marginTop: 12 }}>
                  <UncertaintyNotice title="How to use similarity" tone="info">
                    Similarity is a model estimate over the features the engine actually received.
                    A high score is not a transfer recommendation, and a missing axis is shown as
                    “Not reported” rather than zero.
                  </UncertaintyNotice>
                </div>
              </div>
            ) : (
              <EmptyState
                icon={Users}
                eyebrow="No candidates"
                title={similar.data.message || "The similarity engine returned no candidates."}
                description="This usually means the selected player lacks enough comparable feature coverage. Try another player or inspect role coverage."
                testId="similarity-empty"
              />
            )
          ) : null}
        </div>
      </div>

      <EvidenceDrawer title="Similarity evidence" evidence={evidence} onClose={() => setEvidence(null)} />
    </section>
  );
}
