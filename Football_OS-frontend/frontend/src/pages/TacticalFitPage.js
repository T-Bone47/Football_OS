import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, CircleAlert, Compass, Database, Radar, Target } from "lucide-react";
import {
  apiErrorMessage,
  getClubs,
  getPlayer,
  getPlayerPage,
  getPlayerTacticalFit,
  getTacticalContexts,
} from "@/lib/footballApi";
import PerformanceRadar from "@/components/PerformanceRadar";
import FormationPitch from "@/components/FormationPitch";
import {
  ChartContainer, ErrorState, InsufficientData, LoadingSkeleton, PageHeader,
  StatusBadge, UncertaintyNotice, formatUnknown,
} from "@/components/ui";

function pct(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export default function TacticalFitPage() {
  const [params] = useSearchParams();
  const [playerId, setPlayerId] = useState(params.get("player") || "");
  const [clubId, setClubId] = useState("");
  const [contextId, setContextId] = useState("433_dm_deep_distributor");

  const roster = useQuery({
    queryKey: ["tactical-roster"],
    queryFn: () => getPlayerPage({ page: 1, page_size: 100, sort_by: "name" }),
    retry: false,
  });

  const clubs = useQuery({
    queryKey: ["tactical-clubs"],
    queryFn: getClubs,
    retry: false,
  });

  const contexts = useQuery({
    queryKey: ["tactical-contexts"],
    queryFn: getTacticalContexts,
    retry: false,
  });

  const player = useQuery({
    queryKey: ["tactical-player", playerId],
    queryFn: () => getPlayer(playerId),
    enabled: !!playerId,
    retry: false,
  });

  const tacticalFit = useQuery({
    queryKey: ["tactical-fit", playerId, contextId, clubId],
    queryFn: () =>
      getPlayerTacticalFit(playerId, {
        context_id: contextId,
        team_id: clubId || undefined,
      }),
    enabled: !!playerId && !!contextId,
    retry: false,
  });

  const activeContext = useMemo(
    () => (contexts.data || []).find((context) => context.context_id === contextId),
    [contexts.data, contextId],
  );

  const formation = activeContext?.formation || "4-3-3";
  const role = activeContext?.target_role || "Deep Distributor";
  const fit = tacticalFit.data;
  const isInsufficient = fit?.fit_status === "INSUFFICIENT_DATA" || fit?.confidence === "INSUFFICIENT_DATA";

  const radarData = useMemo(() => {
    if (!fit?.dimension_breakdown) return [];
    return Object.entries(fit.dimension_breakdown)
      .filter(([, data]) => typeof data?.fit_score === "number")
      .map(([dimension, data]) => ({
        label: dimension.charAt(0).toUpperCase() + dimension.slice(1),
        value: Math.max(0, Math.min(1, data.fit_score)),
      }));
  }, [fit]);

  const dimensions = fit && !isInsufficient ? [
    { label: `Position fit (${fit.target_position || "role"})`, value: fit.position_fit },
    { label: `Role fit (${fit.target_role || role})`, value: fit.role_fit },
    { label: "Dimension requirement fit", value: fit.dimension_fit },
    { label: `Style alignment (${activeContext?.possession_style || "system"})`, value: fit.style_fit },
    { label: "Exposure maturity", value: fit.contextual_fit },
  ].filter((row) => row.value !== null && row.value !== undefined) : [];

  return (
    <section className="intelligence-page" data-testid="tactical-fit-page">
      <PageHeader
        eyebrow="Tactical · System fit"
        title={<span data-testid="page-title">Tactical fit workspace</span>}
        description={(
          <span data-testid="page-description">
            Evaluate empirical player compatibility against team tactical systems, formations,
            and functional role requirements. Fit is a model estimate over the evidence the
            engine actually received.
          </span>
        )}
        meta={(
          <>
            {fit ? (
              <StatusBadge
                tone={isInsufficient ? "warn" : fit.fit_status === "HIGH" ? "success" : "neutral"}
                testId="tactical-fit-badge"
              >
                {isInsufficient ? "INSUFFICIENT SAMPLE" : `${fit.fit_status || "ESTIMATE"} · ${pct(fit.fit_score)}`}
              </StatusBadge>
            ) : (
              <StatusBadge tone="info" testId="tactical-status-badge">CANONICAL FIT ENGINE</StatusBadge>
            )}
            <span className="contract-badge">/api/v1/players/&#123;id&#125;/tactical-fit</span>
            {fit?.confidence ? <span className="fio-freshness">confidence <strong>{fit.confidence}</strong></span> : null}
          </>
        )}
      />

      <div className="fio-toolbar" data-testid="tactical-toolbar">
        <label className="fio-input" style={{ flex: "1 1 260px" }}>
          <Target size={14} aria-hidden="true" />
          <select
            value={playerId}
            onChange={(event) => setPlayerId(event.target.value)}
            aria-label="Player"
            data-testid="tactical-player-select"
          >
            <option value="">Select player</option>
            {(roster.data?.items || []).map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name} {entry.primary_position ? `(${entry.primary_position})` : ""}
              </option>
            ))}
          </select>
        </label>

        <label className="fio-input" style={{ flex: "0 1 260px" }}>
          <Radar size={14} aria-hidden="true" />
          <select
            value={clubId}
            onChange={(event) => setClubId(event.target.value)}
            aria-label="Team"
            data-testid="tactical-club-select"
          >
            <option value="">Team context (optional)</option>
            {(clubs.data || []).map((club) => (
              <option key={club.id} value={club.id}>{club.name}</option>
            ))}
          </select>
        </label>

        <label className="fio-input" style={{ flex: "1 1 280px" }}>
          <Compass size={14} aria-hidden="true" />
          <select
            value={contextId}
            onChange={(event) => setContextId(event.target.value)}
            aria-label="Tactical System"
            data-testid="tactical-context-select"
          >
            {(contexts.data || []).map((context) => (
              <option key={context.context_id} value={context.context_id}>
                {context.formation} · {context.target_position} ({context.target_role})
              </option>
            ))}
          </select>
        </label>
      </div>

      {contexts.isError ? (
        <div style={{ marginBottom: 14 }}>
          <ErrorState compact title="Tactical contexts unavailable" message={apiErrorMessage(contexts.error)} onRetry={() => contexts.refetch()} />
        </div>
      ) : null}

      <div className="split-columns">
        <div className="data-block" data-testid="tactical-pitch-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">System visualization</p>
              <h3>{formation} · {role}</h3>
            </div>
            <StatusBadge tone="neutral">STRUCTURAL</StatusBadge>
          </div>
          <FormationPitch
            formation={formation}
            players={[]}
            variant="system"
            caption={`${formation} · ${role} — structural role map, not player assignments`}
            testId="tactical-pitch"
            showLegend={false}
          />
          <p className="section-copy" style={{ marginTop: 12 }}>
            {activeContext?.description || `Structural alignment for ${formation} ${role}. Marker positions are derived from the formation string; no player is assigned to a slot on this diagram.`}
          </p>
        </div>

        <div className="data-block" data-testid="tactical-fit-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Fit evaluation</p>
              <h3>
                {fit && !isInsufficient
                  ? `${player.data?.name || "Player"} · ${pct(fit.fit_score)} compatibility`
                  : "Select a player to calculate fit"}
              </h3>
            </div>
            {fit?.confidence ? (
              <StatusBadge tone={fit.confidence === "HIGH" ? "success" : fit.confidence === "MEDIUM" ? "info" : "warn"}>
                Confidence: {fit.confidence}
              </StatusBadge>
            ) : null}
          </div>

          {tacticalFit.isLoading ? (
            <div data-testid="tactical-fit-loading">
              <LoadingSkeleton rows={4} label={`Calculating tactical suitability against ${role}`} />
            </div>
          ) : null}

          {tacticalFit.isError ? (
            <div data-testid="tactical-fit-error">
              <ErrorState
                compact
                title="Tactical fit could not be calculated"
                message={apiErrorMessage(tacticalFit.error)}
                onRetry={() => tacticalFit.refetch()}
              />
            </div>
          ) : null}

          {isInsufficient ? (
            <InsufficientData
              title="The sample is too small for a defensible fit score"
              description={`The engine returned ${fit.fit_status || "INSUFFICIENT_DATA"} for this player and context. No percentage is shown because a score would overstate the evidence.`}
              testId="tactical-insufficient"
            />
          ) : null}

          {fit && !isInsufficient ? (
            <div className="dimension-list" data-testid="tactical-dimensions">
              {dimensions.map((row) => (
                <div key={row.label}>
                  <span>{row.label}</span>
                  <div className="dimension-track pos">
                    <i style={{ width: typeof row.value === "number" ? `${Math.round(row.value * 100)}%` : "0%" }} />
                  </div>
                  <b>{pct(row.value)}</b>
                </div>
              ))}
              {dimensions.length === 0 ? (
                <p className="section-copy">The endpoint returned no numeric dimensions for this fit.</p>
              ) : null}
            </div>
          ) : null}

          {!playerId ? (
            <p className="section-copy" style={{ marginTop: 12 }}>
              Select a player from the toolbar to run a point-in-time tactical fit calculation.
            </p>
          ) : null}

          {fit && !isInsufficient ? (
            <div style={{ marginTop: 18, display: "grid", gap: 10 }}>
              {fit.why_fit?.length > 0 ? (
                <div className="fio-notice" style={{ background: "rgba(91,227,143,.04)", borderColor: "rgba(91,227,143,.22)" }}>
                  <CheckCircle2 size={15} aria-hidden="true" style={{ color: "var(--fio-success)" }} />
                  <div>
                    <strong>Tactical strengths</strong>
                    <ul style={{ margin: "5px 0 0", paddingLeft: 16, lineHeight: 1.6 }}>
                      {fit.why_fit.map((reason, index) => <li key={index}>{reason}</li>)}
                    </ul>
                  </div>
                </div>
              ) : null}
              {fit.why_not_fit?.length > 0 ? (
                <div className="fio-notice warn">
                  <CircleAlert size={15} aria-hidden="true" />
                  <div>
                    <strong>Tactical caveats &amp; bottlenecks</strong>
                    <ul style={{ margin: "5px 0 0", paddingLeft: 16, lineHeight: 1.6 }}>
                      {fit.why_not_fit.map((reason, index) => <li key={index}>{reason}</li>)}
                    </ul>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {radarData.length > 0 ? (
        <div style={{ marginTop: 14 }}>
          <ChartContainer
            title="Requirement compatibility radar"
            subtitle="Only dimensions with a numeric fit score are plotted; missing axes are omitted rather than zero-filled."
            coverage={`${radarData.length} dimensions`}
            testId="tactical-radar-panel"
          >
            <PerformanceRadar data={radarData} testId="tactical-radar" />
          </ChartContainer>
        </div>
      ) : null}

      <div style={{ marginTop: 14 }}>
        <UncertaintyNotice title="How to read tactical fit">
          Fit compares a player&apos;s measured profile with a system requirement. It is not a
          prediction of performance, availability, or price. Confidence reflects the evidence
          behind the estimate; an insufficient sample is shown as such, never as 0%.
        </UncertaintyNotice>
      </div>

      {!fit && playerId && !tacticalFit.isLoading && !tacticalFit.isError ? (
        <p className="section-copy" style={{ marginTop: 12 }}>
          No fit record was returned for {formatUnknown(player.data?.name)} in this context.
        </p>
      ) : null}
    </section>
  );
}
