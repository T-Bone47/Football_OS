import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Globe, ShieldCheck, Activity, Database, GitBranch, Play, RefreshCw,
  AlertTriangle, CheckCircle2, ChevronRight, BarChart2, Eye, Server,
  Clock, ShieldAlert, Cpu, FileText, ArrowUpRight, ArrowDownRight, Layers
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

export default function GlobalOperationsPage() {
  const [activeTab, setActiveTab] = useState("coverage"); // "coverage", "calibration", "datasets", "shadow", "drift", "report"
  const [coverageList, setCoverageList] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [lineageInfo, setLineageInfo] = useState(null);
  const [driftSnapshots, setDriftSnapshots] = useState([]);
  const [driftAlerts, setDriftAlerts] = useState([]);
  const [shadowRecords, setShadowRecords] = useState([]);
  const [shadowSummary, setShadowSummary] = useState(null);
  const [validationReport, setValidationReport] = useState(null);
  const [loading, setLoading] = useState(true);

  // Calibration state
  const [calibComp, setCalibComp] = useState("LALIGA");
  const [calibMethod, setCalibMethod] = useState("TEMPERATURE_SCALING");
  const [calibResult, setCalibResult] = useState(null);
  const [calibrating, setCalibrating] = useState(false);

  // Shadow test state
  const [shadowRunning, setShadowRunning] = useState(false);
  const [shadowInferenceResult, setShadowInferenceResult] = useState(null);

  useEffect(() => {
    fetchGlobalData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchGlobalData = async () => {
    try {
      const [covRes, dsRes, driftRes, alertsRes, shadowRecs, shadowSum] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/phase11/competitions/coverage`),
        axios.get(`${BACKEND_URL}/api/phase11/datasets`),
        axios.get(`${BACKEND_URL}/api/phase11/competitions/EPL/drift`),
        axios.get(`${BACKEND_URL}/api/phase11/drift/alerts`),
        axios.get(`${BACKEND_URL}/api/phase11/models/shadow/records`),
        axios.get(`${BACKEND_URL}/api/phase11/models/calibrated_multinomial_logit_v1/shadow/summary`),
      ]);
      setCoverageList(covRes.data);
      setDatasets(dsRes.data);
      if (dsRes.data.length > 0) {
        setSelectedDataset(dsRes.data[0]);
      }
      setDriftSnapshots(driftRes.data);
      setDriftAlerts(alertsRes.data);
      setShadowRecords(shadowRecs.data);
      setShadowSummary(shadowSum.data);
    } catch (err) {
      console.error("Failed to load Phase 11 global data", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunCalibration = async () => {
    setCalibrating(true);
    try {
      const res = await axios.post(`${BACKEND_URL}/api/phase11/competitions/${calibComp}/calibrate`, {
        method: calibMethod,
        validation_window: "2024-01-16 to 2024-03-31"
      });
      setCalibResult(res.data);
    } catch (err) {
      console.error("Calibration failed", err);
    } finally {
      setCalibrating(false);
    }
  };

  const handleTestShadowInference = async () => {
    setShadowRunning(true);
    try {
      const res = await axios.post(`${BACKEND_URL}/api/phase11/models/calibrated_multinomial_logit_v1/shadow/inference`, {
        entity_id: "match_laliga_test_01",
        competition: "LALIGA",
        input_features: { home_elo: 1680, away_elo: 1610, home_advantage: 65, goal_ratio: 1.25 }
      });
      setShadowInferenceResult(res.data);
      // Refresh shadow records and summary
      const [recs, sum] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/phase11/models/shadow/records`),
        axios.get(`${BACKEND_URL}/api/phase11/models/calibrated_multinomial_logit_v1/shadow/summary`),
      ]);
      setShadowRecords(recs.data);
      setShadowSummary(sum.data);
    } catch (err) {
      console.error("Shadow inference test failed", err);
    } finally {
      setShadowRunning(false);
    }
  };

  const handleInspectLineage = async (datasetId) => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/phase11/datasets/${datasetId}/lineage`);
      setLineageInfo(res.data);
    } catch (err) {
      console.error("Lineage check failed", err);
    }
  };

  const handleLoadReport = async (compId) => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/phase11/reports/cross-competition/${compId}`);
      setValidationReport(res.data);
      setActiveTab("report");
    } catch (err) {
      console.error("Failed to load validation report", err);
    }
  };

  if (loading) {
    return (
      <main className="page-container" data-testid="global-ops-loading">
        <div className="empty-state">
          <Clock className="spin" size={24} />
          <p>Loading Phase 11 global operations & cross-competition validation…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="page-container" data-testid="global-operations-page">
      {/* Header */}
      <header className="page-header" data-testid="global-ops-header">
        <div>
          <div className="eyebrow" data-testid="global-ops-eyebrow">
            PHASE 11 · GLOBAL INTELLIGENCE OPERATIONS
          </div>
          <h1 data-testid="global-ops-title">Cross-Competition Calibration & Governance</h1>
          <p className="page-subtitle">
            Tier 1-3 coverage matrix, zero-inheritance probability calibration, immutable dataset registry, and shadow execution.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="secondary-button"
            onClick={fetchGlobalData}
            data-testid="refresh-global-btn"
          >
            <RefreshCw size={14} /> Refresh Operations
          </button>
        </div>
      </header>

      {/* Epistemic Zero-Inheritance Notice */}
      <section className="governance-card" style={{ marginBottom: "1.5rem" }} data-testid="zero-inheritance-banner">
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
          <ShieldCheck size={20} color="var(--accent-teal, #14b8a6)" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Strict Zero-Inheritance & Non-Pooling Policy Active (§2, §5)
            </div>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", lineHeight: "1.4" }}>
              EPL model validity is never inherited by non-EPL competitions. Each competition independently establishes
              its own temporal dataset splits, calibration curves, Brier scores, and drift baselines. Competitions advance through
              governed stages (DATA_INGESTED &rarr; DATA_VALIDATED &rarr; FEATURE_READY &rarr; VALIDATION_READY &rarr; MODEL_VALIDATED &rarr; PRODUCTION_READY).
            </p>
          </div>
        </div>
      </section>

      {/* Tabs */}
      <div className="tab-bar" style={{ display: "flex", gap: "1rem", borderBottom: "1px solid var(--border-subtle, #1e293b)", paddingBottom: "0.5rem", marginBottom: "1.5rem", overflowX: "auto" }}>
        <button
          className={`tab-button ${activeTab === "coverage" ? "active" : ""}`}
          onClick={() => setActiveTab("coverage")}
          data-testid="tab-coverage"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "coverage" ? "#fff" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "coverage" ? "2px solid #3b82f6" : "none" }}
        >
          Coverage & Readiness ({coverageList.length})
        </button>
        <button
          className={`tab-button ${activeTab === "calibration" ? "active" : ""}`}
          onClick={() => setActiveTab("calibration")}
          data-testid="tab-calibration"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "calibration" ? "#fff" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "calibration" ? "2px solid #3b82f6" : "none" }}
        >
          Probability Calibration & Reliability Curves
        </button>
        <button
          className={`tab-button ${activeTab === "datasets" ? "active" : ""}`}
          onClick={() => setActiveTab("datasets")}
          data-testid="tab-datasets"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "datasets" ? "#fff" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "datasets" ? "2px solid #3b82f6" : "none" }}
        >
          Immutable Dataset Registry & Lineage ({datasets.length})
        </button>
        <button
          className={`tab-button ${activeTab === "shadow" ? "active" : ""}`}
          onClick={() => setActiveTab("shadow")}
          data-testid="tab-shadow"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "shadow" ? "#fff" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "shadow" ? "2px solid #3b82f6" : "none" }}
        >
          Model Shadow Mode
        </button>
        <button
          className={`tab-button ${activeTab === "drift" ? "active" : ""}`}
          onClick={() => setActiveTab("drift")}
          data-testid="tab-drift"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "drift" ? "#fff" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "drift" ? "2px solid #3b82f6" : "none" }}
        >
          Drift Telemetry & Alerts ({driftAlerts.length})
        </button>
        <button
          className={`tab-button ${activeTab === "report" ? "active" : ""}`}
          onClick={() => setActiveTab("report")}
          data-testid="tab-report"
          style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "report" ? "#fff" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "report" ? "2px solid #3b82f6" : "none" }}
        >
          Validation Dossier (16-Section)
        </button>
      </div>

      {/* TAB 1: GLOBAL COVERAGE & READINESS MATRIX */}
      {activeTab === "coverage" && (
        <section data-testid="coverage-section">
          <div className="table-responsive">
            <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle, #1e293b)", textAlign: "left", color: "var(--text-muted, #94a3b8)" }}>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Competition</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Tier</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Readiness State</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Matches</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Events</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Player Stats</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Calibration Status</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Gate Pass Rate</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {coverageList.map(comp => {
                  const isProd = comp.readiness_state === "PRODUCTION_READY";
                  const isModelVal = comp.readiness_state === "MODEL_VALIDATED";
                  const isValReady = comp.readiness_state === "VALIDATION_READY";
                  const stateColor = isProd ? "#10b981" : isModelVal ? "#3b82f6" : isValReady ? "#a855f7" : "#f59e0b";

                  return (
                    <tr key={comp.competition_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`cov-row-${comp.competition_id.toLowerCase()}`}>
                      <td style={{ padding: "0.6rem 0.5rem" }}>
                        <strong>{comp.competition_name}</strong>
                        <span style={{ display: "block", fontSize: "0.7rem", color: "var(--text-muted, #64748b)" }}>{comp.country} · {comp.competition_id}</span>
                      </td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>
                        <span className="badge micro neutral">{comp.tier}</span>
                      </td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>
                        <span style={{ padding: "2px 6px", borderRadius: "4px", fontSize: "0.7rem", fontWeight: 700, background: `${stateColor}22`, color: stateColor, border: `1px solid ${stateColor}44` }}>
                          {comp.readiness_state}
                        </span>
                      </td>
                      <td style={{ padding: "0.6rem 0.5rem", fontWeight: 600 }}>{comp.matches_available}</td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>{comp.events_available ? `${(comp.events_available / 1000).toFixed(0)}k` : "0"}</td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>{comp.player_stats_available?.toLocaleString()}</td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>
                        <span className={`badge micro ${comp.calibration_status === "CALIBRATED" ? "success" : "neutral"}`}>
                          {comp.calibration_status}
                        </span>
                      </td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>{(comp.validation_rate * 100).toFixed(1)}%</td>
                      <td style={{ padding: "0.6rem 0.5rem" }}>
                        <button
                          className="secondary-button"
                          style={{ padding: "2px 8px", fontSize: "0.75rem" }}
                          onClick={() => handleLoadReport(comp.competition_id)}
                          data-testid={`inspect-btn-${comp.competition_id.toLowerCase()}`}
                        >
                          Dossier
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 2: PROBABILITY CALIBRATION */}
      {activeTab === "calibration" && (
        <section data-testid="calibration-section">
          <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "1.5rem" }}>
            {/* Calibration Form */}
            <div className="panel" style={{ padding: "1rem" }}>
              <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem", fontWeight: 700 }}>Run Independent Calibration</h3>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", marginBottom: "1rem" }}>
                Fit probability calibration parameters learned strictly on the target competition validation split.
              </p>
              <div className="stack" style={{ gap: "0.75rem" }}>
                <div>
                  <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                    Target Competition
                  </label>
                  <select
                    className="input-field"
                    value={calibComp}
                    onChange={e => setCalibComp(e.target.value)}
                  >
                    <option value="LALIGA">La Liga (Spain - Tier 1)</option>
                    <option value="SERIEA">Serie A (Italy - Tier 1)</option>
                    <option value="BUNDESLIGA">Bundesliga (Germany - Tier 1)</option>
                    <option value="LIGUE1">Ligue 1 (France - Tier 1)</option>
                    <option value="EPL">Premier League (England - Baseline)</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                    Calibration Method
                  </label>
                  <select
                    className="input-field"
                    value={calibMethod}
                    onChange={e => setCalibMethod(e.target.value)}
                  >
                    <option value="TEMPERATURE_SCALING">Temperature Scaling (Optimal Logit Divider)</option>
                    <option value="ISOTONIC_REGRESSION">Isotonic Regression (Monotonic Step)</option>
                    <option value="RAW">Raw Baseline (Uncalibrated)</option>
                  </select>
                </div>

                <button
                  className="primary-button"
                  onClick={handleRunCalibration}
                  disabled={calibrating}
                  style={{ marginTop: "0.5rem" }}
                  data-testid="execute-calibration-btn"
                >
                  <Play size={14} /> {calibrating ? "Optimizing Parameter on Val Split…" : "Fit & Evaluate Calibration"}
                </button>
              </div>
            </div>

            {/* Calibration Evaluation Results */}
            <div className="panel" style={{ padding: "1rem" }} data-testid="calibration-results-panel">
              <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem", fontWeight: 700 }}>
                Calibration Evaluation: {calibComp}
              </h3>
              {calibResult ? (
                <div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.75rem", marginBottom: "1rem" }}>
                    <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "4px" }}>
                      <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>ECE Reduction</span>
                      <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.2rem", color: "#10b981" }}>
                        {calibResult.ece_reduction > 0 ? `-${calibResult.ece_reduction}` : calibResult.ece_reduction}
                      </div>
                      <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>
                        {calibResult.metrics_before?.ece} &rarr; {calibResult.metrics_after?.ece}
                      </span>
                    </div>

                    <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "4px" }}>
                      <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Learned Param</span>
                      <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.2rem", color: "#3b82f6" }}>
                        T = {calibResult.parameters?.temperature || "1.00"}
                      </div>
                      <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>
                        Validation Split Only
                      </span>
                    </div>

                    <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "4px" }}>
                      <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Log Loss</span>
                      <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.2rem", color: "#60a5fa" }}>
                        {calibResult.metrics_after?.log_loss}
                      </div>
                      <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>
                        Baseline: {calibResult.metrics_before?.log_loss}
                      </span>
                    </div>
                  </div>

                  {/* 10-Bin Reliability Diagram */}
                  <div>
                    <h4 style={{ fontSize: "0.85rem", marginBottom: "0.5rem", fontWeight: 600 }}>10-Bin Reliability Curve</h4>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: "4px", background: "var(--bg-surface, #0f172a)", padding: "0.75rem", borderRadius: "6px" }}>
                      {calibResult.reliability_bins?.map(b => {
                        const gap = Math.abs(b.predicted_prob_mean - b.empirical_frequency);
                        const isClose = gap < 0.05;
                        return (
                          <div key={b.bin_index} style={{ textAlign: "center", fontSize: "0.65rem" }}>
                            <div style={{ height: "60px", display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
                              <div
                                style={{
                                  width: "14px",
                                  height: `${Math.max(10, b.predicted_prob_mean * 60)}px`,
                                  background: isClose ? "#10b981" : "#f59e0b",
                                  borderRadius: "2px"
                                }}
                              />
                            </div>
                            <span style={{ display: "block", marginTop: "4px", color: "var(--text-muted, #94a3b8)" }}>
                              {(b.bin_upper * 100).toFixed(0)}%
                            </span>
                            <span style={{ fontSize: "0.6rem", color: "#64748b" }}>n={b.sample_count}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-state" style={{ padding: "2rem" }}>
                  <p style={{ color: "var(--text-muted, #94a3b8)", fontSize: "0.85rem" }}>
                    Select a competition and click "Fit & Evaluate Calibration" to inspect the probability reliability curve.
                  </p>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* TAB 3: IMMUTABLE DATASET REGISTRY */}
      {activeTab === "datasets" && (
        <section data-testid="datasets-section">
          <div style={{ display: "grid", gridTemplateColumns: "350px 1fr", gap: "1.5rem" }}>
            <div className="stack" style={{ gap: "0.6rem" }}>
              <span style={{ fontWeight: 600, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Registered Datasets ({datasets.length})
              </span>
              {datasets.map(ds => {
                const isSelected = selectedDataset?.dataset_id === ds.dataset_id;
                return (
                  <div
                    key={ds.dataset_id}
                    onClick={() => { setSelectedDataset(ds); setLineageInfo(null); }}
                    className={`clickable-card ${isSelected ? "selected" : ""}`}
                    style={{
                      padding: "0.75rem",
                      borderRadius: "6px",
                      border: isSelected ? "1px solid #3b82f6" : "1px solid var(--border-subtle, #1e293b)",
                      background: isSelected ? "rgba(59, 130, 246, 0.08)" : "var(--bg-surface, #0f172a)",
                      cursor: "pointer"
                    }}
                    data-testid={`dataset-card-${ds.dataset_id}`}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <strong style={{ fontSize: "0.85rem" }}>{ds.dataset_id}</strong>
                      <span className="badge micro neutral">v{ds.dataset_version}</span>
                    </div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginTop: "2px" }}>
                      {ds.competition_scope} · {ds.row_count} rows
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Selected Dataset Detail */}
            <div className="panel" style={{ padding: "1rem" }} data-testid="dataset-detail-panel">
              {selectedDataset && (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem", borderBottom: "1px solid var(--border-subtle, #1e293b)", paddingBottom: "0.75rem" }}>
                    <div>
                      <h3 style={{ fontSize: "1.1rem", margin: 0 }}>{selectedDataset.dataset_id}</h3>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #64748b)", fontFamily: "monospace" }}>
                        Version {selectedDataset.dataset_version} · Created: {new Date(selectedDataset.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <button
                      className="primary-button"
                      style={{ fontSize: "0.75rem", padding: "4px 10px" }}
                      onClick={() => handleInspectLineage(selectedDataset.dataset_id)}
                      data-testid="verify-lineage-btn"
                    >
                      <ShieldCheck size={14} /> Verify Full Lineage
                    </button>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", fontSize: "0.8rem", marginBottom: "1rem" }}>
                    <div><span>Competition Scope:</span> <strong style={{ color: "#fff" }}>{selectedDataset.competition_scope}</strong></div>
                    <div><span>Season Scope:</span> <strong style={{ color: "#fff" }}>{selectedDataset.season_scope}</strong></div>
                    <div><span>Row Count:</span> <strong style={{ color: "#fff" }}>{selectedDataset.row_count}</strong></div>
                    <div><span>Feature Set:</span> <strong style={{ color: "#fff" }}>{selectedDataset.feature_set_version}</strong></div>
                  </div>

                  <div style={{ marginBottom: "1rem" }}>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                      Cryptographic SHA-256 Checksum:
                    </span>
                    <span style={{ fontFamily: "monospace", fontSize: "0.8rem", background: "rgba(255,255,255,0.03)", padding: "4px 8px", borderRadius: "4px", display: "block" }}>
                      {selectedDataset.checksum}
                    </span>
                  </div>

                  {lineageInfo && (
                    <div style={{ marginTop: "1rem", padding: "0.85rem", background: "rgba(16, 185, 129, 0.08)", border: "1px solid #10b981", borderRadius: "6px" }} data-testid="lineage-result-banner">
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "#10b981", fontWeight: 700, fontSize: "0.85rem" }}>
                        <CheckCircle2 size={16} /> End-to-End Lineage Verified (§20)
                      </div>
                      <p style={{ margin: "0.4rem 0 0", fontSize: "0.75rem", color: "#fff", fontFamily: "monospace" }}>
                        {lineageInfo.lineage?.lineage_path}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* TAB 4: MODEL SHADOW MODE */}
      {activeTab === "shadow" && (
        <section data-testid="shadow-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <h3 style={{ fontSize: "1rem", margin: 0, fontWeight: 700 }}>Active Shadow Model Cohorts (§18)</h3>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", margin: "0.2rem 0 0" }}>
                Candidate models execute in parallel on identical inputs without influencing authoritative production decisions.
              </p>
            </div>
            <button
              className="primary-button"
              onClick={handleTestShadowInference}
              disabled={shadowRunning}
              data-testid="test-shadow-inference-btn"
            >
              <Cpu size={14} /> {shadowRunning ? "Executing Dual Inference…" : "Run Dual Shadow Inference Test"}
            </button>
          </div>

          {shadowSummary && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1.5rem" }}>
              <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Evaluations</span>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.2rem", color: "#fff" }}>
                  {shadowSummary.total_evaluations}
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Cohort Size</span>
              </div>

              <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Mean Divergence</span>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.2rem", color: shadowSummary.mean_divergence < 0.10 ? "#10b981" : "#f59e0b" }}>
                  {shadowSummary.mean_divergence}
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>L1 Probability Delta</span>
              </div>

              <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Candidate Latency</span>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.2rem", color: "#60a5fa" }}>
                  {shadowSummary.shadow_mean_latency_ms}ms
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Prod: {shadowSummary.production_mean_latency_ms}ms</span>
              </div>

              <div className="card" style={{ padding: "0.75rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Recommendation</span>
                <div style={{ fontSize: "0.95rem", fontWeight: 700, marginTop: "0.3rem", color: "#10b981" }}>
                  {shadowSummary.recommendation}
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Promotion Gate</span>
              </div>
            </div>
          )}

          {/* Recent Shadow Executions Table */}
          <div className="table-responsive">
            <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle, #1e293b)", textAlign: "left", color: "var(--text-muted, #94a3b8)" }}>
                  <th style={{ padding: "0.5rem" }}>Execution ID</th>
                  <th style={{ padding: "0.5rem" }}>Entity / Match</th>
                  <th style={{ padding: "0.5rem" }}>Competition</th>
                  <th style={{ padding: "0.5rem" }}>L1 Divergence</th>
                  <th style={{ padding: "0.5rem" }}>Prod Latency</th>
                  <th style={{ padding: "0.5rem" }}>Shadow Latency</th>
                  <th style={{ padding: "0.5rem" }}>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {shadowRecords.map(r => (
                  <tr key={r.execution_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`shadow-row-${r.execution_id}`}>
                    <td style={{ padding: "0.5rem", fontFamily: "monospace" }}>{r.execution_id}</td>
                    <td style={{ padding: "0.5rem" }}>{r.entity_id}</td>
                    <td style={{ padding: "0.5rem" }}><span className="badge micro neutral">{r.competition}</span></td>
                    <td style={{ padding: "0.5rem", fontWeight: 600, color: r.output_divergence < 0.10 ? "#10b981" : "#f59e0b" }}>
                      {r.output_divergence}
                    </td>
                    <td style={{ padding: "0.5rem" }}>{r.production_latency_ms}ms</td>
                    <td style={{ padding: "0.5rem" }}>{r.shadow_latency_ms}ms</td>
                    <td style={{ padding: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)" }}>
                      {new Date(r.timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* TAB 5: DRIFT TELEMETRY & ALERTS */}
      {activeTab === "drift" && (
        <section data-testid="drift-section">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
            {/* Drift Snapshots */}
            <div className="panel" style={{ padding: "1rem" }}>
              <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem", fontWeight: 700 }}>Population Stability (PSI) Baselines</h3>
              <div className="stack" style={{ gap: "0.6rem" }}>
                {driftSnapshots.map((s, idx) => (
                  <div key={idx} className="card" style={{ padding: "0.85rem", background: "var(--bg-surface, #0f172a)", borderRadius: "6px", border: "1px solid var(--border-subtle, #1e293b)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <strong>{s.competition} · {s.season}</strong>
                      <span className="badge micro success">{s.drift_status}</span>
                    </div>
                    <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--text-bright, #fff)" }}>
                      <span>Overall PSI: <strong>{s.overall_psi}</strong></span>
                      <span>Brier Drift: <strong>{s.brier_drift > 0 ? `+${s.brier_drift}` : s.brier_drift}</strong></span>
                      <span>Log Loss Drift: <strong>{s.log_loss_drift > 0 ? `+${s.log_loss_drift}` : s.log_loss_drift}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Factual Operational Alerts */}
            <div className="panel" style={{ padding: "1rem" }}>
              <h3 style={{ fontSize: "0.95rem", marginBottom: "0.75rem", fontWeight: 700 }}>
                Operational Alerts ({driftAlerts.length})
              </h3>
              {driftAlerts.length === 0 ? (
                <div className="empty-state" style={{ padding: "2rem" }}>
                  <CheckCircle2 size={24} color="#10b981" style={{ margin: "0 auto 0.5rem" }} />
                  <p style={{ color: "var(--text-muted, #94a3b8)", fontSize: "0.85rem" }}>
                    All competitions operating within normal PSI and calibration bounds.
                  </p>
                </div>
              ) : (
                <div className="stack" style={{ gap: "0.6rem" }}>
                  {driftAlerts.map(a => (
                    <div key={a.alert_id} className="card" style={{ padding: "0.85rem", background: "rgba(245, 158, 11, 0.08)", border: "1px solid #f59e0b", borderRadius: "6px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <strong style={{ color: "#f59e0b", fontSize: "0.85rem" }}>{a.category}</strong>
                        <span className="badge micro warning">{a.severity}</span>
                      </div>
                      <p style={{ fontSize: "0.8rem", margin: "0.3rem 0", color: "#fff" }}>{a.headline}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* TAB 6: 16-SECTION CROSS-COMPETITION REPORT */}
      {activeTab === "report" && (
        <section data-testid="report-section">
          {validationReport ? (
            <div className="panel" style={{ padding: "1.5rem", maxWidth: "900px", margin: "0 auto" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem", borderBottom: "1px solid var(--border-subtle, #1e293b)", paddingBottom: "1rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.2rem", margin: 0 }}>{validationReport.title}</h2>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                    Report ID: {validationReport.report_id} · Generated: {new Date(validationReport.generated_at).toLocaleString()}
                  </span>
                </div>
                <span className="badge success" style={{ fontSize: "0.8rem" }}>
                  STATE: {validationReport.summary_metrics?.readiness_state}
                </span>
              </div>

              {/* Render Section Cards */}
              <div className="stack" style={{ gap: "1rem" }}>
                {Object.entries(validationReport.sections).map(([secKey, secContent]) => (
                  <div key={secKey} className="card" style={{ padding: "1rem", background: "var(--bg-surface, #0f172a)", borderRadius: "6px", border: "1px solid var(--border-subtle, #1e293b)" }}>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "#60a5fa", marginBottom: "0.5rem" }}>
                      {secKey.replace(/^\d+_/, "").replaceAll("_", " ")}
                    </h3>
                    <pre style={{ fontSize: "0.75rem", color: "var(--text-muted, #d1d5db)", background: "rgba(0,0,0,0.3)", padding: "0.75rem", borderRadius: "4px", overflowX: "auto", fontFamily: "monospace" }}>
                      {JSON.stringify(secContent, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-state" style={{ padding: "2rem" }}>
              <FileText size={24} color="#64748b" style={{ margin: "0 auto 0.5rem" }} />
              <p style={{ color: "var(--text-muted, #94a3b8)", fontSize: "0.85rem" }}>
                Select a competition from the Coverage table to view its full 16-section validation dossier.
              </p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
