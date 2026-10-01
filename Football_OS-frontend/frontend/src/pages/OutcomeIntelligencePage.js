import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle,
  Clock,
  Compass,
  Database,
  DollarSign,
  FileText,
  Filter,
  GitCommit,
  GitFork,
  HelpCircle,
  Layers,
  Lock,
  Play,
  Radar,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sliders,
  TrendingDown,
  TrendingUp,
  Users,
  Zap,
  BookOpen,
} from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
const OUTCOMES_API = `${BACKEND_URL}/api/v1/outcomes`;

export default function OutcomeIntelligencePage() {
  const [activeTab, setActiveTab] = useState('outcomes');
  const [loading, setLoading] = useState(false);
  const [selectedDecisionId, setSelectedDecisionId] = useState('dec_rec_timber_2023');

  // Surface 1: Decision Outcomes & Evaluations
  const [decisions, setDecisions] = useState([]);
  const [activeEvaluation, setActiveEvaluation] = useState(null);

  // Surface 2: Prediction Calibration
  const [calibrationWindow, setCalibrationWindow] = useState(30);
  const [calibrationReport, setCalibrationReport] = useState(null);

  // Surface 3: Transfer Realizations
  const [transfers, setTransfers] = useState([]);

  // Surface 4: Tactical Realizations
  const [tacticalReports, setTacticalReports] = useState([]);

  // Surface 5: Scenario Lifecycle
  const [scenarioLifecycles, setScenarioLifecycles] = useState([]);

  // Surface 6: Subgroup Performance
  const [subgroupsReport, setSubgroupsReport] = useState(null);

  // Surface 7: Decision Freshness & Benchmarks
  const [freshnessAssessments, setFreshnessAssessments] = useState([]);

  // Surface 8: Learning Signals & Challengers
  const [learningSignalsData, setLearningSignalsData] = useState({ learning_signals: [], pattern_reports: [], challenger_evaluations: [] });

  // Surface 9: Research Workspace
  const [researchDossiers, setResearchDossiers] = useState([]);
  const [newTopic, setNewTopic] = useState('High-Block Offside Trap Susceptibility');
  const [newHypothesis, setNewHypothesis] = useState('A defensive line height >48m elevates vulnerability to third-man runners.');
  const [newModality, setNewModality] = useState('HYPOTHESIS');
  const [newContent, setNewContent] = useState('Initial match study suggests 1.8 dangerous line-breaks per 90.');

  // Copilot V4 Console
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotResponse, setCopilotResponse] = useState(null);
  const [copilotLoading, setCopilotLoading] = useState(false);

  // Initial Data Fetching
  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    setLoading(true);
    try {
      const [decRes, calRes, transRes, tacRes, scenRes, subRes, freshRes, learnRes, resRes] = await Promise.all([
        axios.get(`${OUTCOMES_API}/decisions`).catch(() => ({ data: [] })),
        axios.get(`${OUTCOMES_API}/models/calibrated_multinomial_logit_v1/calibration?window_size=30`).catch(() => ({ data: null })),
        axios.get(`${OUTCOMES_API}/transfers`).catch(() => ({ data: [] })),
        axios.get(`${OUTCOMES_API}/tactical`).catch(() => ({ data: [] })),
        axios.get(`${OUTCOMES_API}/scenarios`).catch(() => ({ data: [] })),
        axios.get(`${OUTCOMES_API}/models/calibrated_multinomial_logit_v1/subgroups`).catch(() => ({ data: null })),
        axios.get(`${OUTCOMES_API}/freshness`).catch(() => ({ data: [] })),
        axios.get(`${OUTCOMES_API}/learning-signals`).catch(() => ({ data: { learning_signals: [], pattern_reports: [], challenger_evaluations: [] } })),
        axios.get(`${OUTCOMES_API}/research`).catch(() => ({ data: [] })),
      ]);

      setDecisions(decRes.data || []);
      setCalibrationReport(calRes.data || null);
      setTransfers(transRes.data || []);
      setTacticalReports(tacRes.data || []);
      setScenarioLifecycles(scenRes.data || []);
      setSubgroupsReport(subRes.data || null);
      setFreshnessAssessments(freshRes.data || []);
      setLearningSignalsData(learnRes.data || { learning_signals: [], pattern_reports: [], challenger_evaluations: [] });
      setResearchDossiers(resRes.data || []);

      // Load Timber default evaluation
      if (decRes.data && decRes.data.length > 0) {
        fetchDecisionEvaluation(decRes.data[0].decision_id);
      }
    } catch (e) {
      console.error('Failed to load outcome intelligence telemetry:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchDecisionEvaluation = async (decisionId) => {
    try {
      const res = await axios.get(`${OUTCOMES_API}/decisions/${decisionId}/evaluation`);
      setActiveEvaluation(res.data);
      setSelectedDecisionId(decisionId);
    } catch (e) {
      console.error('Failed to fetch decision evaluation:', e);
    }
  };

  const handleCalibrationWindowChange = async (w) => {
    setCalibrationWindow(w);
    try {
      const res = await axios.get(`${OUTCOMES_API}/models/calibrated_multinomial_logit_v1/calibration?window_size=${w}`);
      setCalibrationReport(res.data);
    } catch (e) {
      console.error('Failed to fetch window calibration:', e);
    }
  };

  const handleCreateResearchDossier = async () => {
    try {
      const payload = {
        topic: newTopic,
        hypothesis: newHypothesis,
        items: [
          {
            title: 'Initial Analytical Investigation',
            modality: newModality,
            content: newContent,
            evidence_source: 'analyst_workspace',
            confidence: 0.85,
          },
        ],
        created_by: 'lead_tactical_analyst',
      };
      const res = await axios.post(`${OUTCOMES_API}/research`, payload);
      setResearchDossiers([res.data, ...researchDossiers]);
      setNewTopic('');
      setNewHypothesis('');
      setNewContent('');
    } catch (e) {
      console.error('Failed to create research dossier:', e);
    }
  };

  const handleCopilotQuery = async (queryText) => {
    const q = queryText || copilotQuery;
    if (!q) return;
    setCopilotLoading(true);
    try {
      const res = await axios.post(`${OUTCOMES_API}/copilot`, {
        query: q,
        decision_id: selectedDecisionId,
      });
      setCopilotResponse(res.data);
    } catch (e) {
      console.error('Copilot query failed:', e);
    } finally {
      setCopilotLoading(false);
    }
  };

  return (
    <div className="outcome-lab-container" style={{ padding: '24px', backgroundColor: '#0b0f17', color: '#e2e8f0', minHeight: '100vh', fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* Header Banner */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1e293b', paddingBottom: '18px', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ backgroundColor: '#10b981', color: '#000', fontSize: '10px', fontWeight: 800, padding: '3px 8px', borderRadius: '4px', letterSpacing: '0.05em' }}>PHASE 14</span>
            <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Football Research & Outcome Intelligence OS</span>
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '6px 0 0 0', color: '#f8fafc' }}>Outcome-Aware Decision Intelligence 3.0</h1>
          <p style={{ color: '#64748b', fontSize: '13px', margin: '4px 0 0 0' }}>
            Retrospective evaluation, rolling prediction calibration, tactical fidelity, and non-causal institutional learning.
          </p>
        </div>

        {/* Global Epistemic Legend */}
        <div style={{ display: 'flex', gap: '8px', backgroundColor: '#111827', padding: '8px 12px', borderRadius: '8px', border: '1px solid #1f2937' }}>
          <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 700 }}>● OBSERVED</span>
          <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700 }}>● MODELLED</span>
          <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 700 }}>● COUNTERFACTUAL</span>
          <span style={{ fontSize: '11px', color: '#a855f7', fontWeight: 700 }}>● SCENARIO</span>
          <span style={{ fontSize: '11px', color: '#ec4899', fontWeight: 700 }}>● HYPOTHESIS</span>
        </div>
      </header>

      {/* Scout Copilot V4 Quick Inquiry Strip */}
      <section style={{ backgroundColor: '#131b2a', border: '1px solid #1e293b', borderRadius: '8px', padding: '14px 16px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <Compass size={18} style={{ color: '#38bdf8' }} />
          <input
            type="text"
            placeholder="Ask Copilot V4: 'What actually happened?', 'Where did the scenario diverge?', 'How accurate has this model been?'"
            value={copilotQuery}
            onChange={(e) => setCopilotQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCopilotQuery()}
            style={{ flex: 1, backgroundColor: '#090d14', border: '1px solid #263346', borderRadius: '6px', padding: '8px 12px', color: '#fff', fontSize: '13px' }}
          />
          <button
            onClick={() => handleCopilotQuery()}
            disabled={copilotLoading}
            style={{ backgroundColor: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', padding: '8px 14px', fontSize: '12px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
          >
            {copilotLoading ? <RefreshCw size={14} className="spin" /> : <Send size={14} />} Dispatch
          </button>
        </div>

        {/* Quick Question Chips */}
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px', overflowX: 'auto', paddingBottom: '2px' }}>
          {['What did we expect?', 'What actually happened?', 'Where did the scenario diverge?', 'How accurate has this model been in this competition?', 'Which recruitment decisions require review?'].map((q) => (
            <button
              key={q}
              onClick={() => { setCopilotQuery(q); handleCopilotQuery(q); }}
              style={{ backgroundColor: '#1a2436', color: '#94a3b8', border: '1px solid #2a3850', borderRadius: '14px', padding: '3px 10px', fontSize: '11px', cursor: 'pointer', whiteSpace: 'nowrap' }}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Copilot Response Panel */}
        {copilotResponse && (
          <div style={{ marginTop: '12px', backgroundColor: '#080c14', border: '1px solid #2a3a54', borderRadius: '6px', padding: '12px', fontSize: '13px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ color: '#38bdf8', fontWeight: 700, fontSize: '11px' }}>CLASS: {copilotResponse.query_class}</span>
              {copilotResponse.evidence_digest && (
                <span style={{ color: '#64748b', fontSize: '10px', fontFamily: 'monospace' }}>DIGEST: {copilotResponse.evidence_digest.slice(0, 16)}...</span>
              )}
            </div>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', color: '#e2e8f0', lineHeight: 1.5 }}>
              {copilotResponse.response}
            </pre>
          </div>
        )}
      </section>

      {/* Navigation Tabs (9 Canonical Surfaces) */}
      <nav style={{ display: 'flex', gap: '4px', borderBottom: '1px solid #1e293b', marginBottom: '20px', overflowX: 'auto' }}>
        {[
          { id: 'outcomes', label: '1. Decision Outcomes', icon: TargetIcon },
          { id: 'calibration', label: '2. Prediction Calibration', icon: Activity },
          { id: 'transfers', label: '3. Transfer Realization', icon: DollarSign },
          { id: 'tactical', label: '4. Tactical Realization', icon: Radar },
          { id: 'scenarios', label: '5. Scenario Accuracy', icon: GitFork },
          { id: 'monitoring', label: '6. Model Monitoring', icon: BarChart3 },
          { id: 'freshness', label: '7. Decision Freshness', icon: Clock },
          { id: 'learning', label: '8. Learning Signals', icon: Zap },
          { id: 'research', label: '9. Research Workspace', icon: BookOpen },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: activeTab === id ? '#1e293b' : 'transparent',
              color: activeTab === id ? '#f8fafc' : '#64748b',
              border: 'none',
              borderBottom: activeTab === id ? '2px solid #38bdf8' : '2px solid transparent',
              padding: '10px 14px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </nav>

      {/* Surface 1: Decision Outcomes */}
      {activeTab === 'outcomes' && (
        <section style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '20px' }}>
          {/* Decision Selector Card */}
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '16px' }}>
            <h3 style={{ fontSize: '14px', margin: '0 0 12px 0', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Finalized Decisions</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {decisions.map((d) => (
                <div
                  key={d.decision_id}
                  onClick={() => fetchDecisionEvaluation(d.decision_id)}
                  style={{
                    backgroundColor: selectedDecisionId === d.decision_id ? '#1e293b' : '#0d131f',
                    border: selectedDecisionId === d.decision_id ? '1px solid #38bdf8' : '1px solid #1e293b',
                    borderRadius: '6px',
                    padding: '10px 12px',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>{d.historical_record.project_name}</span>
                    <span style={{ fontSize: '10px', backgroundColor: '#064e3b', color: '#34d399', padding: '2px 6px', borderRadius: '4px' }}>
                      {d.retrospective_section?.overall_alignment || 'EVALUATING'}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>ID: {d.decision_id}</div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>Scenario: {d.historical_record.chosen_scenario_name}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Realization Multi-Metric Comparison Matrix */}
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '18px' }}>
            {activeEvaluation ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #1f2937', paddingBottom: '12px', marginBottom: '16px' }}>
                  <div>
                    <h2 style={{ fontSize: '18px', margin: 0, color: '#f8fafc' }}>
                      Retrospective Evaluation: {activeEvaluation.subject_name}
                    </h2>
                    <span style={{ fontSize: '12px', color: '#64748b' }}>Window: {activeEvaluation.evaluation_window} · Evaluated: {activeEvaluation.evaluated_at.slice(0, 10)}</span>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{
                      display: 'inline-block',
                      backgroundColor: activeEvaluation.overall_alignment === 'ALIGNED' ? '#064e3b' : '#78350f',
                      color: activeEvaluation.overall_alignment === 'ALIGNED' ? '#34d399' : '#fcd34d',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontWeight: 700,
                      fontSize: '12px',
                    }}>
                      ALIGNMENT: {activeEvaluation.overall_alignment}
                    </span>
                  </div>
                </div>

                {/* Dense Multi-Metric Grid */}
                <h4 style={{ fontSize: '13px', margin: '0 0 10px 0', color: '#94a3b8' }}>Expectation vs Realization Multi-Metric Matrix</h4>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left', marginBottom: '18px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #263346', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                      <th style={{ padding: '8px 10px' }}>Metric</th>
                      <th style={{ padding: '8px 10px' }}>Expected (MODELLED)</th>
                      <th style={{ padding: '8px 10px' }}>Realized (OBSERVED)</th>
                      <th style={{ padding: '8px 10px' }}>Delta</th>
                      <th style={{ padding: '8px 10px' }}>Tolerance</th>
                      <th style={{ padding: '8px 10px' }}>Alignment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeEvaluation.metric_comparisons.map((m) => (
                      <tr key={m.metric_name} style={{ borderBottom: '1px solid #1a2436' }}>
                        <td style={{ padding: '10px', fontWeight: 600, color: '#f8fafc' }}>{m.metric_name}</td>
                        <td style={{ padding: '10px', color: '#38bdf8' }}>{m.expected_value.toLocaleString()} {m.unit}</td>
                        <td style={{ padding: '10px', color: '#10b981', fontWeight: 600 }}>{m.realized_value.toLocaleString()} {m.unit}</td>
                        <td style={{ padding: '10px', color: m.is_within_tolerance ? '#94a3b8' : '#f87171' }}>
                          {m.relative_delta_pct > 0 ? `+${m.relative_delta_pct}%` : `${m.relative_delta_pct}%`}
                        </td>
                        <td style={{ padding: '10px', color: '#64748b' }}>±{m.tolerance_band_pct}%</td>
                        <td style={{ padding: '10px' }}>
                          <span style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: m.is_within_tolerance ? '#064e3b' : '#7f1d1d',
                            color: m.is_within_tolerance ? '#34d399' : '#f87171',
                          }}>
                            {m.directional_alignment}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Non-Causal Qualitative Findings */}
                <h4 style={{ fontSize: '13px', margin: '0 0 8px 0', color: '#94a3b8' }}>Associative Realization Findings (Non-Causal Grounding)</h4>
                <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '12px' }}>
                  {activeEvaluation.findings.map((f, i) => (
                    <div key={i} style={{ fontSize: '12px', color: '#cbd5e1', marginBottom: '6px' }}>
                      • {f}
                    </div>
                  ))}
                </div>

                {/* Process Quality & Error Taxonomy Diagnosis */}
                {activeEvaluation.divergence_diagnostic && (
                  <div style={{ marginTop: '16px', backgroundColor: '#131b28', border: '1px solid #243448', borderRadius: '6px', padding: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>DIVERGENCE ROOT ERROR DIAGNOSTIC</span>
                      <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 600 }}>PRIMARY: {activeEvaluation.divergence_diagnostic.primary_category}</span>
                    </div>
                    {Object.entries(activeEvaluation.divergence_diagnostic.category_explanations).map(([cat, exp]) => (
                      <div key={cat} style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>
                        <strong style={{ color: '#e2e8f0' }}>[{cat}]:</strong> {exp}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>Select a decision record to view retrospective realization telemetry.</div>
            )}
          </div>
        </section>
      )}

      {/* Surface 2: Prediction Calibration */}
      {activeTab === 'calibration' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h2 style={{ fontSize: '18px', margin: 0, color: '#f8fafc' }}>Rolling Prediction Calibration Feedback</h2>
              <p style={{ fontSize: '12px', color: '#64748b', margin: '4px 0 0 0' }}>
                Multi-class Log Loss, Brier quadratic scoring rule, and Expected Calibration Error (ECE) across sliding verification windows.
              </p>
            </div>
            {/* Window Selector */}
            <div style={{ display: 'flex', gap: '6px' }}>
              {[15, 30, 50, 100].map((w) => (
                <button
                  key={w}
                  onClick={() => handleCalibrationWindowChange(w)}
                  style={{
                    backgroundColor: calibrationWindow === w ? '#2563eb' : '#1e293b',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '6px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Window {w}
                </button>
              ))}
            </div>
          </div>

          {calibrationReport && (
            <div>
              {/* Top Level Metric Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '14px', marginBottom: '20px' }}>
                <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '14px' }}>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase' }}>Multi-Class Log Loss</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#38bdf8', marginTop: '4px' }}>{calibrationReport.log_loss.toFixed(4)}</div>
                  <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>Baseline Random: ~1.0986</div>
                </div>
                <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '14px' }}>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase' }}>Brier Score</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#10b981', marginTop: '4px' }}>{calibrationReport.brier_score.toFixed(4)}</div>
                  <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>Baseline Random: ~0.6670</div>
                </div>
                <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '14px' }}>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase' }}>Expected Cal Error (ECE)</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#f59e0b', marginTop: '4px' }}>{calibrationReport.ece.toFixed(4)}</div>
                  <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>Max Bin Gap: {calibrationReport.mce.toFixed(4)}</div>
                </div>
                <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '14px' }}>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase' }}>Reliability Curve Slope</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#a855f7', marginTop: '4px' }}>{calibrationReport.calibration_slope.toFixed(3)}</div>
                  <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>
                    Target: 1.000 (Intercept {calibrationReport.calibration_intercept >= 0 ? '+' : ''}{calibrationReport.calibration_intercept ? calibrationReport.calibration_intercept.toFixed(3) : '0.000'})
                  </div>
                </div>
                <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '14px' }}>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase' }}>Sample Size (N)</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc', marginTop: '4px' }}>{calibrationReport.sample_size}</div>
                  <div style={{ fontSize: '10px', color: '#34d399', marginTop: '2px' }}>Status: {calibrationReport.evaluation_status}</div>
                </div>
              </div>

              {/* 10-Bin Reliability Curve Table */}
              <h4 style={{ fontSize: '13px', margin: '0 0 10px 0', color: '#94a3b8' }}>10-Decile Reliability Bin Distribution</h4>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #263346', color: '#64748b' }}>
                    <th style={{ padding: '8px' }}>Bin Range</th>
                    <th style={{ padding: '8px' }}>Observations (Count)</th>
                    <th style={{ padding: '8px' }}>Mean Forecast Confidence</th>
                    <th style={{ padding: '8px' }}>Empirical Win Accuracy</th>
                    <th style={{ padding: '8px' }}>Calibration Gap</th>
                  </tr>
                </thead>
                <tbody>
                  {calibrationReport.reliability_bins.map((b) => (
                    <tr key={b.bin_index} style={{ borderBottom: '1px solid #1a2436' }}>
                      <td style={{ padding: '8px', color: '#f8fafc', fontWeight: 600 }}>{b.range}</td>
                      <td style={{ padding: '8px', color: '#94a3b8' }}>{b.count} fixtures</td>
                      <td style={{ padding: '8px', color: '#38bdf8' }}>{(b.avg_confidence * 100).toFixed(1)}%</td>
                      <td style={{ padding: '8px', color: '#10b981', fontWeight: 600 }}>{(b.empirical_accuracy * 100).toFixed(1)}%</td>
                      <td style={{ padding: '8px', color: b.calibration_gap > 0.05 ? '#f87171' : '#34d399' }}>
                        {(b.calibration_gap * 100).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Surface 3: Transfer Realizations */}
      {activeTab === 'transfers' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 12px 0', color: '#f8fafc' }}>Completed Transfer Realizations (Ledger Audit)</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #263346', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                <th style={{ padding: '8px 10px' }}>Outcome ID</th>
                <th style={{ padding: '8px 10px' }}>Player ID</th>
                <th style={{ padding: '8px 10px' }}>Metric</th>
                <th style={{ padding: '8px 10px' }}>Realized Value</th>
                <th style={{ padding: '8px 10px' }}>Verified Source</th>
                <th style={{ padding: '8px 10px' }}>Observed At</th>
                <th style={{ padding: '8px 10px' }}>SHA-256 Digest</th>
              </tr>
            </thead>
            <tbody>
              {transfers.map((t) => (
                <tr key={t.outcome_id} style={{ borderBottom: '1px solid #1a2436' }}>
                  <td style={{ padding: '10px', color: '#38bdf8', fontWeight: 600 }}>{t.outcome_id}</td>
                  <td style={{ padding: '10px', color: '#f8fafc' }}>{t.player_id}</td>
                  <td style={{ padding: '10px', color: '#94a3b8' }}>{t.metric}</td>
                  <td style={{ padding: '10px', color: '#10b981', fontWeight: 700 }}>€{(t.value / 1e6).toFixed(1)}M</td>
                  <td style={{ padding: '10px', color: '#cbd5e1' }}>{t.source}</td>
                  <td style={{ padding: '10px', color: '#64748b' }}>{t.observed_at.slice(0, 10)}</td>
                  <td style={{ padding: '10px', color: '#64748b', fontFamily: 'monospace', fontSize: '11px' }}>{t.record_digest.slice(0, 16)}...</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Surface 4: Tactical Realizations */}
      {activeTab === 'tactical' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 12px 0', color: '#f8fafc' }}>Tactical Realization Fidelity</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {tacticalReports.map((r) => (
              <div key={r.report_id} style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div>
                    <h3 style={{ fontSize: '15px', margin: 0, color: '#f8fafc' }}>Scenario: {r.scenario_id} ({r.evaluation_window})</h3>
                    <span style={{ fontSize: '12px', color: '#64748b' }}>Simulated: {r.simulated_formation} · Observed Primary: {r.primary_observed_formation}</span>
                  </div>
                  <span style={{ backgroundColor: '#064e3b', color: '#34d399', padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 700 }}>
                    {r.tactical_state}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '12px' }}>
                  {r.components.map((c, i) => (
                    <div key={i} style={{ backgroundColor: '#131b28', padding: '10px', borderRadius: '4px', border: '1px solid #202d3e' }}>
                      <div style={{ fontSize: '10px', color: '#64748b' }}>{c.component_type}</div>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: '#e2e8f0', marginTop: '2px' }}>{c.simulated_state} → {c.observed_state}</div>
                      <div style={{ fontSize: '11px', color: c.is_aligned ? '#34d399' : '#f87171', marginTop: '4px' }}>
                        {c.is_aligned ? '✓ Aligned' : '✗ Divergent'}
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                  {r.findings.map((f, idx) => <div key={idx}>• {f}</div>)}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Surface 5: Scenario Accuracy */}
      {activeTab === 'scenarios' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 12px 0', color: '#f8fafc' }}>Scenario Lifecycle Realization Tracker</h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #263346', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                <th style={{ padding: '8px 10px' }}>Scenario Name</th>
                <th style={{ padding: '8px 10px' }}>Status</th>
                <th style={{ padding: '8px 10px' }}>Simulated At</th>
                <th style={{ padding: '8px 10px' }}>Outcomes Observed</th>
                <th style={{ padding: '8px 10px' }}>Divergence Findings</th>
                <th style={{ padding: '8px 10px' }}>Immutable Hash</th>
              </tr>
            </thead>
            <tbody>
              {scenarioLifecycles.map((s) => (
                <tr key={s.scenario_id} style={{ borderBottom: '1px solid #1a2436' }}>
                  <td style={{ padding: '10px', color: '#f8fafc', fontWeight: 600 }}>{s.scenario_name}</td>
                  <td style={{ padding: '10px' }}>
                    <span style={{ backgroundColor: '#064e3b', color: '#34d399', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700 }}>
                      {s.realization_status}
                    </span>
                  </td>
                  <td style={{ padding: '10px', color: '#64748b' }}>{s.simulated_at.slice(0, 10)}</td>
                  <td style={{ padding: '10px', color: '#38bdf8', fontWeight: 600 }}>{s.realized_outcomes_count} records</td>
                  <td style={{ padding: '10px', color: '#94a3b8' }}>{s.divergence_summary[0] || 'None noted'}</td>
                  <td style={{ padding: '10px', color: '#64748b', fontFamily: 'monospace', fontSize: '11px' }}>{s.original_scenario_hash.slice(0, 16)}...</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Surface 6: Model Monitoring (Subgroups) */}
      {activeTab === 'monitoring' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div>
              <h2 style={{ fontSize: '18px', margin: 0, color: '#f8fafc' }}>Contextual Subgroup Performance (Zero Silent Averaging)</h2>
              <span style={{ fontSize: '12px', color: '#64748b' }}>Exposes sample sizes (N) and error rates across competitions, age bands, and OOD states.</span>
            </div>
          </div>
          {subgroupsReport && (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #263346', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                  <th style={{ padding: '8px 10px' }}>Dimension</th>
                  <th style={{ padding: '8px 10px' }}>Slice Value</th>
                  <th style={{ padding: '8px 10px' }}>Sample (N)</th>
                  <th style={{ padding: '8px 10px' }}>Log Loss</th>
                  <th style={{ padding: '8px 10px' }}>Brier Score</th>
                  <th style={{ padding: '8px 10px' }}>Empirical Accuracy</th>
                  <th style={{ padding: '8px 10px' }}>Alert Level</th>
                </tr>
              </thead>
              <tbody>
                {subgroupsReport.slices.map((s, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid #1a2436' }}>
                    <td style={{ padding: '10px', color: '#94a3b8' }}>{s.dimension}</td>
                    <td style={{ padding: '10px', color: '#f8fafc', fontWeight: 600 }}>{s.slice_value}</td>
                    <td style={{ padding: '10px', color: s.sample_size < 10 ? '#f59e0b' : '#38bdf8' }}>{s.sample_size} fixtures</td>
                    <td style={{ padding: '10px', color: '#e2e8f0' }}>{s.log_loss ? s.log_loss.toFixed(4) : '—'}</td>
                    <td style={{ padding: '10px', color: '#e2e8f0' }}>{s.brier_score ? s.brier_score.toFixed(4) : '—'}</td>
                    <td style={{ padding: '10px', color: '#10b981', fontWeight: 600 }}>{s.accuracy ? `${(s.accuracy * 100).toFixed(1)}%` : '—'}</td>
                    <td style={{ padding: '10px' }}>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: s.alert_level === 'NORMAL' ? '#064e3b' : s.alert_level === 'MONITOR' ? '#78350f' : '#7f1d1d',
                        color: s.alert_level === 'NORMAL' ? '#34d399' : s.alert_level === 'MONITOR' ? '#fcd34d' : '#f87171',
                      }}>
                        {s.alert_level}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {/* Surface 7: Decision Freshness */}
      {activeTab === 'freshness' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 12px 0', color: '#f8fafc' }}>Decision Freshness V2 & Versioned Benchmarks</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
            {freshnessAssessments.map((a) => (
              <div key={a.assessment_id} style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ fontSize: '15px', margin: 0, color: '#f8fafc' }}>Decision: {a.decision_id}</h3>
                  <span style={{
                    backgroundColor: a.freshness_state === 'FRESH' ? '#064e3b' : a.freshness_state === 'AGING' ? '#1e3a8a' : '#78350f',
                    color: a.freshness_state === 'FRESH' ? '#34d399' : a.freshness_state === 'AGING' ? '#60a5fa' : '#fcd34d',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 700,
                  }}>
                    {a.freshness_state} (Staleness: {a.staleness_score})
                  </span>
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>Action: {a.action_required}</div>
                <div style={{ marginTop: '10px' }}>
                  <div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Material Shift Telemetry:</div>
                  {a.material_changes.map((m, idx) => (
                    <div key={idx} style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '3px' }}>
                      • <strong>{m.type}:</strong> {m.detail}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Surface 8: Learning Signals & Challengers */}
      {activeTab === 'learning' && (
        <section style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 12px 0', color: '#f8fafc' }}>Governed Institutional Learning & Challenger Models</h2>
          {/* Challenger Governance Card */}
          <div style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '16px', marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ fontSize: '15px', margin: 0, color: '#f8fafc' }}>Champion vs Challenger Evaluation Report</h3>
              <span style={{ backgroundColor: '#0284c7', color: '#fff', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700 }}>
                {learningSignalsData.challenger_evaluations[0]?.governed_recommendation || 'CHALLENGER_RECOMMENDED'}
              </span>
            </div>
            {learningSignalsData.challenger_evaluations[0] && (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '12px' }}>
                  <div style={{ backgroundColor: '#131b28', padding: '10px', borderRadius: '4px' }}>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>Champion Log Loss</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>{learningSignalsData.challenger_evaluations[0].champion_log_loss.toFixed(4)}</div>
                  </div>
                  <div style={{ backgroundColor: '#131b28', padding: '10px', borderRadius: '4px' }}>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>Challenger Log Loss</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#10b981' }}>{learningSignalsData.challenger_evaluations[0].challenger_log_loss.toFixed(4)}</div>
                  </div>
                  <div style={{ backgroundColor: '#131b28', padding: '10px', borderRadius: '4px' }}>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>Champion ECE</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>{learningSignalsData.challenger_evaluations[0].champion_ece.toFixed(4)}</div>
                  </div>
                  <div style={{ backgroundColor: '#131b28', padding: '10px', borderRadius: '4px' }}>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>Challenger ECE</div>
                    <div style={{ fontSize: '16px', fontWeight: 700, color: '#10b981' }}>{learningSignalsData.challenger_evaluations[0].challenger_ece.toFixed(4)}</div>
                  </div>
                </div>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                  {learningSignalsData.challenger_evaluations[0].promotion_notes.map((n, i) => <div key={i}>• {n}</div>)}
                </div>
              </div>
            )}
          </div>

          {/* Active Learning Signals */}
          <h3 style={{ fontSize: '14px', margin: '0 0 10px 0', color: '#94a3b8' }}>Institutional Divergence Signals</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {learningSignalsData.learning_signals.map((s) => (
              <div key={s.signal_id} style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>{s.target_component} · {s.trigger_metric}</span>
                  <span style={{ fontSize: '11px', color: '#f59e0b', fontWeight: 700 }}>ACTION: {s.action_state}</span>
                </div>
                <p style={{ fontSize: '12px', color: '#cbd5e1', margin: '6px 0' }}>{s.description}</p>
                <div style={{ fontSize: '11px', color: '#64748b' }}>
                  {s.evidence_summary.map((e, idx) => <span key={idx} style={{ marginRight: '12px' }}>• {e}</span>)}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Surface 9: Research Workspace */}
      {activeTab === 'research' && (
        <section style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: '20px' }}>
          {/* New Dossier Form */}
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '18px' }}>
            <h3 style={{ fontSize: '15px', margin: '0 0 12px 0', color: '#f8fafc' }}>New Research Dossier</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8' }}>Research Topic</label>
                <input
                  type="text"
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  style={{ width: '100%', backgroundColor: '#090d14', border: '1px solid #263346', borderRadius: '4px', padding: '6px 10px', color: '#fff', fontSize: '12px', marginTop: '4px' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8' }}>Conjectural Hypothesis</label>
                <textarea
                  value={newHypothesis}
                  onChange={(e) => setNewHypothesis(e.target.value)}
                  rows={3}
                  style={{ width: '100%', backgroundColor: '#090d14', border: '1px solid #263346', borderRadius: '4px', padding: '6px 10px', color: '#fff', fontSize: '12px', marginTop: '4px' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8' }}>Epistemic Modality</label>
                <select
                  value={newModality}
                  onChange={(e) => setNewModality(e.target.value)}
                  style={{ width: '100%', backgroundColor: '#090d14', border: '1px solid #263346', borderRadius: '4px', padding: '6px 10px', color: '#fff', fontSize: '12px', marginTop: '4px' }}
                >
                  <option value="HYPOTHESIS">HYPOTHESIS (Unverified Conjecture)</option>
                  <option value="ANALYSIS">ANALYSIS (Statistical Study)</option>
                  <option value="MODELLED">MODELLED (Algorithmic Output)</option>
                  <option value="OBSERVED">OBSERVED (Empirical Telemetry)</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8' }}>Initial Finding / Content</label>
                <textarea
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  rows={3}
                  style={{ width: '100%', backgroundColor: '#090d14', border: '1px solid #263346', borderRadius: '4px', padding: '6px 10px', color: '#fff', fontSize: '12px', marginTop: '4px' }}
                />
              </div>
              <button
                onClick={handleCreateResearchDossier}
                style={{ backgroundColor: '#2563eb', color: '#fff', border: 'none', borderRadius: '4px', padding: '8px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', marginTop: '6px' }}
              >
                Record Research Dossier
              </button>
            </div>
          </div>

          {/* Dossiers List */}
          <div style={{ backgroundColor: '#111827', border: '1px solid #1f2937', borderRadius: '8px', padding: '18px' }}>
            <h3 style={{ fontSize: '15px', margin: '0 0 12px 0', color: '#f8fafc' }}>Active Research Studies</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {researchDossiers.map((d) => (
                <div key={d.dossier_id} style={{ backgroundColor: '#0d131f', border: '1px solid #1e293b', borderRadius: '6px', padding: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h4 style={{ fontSize: '14px', margin: 0, color: '#f8fafc' }}>{d.topic}</h4>
                    <span style={{ fontSize: '10px', backgroundColor: '#1e3a8a', color: '#60a5fa', padding: '2px 6px', borderRadius: '4px', fontWeight: 700 }}>
                      {d.validation_status}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#ec4899', fontStyle: 'italic', margin: '6px 0' }}>
                    Hypothesis: {d.hypothesis}
                  </p>
                  <div style={{ marginTop: '10px', borderTop: '1px solid #1e293b', paddingTop: '8px' }}>
                    {d.items.map((item, idx) => (
                      <div key={idx} style={{ fontSize: '12px', color: '#cbd5e1', marginBottom: '6px' }}>
                        <span style={{
                          fontSize: '9px',
                          fontWeight: 800,
                          padding: '1px 5px',
                          borderRadius: '3px',
                          backgroundColor: item.modality === 'OBSERVED' ? '#064e3b' : item.modality === 'HYPOTHESIS' ? '#831843' : '#1e3a8a',
                          color: item.modality === 'OBSERVED' ? '#34d399' : item.modality === 'HYPOTHESIS' ? '#f472b6' : '#60a5fa',
                          marginRight: '6px',
                        }}>
                          {item.modality}
                        </span>
                        {item.content}
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: '10px', color: '#64748b', marginTop: '6px' }}>Digest: {d.digest ? d.digest.slice(0, 16) : '—'}...</div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function TargetIcon(props) {
  return <CheckCircle {...props} />;
}
