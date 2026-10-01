// /operations — Phase 17 live operations dashboard.
// Every figure is read from /api/v1/ops (probes, job runs, alerts, readiness,
// inference log). There is no sample data and no activity chart: when
// nothing has happened the page says so.
import React from "react";
import { Link } from "react-router-dom";
import { Ago, CountUp, Empty, Grid, OpsGate, Remote, Section, StatusBadge, Table, Tile, useOps } from "@/components/ops/OpsKit";

function SystemHealth() {
  const q = useOps("/system/status");
  return (
    <Section title="System health" subtitle="Each component is probed on request (database query, Redis PING, storage write/delete, provider probes).">
      <Remote query={q} what="system status" empty="No status returned.">
        {(s) => (
          <>
            <p className="ops-muted">Overall <StatusBadge value={s.status} /> · environment {s.environment} · checked <Ago ts={s.checked_at} /></p>
            <Grid>
              {Object.entries(s.components).map(([name, c]) => (
                <Tile key={name}>
                  <div className="label">{name.replace(/_/g, " ")}</div>
                  <div className="value">{c.status ? <StatusBadge value={c.status} /> : c.backend ? c.backend
                    : Object.entries(c).map(([p, v]) => <div key={p}>{p}: <StatusBadge value={v.status} /></div>)}</div>
                  <div className="detail">
                    {c.latency_ms !== undefined && `${c.latency_ms} ms`}
                    {c.migration_head && ` · migration ${c.migration_head}`}
                    {c.detail || c.note || c.degraded_mode || ""}
                  </div>
                </Tile>
              ))}
            </Grid>
            {!s.environment_audit.ok && <div className="ops-banner">Environment policy violations: {s.environment_audit.violations.join("; ")}</div>}
          </>
        )}
      </Remote>
    </Section>
  );
}

function Alerts() {
  const q = useOps("/alerts");
  return (
    <Section title="Alerts" subtitle="Raised only with evidence and a dedup key. Platform alerts are visible to ADMIN and DATA_ENGINEER roles.">
      <Remote query={q} what="alerts" empty="No alerts have been triggered.">
        {(rows) => (
          <Table rowKey={(r) => r.id} rows={rows.slice(0, 25)} columns={[
            { key: "state", label: "State", render: (r) => <StatusBadge value={r.state} /> },
            { key: "title", label: "Alert" },
            { key: "category", label: "Category" },
            { key: "evidence", label: "Evidence", num: true, render: (r) => r.evidence.length },
            { key: "notifications", label: "Delivery", render: (r) => r.notifications.map((n) => `${n.channel}:${n.state}`).join(", ") || "—" },
            { key: "triggered_at", label: "Triggered", render: (r) => <Ago ts={r.triggered_at} /> },
          ]} />
        )}
      </Remote>
    </Section>
  );
}

function Jobs() {
  const q = useOps("/ingestion/jobs", { limit: 15 });
  return (
    <Section title="Recent ingestion jobs" subtitle="Every scheduled or on-demand execution, including deferred and failed ones."
             actions={<Link className="row-action" to="/data-ops">Data operations →</Link>}>
      <Remote query={q} what="jobs" empty="No ingestion job has run yet.">
        {(rows) => (
          <Table rowKey={(r) => r.id} rows={rows} columns={[
            { key: "status", label: "Status", render: (r) => <StatusBadge value={r.status} /> },
            { key: "job_name", label: "Job" },
            { key: "provider", label: "Provider" },
            { key: "resource", label: "Resource" },
            { key: "records", label: "Records", num: true },
            { key: "latency_ms", label: "ms", num: true },
            { key: "started_at", label: "Started", render: (r) => <Ago ts={r.started_at} /> },
          ]} />
        )}
      </Remote>
    </Section>
  );
}

function Readiness() {
  const q = useOps("/competitions/readiness");
  return (
    <Section title="Competition readiness" subtitle="Computed per competition from its own data and validation; nothing is inherited."
             actions={<Link className="row-action" to="/model-ops">Model operations →</Link>}>
      <Remote query={q} what="readiness" empty="No competition data is loaded.">
        {(d) => d.competitions.length === 0 ? <Empty>No competition data is loaded.</Empty> : (
          <Table rowKey={(r) => r.competition} rows={d.competitions} columns={[
            { key: "competition", label: "Competition" },
            { key: "production_status", label: "Status", render: (r) => <StatusBadge value={r.production_status} /> },
            { key: "matches", label: "Matches", num: true, render: (r) => r.match_data.matches },
            { key: "players", label: "Players", num: true, render: (r) => r.player_data.distinct_players },
            { key: "validation", label: "Model validation", render: (r) => <StatusBadge value={r.model_support.validation.status} /> },
            { key: "live", label: "Live calibration", render: (r) => <StatusBadge value={r.calibration.live} /> },
            { key: "mode", label: "Data mode", render: (r) => r.freshness.data_mode || "—" },
          ]} />
        )}
      </Remote>
    </Section>
  );
}

function ModelHealth() {
  const q = useOps("/models/health");
  return (
    <Section title="Match prediction health" subtitle="From the immutable inference log. Live and historical-replay requests are counted separately.">
      <Remote query={q} what="model health" empty="No model health data.">
        {(h) => h.inference_volume === 0 ? <Empty>No prediction request has been logged.</Empty> : (
          <Grid>
            <Tile><div className="label">Requests logged</div><div className="value"><CountUp value={h.inference_volume} /></div>
              <div className="detail">{h.live_inference_volume} live</div></Tile>
            <Tile><div className="label">Refusal rate</div><div className="value"><CountUp value={h.refusal_rate} /></div>
              <div className="detail">{Object.entries(h.by_status).map(([k, v]) => `${k} ${v}`).join(" · ")}</div></Tile>
            <Tile><div className="label">Latency p50 / p95 / p99</div>
              <div className="value">{h.latency_ms.p50} / {h.latency_ms.p95} / {h.latency_ms.p99} ms</div></Tile>
            <Tile><div className="label">Live calibration</div><div className="value"><StatusBadge value={h.live_calibration.status} /></div>
              <div className="detail">{h.live_calibration.n ?? 0} live outcomes (minimum {h.live_calibration.minimum_required ?? "—"})</div></Tile>
          </Grid>
        )}
      </Remote>
    </Section>
  );
}

export default function OperationsPage() {
  return (
    <OpsGate title="Live operations" eyebrow="PHASE 17 · OPERATIONS">
      {() => (
        <div data-testid="operations-page">
          <SystemHealth />
          <ModelHealth />
          <Readiness />
          <Alerts />
          <Jobs />
        </div>
      )}
    </OpsGate>
  );
}
