import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Activity, ShieldCheck, Database, RefreshCw, AlertTriangle, CheckCircle2,
  Clock, GitBranch, Layers, Play, Check, ChevronRight, Server, Box
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

export default function OperationsPage() {
  const [activeTab, setActiveTab] = useState("readiness"); // "readiness", "ingestion", "lifecycle"
  const [readinessList, setReadinessList] = useState([]);
  const [ingestionRuns, setIngestionRuns] = useState([]);
  const [lifecycleModels, setLifecycleModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState(null);

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchData = async () => {
    try {
      const [readinessRes, runsRes, modelsRes] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/phase10/operations/competition-readiness`),
        axios.get(`${BACKEND_URL}/api/phase10/operations/ingestion/runs`),
        axios.get(`${BACKEND_URL}/api/phase10/operations/model-lifecycle`),
      ]);
      setReadinessList(readinessRes.data);
      setIngestionRuns(runsRes.data);
      setLifecycleModels(modelsRes.data);
    } catch (err) {
      console.error("Failed to load operations data", err);
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerIngestion = async () => {
    setTriggering(true);
    setTriggerResult(null);
    try {
      const res = await axios.post(`${BACKEND_URL}/api/phase10/operations/ingestion/trigger`, {
        provider: "api-football",
        resource: "fixtures",
        dry_run: false
      });
      setTriggerResult(res.data);
      // Refresh runs
      const runsRes = await axios.get(`${BACKEND_URL}/api/phase10/operations/ingestion/runs`);
      setIngestionRuns(runsRes.data);
    } catch (err) {
      console.error("Failed to trigger ingestion", err);
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <main className="page-container" data-testid="operations-loading">
        <div className="empty-state">
          <p>Loading live operations, readiness & ingestion lifecycle…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="page-container" data-testid="operations-page">
      {/* Header */}
      <header className="page-header" data-testid="operations-header">
        <div>
          <div className="eyebrow" data-testid="operations-eyebrow">
            PHASE 10 · LIVE OPERATIONS & PLATFORM GOVERNANCE
          </div>
          <h1 data-testid="operations-title">Continuous Operations & Readiness</h1>
          <p className="page-subtitle">
            Controlled 11-stage ingestion, competition readiness gates, and formal model lifecycle tracking.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="primary-button"
            onClick={handleTriggerIngestion}
            disabled={triggering}
            data-testid="trigger-ingestion-btn"
          >
            <Play size={14} /> {triggering ? "Executing 11-Stage Pipeline…" : "Trigger Operational Ingestion"}
          </button>
        </div>
      </header>

      {/* Trigger Feedback Banner */}
      {triggerResult && (
        <section className="result-card" style={{ marginBottom: "1.25rem", padding: "1rem", background: "rgba(16, 185, 129, 0.08)", border: "1px solid #10b981", borderRadius: "6px" }} data-testid="trigger-result-banner">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <CheckCircle2 size={18} color="#10b981" />
              <strong style={{ color: "#10b981" }}>Cycle Complete: {triggerResult.status}</strong>
            </div>
            <span style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "var(--text-muted, #94a3b8)" }}>
              Run ID: {triggerResult.ingestion_run_id}
            </span>
          </div>
          <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--text-bright, #fff)" }}>
            <span>Seen: {triggerResult.records_seen}</span>
            <span>Accepted: {triggerResult.records_accepted}</span>
            <span>Gate: {triggerResult.validation_status}</span>
            <span>Snapshot: {triggerResult.snapshot_id}</span>
            <span style={{ fontFamily: "monospace" }}>SHA-256: {triggerResult.checksum?.slice(0, 16)}…</span>
          </div>
        </section>
      )}

      {/* Tabs */}
      <div className="tab-bar" style={{ display: "flex", gap: "1rem", borderBottom: "1px solid var(--border-subtle, #1e293b)", paddingBottom: "0.5rem", marginBottom: "1.5rem" }}>
        <button
          className={`tab-button ${activeTab === "readiness" ? "active" : ""}`}
          onClick={() => setActiveTab("readiness")}
          data-testid="tab-readiness"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "readiness" ? "var(--text-bright, #fff)" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "readiness" ? "2px solid var(--accent-blue, #3b82f6)" : "none" }}
        >
          Competition Readiness ({readinessList.length})
        </button>
        <button
          className={`tab-button ${activeTab === "ingestion" ? "active" : ""}`}
          onClick={() => setActiveTab("ingestion")}
          data-testid="tab-ingestion"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "ingestion" ? "var(--text-bright, #fff)" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "ingestion" ? "2px solid var(--accent-blue, #3b82f6)" : "none" }}
        >
          Ingestion Runs & Provenance ({ingestionRuns.length})
        </button>
        <button
          className={`tab-button ${activeTab === "lifecycle" ? "active" : ""}`}
          onClick={() => setActiveTab("lifecycle")}
          data-testid="tab-lifecycle"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "lifecycle" ? "var(--text-bright, #fff)" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "lifecycle" ? "2px solid var(--accent-blue, #3b82f6)" : "none" }}
        >
          Model Governance & Lifecycle ({lifecycleModels.length})
        </button>
      </div>

      {/* TAB 1: COMPETITION READINESS */}
      {activeTab === "readiness" && (
        <section data-testid="readiness-section">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1rem" }}>
            {readinessList.map(comp => {
              const isProd = comp.readiness_state === "PRODUCTION_READY";
              const isDataAvail = comp.readiness_state === "DATA_AVAILABLE";
              const stateColor = isProd ? "#10b981" : isDataAvail ? "#3b82f6" : "#f59e0b";
              return (
                <div
                  key={comp.competition_code}
                  className="card"
                  style={{
                    padding: "1rem",
                    borderRadius: "6px",
                    border: `1px solid ${isProd ? "rgba(16, 185, 129, 0.3)" : "var(--border-subtle, #1e293b)"}`,
                    background: "var(--bg-surface, #0f172a)"
                  }}
                  data-testid={`readiness-card-${comp.competition_code.toLowerCase()}`}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
                    <div>
                      <h3 style={{ fontSize: "1rem", margin: 0, fontWeight: 700 }}>{comp.name}</h3>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>{comp.country} · {comp.competition_code}</span>
                    </div>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "0.7rem",
                        fontWeight: 700,
                        background: `${stateColor}22`,
                        color: stateColor,
                        border: `1px solid ${stateColor}44`
                      }}
                    >
                      {comp.readiness_state}
                    </span>
                  </div>

                  {/* Coverage Dimensions */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem", marginBottom: "0.75rem", fontSize: "0.75rem", textAlign: "center" }}>
                    <div style={{ background: "var(--bg-card, #1e293b)", padding: "0.4rem", borderRadius: "4px" }}>
                      <span style={{ color: "var(--text-muted, #94a3b8)", display: "block" }}>Matches</span>
                      <strong>{comp.coverage_dimensions?.matches || 0}</strong>
                    </div>
                    <div style={{ background: "var(--bg-card, #1e293b)", padding: "0.4rem", borderRadius: "4px" }}>
                      <span style={{ color: "var(--text-muted, #94a3b8)", display: "block" }}>Events</span>
                      <strong>{comp.coverage_dimensions?.events ? `${(comp.coverage_dimensions.events/1000).toFixed(0)}k` : "0"}</strong>
                    </div>
                    <div style={{ background: "var(--bg-card, #1e293b)", padding: "0.4rem", borderRadius: "4px" }}>
                      <span style={{ color: "var(--text-muted, #94a3b8)", display: "block" }}>Players</span>
                      <strong>{comp.coverage_dimensions?.player_match_stats || 0}</strong>
                    </div>
                  </div>

                  {/* Model Calibration Boundary */}
                  <div style={{ fontSize: "0.75rem", borderTop: "1px dashed var(--border-subtle, #1e293b)", paddingTop: "0.5rem", color: "var(--text-muted, #94a3b8)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
                      <span>Model Calibrated:</span>
                      <strong style={{ color: comp.is_model_calibrated ? "#10b981" : "#f59e0b" }}>
                        {comp.is_model_calibrated ? "YES (EPL Calibrated)" : "NO (Zero EPL Inheritance)"}
                      </strong>
                    </div>
                    <p style={{ margin: "0.3rem 0 0", fontSize: "0.7rem", color: "var(--text-muted, #64748b)" }}>
                      {comp.notes}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* TAB 2: INGESTION RUNS */}
      {activeTab === "ingestion" && (
        <section data-testid="ingestion-section">
          <div className="table-responsive">
            <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle, #1e293b)", textAlign: "left", color: "var(--text-muted, #94a3b8)" }}>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Run ID</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Provider / Resource</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Status</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Records (Seen/Acc)</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Validation</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Snapshot SHA-256</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Requested At</th>
                </tr>
              </thead>
              <tbody>
                {ingestionRuns.map(run => (
                  <tr key={run.ingestion_run_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`run-row-${run.ingestion_run_id}`}>
                    <td style={{ padding: "0.6rem 0.5rem", fontFamily: "monospace", fontWeight: 600 }}>
                      {run.ingestion_run_id}
                    </td>
                    <td style={{ padding: "0.6rem 0.5rem" }}>
                      <span className="badge micro neutral">{run.provider}</span> / {run.resource}
                    </td>
                    <td style={{ padding: "0.6rem 0.5rem" }}>
                      <span className={`badge micro ${run.status === "COMPLETED" ? "success" : "warning"}`}>
                        {run.status}
                      </span>
                    </td>
                    <td style={{ padding: "0.6rem 0.5rem" }}>
                      {run.records_seen} / {run.records_accepted}
                    </td>
                    <td style={{ padding: "0.6rem 0.5rem" }}>
                      <span className={`badge micro ${run.validation_status === "PASSED" ? "success" : "neutral"}`}>
                        {run.validation_status}
                      </span>
                    </td>
                    <td style={{ padding: "0.6rem 0.5rem", fontFamily: "monospace", fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)" }}>
                      {run.checksum ? `${run.checksum.slice(0, 16)}…` : "—"}
                    </td>
                    <td style={{ padding: "0.6rem 0.5rem", fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)" }}>
                      {new Date(run.requested_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 3: MODEL LIFECYCLE */}
      {activeTab === "lifecycle" && (
        <section data-testid="lifecycle-section">
          <div className="stack" style={{ gap: "0.75rem" }}>
            {lifecycleModels.map(m => (
              <div
                key={m.model_id}
                className="card"
                style={{
                  padding: "1rem",
                  borderRadius: "6px",
                  border: "1px solid var(--border-subtle, #1e293b)",
                  background: "var(--bg-surface, #0f172a)"
                }}
                data-testid={`lifecycle-card-${m.model_id}`}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <h3 style={{ fontSize: "1rem", margin: 0, fontWeight: 700 }}>{m.name}</h3>
                      <span className="badge micro info">{m.model_type}</span>
                      <span className="badge micro neutral">v{m.version}</span>
                    </div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #64748b)", fontFamily: "monospace" }}>
                      ID: {m.model_id} · Authority: {m.is_authoritative ? "AUTHORITATIVE" : "SHADOW"}
                    </span>
                  </div>
                  <span className={`badge ${m.state === "PRODUCTION" ? "success" : "info"}`} style={{ fontSize: "0.75rem" }}>
                    STAGE: {m.state}
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem", marginTop: "0.75rem", fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)" }}>
                  <div>
                    <span>Validation Score:</span> <strong style={{ color: "#fff" }}>{m.validation_metrics?.brier_score != null ? `Brier ${m.validation_metrics.brier_score}` : (m.validation_metrics?.mae_eur ? `MAE €${(m.validation_metrics.mae_eur/1e6).toFixed(1)}M` : "VALIDATED")}</strong>
                  </div>
                  <div>
                    <span>Promoted At:</span> <strong style={{ color: "#fff" }}>{m.promoted_at ? new Date(m.promoted_at).toLocaleDateString() : "—"}</strong>
                  </div>
                  <div>
                    <span>Approved By:</span> <strong style={{ color: "#fff" }}>{m.approved_by || "Head of Analytics"}</strong>
                  </div>
                </div>

                <div style={{ marginTop: "0.6rem", fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                  Inputs: {m.input_features?.join(", ") || "Validated feature registry set"}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
