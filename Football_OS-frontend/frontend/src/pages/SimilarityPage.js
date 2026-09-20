import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { Compass, Database, Search } from "lucide-react";
import { apiErrorMessage, getPlayers, getSimilarPlayers } from "@/lib/footballApi";
import EvidenceDrawer from "@/components/EvidenceDrawer";

export default function SimilarityPage() {
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState(params.get("player") || "");
  const [search, setSearch] = useState("");
  const [evidence, setEvidence] = useState(null);

  const roster = useQuery({ queryKey: ["similarity-roster"], queryFn: () => getPlayers({ limit: 200 }), retry: false });
  const similar = useQuery({
    queryKey: ["similarity-results", selectedId],
    queryFn: () => getSimilarPlayers(selectedId, { limit: 12 }),
    enabled: !!selectedId,
    retry: false,
  });

  const filteredRoster = useMemo(() => {
    if (!roster.data) return [];
    const q = search.trim().toLowerCase();
    return roster.data.filter((p) => !q || p.name.toLowerCase().includes(q)).slice(0, 60);
  }, [roster.data, search]);

  const selectedPlayer = roster.data?.find((p) => p.id === selectedId);

  return (
    <section className="intelligence-page" data-testid="similarity-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">INTELLIGENCE / SIMILARITY</p>
          <h1 data-testid="page-title">Similarity explorer</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Pick a player from the connected index — the platform returns multi-dimensional similarity with statistical, role, and contextual axes.
          </p>
        </div>
        <span className="contract-badge">/api/v1/players/&#123;id&#125;/similar</span>
      </div>

      <div className="split-columns" style={{ marginTop: 24 }}>
        <div className="data-block" data-testid="similarity-picker">
          <div className="section-heading">
            <div><p className="eyebrow">STEP 01</p><h3>Choose a player</h3></div>
          </div>
          <label className="command-input">
            <Search size={15} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter roster"
              aria-label="Filter roster"
              data-testid="similarity-picker-search"
            />
          </label>
          {roster.isLoading && <p className="section-copy">Loading roster…</p>}
          {roster.isError && <p className="section-copy error-state">{apiErrorMessage(roster.error)}</p>}
          <div style={{ maxHeight: 320, overflowY: "auto", display: "grid", gap: 4 }}>
            {filteredRoster.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                data-testid={`similarity-roster-${p.id}`}
                className="command-result"
                style={{
                  border: p.id === selectedId ? "1px solid var(--cyan)" : "1px solid transparent",
                  background: p.id === selectedId ? "var(--cyan-soft)" : "transparent",
                  padding: "10px 12px",
                }}
              >
                <span>{p.name}</span>
                <small>{p.primary_position || "—"}</small>
              </button>
            ))}
            {filteredRoster.length === 0 && roster.data && (
              <p className="command-empty">No players in the connected index.</p>
            )}
          </div>
        </div>

        <div className="data-block" data-testid="similarity-results">
          <div className="section-heading">
            <div>
              <p className="eyebrow">STEP 02</p>
              <h3>{selectedPlayer ? `Comparable to ${selectedPlayer.name}` : "Comparable players"}</h3>
              {similar.data?.embedding_version && (
                <span className="badge model" data-testid="similarity-embedding-badge">EMBEDDING · {similar.data.embedding_version}</span>
              )}
            </div>
          </div>
          {!selectedId && (
            <p className="section-copy">Pick a player on the left to see comparable candidates from the similarity engine.</p>
          )}
          {selectedId && similar.isLoading && <p className="section-copy">Computing similarity…</p>}
          {selectedId && similar.isError && (
            <p className="section-copy error-state">
              <Database size={13} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              {apiErrorMessage(similar.error)}
            </p>
          )}
          {selectedId && similar.data?.results && (
            <div className="similar-list">
              {similar.data.results.map((c) => (
                <div className="similar-row" key={c.player_id} data-testid={`similarity-result-${c.player_id}`}>
                  <div>
                    <Link to={`/players/${c.player_id}`} className="player-link">{c.player_name}</Link>
                    <small>{c.primary_archetype || c.position_group || "Role unavailable"}</small>
                  </div>
                  <b>{Math.round((c.overall_similarity ?? 0) * 100)}%</b>
                  <button
                    className="evidence-button"
                    onClick={() => setEvidence({
                      overall: c.overall_similarity,
                      statistical: c.statistical_similarity,
                      role: c.role_similarity,
                      contextual: c.contextual_similarity,
                      why_similar: c.why_similar,
                      why_different: c.why_different,
                    })}
                    data-testid={`similarity-why-${c.player_id}`}
                  >
                    <Compass size={13} /> Why?
                  </button>
                </div>
              ))}
              {similar.data.results.length === 0 && (
                <p className="section-copy">The similarity engine returned no candidates.</p>
              )}
            </div>
          )}
        </div>
      </div>

      <EvidenceDrawer title="Similarity evidence" evidence={evidence} onClose={() => setEvidence(null)} />
    </section>
  );
}
