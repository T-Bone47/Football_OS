import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, CheckCircle2, CircleAlert, Compass, Database,
  DollarSign, FileText, GitCompare, Layers, Network, Radar,
  ShieldAlert, ShieldCheck, Target, TrendingUp, Users, Info
} from "lucide-react";
import {
  getRecruitmentTargets,
  analyzeRecruitmentTargets,
  analyzeReplacement,
  analyzeTransferScenario,
  compareCandidates,
  getDecisionEvidence,
  getPlayers,
  getTacticalContexts,
  getClubs,
} from "@/lib/footballApi";
import EvidenceDrawer from "@/components/EvidenceDrawer";

export default function DecisionPage() {
  // Mode: "recruitment" | "replacement" | "scenario" | "comparison"
  const [mode, setMode] = useState("recruitment");

  // Recruitment filters
  const [targetPosition, setTargetPosition] = useState("CM");
  const [tacticalContextId, setTacticalContextId] = useState("433_cm_progressive_midfielder");
  const [targetRole, setTargetRole] = useState("Progressive Midfielder");
  const [budgetEur, setBudgetEur] = useState(35000000);
  const [minAge, setMinAge] = useState(19);
  const [maxAge, setMaxAge] = useState(28);
  const [minMinutes, setMinMinutes] = useState(600);
  const [riskTolerance, setRiskTolerance] = useState("MEDIUM");

  // Replacement filters
  const [replacePlayerId, setReplacePlayerId] = useState("");
  const [minSimilarity, setMinSimilarity] = useState(0.70);

  // Scenario filters
  const [scenarioClubId, setScenarioClubId] = useState("");
  const [transferInId, setTransferInId] = useState("");
  const [transferOutId, setTransferOutId] = useState("");

  // Comparison selection
  const [selectedCandidateIds, setSelectedCandidateIds] = useState([]);

  // Active inspected candidate
  const [activeCandidateIndex, setActiveCandidateIndex] = useState(0);

  // Evidence drawer state
  const [evidenceDrawerData, setEvidenceDrawerData] = useState(null);

  // Load supporting options
  const playersQuery = useQuery({
    queryKey: ["decision-roster"],
    queryFn: () => getPlayers({ limit: 100 }),
    retry: false,
  });

  const contextsQuery = useQuery({
    queryKey: ["decision-contexts"],
    queryFn: getTacticalContexts,
    retry: false,
  });

  const clubsQuery = useQuery({
    queryKey: ["decision-clubs"],
    queryFn: getClubs,
    retry: false,
  });

  // Recruitment Query
  const recruitmentQuery = useQuery({
    queryKey: [
      "recruitment-decision",
      targetPosition,
      tacticalContextId,
      targetRole,
      budgetEur,
      minAge,
      maxAge,
      minMinutes,
      riskTolerance,
    ],
    queryFn: () =>
      analyzeRecruitmentTargets({
        target_position: targetPosition,
        tactical_context_id: tacticalContextId || undefined,
        target_role: targetRole || undefined,
        budget_eur: Number(budgetEur) || undefined,
        min_age: Number(minAge) || undefined,
        max_age: Number(maxAge) || undefined,
        min_minutes: Number(minMinutes) || undefined,
        risk_tolerance: riskTolerance,
        limit: 8,
      }),
    enabled: mode === "recruitment",
    retry: false,
  });

  // Replacement Query
  const replacementQuery = useQuery({
    queryKey: ["replacement-decision", replacePlayerId, targetRole, minSimilarity, budgetEur],
    queryFn: () =>
      analyzeReplacement({
        player_id_to_replace: replacePlayerId,
        target_role: targetRole || undefined,
        min_similarity: Number(minSimilarity),
        budget_eur: Number(budgetEur) || undefined,
        limit: 6,
      }),
    enabled: mode === "replacement" && !!replacePlayerId,
    retry: false,
  });

  // Scenario Query
  const scenarioQuery = useQuery({
    queryKey: ["scenario-decision", scenarioClubId, transferInId, transferOutId, budgetEur],
    queryFn: () =>
      analyzeTransferScenario({
        club_id: scenarioClubId || undefined,
        roster_changes: [
          ...(transferInId ? [{ player_id: transferInId, direction: "IN" }] : []),
          ...(transferOutId ? [{ player_id: transferOutId, direction: "OUT" }] : []),
        ],
        budget_eur: Number(budgetEur) || undefined,
      }),
    enabled: mode === "scenario" && (!!transferInId || !!transferOutId),
    retry: false,
  });

  // Candidates comparison Query
  const comparisonQuery = useQuery({
    queryKey: ["comparison-decision", selectedCandidateIds],
    queryFn: () =>
      compareCandidates({
        candidate_ids: selectedCandidateIds,
      }),
    enabled: mode === "comparison" && selectedCandidateIds.length >= 2,
    retry: false,
  });

  // Determine current active recommendations list
  const activeRecommendations = useMemo(() => {
    if (mode === "recruitment") {
      return recruitmentQuery.data?.top_recommendations || [];
    }
    if (mode === "replacement") {
      return replacementQuery.data?.top_replacements || [];
    }
    return [];
  }, [mode, recruitmentQuery.data, replacementQuery.data]);

  const activeCandidate = activeRecommendations[activeCandidateIndex] || activeRecommendations[0] || null;
  const decisionAssessment = mode === "recruitment"
    ? recruitmentQuery.data?.decision
    : mode === "replacement"
    ? replacementQuery.data?.decision
    : mode === "scenario"
    ? scenarioQuery.data?.decision
    : null;

  const excludedSummaries = mode === "recruitment"
    ? recruitmentQuery.data?.excluded_summaries || []
    : mode === "replacement"
    ? replacementQuery.data?.excluded_summaries || []
    : [];

  return (
    <section className="intelligence-page" data-testid="decision-workspace-page">
      {/* 1. Header & Decision Context */}
      <div className="page-heading">
        <div>
          <p className="eyebrow">DECISION INTELLIGENCE / UNIFIED ENGINE</p>
          <h1 data-testid="page-title">Recruitment & Transfer Decisions</h1>
          <p className="workspace-subtitle" data-testid="page-description">
            Evidence-backed decision engine connecting player intelligence, tactical fit, similarity, market valuation, transfer risk, squad needs, and scenario prediction.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span className="contract-badge" data-testid="decision-version-badge">
            DECISION ENGINE v1.0 · PHASE 7
          </span>
        </div>
      </div>

      {/* Mode Navigation Tabs */}
      <div className="page-tabs" style={{ marginBottom: "20px" }}>
        <button
          className={mode === "recruitment" ? "page-tab active" : "page-tab"}
          onClick={() => setMode("recruitment")}
          data-testid="mode-tab-recruitment"
        >
          <Target size={14} style={{ marginRight: 6 }} /> Recruitment Targeting
        </button>
        <button
          className={mode === "replacement" ? "page-tab active" : "page-tab"}
          onClick={() => setMode("replacement")}
          data-testid="mode-tab-replacement"
        >
          <Users size={14} style={{ marginRight: 6 }} /> Replacement Analysis
        </button>
        <button
          className={mode === "scenario" ? "page-tab active" : "page-tab"}
          onClick={() => setMode("scenario")}
          data-testid="mode-tab-scenario"
        >
          <GitCompare size={14} style={{ marginRight: 6 }} /> Transfer Scenario Simulator
        </button>
        <button
          className={mode === "comparison" ? "page-tab active" : "page-tab"}
          onClick={() => setMode("comparison")}
          data-testid="mode-tab-comparison"
        >
          <Layers size={14} style={{ marginRight: 6 }} /> Candidate Comparison
        </button>
      </div>

      {/* 2. Squad Requirement & Input Constraints Panel */}
      <div className="filter-panel" style={{ marginBottom: "24px" }} data-testid="squad-requirements-panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: "6px" }}>
            <Target size={15} color="var(--cyan)" />
            {mode === "recruitment" && "Squad Requirement & Hard Constraints"}
            {mode === "replacement" && "Target Player Replacement Parameters"}
            {mode === "scenario" && "Transfer Scenario Specification"}
            {mode === "comparison" && "Multi-Candidate Evaluation Slots"}
          </h3>
          <span className="eyebrow" style={{ color: "var(--muted-strong)" }}>
            HARD CONSTRAINTS STRICTLY ENFORCED
          </span>
        </div>

        {mode === "recruitment" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px" }}>
            <div>
              <label className="metadata-label">Position</label>
              <select
                className="select-input"
                value={targetPosition}
                onChange={(e) => setTargetPosition(e.target.value)}
                data-testid="filter-target-position"
              >
                <option value="GK">GK - Goalkeeper</option>
                <option value="CB">CB - Centre Back</option>
                <option value="LB">LB - Left Back</option>
                <option value="RB">RB - Right Back</option>
                <option value="DM">DM - Defensive Midfield</option>
                <option value="CM">CM - Central Midfield</option>
                <option value="AM">AM - Attacking Midfield</option>
                <option value="LW">LW - Left Wing</option>
                <option value="RW">RW - Right Wing</option>
                <option value="ST">ST - Striker</option>
              </select>
            </div>

            <div>
              <label className="metadata-label">Tactical System</label>
              <select
                className="select-input"
                value={tacticalContextId}
                onChange={(e) => setTacticalContextId(e.target.value)}
                data-testid="filter-tactical-context"
              >
                <option value="433_cm_progressive_midfielder">4-3-3 Progressive Midfield</option>
                <option value="433_dm_deep_distributor">4-3-3 Deep Distributor (DM)</option>
                <option value="4231_am_chance_creator">4-2-3-1 Chance Creator (AM)</option>
                <option value="433_w_isolated_creator">4-3-3 Isolated Creator (W)</option>
                <option value="433_cb_ball_playing_cover">4-3-3 Ball Playing Cover (CB)</option>
                <option value="433_st_target_presser">4-3-3 Target Presser (ST)</option>
              </select>
            </div>

            <div>
              <label className="metadata-label">Target Role Archetype</label>
              <input
                type="text"
                className="search-input"
                value={targetRole}
                onChange={(e) => setTargetRole(e.target.value)}
                placeholder="e.g. Progressive Midfielder"
                data-testid="filter-target-role"
              />
            </div>

            <div>
              <label className="metadata-label">Budget Ceiling (€)</label>
              <input
                type="number"
                className="search-input"
                value={budgetEur}
                onChange={(e) => setBudgetEur(Number(e.target.value))}
                step="5000000"
                data-testid="filter-budget"
              />
            </div>

            <div>
              <label className="metadata-label">Age Window</label>
              <div style={{ display: "flex", gap: "6px" }}>
                <input
                  type="number"
                  className="search-input"
                  value={minAge}
                  onChange={(e) => setMinAge(Number(e.target.value))}
                  placeholder="Min"
                  style={{ width: "70px" }}
                />
                <input
                  type="number"
                  className="search-input"
                  value={maxAge}
                  onChange={(e) => setMaxAge(Number(e.target.value))}
                  placeholder="Max"
                  style={{ width: "70px" }}
                />
              </div>
            </div>

            <div>
              <label className="metadata-label">Minutes Floor</label>
              <input
                type="number"
                className="search-input"
                value={minMinutes}
                onChange={(e) => setMinMinutes(Number(e.target.value))}
                step="100"
                data-testid="filter-min-minutes"
              />
            </div>

            <div>
              <label className="metadata-label">Risk Tolerance</label>
              <select
                className="select-input"
                value={riskTolerance}
                onChange={(e) => setRiskTolerance(e.target.value)}
                data-testid="filter-risk-tolerance"
              >
                <option value="LOW">Low (Conservative)</option>
                <option value="MEDIUM">Medium (Balanced)</option>
                <option value="HIGH">High (Speculative)</option>
              </select>
            </div>
          </div>
        )}

        {mode === "replacement" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px" }}>
            <div>
              <label className="metadata-label">Player to Replace</label>
              <select
                className="select-input"
                value={replacePlayerId}
                onChange={(e) => setReplacePlayerId(e.target.value)}
                data-testid="filter-replace-player"
              >
                <option value="">Select player to replace...</option>
                {(playersQuery.data || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.primary_position || "MF"})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="metadata-label">Minimum Similarity (0.50 - 0.95)</label>
              <input
                type="number"
                step="0.05"
                min="0.50"
                max="0.95"
                className="search-input"
                value={minSimilarity}
                onChange={(e) => setMinSimilarity(Number(e.target.value))}
                data-testid="filter-min-similarity"
              />
            </div>

            <div>
              <label className="metadata-label">Replacement Budget (€)</label>
              <input
                type="number"
                className="search-input"
                value={budgetEur}
                onChange={(e) => setBudgetEur(Number(e.target.value))}
                step="5000000"
                data-testid="filter-replacement-budget"
              />
            </div>
          </div>
        )}

        {mode === "scenario" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px" }}>
            <div>
              <label className="metadata-label">Club Baseline</label>
              <select
                className="select-input"
                value={scenarioClubId}
                onChange={(e) => setScenarioClubId(e.target.value)}
                data-testid="filter-scenario-club"
              >
                <option value="">Select target squad...</option>
                {(clubsQuery.data || []).map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="metadata-label">Hypothetical Transfer IN</label>
              <select
                className="select-input"
                value={transferInId}
                onChange={(e) => setTransferInId(e.target.value)}
                data-testid="filter-scenario-in"
              >
                <option value="">Select incoming target...</option>
                {(playersQuery.data || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.primary_position || "MF"})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="metadata-label">Hypothetical Transfer OUT</label>
              <select
                className="select-input"
                value={transferOutId}
                onChange={(e) => setTransferOutId(e.target.value)}
                data-testid="filter-scenario-out"
              >
                <option value="">Select outgoing player...</option>
                {(playersQuery.data || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.primary_position || "MF"})</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {mode === "comparison" && (
          <div>
            <p className="auth-copy" style={{ marginBottom: "8px" }}>
              Select 2 to 4 candidates from recruitment or roster to evaluate side-by-side:
            </p>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              {(playersQuery.data || []).slice(0, 10).map((p) => {
                const isSelected = selectedCandidateIds.includes(p.id);
                return (
                  <button
                    key={p.id}
                    className={isSelected ? "outline-button primary-selected" : "outline-button"}
                    style={{
                      borderColor: isSelected ? "var(--cyan)" : "var(--line)",
                      background: isSelected ? "var(--cyan-soft)" : "transparent",
                    }}
                    onClick={() => {
                      if (isSelected) {
                        setSelectedCandidateIds(selectedCandidateIds.filter((id) => id !== p.id));
                      } else if (selectedCandidateIds.length < 4) {
                        setSelectedCandidateIds([...selectedCandidateIds, p.id]);
                      }
                    }}
                  >
                    {p.name} ({p.primary_position})
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 3. Decision Assessment Summary & Confidence Banner */}
      {decisionAssessment && (
        <div
          className="dashboard-card"
          style={{
            marginBottom: "20px",
            borderLeft: "3px solid var(--cyan)",
            background: "linear-gradient(135deg, rgba(49, 200, 206, 0.05), rgba(12, 18, 24, 0.95))",
          }}
          data-testid="decision-summary-card"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                <span className="eyebrow" style={{ color: "var(--cyan)" }}>
                  {decisionAssessment.decision_type} ASSESSMENT · ID: {decisionAssessment.decision_id.slice(0, 8)}
                </span>
                <span className="contract-badge" style={{ fontSize: "11px" }}>
                  Status: {decisionAssessment.confidence.data_status}
                </span>
              </div>
              <h2 style={{ margin: "0 0 6px 0", fontSize: "16px" }}>{decisionAssessment.summary}</h2>
              <p style={{ color: "var(--muted)", fontSize: "12.5px", margin: 0 }}>
                Analyzed <strong>{decisionAssessment.total_candidates_analyzed}</strong> candidate pool · Passed: <strong>{decisionAssessment.passed_candidates_count}</strong> · Excluded: <strong>{decisionAssessment.excluded_candidates_count}</strong>
              </p>
            </div>

            <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
              <div style={{ textAlign: "right" }}>
                <span className="metadata-label">Decision Confidence</span>
                <div style={{ fontSize: "15px", fontWeight: "600", color: "var(--cyan)" }}>
                  {decisionAssessment.confidence.confidence_tier}
                </div>
                <small style={{ color: "var(--muted)" }}>
                  Data: {(decisionAssessment.confidence.data_confidence * 100).toFixed(0)}% · Model: {(decisionAssessment.confidence.model_confidence * 100).toFixed(0)}%
                </small>
              </div>

              {decisionAssessment.evidence_graph && (
                <button
                  className="outline-button"
                  onClick={() => setEvidenceDrawerData(decisionAssessment.evidence_graph)}
                  data-testid="open-evidence-graph-button"
                >
                  <Network size={14} style={{ marginRight: 4 }} /> Trace Evidence DAG
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 4. Candidate Universe & Multi-Dimensional Comparison Table */}
      {(mode === "recruitment" || mode === "replacement") && activeRecommendations.length > 0 && (
        <div style={{ marginBottom: "28px" }} data-testid="candidate-comparison-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
            <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: "6px" }}>
              <Users size={16} color="var(--cyan)" />
              Candidate Recommendations ({activeRecommendations.length})
            </h3>
            <span style={{ fontSize: "12px", color: "var(--muted)" }}>
              Sorted deterministically across multi-factor evidence layers.
            </span>
          </div>

          <div className="player-table-wrap">
            <table className="compare-table" data-testid="candidates-matrix-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", width: "180px" }}>Player Profile</th>
                  <th>Target Role</th>
                  <th>Tactical Fit</th>
                  <th>Contribution</th>
                  {mode === "replacement" && <th>Similarity</th>}
                  <th>Estimated Value</th>
                  <th>Transfer Risk</th>
                  <th>Squad Impact</th>
                  <th>Confidence</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {activeRecommendations.map((cand, idx) => {
                  const isSelected = idx === activeCandidateIndex;
                  return (
                    <tr
                      key={cand.candidate_id}
                      style={{
                        background: isSelected ? "var(--surface-hover)" : undefined,
                        cursor: "pointer",
                      }}
                      onClick={() => setActiveCandidateIndex(idx)}
                      data-testid={`candidate-row-${idx}`}
                    >
                      <td style={{ textAlign: "left" }}>
                        <strong style={{ color: isSelected ? "var(--cyan)" : "var(--text)" }}>
                          {cand.player_name}
                        </strong>
                        <div style={{ fontSize: "11.5px", color: "var(--muted)" }}>
                          {cand.primary_position} · {cand.age?.toFixed(0)} y/o · {cand.current_club_name || "Club"}
                        </div>
                      </td>
                      <td>
                        <span className="contract-badge" style={{ fontSize: "11px" }}>
                          {cand.target_role}
                        </span>
                      </td>
                      <td>
                        <strong style={{ color: cand.tactical.tactical_fit_score >= 75 ? "var(--green)" : "var(--amber)" }}>
                          {cand.tactical.tactical_fit_score.toFixed(1)}%
                        </strong>
                      </td>
                      <td>
                        <strong>{cand.performance.contribution_rating.toFixed(1)}</strong>
                        <div style={{ fontSize: "10.5px", color: "var(--muted)" }}>
                          {cand.performance.trajectory}
                        </div>
                      </td>
                      {mode === "replacement" && (
                        <td>
                          <strong>{(cand.similarity.overall_similarity * 100).toFixed(0)}%</strong>
                        </td>
                      )}
                      <td>
                        <strong>€{(cand.market.estimated_value_eur / 1000000).toFixed(1)}M</strong>
                        <div style={{ fontSize: "10.5px", color: cand.market.affordability_status === "AFFORDABLE" ? "var(--green)" : "var(--amber)" }}>
                          {cand.market.affordability_status}
                        </div>
                      </td>
                      <td>
                        <span
                          className="contract-badge"
                          style={{
                            fontSize: "11px",
                            borderColor: cand.risk.risk_level === "LOW" ? "var(--green)" : (cand.risk.risk_level === "MEDIUM" ? "var(--amber)" : "var(--danger)"),
                            color: cand.risk.risk_level === "LOW" ? "var(--green)" : (cand.risk.risk_level === "MEDIUM" ? "var(--amber)" : "var(--danger)"),
                          }}
                        >
                          {cand.risk.risk_level}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: "12px", color: cand.squad_impact.net_squad_upgrade ? "var(--green)" : "var(--muted)" }}>
                          {cand.squad_impact.net_squad_upgrade ? "Upgrade" : "Depth"}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: "11.5px", color: "var(--muted-strong)" }}>
                          {cand.confidence.confidence_tier}
                        </span>
                      </td>
                      <td>
                        <button
                          className="ghost-button"
                          style={{ padding: "2px 8px", fontSize: "11px" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEvidenceDrawerData({
                              player_name: cand.player_name,
                              candidate_id: cand.candidate_id,
                              why_matches: cand.why_matches,
                              where_differs: cand.where_differs,
                              performance_rating: cand.performance.contribution_rating,
                              tactical_fit: cand.tactical.tactical_fit_score,
                              estimated_value_eur: cand.market.estimated_value_eur,
                              risk_score: cand.risk.overall_risk_score,
                              confidence_tier: cand.confidence.confidence_tier,
                              data_status: cand.confidence.data_status,
                            });
                          }}
                        >
                          Evidence
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 5. Deep Multi-Dimensional Candidate Breakdown */}
      {activeCandidate && (mode === "recruitment" || mode === "replacement") && (
        <div style={{ marginBottom: "28px" }} data-testid="candidate-deep-breakdown">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h3 style={{ margin: 0 }}>
              Deep Assessment: <span style={{ color: "var(--cyan)" }}>{activeCandidate.player_name}</span>
            </h3>
            <span className="eyebrow">
              {activeCandidate.performance.sample_minutes} mins played · {activeCandidate.performance.sample_matches} matches
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "16px" }}>
            {/* 5a. Player Intelligence & Performance */}
            <div className="dashboard-card">
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                <TrendingUp size={16} color="var(--cyan)" />
                <h4 style={{ margin: 0 }}>1. Performance & Trajectory</h4>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "10px" }}>
                <div>
                  <span className="metadata-label">Contribution Rating</span>
                  <div style={{ fontSize: "16px", fontWeight: "600" }}>{activeCandidate.performance.contribution_rating.toFixed(1)} / 100</div>
                </div>
                <div>
                  <span className="metadata-label">Peer Percentile</span>
                  <div style={{ fontSize: "16px", fontWeight: "600" }}>P{activeCandidate.performance.percentile_in_role.toFixed(0)}</div>
                </div>
                <div>
                  <span className="metadata-label">Offensive Impact</span>
                  <div style={{ fontSize: "14px", fontWeight: "500" }}>{activeCandidate.performance.offensive_impact.toFixed(1)}</div>
                </div>
                <div>
                  <span className="metadata-label">Defensive Impact</span>
                  <div style={{ fontSize: "14px", fontWeight: "500" }}>{activeCandidate.performance.defensive_impact.toFixed(1)}</div>
                </div>
              </div>
              <span className="contract-badge" style={{ fontSize: "11px" }}>
                Trajectory: {activeCandidate.performance.trajectory}
              </span>
            </div>

            {/* 5b. Tactical Fit */}
            <div className="dashboard-card">
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                <Radar size={16} color="var(--cyan)" />
                <h4 style={{ margin: 0 }}>2. Tactical Fit & System Role</h4>
              </div>
              <div style={{ marginBottom: "8px" }}>
                <span className="metadata-label">Tactical System Fit</span>
                <div style={{ fontSize: "16px", fontWeight: "600", color: "var(--cyan)" }}>
                  {activeCandidate.tactical.tactical_fit_score.toFixed(1)}% ({activeCandidate.tactical.target_role})
                </div>
                <small style={{ color: "var(--muted)" }}>System: {activeCandidate.tactical.system_name}</small>
              </div>
              <div style={{ fontSize: "12px", color: "var(--muted-strong)" }}>
                <strong>Tactical Strengths:</strong>
                <ul style={{ margin: "4px 0 0 0", paddingLeft: "18px" }}>
                  {activeCandidate.tactical.strengths.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>

            {/* 5c. Market & Valuation */}
            <div className="dashboard-card">
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                <DollarSign size={16} color="var(--cyan)" />
                <h4 style={{ margin: 0 }}>3. Market Valuation & Fee Range</h4>
              </div>
              <div style={{ marginBottom: "8px" }}>
                <span className="metadata-label">Predicted Baseline Value</span>
                <div style={{ fontSize: "16px", fontWeight: "600", color: "var(--green)" }}>
                  €{(activeCandidate.market.estimated_value_eur / 1000000).toFixed(2)}M
                </div>
                <small style={{ color: "var(--muted)" }}>
                  Range: €{(activeCandidate.market.fee_range_low_eur / 1000000).toFixed(1)}M – €{(activeCandidate.market.fee_range_high_eur / 1000000).toFixed(1)}M
                </small>
              </div>
              <div style={{ fontSize: "12px", color: "var(--muted-strong)" }}>
                <div>Affordability: <strong>{activeCandidate.market.affordability_status}</strong></div>
                <div>Comparables: {activeCandidate.market.comparable_transfers_count} historical market records</div>
              </div>
            </div>

            {/* 5d. Transfer Risk */}
            <div className="dashboard-card">
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                <ShieldAlert size={16} color="var(--cyan)" />
                <h4 style={{ margin: 0 }}>4. Transfer Risk Decomposition</h4>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "8px" }}>
                <div>
                  <span className="metadata-label">Overall Risk</span>
                  <div style={{ fontSize: "16px", fontWeight: "600" }}>{activeCandidate.risk.risk_level} ({(activeCandidate.risk.overall_risk_score * 100).toFixed(0)}%)</div>
                </div>
                <div>
                  <span className="metadata-label">Adaptation Risk</span>
                  <div style={{ fontSize: "14px" }}>{(activeCandidate.risk.adaptation_risk * 100).toFixed(0)}%</div>
                </div>
                <div>
                  <span className="metadata-label">Performance Risk</span>
                  <div style={{ fontSize: "14px" }}>{(activeCandidate.risk.performance_risk * 100).toFixed(0)}%</div>
                </div>
                <div>
                  <span className="metadata-label">Financial Risk</span>
                  <div style={{ fontSize: "14px" }}>{(activeCandidate.risk.financial_risk * 100).toFixed(0)}%</div>
                </div>
              </div>
            </div>

            {/* 5e. Squad Impact */}
            <div className="dashboard-card">
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                <Activity size={16} color="var(--cyan)" />
                <h4 style={{ margin: 0 }}>5. Squad Impact & Transition</h4>
              </div>
              <div style={{ fontSize: "12.5px", color: "var(--text)" }}>
                <div>Slot: <strong>{activeCandidate.squad_impact.formation_slot}</strong></div>
                <div>Depth Transition: {activeCandidate.squad_impact.depth_status_before} → <strong>{activeCandidate.squad_impact.depth_status_after}</strong></div>
                <div>Age Profile: {activeCandidate.squad_impact.age_profile_impact}</div>
                <div>Net Squad Upgrade: <strong>{activeCandidate.squad_impact.net_squad_upgrade ? "YES (Quality Improvement)" : "NO (Depth Cover)"}</strong></div>
              </div>
            </div>

            {/* 5f. Why Matches vs Where Differs */}
            <div className="dashboard-card" style={{ gridColumn: "span 2" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
                <FileText size={16} color="var(--cyan)" />
                <h4 style={{ margin: 0 }}>6. Explainable Rationale: Why Matches & Where Differs</h4>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div>
                  <span className="metadata-label" style={{ color: "var(--green)" }}>WHY THIS PLAYER MATCHES</span>
                  <ul style={{ margin: "6px 0 0 0", paddingLeft: "18px", fontSize: "12.5px" }}>
                    {activeCandidate.why_matches.map((item, idx) => (
                      <li key={idx} style={{ marginBottom: "4px" }}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <span className="metadata-label" style={{ color: "var(--amber)" }}>WHERE THIS PLAYER DIFFERS</span>
                  <ul style={{ margin: "6px 0 0 0", paddingLeft: "18px", fontSize: "12.5px" }}>
                    {activeCandidate.where_differs.map((item, idx) => (
                      <li key={idx} style={{ marginBottom: "4px" }}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 6. Scenario Simulation View */}
      {mode === "scenario" && scenarioQuery.data && (
        <div style={{ marginBottom: "28px" }} data-testid="scenario-simulation-results">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: "6px" }}>
              <GitCompare size={16} color="var(--cyan)" />
              Transfer Scenario & Match Impact Simulation
            </h3>
            <span className="contract-badge">COUNTERFACTUAL SIMULATION MODEL</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
            <div className="dashboard-card">
              <h4 style={{ margin: "0 0 10px 0" }}>Financial & Roster Expenditure</h4>
              <div style={{ fontSize: "13px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                  <span>Gross Expenditure:</span>
                  <strong>€{(scenarioQuery.data.estimated_total_expenditure_eur / 1000000).toFixed(1)}M</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                  <span>Gross Receipts:</span>
                  <strong>€{(scenarioQuery.data.estimated_total_receipts_eur / 1000000).toFixed(1)}M</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px", color: "var(--cyan)" }}>
                  <span>Net Transfer Spend:</span>
                  <strong>€{(scenarioQuery.data.net_financial_impact_eur / 1000000).toFixed(1)}M</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "10px" }}>
                  <span>Roster Headcount:</span>
                  <strong>{scenarioQuery.data.squad_headcount_before} → {scenarioQuery.data.squad_headcount_after} players</strong>
                </div>
              </div>
            </div>

            <div className="dashboard-card">
              <h4 style={{ margin: "0 0 10px 0" }}>Expected Match Prediction Impact</h4>
              {scenarioQuery.data.match_prediction_impact ? (
                <div style={{ fontSize: "13px" }}>
                  <div style={{ marginBottom: "8px" }}>
                    <span className="metadata-label">Baseline Match Win Probability</span>
                    <div style={{ fontSize: "15px", fontWeight: "600" }}>
                      {(scenarioQuery.data.match_prediction_impact.baseline_home_win_prob * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div style={{ marginBottom: "8px" }}>
                    <span className="metadata-label">Scenario Win Probability</span>
                    <div style={{ fontSize: "15px", fontWeight: "600", color: "var(--green)" }}>
                      {(scenarioQuery.data.match_prediction_impact.scenario_home_win_prob * 100).toFixed(1)}%
                    </div>
                  </div>
                  <small style={{ color: "var(--muted)" }}>
                    {scenarioQuery.data.match_prediction_impact.counterfactual_notes}
                  </small>
                </div>
              ) : (
                <div style={{ color: "var(--muted)", fontSize: "12.5px" }}>
                  No active fixture selected to evaluate match prediction impact.
                </div>
              )}
            </div>

            <div className="dashboard-card" style={{ gridColumn: "span 2" }}>
              <h4 style={{ margin: "0 0 8px 0" }}>Scenario Assumptions & Model Provenance</h4>
              <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "12.5px", color: "var(--muted-strong)" }}>
                {scenarioQuery.data.scenario_assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* 7. Candidate Comparison Matrix View */}
      {mode === "comparison" && comparisonQuery.data && (
        <div style={{ marginBottom: "28px" }} data-testid="comparison-matrix-view">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <h3 style={{ margin: 0 }}>Side-by-Side Dimensional Comparison</h3>
            <span className="contract-badge">NO SINGLE WINNER REDUCTION</span>
          </div>

          <div className="player-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", width: "160px" }}>Dimension</th>
                  {comparisonQuery.data.candidates.map((c) => (
                    <th key={c.candidate_id}>{c.player_name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Target Role</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}>{c.target_role}</td>
                  ))}
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Tactical Fit</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}><strong>{c.tactical.tactical_fit_score.toFixed(1)}%</strong></td>
                  ))}
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Contribution Rating</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}>{c.performance.contribution_rating.toFixed(1)}</td>
                  ))}
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Estimated Valuation</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}>€{(c.market.estimated_value_eur / 1000000).toFixed(1)}M</td>
                  ))}
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Transfer Risk</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}>
                      <span className="contract-badge">{c.risk.risk_level}</span>
                    </td>
                  ))}
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Net Squad Upgrade</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}>{c.squad_impact.net_squad_upgrade ? "Yes" : "No"}</td>
                  ))}
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}><strong>Data Confidence</strong></td>
                  {comparisonQuery.data.candidates.map((c) => (
                    <td key={c.candidate_id}>{c.confidence.confidence_tier}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <div className="dashboard-card" style={{ marginTop: "16px" }}>
            <h4 style={{ margin: "0 0 8px 0" }}>Dimensional Divergences</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "12.5px" }}>
              {Object.entries(comparisonQuery.data.dimensional_divergences || {}).map(([dim, diff]) => (
                <div key={dim}>
                  <strong style={{ color: "var(--cyan)" }}>{dim.toUpperCase()}:</strong> {diff}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 8. Excluded Candidates Breakdown (Hard Constraints Enforcement) */}
      {excludedSummaries.length > 0 && (
        <div className="dashboard-card" style={{ marginTop: "24px" }} data-testid="excluded-candidates-card">
          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}>
            <CircleAlert size={15} color="var(--amber)" />
            <h4 style={{ margin: 0 }}>Excluded Candidates ({excludedSummaries.length})</h4>
          </div>
          <p style={{ color: "var(--muted)", fontSize: "12px", margin: "0 0 10px 0" }}>
            The following players were evaluated by the recruitment engine but failed one or more non-negotiable hard constraints. Soft evidence does not override hard requirements.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "8px" }}>
            {excludedSummaries.slice(0, 8).map((ex, i) => (
              <div
                key={i}
                style={{
                  padding: "8px 12px",
                  borderRadius: "3px",
                  border: "1px solid var(--line)",
                  background: "var(--surface)",
                  fontSize: "12px",
                }}
              >
                <strong>{ex.player_name}</strong>
                <ul style={{ margin: "4px 0 0 0", paddingLeft: "16px", color: "var(--amber)" }}>
                  {ex.exclusion_reasons?.map((r, ri) => (
                    <li key={ri}>{r}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Traceable Evidence Drawer */}
      <EvidenceDrawer
        title="Decision Assessment Evidence DAG"
        evidence={evidenceDrawerData}
        onClose={() => setEvidenceDrawerData(null)}
      />
    </section>
  );
}
