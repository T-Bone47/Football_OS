import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle,
  Clock,
  Compass,
  DollarSign,
  FileText,
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
} from 'lucide-react';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function DecisionLabPage() {
  const [activeTab, setActiveTab] = useState('squad');
  const [clubId, setClubId] = useState('arsenal_fc');
  const [loading, setLoading] = useState(false);

  // Surface 1: Current Squad Baseline
  const [squadBaseline, setSquadBaseline] = useState(null);

  // Surface 2: Tactical System
  const [selectedFormation, setSelectedFormation] = useState('4-3-3');
  const [tacticalEvaluation, setTacticalEvaluation] = useState(null);

  // Surface 3 & 4: Scenarios & Comparison
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenarioIds, setSelectedScenarioIds] = useState(['scen_sell_buy_inacio', 'scen_multi_buy_cb_dm']);
  const [comparisonResult, setComparisonResult] = useState(null);

  // Scenario Builder Form State
  const [newScenarioName, setNewScenarioName] = useState('Custom: Multi-Target Window');
  const [newScenarioType, setNewScenarioType] = useState('SELL_BUY');
  const [movements, setMovements] = useState([
    { action: 'SELL', player_id: 'partey_05', player_name: 'Thomas Partey', position: 'DM', fee_eur: 12000000, weekly_wage_eur: 200000, tactical_role: 'Lone Pivot' },
    { action: 'BUY', player_id: 'inacio_25', player_name: 'Gonçalo Inácio', position: 'CB', fee_eur: 45000000, weekly_wage_eur: 110000, tactical_role: 'Ball Playing CB' },
  ]);

  // Surface 5: Budget & Pareto Frontier
  const [budgetCeiling, setBudgetCeiling] = useState(65000000);
  const [paretoFrontier, setParetoFrontier] = useState([]);

  // Surface 6: Squad Depth
  const [congestionMode, setCongestionMode] = useState('DOMESTIC_LEAGUE');
  const [depthEvaluation, setDepthEvaluation] = useState(null);

  // Surface 7: Sensitivity & Robustness
  const [sensitivityProfile, setSensitivityProfile] = useState(null);
  const [robustnessReport, setRobustnessReport] = useState(null);

  // Surface 8: Evidence Graph
  const [evidenceGraph, setEvidenceGraph] = useState(null);

  // Surface 9: Decision Record & Follow-Up
  const [decisionRecords, setDecisionRecords] = useState([]);
  const [decisionSigner, setDecisionSigner] = useState('Edu Gaspar / Sporting Director');
  const [decisionAnnotations, setDecisionAnnotations] = useState('Approved following side-by-side Pareto evaluation. Defensive succession secured within wage headroom.');
  const [finalizeSuccess, setFinalizeSuccess] = useState(null);

  // Surface 10: Scout Copilot V3
  const [copilotQuery, setCopilotQuery] = useState('');
  const [copilotResponse, setCopilotResponse] = useState(null);
  const [copilotLoading, setCopilotLoading] = useState(false);

  useEffect(() => {
    loadLabData();
  }, [clubId]);

  useEffect(() => {
    loadTacticalEvaluation(selectedFormation);
  }, [selectedFormation, clubId]);

  useEffect(() => {
    loadDepthEvaluation(congestionMode);
  }, [congestionMode, clubId]);

  const loadLabData = async () => {
    setLoading(true);
    try {
      // 1. Squad Baseline
      const squadRes = await fetch(`${API_BASE}/api/v1/decision-lab/squad/${clubId}`);
      if (squadRes.ok) {
        const data = await squadRes.json();
        setSquadBaseline(data);
      }

      // 2. Scenarios
      const scenRes = await fetch(`${API_BASE}/api/v1/decision-lab/scenarios?club_id=${clubId}`);
      if (scenRes.ok) {
        const scens = await scenRes.json();
        setScenarios(scens);
        if (scens.length >= 2) {
          triggerComparison([scens[0].scenario_id, scens[1].scenario_id]);
          triggerSensitivity(scens[0]);
          triggerRobustness(scens[0]);
          loadEvidenceGraph(scens[0].scenario_id);
        }
      }

      // 3. Pareto Frontier
      const budgetRes = await fetch(`${API_BASE}/api/v1/decision-lab/budget`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ club_id: clubId, formation: '4-3-3', budget_ceiling_eur: budgetCeiling }),
      });
      if (budgetRes.ok) {
        setParetoFrontier(await budgetRes.json());
      }

      // 4. Decision Records
      const decRes = await fetch(`${API_BASE}/api/v1/decision-lab/decisions?club_id=${clubId}`);
      if (decRes.ok) {
        setDecisionRecords(await decRes.json());
      }
    } catch (err) {
      console.error('Failed to load Decision Lab data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadTacticalEvaluation = async (formation) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/tactical/${clubId}?formation=${encodeURIComponent(formation)}`);
      if (res.ok) setTacticalEvaluation(await res.json());
    } catch (err) {
      console.error('Failed to evaluate tactical system:', err);
    }
  };

  const loadDepthEvaluation = async (congestion) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/depth/${clubId}?congestion=${congestion}`);
      if (res.ok) setDepthEvaluation(await res.json());
    } catch (err) {
      console.error('Failed to evaluate depth:', err);
    }
  };

  const triggerComparison = async (ids) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/scenarios/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_ids: ids, club_id: clubId }),
      });
      if (res.ok) setComparisonResult(await res.json());
    } catch (err) {
      console.error('Failed to compare scenarios:', err);
    }
  };

  const triggerSensitivity = async (scen) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/sensitivity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scen.scenario_id,
          club_id: clubId,
          net_spend_eur: scen.net_spend_eur || 20000000,
          wage_delta_weekly: scen.wage_bill_delta_weekly || -80000,
          tactical_fit: 88.4,
        }),
      });
      if (res.ok) setSensitivityProfile(await res.json());
    } catch (err) {
      console.error('Failed to calculate sensitivity:', err);
    }
  };

  const triggerRobustness = async (scen) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/robustness`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scen.scenario_id,
          scenario_name: scen.name,
          club_id: clubId,
          net_spend_eur: scen.net_spend_eur || 20000000,
          wage_bill_delta: scen.wage_bill_delta_weekly || -80000,
          tactical_fit_delta: scen.tactical_fit_delta || 2.2,
          squad_depth_delta: scen.squad_depth_rating_delta || 1.5,
        }),
      });
      if (res.ok) setRobustnessReport(await res.json());
    } catch (err) {
      console.error('Failed to calculate robustness:', err);
    }
  };

  const loadEvidenceGraph = async (scenarioId) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/evidence/${scenarioId}?club_id=${clubId}`);
      if (res.ok) setEvidenceGraph(await res.json());
    } catch (err) {
      console.error('Failed to load evidence graph:', err);
    }
  };

  const handleCreateScenario = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newScenarioName,
          club_id: clubId,
          scenario_type: newScenarioType,
          movements: movements,
          assumptions: [
            'Simulated within standard 30-day transfer registration window',
            'Wage structure preserves club statutory financial fair play buffer',
          ],
        }),
      });
      if (res.ok) {
        const created = await res.json();
        setScenarios([created, ...scenarios]);
        setActiveTab('comparison');
        triggerComparison([created.scenario_id, scenarios[0]?.scenario_id || created.scenario_id]);
      }
    } catch (err) {
      console.error('Failed to create scenario:', err);
    }
  };

  const handleFinalizeDecision = async () => {
    try {
      const chosen = scenarios[0];
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/finalize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: 'rec_proj_cb_2026',
          project_name: 'Defensive Line Modernization 2026',
          club_id: clubId,
          chosen_scenario_id: chosen?.scenario_id || 'scen_01',
          chosen_scenario_name: chosen?.name || 'Scenario A',
          candidate_set: squadBaseline?.squad_players?.slice(0, 3) || [],
          alternatives_considered: scenarios.slice(1, 3).map((s) => ({
            scenario_id: s.scenario_id,
            name: s.name,
            net_spend_eur: s.net_spend_eur,
            tactical_fit_delta: s.tactical_fit_delta,
            squad_depth_delta: s.squad_depth_rating_delta,
            rejection_rationale: 'Sub-optimal financial efficiency or excessive squad churn.',
          })),
          scenario_assumptions: chosen?.assumptions || [],
          constraints: { budget_ceiling_eur: budgetCeiling, formation: selectedFormation },
          human_annotations: decisionAnnotations,
          signed_by: decisionSigner,
        }),
      });
      if (res.ok) {
        const saved = await res.json();
        setDecisionRecords([saved, ...decisionRecords]);
        setFinalizeSuccess(`Decision ${saved.decision_id} cryptographically recorded (SHA-256: ${saved.audit_digest.slice(0, 16)}...).`);
      }
    } catch (err) {
      console.error('Failed to finalize decision:', err);
    }
  };

  const handleCopilotSubmit = async (queryText) => {
    const q = queryText || copilotQuery;
    if (!q.trim()) return;
    setCopilotLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/decision-lab/copilot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, club_id: clubId }),
      });
      if (res.ok) {
        setCopilotResponse(await res.json());
      }
    } catch (err) {
      console.error('Copilot query error:', err);
    } finally {
      setCopilotLoading(false);
    }
  };

  const tabs = [
    { id: 'squad', label: 'Current Squad Baseline', icon: Users },
    { id: 'tactical', label: 'Tactical System Simulator', icon: Radar },
    { id: 'builder', label: 'Scenario Builder', icon: Sliders },
    { id: 'comparison', label: 'Multi-Scenario Comparison', icon: GitFork },
    { id: 'pareto', label: 'Budget Pareto Frontier', icon: DollarSign },
    { id: 'depth', label: 'Squad Depth & Congestion', icon: Layers },
    { id: 'sensitivity', label: 'Sensitivity & Robustness', icon: Activity },
    { id: 'evidence', label: 'Evidence Graph Lineage', icon: GitCommit },
    { id: 'decisions', label: 'Decision Records & Follow-Up', icon: ShieldCheck },
  ];

  const quickPrompts = [
    'Build three scenarios for replacing our centre-back.',
    'Compare 4-3-3 and 3-4-2-1 for this squad.',
    'Which positions are most exposed if two midfielders leave?',
    'Show me the trade-offs between these scenarios.',
    'Why is this scenario unsupported?',
    'Which assumptions make this scenario sensitive?',
  ];

  return (
    <div className="space-y-6 pb-12" data-testid="decision-lab-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white">Decision Lab 2.0</h1>
            <span className="px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
              DECISION_SIMULATION_VALIDATED
            </span>
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Deterministic Tactical Simulation, Multi-Scenario Construction, Pareto Trade-Offs & Counterfactual Intelligence.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Club Context:</label>
          <select
            value={clubId}
            onChange={(e) => setClubId(e.target.value)}
            className="bg-gray-900 border border-gray-700 text-sm text-gray-200 rounded px-3 py-1.5 focus:outline-none focus:border-blue-500"
          >
            <option value="arsenal_fc">Arsenal FC (EPL Baseline)</option>
            <option value="brentford_fc">Brentford FC (EPL)</option>
            <option value="real_madrid">Real Madrid CF (La Liga)</option>
          </select>
          <button
            onClick={loadLabData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded transition"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Sync
          </button>
        </div>
      </div>

      {/* Epistemic Modality Banner (§7, §36) */}
      <div className="p-3 bg-blue-950/40 border border-blue-900/60 rounded text-xs text-blue-200 flex items-start gap-2.5">
        <HelpCircle size={16} className="text-blue-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-blue-300">Epistemic Modality Separation:</span> All metrics in this workspace are strictly classified into{' '}
          <span className="font-mono text-emerald-300">OBSERVED</span> (actual matches/contracts),{' '}
          <span className="font-mono text-purple-300">MODELLED</span> (statistical baseline fits),{' '}
          <span className="font-mono text-amber-300">COUNTERFACTUAL</span> (simulated hypothetical outputs), or{' '}
          <span className="font-mono text-cyan-300">ASSUMPTION</span>. Counterfactuals are deterministic mathematical models and are never presented as observed future facts.
        </div>
      </div>

      {/* Scout Copilot V3 Mini-Bar (§26) */}
      <div className="p-4 bg-gray-900/80 border border-gray-800 rounded-lg space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
            <Zap size={16} className="text-amber-400" />
            <span>Scout Copilot V3 — Deterministic Decision Assistant</span>
          </div>
          <span className="text-xs text-gray-400 font-mono">Zero LLM Metric Hallucination Guarantee</span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={copilotQuery}
            onChange={(e) => setCopilotQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCopilotSubmit()}
            placeholder="Ask deterministic scenario question (e.g. 'Build three scenarios for replacing our centre-back')..."
            className="flex-1 bg-black/60 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-amber-500"
          />
          <button
            onClick={() => handleCopilotSubmit()}
            disabled={copilotLoading}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded flex items-center gap-1.5 transition disabled:opacity-50"
          >
            {copilotLoading ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
            Dispatch
          </button>
        </div>
        {/* Quick Prompts */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {quickPrompts.map((qp, idx) => (
            <button
              key={idx}
              onClick={() => {
                setCopilotQuery(qp);
                handleCopilotSubmit(qp);
              }}
              className="text-xs px-2.5 py-1 bg-gray-800/80 hover:bg-gray-700 border border-gray-700/60 rounded text-gray-300 transition"
            >
              {qp}
            </button>
          ))}
        </div>
        {/* Copilot Response Panel */}
        {copilotResponse && (
          <div className="mt-3 p-3 bg-black/80 border border-amber-900/40 rounded text-xs space-y-2">
            <div className="flex items-center justify-between text-amber-400 font-semibold border-b border-gray-800 pb-1.5">
              <span>Intent: {copilotResponse.intent}</span>
              <span className="text-gray-400 font-mono">{copilotResponse.epistemic_notice}</span>
            </div>
            <p className="text-gray-200 text-sm leading-relaxed">{copilotResponse.summary}</p>
            {copilotResponse.trade_off_analysis && (
              <div className="grid grid-cols-2 gap-2 pt-1 text-gray-300">
                <div className="p-2 bg-gray-900 rounded border border-gray-800">
                  <div className="font-semibold text-blue-400">4-3-3 Fit</div>
                  <div>{copilotResponse.trade_off_analysis['4-3-3_advantages']}</div>
                </div>
                <div className="p-2 bg-gray-900 rounded border border-gray-800">
                  <div className="font-semibold text-purple-400">3-4-2-1 Fit</div>
                  <div>{copilotResponse.trade_off_analysis['3-4-2-1_advantages']}</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <div className="flex overflow-x-auto border-b border-gray-800 gap-1 pb-1">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-xs font-medium whitespace-nowrap rounded-t transition-colors ${
                isActive
                  ? 'bg-gray-800 text-white border-b-2 border-blue-500 font-semibold'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900'
              }`}
            >
              <Icon size={15} className={isActive ? 'text-blue-400' : 'text-gray-500'} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ────────────────── Surface 1: Current Squad Baseline ────────────────── */}
      {activeTab === 'squad' && squadBaseline && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Available Transfer Budget</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">
                €{(squadBaseline.financial_state.available_transfer_budget_eur / 1000000).toFixed(1)}M
              </div>
              <div className="text-xs text-gray-500 mt-1">OBSERVED Board Allocation 2025/26</div>
            </div>
            <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Weekly Wage Headroom</div>
              <div className="text-2xl font-bold text-blue-400 mt-1">
                €{(squadBaseline.financial_state.weekly_wage_headroom_eur / 1000).toFixed(0)}k / wk
              </div>
              <div className="text-xs text-gray-500 mt-1">Statutory PSR/FFP Operating Ceiling</div>
            </div>
            <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
              <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">Squad Asset Valuation</div>
              <div className="text-2xl font-bold text-purple-400 mt-1">
                €{(squadBaseline.financial_state.estimated_squad_value_eur / 1000000).toFixed(0)}M
              </div>
              <div className="text-xs text-gray-500 mt-1">Aggregated Transfermarkt Benchmark</div>
            </div>
          </div>

          <div className="bg-gray-900/60 border border-gray-800 rounded-lg overflow-hidden">
            <div className="p-4 border-b border-gray-800 flex justify-between items-center">
              <div>
                <h3 className="text-sm font-semibold text-white">First Team Roster Baseline ({squadBaseline.squad_players.length} Players)</h3>
                <p className="text-xs text-gray-400">All player minutes and contribution percentiles verified from Bronze/Silver event data.</p>
              </div>
              <span className="text-xs font-mono px-2 py-1 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">
                OBSERVED_STATE
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-gray-300">
                <thead className="bg-gray-950/80 text-gray-400 uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="px-4 py-3">Player</th>
                    <th className="px-4 py-3">Pos</th>
                    <th className="px-4 py-3">Primary Role</th>
                    <th className="px-4 py-3">Age</th>
                    <th className="px-4 py-3">Season Min</th>
                    <th className="px-4 py-3">Contribution</th>
                    <th className="px-4 py-3">Tactical Fit</th>
                    <th className="px-4 py-3">Valuation</th>
                    <th className="px-4 py-3">Wage</th>
                    <th className="px-4 py-3">Contract</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60 font-mono">
                  {squadBaseline.squad_players.map((p) => (
                    <tr key={p.player_id} className="hover:bg-gray-800/30">
                      <td className="px-4 py-2.5 font-medium text-white font-sans">{p.name}</td>
                      <td className="px-4 py-2.5 text-blue-400">{p.position}</td>
                      <td className="px-4 py-2.5 text-gray-300 font-sans">{p.primary_role}</td>
                      <td className="px-4 py-2.5 text-gray-400">{p.age}</td>
                      <td className="px-4 py-2.5 text-gray-300">{p.minutes_played_season.toLocaleString()}m</td>
                      <td className="px-4 py-2.5 text-emerald-400">{p.contribution_percentile.toFixed(1)}%</td>
                      <td className="px-4 py-2.5 text-purple-400">{p.tactical_fit_score.toFixed(1)}</td>
                      <td className="px-4 py-2.5 text-gray-200">€{(p.market_valuation_eur / 1000000).toFixed(1)}M</td>
                      <td className="px-4 py-2.5 text-gray-400">€{(p.weekly_wage_eur / 1000).toFixed(0)}k/w</td>
                      <td className="px-4 py-2.5 text-gray-400">{p.contract_expiry_year}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────── Surface 2: Tactical System Simulator ────────────────── */}
      {activeTab === 'tactical' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-3 p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
            <span className="text-xs font-semibold uppercase text-gray-400">Target Formation:</span>
            {['4-3-3', '4-2-3-1', '3-5-2', '3-4-3', '4-4-2', '5-3-2', '4-1-4-1', '3-4-2-1'].map((fmt) => (
              <button
                key={fmt}
                onClick={() => setSelectedFormation(fmt)}
                className={`px-3 py-1 text-xs font-mono font-medium rounded transition ${
                  selectedFormation === fmt
                    ? 'bg-blue-600 text-white font-bold'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {fmt}
              </button>
            ))}
          </div>

          {tacticalEvaluation && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Tactical Metrics Card */}
              <div className="p-5 bg-gray-900/60 border border-gray-800 rounded-lg space-y-4">
                <div className="flex justify-between items-center border-b border-gray-800 pb-3">
                  <div>
                    <h3 className="text-base font-bold text-white">System Compatibility: {tacticalEvaluation.formation}</h3>
                    <p className="text-xs text-gray-400">Modelled structural fit against active squad roster.</p>
                  </div>
                  <span
                    className={`px-2.5 py-1 text-xs font-bold rounded ${
                      tacticalEvaluation.diagnostics_state === 'OPTIMAL'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : 'bg-amber-950 text-amber-400 border border-amber-800'
                    }`}
                  >
                    {tacticalEvaluation.diagnostics_state}
                  </span>
                </div>

                <div className="space-y-3 text-xs">
                  <div>
                    <div className="flex justify-between text-gray-300 mb-1">
                      <span>Overall Compatibility</span>
                      <span className="font-mono text-blue-400 font-bold">{tacticalEvaluation.overall_compatibility_score.toFixed(1)} / 100</span>
                    </div>
                    <div className="w-full bg-gray-800 rounded-full h-2">
                      <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${tacticalEvaluation.overall_compatibility_score}%` }}></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-gray-300 mb-1">
                      <span>Positional Coverage</span>
                      <span className="font-mono text-emerald-400 font-bold">{tacticalEvaluation.positional_coverage_pct.toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-gray-800 rounded-full h-2">
                      <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${tacticalEvaluation.positional_coverage_pct}%` }}></div>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pt-2">
                    <div className="p-3 bg-gray-950 rounded border border-gray-800">
                      <span className="text-gray-400">Progression Score:</span>
                      <div className="text-lg font-bold text-purple-400 font-mono">{tacticalEvaluation.build_up_progression_score}</div>
                    </div>
                    <div className="p-3 bg-gray-950 rounded border border-gray-800">
                      <span className="text-gray-400">Pressing Intensity (PPDA):</span>
                      <div className="text-lg font-bold text-amber-400 font-mono">{tacticalEvaluation.pressing_intensity_ppda}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Tactical Diagnostics & Structural Gaps */}
              <div className="p-5 bg-gray-900/60 border border-gray-800 rounded-lg space-y-4">
                <h3 className="text-base font-bold text-white">Tactical Diagnostics</h3>
                {tacticalEvaluation.detected_gaps?.length > 0 ? (
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-rose-400 uppercase tracking-wide">Structural Deficiencies:</span>
                    {tacticalEvaluation.detected_gaps.map((gap, i) => (
                      <div key={i} className="p-2.5 bg-rose-950/40 border border-rose-900/60 rounded text-xs text-rose-300 flex items-start gap-2">
                        <AlertTriangle size={14} className="shrink-0 mt-0.5 text-rose-400" />
                        <span>{gap}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-3 bg-emerald-950/40 border border-emerald-900/60 rounded text-xs text-emerald-300 flex items-center gap-2">
                    <CheckCircle size={15} className="text-emerald-400" />
                    <span>Positional coverage complete. Zero critical structural gaps detected in starter slots.</span>
                  </div>
                )}

                <div className="pt-2 text-xs space-y-2">
                  <span className="text-gray-400 font-semibold uppercase tracking-wide">Modelled Recommendations:</span>
                  {tacticalEvaluation.recommendations?.map((rec, i) => (
                    <div key={i} className="p-2 bg-gray-950 rounded border border-gray-800 text-gray-300">
                      • {rec}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ────────────────── Surface 3: Scenario Builder ────────────────── */}
      {activeTab === 'builder' && (
        <div className="p-6 bg-gray-900/60 border border-gray-800 rounded-lg space-y-6">
          <div>
            <h3 className="text-base font-bold text-white">Create Multi-Transfer Simulation Scenario</h3>
            <p className="text-xs text-gray-400">
              Define simulated roster movements (Buy, Sell, Retain, Promote). Changes are strictly evaluated under counterfactual boundaries.
            </p>
          </div>

          <form onSubmit={handleCreateScenario} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-300 uppercase mb-1">Scenario Name</label>
                <input
                  type="text"
                  value={newScenarioName}
                  onChange={(e) => setNewScenarioName(e.target.value)}
                  className="w-full bg-black/60 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-300 uppercase mb-1">Scenario Type</label>
                <select
                  value={newScenarioType}
                  onChange={(e) => setNewScenarioType(e.target.value)}
                  className="w-full bg-black/60 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                >
                  <option value="SELL_BUY">Scenario A: Sell X / Buy Y</option>
                  <option value="MULTI_BUY">Scenario B: Sell X / Buy Y + Z</option>
                  <option value="SELL_PROMOTE">Scenario C: Retain X / Promote Academy</option>
                  <option value="STATUS_QUO">Scenario E: Status Quo (No Transfers)</option>
                </select>
              </div>
            </div>

            {/* Movements List */}
            <div className="border border-gray-800 rounded p-4 space-y-3 bg-black/40">
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Simulated Roster Movements</span>
              {movements.map((m, idx) => (
                <div key={idx} className="grid grid-cols-6 gap-2 text-xs">
                  <div className="p-2 bg-gray-900 rounded font-mono font-bold text-blue-400">{m.action}</div>
                  <div className="col-span-2 p-2 bg-gray-900 rounded text-gray-200">{m.player_name} ({m.position})</div>
                  <div className="p-2 bg-gray-900 rounded text-emerald-400 font-mono">€{(m.fee_eur / 1000000).toFixed(1)}M</div>
                  <div className="p-2 bg-gray-900 rounded text-purple-400 font-mono">€{(m.weekly_wage_eur / 1000).toFixed(0)}k/w</div>
                  <div className="p-2 bg-gray-900 rounded text-gray-400">{m.tactical_role}</div>
                </div>
              ))}
            </div>

            <button
              type="submit"
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded flex items-center gap-2 transition"
            >
              <Play size={15} />
              Simulate Counterfactual Scenario
            </button>
          </form>
        </div>
      )}

      {/* ────────────────── Surface 4: Multi-Scenario Comparison ────────────────── */}
      {activeTab === 'comparison' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Side-by-Side Pareto Scenario Comparison</h3>
              <p className="text-xs text-gray-400">Never collapsed into an opaque score. Every dimension transparently exposed.</p>
            </div>
            <span className="text-xs font-mono text-gray-400">calibrated_multinomial_logit_v1 active</span>
          </div>

          {comparisonResult && (
            <div className="bg-gray-900/60 border border-gray-800 rounded-lg overflow-hidden">
              <table className="w-full text-left text-xs text-gray-300">
                <thead className="bg-gray-950/80 text-gray-400 uppercase tracking-wider font-semibold">
                  <tr>
                    <th className="px-4 py-3">Metric Dimension</th>
                    {comparisonResult.scenarios.map((s) => (
                      <th key={s.scenario_id} className="px-4 py-3 font-sans text-white text-sm">
                        {s.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60 font-mono">
                  <tr>
                    <td className="px-4 py-3 text-gray-400 font-sans font-medium">Net Spend (EUR)</td>
                    {comparisonResult.scenarios.map((s) => (
                      <td key={s.scenario_id} className={`px-4 py-3 font-bold ${s.net_spend_eur > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                        €{(s.net_spend_eur / 1000000).toFixed(1)}M
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-400 font-sans font-medium">Weekly Wage Bill Delta</td>
                    {comparisonResult.scenarios.map((s) => (
                      <td key={s.scenario_id} className={`px-4 py-3 ${s.wage_bill_delta_weekly <= 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {s.wage_bill_delta_weekly > 0 ? '+' : ''}€{(s.wage_bill_delta_weekly / 1000).toFixed(0)}k / wk
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-400 font-sans font-medium">Tactical System Fit Delta</td>
                    {comparisonResult.scenarios.map((s) => (
                      <td key={s.scenario_id} className="px-4 py-3 text-purple-400 font-bold">
                        {s.tactical_fit_delta > 0 ? '+' : ''}{s.tactical_fit_delta.toFixed(1)} pts
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-400 font-sans font-medium">Squad Depth Delta</td>
                    {comparisonResult.scenarios.map((s) => (
                      <td key={s.scenario_id} className="px-4 py-3 text-blue-400 font-bold">
                        {s.squad_depth_rating_delta > 0 ? '+' : ''}{s.squad_depth_rating_delta.toFixed(1)} pts
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-400 font-sans font-medium">Match Prediction Win Prob</td>
                    {comparisonResult.scenarios.map((s) => (
                      <td key={s.scenario_id} className="px-4 py-3 text-emerald-300">
                        {s.match_impact?.is_supported
                          ? `${(s.match_impact.scenario_win_prob * 100).toFixed(1)}% (${s.match_impact.win_prob_delta > 0 ? '+' : ''}${(s.match_impact.win_prob_delta * 100).toFixed(1)}%)`
                          : 'SCENARIO_UNSUPPORTED'}
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td className="px-4 py-3 text-gray-400 font-sans font-medium">Prediction Boundary Contract</td>
                    {comparisonResult.scenarios.map((s) => (
                      <td key={s.scenario_id} className="px-4 py-3 text-xs font-sans">
                        <span className={`px-2 py-0.5 rounded font-mono ${s.match_impact?.is_supported ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                          {s.match_impact?.status || 'VALID'}
                        </span>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ────────────────── Surface 5: Budget Pareto Frontier ────────────────── */}
      {activeTab === 'pareto' && (
        <div className="space-y-6">
          <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Constrained Optimization: Pareto Decision Frontier</h3>
              <p className="text-xs text-gray-400">Multiple mathematically efficient squad strategies without opaque single scores.</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Ceiling:</span>
              <span className="text-sm font-bold text-emerald-400 font-mono">€{(budgetCeiling / 1000000).toFixed(0)}M</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {paretoFrontier.map((alt) => (
              <div key={alt.alternative_id} className="p-5 bg-gray-900/60 border border-gray-800 rounded-lg space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-start">
                    <h4 className="text-sm font-bold text-white">{alt.strategy_name}</h4>
                    <span className="text-xs px-2 py-0.5 bg-blue-950 text-blue-400 border border-blue-800 rounded font-mono">
                      PARETO
                    </span>
                  </div>
                  <div className="mt-4 space-y-2 text-xs font-mono">
                    <div className="flex justify-between text-gray-300">
                      <span>Total Acquisition Cost:</span>
                      <span className="text-emerald-400 font-bold">€{(alt.total_spend_eur / 1000000).toFixed(1)}M</span>
                    </div>
                    <div className="flex justify-between text-gray-300">
                      <span>Tactical Coverage:</span>
                      <span className="text-purple-400 font-bold">{alt.tactical_coverage_score.toFixed(1)} / 100</span>
                    </div>
                    <div className="flex justify-between text-gray-300">
                      <span>Squad Depth Rating:</span>
                      <span className="text-blue-400 font-bold">{alt.depth_rating.toFixed(1)} / 100</span>
                    </div>
                    <div className="flex justify-between text-gray-300">
                      <span>Operational Risk Score:</span>
                      <span className="text-amber-400 font-bold">{alt.risk_score.toFixed(1)} / 100</span>
                    </div>
                    <div className="flex justify-between text-gray-300">
                      <span>Average Recruit Age:</span>
                      <span className="text-gray-400 font-bold">{alt.average_age.toFixed(1)} yrs</span>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-gray-800 text-xs text-gray-400">
                  <span className="font-semibold text-gray-300 block mb-1">Trade-off Profile:</span>
                  {alt.trade_off_summary}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────── Surface 6: Squad Depth & Congestion ────────────────── */}
      {activeTab === 'depth' && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-3 p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
            <span className="text-xs font-semibold uppercase text-gray-400">Fixture Schedule Load:</span>
            {[
              { id: 'DOMESTIC_LEAGUE', label: 'Domestic League Only (38 Matches)' },
              { id: 'DOMESTIC_PLUS_EUROPE', label: 'Domestic + Champions League (52+ Matches)' },
              { id: 'SEVERE_CONGESTION', label: 'Congested 3-Match Weeks (Domestic + UCL + Cups)' },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => setCongestionMode(m.id)}
                className={`px-3 py-1 text-xs font-medium rounded transition ${
                  congestionMode === m.id
                    ? 'bg-blue-600 text-white font-bold'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {depthEvaluation && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
                  <div className="text-xs text-gray-400 uppercase font-semibold">Depth State</div>
                  <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">{depthEvaluation.depth_state}</div>
                </div>
                <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
                  <div className="text-xs text-gray-400 uppercase font-semibold">Overall Depth Rating</div>
                  <div className="text-xl font-bold text-blue-400 mt-1 font-mono">{depthEvaluation.overall_depth_rating.toFixed(1)} / 100</div>
                </div>
                <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
                  <div className="text-xs text-gray-400 uppercase font-semibold">Active Absences Tested</div>
                  <div className="text-xl font-bold text-amber-400 mt-1 font-mono">{depthEvaluation.simulated_absences.length}</div>
                </div>
                <div className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg">
                  <div className="text-xs text-gray-400 uppercase font-semibold">Critical Vulnerabilities</div>
                  <div className="text-xl font-bold text-rose-400 mt-1 font-mono">{depthEvaluation.critical_vulnerabilities.length}</div>
                </div>
              </div>

              {/* Positional Breakdown */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {depthEvaluation.position_coverages?.map((pos, idx) => (
                  <div key={idx} className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white text-sm">{pos.position_group}</span>
                      <span className={`text-xs px-2 py-0.5 rounded font-mono ${pos.depth_state === 'SOLID' ? 'bg-emerald-950 text-emerald-400' : 'bg-amber-950 text-amber-400'}`}>
                        {pos.depth_state}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 space-y-1 font-mono">
                      <div>Starters: {pos.starters_count}</div>
                      <div>Primary Reserves: {pos.primary_reserves_count}</div>
                      <div>Academy Backup: {pos.academy_backups_count}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ────────────────── Surface 7: Sensitivity & Robustness ────────────────── */}
      {activeTab === 'sensitivity' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Sensitivity Intervals */}
            {sensitivityProfile && (
              <div className="p-5 bg-gray-900/60 border border-gray-800 rounded-lg space-y-4">
                <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                  <h3 className="text-sm font-bold text-white">Sensitivity Intervals (Low / Base / High)</h3>
                  <span className="text-xs text-amber-400 font-mono">NON-STATISTICAL CI</span>
                </div>
                <p className="text-xs text-gray-400">{sensitivityProfile.methodology_note}</p>
                <div className="space-y-3 font-mono text-xs">
                  {sensitivityProfile.intervals?.map((interval, i) => (
                    <div key={i} className="p-3 bg-gray-950 rounded border border-gray-800 space-y-1">
                      <div className="flex justify-between text-gray-300 font-sans font-semibold">
                        <span>{interval.dimension}</span>
                        <span className="text-blue-400 font-mono">{interval.unit}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center pt-1">
                        <div className="p-1.5 bg-gray-900 rounded">
                          <span className="text-gray-500 block text-2xs uppercase">Low</span>
                          <span className="text-emerald-400 font-bold">{interval.low_value.toLocaleString()}</span>
                        </div>
                        <div className="p-1.5 bg-gray-800 rounded border border-gray-700">
                          <span className="text-gray-400 block text-2xs uppercase">Base</span>
                          <span className="text-white font-bold">{interval.base_value.toLocaleString()}</span>
                        </div>
                        <div className="p-1.5 bg-gray-900 rounded">
                          <span className="text-gray-500 block text-2xs uppercase">High</span>
                          <span className="text-rose-400 font-bold">{interval.high_value.toLocaleString()}</span>
                        </div>
                      </div>
                      <div className="text-2xs text-gray-500 font-sans pt-1">• {interval.perturbation_rationale}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Robustness Analysis */}
            {robustnessReport && (
              <div className="p-5 bg-gray-900/60 border border-gray-800 rounded-lg space-y-4">
                <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                  <h3 className="text-sm font-bold text-white">Scenario Robustness Stress-Testing</h3>
                  <span className={`px-2.5 py-0.5 text-xs font-bold rounded font-mono ${robustnessReport.robustness_class === 'STABLE' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-amber-950 text-amber-400 border border-amber-800'}`}>
                    {robustnessReport.robustness_class}
                  </span>
                </div>
                <div className="p-3 bg-gray-950 rounded border border-gray-800 flex justify-between items-center">
                  <span className="text-xs text-gray-300">Resilience Score:</span>
                  <span className="text-lg font-bold text-blue-400 font-mono">{robustnessReport.overall_resilience_score.toFixed(1)} / 100</span>
                </div>

                <div className="space-y-2 text-xs">
                  <span className="text-gray-400 uppercase font-semibold">Stress Perturbation Results:</span>
                  {robustnessReport.perturbation_tests?.map((t, idx) => (
                    <div key={idx} className="p-2.5 bg-gray-950 rounded border border-gray-800 space-y-1">
                      <div className="flex justify-between items-center">
                        <span className="font-semibold text-white">{t.stress_factor} ({t.applied_delta_pct > 0 ? '+' : ''}{t.applied_delta_pct}%)</span>
                        <span className={`px-1.5 py-0.5 text-2xs rounded font-mono ${t.breached ? 'bg-rose-950 text-rose-400' : 'bg-emerald-950 text-emerald-400'}`}>
                          {t.breached ? 'BREACHED' : 'TOLERATED'}
                        </span>
                      </div>
                      <p className="text-2xs text-gray-400">{t.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ────────────────── Surface 8: Evidence Graph ────────────────── */}
      {activeTab === 'evidence' && evidenceGraph && (
        <div className="p-6 bg-gray-900/60 border border-gray-800 rounded-lg space-y-5">
          <div className="flex justify-between items-center border-b border-gray-800 pb-3">
            <div>
              <h3 className="text-base font-bold text-white">Unified 12-Stage Scenario Evidence Graph</h3>
              <p className="text-xs text-gray-400">Cryptographically verifiable lineage from Club Context to Counterfactual Outputs.</p>
            </div>
            <div className="text-xs font-mono text-gray-400 bg-gray-950 px-3 py-1.5 rounded border border-gray-800">
              SHA-256: {evidenceGraph.graph_digest?.slice(0, 24)}...
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {evidenceGraph.nodes?.map((n) => (
              <div key={n.node_id} className="p-3.5 bg-gray-950 rounded border border-gray-800/80 space-y-1.5">
                <div className="flex justify-between items-center">
                  <span className="text-2xs font-mono text-gray-500 uppercase">{n.stage}</span>
                  <span className={`text-2xs font-mono px-1.5 py-0.5 rounded ${
                    n.epistemic_status === 'OBSERVED' ? 'bg-emerald-950 text-emerald-400' :
                    n.epistemic_status === 'MODELLED' ? 'bg-purple-950 text-purple-400' :
                    n.epistemic_status === 'COUNTERFACTUAL' ? 'bg-amber-950 text-amber-400' : 'bg-cyan-950 text-cyan-400'
                  }`}>
                    {n.epistemic_status}
                  </span>
                </div>
                <div className="font-semibold text-white text-xs">{n.label}</div>
                <div className="text-2xs text-gray-400 font-mono">Source: {n.source_component}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────── Surface 9: Decision Records & Follow-Up ────────────────── */}
      {activeTab === 'decisions' && (
        <div className="space-y-6">
          {/* Finalize Form */}
          <div className="p-5 bg-gray-900/60 border border-gray-800 rounded-lg space-y-4">
            <h3 className="text-base font-bold text-white">Finalize Immutable Decision Record V2</h3>
            {finalizeSuccess && (
              <div className="p-3 bg-emerald-950/60 border border-emerald-800 text-xs text-emerald-300 rounded flex items-center gap-2">
                <CheckCircle size={15} />
                <span>{finalizeSuccess}</span>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Signer / Authorized Official</label>
                <input
                  type="text"
                  value={decisionSigner}
                  onChange={(e) => setDecisionSigner(e.target.value)}
                  className="w-full bg-black/60 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Human Annotation & Rationale</label>
                <input
                  type="text"
                  value={decisionAnnotations}
                  onChange={(e) => setDecisionAnnotations(e.target.value)}
                  className="w-full bg-black/60 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <button
              onClick={handleFinalizeDecision}
              className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold uppercase tracking-wider rounded flex items-center gap-1.5 transition"
            >
              <Lock size={14} />
              Cryptographically Commit Decision
            </button>
          </div>

          {/* Existing Records */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400">Historical Decision Records ({decisionRecords.length})</h3>
            {decisionRecords.map((rec) => (
              <div key={rec.decision_id} className="p-4 bg-gray-900/60 border border-gray-800 rounded-lg space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="text-sm font-bold text-white">{rec.project_name}</h4>
                    <p className="text-xs text-gray-400">Decision: {rec.final_decision} → {rec.chosen_scenario_name}</p>
                  </div>
                  <span className="text-xs font-mono text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                    {rec.epistemic_status}
                  </span>
                </div>
                <div className="text-2xs text-gray-500 font-mono">
                  ID: {rec.decision_id} | Signed: {rec.signed_by} | Digest: {rec.audit_digest?.slice(0, 24)}...
                </div>
                <p className="text-xs text-gray-300 italic">"{rec.human_annotations}"</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
