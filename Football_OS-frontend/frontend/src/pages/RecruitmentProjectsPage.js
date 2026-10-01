import React, { useState, useEffect } from "react";
import axios from "axios";
import {
  Briefcase, Filter, Users, GitCompare, GitFork, ShieldCheck,
  CheckCircle2, Clock, AlertTriangle, FileText, ChevronRight,
  TrendingUp, Award, Layers
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:8000";

export default function RecruitmentProjectsPage() {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [activeTab, setActiveTab] = useState("workspace"); // workspace, comparison, report, decision
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [comparisonData, setComparisonData] = useState(null);
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchProjects = async () => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/phase10/recruitment/projects`);
      setProjects(res.data);
      if (res.data.length > 0) {
        setSelectedProject(res.data[0]);
      }
    } catch (err) {
      console.error("Failed to load recruitment projects", err);
    } finally {
      setLoading(false);
    }
  };

  const handleStateChange = async (candidateId, newState) => {
    if (!selectedProject) return;
    try {
      await axios.put(
        `${BACKEND_URL}/api/phase10/recruitment/projects/${selectedProject.project_id}/candidates/${candidateId}/state`,
        { new_state: newState }
      );
      // Refresh project
      const res = await axios.get(`${BACKEND_URL}/api/phase10/recruitment/projects/${selectedProject.project_id}`);
      setSelectedProject(res.data);
    } catch (err) {
      console.error("Failed to update candidate state", err);
    }
  };

  const handleCompare = async () => {
    if (!selectedProject || selectedCandidates.length < 2) return;
    try {
      const res = await axios.post(
        `${BACKEND_URL}/api/phase10/recruitment/projects/${selectedProject.project_id}/compare`,
        { candidate_ids: selectedCandidates }
      );
      setComparisonData(res.data);
      setActiveTab("comparison");
    } catch (err) {
      console.error("Failed to compare candidates", err);
    }
  };

  const handleLoadReport = async () => {
    if (!selectedProject) return;
    try {
      const res = await axios.get(
        `${BACKEND_URL}/api/phase10/recruitment/projects/${selectedProject.project_id}/report`
      );
      setReportData(res.data);
      setActiveTab("report");
    } catch (err) {
      console.error("Failed to generate report", err);
    }
  };

  if (loading) {
    return <div className="page-loading" data-testid="recruitment-loading">Loading Recruitment Workspace...</div>;
  }

  const p = selectedProject;

  return (
    <div className="recruitment-workspace" data-testid="recruitment-projects-page" style={{ padding: "24px", color: "#f8fafc" }}>
      {/* ── §19 Project Header ── */}
      {p && (
        <header className="project-header" style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", padding: "20px", marginBottom: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
                <Briefcase size={20} color="#38bdf8" />
                <h1 style={{ margin: 0, fontSize: "22px", fontWeight: "700" }}>{p.name}</h1>
                <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "4px", background: "#0284c7", color: "#fff", fontWeight: "600" }}>
                  {p.status}
                </span>
              </div>
              <p style={{ margin: "4px 0 0 0", color: "#94a3b8", fontSize: "14px" }}>
                Target: <strong style={{ color: "#e2e8f0" }}>{p.position} ({p.target_role})</strong> · Club: <strong style={{ color: "#e2e8f0" }}>{p.club}</strong> · Season: <strong style={{ color: "#e2e8f0" }}>{p.season}</strong>
              </p>
            </div>

            <div style={{ display: "flex", gap: "24px", textAlign: "right" }}>
              <div>
                <p style={{ margin: 0, fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>Formation</p>
                <p style={{ margin: 0, fontSize: "16px", fontWeight: "600", color: "#38bdf8" }}>{p.formation}</p>
              </div>
              <div>
                <p style={{ margin: 0, fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>Budget (EUR)</p>
                <p style={{ margin: 0, fontSize: "16px", fontWeight: "600", color: "#4ade80" }}>€{(p.budget_eur / 1e6).toFixed(1)}M</p>
              </div>
              <div>
                <p style={{ margin: 0, fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>Age Limit</p>
                <p style={{ margin: 0, fontSize: "16px", fontWeight: "600", color: "#e2e8f0" }}>{p.min_age} - {p.max_age} yrs</p>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: "12px", marginTop: "16px", borderTop: "1px solid #1e293b", paddingTop: "12px" }}>
            <button
              onClick={() => setActiveTab("workspace")}
              style={{ padding: "6px 14px", borderRadius: "4px", background: activeTab === "workspace" ? "#1e293b" : "transparent", color: activeTab === "workspace" ? "#38bdf8" : "#94a3b8", border: "1px solid #334155", cursor: "pointer", fontWeight: "600" }}
            >
              Shortlist Workflow
            </button>
            <button
              onClick={handleCompare}
              disabled={selectedCandidates.length < 2}
              style={{ padding: "6px 14px", borderRadius: "4px", background: activeTab === "comparison" ? "#1e293b" : "transparent", color: activeTab === "comparison" ? "#38bdf8" : "#94a3b8", border: "1px solid #334155", cursor: selectedCandidates.length < 2 ? "not-allowed" : "pointer", opacity: selectedCandidates.length < 2 ? 0.5 : 1 }}
            >
              Compare ({selectedCandidates.length})
            </button>
            <button
              onClick={handleLoadReport}
              style={{ padding: "6px 14px", borderRadius: "4px", background: activeTab === "report" ? "#1e293b" : "transparent", color: activeTab === "report" ? "#38bdf8" : "#94a3b8", border: "1px solid #334155", cursor: "pointer" }}
            >
              Evidence Report
            </button>
          </div>
        </header>
      )}

      {/* ── Workflow Workspace Tab ── */}
      {activeTab === "workspace" && p && (
        <section data-testid="workspace-content">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h2 style={{ fontSize: "16px", fontWeight: "600", margin: 0 }}>Candidate Pipeline ({p.candidates.length})</h2>
            <span style={{ fontSize: "12px", color: "#94a3b8" }}>Select 2 or more candidates to compare multi-dimensional profiles</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: "16px" }}>
            {p.candidates.map((c) => {
              const isSelected = selectedCandidates.includes(c.candidate_id);
              const assess = c.analytical_assessment || {};

              return (
                <div
                  key={c.candidate_id}
                  data-testid={`candidate-card-${c.candidate_id}`}
                  style={{
                    background: "#0f172a",
                    border: isSelected ? "2px solid #38bdf8" : "1px solid #1e293b",
                    borderRadius: "8px",
                    padding: "16px",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between"
                  }}
                >
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedCandidates([...selectedCandidates, c.candidate_id]);
                              } else {
                                setSelectedCandidates(selectedCandidates.filter((id) => id !== c.candidate_id));
                              }
                            }}
                          />
                          <h3 style={{ margin: 0, fontSize: "16px", fontWeight: "700" }}>{c.player_name}</h3>
                        </div>
                        <p style={{ margin: "2px 0 0 24px", fontSize: "12px", color: "#94a3b8" }}>
                          {c.current_club} · {c.current_competition} · {c.age} yrs
                        </p>
                      </div>

                      <select
                        value={c.state}
                        onChange={(e) => handleStateChange(c.candidate_id, e.target.value)}
                        style={{ background: "#1e293b", color: "#38bdf8", border: "1px solid #334155", borderRadius: "4px", fontSize: "11px", padding: "4px 8px" }}
                      >
                        <option value="DISCOVERED">DISCOVERED</option>
                        <option value="REVIEWING">REVIEWING</option>
                        <option value="SHORTLISTED">SHORTLISTED</option>
                        <option value="SCENARIO_TESTED">SCENARIO_TESTED</option>
                        <option value="DECISION_RECORDED">DECISION_RECORDED</option>
                        <option value="ARCHIVED">ARCHIVED</option>
                      </select>
                    </div>

                    {/* Independent Analytical Metrics */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", margin: "12px 0", background: "#0b1329", padding: "10px", borderRadius: "6px" }}>
                      <div>
                        <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase" }}>Tactical Fit</span>
                        <p style={{ margin: 0, fontSize: "14px", fontWeight: "600", color: "#38bdf8" }}>{assess.tactical_fit_score?.toFixed(1) || "N/A"}%</p>
                      </div>
                      <div>
                        <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase" }}>Contribution</span>
                        <p style={{ margin: 0, fontSize: "14px", fontWeight: "600", color: "#e2e8f0" }}>{assess.contribution_rating?.toFixed(1) || "N/A"}%</p>
                      </div>
                      <div>
                        <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase" }}>Valuation (EUR)</span>
                        <p style={{ margin: 0, fontSize: "14px", fontWeight: "600", color: "#4ade80" }}>€{((assess.estimated_value_eur || 0) / 1e6).toFixed(1)}M</p>
                      </div>
                      <div>
                        <span style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase" }}>Risk Score</span>
                        <p style={{ margin: 0, fontSize: "14px", fontWeight: "600", color: assess.overall_risk_score > 0.4 ? "#f87171" : "#fbbf24" }}>
                          {assess.overall_risk_score?.toFixed(2) || "0.00"}
                        </p>
                      </div>
                    </div>

                    {/* Scout Notes */}
                    {c.scout_notes && c.scout_notes.length > 0 && (
                      <div style={{ fontSize: "12px", color: "#cbd5e1", fontStyle: "italic", borderLeft: "2px solid #38bdf8", paddingLeft: "8px", margin: "8px 0" }}>
                        "{c.scout_notes[0]}"
                      </div>
                    )}
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid #1e293b", paddingTop: "8px", marginTop: "8px", fontSize: "11px", color: "#64748b" }}>
                    <span>Hard Constraints: <strong style={{ color: c.hard_constraints_passed ? "#4ade80" : "#f87171" }}>{c.hard_constraints_passed ? "PASS" : "FAIL"}</strong></span>
                    <span>Confidence: <strong style={{ color: "#38bdf8" }}>{c.overall_confidence}</strong></span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Comparison Tab ── */}
      {activeTab === "comparison" && comparisonData && (
        <section data-testid="comparison-content" style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", padding: "20px" }}>
          <h2 style={{ fontSize: "18px", fontWeight: "700", marginBottom: "16px" }}>Multi-Dimensional Shortlist Comparison</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "14px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8" }}>
                <th style={{ padding: "10px" }}>Dimension</th>
                {comparisonData.candidates.map((c) => (
                  <th key={c.candidate_id} style={{ padding: "10px", color: "#f8fafc" }}>{c.player_name} ({c.current_club})</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <td style={{ padding: "10px", color: "#94a3b8" }}>Tactical Fit</td>
                {comparisonData.candidates.map((c) => (
                  <td key={c.candidate_id} style={{ padding: "10px", fontWeight: "600", color: "#38bdf8" }}>
                    {c.analytical_assessment?.tactical_fit_score?.toFixed(1)}%
                  </td>
                ))}
              </tr>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <td style={{ padding: "10px", color: "#94a3b8" }}>Contribution Percentile</td>
                {comparisonData.candidates.map((c) => (
                  <td key={c.candidate_id} style={{ padding: "10px", fontWeight: "600" }}>
                    {c.analytical_assessment?.contribution_rating?.toFixed(1)}%
                  </td>
                ))}
              </tr>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <td style={{ padding: "10px", color: "#94a3b8" }}>Estimated Valuation</td>
                {comparisonData.candidates.map((c) => (
                  <td key={c.candidate_id} style={{ padding: "10px", fontWeight: "600", color: "#4ade80" }}>
                    €{((c.analytical_assessment?.estimated_value_eur || 0) / 1e6).toFixed(1)}M
                  </td>
                ))}
              </tr>
              <tr style={{ borderBottom: "1px solid #1e293b" }}>
                <td style={{ padding: "10px", color: "#94a3b8" }}>Overall Risk Score</td>
                {comparisonData.candidates.map((c) => (
                  <td key={c.candidate_id} style={{ padding: "10px", fontWeight: "600", color: c.analytical_assessment?.overall_risk_score > 0.4 ? "#f87171" : "#fbbf24" }}>
                    {c.analytical_assessment?.overall_risk_score?.toFixed(2)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </section>
      )}

      {/* ── Report Tab ── */}
      {activeTab === "report" && reportData && (
        <section data-testid="report-content" style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", padding: "24px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h2 style={{ fontSize: "20px", fontWeight: "700", margin: 0 }}>14-Section Evidence Report</h2>
            <span style={{ fontSize: "12px", color: "#64748b" }}>Report ID: {reportData.report_id}</span>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <h3 style={{ fontSize: "14px", color: "#38bdf8", textTransform: "uppercase" }}>1. Executive Summary</h3>
            <p style={{ color: "#cbd5e1", fontSize: "14px", lineHeight: "1.5" }}>{reportData.sections["1_executive_summary"]}</p>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <h3 style={{ fontSize: "14px", color: "#38bdf8", textTransform: "uppercase" }}>11. Evidence Layers</h3>
            <ul style={{ color: "#cbd5e1", fontSize: "13px", paddingLeft: "20px" }}>
              {reportData.sections["11_evidence"]?.map((item, idx) => (
                <li key={idx} style={{ marginBottom: "4px" }}>{item}</li>
              ))}
            </ul>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <h3 style={{ fontSize: "14px", color: "#f87171", textTransform: "uppercase" }}>13. Material Disclosures & Limitations</h3>
            <ul style={{ color: "#94a3b8", fontSize: "13px", paddingLeft: "20px" }}>
              {reportData.sections["13_limitations"]?.map((item, idx) => (
                <li key={idx} style={{ marginBottom: "4px" }}>{item}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}
