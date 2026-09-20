import React, { useState, useEffect } from 'react';
import { 
  Dices, 
  Play, 
  Square, 
  RotateCcw, 
  CheckCircle2, 
  XCircle, 
  ShieldCheck, 
  ShieldAlert, 
  TrendingUp, 
  Activity, 
  Sliders, 
  FileText, 
  HelpCircle,
  Clock,
  BarChart2,
  Layers,
  Save,
  RefreshCw,
  FolderOpen
} from 'lucide-react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { useScriptRunner } from '../useScriptRunner';

interface CandidateInfo {
  id: string;
  dir: string;
  hasTrades: boolean;
  hasMonteCarlo: boolean;
  isCertified: boolean | null;
  passRate: number | null;
  p1PassRate: number | null;
  p2PassRate: number | null;
  worstMaxDD: number | null;
}

interface PhaseResult {
  target_pct: number;
  pass_count: number;
  pass_rate: number;
  breach_max_dd_count: number;
  breach_max_rate: number;
  breach_daily_dd_count: number;
  breach_daily_rate: number;
  incomplete_count: number;
  incomplete_rate: number;
  median_days: number;
  p10_days: number;
  p90_days: number;
  median_max_dd: number;
  p90_max_dd: number;
  p99_max_dd: number;
  largest_profit_day: number;
  largest_loss_day: number;
  avg_daily: number;
  p95_profit_day: number;
  p95_loss_day: number;
  sample_equity_curves?: number[][];
}

interface RunInfo {
  name: string;
  path: string;
  passedCandidates: number;
  candidates: string[];
}

interface MonteCarloData {
  candidate: string;
  run_folder?: string | null;
  deposit: number;
  simulations: number;
  no_max_days?: boolean;
  max_days_enabled?: boolean;
  max_days?: number | null;
  is_certified: boolean;
  combined_pass_rate: number;
  worst_breach_max_dd: number;
  phase1: PhaseResult;
  phase2: PhaseResult;
  doc_path?: string | null;
  historical_pnl_count?: number;
}

export function MonteCarlo() {
  const [candidates, setCandidates] = useState<CandidateInfo[]>([]);
  const [availableRuns, setAvailableRuns] = useState<RunInfo[]>([]);
  const [runFolder, setRunFolder] = useState<string>('');
  const [customRunFolder, setCustomRunFolder] = useState<string>('');
  const [selectedCandidate, setSelectedCandidate] = useState<string>('cand_014');
  const [customCandidate, setCustomCandidate] = useState<string>('');
  const [simulations, setSimulations] = useState<number>(5000);
  const [startingCapital, setStartingCapital] = useState<number>(2500);
  const [phase1Target, setPhase1Target] = useState<number>(8.0);
  const [phase2Target, setPhase2Target] = useState<number>(5.0);
  const [maxDrawdown, setMaxDrawdown] = useState<number>(10.0);
  const [dailyDrawdown, setDailyDrawdown] = useState<number>(5.0);
  const [blockSize, setBlockSize] = useState<number>(10);
  const [maxDays, setMaxDays] = useState<number>(250);
  const [noMaxDays, setNoMaxDays] = useState<boolean>(false);

  const [activeCandidateData, setActiveCandidateData] = useState<MonteCarloData | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [loadingResult, setLoadingResult] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();

  // Fetch candidates and runs from workspace
  const fetchCandidatesAndRuns = async () => {
    setLoadingCandidates(true);
    try {
      const [candRes, workRes] = await Promise.all([
        fetch('/api/candidates'),
        fetch('/api/workspace')
      ]);

      if (candRes.ok) {
        const data = await candRes.json();
        const cands: CandidateInfo[] = data.candidates || [];
        setCandidates(cands);
        if (cands.length > 0 && !cands.some(c => c.id === selectedCandidate)) {
          setSelectedCandidate(cands[0].id);
        }
      }

      if (workRes.ok) {
        const wData = await workRes.json();
        const runsList: RunInfo[] = Array.isArray(wData.runsDetailed)
          ? wData.runsDetailed
          : Array.isArray(wData.runs)
            ? wData.runs.map((r: any) => typeof r === 'string' ? { name: r, path: r, passedCandidates: 0, candidates: [] } : r)
            : [];
        setAvailableRuns(runsList);
      }
    } catch (e) {
      console.error("Failed to load candidates/runs", e);
    } finally {
      setLoadingCandidates(false);
    }
  };

  // Fetch candidate Monte Carlo result
  const fetchCandidateResult = async (candId: string, specificRun?: string) => {
    if (!candId) return;
    setLoadingResult(true);
    try {
      const effRun = specificRun ?? (customRunFolder.trim() || runFolder.trim());
      const queryParam = effRun ? `&run_folder=${encodeURIComponent(effRun)}` : '';
      const res = await fetch(`/api/candidate-monte-carlo?candidate=${candId}${queryParam}`);
      if (res.ok) {
        const data = await res.json();
        setActiveCandidateData(data);
      } else {
        setActiveCandidateData(null);
      }
    } catch (e) {
      setActiveCandidateData(null);
    } finally {
      setLoadingResult(false);
    }
  };

  // Load config defaults
  const loadConfigDefaults = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const cfg = await res.json();
        if (cfg.deposit) setStartingCapital(parseFloat(cfg.deposit));
        const mc = cfg.monte_carlo_candidate;
        if (mc) {
          if (mc.target_candidate) setSelectedCandidate(mc.target_candidate);
          if (mc.run_folder || mc.run_dir) {
            setRunFolder(mc.run_folder || mc.run_dir);
            setCustomRunFolder(mc.run_folder || mc.run_dir);
          }
          if (mc.simulations) setSimulations(mc.simulations);
          if (mc.phase1_target_pct) setPhase1Target(mc.phase1_target_pct);
          if (mc.phase2_target_pct) setPhase2Target(mc.phase2_target_pct);
          if (mc.max_dd_limit_pct) setMaxDrawdown(mc.max_dd_limit_pct);
          if (mc.daily_dd_limit_pct) setDailyDrawdown(mc.daily_dd_limit_pct);
          if (mc.block_size) setBlockSize(mc.block_size);
          if (mc.max_days) setMaxDays(mc.max_days);
          if (mc.no_max_days !== undefined) setNoMaxDays(!!mc.no_max_days);
          else if (mc.max_days_enabled !== undefined) setNoMaxDays(!mc.max_days_enabled);
        }
      }
    } catch (e) {
      console.error("Failed to load config", e);
    }
  };

  useEffect(() => {
    fetchCandidatesAndRuns();
    loadConfigDefaults();
  }, []);

  useEffect(() => {
    const target = customCandidate.trim() || selectedCandidate;
    const effRun = customRunFolder.trim() || runFolder.trim();
    if (target) {
      fetchCandidateResult(target, effRun);
    }
  }, [selectedCandidate, customCandidate, runFolder, customRunFolder]);

  // Save current settings to config.json
  const handleSaveConfig = async () => {
    const target = customCandidate.trim() || selectedCandidate;
    const effRun = customRunFolder.trim() || runFolder.trim();
    try {
      const res = await fetch('/api/candidate-monte-carlo/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_candidate: target,
          run_folder: effRun || null,
          simulations,
          phase1_target_pct: phase1Target,
          phase2_target_pct: phase2Target,
          max_dd_limit_pct: maxDrawdown,
          daily_dd_limit_pct: dailyDrawdown,
          block_size: blockSize,
          max_days: maxDays,
          no_max_days: noMaxDays,
          max_days_enabled: !noMaxDays,
        }),
      });
      if (res.ok) {
        setSaveMessage("Monte Carlo settings saved to config.json");
        setTimeout(() => setSaveMessage(null), 3000);
      }
    } catch (e) {
      setSaveMessage("Failed to save settings");
      setTimeout(() => setSaveMessage(null), 3000);
    }
  };

  // Run Monte Carlo simulation script
  const handleRunSimulation = () => {
    const target = customCandidate.trim() || selectedCandidate;
    if (!target) return;

    const effRunFolder = customRunFolder.trim() || runFolder.trim();

    let cliArgs = `${target} --sims ${simulations} --p1 ${phase1Target} --p2 ${phase2Target} --max-dd ${maxDrawdown} --daily-dd ${dailyDrawdown} --block-size ${blockSize} --deposit ${startingCapital}`;
    
    if (effRunFolder) {
      cliArgs += ` --run-dir "${effRunFolder}"`;
    }

    if (noMaxDays) {
      cliArgs += ` --no-max-days`;
    } else {
      cliArgs += ` --max-days ${maxDays}`;
    }

    runScript('run_can_monte_carlo.py', {
      args: cliArgs,
      onStart: () => {
        // clear previous message
      },
      onDone: (exitCode) => {
        // Refresh result once finished
        fetchCandidateResult(target, effRunFolder);
        fetchCandidatesAndRuns();
      }
    });
  };

  const activeCandInfo = candidates.find(c => c.id === (customCandidate.trim() || selectedCandidate));

  return (
    <div className="flex flex-col h-full space-y-5">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <SectionHeader 
          title="🎲 Candidate Monte Carlo Simulation" 
          subtitle="Run block-bootstrap resamplings against prop-firm profit targets and drawdown rules for a specific candidate" 
        />
        
        <div className="flex items-center gap-2.5">
          <Button 
            variant="secondary" 
            onClick={() => { fetchCandidates(); fetchCandidateResult(customCandidate.trim() || selectedCandidate); }} 
            className="text-xs py-2 px-3"
            disabled={loadingCandidates}
          >
            <RefreshCw size={14} className={loadingCandidates ? "animate-spin" : ""} />
            <span>Refresh Candidates</span>
          </Button>

          <Button 
            variant="secondary" 
            onClick={handleSaveConfig} 
            className="text-xs py-2 px-3 border-amber-600/40 text-amber-300 hover:text-white"
          >
            <Save size={14} />
            <span>Save Settings</span>
          </Button>
        </div>
      </div>

      {saveMessage && (
        <div className="bg-emerald-950/60 border border-emerald-600/50 text-emerald-300 px-4 py-2 rounded-lg text-xs flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 size={15} />
          <span>{saveMessage}</span>
        </div>
      )}

      {/* Target Candidate & Configuration Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Candidate Selector Card */}
        <Card className="p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-white text-sm font-bold flex items-center gap-2">
                <Layers size={16} className="text-[#f59e0b]" />
                Target Candidate
              </h3>
              <span className="text-[11px] font-mono text-[#8b95a6]">
                {candidates.length} candidate{candidates.length === 1 ? '' : 's'} available
              </span>
            </div>

            <p className="text-xs text-[#8b95a6] mb-4">
              Select an optimization pass candidate or enter a custom candidate folder.
            </p>

            {/* Candidate Dropdown */}
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-medium text-[#8b95a6] uppercase tracking-wider block mb-1.5">
                  Select Discovered Candidate
                </label>
                <select
                  value={selectedCandidate}
                  onChange={(e) => {
                    setSelectedCandidate(e.target.value);
                    setCustomCandidate('');
                  }}
                  className="w-full bg-[#141b2d] border border-[#2d3748] text-white rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-[#f59e0b]"
                >
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id} {c.isCertified ? '— ✔ Certified' : c.hasMonteCarlo ? '— ✘ Not Certified' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* Or manual candidate name */}
              <div>
                <label className="text-[11px] font-medium text-[#8b95a6] uppercase tracking-wider block mb-1.5">
                  Or Custom Candidate ID
                </label>
                <input
                  type="text"
                  placeholder="e.g. cand_014"
                  value={customCandidate}
                  onChange={(e) => setCustomCandidate(e.target.value)}
                  className="w-full bg-[#141b2d] border border-[#2d3748] text-white rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-[#f59e0b]"
                />
              </div>

              {/* Run Folder Selection (User Request) */}
              <div className="pt-2.5 border-t border-[#1e293b] space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-medium text-[#8b95a6] uppercase tracking-wider flex items-center gap-1.5">
                    <FolderOpen size={13} className="text-[#f59e0b]" />
                    Run Folder Location
                  </label>
                  <span className="text-[10px] text-[#64748b]">Optional</span>
                </div>

                {availableRuns.length > 0 && (
                  <select
                    value={runFolder}
                    onChange={(e) => {
                      const val = e.target.value;
                      setRunFolder(val);
                      setCustomRunFolder(val);
                      const matched = availableRuns.find(r => r.path === val || r.name === val);
                      if (matched && Array.isArray(matched.candidates) && matched.candidates.length > 0) {
                        if (!matched.candidates.includes(selectedCandidate)) {
                          setSelectedCandidate(matched.candidates[0]);
                          setCustomCandidate('');
                        }
                      }
                    }}
                    className="w-full bg-[#141b2d] border border-[#2d3748] text-white rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-[#f59e0b]"
                  >
                    <option value="">Auto-detect across latest optimization runs</option>
                    {availableRuns.map((r) => {
                      const candCount = Array.isArray(r.candidates) ? r.candidates.length : 0;
                      return (
                        <option key={r.path || r.name} value={r.path || r.name}>
                          {r.name} ({candCount} candidate{candCount === 1 ? '' : 's'})
                        </option>
                      );
                    })}
                  </select>
                )}

                <input
                  type="text"
                  placeholder="Or enter path, e.g. optimization_runs/TRB/run_20260312_153022"
                  value={customRunFolder}
                  onChange={(e) => {
                    setCustomRunFolder(e.target.value);
                    setRunFolder(e.target.value);
                  }}
                  className="w-full bg-[#141b2d] border border-[#2d3748] text-white rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-[#f59e0b]"
                />
                <span className="text-[10px] text-[#64748b] block">
                  Leave blank for auto-detect or specify a run directory where this candidate resides.
                </span>
              </div>
            </div>
          </div>

          {/* Candidate Info Badge */}
          <div className="mt-5 p-3 rounded-lg bg-[#0b101d] border border-[#2d3748] space-y-1.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-[#8b95a6]">Status:</span>
              {activeCandInfo?.hasMonteCarlo ? (
                <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                  activeCandInfo.isCertified 
                    ? 'bg-emerald-950/60 border border-emerald-600/40 text-emerald-300' 
                    : 'bg-red-950/60 border border-red-600/40 text-red-300'
                }`}>
                  {activeCandInfo.isCertified ? 'CERTIFIED' : 'NOT CERTIFIED'}
                </span>
              ) : (
                <span className="text-[#64748b]">Ready for Monte Carlo</span>
              )}
            </div>

            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className="text-[#8b95a6]">Resolved Directory:</span>
              <span className="text-white truncate max-w-[180px]" title={customRunFolder || activeCandInfo?.dir || ''}>
                {customRunFolder || activeCandInfo?.dir || 'Auto-scan'}
              </span>
            </div>

            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className="text-[#8b95a6]">Trade History:</span>
              <span className={activeCandInfo?.hasTrades ? "text-emerald-400" : "text-amber-400"}>
                {activeCandInfo?.hasTrades ? "trades.csv detected" : "report calibration"}
              </span>
            </div>
          </div>
        </Card>

        {/* Simulation Horizon & Bootstrap Parameters */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-white text-sm font-bold flex items-center gap-2">
              <Sliders size={16} className="text-[#3b82f6]" />
              Simulation Horizons
            </h3>
            <span className="text-[11px] text-blue-400 font-mono">Block-Bootstrap</span>
          </div>

          <div className="space-y-3.5 text-xs">
            {/* Iterations */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-[#8b95a6]">Iterations (Runs)</span>
                <span className="text-white font-mono font-bold">{simulations.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-2">
                {[1000, 2500, 5000, 10000].map(n => (
                  <button
                    key={n}
                    onClick={() => setSimulations(n)}
                    className={`flex-1 py-1 px-2 rounded text-[11px] font-mono border transition-colors ${
                      simulations === n 
                        ? 'bg-amber-500/20 border-amber-500 text-amber-300 font-bold' 
                        : 'bg-[#141b2d] border-[#2d3748] text-[#8b95a6] hover:text-white'
                    }`}
                  >
                    {n >= 1000 ? `${n / 1000}k` : n}
                  </button>
                ))}
              </div>
            </div>

            {/* Starting Balance */}
            <div>
              <label className="text-[#8b95a6] block mb-1">Deposit / Account Capital ($)</label>
              <input
                type="number"
                value={startingCapital}
                onChange={(e) => setStartingCapital(parseFloat(e.target.value) || 0)}
                className="w-full bg-[#141b2d] border border-[#2d3748] rounded px-3 py-1.5 text-white font-mono focus:outline-none focus:border-[#f59e0b]"
              />
            </div>

            {/* Block Size */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="text-[#8b95a6]">Resampling Block Size (Days)</span>
                <span className="text-white font-mono">{blockSize} days</span>
              </div>
              <input
                type="range"
                min={2}
                max={30}
                step={1}
                value={blockSize}
                onChange={(e) => setBlockSize(parseInt(e.target.value))}
                className="w-full accent-amber-500"
              />
              <span className="text-[10px] text-[#64748b] block mt-0.5">
                Preserves volatility clustering and multi-day drawdown streaks
              </span>
            </div>

            {/* Max Horizon Days & Toggle (User Request) */}
            <div className="pt-2.5 border-t border-[#1e293b] space-y-2.5">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-white font-medium block text-xs">Max Trading Days</span>
                  <span className="text-[10px] text-[#8b95a6]">
                    {noMaxDays ? "Unlimited (No cutoff day cap)" : `${maxDays} trading days cutoff`}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-[#8b95a6]">
                    {noMaxDays ? 'Off (No Max)' : 'Active'}
                  </span>
                  <button
                    type="button"
                    onClick={() => setNoMaxDays(!noMaxDays)}
                    className={`relative inline-flex h-5 w-10 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      noMaxDays ? 'bg-amber-500' : 'bg-[#2d3748]'
                    }`}
                    title={noMaxDays ? "Disable Max Days: simulations run without day limits" : "Enable Max Days limit"}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        noMaxDays ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {noMaxDays ? (
                <div className="p-2.5 rounded-lg bg-amber-950/30 border border-amber-600/30 text-[11px] text-amber-300 flex items-start gap-2">
                  <Clock size={15} className="shrink-0 mt-0.5 text-amber-400" />
                  <div>
                    <strong>Unlimited Trading Days Enabled:</strong>
                    <div className="text-[10px] text-amber-400/80 mt-0.5">
                      Max trading days constraint is switched off. Simulations proceed until the profit target is hit or a drawdown rule is breached.
                    </div>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-[#8b95a6]">Trading Days Horizon</span>
                    <span className="text-white font-mono">{maxDays} days</span>
                  </div>
                  <input
                    type="range"
                    min={50}
                    max={500}
                    step={25}
                    value={maxDays}
                    onChange={(e) => setMaxDays(parseInt(e.target.value))}
                    className="w-full accent-blue-500"
                  />
                  <span className="text-[10px] text-[#64748b] block mt-0.5">
                    Approximately 250 trading days = 1 calendar trading year
                  </span>
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Prop-Firm Gates & Risk Limits */}
        <Card className="p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-white text-sm font-bold flex items-center gap-2">
                <ShieldCheck size={16} className="text-emerald-400" />
                Prop Firm Gate Thresholds
              </h3>
              <span className="text-[11px] text-emerald-400 font-mono">Two-Phase</span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="text-[#8b95a6] block mb-1">Phase 1 Target (%)</label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.5"
                    value={phase1Target}
                    onChange={(e) => setPhase1Target(parseFloat(e.target.value) || 0)}
                    className="w-full bg-[#141b2d] border border-[#2d3748] rounded px-2.5 py-1.5 text-white font-mono pr-7 focus:outline-none focus:border-[#f59e0b]"
                  />
                  <span className="absolute right-2.5 top-1.5 text-[#64748b]">%</span>
                </div>
                <span className="text-[10px] text-emerald-400 block mt-0.5 font-mono">
                  +${((startingCapital * phase1Target) / 100).toFixed(0)}
                </span>
              </div>

              <div>
                <label className="text-[#8b95a6] block mb-1">Phase 2 Target (%)</label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.5"
                    value={phase2Target}
                    onChange={(e) => setPhase2Target(parseFloat(e.target.value) || 0)}
                    className="w-full bg-[#141b2d] border border-[#2d3748] rounded px-2.5 py-1.5 text-white font-mono pr-7 focus:outline-none focus:border-[#f59e0b]"
                  />
                  <span className="absolute right-2.5 top-1.5 text-[#64748b]">%</span>
                </div>
                <span className="text-[10px] text-blue-400 block mt-0.5 font-mono">
                  +${((startingCapital * phase2Target) / 100).toFixed(0)}
                </span>
              </div>

              <div>
                <label className="text-[#8b95a6] block mb-1">Max Static DD (%)</label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.5"
                    value={maxDrawdown}
                    onChange={(e) => setMaxDrawdown(parseFloat(e.target.value) || 0)}
                    className="w-full bg-[#141b2d] border border-[#2d3748] rounded px-2.5 py-1.5 text-white font-mono pr-7 focus:outline-none focus:border-red-500"
                  />
                  <span className="absolute right-2.5 top-1.5 text-[#64748b]">%</span>
                </div>
                <span className="text-[10px] text-red-400 block mt-0.5 font-mono">
                  -${((startingCapital * maxDrawdown) / 100).toFixed(0)} limit
                </span>
              </div>

              <div>
                <label className="text-[#8b95a6] block mb-1">Daily DD Limit (%)</label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.5"
                    value={dailyDrawdown}
                    onChange={(e) => setDailyDrawdown(parseFloat(e.target.value) || 0)}
                    className="w-full bg-[#141b2d] border border-[#2d3748] rounded px-2.5 py-1.5 text-white font-mono pr-7 focus:outline-none focus:border-red-500"
                  />
                  <span className="absolute right-2.5 top-1.5 text-[#64748b]">%</span>
                </div>
                <span className="text-[10px] text-red-400 block mt-0.5 font-mono">
                  From prev day close
                </span>
              </div>
            </div>
          </div>

          {/* Action Trigger Buttons */}
          <div className="pt-4 mt-4 border-t border-[#2d3748] flex items-center gap-2">
            {isRunning ? (
              <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700 w-full text-xs font-bold py-2.5">
                <Square size={15} />
                <span>Stop Simulation</span>
              </Button>
            ) : (
              <Button onClick={handleRunSimulation} className="w-full text-xs font-bold py-2.5 bg-[#f59e0b] hover:bg-[#d97706] text-black">
                <Play size={15} />
                <span>Run Monte Carlo ({simulations.toLocaleString()} Sims)</span>
              </Button>
            )}
          </div>
        </Card>
      </div>

      {/* Certification Result Banner */}
      {activeCandidateData && (
        <Card className={`p-5 border transition-all animate-in fade-in ${
          activeCandidateData.is_certified 
            ? 'bg-emerald-950/20 border-emerald-500/50' 
            : 'bg-red-950/20 border-red-500/50'
        }`}>
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className={`p-3 rounded-xl ${
                activeCandidateData.is_certified 
                  ? 'bg-emerald-500 text-black' 
                  : 'bg-red-500 text-white'
              }`}>
                {activeCandidateData.is_certified ? <ShieldCheck size={28} /> : <ShieldAlert size={28} />}
              </div>

              <div>
                <div className="flex items-center gap-3">
                  <h3 className="text-xl font-bold text-white tracking-wide">
                    {activeCandidateData.is_certified ? "VERDICT: CERTIFIED" : "VERDICT: NOT CERTIFIED"}
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  <span className="px-2 py-0.5 rounded text-xs font-mono bg-[#111827] border border-[#2d3748] text-white">
                    {activeCandidateData.candidate}
                  </span>
                  {activeCandidateData.run_folder && (
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-blue-950/40 border border-blue-600/30 text-blue-300 truncate max-w-[260px]" title={activeCandidateData.run_folder}>
                      📁 {activeCandidateData.run_folder}
                    </span>
                  )}
                  {activeCandidateData.no_max_days ? (
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-950/50 border border-amber-500/40 text-amber-300">
                      ⏱ Unlimited Days
                    </span>
                  ) : activeCandidateData.max_days ? (
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-zinc-900 border border-zinc-700 text-zinc-300">
                      ⏱ Max {activeCandidateData.max_days}d
                    </span>
                  ) : null}
                </div>
                <p className="text-xs text-[#8b95a6] mt-1.5">
                  {activeCandidateData.is_certified 
                    ? "Strategy satisfied the Monte Carlo prop-firm certification threshold (Combined Pass Rate ≥ 40% & Worst Max DD Breach ≤ 20%)." 
                    : "Strategy did not satisfy the minimum survival/pass rate criteria for prop firm deployment."}
                </p>
              </div>
            </div>

            {/* Quick KPIs in Banner */}
            <div className="flex items-center gap-6 bg-[#0b101d] px-5 py-2.5 rounded-xl border border-[#2d3748] text-center">
              <div>
                <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Combined Pass Rate</span>
                <span className={`text-xl font-bold font-mono ${
                  activeCandidateData.combined_pass_rate >= 40 ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  {activeCandidateData.combined_pass_rate}%
                </span>
              </div>
              <div className="h-8 w-px bg-[#2d3748]"></div>
              <div>
                <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Worst Max DD Breach</span>
                <span className={`text-xl font-bold font-mono ${
                  activeCandidateData.worst_breach_max_dd <= 20 ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  {activeCandidateData.worst_breach_max_dd}%
                </span>
              </div>
              <div className="h-8 w-px bg-[#2d3748]"></div>
              <div>
                <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Simulations</span>
                <span className="text-xl font-bold font-mono text-white">
                  {activeCandidateData.simulations?.toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Detailed Phase 1 & Phase 2 Breakdown Cards */}
      {activeCandidateData && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 animate-in fade-in">
          {/* Phase 1 Card */}
          <Card className="p-5 border border-[#2d3748]">
            <div className="flex items-center justify-between pb-3 mb-4 border-b border-[#2d3748]">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-400 font-mono border border-emerald-500/30">
                  PHASE 1
                </span>
                <h4 className="text-sm font-bold text-white">
                  {activeCandidateData.phase1.target_pct}% Profit Target
                </h4>
              </div>
              <span className="text-xs font-mono font-bold text-emerald-400">
                {activeCandidateData.phase1.pass_rate}% Pass Rate
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 text-xs font-mono">
              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Passes / Runs</span>
                <span className="text-white font-bold">
                  {activeCandidateData.phase1.pass_count?.toLocaleString()} / {activeCandidateData.simulations?.toLocaleString()}
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Max DD Breach</span>
                <span className={activeCandidateData.phase1.breach_max_rate > 10 ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>
                  {activeCandidateData.phase1.breach_max_rate}%
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Daily DD Breach</span>
                <span className={activeCandidateData.phase1.breach_daily_rate > 5 ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>
                  {activeCandidateData.phase1.breach_daily_rate}%
                </span>
              </div>

              {activeCandidateData.phase1.incomplete_rate !== undefined && activeCandidateData.phase1.incomplete_rate > 0 ? (
                <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                  <span className="text-[#8b95a6] text-[10px] block">Time Expired (&gt;{activeCandidateData.phase1.max_days || 250}d)</span>
                  <span className="text-amber-400 font-bold">
                    {activeCandidateData.phase1.incomplete_rate}% ({activeCandidateData.phase1.incomplete_count} runs)
                  </span>
                </div>
              ) : null}

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Median Days</span>
                <span className="text-amber-400 font-bold">
                  {activeCandidateData.phase1.median_days} days
                </span>
                <span className="text-[10px] text-[#64748b] block">
                  P10: {activeCandidateData.phase1.p10_days}d | P90: {activeCandidateData.phase1.p90_days}d
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Median Max DD</span>
                <span className="text-white font-bold">
                  {activeCandidateData.phase1.median_max_dd}%
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">P90 / P99 Max DD</span>
                <span className="text-white font-bold">
                  {activeCandidateData.phase1.p90_max_dd}% / {activeCandidateData.phase1.p99_max_dd}%
                </span>
              </div>
            </div>
          </Card>

          {/* Phase 2 Card */}
          <Card className="p-5 border border-[#2d3748]">
            <div className="flex items-center justify-between pb-3 mb-4 border-b border-[#2d3748]">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-xs font-bold bg-blue-500/20 text-blue-400 font-mono border border-blue-500/30">
                  PHASE 2
                </span>
                <h4 className="text-sm font-bold text-white">
                  {activeCandidateData.phase2.target_pct}% Profit Target
                </h4>
              </div>
              <span className="text-xs font-mono font-bold text-blue-400">
                {activeCandidateData.phase2.pass_rate}% Pass Rate
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 text-xs font-mono">
              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Passes / Runs</span>
                <span className="text-white font-bold">
                  {activeCandidateData.phase2.pass_count?.toLocaleString()} / {activeCandidateData.simulations?.toLocaleString()}
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Max DD Breach</span>
                <span className={activeCandidateData.phase2.breach_max_rate > 10 ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>
                  {activeCandidateData.phase2.breach_max_rate}%
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Daily DD Breach</span>
                <span className={activeCandidateData.phase2.breach_daily_rate > 5 ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>
                  {activeCandidateData.phase2.breach_daily_rate}%
                </span>
              </div>

              {activeCandidateData.phase2.incomplete_rate !== undefined && activeCandidateData.phase2.incomplete_rate > 0 ? (
                <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                  <span className="text-[#8b95a6] text-[10px] block">Time Expired (&gt;{activeCandidateData.phase2.max_days || 250}d)</span>
                  <span className="text-amber-400 font-bold">
                    {activeCandidateData.phase2.incomplete_rate}% ({activeCandidateData.phase2.incomplete_count} runs)
                  </span>
                </div>
              ) : null}

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Median Days</span>
                <span className="text-amber-400 font-bold">
                  {activeCandidateData.phase2.median_days} days
                </span>
                <span className="text-[10px] text-[#64748b] block">
                  P10: {activeCandidateData.phase2.p10_days}d | P90: {activeCandidateData.phase2.p90_days}d
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">Median Max DD</span>
                <span className="text-white font-bold">
                  {activeCandidateData.phase2.median_max_dd}%
                </span>
              </div>

              <div className="bg-[#111827] p-2.5 rounded-lg border border-[#2d3748]">
                <span className="text-[#8b95a6] text-[10px] block">P90 / P99 Max DD</span>
                <span className="text-white font-bold">
                  {activeCandidateData.phase2.p90_max_dd}% / {activeCandidateData.phase2.p99_max_dd}%
                </span>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Interactive Simulation Equity Curve Simulator (SVG) */}
      {activeCandidateData?.phase1?.sample_equity_curves && activeCandidateData.phase1.sample_equity_curves.length > 0 && (
        <Card className="p-5 border border-[#2d3748]">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="text-sm font-bold text-white flex items-center gap-2">
                <TrendingUp size={16} className="text-emerald-400" />
                Monte Carlo Sample Equity Trajectories (10 Iteration Paths)
              </h4>
              <p className="text-xs text-[#8b95a6]">
                Simulated equity curves resampled from {activeCandidateData.candidate}'s historical daily return distribution
              </p>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono">
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="w-3 h-0.5 bg-emerald-400 inline-block"></span> Phase 1 (+{phase1Target}%)
              </span>
              <span className="flex items-center gap-1.5 text-red-400">
                <span className="w-3 h-0.5 bg-red-400 inline-block"></span> Max DD (-{maxDrawdown}%)
              </span>
            </div>
          </div>

          <div className="h-64 w-full bg-[#050811] rounded-lg p-3 border border-[#1a2235] relative flex items-center justify-center">
            {/* SVG Plot */}
            <svg className="w-full h-full" viewBox="0 0 800 240" preserveAspectRatio="none">
              {/* Grid Lines */}
              <line x1="0" y1="40" x2="800" y2="40" stroke="#1f2937" strokeDasharray="3 3" />
              <line x1="0" y1="120" x2="800" y2="120" stroke="#374151" strokeWidth="1" />
              <line x1="0" y1="200" x2="800" y2="200" stroke="#1f2937" strokeDasharray="3 3" />

              {/* Target lines */}
              {/* Base balance: y = 120 */}
              {/* Target +8%: y = 50 */}
              <line x1="0" y1="50" x2="800" y2="50" stroke="#10b981" strokeWidth="1.5" strokeDasharray="4 4" opacity="0.8" />
              <text x="790" y="45" fill="#10b981" textAnchor="end" fontSize="10" fontFamily="monospace">
                +${((startingCapital * phase1Target) / 100).toFixed(0)} Target
              </text>

              {/* Drawdown limit -10%: y = 205 */}
              <line x1="0" y1="205" x2="800" y2="205" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="4 4" opacity="0.8" />
              <text x="790" y="220" fill="#ef4444" textAnchor="end" fontSize="10" fontFamily="monospace">
                -${((startingCapital * maxDrawdown) / 100).toFixed(0)} Max DD
              </text>

              {/* Base line */}
              <text x="10" y="115" fill="#8b95a6" fontSize="10" fontFamily="monospace">
                ${startingCapital.toLocaleString()} Deposit
              </text>

              {/* Sample Curves */}
              {activeCandidateData.phase1.sample_equity_curves.map((curve, cIdx) => {
                if (!curve || curve.length < 2) return null;
                const minVal = startingCapital * (1 - (maxDrawdown * 1.3) / 100);
                const maxVal = startingCapital * (1 + (phase1Target * 1.3) / 100);
                const range = maxVal - minVal;

                const points = curve.map((val, idx) => {
                  const x = (idx / (curve.length - 1)) * 800;
                  const norm = (val - minVal) / range;
                  const y = 230 - norm * 220;
                  return `${x.toFixed(1)},${y.toFixed(1)}`;
                }).join(' ');

                const colors = ['#f59e0b', '#3b82f6', '#10b981', '#ec4899', '#8b5cf6', '#06b6d4', '#84cc16', '#eab308', '#14b8a6', '#6366f1'];
                const strokeColor = colors[cIdx % colors.length];

                return (
                  <polyline
                    key={cIdx}
                    fill="none"
                    stroke={strokeColor}
                    strokeWidth="1.5"
                    strokeOpacity="0.85"
                    points={points}
                  />
                );
              })}
            </svg>
          </div>
        </Card>
      )}

      {/* Upgraded Terminal with Full Screen and Smooth Up/Down Scrolling */}
      <div className="flex-1 flex flex-col min-h-[420px]">
        <LogViewer 
          logs={logs} 
          title={`Candidate Monte Carlo Terminal ${isRunning ? '(Executing...)' : ''}`}
          isRunning={isRunning}
          onClear={clearLogs}
        />
      </div>
    </div>
  );
}
