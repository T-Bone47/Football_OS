import React, { useState, useEffect } from "react";
import axios from "axios";
import { ShieldCheck, AlertTriangle, Plus, ChevronRight } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

const EMPTY_FORM = {
  project_id: "",
  name: "",
  scenario_type: "SELL_BUY",
  movement: { player_id: "", player_name: "", action: "BUY", fee_eur: "", wage_eur_weekly: "" },
};

const numberOrNull = (v) => (v === "" || v === null || v === undefined ? null : Number(v));
const millions = (v) => (v == null ? "n/a" : `€${(v / 1e6).toFixed(1)}M`);
const euros = (v) => (v == null ? "n/a" : `${v > 0 ? "+" : ""}€${Math.round(v).toLocaleString()}`);

// Evidence lines are prefixed by the server with how each figure arose.
const EVIDENCE_TONE = { SUPPLIED: "#a855f7", COMPUTED: "#10b981", UNKNOWN: "#f59e0b", NOT_MODELLED: "#94a3b8" };

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState([]);
  const [projects, setProjects] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadAll = async () => {
    try {
      const [scenRes, projRes] = await Promise.all([
        axios.get(`${BACKEND_URL}/api/phase10/scenarios`),
        axios.get(`${BACKEND_URL}/api/phase10/recruitment/projects`),
      ]);
      setScenarios(scenRes.data);
      setProjects(projRes.data);
      if (scenRes.data.length > 0) setSelectedScenario(scenRes.data[0]);
    } catch (err) {
      console.error("Failed to load scenarios", err);
      setLoadError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateScenario = async (e) => {
    e.preventDefault();
    setCreateError(null);
    const m = form.movement;
    try {
      const res = await axios.post(`${BACKEND_URL}/api/phase10/scenarios`, {
        project_id: form.project_id,
        name: form.name,
        scenario_type: form.scenario_type,
        movements: [
          {
            player_id: m.player_id,
            player_name: m.player_name,
            action: m.action,
            fee_eur: numberOrNull(m.fee_eur),
            wage_eur_weekly: numberOrNull(m.wage_eur_weekly),
          },
        ],
      });
      setScenarios([...scenarios, res.data]);
      setSelectedScenario(res.data);
      setShowCreateModal(false);
      setForm(EMPTY_FORM);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setCreateError(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : err.message);
    }
  };

  if (loading) {
    return (
      <main className="page-container" data-testid="scenarios-loading">
        <div className="empty-state">
          <p>Loading planning scenarios…</p>
        </div>
      </main>
    );
  }

  const res = selectedScenario?.results || {};
  const field = { fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" };
  const setMovement = (patch) => setForm({ ...form, movement: { ...form.movement, ...patch } });

  return (
    <main className="page-container" data-testid="scenarios-page">
      <header className="page-header" data-testid="scenarios-header">
        <div>
          <div className="eyebrow" data-testid="scenarios-eyebrow">PHASE 10 · PLANNING SCENARIOS</div>
          <h1 data-testid="scenarios-title">Planning Scenarios</h1>
          <p className="page-subtitle">
            Arithmetic on the fees and wages you enter. Squad and match impact are not modelled.
          </p>
        </div>
        <div className="header-actions">
          <button className="primary-button" onClick={() => setShowCreateModal(true)} data-testid="create-scenario-btn">
            <Plus size={14} /> New Scenario Alternative
          </button>
        </div>
      </header>

      <section className="governance-card" style={{ marginBottom: "1.5rem" }} data-testid="scenario-contract-banner">
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
          <ShieldCheck size={20} color="var(--accent-teal, #14b8a6)" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              No forecast is produced
            </div>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", lineHeight: "1.4" }}>
              No validated match-prediction model exists, so squad rating, tactical balance, league points and win
              probability are shown as <strong>not modelled</strong>. Unknown fees or wages make the totals{" "}
              <strong>n/a</strong>, never zero.
            </p>
          </div>
        </div>
      </section>

      {loadError && (
        <section className="result-card" style={{ marginBottom: "1rem", padding: "0.75rem", border: "1px solid #ef4444", borderRadius: "6px" }} data-testid="scenarios-load-error">
          <AlertTriangle size={16} color="#ef4444" /> <strong style={{ color: "#ef4444" }}>Could not load scenarios: {loadError}</strong>
        </section>
      )}

      <div className="two-column-layout" style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "1.5rem" }}>
        <aside className="panel" data-testid="scenarios-list-panel">
          <span style={{ fontWeight: 600, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: "1rem" }}>
            Available Alternatives ({scenarios.length})
          </span>
          <div className="stack" style={{ gap: "0.6rem" }}>
            {scenarios.map((scen) => {
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
                    cursor: "pointer",
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
            {scenarios.length === 0 && (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)" }} data-testid="scenarios-empty">
                No scenarios yet. Create one against one of your recruitment projects.
              </p>
            )}
          </div>
        </aside>

        <section className="panel" data-testid="scenario-detail-panel">
          {selectedScenario ? (
            <div>
              <div style={{ marginBottom: "1.25rem" }}>
                <h2 style={{ fontSize: "1.2rem", margin: 0 }}>{selectedScenario.name}</h2>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", fontFamily: "monospace" }}>
                  ID: {selectedScenario.scenario_id} · Project: {selectedScenario.project_id} · Status: {res.data_status}
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", marginBottom: "1.5rem" }}>
                {[
                  ["Net Spend", millions(res.net_transfer_spend_eur), "Sum of entered fees"],
                  ["Weekly Wage Delta", euros(res.wage_bill_delta_weekly), "Sum of entered wages"],
                  ["Tactical Balance", res.tactical_balance_delta == null ? "not modelled" : res.tactical_balance_delta.toFixed(1), "No validated model"],
                  ["Match Win Prob.", res.match_prediction_impact?.status === "NOT_MODELLED" ? "not modelled" : "n/a", "No validated model"],
                ].map(([label, value, note]) => (
                  <div key={label} className="card" style={{ padding: "0.85rem", background: "var(--bg-card, #1e293b)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase" }}>{label}</span>
                    <div style={{ fontSize: "1.1rem", fontWeight: 700, marginTop: "0.25rem" }}>{value}</div>
                    <span style={{ fontSize: "0.65rem", color: "var(--text-muted, #64748b)" }}>{note}</span>
                  </div>
                ))}
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem", fontWeight: 600 }}>Planned Squad Movements</h3>
                <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle, #1e293b)", textAlign: "left", color: "var(--text-muted, #94a3b8)" }}>
                      <th style={{ padding: "0.5rem" }}>Player</th>
                      <th style={{ padding: "0.5rem" }}>Action</th>
                      <th style={{ padding: "0.5rem" }}>Fee</th>
                      <th style={{ padding: "0.5rem" }}>Weekly Wage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedScenario.movements?.map((m, idx) => (
                      <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                        <td style={{ padding: "0.5rem", fontWeight: 600 }}>{m.player_name}</td>
                        <td style={{ padding: "0.5rem" }}>{m.action}</td>
                        <td style={{ padding: "0.5rem" }}>{millions(m.fee_eur)}</td>
                        <td style={{ padding: "0.5rem" }}>{m.wage_eur_weekly == null ? "n/a" : `€${m.wage_eur_weekly.toLocaleString()}`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div>
                <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem", fontWeight: 600 }}>How each figure arose</h3>
                <div className="stack" style={{ gap: "0.5rem" }}>
                  {res.evidence_nodes?.map((node, i) => {
                    const kind = node.split(":")[0];
                    const tone = EVIDENCE_TONE[kind] || "#94a3b8";
                    return (
                      <div key={i} style={{ padding: "0.6rem 0.85rem", borderRadius: "4px", background: "rgba(148, 163, 184, 0.08)", borderLeft: `3px solid ${tone}`, fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{ fontWeight: 700, fontSize: "0.7rem", color: tone }}>[{kind}]</span>
                        <span>{node.replace(/^[A-Z_]+:\s*/, "")}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <p>Select a scenario to view its figures.</p>
            </div>
          )}
        </section>
      </div>

      {showCreateModal && (
        <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div className="modal-card" style={{ background: "var(--bg-surface, #0f172a)", padding: "1.5rem", borderRadius: "8px", maxWidth: "550px", width: "100%" }}>
            <h2 style={{ fontSize: "1.1rem", marginBottom: "1rem" }}>Create New Scenario Alternative</h2>
            <form onSubmit={handleCreateScenario} className="form-stack" style={{ display: "grid", gap: "0.75rem" }}>
              <div>
                <label style={field}>Recruitment project</label>
                <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} className="input-field" required data-testid="scenario-project-select">
                  <option value="">Select one of your projects…</option>
                  {projects.map((p) => (
                    <option key={p.project_id} value={p.project_id}>{p.name} · {p.club}</option>
                  ))}
                </select>
                {projects.length === 0 && <span style={field}>You have no recruitment projects yet: create one first.</span>}
              </div>
              <div>
                <label style={field}>Scenario Title</label>
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="input-field" required />
              </div>
              <div>
                <label style={field}>Alternative Type</label>
                <select value={form.scenario_type} onChange={(e) => setForm({ ...form, scenario_type: e.target.value })} className="input-field">
                  <option value="SELL_BUY">SELL_BUY (Sell X / Buy Y)</option>
                  <option value="RETAIN_BUY">RETAIN_BUY (Retain X / Buy Y)</option>
                  <option value="SELL_ACADEMY">SELL_ACADEMY (Sell X / Promote Academy)</option>
                </select>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div>
                  <label style={field}>Player id</label>
                  <input type="text" value={form.movement.player_id} onChange={(e) => setMovement({ player_id: e.target.value })} className="input-field" required />
                </div>
                <div>
                  <label style={field}>Player name</label>
                  <input type="text" value={form.movement.player_name} onChange={(e) => setMovement({ player_name: e.target.value })} className="input-field" required />
                </div>
                <div>
                  <label style={field}>Action</label>
                  <select value={form.movement.action} onChange={(e) => setMovement({ action: e.target.value })} className="input-field">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                    <option value="RETAIN">RETAIN</option>
                    <option value="PROMOTE_ACADEMY">PROMOTE_ACADEMY</option>
                  </select>
                </div>
                <div>
                  <label style={field}>Fee (EUR, leave blank if unknown)</label>
                  <input type="number" min="0" value={form.movement.fee_eur} onChange={(e) => setMovement({ fee_eur: e.target.value })} className="input-field" />
                </div>
                <div>
                  <label style={field}>Weekly wage (EUR, optional)</label>
                  <input type="number" min="0" value={form.movement.wage_eur_weekly} onChange={(e) => setMovement({ wage_eur_weekly: e.target.value })} className="input-field" />
                </div>
              </div>
              {createError && <div style={{ color: "#ef4444", fontSize: "0.8rem" }} data-testid="scenario-create-error">{createError}</div>}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1rem" }}>
                <button type="button" className="secondary-button" onClick={() => setShowCreateModal(false)}>Cancel</button>
                <button type="submit" className="primary-button">Save Alternative</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
