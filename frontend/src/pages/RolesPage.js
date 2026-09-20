import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import { apiErrorMessage, getPlayerRole, getPlayers } from "@/lib/footballApi";

export default function RolesPage() {
  const players = useQuery({ queryKey: ["roles-players"], queryFn: () => getPlayers({ limit: 80 }), retry: false });

  const roles = useQueries({
    queries: (players.data || []).map((p) => ({
      queryKey: ["role", p.id],
      queryFn: () => getPlayerRole(p.id),
      enabled: !!players.data,
      retry: false,
      staleTime: 300000,
    })),
  });

  const clusters = useMemo(() => {
    const map = new Map();
    roles.forEach((q, idx) => {
      const player = players.data?.[idx];
      const arche = q.data?.primary_archetype;
      if (!player || !arche) return;
      if (!map.has(arche)) map.set(arche, { players: [], confidenceSum: 0, count: 0 });
      const bucket = map.get(arche);
      bucket.players.push({ ...player, confidence: q.data?.confidence });
      bucket.confidenceSum += q.data?.confidence || 0;
      bucket.count += 1;
    });
    return Array.from(map.entries())
      .map(([archetype, bucket]) => ({
        archetype,
        players: bucket.players,
        size: bucket.players.length,
        avgConfidence: bucket.count > 0 ? bucket.confidenceSum / bucket.count : 0,
      }))
      .sort((a, b) => b.size - a.size);
  }, [players.data, roles]);

  const loadedRoles = roles.filter((r) => r.data).length;
  const totalPlayers = players.data?.length || 0;

  return (
    <section className="intelligence-page" data-testid="roles-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">INTELLIGENCE / ROLES</p>
          <h1 data-testid="page-title">Role discovery</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Cluster the connected player universe into archetypes surfaced by the role model. No clusters are fabricated — only what the backend returns.
          </p>
        </div>
        <span className="contract-badge">/api/v1/players/&#123;id&#125;/role</span>
      </div>

      {players.isLoading && <p className="inline-state" data-testid="roles-loading">Loading player universe…</p>}
      {players.isError && (
        <div className="inline-state error-state" data-testid="roles-error">{apiErrorMessage(players.error)}</div>
      )}

      {players.data && totalPlayers > 0 && (
        <>
          <div className="status-strip" data-testid="roles-status">
            <span className={`live-dot ${loadedRoles === totalPlayers ? "" : "warn"}`} />
            <strong>{loadedRoles} / {totalPlayers}</strong>
            <span>role classifications loaded from the backend</span>
          </div>

          <div className="dashboard-grid three" data-testid="roles-clusters">
            {clusters.map((cluster) => (
              <article className="intelligence-card" key={cluster.archetype} data-testid={`roles-cluster-${cluster.archetype.replaceAll(" ", "-")}`}>
                <span className="badge model"><Layers size={11} /> {cluster.archetype}</span>
                <div className="metric-value">{cluster.size}</div>
                <p>players · avg model confidence {(cluster.avgConfidence * 100).toFixed(0)}%</p>
                <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10, display: "grid", gap: 4 }}>
                  {cluster.players.slice(0, 4).map((p) => (
                    <small key={p.id} style={{ color: "var(--muted-strong)", fontSize: 11 }}>
                      · {p.name}
                    </small>
                  ))}
                  {cluster.players.length > 4 && (
                    <small style={{ color: "var(--muted)", fontSize: 10 }}>+ {cluster.players.length - 4} more</small>
                  )}
                </div>
              </article>
            ))}
          </div>

          {clusters.length === 0 && loadedRoles === 0 && (
            <div className="empty-workspace" data-testid="roles-empty">
              <p className="eyebrow">INSUFFICIENT DATA</p>
              <h2>Role classifications not yet available.</h2>
              <p>The connected backend has not returned archetypes for the current player index.</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
