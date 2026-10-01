// /data-ops — Phase 17 data operations console. All values come from
// /api/v1/ops; empty tables mean nothing has been recorded.
import React, { useState } from "react";
import { describeError, opsPost } from "@/lib/opsApi";
import { Ago, Empty, Grid, OpsGate, Remote, Section, StatusBadge, Table, TabPanel, Tabs, Tile, useOps } from "@/components/ops/OpsKit";

function Providers({ me }) {
  const q = useOps("/providers");
  const [probe, setProbe] = useState({ running: false, error: null });
  const canProbe = ["ADMIN", "DATA_ENGINEER"].includes(me.role);
  const run = async () => {
    setProbe({ running: true, error: null });
    try { await opsPost("/providers/probe"); q.reload(); setProbe({ running: false, error: null }); }
    catch (e) { setProbe({ running: false, error: describeError(e) }); }
  };
  return (
    <Section title="Provider connectivity" subtitle="Latest real probe per provider and resource. A provider never probed is UNKNOWN."
             actions={canProbe && <button className="primary-button" onClick={run} disabled={probe.running}>{probe.running ? "Probing…" : "Run live probe"}</button>}>
      {probe.error && <div className="ops-state ops-error">{probe.error}</div>}
      <Remote query={q} what="providers" empty="No provider has been probed.">
        {(d) => d.probes.length === 0 ? <Empty>No provider has been probed.</Empty> : (
          <>
            <Table rowKey={(r) => `${r.provider}/${r.resource}`} rows={d.probes} columns={[
              { key: "provider", label: "Provider" },
              { key: "resource", label: "Resource" },
              { key: "state", label: "State", render: (r) => <StatusBadge value={r.state} /> },
              { key: "authentication_state", label: "Authentication" },
              { key: "http_status", label: "HTTP", num: true },
              { key: "latency_ms", label: "ms", num: true },
              { key: "quota", label: "Quota", render: (r) => r.quota?.exposed === false ? "not exposed" : <span className="ops-mono">{JSON.stringify(r.quota)}</span> },
              { key: "probed_at", label: "Probed", render: (r) => <Ago ts={r.probed_at} /> },
            ]} />
            <p className="ops-muted">Rate governance ({d.rate_governance.backend}): {Object.keys(d.rate_governance.providers).length === 0
              ? "no requests made by this API process yet."
              : Object.entries(d.rate_governance.providers).map(([p, v]) => `${p} ${v.requests_last_minute}/${v.budget.per_minute} per min (${v.budget.source}), 429s ${v.http_429}, retries ${v.retries}`).join(" · ")}</p>
          </>
        )}
      </Remote>
    </Section>
  );
}

function Jobs({ failedOnly }) {
  const q = useOps("/ingestion/jobs", { limit: 200 });
  return (
    <Section title={failedOnly ? "Failed and blocked jobs" : "Ingestion runs"}
             subtitle={failedOnly ? "Jobs that did not reach Silver, with the recorded reason." : "Every execution with its outcome, latency, records and Bronze snapshot."}>
      <Remote query={q} what="jobs" empty="No ingestion job has run.">
        {(rows) => {
          const shown = failedOnly ? rows.filter((r) => r.status !== "SUCCESS") : rows;
          if (shown.length === 0) return <Empty>{failedOnly ? "No failed or blocked jobs in the latest 200." : "No ingestion job has run."}</Empty>;
          return (
            <Table rowKey={(r) => r.id} rows={shown} columns={[
              { key: "status", label: "Status", render: (r) => <StatusBadge value={r.status} /> },
              { key: "job_name", label: "Job" },
              { key: "schedule_class", label: "Schedule" },
              { key: "provider", label: "Provider" },
              { key: "resource", label: "Resource" },
              { key: "parameters", label: "Scope", render: (r) => <span className="ops-mono">{JSON.stringify(r.parameters)}</span> },
              { key: "records", label: "Records", num: true },
              { key: "latency_ms", label: "ms", num: true },
              { key: "errors", label: "Errors", render: (r) => r.errors.length ? <span className="ops-error-text">{r.errors[0]}</span> : "—" },
              { key: "started_at", label: "Started", render: (r) => <Ago ts={r.started_at} /> },
            ]} />
          );
        }}
      </Remote>
    </Section>
  );
}

function Snapshots() {
  const q = useOps("/ingestion/snapshots", { limit: 100 });
  return (
    <Section title="Bronze snapshots" subtitle="Content-addressed raw payloads with request metadata and licence.">
      <Remote query={q} what="snapshots" empty="No snapshot has been captured.">
        {(rows) => (
          <Table rowKey={(r) => `${r.sha256}-${r.ingestion_run_id}`} rows={rows} columns={[
            { key: "sha256", label: "SHA-256", render: (r) => <span className="ops-mono">{r.sha256.slice(0, 16)}…</span> },
            { key: "provider", label: "Provider" },
            { key: "endpoint", label: "Endpoint" },
            { key: "parameters", label: "Params", render: (r) => <span className="ops-mono">{JSON.stringify(r.parameters)}</span> },
            { key: "http_status", label: "HTTP", num: true },
            { key: "size_bytes", label: "Bytes", num: true },
            { key: "validation", label: "Validation", render: (r) => <StatusBadge value={r.validation} /> },
            { key: "provider_retrieved_at", label: "Retrieved", render: (r) => <Ago ts={r.provider_retrieved_at} /> },
          ]} />
        )}
      </Remote>
    </Section>
  );
}

function FreshnessChain({ csId, name }) {
  const q = useOps(`/freshness/${csId}`);
  return (
    <Remote query={q} what={`freshness for ${name}`} empty="No freshness data.">
      {(f) => (
        <div className="ops-section">
          <p className="ops-muted"><strong>{f.competition}</strong> · data mode {f.data_mode} · live: {String(f.is_live)}</p>
          <Table rowKey={(r) => r.layer} rows={f.layers} columns={[
            { key: "layer", label: "Layer" },
            { key: "state", label: "State", render: (r) => <StatusBadge value={r.state} /> },
            { key: "timestamp", label: "Timestamp", render: (r) => r.timestamp ? <Ago ts={r.timestamp} /> : "—" },
            { key: "age_hours", label: "Age (h)", num: true },
            { key: "basis", label: "Basis" },
          ]} />
        </div>
      )}
    </Remote>
  );
}

function Freshness() {
  const q = useOps("/competitions/readiness");
  return (
    <Section title="Freshness propagation" subtitle="Source → Bronze → Silver → Feature → Model → Intelligence → Decision → Alert, with real timestamps. Archive data is never shown as live.">
      <Remote query={q} what="competitions" empty="No competition data.">
        {(d) => d.competitions.length === 0 ? <Empty>No competition data is loaded.</Empty>
          : d.competitions.flatMap((c) => c.competition_season_ids.map((id) => <FreshnessChain key={id} csId={id} name={c.competition} />))}
      </Remote>
    </Section>
  );
}

function Quality() {
  const q = useOps("/quality/reports", { limit: 100 });
  return (
    <Section title="Data quality" subtitle="DataQualityReports for Bronze payloads and Silver scopes. Checks that could not run are WARN with evaluated=false.">
      <Remote query={q} what="quality reports" empty="No quality report has been produced.">
        {(rows) => {
          const incidents = rows.flatMap((r) => r.checks.filter((c) => c.status !== "PASS").map((c) => ({ ...c, scope: r.scope, at: r.created_at, id: r.id })));
          return (
            <>
              <Table rowKey={(r) => r.id} rows={rows.slice(0, 30)} columns={[
                { key: "overall", label: "Overall", render: (r) => <StatusBadge value={r.overall} /> },
                { key: "scope", label: "Scope", render: (r) => <span className="ops-mono">{r.scope}</span> },
                { key: "records_examined", label: "Records", num: true },
                { key: "checks", label: "Checks", render: (r) => r.checks.map((c) => `${c.name}:${c.status}`).join(", ") },
                { key: "created_at", label: "At", render: (r) => <Ago ts={r.created_at} /> },
              ]} />
              <h3 className="ops-muted">Quality incidents and conflicts (non-PASS checks)</h3>
              {incidents.length === 0 ? <Empty>Every check passed.</Empty> : (
                <Table rowKey={(r, i) => `${r.id}-${i}`} rows={incidents.slice(0, 50)} columns={[
                  { key: "status", label: "Status", render: (r) => <StatusBadge value={r.status} /> },
                  { key: "name", label: "Check" },
                  { key: "affected_records", label: "Affected", num: true },
                  { key: "evaluated", label: "Evaluated", render: (r) => String(r.evaluated) },
                  { key: "detail", label: "Detail" },
                  { key: "scope", label: "Scope", render: (r) => <span className="ops-mono">{r.scope}</span> },
                ]} />
              )}
            </>
          );
        }}
      </Remote>
    </Section>
  );
}

function Coverage() {
  const q = useOps("/capabilities");
  return (
    <Section title="Competition coverage and provider capability" subtitle="LIVE_AVAILABLE means verified by a real request from this deployment, not real-time data.">
      <Remote query={q} what="capability matrix" empty="No capability data.">
        {(m) => (
          <>
            {Object.entries(m.providers).map(([p, v]) => (
              <div key={p} className="ops-section">
                <p><strong>{p}</strong> · connectivity <StatusBadge value={v.connectivity} /> · {v.timing?.data_mode}</p>
                <Grid>
                  {Object.entries(v.resources).filter(([, r]) => r.state !== "UNAVAILABLE").map(([res, r]) => (
                    <Tile key={res}><div className="label">{res}</div><div className="value"><StatusBadge value={r.state} /></div>
                      <div className="detail">{r.evidence}{r.successful_scopes ? ` · ${r.successful_scopes} scope(s)` : ""}</div></Tile>
                  ))}
                </Grid>
              </div>
            ))}
            <p className="ops-muted">StatsBomb index: {m.statsbomb_competition_seasons.filter((c) => c.matches === "LIVE_AVAILABLE").length} of {m.statsbomb_competition_seasons.length} competition seasons ingested.</p>
            <Table rowKey={(r) => `${r.competition_id}-${r.season_id}`} rows={m.statsbomb_competition_seasons.filter((c) => c.matches === "LIVE_AVAILABLE")} columns={[
              { key: "competition", label: "Competition" },
              { key: "season", label: "Season" },
              { key: "matches", label: "Matches", render: (r) => <StatusBadge value={r.matches} /> },
              { key: "provider_match_updated", label: "Provider updated", render: (r) => <Ago ts={r.provider_match_updated} /> },
            ]} />
          </>
        )}
      </Remote>
    </Section>
  );
}

const TABS = [
  { id: "providers", label: "Providers" }, { id: "runs", label: "Ingestion runs" }, { id: "snapshots", label: "Snapshots" },
  { id: "freshness", label: "Freshness" }, { id: "quality", label: "Quality & conflicts" }, { id: "failed", label: "Failed jobs" },
  { id: "coverage", label: "Coverage" },
];

export default function DataOpsPage() {
  const [tab, setTab] = useState("providers");
  return (
    <OpsGate title="Data operations" eyebrow="PHASE 17 · DATA OPS">
      {(me) => (
        <div data-testid="data-ops-page">
          <Tabs tabs={TABS} active={tab} onChange={setTab} />
          <TabPanel id={tab}>
            {tab === "providers" && <Providers me={me} />}
            {tab === "runs" && <Jobs />}
            {tab === "snapshots" && <Snapshots />}
            {tab === "freshness" && <Freshness />}
            {tab === "quality" && <Quality />}
            {tab === "failed" && <Jobs failedOnly />}
            {tab === "coverage" && <Coverage />}
          </TabPanel>
        </div>
      )}
    </OpsGate>
  );
}
