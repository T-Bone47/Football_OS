// /model-ops — Phase 17 model operations console. Registry, health,
// calibration and drift come from the API; live and historical-replay
// evidence are always shown separately.
import React, { useState } from "react";
import { describeError, opsPost } from "@/lib/opsApi";
import { CountUp, Empty, Grid, OpsGate, Remote, Section, StatusBadge, Table, TabPanel, Tabs, Tile, useOps } from "@/components/ops/OpsKit";

function Registry({ me }) {
  const q = useOps("/models");
  const [result, setResult] = useState({});
  const promote = async (modelId) => {
    try {
      const r = await opsPost(`/models/${modelId}/promote`);
      setResult({ [modelId]: { ok: true, text: r.status } });
      q.reload();
    } catch (e) {
      const blockers = e?.response?.data?.detail?.blockers;
      setResult({ [modelId]: { ok: false, text: blockers ? blockers.join("; ") : describeError(e) } });
    }
  };
  return (
    <Section title="Model registry" subtitle="Only registered models can serve. ACTIVE requires live outcomes and a human promotion; nothing is promoted automatically.">
      <Remote query={q} what="models" empty="No model is registered.">
        {(rows) => rows.map((m) => (
          <div className="ops-section" key={`${m.model_id}:${m.model_version}`}>
            <p><strong>{m.model_id}</strong> v{m.model_version} · <StatusBadge value={m.deployment_state} /> · domain {m.domain}</p>
            <dl className="ops-kv">
              <dt>Feature version</dt><dd>{m.feature_version}</dd>
              <dt>Dataset version</dt><dd>{m.dataset_version}</dd>
              <dt>Artifact SHA-256</dt><dd className="ops-mono">{m.artifact_sha256}</dd>
              <dt>Supported competitions</dt><dd>{m.supported_competitions.length ? m.supported_competitions.join(", ") : "none (no competition has passed validation)"}</dd>
              <dt>Minimum history</dt><dd>{m.min_history_matches} matches per side</dd>
              <dt>Max data age (live)</dt><dd>{m.max_feature_age_hours ?? "—"} h</dd>
            </dl>
            <h3 className="ops-muted">Per-competition validation (walk-forward on real results; historical replay, not live)</h3>
            {Object.entries(m.validation_metrics).filter(([, v]) => typeof v === "object").length === 0 ? <Empty>No validation has run.</Empty> : (
              <Table rowKey={(r) => r.k} rows={Object.entries(m.validation_metrics).filter(([, v]) => typeof v === "object").map(([k, v]) => ({ k, ...v }))} columns={[
                { key: "k", label: "Competition" },
                { key: "status", label: "Verdict", render: (r) => <StatusBadge value={r.status} /> },
                { key: "n", label: "n", num: true },
                { key: "log_loss", label: "Log loss", num: true },
                { key: "baseline_class_prior_log_loss", label: "Baseline", num: true },
                { key: "brier", label: "Brier", num: true },
                { key: "ece", label: "ECE", num: true },
                { key: "accuracy", label: "Accuracy", num: true },
              ]} />
            )}
            {m.validation_metrics.declared_metrics_status && <p className="ops-muted">Declared metrics: {m.validation_metrics.declared_metrics_status}</p>}
            {me.role === "ADMIN" && (
              <p>
                <button className="primary-button" onClick={() => promote(m.model_id)}>Request promotion to ACTIVE</button>{" "}
                {result[m.model_id] && <span className={result[m.model_id].ok ? "ops-muted" : "ops-error-text"}>{result[m.model_id].text}</span>}
              </p>
            )}
          </div>
        ))}
      </Remote>
    </Section>
  );
}

function Health() {
  const q = useOps("/models/health");
  return (
    <Section title="Live model health" subtitle="LiveModelHealthSnapshot from the immutable inference log.">
      <Remote query={q} what="health" empty="No health data.">
        {(h) => h.inference_volume === 0 ? <Empty>No inference request has been logged.</Empty> : (
          <>
            <Grid>
              <Tile><div className="label">Volume</div><div className="value"><CountUp value={h.inference_volume} /></div><div className="detail">live {h.live_inference_volume}</div></Tile>
              <Tile><div className="label">Refusal rate</div><div className="value"><CountUp value={h.refusal_rate} /></div></Tile>
              <Tile><div className="label">OOD rate</div><div className="value"><CountUp value={h.ood_rate} /></div></Tile>
              <Tile><div className="label">Missing features</div><div className="value">{h.missing_feature_rate ?? "—"}</div></Tile>
              <Tile><div className="label">Latency p95</div><div className="value"><CountUp value={h.latency_ms.p95} suffix=" ms" /></div></Tile>
            </Grid>
            <p className="ops-muted">By status: {Object.entries(h.by_status).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
            <p className="ops-muted">By evidence mode: {Object.entries(h.by_evidence_mode).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
            {h.confidence_histogram && (
              <Table rowKey={(r) => r.bin} rows={Object.entries(h.confidence_histogram).map(([bin, n]) => ({ bin, n }))} columns={[
                { key: "bin", label: "Confidence" }, { key: "n", label: "Served predictions", num: true },
              ]} />
            )}
          </>
        )}
      </Remote>
    </Section>
  );
}

function Calibration({ mode }) {
  const q = useOps("/models/calibration", { mode });
  const label = mode === "LIVE" ? "Live calibration" : "Historical-replay calibration";
  return (
    <Section title={label} subtitle={mode === "LIVE" ? "Only predictions logged before kickoff count as live." : "Predictions made after the match (backtests). Never presented as live evidence."}>
      <Remote query={q} what={label} empty="No calibration data.">
        {(c) => c.status !== "MEASURED" ? <Empty><StatusBadge value={c.status} /> — {c.n} of {c.minimum_required} required outcomes.</Empty> : (
          <>
            <Grid>
              {["n", "log_loss", "baseline_class_prior_log_loss", "brier", "ece", "mce", "accuracy"].map((k) => (
                <Tile key={k}><div className="label">{k.replace(/_/g, " ")}</div><div className="value">{String(c[k])}</div></Tile>
              ))}
              <Tile><div className="label">Beats class-prior baseline</div><div className="value"><StatusBadge value={c.beats_class_prior_baseline ? "PASS" : "FAIL"} /></div></Tile>
            </Grid>
            <Table rowKey={(r) => r.bin.join("-")} rows={c.calibration_curve} columns={[
              { key: "bin", label: "Confidence bin", render: (r) => `${r.bin[0]}–${r.bin[1]}` },
              { key: "n", label: "n", num: true }, { key: "mean_confidence", label: "Mean confidence", num: true },
              { key: "accuracy", label: "Observed accuracy", num: true },
            ]} />
          </>
        )}
      </Remote>
    </Section>
  );
}

function Drift({ mode }) {
  const q = useOps("/models/drift", { mode });
  return (
    <Section title={`Drift (${mode})`} subtitle="PSI between the earlier and later half of served inputs. DRIFT recommends retraining through the governed challenger workflow; nothing retrains automatically.">
      <Remote query={q} what="drift" empty="No drift data.">
        {(d) => d.status === "NOT_ENOUGH_OBSERVATIONS" ? <Empty><StatusBadge value={d.status} /> — {d.reference_n}/{d.current_n} (minimum {d.minimum_per_window} per window).</Empty> : (
          <>
            <p className="ops-muted">Overall <StatusBadge value={d.status} /> · retrain recommended: {String(d.retrain_recommended)} · {d.action}</p>
            <Table rowKey={(r) => r.f} rows={Object.entries(d.features).map(([f, v]) => ({ f, ...v }))} columns={[
              { key: "f", label: "Feature" }, { key: "psi", label: "PSI", num: true },
              { key: "class", label: "Class", render: (r) => <StatusBadge value={r.class || r.status} /> },
            ]} />
          </>
        )}
      </Remote>
    </Section>
  );
}

const TABS = [{ id: "registry", label: "Registry & deployment" }, { id: "health", label: "Health" },
  { id: "calibration", label: "Calibration" }, { id: "drift", label: "Drift & OOD" }];

export default function ModelOpsPage() {
  const [tab, setTab] = useState("registry");
  return (
    <OpsGate title="Model operations" eyebrow="PHASE 17 · MODEL OPS">
      {(me) => (
        <div data-testid="model-ops-page">
          <Tabs tabs={TABS} active={tab} onChange={setTab} />
          <TabPanel id={tab}>
            {tab === "registry" && <Registry me={me} />}
            {tab === "health" && <Health />}
            {tab === "calibration" && <><Calibration mode="LIVE" /><Calibration mode="HISTORICAL_REPLAY" /></>}
            {tab === "drift" && <><Drift mode="LIVE" /><Drift mode="VALIDATION_BACKTEST" /></>}
          </TabPanel>
        </div>
      )}
    </OpsGate>
  );
}
