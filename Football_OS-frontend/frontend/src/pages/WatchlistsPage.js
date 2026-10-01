import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Bookmark, ShieldAlert, Eye, TrendingUp, Filter, AlertCircle,
  Plus, CheckCircle2, ChevronRight, Activity, Clock, ShieldCheck,
  Search, RefreshCw, Layers, ArrowUpRight, ArrowDownRight, Info
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

export default function WatchlistsPage() {
  const [watchlists, setWatchlists] = useState([]);
  const [selectedWatchlist, setSelectedWatchlist] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [activeTab, setActiveTab] = useState("alerts"); // "alerts", "tracked", "evaluate"
  const [filterType, setFilterType] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Evaluate modal/form state
  const [evalForm, setEvalForm] = useState({
    entity_id: "p_william_saliba",
    entity_name: "William Saliba",
    metric_name: "tactical_fit_score",
    previous_val: 78.0,
    new_val: 84.5,
    change_type: "tactical_fit_change"
  });
  const [evalResult, setEvalResult] = useState(null);

  useEffect(() => {
    fetchWatchlists();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchWatchlists = async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/phase10/watchlists`);
      setWatchlists(res.data);
      if (res.data.length > 0) {
        setSelectedWatchlist(res.data[0]);
        fetchAlerts(res.data[0].watchlist_id);
      }
    } catch (err) {
      console.error("Failed to load watchlists", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAlerts = async (watchlistId) => {
    setRefreshing(true);
    try {
      const res = await axios.get(`${BACKEND_URL}/api/phase10/watchlists/alerts`, {
        params: { watchlist_id: watchlistId }
      });
      setAlerts(res.data);
    } catch (err) {
      console.error("Failed to load alerts", err);
    } finally {
      setRefreshing(false);
    }
  };

  const handleSelectWatchlist = (wl) => {
    setSelectedWatchlist(wl);
    fetchAlerts(wl.watchlist_id);
    setEvalResult(null);
  };

  const handleEvaluateChange = async (e) => {
    e.preventDefault();
    if (!selectedWatchlist) return;
    try {
      const res = await axios.post(
        `${BACKEND_URL}/api/phase10/watchlists/${selectedWatchlist.watchlist_id}/evaluate`,
        evalForm
      );
      setEvalResult(res.data);
      fetchAlerts(selectedWatchlist.watchlist_id);
    } catch (err) {
      console.error("Failed to evaluate change", err);
    }
  };

  const filteredAlerts = alerts.filter(a => {
    if (filterType === "ALL") return true;
    return a.change_type?.toLowerCase() === filterType.toLowerCase();
  });

  if (loading) {
    return (
      <main className="page-container" data-testid="watchlists-loading">
        <div className="empty-state">
          <Clock className="spin" size={24} />
          <p>Loading operational watchlists & governed alerts…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="page-container" data-testid="watchlists-page">
      {/* Header */}
      <header className="page-header" data-testid="watchlists-header">
        <div>
          <div className="eyebrow" data-testid="watchlists-eyebrow">
            PHASE 10 · OPERATIONAL SURFACES
          </div>
          <h1 data-testid="watchlists-title">Persistent Watchlists & Governed Alerts</h1>
          <p className="page-subtitle">
            Continuous tracking across players, clubs, and metrics with strict non-causal alert governance.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="secondary-button"
            onClick={() => selectedWatchlist && fetchAlerts(selectedWatchlist.watchlist_id)}
            disabled={refreshing}
            data-testid="refresh-alerts-btn"
          >
            <RefreshCw size={14} className={refreshing ? "spin" : ""} /> Refresh Signals
          </button>
        </div>
      </header>

      {/* Alert Governance Banner */}
      <section className="governance-card" style={{ marginBottom: "1.5rem" }} data-testid="alert-governance-banner">
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
          <ShieldCheck size={20} color="var(--accent-teal, #14b8a6)" style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              Alert Governance & Epistemic Separation Active
            </div>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", lineHeight: "1.4" }}>
              Alerts report quantified metric deltas only. Causal inferences ("player improved", "form slumped due to coaching")
              are strictly rejected at the engine boundary. Every alert contains complete provenance, model version, and verification digest.
            </p>
          </div>
        </div>
      </section>

      {/* Main Layout: Sidebar & Content */}
      <div className="two-column-layout" style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "1.5rem" }}>
        {/* Left: Watchlist Selector */}
        <aside className="panel" data-testid="watchlists-list-panel">
          <div className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <span style={{ fontWeight: 600, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Active Watchlists ({watchlists.length})
            </span>
          </div>

          <div className="stack" style={{ gap: "0.5rem" }}>
            {watchlists.map(wl => {
              const isSelected = selectedWatchlist?.watchlist_id === wl.watchlist_id;
              return (
                <div
                  key={wl.watchlist_id}
                  onClick={() => handleSelectWatchlist(wl)}
                  className={`clickable-card ${isSelected ? "selected" : ""}`}
                  style={{
                    padding: "0.85rem",
                    borderRadius: "6px",
                    border: isSelected ? "1px solid var(--accent-blue, #3b82f6)" : "1px solid var(--border-subtle, #1e293b)",
                    background: isSelected ? "rgba(59, 130, 246, 0.08)" : "var(--bg-surface, #0f172a)",
                    cursor: "pointer"
                  }}
                  data-testid={`watchlist-item-${wl.watchlist_id}`}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{wl.name}</span>
                    <ChevronRight size={14} color="var(--text-muted, #64748b)" />
                  </div>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", margin: "0.25rem 0 0.5rem" }}>
                    {wl.description}
                  </p>
                  <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                    {wl.tags?.map(t => (
                      <span key={t} className="badge micro" style={{ fontSize: "0.65rem", padding: "1px 6px" }}>{t}</span>
                    ))}
                    <span className="badge micro neutral" style={{ fontSize: "0.65rem", padding: "1px 6px" }}>
                      {wl.items?.length || 0} tracked
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* Right: Workspace (Alerts / Tracked / Change Evaluator) */}
        <section className="panel" data-testid="watchlist-detail-panel">
          {selectedWatchlist && (
            <>
              {/* Tab Bar */}
              <div className="tab-bar" style={{ display: "flex", gap: "1rem", borderBottom: "1px solid var(--border-subtle, #1e293b)", paddingBottom: "0.5rem", marginBottom: "1.25rem" }}>
                <button
                  className={`tab-button ${activeTab === "alerts" ? "active" : ""}`}
                  onClick={() => setActiveTab("alerts")}
                  data-testid="tab-alerts"
                  style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "alerts" ? "var(--text-bright, #fff)" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "alerts" ? "2px solid var(--accent-blue, #3b82f6)" : "none" }}
                >
                  Governed Alerts ({filteredAlerts.length})
                </button>
                <button
                  className={`tab-button ${activeTab === "tracked" ? "active" : ""}`}
                  onClick={() => setActiveTab("tracked")}
                  data-testid="tab-tracked"
                  style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "tracked" ? "var(--text-bright, #fff)" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "tracked" ? "2px solid var(--accent-blue, #3b82f6)" : "none" }}
                >
                  Tracked Entities ({selectedWatchlist.items?.length || 0})
                </button>
                <button
                  className={`tab-button ${activeTab === "evaluate" ? "active" : ""}`}
                  onClick={() => setActiveTab("evaluate")}
                  data-testid="tab-evaluate"
                  style={{ background: "none", border: "none", padding: "0.4rem 0.8rem", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem", color: activeTab === "evaluate" ? "var(--text-bright, #fff)" : "var(--text-muted, #94a3b8)", borderBottom: activeTab === "evaluate" ? "2px solid var(--accent-blue, #3b82f6)" : "none" }}
                >
                  Change Evaluator (Test Boundary)
                </button>
              </div>

              {/* TAB 1: GOVERNED ALERTS */}
              {activeTab === "alerts" && (
                <div data-testid="alerts-view">
                  {/* Filter Toolbar */}
                  <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", alignItems: "center" }}>
                    <Filter size={14} color="var(--text-muted, #64748b)" />
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #64748b)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Filter Change:</span>
                    {["ALL", "PERFORMANCE_CHANGE", "TACTICAL_FIT_CHANGE", "VALUATION_CHANGE", "RISK_CHANGE", "ROLE_CHANGE"].map(ft => (
                      <button
                        key={ft}
                        onClick={() => setFilterType(ft)}
                        className={`badge-button ${filterType === ft ? "active" : ""}`}
                        style={{
                          background: filterType === ft ? "var(--accent-blue, #3b82f6)" : "var(--bg-card, #1e293b)",
                          color: filterType === ft ? "#fff" : "var(--text-muted, #94a3b8)",
                          border: "none",
                          padding: "3px 8px",
                          borderRadius: "4px",
                          fontSize: "0.7rem",
                          cursor: "pointer"
                        }}
                        data-testid={`filter-${ft}`}
                      >
                        {ft.replaceAll("_", " ")}
                      </button>
                    ))}
                  </div>

                  {filteredAlerts.length === 0 ? (
                    <div className="empty-state" style={{ padding: "2rem", textAlign: "center", border: "1px dashed var(--border-subtle, #334155)", borderRadius: "6px" }}>
                      <AlertCircle size={20} color="var(--text-muted, #64748b)" style={{ margin: "0 auto 0.5rem" }} />
                      <p style={{ color: "var(--text-muted, #94a3b8)", fontSize: "0.85rem" }}>
                        No governed alerts matching current filter.
                      </p>
                    </div>
                  ) : (
                    <div className="stack" style={{ gap: "0.75rem" }}>
                      {filteredAlerts.map(alert => {
                        const isPositive = alert.delta > 0;
                        return (
                          <div
                            key={alert.alert_id}
                            className="card alert-card"
                            style={{
                              padding: "1rem",
                              borderRadius: "6px",
                              border: "1px solid var(--border-subtle, #1e293b)",
                              background: "var(--bg-surface, #0f172a)"
                            }}
                            data-testid={`alert-card-${alert.alert_id}`}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                  <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{alert.entity_name}</span>
                                  <span className="badge micro info" style={{ fontSize: "0.65rem" }}>
                                    {alert.change_type?.replaceAll("_", " ")}
                                  </span>
                                  <span className="badge micro success" style={{ fontSize: "0.65rem" }}>
                                    CONFIDENCE: {alert.confidence}
                                  </span>
                                  <span className="badge micro neutral" style={{ fontSize: "0.65rem" }}>
                                    {alert.data_status}
                                  </span>
                                </div>
                                <p style={{ fontSize: "0.85rem", margin: "0.4rem 0", color: "var(--text-bright, #f8fafc)", fontFamily: "monospace" }}>
                                  {alert.what_changed}
                                </p>
                              </div>
                              <div style={{ textAlign: "right" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", justifyContent: "flex-end" }}>
                                  {isPositive ? (
                                    <ArrowUpRight size={16} color="var(--accent-green, #10b981)" />
                                  ) : (
                                    <ArrowDownRight size={16} color="var(--accent-red, #ef4444)" />
                                  )}
                                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: isPositive ? "#10b981" : "#ef4444" }}>
                                    {alert.delta > 0 ? `+${alert.delta}` : alert.delta}
                                  </span>
                                </div>
                                <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #64748b)" }}>
                                  {alert.previous_value} → {alert.new_value}
                                </span>
                              </div>
                            </div>

                            {/* Evidence & Provenance Strip */}
                            <div style={{ marginTop: "0.75rem", paddingTop: "0.6rem", borderTop: "1px dashed var(--border-subtle, #1e293b)", fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.35rem" }}>
                                <span><strong>Model:</strong> {alert.model_version}</span>
                                <span><strong>Provider:</strong> {alert.source_provider}</span>
                                <span><strong>Triggered:</strong> {new Date(alert.created_at).toLocaleDateString()}</span>
                              </div>
                              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.35rem" }}>
                                {alert.evidence_summary?.map((ev, i) => (
                                  <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: "3px", background: "rgba(255,255,255,0.03)", padding: "2px 6px", borderRadius: "4px" }}>
                                    <CheckCircle2 size={11} color="var(--accent-teal, #14b8a6)" /> {ev}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: TRACKED ENTITIES */}
              {activeTab === "tracked" && (
                <div data-testid="tracked-entities-view">
                  <div className="table-responsive">
                    <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle, #1e293b)", textAlign: "left", color: "var(--text-muted, #94a3b8)" }}>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Entity</th>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Type</th>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Role Snapshot</th>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Contribution %ile</th>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Est. Valuation</th>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Risk Score</th>
                          <th style={{ padding: "0.6rem 0.5rem" }}>Observed Mins</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedWatchlist.items?.map(item => {
                          const snap = item.current_value_snapshot || {};
                          return (
                            <tr key={item.item_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`tracked-row-${item.item_id}`}>
                              <td style={{ padding: "0.6rem 0.5rem", fontWeight: 600 }}>{item.entity_name}</td>
                              <td style={{ padding: "0.6rem 0.5rem" }}>
                                <span className="badge micro neutral">{item.entity_type}</span>
                              </td>
                              <td style={{ padding: "0.6rem 0.5rem" }}>{snap.role || "—"}</td>
                              <td style={{ padding: "0.6rem 0.5rem" }}>{snap.contribution_percentile ? `${snap.contribution_percentile}%` : "—"}</td>
                              <td style={{ padding: "0.6rem 0.5rem" }}>
                                {snap.estimated_value_eur ? `€${(snap.estimated_value_eur / 1e6).toFixed(1)}M` : "—"}
                              </td>
                              <td style={{ padding: "0.6rem 0.5rem" }}>{snap.overall_risk_score ?? "—"}</td>
                              <td style={{ padding: "0.6rem 0.5rem" }}>{snap.minutes_played ? `${snap.minutes_played}'` : "—"}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 3: CHANGE EVALUATOR */}
              {activeTab === "evaluate" && (
                <div data-testid="evaluate-view">
                  <div style={{ maxWidth: "600px" }}>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-muted, #94a3b8)", marginBottom: "1rem" }}>
                      Submit an operational metric shift to test the alert governance validation boundary and non-causal statement synthesis.
                    </p>
                    <form onSubmit={handleEvaluateChange} className="form-stack" style={{ display: "grid", gap: "0.75rem" }}>
                      <div>
                        <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                          Entity ID & Name
                        </label>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                          <input
                            type="text"
                            value={evalForm.entity_id}
                            onChange={e => setEvalForm({ ...evalForm, entity_id: e.target.value })}
                            className="input-field"
                            placeholder="p_player_id"
                          />
                          <input
                            type="text"
                            value={evalForm.entity_name}
                            onChange={e => setEvalForm({ ...evalForm, entity_name: e.target.value })}
                            className="input-field"
                            placeholder="Player Name"
                          />
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                        <div>
                          <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                            Metric Name
                          </label>
                          <input
                            type="text"
                            value={evalForm.metric_name}
                            onChange={e => setEvalForm({ ...evalForm, metric_name: e.target.value })}
                            className="input-field"
                            placeholder="tactical_fit_score"
                          />
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                            Change Type
                          </label>
                          <select
                            value={evalForm.change_type}
                            onChange={e => setEvalForm({ ...evalForm, change_type: e.target.value })}
                            className="input-field"
                          >
                            <option value="performance_change">performance_change</option>
                            <option value="tactical_fit_change">tactical_fit_change</option>
                            <option value="valuation_change">valuation_change</option>
                            <option value="risk_change">risk_change</option>
                            <option value="role_change">role_change</option>
                          </select>
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                        <div>
                          <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                            Previous Metric Value
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            value={evalForm.previous_val}
                            onChange={e => setEvalForm({ ...evalForm, previous_val: parseFloat(e.target.value) || 0 })}
                            className="input-field"
                          />
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", display: "block", marginBottom: "4px" }}>
                            New Metric Value
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            value={evalForm.new_val}
                            onChange={e => setEvalForm({ ...evalForm, new_val: parseFloat(e.target.value) || 0 })}
                            className="input-field"
                          />
                        </div>
                      </div>

                      <button type="submit" className="primary-button" style={{ marginTop: "0.5rem" }} data-testid="evaluate-submit-btn">
                        Evaluate & Synthesize Governed Alert
                      </button>
                    </form>

                    {evalResult && (
                      <div className="result-card" style={{ marginTop: "1rem", padding: "0.85rem", background: "rgba(20, 184, 166, 0.08)", border: "1px solid var(--accent-teal, #14b8a6)", borderRadius: "6px" }} data-testid="evaluate-result-card">
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 600, color: "var(--accent-teal, #14b8a6)", fontSize: "0.85rem" }}>
                          <CheckCircle2 size={16} /> Status: {evalResult.status}
                        </div>
                        {evalResult.alert && (
                          <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--text-bright, #fff)" }}>
                            <p style={{ margin: "0.25rem 0", fontFamily: "monospace" }}>
                              {evalResult.alert.what_changed}
                            </p>
                            <span style={{ fontSize: "0.7rem", color: "var(--text-muted, #94a3b8)" }}>
                              Delta: {evalResult.alert.delta} · Confidence: {evalResult.alert.confidence} · {evalResult.alert.model_version}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  );
}
