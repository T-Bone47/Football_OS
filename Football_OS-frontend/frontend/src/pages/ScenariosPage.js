import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Beaker, GitFork, ArrowRight, ShieldCheck, AlertTriangle, CheckCircle2,
  DollarSign, TrendingUp, Users, Plus, RefreshCw, Layers, Sliders, ChevronRight
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // New scenario form
  const [newScenario, setNewScenario] = useState({
    name: "Scenario B: Retain Outgoing / Buy Inácio",
    scenario_type: "RETAIN_BUY",
    assumptions: [
      "Retain current midfield depth for UEFA Champions League competition",
      "Fund Inácio acquisition (€38M) through amortized credit reserve",
      "Wage delta of +€115,000/week absorbed by commercial headroom"
    ],
    movements: [
      {
        player_id: "p_goncalo_inacio",
        player_name: "Gonçalo Inácio",
        action: "BUY",
        fee_eur: 38000000,
        wage_eur_weekly: 115000,
        tactical_role: "Ball Playing Defender"
      }
    ]
  });

  useEffect(() => {
    fetchScenarios();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchScenarios = async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/phase10/scenarios`);
      setScenarios(res.data);
      if (res.data.length > 0) {
        setSelectedScenario(res.data[0]);
      }
    } catch (err) {
      console.error("Failed to load scenarios", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateScenario = async (e) => {
    e.preventDefault();
    try {
      const res = await axios.post(`${BACKEND_URL}/api/phase10/scenarios`, {
        project_id: "proj_cb_summer_2027",
        ...newScenario
      });
      setScenarios([...scenarios, res.data]);
      setSelectedScenario(res.data);
      setShowCreateModal(false);
    } catch (err) {
      console.error("Failed to create scenario", err);
    }
  };

  if (loading) {
    return (
      <main className="page-container" data-testid="scenarios-loading">
        <div className="empty-state">
          <p>Loading multi-alternative planning scenarios…</p>
        </div>
      </main>
    );
  }

  const res = selectedScenario?.results || {};
  const isUnsupported = res.match_prediction_impact?.status === "SCENARIO_UNSUPPORTED";

  return (
    <main className="page-container" data-testid="scenarios-page">
      {/* Header */}
      <header className="page-header" data-testid="scenarios-header">
        <div>
          <div className="eyebrow" data-testid="scenarios-eyebrow">
            PHASE 10 · MULTI-ALTERNATIVE SQUAD SIMULATION
          </div>
          <h1 data-testid="scenarios-title">Persistent Scenario Management</h1>
          <p className="page-subtitle">
            Simulate squad restructuring alternatives with strict separation of OBSERVED, MODELLED, and SCENARIO data.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="primary-button"
            onClick={() => setShowCreateModal(true)}
            data-testid="create-scenario-btn"
          >
            <Plus size={14} /> New Scenario Alternative
          </button>
        </div>
      </header>

      {/* Contract & Epistemic Separation Notice */}
      <section className="governance-card" style={{ marginBottom: "1.5rem" }} data-testid="scenario-contract-banner">
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
          <ShieldCheck size={20} color="var(--accent-teal, #14b8a6)" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Prediction Contract & Modality Discipline Active (§11, §12)
            </div>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", lineHeight: "1.4" }}>
              Predictions are generated only when modified squad inputs remain within calibrated bounds (&le; 5 net squad movements).
              If squad disruption exceeds the contract, the engine returns explicit <strong style={{ color: "#f59e0b" }}>SCENARIO_UNSUPPORTED</strong> rather than fabricating outputs.
            </p>
          </div>
        </div>
      </section>

      {/* Layout */}
      <div className="two-column-layout" style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "1.5rem" }}>
        {/* Left: Scenarios list */}
        <aside className="panel" data-testid="scenarios-list-panel">
          <span style={{ fontWeight: 600, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: "1rem" }}>
            Available Alternatives ({scenarios.length})
          </span>
          <div className="stack" style={{ gap: "0.6rem" }}>
            {scenarios.map(scen => {
              const isSelected = selectedScenario?.scenario_id === scen.scenario_id;
              return (
                <div
                  key={scen.scenario_id}
                  onClick={() => setSelectedScenario(scen)}
                  className={`clickable-card ${isSelected ? "selected" : ""}`}
                  style={{
                    padding: "0.85rem",
                    borderRadius: "6px",
                    border: isSelected ? "1px solid var(--accent-blue, #3b82f6)" : "1px solid var(--border-subtle, #1e293b)",
                    background: isSelected ? "rgba(59, 130, 246, 0.08)" : "var(--bg-surface, #0f172a)",
                    cursor: "pointer"
                  }}
                  data-testid={`scenario-card-${scen.scenario_id}`}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{scen.name}</span>
                    <ChevronRight size={14} color="var(--text-muted, #64748b)" />
                  </div>
                  <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.5rem" }}>
                    <span className="badge micro info" style={{ fontSize: "0.65rem" }}>{scen.scenario_type}</span>
                    <span className="badge micro neutral" style={{ fontSize: "0.65rem" }}>{scen.movements?.length || 0} moves</span>
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Right: Selected Scenario Detail */}
        <section className="panel" data-testid="scenario-detail-panel">
          {selectedScenario ? (
            <div>
              {/* Header Info */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem", borderBottom: "1px solid var(--border-subtle, #1e293b)", paddingBottom: "1rem" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.3rem" }}>
                    <h2 style={{ fontSize: "1.2rem", margin: 0 }}>{selectedScenario.name}</h2>
                    <span className="badge micro info">{selectedScenario.scenario_type}</span>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", fontFamily: "monospace" }}>
                    ID: {selectedScenario.scenario_id} · Project: {selectedScenario.project_id}
                  </span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span className={`badge ${isUnsupported ? "warning" : "success"}`} style={{ fontSize: "0.75rem" }}>
                    STATUS: {res.data_status || "MODELLED"}
                  </span>
                </div>
              </div>

              {/* Core Simulation Metrics Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1.5rem" }}>
                <div className="card" style={{ padding: "0.85rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Net Spend</span>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.25rem", color: res.net_transfer_spend_eur > 0 ? "#f87171" : "#4ade80" }}>
                    {res.net_transfer_spend_eur ? `€${(res.net_transfer_spend_eur / 1e6).toFixed(1)}M` : "€0.0M"}
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Capital Outlay</span>
                </div>

                <div className="card" style={{ padding: "0.85rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Weekly Wage Delta</span>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.25rem", color: res.wage_bill_delta_weekly > 0 ? "#f87171" : "#4ade80" }}>
                    {res.wage_bill_delta_weekly ? `${res.wage_bill_delta_weekly > 0 ? "+" : ""}€${Math.round(res.wage_bill_delta_weekly).toLocaleString()}/wk` : "€0"}
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Payroll Impact</span>
                </div>

                <div className="card" style={{ padding: "0.85rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Tactical Balance</span>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.25rem", color: "var(--accent-teal, #14b8a6)" }}>
                    {res.tactical_balance_delta ? `+${res.tactical_balance_delta.toFixed(1)}` : "+0.0"}
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Squad Cohesion</span>
                </div>

                <div className="card" style={{ padding: "0.85rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>Match Win Prob.</span>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.25rem", color: isUnsupported ? "#f59e0b" : "#60a5fa" }}>
                    {isUnsupported
                      ? "UNSUPPORTED"
                      : (res.match_prediction_impact?.win_probability_delta != null
                          ? `${(res.match_prediction_impact.win_probability_delta * 100).toFixed(1)}%`
                          : "N/A")}
                  </div>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>Logit Model v1</span>
                </div>
              </div>

              {/* If scenario unsupported warning */}
              {isUnsupported && (
                <div style={{ padding: "0.75rem", background: "rgba(245, 158, 11, 0.1)", border: "1px solid #f59e0b", borderRadius: "6px", marginBottom: "1.25rem", fontSize: "0.85rem" }}>
                  <strong style={{ color: "#f59e0b" }}>Contract Exceeded: SCENARIO_UNSUPPORTED</strong>
                  <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted, #d1d5db)" }}>
                    {res.match_prediction_impact?.reason || "Squad turnover exceeds validated calibration boundary for match outcome inference."}
                  </p>
                </div>
              )}

              {/* Roster Movements Table */}
              <div style={{ marginBottom: "1.5rem" }}>
                <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem", fontWeight: 600 }}>Planned Squad Movements</h3>
                <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle, #1e293b)", textAlign: "left", color: "var(--text-muted, #94a3b8)" }}>
                      <th style={{ padding: "0.5rem" }}>Player</th>
                      <th style={{ padding: "0.5rem" }}>Action</th>
                      <th style={{ padding: "0.5rem" }}>Role</th>
                      <th style={{ padding: "0.5rem" }}>Fee</th>
                      <th style={{ padding: "0.5rem" }}>Weekly Wage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedScenario.movements?.map((m, idx) => (
                      <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                        <td style={{ padding: "0.5rem", fontWeight: 600 }}>{m.player_name}</td>
                        <td style={{ padding: "0.5rem" }}>
                          <span className={`badge micro ${m.action === "BUY" ? "info" : m.action === "SELL" ? "warning" : "neutral"}`}>
                            {m.action}
                          </span>
                        </td>
                        <td style={{ padding: "0.5rem" }}>{m.tactical_role}</td>
                        <td style={{ padding: "0.5rem" }}>€{(m.fee_eur / 1e6).toFixed(1)}M</td>
                        <td style={{ padding: "0.5rem" }}>€{m.wage_eur_weekly?.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Modality Breakdown: OBSERVED vs MODELLED vs SCENARIO */}
              <div>
                <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem", fontWeight: 600 }}>
                  Epistemic Modality Separation (§11)
                </h3>
                <div className="stack" style={{ gap: "0.5rem" }}>
                  {res.evidence_nodes?.map((node, i) => {
                    const isObserved = node.startsWith("OBSERVED");
                    const isModelled = node.startsWith("MODELLED");
                    const isScenario = node.startsWith("SCENARIO");
                    return (
                      <div
                        key={i}
                        style={{
                          padding: "0.6rem 0.85rem",
                          borderRadius: "4px",
                          background: isObserved
                            ? "rgba(16, 185, 129, 0.08)"
                            : isModelled
                            ? "rgba(59, 130, 246, 0.08)"
                            : "rgba(168, 85, 247, 0.08)",
                          borderLeft: `3px solid ${
                            isObserved ? "#10b981" : isModelled ? "#3b82f6" : "#a855f7"
                          }`,
                          fontSize: "0.8rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem"
                        }}
                      >
                        <span style={{
                          fontWeight: 700,
                          fontSize: "0.7rem",
                          color: isObserved ? "#10b981" : isModelled ? "#3b82f6" : "#a855f7"
                        }}>
                          {isObserved ? "[OBSERVED]" : isModelled ? "[MODELLED]" : "[SCENARIO]"}
                        </span>
                        <span>{node.replace(/^(OBSERVED|MODELLED|SCENARIO):\s*/, "")}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <p>Select a scenario to view simulation analysis.</p>
            </div>
          )}
        </section>
      </div>

      {/* New Scenario Modal */}
      {showCreateModal && (
        <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div className="modal-card" style={{ background: "var(--bg-surface, #0f172a)", padding: "1.5rem", borderRadius: "8px", maxWidth: "550px", width: "100%", border: "1px solid var(--border-subtle, #334155)" }}>
            <h2 style={{ fontSize: "1.1rem", marginBottom: "1rem" }}>Create New Scenario Alternative</h2>
            <form onSubmit={handleCreateScenario} className="form-stack" style={{ display: "grid", gap: "0.75rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                  Scenario Title
                </label>
                <input
                  type="text"
                  value={newScenario.name}
                  onChange={e => setNewScenario({ ...newScenario, name: e.target.value })}
                  className="input-field"
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                  Alternative Type
                </label>
                <select
                  value={newScenario.scenario_type}
                  onChange={e => setNewScenario({ ...newScenario, scenario_type: e.target.value })}
                  className="input-field"
                >
                  <option value="SELL_BUY">SELL_BUY (Sell X / Buy Y)</option>
                  <option value="RETAIN_BUY">RETAIN_BUY (Retain X / Buy Y)</option>
                  <option value="SELL_ACADEMY">SELL_ACADEMY (Sell X / Promote Academy)</option>
                </select>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1rem" }}>
                <button type="button" className="secondary-button" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="primary-button">
                  Simulate & Save Alternative
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
