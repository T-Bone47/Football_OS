import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart2,
  BookOpen,
  CheckCircle2,
  Compass,
  Database,
  ExternalLink,
  FileText,
  Filter,
  Flame,
  GitBranch,
  Layers,
  Lock,
  Network,
  RefreshCw,
  Search,
  Send,
  Shield,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  getResearchQuestions,
  getResearchHypotheses,
  getResearchCohorts,
  getResearchExperiments,
  getResearchPatterns,
  getCrossCompetitionEvaluations,
  getLeagueTranslations,
  getPlayerTrajectories,
  getRoleTransitions,
  getTacticalPatterns,
  getTransferMarketResearch,
  getModelErrorResearch,
  getFeatureCandidates,
  getGlobalValidationMatrix,
  getResearchChallengers,
  getResearchEvidenceGraph,
  queryResearchCopilot,
} from '@/lib/footballApi';

export default function ResearchPage() {
  const [activeTab, setActiveTab] = useState('questions');
  const [loading, setLoading] = useState(false);

  // 12 surfaces state
  const [questions, setQuestions] = useState([]);
  const [hypotheses, setHypotheses] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [patterns, setPatterns] = useState([]);
  const [crossCompetition, setCrossCompetition] = useState([]);
  const [leagueTranslations, setLeagueTranslations] = useState([]);
  const [trajectories, setTrajectories] = useState([]);
  const [roleTransitions, setRoleTransitions] = useState([]);
  const [tacticalPatterns, setTacticalPatterns] = useState([]);
  const [transferMarket, setTransferMarket] = useState(null);
  const [modelErrors, setModelErrors] = useState([]);
  const [featureCandidates, setFeatureCandidates] = useState([]);
  const [validationMatrix, setValidationMatrix] = useState(null);
  const [challengers, setChallengers] = useState([]);
  const [evidenceGraph, setEvidenceGraph] = useState(null);

  // Copilot V5
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotResponse, setCopilotResponse] = useState(null);
  const [copilotLoading, setCopilotLoading] = useState(false);

  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    setLoading(true);
    try {
      const [
        qRes,
        hRes,
        cRes,
        expRes,
        patRes,
        ccRes,
        ltRes,
        trRes,
        rtRes,
        tpRes,
        tmRes,
        meRes,
        fcRes,
        vmRes,
        chRes,
        egRes,
      ] = await Promise.allSettled([
        getResearchQuestions(),
        getResearchHypotheses(),
        getResearchCohorts(),
        getResearchExperiments(),
        getResearchPatterns(),
        getCrossCompetitionEvaluations(),
        getLeagueTranslations(),
        getPlayerTrajectories(),
        getRoleTransitions(),
        getTacticalPatterns(),
        getTransferMarketResearch(),
        getModelErrorResearch(),
        getFeatureCandidates(),
        getGlobalValidationMatrix(),
        getResearchChallengers(),
        getResearchEvidenceGraph('global_research_v15'),
      ]);

      if (qRes.status === 'fulfilled') setQuestions(qRes.value || []);
      if (hRes.status === 'fulfilled') setHypotheses(hRes.value || []);
      if (cRes.status === 'fulfilled') setCohorts(cRes.value || []);
      if (expRes.status === 'fulfilled') setExperiments(expRes.value || []);
      if (patRes.status === 'fulfilled') setPatterns(patRes.value || []);
      if (ccRes.status === 'fulfilled') setCrossCompetition(ccRes.value || []);
      if (ltRes.status === 'fulfilled') setLeagueTranslations(ltRes.value || []);
      if (trRes.status === 'fulfilled') setTrajectories(trRes.value || []);
      if (rtRes.status === 'fulfilled') setRoleTransitions(rtRes.value || []);
      if (tpRes.status === 'fulfilled') setTacticalPatterns(tpRes.value || []);
      if (tmRes.status === 'fulfilled') setTransferMarket(tmRes.value || null);
      if (meRes.status === 'fulfilled') setModelErrors(meRes.value || []);
      if (fcRes.status === 'fulfilled') setFeatureCandidates(fcRes.value || []);
      if (vmRes.status === 'fulfilled') setValidationMatrix(vmRes.value || null);
      if (chRes.status === 'fulfilled') setChallengers(chRes.value || []);
      if (egRes.status === 'fulfilled') setEvidenceGraph(egRes.value || null);
    } catch (e) {
      console.error('Failed to load research data', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCopilotSubmit = async (e) => {
    e?.preventDefault();
    if (!copilotQuery.trim()) return;
    setCopilotLoading(true);
    try {
      const res = await queryResearchCopilot({ query: copilotQuery });
      setCopilotResponse(res);
    } catch (err) {
      setCopilotResponse({
        query_class: 'ERROR',
        summary_answer: 'Analytical inquiry encountered an execution error.',
        evidence_items: [],
        confidence: 0,
        data_sufficiency: 'UNAVAILABLE',
        non_causal_statement: 'System encountered a processing failure.',
      });
    } finally {
      setCopilotLoading(false);
    }
  };

  const renderModalityBadge = (modality) => {
    switch (modality) {
      case 'OBSERVED':
      case 'FACT':
        return <span className="badge badge-success" style={{ background: '#059669', color: '#fff', fontSize: '10px' }}>FACT / OBSERVED</span>;
      case 'HYPOTHESIS':
        return <span className="badge badge-warning" style={{ background: '#d97706', color: '#fff', fontSize: '10px' }}>HYPOTHESIS</span>;
      case 'MODELLED':
      case 'MODEL':
        return <span className="badge badge-info" style={{ background: '#2563eb', color: '#fff', fontSize: '10px' }}>MODELLED</span>;
      case 'COUNTERFACTUAL':
      case 'SCENARIO':
        return <span className="badge badge-danger" style={{ background: '#7c3aed', color: '#fff', fontSize: '10px' }}>SCENARIO / CF</span>;
      default:
        return <span className="badge badge-secondary" style={{ background: '#475569', color: '#fff', fontSize: '10px' }}>ANALYSIS</span>;
    }
  };

  return (
    <div className="intelligence-page" data-testid="global-scout-research-workspace" style={{ padding: '24px', background: '#0a0d14', color: '#e2e8f0', minHeight: '100vh' }}>
      {/* Top Banner & Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid #1e293b', paddingBottom: '16px', marginBottom: '24px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '11px', letterSpacing: '0.1em', fontWeight: 700, color: '#38bdf8' }}>RESEARCH OS // PHASE 15</span>
            <span className="badge" style={{ background: '#10b981', color: '#022c22', fontSize: '10px', fontWeight: 700, padding: '2px 8px', borderRadius: '4px' }}>ADAPTIVE INTELLIGENCE</span>
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '6px 0 2px 0', color: '#f8fafc' }}>Global Scout Research Workspace</h1>
          <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>
            Governed multi-competition discovery, hypothesis validation holdouts, and adaptive intelligence without causal fallacies.
          </p>
        </div>
        <button
          onClick={fetchInitialData}
          disabled={loading}
          style={{ background: '#1e293b', border: '1px solid #334155', color: '#cbd5e1', padding: '8px 14px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh Surfaces
        </button>
      </div>

      {/* Epistemic Segregation Legend */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px 16px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Shield size={14} color="#38bdf8" />
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e8f0' }}>EPISTEMIC MODALITY GUARDRAIL:</span>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>Discovery is not validation. Validation is not production adoption.</span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {renderModalityBadge('FACT')}
          {renderModalityBadge('ANALYSIS')}
          {renderModalityBadge('HYPOTHESIS')}
          {renderModalityBadge('MODEL')}
          {renderModalityBadge('SCENARIO')}
        </div>
      </div>

      {/* Navigation Tabs (12 Views) */}
      <div style={{ display: 'flex', gap: '4px', overflowX: 'auto', borderBottom: '1px solid #1e293b', paddingBottom: '8px', marginBottom: '24px' }}>
        {[
          { id: 'questions', label: '1. Questions', icon: BookOpen },
          { id: 'hypotheses', label: '2. Hypotheses', icon: Sparkles },
          { id: 'cohorts', label: '3. Cohorts', icon: Users },
          { id: 'experiments', label: '4. Experiments', icon: Activity },
          { id: 'cross_competition', label: '5. Cross-Competition', icon: Compass },
          { id: 'trajectories', label: '6. Trajectories', icon: TrendingUp },
          { id: 'tactical', label: '7. Tactical Research', icon: Layers },
          { id: 'transfer_market', label: '8. Transfer Market', icon: BarChart2 },
          { id: 'model_errors', label: '9. Model Errors', icon: ShieldAlert },
          { id: 'feature_candidates', label: '10. Features', icon: GitBranch },
          { id: 'challengers', label: '11. Challengers', icon: Flame },
          { id: 'evidence_graph', label: '12. Evidence Lineage', icon: Network },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 12px',
                borderRadius: '6px',
                background: isActive ? '#0284c7' : 'transparent',
                color: isActive ? '#ffffff' : '#94a3b8',
                border: isActive ? '1px solid #38bdf8' : '1px solid transparent',
                fontSize: '12px',
                fontWeight: isActive ? 600 : 500,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Main Workspace View Switcher */}
      <div style={{ marginBottom: '32px' }}>
        {/* 1. Research Questions */}
        {activeTab === 'questions' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Framed Research Inquiries ({questions.length})</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))', gap: '16px' }}>
              {questions.map((q) => (
                <div key={q.question_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700 }}>{q.question_id}</span>
                    {renderModalityBadge(q.epistemic_status)}
                  </div>
                  <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', marginBottom: '6px' }}>{q.title}</h4>
                  <p style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '12px' }}>{q.description}</p>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {q.tags?.map((t) => (
                      <span key={t} style={{ background: '#1e293b', color: '#cbd5e1', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>#{t}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 2. Hypotheses */}
        {activeTab === 'hypotheses' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Governed Hypotheses & Validation Lifecycle</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {hypotheses.map((h) => (
                <div key={h.hypothesis_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>{h.hypothesis_id}</span>
                      <span style={{ background: '#0369a1', color: '#e0f2fe', fontSize: '10px', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                        LIFECYCLE: {h.lifecycle_state}
                      </span>
                    </div>
                    {renderModalityBadge(h.epistemic_status)}
                  </div>
                  <p style={{ fontSize: '13px', fontWeight: 500, color: '#f1f5f9', marginBottom: '10px' }}>"{h.statement}"</p>
                  <div style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                    <span>Sample Size: <strong>{h.sample_size}</strong></span>
                    <span>Competitions: <strong>{h.affected_competitions?.join(', ') || 'Global'}</strong></span>
                    <span>Uncertainty: <strong>{h.uncertainty_description}</strong></span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 3. Cohorts */}
        {activeTab === 'cohorts' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Versioned & Immutable Research Cohorts</h3>
            <div style={{ overflowX: 'auto', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1e293b', color: '#94a3b8' }}>
                    <th style={{ padding: '10px 14px' }}>COHORT ID</th>
                    <th style={{ padding: '10px 14px' }}>TYPE</th>
                    <th style={{ padding: '10px 14px' }}>NAME</th>
                    <th style={{ padding: '10px 14px' }}>SIZE</th>
                    <th style={{ padding: '10px 14px' }}>VERSION</th>
                    <th style={{ padding: '10px 14px' }}>IMMUTABILITY HASH</th>
                  </tr>
                </thead>
                <tbody>
                  {cohorts.map((c) => (
                    <tr key={c.cohort_id} style={{ borderBottom: '1px solid #1e293b' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 600, color: '#38bdf8' }}>{c.cohort_id}</td>
                      <td style={{ padding: '10px 14px' }}><span style={{ background: '#1e293b', padding: '2px 6px', borderRadius: '4px' }}>{c.cohort_type}</span></td>
                      <td style={{ padding: '10px 14px', color: '#f1f5f9' }}>{c.name}</td>
                      <td style={{ padding: '10px 14px' }}>{c.sample_size}</td>
                      <td style={{ padding: '10px 14px' }}>v{c.version}</td>
                      <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '11px', color: '#64748b' }}>
                        {c.cohort_hash ? c.cohort_hash.substring(0, 16) + '...' : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 4. Experiments */}
        {activeTab === 'experiments' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Completed Experiments & Replay Lineage</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {experiments.map((exp) => (
                <div key={exp.experiment_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#38bdf8' }}>{exp.experiment_id}</span>
                    <span style={{ background: exp.is_completed ? '#059669' : '#d97706', color: '#fff', fontSize: '10px', padding: '2px 8px', borderRadius: '4px' }}>
                      {exp.is_completed ? 'COMPLETED & SEALED' : 'IN_PROGRESS'}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '8px' }}>
                    Methodology: <strong>{exp.methodology}</strong> | Cohort: <strong>{exp.cohort_id}</strong>
                  </div>
                  {exp.result && (
                    <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px', fontSize: '12px' }}>
                      <div>Effect Estimate: <strong>{exp.result.effect_estimate > 0 ? `+${exp.result.effect_estimate}` : exp.result.effect_estimate}</strong> (p-val: {exp.result.p_value_or_posterior})</div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>{exp.result.non_causal_statement}</div>
                    </div>
                  )}
                  <div style={{ marginTop: '8px', fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                    SHA-256 Digest: {exp.experiment_hash ? exp.experiment_hash.substring(0, 24) + '...' : '—'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 5. Cross-Competition Generalization */}
        {activeTab === 'cross_competition' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Cross-Competition Generalization & Domain Shift</h3>
            <div style={{ overflowX: 'auto', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1e293b', color: '#94a3b8' }}>
                    <th style={{ padding: '10px 14px' }}>ENGINE</th>
                    <th style={{ padding: '10px 14px' }}>TRAIN LEAGUE(S)</th>
                    <th style={{ padding: '10px 14px' }}>TEST LEAGUE</th>
                    <th style={{ padding: '10px 14px' }}>DOMAIN</th>
                    <th style={{ padding: '10px 14px' }}>STATUS</th>
                    <th style={{ padding: '10px 14px' }}>IN-DOMAIN MAE</th>
                    <th style={{ padding: '10px 14px' }}>CROSS MAE</th>
                    <th style={{ padding: '10px 14px' }}>DRIFT (PSI)</th>
                  </tr>
                </thead>
                <tbody>
                  {crossCompetition.map((cc, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #1e293b' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 600 }}>{cc.engine_name}</td>
                      <td style={{ padding: '10px 14px' }}>{cc.train_competitions?.join(', ')}</td>
                      <td style={{ padding: '10px 14px', fontWeight: 600, color: '#38bdf8' }}>{cc.test_competition}</td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{ background: cc.generalization_domain === 'IN_DOMAIN' ? '#059669' : '#d97706', padding: '2px 6px', borderRadius: '4px', fontSize: '10px', color: '#fff' }}>
                          {cc.generalization_domain}
                        </span>
                      </td>
                      <td style={{ padding: '10px 14px' }}>{cc.validation_status}</td>
                      <td style={{ padding: '10px 14px' }}>{cc.in_domain_baseline_metric}</td>
                      <td style={{ padding: '10px 14px' }}>{cc.cross_domain_metric}</td>
                      <td style={{ padding: '10px 14px', fontFamily: 'monospace' }}>{cc.distribution_drift_psi}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 6. Player Trajectories */}
        {activeTab === 'trajectories' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Multi-Tier Player Trajectories & Breakouts</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {trajectories.map((t) => (
                <div key={t.player_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '14px', fontWeight: 700, color: '#38bdf8' }}>{t.player_id}</span>
                    <span style={{ background: t.is_breakout ? '#059669' : '#334155', color: '#fff', fontSize: '10px', padding: '2px 8px', borderRadius: '4px' }}>
                      {t.trajectory_classification}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', marginTop: '12px' }}>
                    <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                      <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700 }}>PAST OBSERVED</span>
                      <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '4px' }}>{t.past_observed?.length} Seasons Measured</div>
                    </div>
                    <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                      <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700 }}>CURRENT OBSERVED</span>
                      <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '4px' }}>
                        {t.current_observed ? `${t.current_observed.value} (${t.current_observed.minutes}m)` : '—'}
                      </div>
                    </div>
                    <div style={{ background: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                      <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700 }}>PROJECTED RANGE (P10-P90)</span>
                      <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '4px' }}>
                        {t.projected_range ? `[${t.projected_range.p10} — ${t.projected_range.p90}]` : '—'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 7. Tactical Research */}
        {activeTab === 'tactical' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Observed vs Modelled vs Counterfactual Tactical Structures</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {tacticalPatterns.map((tp) => (
                <div key={tp.report_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '14px', fontWeight: 700, color: '#38bdf8' }}>{tp.team_id}</span>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>{tp.observed_pattern?.season} ({tp.observed_pattern?.matches_observed} matches)</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
                    <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                      {renderModalityBadge('OBSERVED')}
                      <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '6px' }}>{tp.observed_pattern?.in_possession_structure} / {tp.observed_pattern?.out_of_possession_structure}</div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>Width: {tp.observed_pattern?.measured_width_meters}m | Press line: {tp.observed_pattern?.high_press_line_meters}m</div>
                    </div>
                    <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                      {renderModalityBadge('MODELLED')}
                      <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '6px' }}>Press Index: {tp.modelled_interpretation?.counter_press_intensity_index}</div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>Box Density: {tp.modelled_interpretation?.box_occupation_density}</div>
                    </div>
                    <div style={{ background: '#1e293b', padding: '12px', borderRadius: '6px' }}>
                      {renderModalityBadge('COUNTERFACTUAL')}
                      <div style={{ fontSize: '13px', fontWeight: 600, marginTop: '6px' }}>
                        {tp.counterfactual_scenarios?.length > 0 ? tp.counterfactual_scenarios[0].simulated_formation : 'None active'}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>{tp.counterfactual_scenarios?.[0]?.simulated_variation || '—'}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 8. Transfer Market Research */}
        {activeTab === 'transfer_market' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Transfer Market Residuals & 9-State Fee Taxonomy</h3>
            {transferMarket?.summary_residuals && (
              <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
                <h4 style={{ fontSize: '13px', color: '#38bdf8', fontWeight: 700, marginBottom: '10px' }}>GLOBAL RESIDUAL PROFILE</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', fontSize: '12px' }}>
                  <div>Valid Sample: <strong>{transferMarket.summary_residuals.sample_size}</strong></div>
                  <div>Mean Residual: <strong>{transferMarket.summary_residuals.mean_residual_pct > 0 ? `+${transferMarket.summary_residuals.mean_residual_pct}%` : `${transferMarket.summary_residuals.mean_residual_pct}%`}</strong></div>
                  <div>Median Residual: <strong>{transferMarket.summary_residuals.median_residual_pct}%</strong></div>
                  <div>Overestimation Freq: <strong>{(transferMarket.summary_residuals.overestimation_frequency * 100).toFixed(1)}%</strong></div>
                </div>
              </div>
            )}
            <div style={{ overflowX: 'auto', background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #1e293b', color: '#94a3b8' }}>
                    <th style={{ padding: '10px 14px' }}>PLAYER</th>
                    <th style={{ padding: '10px 14px' }}>FROM -> TO</th>
                    <th style={{ padding: '10px 14px' }}>FEE TAXONOMY</th>
                    <th style={{ padding: '10px 14px' }}>REALIZED FEE</th>
                    <th style={{ padding: '10px 14px' }}>MODELLED VAL</th>
                    <th style={{ padding: '10px 14px' }}>RESIDUAL</th>
                  </tr>
                </thead>
                <tbody>
                  {transferMarket?.recent_transfers?.map((t) => (
                    <tr key={t.transfer_id} style={{ borderBottom: '1px solid #1e293b' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 600 }}>{t.player_id}</td>
                      <td style={{ padding: '10px 14px' }}>{t.selling_club} → {t.buying_club}</td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{ background: '#1e293b', padding: '2px 6px', borderRadius: '4px', fontSize: '10px' }}>{t.fee_type}</span>
                      </td>
                      <td style={{ padding: '10px 14px' }}>{t.realized_fee_eur !== null ? `€${(t.realized_fee_eur / 1e6).toFixed(1)}M` : 'UNDISCLOSED'}</td>
                      <td style={{ padding: '10px 14px' }}>{t.modelled_valuation_eur ? `€${(t.modelled_valuation_eur / 1e6).toFixed(1)}M` : '—'}</td>
                      <td style={{ padding: '10px 14px', color: t.valuation_residual_pct > 0 ? '#10b981' : '#f43f5e' }}>
                        {t.valuation_residual_pct !== null ? `${t.valuation_residual_pct > 0 ? '+' : ''}${t.valuation_residual_pct}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 9. Model Error Research */}
        {activeTab === 'model_errors' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Fine-Grained Contextual Error Slices (Anti-Smoothing)</h3>
            {modelErrors.map((me) => (
              <div key={me.model_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px', marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#38bdf8' }}>{me.model_id} (v{me.model_version})</span>
                  <span style={{ fontSize: '11px', color: '#94a3b8' }}>Audit: Silent Averaging Prevented</span>
                </div>
                <div style={{ marginBottom: '12px' }}>
                  <h5 style={{ fontSize: '12px', color: '#f43f5e', fontWeight: 700, marginBottom: '6px' }}>IDENTIFIED FAILURE BOUNDARIES & WEAK SUBGROUPS</h5>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {me.weakest_subgroups?.map((w, idx) => (
                      <div key={idx} style={{ background: '#1e293b', borderLeft: '3px solid #f43f5e', padding: '8px 12px', fontSize: '12px' }}>
                        <strong>{w.slice_type} // {w.slice_key}</strong>: {w.weak_subgroup_reason} (N={w.sample_size}, ECE: {w.expected_calibration_error})
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 10. Feature Candidates */}
        {activeTab === 'feature_candidates' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Candidate Features Identified in Research</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: '16px' }}>
              {featureCandidates.map((fc) => (
                <div key={fc.candidate_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#38bdf8' }}>{fc.feature_name}</span>
                    <span style={{ background: '#334155', color: '#cbd5e1', fontSize: '10px', padding: '2px 6px', borderRadius: '4px' }}>
                      Target: {fc.target_metric}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '10px' }}>{fc.rationale}</p>
                  <div style={{ fontSize: '11px', color: '#cbd5e1', display: 'flex', gap: '16px' }}>
                    <span>Effect: <strong>{fc.effect_magnitude > 0 ? `+${fc.effect_magnitude}` : fc.effect_magnitude}</strong></span>
                    <span>Stability: <strong>{fc.stability_score}</strong></span>
                    <span>Leakage Checked: <strong>{fc.leakage_audited ? 'YES' : 'NO'}</strong></span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 11. Challengers & Governed Promotion */}
        {activeTab === 'challengers' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Champion vs Challenger Governed Promotion Ledger</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {challengers.map((ch) => (
                <div key={ch.promotion_id} style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#38bdf8' }}>{ch.candidate_id} vs {ch.champion_id}</span>
                    <span style={{ background: ch.promotion_status === 'PROMOTED' ? '#059669' : '#d97706', color: '#fff', fontSize: '10px', padding: '2px 8px', borderRadius: '4px' }}>
                      {ch.promotion_status}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: '#cbd5e1', marginBottom: '8px' }}>{ch.justification}</p>
                  <div style={{ fontSize: '11px', color: '#64748b' }}>Authorized by: <strong>{ch.governed_approval_author}</strong></div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 12. Research Evidence Lineage Graph */}
        {activeTab === 'evidence_graph' && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Cryptographic Research Lineage Graph</h3>
            <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '12px' }}>
                Graph Digest (SHA-256): <span style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{evidenceGraph?.graph_digest || '—'}</span>
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {evidenceGraph?.nodes?.map((n) => (
                  <div key={n.node_id} style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '8px 12px', fontSize: '12px' }}>
                    <div style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700 }}>{n.node_type}</div>
                    <div style={{ fontWeight: 600, color: '#f8fafc' }}>{n.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Scout Copilot V5 Console */}
      <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
          <Sparkles size={16} color="#38bdf8" />
          <h4 style={{ fontSize: '14px', fontWeight: 600, margin: 0, color: '#f8fafc' }}>Scout Copilot V5 // Research Query Dispatcher</h4>
        </div>
        <form onSubmit={handleCopilotSubmit} style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <input
            type="text"
            placeholder="e.g., 'Find evidence for hypothesis', 'Compare pattern across leagues', 'Show where the pattern fails'..."
            value={copilotQuery}
            onChange={(e) => setCopilotQuery(e.target.value)}
            style={{ flex: 1, background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '10px 14px', color: '#f8fafc', fontSize: '13px' }}
          />
          <button
            type="submit"
            disabled={copilotLoading || !copilotQuery.trim()}
            style={{ background: '#0284c7', border: 'none', color: '#fff', padding: '0 16px', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600 }}
          >
            <Send size={14} /> Query
          </button>
        </form>

        {copilotResponse && (
          <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <span style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700 }}>CLASS: {copilotResponse.query_class}</span>
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Confidence: {(copilotResponse.confidence * 100).toFixed(0)}%</span>
            </div>
            <p style={{ fontSize: '13px', color: '#f8fafc', marginBottom: '8px' }}>{copilotResponse.summary_answer}</p>
            <div style={{ fontSize: '11px', color: '#94a3b8', borderTop: '1px solid #334155', paddingTop: '8px' }}>
              <strong>Non-Causal Audit:</strong> {copilotResponse.non_causal_statement}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
