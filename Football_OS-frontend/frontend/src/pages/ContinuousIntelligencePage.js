import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  Clock,
  Shuffle,
  DollarSign,
  AlertTriangle,
  Award,
  Layers,
  Search,
  CheckCircle,
  RefreshCw,
  GitCommit,
  ShieldCheck,
  Zap
} from 'lucide-react';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function ContinuousIntelligencePage() {
  const [activeTab, setActiveTab] = useState('emerging');
  const [emergingPlayers, setEmergingPlayers] = useState([]);
  const [trajectories, setTrajectories] = useState([]);
  const [roleTransitions, setRoleTransitions] = useState([]);
  const [marketOpportunities, setMarketOpportunities] = useState([]);
  const [decisionFreshness, setDecisionFreshness] = useState([]);
  const [challengerComparisons, setChallengerComparisons] = useState([]);
  const [learningJobs, setLearningJobs] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotResponse, setCopilotResponse] = useState(null);
  const [copilotLoading, setCopilotLoading] = useState(false);

  useEffect(() => {
    fetchOperationalData();
  }, []);

  const fetchOperationalData = async () => {
    setLoading(true);
    try {
      const [
        resEmg,
        resTrans,
        resMkt,
        resFresh,
        resChall,
        resJobs,
        resAlerts
      ] = await Promise.all([
        fetch(`${API_BASE}/api/phase12/emerging`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/phase12/role-transitions`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/phase12/market/opportunities`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/phase12/decisions/freshness`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/phase12/models/challengers`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/phase12/learning/jobs`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/phase12/alerts`).then(r => r.ok ? r.json() : []),
      ]);

      setEmergingPlayers(resEmg);
      setRoleTransitions(resTrans);
      setMarketOpportunities(resMkt);
      setDecisionFreshness(resFresh);
      setChallengerComparisons(resChall);
      setLearningJobs(resJobs);
      setAlerts(resAlerts);
    } catch (e) {
      console.warn('API error, falling back to local operational telemetry:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCopilotSubmit = async (e) => {
    e.preventDefault();
    if (!copilotQuery.trim()) return;
    setCopilotLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/phase12/copilot/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: copilotQuery })
      });
      if (res.ok) {
        const data = await res.json();
        setCopilotResponse(data);
      }
    } catch (err) {
      console.error('Copilot query error:', err);
    } finally {
      setCopilotLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 space-y-6">
      {/* Top Banner / Breadcrumb */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-slate-800 pb-4 gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <RefreshCw className="h-6 w-6 text-emerald-400" />
              Continuous Decision Intelligence Workstation
            </h1>
            <span className="px-2 py-0.5 text-xs font-mono font-semibold rounded bg-emerald-950 text-emerald-300 border border-emerald-700">
              PHASE 12 CERTIFIED
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Real-time evidence impact graph, decision freshness evaluation, emerging player detection, and challenger governance.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchOperationalData}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 rounded transition"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh Telemetry
          </button>
        </div>
      </div>

      {/* Scout Copilot V2 Dispatch Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
        <form onSubmit={handleCopilotSubmit} className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={copilotQuery}
              onChange={(e) => setCopilotQuery(e.target.value)}
              placeholder="Copilot V2: 'Find emerging U23 centre backs', 'Which decisions are stale?', 'Show value gaps'..."
              className="w-full bg-slate-950 border border-slate-700 rounded pl-9 pr-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={copilotLoading}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-slate-950 font-semibold text-sm rounded flex items-center gap-2 transition"
          >
            <Zap className="h-4 w-4" />
            {copilotLoading ? 'Dispatching...' : 'Execute Tool'}
          </button>
        </form>

        {copilotResponse && (
          <div className="mt-4 p-3 bg-slate-950 border border-slate-700 rounded font-mono text-xs space-y-2">
            <div className="flex items-center justify-between text-emerald-400 font-semibold border-b border-slate-800 pb-1">
              <span>DISPATCHED: {copilotResponse.intent}</span>
              <span className="text-slate-400 text-[11px]">{copilotResponse.summary}</span>
            </div>
            {copilotResponse.epistemic_notice && (
              <p className="text-slate-400 italic">Epistemic Guard: {copilotResponse.epistemic_notice}</p>
            )}
            {copilotResponse.results && Array.isArray(copilotResponse.results) && (
              <div className="max-h-48 overflow-y-auto space-y-1 pt-1">
                {copilotResponse.results.map((r, idx) => (
                  <div key={idx} className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300">
                    <span className="font-bold text-white">{r.player_name || r.decision_id || r.model_id}</span> — {r.primary_role || r.freshness_state || r.opportunity_state || r.recommendation}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 space-x-1 overflow-x-auto text-xs font-mono">
        {[
          { id: 'emerging', label: 'Emerging Players', icon: TrendingUp },
          { id: 'freshness', label: 'Decision Freshness', icon: Clock },
          { id: 'roles', label: 'Role Transitions', icon: Shuffle },
          { id: 'market', label: 'Market Inefficiencies', icon: DollarSign },
          { id: 'challenger', label: 'Champion vs Challenger', icon: Award },
          { id: 'learning', label: 'Governed Learning Loop', icon: GitCommit },
          { id: 'alerts', label: 'Operational Alerts', icon: AlertTriangle },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 font-medium border-b-2 transition whitespace-nowrap ${
                isActive
                  ? 'border-emerald-400 text-emerald-400 bg-slate-900/60'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Emerging Players */}
      {activeTab === 'emerging' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Multi-Dimensional Emerging Player Signals (§9, §10)
            </h2>
            <span className="text-xs font-mono text-slate-500">Gated on >= 450 minutes & U23 developmental age</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {emergingPlayers.map((opp) => (
              <div key={opp.opportunity_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-3 font-mono">
                <div className="flex items-start justify-between border-b border-slate-800 pb-2">
                  <div>
                    <h3 className="text-base font-bold text-white flex items-center gap-2">
                      {opp.player_name}
                      <span className="text-xs font-normal text-slate-400">({opp.age}y, {opp.position})</span>
                    </h3>
                    <p className="text-xs text-slate-400">{opp.current_club} • {opp.competition_id} • {opp.primary_role}</p>
                  </div>
                  <span className="px-2 py-0.5 text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-700 rounded">
                    {opp.status}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">MINUTES GAIN</span>
                    <span className="font-bold text-emerald-400">+{opp.minutes_gain_pct}%</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">CONTRIBUTION</span>
                    <span className="font-bold text-emerald-400">+{opp.contribution_gain_pts} pts</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">VALUATION LAG</span>
                    <span className="font-bold text-amber-400">{opp.valuation_lag_pct}%</span>
                  </div>
                </div>

                <div className="text-xs space-y-1">
                  <span className="text-slate-500 block text-[10px]">EMPIRICAL EVIDENCE</span>
                  {opp.evidence && opp.evidence.map((ev, i) => (
                    <div key={i} className="text-slate-300 flex items-start gap-1.5 text-[11px]">
                      <span className="text-emerald-500">•</span> {ev}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: Decision Freshness */}
      {activeTab === 'freshness' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Historical Decision Freshness & Staleness Telemetry (§4)
            </h2>
            <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
              <ShieldCheck className="h-3.5 w-3.5" /> Immutable Historical Decisions Preserved
            </span>
          </div>

          <div className="space-y-3 font-mono">
            {decisionFreshness.map((fresh) => (
              <div key={fresh.assessment_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white text-sm">{fresh.decision_id}</span>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 text-xs rounded border ${
                      fresh.freshness_state === 'STALE'
                        ? 'bg-rose-950 text-rose-300 border-rose-700'
                        : fresh.freshness_state === 'MONITOR'
                        ? 'bg-amber-950 text-amber-300 border-amber-700'
                        : 'bg-emerald-950 text-emerald-300 border-emerald-700'
                    }`}>
                      STATUS: {fresh.freshness_state}
                    </span>
                    <span className="text-xs text-slate-500">Materiality: {fresh.materiality}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs pt-1">
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">VALUATION SHIFT</span>
                    <span className="text-white font-semibold">
                      {fresh.valuation_delta_eur >= 0 ? '+' : ''}€{(fresh.valuation_delta_eur / 1e6).toFixed(1)}M
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">CHANGED FEATURES</span>
                    <span className="text-white font-semibold">{fresh.changed_features?.length || 0} features</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">ROLE SHIFT</span>
                    <span className="text-white font-semibold">{fresh.role_changed ? 'YES' : 'NO'}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">EVIDENCE DIGEST</span>
                    <span className="text-slate-400 font-mono text-[10px] truncate block">
                      {fresh.current_evidence_digest?.slice(0, 16)}...
                    </span>
                  </div>
                </div>

                <div className="pt-2 text-xs text-slate-300 space-y-1">
                  {fresh.reasons && fresh.reasons.map((r, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[11px]">
                      <span className="text-amber-500">→</span> {r}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Role Transitions */}
      {activeTab === 'roles' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Empirical Tactical Role Transitions (§11)
            </h2>
            <span className="text-xs font-mono text-slate-500">Strictly Non-Causal • >= 450 competitive minutes</span>
          </div>

          <div className="space-y-3 font-mono">
            {roleTransitions.map((t) => (
              <div key={t.transition_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div>
                    <h3 className="text-base font-bold text-white">{t.player_name}</h3>
                    <p className="text-xs text-slate-400">{t.current_club} • {t.competition_id} • {t.position}</p>
                  </div>
                  <span className="px-2 py-0.5 text-xs bg-slate-950 text-slate-300 border border-slate-700 rounded">
                    Confidence: {t.confidence}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-xs bg-slate-950 p-3 rounded border border-slate-800">
                  <div className="flex-1">
                    <span className="text-slate-500 block text-[10px]">PREVIOUS ROLE</span>
                    <span className="font-semibold text-slate-300">{t.previous_role}</span>
                  </div>
                  <Shuffle className="h-4 w-4 text-emerald-400" />
                  <div className="flex-1">
                    <span className="text-slate-500 block text-[10px]">CURRENT ROLE</span>
                    <span className="font-semibold text-emerald-400">{t.current_role}</span>
                  </div>
                </div>

                <div className="text-xs space-y-1">
                  <span className="text-slate-500 block text-[10px]">OBSERVATIONAL EVIDENCE</span>
                  {t.observational_evidence && t.observational_evidence.map((ev, i) => (
                    <div key={i} className="text-slate-300 flex items-start gap-1.5 text-[11px]">
                      <span className="text-emerald-500">•</span> {ev}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: Market Inefficiencies */}
      {activeTab === 'market' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Market Inefficiency & Value Gap Opportunities (§12)
            </h2>
            <span className="text-xs font-mono text-slate-500">Observed Reference vs GBR Modelled Prediction</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono">
            {marketOpportunities.map((m) => (
              <div key={m.signal_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-3">
                <div className="flex items-start justify-between border-b border-slate-800 pb-2">
                  <div>
                    <h3 className="text-base font-bold text-white">{m.player_name}</h3>
                    <p className="text-xs text-slate-400">{m.current_club} • {m.competition_id} • {m.position}</p>
                  </div>
                  <span className="px-2 py-0.5 text-xs font-bold bg-amber-950 text-amber-300 border border-amber-700 rounded">
                    {m.opportunity_state}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">OBSERVED REF</span>
                    <span className="font-bold text-slate-300">€{(m.observed_market_reference_eur / 1e6).toFixed(1)}M</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">MODELLED VALUE</span>
                    <span className="font-bold text-emerald-400">€{(m.modelled_valuation_eur / 1e6).toFixed(1)}M</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">VALUE GAP</span>
                    <span className="font-bold text-amber-400">+{m.value_gap_pct?.toFixed(1)}%</span>
                  </div>
                </div>

                <div className="text-xs space-y-1">
                  <span className="text-slate-500 block text-[10px]">SUPPORTING EVIDENCE</span>
                  {m.supporting_evidence && m.supporting_evidence.map((ev, i) => (
                    <div key={i} className="text-slate-300 flex items-start gap-1.5 text-[11px]">
                      <span className="text-emerald-500">•</span> {ev}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 5: Champion vs Challenger */}
      {activeTab === 'challenger' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Champion vs Challenger Comparative Model Governance (§7, §18, §19)
            </h2>
            <span className="text-xs font-mono text-emerald-400">Zero Authoritative Leakage</span>
          </div>

          <div className="space-y-4 font-mono">
            {challengerComparisons.map((c) => (
              <div key={c.comparison_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div>
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      {c.model_family} EVALUATION ({c.competition_scope})
                    </h3>
                    <p className="text-xs text-slate-400">
                      Champion: <span className="text-slate-300 font-semibold">{c.champion_model_id}</span> ({c.champion_version}) vs Challenger: <span className="text-emerald-400 font-semibold">{c.challenger_model_id}</span> ({c.challenger_version})
                    </p>
                  </div>
                  <span className="px-2 py-0.5 text-xs font-bold bg-slate-950 text-slate-200 border border-slate-700 rounded">
                    {c.recommendation}
                  </span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">LOG LOSS (CHAMP / CHALL)</span>
                    <span className="text-slate-300">{c.champion_log_loss}</span> → <span className="text-emerald-400 font-bold">{c.challenger_log_loss}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">BRIER SCORE</span>
                    <span className="text-slate-300">{c.champion_brier}</span> → <span className="text-emerald-400 font-bold">{c.challenger_brier}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">ECE CALIBRATION</span>
                    <span className="text-slate-300">{c.champion_ece}</span> → <span className="text-emerald-400 font-bold">{c.challenger_ece}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">PREDICTION AGREEMENT</span>
                    <span className="text-white font-bold">{(c.prediction_agreement_rate * 100).toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 6: Governed Learning Loop */}
      {activeTab === 'learning' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Governed Continuous Model Learning Loop (§5, §28)
            </h2>
            <span className="text-xs font-mono text-slate-500">Zero Silent Model Promotion • Audited Job Digests</span>
          </div>

          <div className="space-y-3 font-mono">
            {learningJobs.map((job) => (
              <div key={job.job_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div>
                    <h3 className="text-sm font-bold text-white">{job.model_id}</h3>
                    <p className="text-xs text-slate-400">
                      Scope: {job.competition_scope} • Dataset: {job.dataset_version}
                    </p>
                  </div>
                  <span className={`px-2 py-0.5 text-xs font-bold rounded border ${
                    job.decision === 'PROMOTED'
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                      : 'bg-slate-950 text-slate-300 border-slate-700'
                  }`}>
                    {job.decision}
                  </span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">QUALITY GATE</span>
                    <span className="text-emerald-400 font-bold">{job.data_quality_verified ? 'PASSED' : 'FAILED'}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">DRIFT CHECK</span>
                    <span className="text-emerald-400 font-bold">{job.drift_checked ? 'PASSED' : 'FAILED'}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">VALIDATION</span>
                    <span className="text-emerald-400 font-bold">{job.validation_passed ? 'PASSED' : 'FAILED'}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">CALIBRATION</span>
                    <span className="text-emerald-400 font-bold">{job.calibration_fitted ? 'FITTED' : 'PENDING'}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">SHADOW RUN</span>
                    <span className="text-emerald-400 font-bold">{job.shadow_mode_completed ? 'COMPLETE' : 'PENDING'}</span>
                  </div>
                  <div className="bg-slate-950 p-2 rounded border border-slate-800">
                    <span className="text-slate-500 block text-[10px]">DIGEST</span>
                    <span className="text-slate-400 font-mono text-[10px] truncate block">
                      {job.job_digest?.slice(0, 12)}...
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 7: Operational Alerts */}
      {activeTab === 'alerts' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-mono uppercase tracking-wider text-slate-400">
              Phase 12 Operational Telemetry Alerts (§24)
            </h2>
            <span className="text-xs font-mono text-slate-500">Strictly Non-Causal Telemetry</span>
          </div>

          <div className="space-y-3 font-mono">
            {alerts.map((alt) => (
              <div key={alt.alert_id} className="bg-slate-900 border border-slate-800 rounded p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white text-sm">{alt.category}</span>
                  <span className={`px-2 py-0.5 text-xs rounded border ${
                    alt.severity === 'WARNING'
                      ? 'bg-amber-950 text-amber-300 border-amber-700'
                      : 'bg-slate-950 text-slate-300 border-slate-700'
                  }`}>
                    {alt.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-400">Entity: <span className="text-white font-semibold">{alt.entity_name}</span> ({alt.entity_id})</p>
                <div className="text-xs text-slate-300 space-y-1 pt-1">
                  {alt.evidence && alt.evidence.map((ev, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-[11px]">
                      <span className="text-emerald-500">•</span> {ev}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
