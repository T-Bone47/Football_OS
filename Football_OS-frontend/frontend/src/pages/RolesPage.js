import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers, Users } from "lucide-react";
import { apiErrorMessage, getPlayerRolesBatch } from "@/lib/footballApi";
import {
  ConfidenceIndicator, EmptyState, ErrorState, LoadingSkeleton, MetricCard,
  PageHeader, Pagination, StatusBadge, UncertaintyNotice, formatUnknown,
} from "@/components/ui";

const SAMPLE_SIZE = 80;

export default function RolesPage() {
  const [page, setPage] = useState(1);
  const roles = useQuery({
    queryKey: ["roles-batch", page],
    queryFn: () => getPlayerRolesBatch({ page, page_size: SAMPLE_SIZE }),
    retry: false,
  });

  const data = roles.data;
  const items = data?.items || [];

  const clusters = useMemo(() => {
    const map = new Map();
    items.forEach((player) => {
      if (!player.primary_archetype) return;
      if (!map.has(player.primary_archetype)) {
        map.set(player.primary_archetype, { players: [], confidenceSum: 0, count: 0 });
      }
      const bucket = map.get(player.primary_archetype);
      bucket.players.push(player);
      if (typeof player.archetype_confidence === "number") {
        bucket.confidenceSum += player.archetype_confidence;
        bucket.count += 1;
      }
    });
    return Array.from(map.entries())
      .map(([archetype, bucket]) => ({
        archetype,
        players: bucket.players,
        size: bucket.players.length,
        avgConfidence: bucket.count > 0 ? bucket.confidenceSum / bucket.count : null,
      }))
      .sort((a, b) => b.size - a.size);
  }, [items]);

  const sampled = data?.returned ?? 0;
  const classified = data?.classified ?? 0;
  const insufficient = data?.insufficient ?? 0;
  const notClassified = data?.not_classified ?? 0;
  const coverage = data?.coverage;
  const totalPlayers = coverage?.total_players ?? null;
  const qualifiedProfiles = coverage?.qualified_profiles ?? null;
  const totalPages = sampled > 0 && totalPlayers ? Math.ceil(totalPlayers / SAMPLE_SIZE) : 1;

  return (
    <section className="intelligence-page" data-testid="roles-page">
      <PageHeader
        eyebrow="Intelligence · Roles"
        title={<span data-testid="page-title">Role discovery</span>}
        description={(
          <span data-testid="page-description">
            Cluster the connected player universe into archetypes surfaced by the role model.
            Only persisted classifications are shown; players without one are reported as not
            classified rather than forced into a cluster.
          </span>
        )}
        meta={(
          <>
            <span className="contract-badge">/api/v1/players/roles</span>
            <StatusBadge tone="model">Persisted role profiles</StatusBadge>
            <span className="fio-freshness">sample {SAMPLE_SIZE} players per page</span>
          </>
        )}
      />

      {roles.isLoading ? (
        <div data-testid="roles-loading">
          <LoadingSkeleton rows={5} label="Loading player universe" />
        </div>
      ) : null}

      {roles.isError ? (
        <div data-testid="roles-error">
          <ErrorState
            title="Role classifications could not be loaded"
            message={apiErrorMessage(roles.error)}
            onRetry={() => roles.refetch()}
          />
        </div>
      ) : null}

      {data && sampled > 0 ? (
        <>
          <div className="fio-grid cols-4" style={{ marginBottom: 14 }}>
            <MetricCard
              icon={Users}
              label="Players sampled"
              value={sampled}
              sub={`page ${page} of the connected universe`}
              badge="SAMPLE"
            />
            <MetricCard
              icon={Layers}
              label="Classified archetype"
              value={classified}
              sub={`${sampled > 0 ? Math.round((classified / sampled) * 100) : 0}% of this sample`}
              badge={classified > 0 ? "PERSISTED" : "NONE"}
              tone={classified > 0 ? "accent" : "warn"}
            />
            <MetricCard
              label="Insufficient sample"
              value={insufficient}
              sub="profiles below the minimum minutes"
              badge={insufficient > 0 ? "REPORTED" : "NONE"}
              tone={insufficient > 0 ? "warn" : undefined}
            />
            <MetricCard
              label="Not classified"
              value={notClassified}
              sub="no persisted role profile"
              badge={notClassified > 0 ? "GAP" : "NONE"}
              tone={notClassified > 0 ? "warn" : undefined}
            />
          </div>

          <div className="status-strip" data-testid="roles-status">
            <span className={`fio-dot ${classified > 0 ? "success" : "warn"}`} aria-hidden="true" />
            <strong>{classified} / {sampled}</strong>
            <span>
              sampled players with a qualified archetype
              {insufficient > 0 ? ` · ${insufficient} insufficient sample` : ""}
              {notClassified > 0 ? ` · ${notClassified} not classified` : ""}
            </span>
          </div>

          <p className="section-copy" data-testid="roles-coverage" style={{ marginBottom: 14 }}>
            Canonical coverage: <strong>{formatUnknown(qualifiedProfiles)}</strong> of{" "}
            <strong>{formatUnknown(totalPlayers)}</strong> players have a qualified persisted role
            profile. This page inspects {sampled} players; it is a sample denominator, not a
            universe-wide accuracy claim.
          </p>

          <div className="dashboard-grid three" data-testid="roles-clusters">
            {clusters.map((cluster) => (
              <article className="intelligence-card" key={cluster.archetype} data-testid={`roles-cluster-${cluster.archetype.replaceAll(" ", "-")}`}>
                <div className="fio-metric-top">
                  <span className="fio-badge model"><Layers size={11} /> {cluster.archetype}</span>
                  <span className="micro">{cluster.size} players</span>
                </div>
                <div className="metric-value">{cluster.size}</div>
                <ConfidenceIndicator value={cluster.avgConfidence} label="Avg archetype confidence" />
                <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10, display: "grid", gap: 6, marginTop: 10 }}>
                  {cluster.players.slice(0, 4).map((player) => (
                    <div key={player.player_id} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <small style={{ color: "var(--muted-strong)", fontSize: 11 }}>
                        {player.player_name}
                      </small>
                      <small className="fio-mono" style={{ color: "var(--fio-text-4)", fontSize: 9.5 }}>
                        {player.sample_minutes != null ? `${player.sample_minutes} min` : "sample unknown"}
                      </small>
                    </div>
                  ))}
                  {cluster.players.length > 4 ? (
                    <small style={{ color: "var(--muted)", fontSize: 10 }}>+ {cluster.players.length - 4} more in this sample</small>
                  ) : null}
                </div>
              </article>
            ))}
          </div>

          {clusters.length === 0 ? (
            <EmptyState
              icon={Layers}
              eyebrow="Insufficient data"
              title="Role classifications not yet available for this sample."
              description={notClassified > 0
                ? `${notClassified} of ${sampled} sampled players have no persisted role profile.`
                : "Every sampled profile is marked insufficient sample, so no archetype is claimed."}
              testId="roles-empty"
            />
          ) : null}

          <div style={{ marginTop: 14 }}>
            <UncertaintyNotice title="What a role cluster means">
              Archetypes are model classifications backed by stored profiles and sample minutes.
              They describe stylistic similarity, not quality or transfer suitability. A player
              missing from a cluster has not been evaluated as unsuitable — the profile may be
              absent or the sample too small.
            </UncertaintyNotice>
          </div>

          {totalPages > 1 ? (
            <Pagination
              page={page}
              totalPages={totalPages}
              onPage={(next) => setPage(Math.min(Math.max(1, next), totalPages))}
              total={totalPlayers ?? undefined}
              start={Math.min((page - 1) * SAMPLE_SIZE + 1, totalPlayers ?? 0)}
              end={Math.min(page * SAMPLE_SIZE, totalPlayers ?? 0)}
              isFetching={roles.isFetching}
              testIdPrefix="roles"
              label="Role sample pages"
            />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
