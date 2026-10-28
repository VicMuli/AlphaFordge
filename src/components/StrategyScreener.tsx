import { useState, useEffect, useMemo } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { 
  Play, 
  Square, 
  Trash2, 
  RefreshCw, 
  TrendingUp, 
  CheckCircle2, 
  AlertCircle, 
  DollarSign, 
  BarChart3, 
  Plus, 
  Check, 
  Layers,
  ArrowUpDown,
  Percent,
  Clock,
  Settings2,
  Sliders,
  ToggleLeft,
  ToggleRight,
  Save,
  RotateCcw,
  Search,
  Shield,
  Target,
  Activity,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Filter,
  FileText,
  Download,
  ExternalLink,
  FolderOpen,
  Image,
  X
} from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

interface PairResult {
  symbol: string;
  resolved_symbol: string;
  status: 'Passed' | 'Profitable' | 'Unprofitable' | '0 Trades' | 'Running' | 'Pending' | 'Failed';
  net_profit: number;
  profit_pct: number;
  profit_factor: number;
  max_dd_pct: number;
  total_trades: number;
  win_rate: number;
  sharpe: number;
  error?: string;
  report_file?: string;
  files?: {
    report_html?: string;
    trades_csv?: string;
    equity_growth_chart?: string;
    profit_dollars_chart?: string;
    percent_gain_chart?: string;
    monthly_heatmap?: string;
    word_report?: string;
    summary_json?: string;
    set_file?: string;
  };
}

const DEFAULT_MAJORS = ['USDJPY', 'EURUSD', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD'];
const DEFAULT_CROSSES = ['EURJPY', 'GBPJPY', 'EURGBP', 'EURAUD', 'AUDJPY', 'CADJPY', 'CHFJPY'];
const DEFAULT_ASSETS = ['XAUUSD', 'BTCUSD', 'US30', 'NAS100'];

export default function StrategyScreener({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();

  const [eas, setEas] = useState<string[]>(['TRB', 'LRB V1.0', 'ORB', 'HA V1.0']);
  const [selectedEa, setSelectedEa] = useState<string>(config?.active_ea || 'TRB');
  const [period, setPeriod] = useState<string>(config?.period || 'M15');
  const [fromDate, setFromDate] = useState<string>(config?.train_from || '2013.01.01');
  const [toDate, setToDate] = useState<string>(config?.holdout_to || '2026.07.03');
  const [deposit, setDeposit] = useState<string>(config?.deposit || '2500');
  const [setFile, setSetFile] = useState<string>('');

  // Selected symbols checklist
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([
    'USDJPY', 'EURUSD', 'EURJPY', 'GBPUSD', 'XAUUSD', 'AUDUSD'
  ]);
  const [customSymbolInput, setCustomSymbolInput] = useState<string>('');

  // Screener results & sorting
  const [results, setResults] = useState<PairResult[]>([]);
  const [sortField, setSortField] = useState<keyof PairResult>('net_profit');
  const [sortAsc, setSortAsc] = useState<boolean>(false);
  const [loadingResults, setLoadingResults] = useState<boolean>(false);

  // Artifacts Modal & markets_screened viewer
  const [selectedArtifactPair, setSelectedArtifactPair] = useState<PairResult | null>(null);
  const [activeChartTab, setActiveChartTab] = useState<'equity' | 'heatmap' | 'profit' | 'gain'>('equity');
  const [showMarketsDrawer, setShowMarketsDrawer] = useState<boolean>(false);
  const [marketsData, setMarketsData] = useState<any[]>([]);
  const [loadingMarkets, setLoadingMarkets] = useState<boolean>(false);

  const fetchMarketsScreened = async () => {
    setLoadingMarkets(true);
    try {
      const res = await fetch('/api/markets-screened');
      if (res.ok) {
        const data = await res.json();
        setMarketsData(data.pairs || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMarkets(false);
    }
  };

  // Fetch available EAs
  useEffect(() => {
    fetch('/api/workspace')
      .then(res => res.json())
      .then(data => {
        if (data.availableEas && data.availableEas.length > 0) {
          setEas(data.availableEas);
          if (!selectedEa || !data.availableEas.includes(selectedEa)) {
            setSelectedEa(data.availableEas[0]);
          }
        }
      })
      .catch(console.error);
  }, []);

  // Fetch cached screener results for the active EA
  const fetchScreenerResults = async (eaName: string) => {
    setLoadingResults(true);
    try {
      const res = await fetch(`/api/screener-results?ea=${encodeURIComponent(eaName)}`);
      if (res.ok) {
        const data = await res.json();
        if (data.results && Array.isArray(data.results)) {
          setResults(data.results);
        } else {
          setResults([]);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingResults(false);
    }
  };

  // Strategy Parameters & Indicators state
  const [showInputsEditor, setShowInputsEditor] = useState<boolean>(false);
  const [loadingInputs, setLoadingInputs] = useState<boolean>(false);
  const [savingInputs, setSavingInputs] = useState<boolean>(false);
  const [strategyIndicators, setStrategyIndicators] = useState<any[]>([]);
  const [strategyParams, setStrategyParams] = useState<any[]>([]);
  const [hasCustomInputs, setHasCustomInputs] = useState<boolean>(false);
  const [setFileExists, setSetFileExists] = useState<boolean>(false);
  const [paramSearch, setParamSearch] = useState<string>('');
  const [paramCategory, setParamCategory] = useState<string>('all');
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  const fetchStrategyInputs = async (eaName: string) => {
    setLoadingInputs(true);
    try {
      const res = await fetch(`/api/screener-strategy-inputs?ea=${encodeURIComponent(eaName)}`);
      if (res.ok) {
        const data = await res.json();
        setStrategyIndicators(data.indicators || []);
        setStrategyParams(data.params || []);
        setHasCustomInputs(!!data.hasCustomInputs);
        setSetFileExists(!!data.setFileExists);
      }
    } catch (err) {
      console.error('Failed to load strategy inputs:', err);
    } finally {
      setLoadingInputs(false);
    }
  };

  useEffect(() => {
    if (selectedEa) {
      fetchScreenerResults(selectedEa);
      fetchStrategyInputs(selectedEa);
    }
  }, [selectedEa]);

  const handleToggleIndicator = (toggleParam: string) => {
    setStrategyIndicators(prev => prev.map(ind => 
      ind.toggleParam === toggleParam ? { ...ind, enabled: !ind.enabled } : ind
    ));
  };

  const handleParamChange = (paramName: string, val: any) => {
    setStrategyParams(prev => prev.map(p => {
      if (p.name === paramName) {
        let parsedVal = val;
        if (p.type === 'int' || p.type === 'ulong' || p.type === 'long') {
          const num = parseInt(val, 10);
          parsedVal = isNaN(num) ? val : num;
        } else if (p.type === 'double' || p.type === 'float') {
          const num = parseFloat(val);
          parsedVal = isNaN(num) ? val : num;
        } else if (p.type === 'bool') {
          parsedVal = val === true || val === 'true' || val === 1;
        }
        return {
          ...p,
          currentValue: parsedVal,
          isModified: parsedVal !== p.fixedValue
        };
      }
      return p;
    }));
  };

  const handleSaveInputs = async () => {
    setSavingInputs(true);
    setSaveSuccessMsg(null);
    try {
      const paramDict: Record<string, any> = {};
      strategyParams.forEach(p => {
        paramDict[p.name] = p.currentValue !== undefined ? p.currentValue : p.fixedValue;
      });

      const res = await fetch('/api/screener-strategy-inputs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ea: selectedEa,
          indicators: strategyIndicators.map(i => ({
            toggleParam: i.toggleParam,
            enabled: !!i.enabled
          })),
          params: paramDict
        })
      });

      if (res.ok) {
        setHasCustomInputs(true);
        setSetFileExists(true);
        setSaveSuccessMsg('Parameters & indicator inputs saved to screener_inputs.set');
        setTimeout(() => setSaveSuccessMsg(null), 4000);
      }
    } catch (err: any) {
      console.error('Save error:', err);
      alert('Error saving strategy inputs: ' + err.message);
    } finally {
      setSavingInputs(false);
    }
  };

  const handleResetInputs = async () => {
    if (!confirm(`Reset all parameters and indicators for ${selectedEa} back to compiled MQL5 defaults?`)) {
      return;
    }
    setSavingInputs(true);
    try {
      await fetch('/api/screener-strategy-inputs/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ea: selectedEa })
      });
      await fetchStrategyInputs(selectedEa);
      setSaveSuccessMsg('Reset to strategy defaults');
      setTimeout(() => setSaveSuccessMsg(null), 3000);
    } catch (err: any) {
      console.error('Reset error:', err);
    } finally {
      setSavingInputs(false);
    }
  };

  // Toggle symbol selection
  const toggleSymbol = (sym: string) => {
    setSelectedSymbols(prev => 
      prev.includes(sym) ? prev.filter(s => s !== sym) : [...prev, sym]
    );
  };

  const selectAllMajors = () => {
    setSelectedSymbols(prev => Array.from(new Set([...prev, ...DEFAULT_MAJORS])));
  };

  const selectAllCrosses = () => {
    setSelectedSymbols(prev => Array.from(new Set([...prev, ...DEFAULT_CROSSES])));
  };

  const selectAll = () => {
    setSelectedSymbols(Array.from(new Set([...DEFAULT_MAJORS, ...DEFAULT_CROSSES, ...DEFAULT_ASSETS])));
  };

  const clearSelection = () => {
    setSelectedSymbols([]);
  };

  const addCustomSymbol = () => {
    const s = customSymbolInput.trim().toUpperCase();
    if (s && !selectedSymbols.includes(s)) {
      setSelectedSymbols(prev => [...prev, s]);
      setCustomSymbolInput('');
    }
  };

  // Date normalization helper
  const normalizeDate = (val: string, fallback: string, isEnd: boolean): string => {
    if (!val || !val.trim()) return fallback;
    let s = val.trim();
    for (const sep of [' to ', ' - ', ' -> ', '..']) {
      if (s.includes(sep)) {
        const parts = s.split(sep);
        s = isEnd ? parts[1].trim() : parts[0].trim();
        break;
      }
    }
    const mRange = s.match(/^(\d{4})\s*[-/]\s*(\d{4})$/);
    if (mRange) {
      s = isEnd ? mRange[2] : mRange[1];
    }
    if (/^\d{4}$/.test(s)) {
      return isEnd ? `${s}.12.31` : `${s}.01.01`;
    }
    const clean = s.replace(/[-/]/g, '.');
    const parts = clean.split('.');
    if (parts.length === 3) {
      const [p0, p1, p2] = parts.map(p => p.trim());
      if (p0.length === 4 && /^\d+$/.test(p1) && /^\d+$/.test(p2)) {
        return `${p0}.${p1.padStart(2, '0')}.${p2.padStart(2, '0')}`;
      }
    }
    return fallback;
  };

  // Launch multi-pair screener
  const handleRunScreener = () => {
    if (selectedSymbols.length === 0) {
      alert("Please select at least one symbol / pair to screen.");
      return;
    }

    let rawFrom = fromDate.trim() || '2013.01.01';
    let rawTo = toDate.trim() || '2026.07.03';

    for (const sep of [' to ', ' - ', ' -> ', '..']) {
      if (rawFrom.includes(sep)) {
        const parts = rawFrom.split(sep);
        rawFrom = parts[0].trim();
        rawTo = parts[1].trim();
        break;
      }
    }
    const mRange = rawFrom.match(/^(\d{4})\s*[-/]\s*(\d{4})$/);
    if (mRange) {
      rawFrom = mRange[1];
      rawTo = mRange[2];
    }

    const normFrom = normalizeDate(rawFrom, '2013.01.01', false);
    const normTo = normalizeDate(rawTo, '2026.07.03', true);

    setFromDate(normFrom);
    setToDate(normTo);

    const symbolsStr = selectedSymbols.join(',');

    // Initialize UI placeholder results
    const initialResults: PairResult[] = selectedSymbols.map(sym => ({
      symbol: sym,
      resolved_symbol: sym,
      status: 'Pending',
      net_profit: 0,
      profit_pct: 0,
      profit_factor: 0,
      max_dd_pct: 0,
      total_trades: 0,
      win_rate: 0,
      sharpe: 0,
    }));
    setResults(initialResults);

    const activeSetFile = setFile || ((hasCustomInputs || setFileExists) ? 'screener_inputs.set' : '');

    runScript('run_screener.py', {
      args: `--ea "${selectedEa}" --symbols "${symbolsStr}" --period "${period}" --from-date "${normFrom}" --to-date "${normTo}" --deposit ${deposit} ${activeSetFile ? `--set-file "${activeSetFile}"` : ''}`,
      envOverrides: {
        AF_ACTIVE_EA: selectedEa,
        AF_SYMBOLS: symbolsStr,
        AF_PERIOD: period,
        AF_BT_START: normFrom,
        AF_BT_END: normTo,
        AF_DEPOSIT: deposit,
        AF_SET_FILE: activeSetFile,
      },
      onDone: () => {
        fetchScreenerResults(selectedEa);
      }
    });
  };

  // Sorted results
  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      let vA = a[sortField];
      let vB = b[sortField];
      if (typeof vA === 'string') {
        return sortAsc 
          ? (vA as string).localeCompare(vB as string) 
          : (vB as string).localeCompare(vA as string);
      }
      return sortAsc ? (Number(vA) - Number(vB)) : (Number(vB) - Number(vA));
    });
  }, [results, sortField, sortAsc]);

  const handleSort = (field: keyof PairResult) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  // Summary statistics
  const summaryStats = useMemo(() => {
    const valid = results.filter(r => r.status !== 'Pending' && r.status !== 'Running');
    const profitable = valid.filter(r => r.net_profit > 0);
    const totalProfit = valid.reduce((acc, r) => acc + (r.net_profit || 0), 0);
    const avgPf = valid.length > 0 ? (valid.reduce((acc, r) => acc + (r.profit_factor || 0), 0) / valid.length) : 0;
    const best = [...valid].sort((a, b) => b.net_profit - a.net_profit)[0];

    return {
      totalScreened: valid.length,
      profitableCount: profitable.length,
      winRate: valid.length > 0 ? ((profitable.length / valid.length) * 100).toFixed(0) : '0',
      totalProfit,
      avgPf: avgPf.toFixed(2),
      bestSymbol: best ? `${best.symbol} ($${best.net_profit.toLocaleString()})` : 'None',
    };
  }, [results]);

  // Filtered parameters for strategy configuration
  const filteredParams = useMemo(() => {
    return strategyParams.filter(p => {
      const matchCat = paramCategory === 'all' || p.category === paramCategory;
      const matchQuery = !paramSearch.trim() || 
        p.name.toLowerCase().includes(paramSearch.toLowerCase()) || 
        (p.label && p.label.toLowerCase().includes(paramSearch.toLowerCase()));
      return matchCat && matchQuery;
    });
  }, [strategyParams, paramCategory, paramSearch]);

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="📊 Strategy Screener" 
        subtitle="Batch-screen and compare EA performance across multiple currency pairs & market symbols" 
      />

      {/* Top Configuration & Pair Selection Card */}
      <Card className="p-5 border border-[#2d3748] bg-[#161f30]">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-5 pb-4 border-b border-[#2d3748]">
          <div>
            <label className="text-[11px] font-semibold text-[#8b95a6] block mb-1.5 uppercase tracking-wider">
              Strategy / EA
            </label>
            <select
              value={selectedEa}
              onChange={e => setSelectedEa(e.target.value)}
              className="w-full bg-[#0f172a] border border-[#2d3748] text-amber-400 font-semibold rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-amber-400"
            >
              {eas.map(ea => (
                <option key={ea} value={ea}>{ea}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] font-semibold text-[#8b95a6] block mb-1.5 uppercase tracking-wider">
              Timeframe
            </label>
            <select
              value={period}
              onChange={e => setPeriod(e.target.value)}
              className="w-full bg-[#0f172a] border border-[#2d3748] text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-amber-400"
            >
              {['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1'].map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] font-semibold text-[#8b95a6] block mb-1.5 uppercase tracking-wider">
              From Date
            </label>
            <input
              type="text"
              value={fromDate}
              onChange={e => setFromDate(e.target.value)}
              placeholder="2013.01.01 (or 2013-2026)"
              className="w-full bg-[#0f172a] border border-[#2d3748] text-white font-mono rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-amber-400"
            />
          </div>

          <div>
            <label className="text-[11px] font-semibold text-[#8b95a6] block mb-1.5 uppercase tracking-wider">
              To Date
            </label>
            <input
              type="text"
              value={toDate}
              onChange={e => setToDate(e.target.value)}
              placeholder="2026.07.03"
              className="w-full bg-[#0f172a] border border-[#2d3748] text-white font-mono rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-amber-400"
            />
          </div>
        </div>

        {/* Strategy Parameters & Indicator Inputs Bar & Collapsible Drawer */}
        <div className="mb-5 bg-[#0f172a] border border-[#2d3748] rounded-xl p-4 shadow-inner">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                <Sliders className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white tracking-wide">
                    Strategy Parameters & Indicator Switchboard
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded font-mono font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    {selectedEa}
                  </span>
                  {setFileExists || hasCustomInputs ? (
                    <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      Customized (screener_inputs.set)
                    </span>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded font-medium bg-blue-500/10 text-blue-400 border border-blue-500/30 flex items-center gap-1">
                      <Sparkles className="w-3 h-3" />
                      Compiled MQL5 Defaults
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1 text-[11px] text-[#8b95a6]">
                  <span>
                    Active Filters: <strong className="text-emerald-400">{strategyIndicators.filter(i => i.enabled).length}/{strategyIndicators.length}</strong>
                  </span>
                  <span>•</span>
                  <span>
                    Parameters: <strong className="text-white">{strategyParams.length}</strong>
                    {strategyParams.filter(p => p.isModified).length > 0 && (
                      <span className="text-amber-400 ml-1 font-medium">({strategyParams.filter(p => p.isModified).length} modified)</span>
                    )}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {(hasCustomInputs || setFileExists) && (
                <button
                  onClick={handleResetInputs}
                  disabled={savingInputs}
                  className="px-2.5 py-1.5 text-[11px] font-medium bg-red-500/10 hover:bg-red-500/20 text-red-300 border border-red-500/30 rounded-lg flex items-center gap-1.5 transition-colors"
                  title="Reset to default compiled values"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset Defaults
                </button>
              )}
              <button
                onClick={() => setShowInputsEditor(!showInputsEditor)}
                className="px-3 py-1.5 text-xs font-semibold bg-[#1e293b] hover:bg-[#283548] text-amber-400 border border-amber-500/30 rounded-lg flex items-center gap-1.5 transition-all shadow-sm"
              >
                <Settings2 className="w-3.5 h-3.5" />
                {showInputsEditor ? 'Hide Parameter Editor' : 'Modify Parameters & Indicators'}
                {showInputsEditor ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {/* Expanded Configuration Drawer */}
          {showInputsEditor && (
            <div className="mt-4 pt-4 border-t border-[#232f46] space-y-5 animate-in fade-in duration-200">
              {/* Save message notification */}
              {saveSuccessMsg && (
                <div className="p-3 bg-emerald-500/15 border border-emerald-500/40 rounded-lg text-emerald-300 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>{saveSuccessMsg}</span>
                </div>
              )}

              {/* Indicator Filter Switchboard */}
              <div>
                <div className="flex items-center justify-between mb-2.5">
                  <span className="text-xs font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <Activity className="w-3.5 h-3.5 text-amber-400" />
                    Indicator Filter Switchboard
                  </span>
                  <div className="flex items-center gap-2 text-[11px]">
                    <button
                      onClick={() => setStrategyIndicators(prev => prev.map(i => ({ ...i, enabled: true })))}
                      className="text-cyan-400 hover:underline"
                    >
                      Enable All Filters
                    </button>
                    <span className="text-slate-600">|</span>
                    <button
                      onClick={() => setStrategyIndicators(prev => prev.map(i => ({ ...i, enabled: false })))}
                      className="text-slate-400 hover:underline"
                    >
                      Disable All Filters
                    </button>
                  </div>
                </div>

                {loadingInputs ? (
                  <div className="p-6 text-center text-xs text-[#8b95a6]">Loading strategy inputs from MQL5...</div>
                ) : strategyIndicators.length === 0 ? (
                  <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg text-xs text-[#8b95a6]">
                    No explicit indicator filter switches found in {selectedEa}.mq5 source code.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                    {strategyIndicators.map(ind => (
                      <div
                        key={ind.toggleParam || ind.id}
                        onClick={() => handleToggleIndicator(ind.toggleParam)}
                        className={`p-3 rounded-lg border cursor-pointer transition-all flex items-start justify-between gap-3 ${
                          ind.enabled
                            ? 'bg-emerald-950/20 border-emerald-500/40 text-white shadow-sm'
                            : 'bg-[#162032] border-[#232f46] text-slate-400 hover:border-slate-600'
                        }`}
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-white">
                              {ind.name || ind.toggleParam}
                            </span>
                          </div>
                          <div className="text-[10px] font-mono text-[#8b95a6]">
                            {ind.toggleParam}
                          </div>
                          {ind.paramNames && ind.paramNames.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {ind.paramNames.map((pName: string) => (
                                <span key={pName} className="text-[9px] px-1.5 py-0.2 bg-[#0f172a] text-cyan-300 rounded border border-cyan-800/40">
                                  {pName}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        <button
                          type="button"
                          className="mt-0.5 text-lg transition-transform active:scale-95"
                        >
                          {ind.enabled ? (
                            <ToggleRight className="w-6 h-6 text-emerald-400" />
                          ) : (
                            <ToggleLeft className="w-6 h-6 text-slate-600" />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Strategy Parameters Editor */}
              <div>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <span className="text-xs font-bold text-white flex items-center gap-2 uppercase tracking-wider">
                    <Target className="w-3.5 h-3.5 text-amber-400" />
                    Strategy & Execution Parameters ({filteredParams.length})
                  </span>

                  <div className="flex flex-wrap items-center gap-2">
                    {/* Category filter pills */}
                    <div className="flex items-center bg-[#162032] p-0.5 rounded-lg border border-[#232f46] text-[11px]">
                      {[
                        { id: 'all', label: 'All' },
                        { id: 'risk', label: 'Risk' },
                        { id: 'core', label: 'Core' },
                        { id: 'indicator', label: 'Indicators' },
                        { id: 'timing', label: 'Timing' },
                      ].map(cat => (
                        <button
                          key={cat.id}
                          onClick={() => setParamCategory(cat.id)}
                          className={`px-2.5 py-1 rounded-md transition-colors ${
                            paramCategory === cat.id
                              ? 'bg-amber-400 text-slate-950 font-bold'
                              : 'text-slate-400 hover:text-white'
                          }`}
                        >
                          {cat.label}
                        </button>
                      ))}
                    </div>

                    {/* Search box */}
                    <div className="relative">
                      <Search className="w-3 h-3 text-slate-500 absolute left-2.5 top-2.5" />
                      <input
                        type="text"
                        placeholder="Search params..."
                        value={paramSearch}
                        onChange={e => setParamSearch(e.target.value)}
                        className="bg-[#162032] border border-[#232f46] text-white text-xs pl-7 pr-2.5 py-1 rounded-lg focus:outline-none focus:border-amber-400 w-36"
                      />
                    </div>
                  </div>
                </div>

                {loadingInputs ? (
                  <div className="p-6 text-center text-xs text-[#8b95a6]">Loading parameters...</div>
                ) : filteredParams.length === 0 ? (
                  <div className="p-4 bg-[#162032] border border-[#232f46] rounded-lg text-xs text-[#8b95a6] text-center">
                    No parameters found matching the current search or category filter.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[380px] overflow-y-auto pr-1">
                    {filteredParams.map(p => {
                      const curVal = p.currentValue !== undefined ? p.currentValue : p.fixedValue;
                      const isNum = p.type === 'double' || p.type === 'float' || p.type === 'int' || p.type === 'ulong' || p.type === 'long';
                      const step = p.type === 'double' || p.type === 'float' ? '0.05' : '1';

                      return (
                        <div
                          key={p.name}
                          className={`p-3 rounded-lg border transition-all ${
                            p.isModified
                              ? 'bg-amber-950/15 border-amber-500/40'
                              : 'bg-[#162032] border-[#232f46]'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-1 mb-1.5">
                            <label className="text-xs font-semibold text-white truncate" title={p.label || p.name}>
                              {p.name}
                            </label>
                            <div className="flex items-center gap-1">
                              <span className="text-[9px] px-1 py-0.2 bg-[#0f172a] text-slate-400 rounded uppercase font-mono">
                                {p.type}
                              </span>
                              {p.isModified && (
                                <span className="text-[9px] px-1.5 py-0.2 bg-amber-500/20 text-amber-300 font-bold rounded">
                                  Edited
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="text-[10px] text-[#8b95a6] line-clamp-1 mb-2" title={p.description || p.label}>
                            {p.description || p.label || p.name}
                          </div>

                          <div className="flex items-center gap-2">
                            {typeof p.fixedValue === 'boolean' || p.type === 'bool' ? (
                              <select
                                value={String(curVal)}
                                onChange={e => handleParamChange(p.name, e.target.value === 'true')}
                                className="w-full bg-[#0f172a] border border-[#2d3748] text-white rounded px-2.5 py-1 text-xs focus:outline-none focus:border-amber-400"
                              >
                                <option value="true">True (Enabled)</option>
                                <option value="false">False (Disabled)</option>
                              </select>
                            ) : isNum ? (
                              <input
                                type="number"
                                step={step}
                                value={curVal !== undefined ? curVal : ''}
                                onChange={e => handleParamChange(p.name, e.target.value)}
                                className="w-full bg-[#0f172a] border border-[#2d3748] text-white font-mono rounded px-2.5 py-1 text-xs focus:outline-none focus:border-amber-400"
                              />
                            ) : (
                              <input
                                type="text"
                                value={curVal !== undefined ? curVal : ''}
                                onChange={e => handleParamChange(p.name, e.target.value)}
                                className="w-full bg-[#0f172a] border border-[#2d3748] text-white font-mono rounded px-2.5 py-1 text-xs focus:outline-none focus:border-amber-400"
                              />
                            )}

                            {p.isModified && (
                              <button
                                type="button"
                                onClick={() => handleParamChange(p.name, p.fixedValue)}
                                className="text-[10px] px-1.5 py-1 text-slate-400 hover:text-amber-400 rounded hover:bg-[#0f172a]"
                                title={`Revert to default: ${p.fixedValue}`}
                              >
                                <RotateCcw className="w-3 h-3" />
                              </button>
                            )}
                          </div>

                          <div className="mt-1.5 text-[10px] text-slate-500 font-mono flex items-center justify-between">
                            <span>Default: {String(p.fixedValue)}</span>
                            {p.range && (
                              <span>Range: [{p.range.start}..{p.range.stop}]</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Bottom Action Footer */}
              <div className="pt-3 border-t border-[#232f46] flex flex-wrap items-center justify-between gap-3">
                <div className="text-[11px] text-[#8b95a6] flex items-center gap-1.5">
                  <Shield className="w-3.5 h-3.5 text-amber-400" />
                  <span>
                    Saved inputs automatically compile into <code className="text-amber-300 font-mono">screener_inputs.set</code> and apply to all screened pairs.
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleResetInputs}
                    disabled={savingInputs}
                    className="px-3 py-1.5 text-xs text-slate-300 hover:text-white bg-[#1e293b] hover:bg-[#283548] border border-[#334155] rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Reset Defaults
                  </button>
                  <button
                    onClick={handleSaveInputs}
                    disabled={savingInputs}
                    className="px-4 py-1.5 text-xs font-bold text-slate-950 bg-amber-400 hover:bg-amber-300 rounded-lg transition-colors flex items-center gap-1.5 shadow-md"
                  >
                    {savingInputs ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Save className="w-3.5 h-3.5" />
                    )}
                    Save & Apply to Screener
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Pairs Selection Area */}
        <div className="space-y-3 mb-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold text-white flex items-center gap-2">
              <Layers size={15} className="text-amber-400" />
              Select Pairs to Screen ({selectedSymbols.length} Selected):
            </span>
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              <button
                onClick={selectAllMajors}
                className="px-2.5 py-1 bg-[#1e293b] hover:bg-[#334155] text-cyan-300 rounded border border-[#334155] transition-colors"
              >
                + Majors
              </button>
              <button
                onClick={selectAllCrosses}
                className="px-2.5 py-1 bg-[#1e293b] hover:bg-[#334155] text-cyan-300 rounded border border-[#334155] transition-colors"
              >
                + Crosses
              </button>
              <button
                onClick={selectAll}
                className="px-2.5 py-1 bg-[#1e293b] hover:bg-[#334155] text-amber-300 rounded border border-[#334155] transition-colors"
              >
                Select All
              </button>
              <button
                onClick={clearSelection}
                className="px-2.5 py-1 bg-[#1e293b] hover:bg-[#334155] text-red-300 rounded border border-[#334155] transition-colors"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Quick-toggle Badges */}
          <div className="flex flex-wrap gap-2 p-3 bg-[#0a0f1d] border border-[#2d3748] rounded-lg max-h-36 overflow-y-auto">
            {Array.from(new Set([...DEFAULT_MAJORS, ...DEFAULT_CROSSES, ...DEFAULT_ASSETS, ...selectedSymbols])).map(sym => {
              const isSelected = selectedSymbols.includes(sym);
              return (
                <button
                  key={sym}
                  onClick={() => toggleSymbol(sym)}
                  className={`px-3 py-1.5 rounded-md text-xs font-mono font-medium transition-all flex items-center gap-1.5 ${
                    isSelected
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-xs'
                      : 'bg-[#161f30] text-gray-400 border border-[#2d3748] hover:text-white hover:border-gray-500'
                  }`}
                >
                  {isSelected && <Check size={12} className="text-amber-400" />}
                  {sym}
                </button>
              );
            })}
          </div>

          {/* Custom Symbol Adder */}
          <div className="flex items-center gap-2 max-w-sm">
            <input
              type="text"
              value={customSymbolInput}
              onChange={e => setCustomSymbolInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addCustomSymbol()}
              placeholder="Add pair (e.g. AUDCAD, US500, ETHUSD)"
              className="flex-1 bg-[#0f172a] border border-[#2d3748] text-white px-3 py-1.5 text-xs rounded focus:outline-none focus:border-amber-400"
            />
            <Button variant="secondary" onClick={addCustomSymbol} className="text-xs py-1.5 px-3">
              <Plus size={13} /> Add Pair
            </Button>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-[#2d3748]">
          <div className="flex items-center gap-3">
            {isRunning ? (
              <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
                <Square size={16} /> Stop Screener
              </Button>
            ) : (
              <Button onClick={handleRunScreener}>
                <Play size={16} /> Run Strategy Screener ({selectedSymbols.length} Pairs)
              </Button>
            )}
            <Button variant="secondary" onClick={() => fetchScreenerResults(selectedEa)} disabled={loadingResults}>
              <RefreshCw size={14} className={loadingResults ? "animate-spin" : ""} /> Refresh Results
            </Button>
            <Button variant="secondary" onClick={() => { setShowMarketsDrawer(true); fetchMarketsScreened(); }}>
              <FolderOpen size={14} className="text-amber-400" /> markets_screened
            </Button>
            <Button variant="secondary" onClick={clearLogs}>
              <Trash2 size={14} /> Clear Log
            </Button>
          </div>

          <div className="text-xs text-[#8b95a6] font-mono">
            Deposit: <span className="text-amber-300">${Number(deposit).toLocaleString()}</span> | Range: <span className="text-gray-200">{fromDate} → {toDate}</span>
          </div>
        </div>
      </Card>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3.5 bg-[#161f30] border border-[#2d3748] rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] text-[#8b95a6] font-semibold uppercase">Pairs Screened</div>
            <div className="text-xl font-bold text-white mt-0.5">{summaryStats.totalScreened}</div>
          </div>
          <BarChart3 className="text-cyan-400" size={24} />
        </div>

        <div className="p-3.5 bg-[#161f30] border border-[#2d3748] rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] text-[#8b95a6] font-semibold uppercase">Profitable Pairs</div>
            <div className="text-xl font-bold text-emerald-400 mt-0.5">
              {summaryStats.profitableCount} <span className="text-xs font-normal text-gray-400">({summaryStats.winRate}%)</span>
            </div>
          </div>
          <CheckCircle2 className="text-emerald-400" size={24} />
        </div>

        <div className="p-3.5 bg-[#161f30] border border-[#2d3748] rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] text-[#8b95a6] font-semibold uppercase">Avg Profit Factor</div>
            <div className="text-xl font-bold text-amber-400 mt-0.5">{summaryStats.avgPf}</div>
          </div>
          <TrendingUp className="text-amber-400" size={24} />
        </div>

        <div className="p-3.5 bg-[#161f30] border border-[#2d3748] rounded-xl flex items-center justify-between">
          <div>
            <div className="text-[11px] text-[#8b95a6] font-semibold uppercase">Top Performing Pair</div>
            <div className="text-sm font-bold text-cyan-300 mt-0.5 truncate max-w-[150px]">{summaryStats.bestSymbol}</div>
          </div>
          <DollarSign className="text-emerald-400" size={24} />
        </div>
      </div>

      {/* Screener Leaderboard Table */}
      <Card className="p-0 border border-[#2d3748] overflow-hidden bg-[#161f30]">
        <div className="px-5 py-3 border-b border-[#2d3748] flex items-center justify-between bg-[#0f172a]">
          <div className="font-semibold text-white text-xs flex items-center gap-2">
            <BarChart3 size={15} className="text-amber-400" />
            Screener Leaderboard — {selectedEa}
          </div>
          <div className="text-[11px] text-[#8b95a6]">
            Showing {sortedResults.length} Pairs
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#0b101d] text-[#8b95a6] uppercase text-[10px] tracking-wider border-b border-[#2d3748]">
              <tr>
                <th className="py-2.5 px-4 cursor-pointer hover:text-white" onClick={() => handleSort('symbol')}>
                  <div className="flex items-center gap-1">Symbol <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 cursor-pointer hover:text-white" onClick={() => handleSort('status')}>
                  <div className="flex items-center gap-1">Status <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('net_profit')}>
                  <div className="flex items-center justify-end gap-1">Net Profit ($) <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('profit_pct')}>
                  <div className="flex items-center justify-end gap-1">Return % <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('profit_factor')}>
                  <div className="flex items-center justify-end gap-1">Profit Factor <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('max_dd_pct')}>
                  <div className="flex items-center justify-end gap-1">Max DD % <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('total_trades')}>
                  <div className="flex items-center justify-end gap-1">Trades <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('win_rate')}>
                  <div className="flex items-center justify-end gap-1">Win Rate <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-right cursor-pointer hover:text-white" onClick={() => handleSort('sharpe')}>
                  <div className="flex items-center justify-end gap-1">Sharpe <ArrowUpDown size={11} /></div>
                </th>
                <th className="py-2.5 px-3 text-center">
                  Artifacts
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#243048]">
              {sortedResults.length > 0 ? (
                sortedResults.map((r, idx) => {
                  const isProfitable = r.net_profit > 0;
                  const isZeroTrades = r.status === '0 Trades' || r.total_trades === 0;
                  const isFailed = r.status === 'Failed';
                  const isRunningItem = r.status === 'Running';

                  return (
                    <tr key={r.symbol || idx} className="hover:bg-[#1a2540]/60 transition-colors">
                      <td className="py-3 px-4 font-mono font-bold text-white">
                        <div className="flex items-center gap-2">
                          <span>{r.symbol}</span>
                          {r.resolved_symbol && r.resolved_symbol !== r.symbol && (
                            <span className="text-[10px] font-normal text-cyan-400 bg-cyan-950/60 border border-cyan-800/40 px-1.5 py-0.2 rounded">
                              {r.resolved_symbol}
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="py-3 px-3">
                        {isRunningItem ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-900/60 text-blue-300 border border-blue-500/40 animate-pulse">
                            Running
                          </span>
                        ) : isFailed ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-red-900/60 text-red-300 border border-red-500/40" title={r.error}>
                            Failed
                          </span>
                        ) : isZeroTrades ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-900/50 text-amber-300 border border-amber-600/40">
                            0 Trades
                          </span>
                        ) : isProfitable ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-500/40">
                            Profitable
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950/60 text-rose-300 border border-rose-800/40">
                            Unprofitable
                          </span>
                        )}
                      </td>

                      <td className={`py-3 px-3 text-right font-mono font-semibold ${isProfitable ? 'text-emerald-400' : (r.net_profit < 0 ? 'text-rose-400' : 'text-gray-400')}`}>
                        ${r.net_profit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>

                      <td className={`py-3 px-3 text-right font-mono ${isProfitable ? 'text-emerald-400' : (r.profit_pct < 0 ? 'text-rose-400' : 'text-gray-400')}`}>
                        {r.profit_pct.toFixed(1)}%
                      </td>

                      <td className="py-3 px-3 text-right font-mono text-gray-200">
                        {r.profit_factor > 0 ? r.profit_factor.toFixed(2) : '-'}
                      </td>

                      <td className="py-3 px-3 text-right font-mono text-amber-400">
                        {r.max_dd_pct > 0 ? `${r.max_dd_pct.toFixed(1)}%` : '-'}
                      </td>

                      <td className="py-3 px-3 text-right font-mono text-gray-200">
                        {r.total_trades}
                      </td>

                      <td className="py-3 px-3 text-right font-mono text-cyan-300">
                        {r.win_rate > 0 ? `${r.win_rate.toFixed(1)}%` : '-'}
                      </td>

                      <td className="py-3 px-3 text-right font-mono text-gray-300">
                        {r.sharpe > 0 ? r.sharpe.toFixed(2) : '-'}
                      </td>

                      <td className="py-3 px-3 text-center">
                        <button
                          onClick={() => {
                            setSelectedArtifactPair(r);
                            setActiveChartTab('equity');
                          }}
                          className="px-2.5 py-1 text-[11px] font-semibold bg-[#1e293b] hover:bg-[#283548] text-amber-300 hover:text-amber-200 border border-amber-500/30 rounded-md transition-colors inline-flex items-center gap-1.5 shadow-xs"
                        >
                          <FolderOpen size={12} className="text-amber-400" /> Artifacts
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-gray-400 text-xs">
                    No pairs screened yet. Select pairs above and click <span className="text-amber-400 font-semibold">"Run Strategy Screener"</span> to test your strategy across markets.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Terminal Output */}
      <div className="flex-1 min-h-[260px] flex flex-col">
        <LogViewer logs={logs} title={`Screener Live Execution Log ${isRunning ? '(Active Batch Test)' : ''}`} />
      </div>

      {/* ── ARTIFACTS MODAL ─────────────────────────────────────────────────── */}
      {selectedArtifactPair && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs">
          <div className="bg-[#121927] border border-[#2d3748] rounded-xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-[#243048] flex items-center justify-between bg-[#0e1422]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400">
                  <BarChart3 size={20} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    {selectedArtifactPair.symbol} — {selectedEa} Backtest Artifacts
                    <span className="text-xs font-mono font-normal px-2 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                      {selectedArtifactPair.status}
                    </span>
                  </h3>
                  <div className="text-xs text-[#8b95a6] font-mono mt-0.5">
                    Storage: <span className="text-cyan-300">markets_screened/{selectedArtifactPair.symbol}/{selectedEa}/</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedArtifactPair(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#1a2540] transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {/* Performance Metrics Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
                <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg">
                  <div className="text-[10px] uppercase font-semibold text-[#8b95a6]">Net Profit</div>
                  <div className={`text-base font-bold font-mono mt-0.5 ${selectedArtifactPair.net_profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    ${selectedArtifactPair.net_profit.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>

                <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg">
                  <div className="text-[10px] uppercase font-semibold text-[#8b95a6]">Return %</div>
                  <div className={`text-base font-bold font-mono mt-0.5 ${selectedArtifactPair.profit_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {selectedArtifactPair.profit_pct.toFixed(1)}%
                  </div>
                </div>

                <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg">
                  <div className="text-[10px] uppercase font-semibold text-[#8b95a6]">Profit Factor</div>
                  <div className="text-base font-bold font-mono mt-0.5 text-white">
                    {selectedArtifactPair.profit_factor > 0 ? selectedArtifactPair.profit_factor.toFixed(2) : '-'}
                  </div>
                </div>

                <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg">
                  <div className="text-[10px] uppercase font-semibold text-[#8b95a6]">Max Drawdown</div>
                  <div className="text-base font-bold font-mono mt-0.5 text-amber-400">
                    {selectedArtifactPair.max_dd_pct > 0 ? `${selectedArtifactPair.max_dd_pct.toFixed(1)}%` : '-'}
                  </div>
                </div>

                <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg">
                  <div className="text-[10px] uppercase font-semibold text-[#8b95a6]">Total Trades</div>
                  <div className="text-base font-bold font-mono mt-0.5 text-white">
                    {selectedArtifactPair.total_trades}
                  </div>
                </div>

                <div className="p-3 bg-[#162032] border border-[#232f46] rounded-lg">
                  <div className="text-[10px] uppercase font-semibold text-[#8b95a6]">Win Rate</div>
                  <div className="text-base font-bold font-mono mt-0.5 text-cyan-300">
                    {selectedArtifactPair.win_rate > 0 ? `${selectedArtifactPair.win_rate.toFixed(1)}%` : '-'}
                  </div>
                </div>
              </div>

              {/* Artifact Document & Data Download Action Bar */}
              <div className="p-4 bg-[#0d1424] border border-[#232f46] rounded-xl flex flex-wrap items-center justify-between gap-3">
                <div className="text-xs font-semibold text-white flex items-center gap-2">
                  <FileText className="text-amber-400" size={15} />
                  <span>Download Research Artifacts:</span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/${selectedEa}_${selectedArtifactPair.symbol}_Research_Report.docx`)}`}
                    download
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-950/70 text-blue-300 border border-blue-600/40 hover:bg-blue-900/60 transition-colors shadow-xs"
                  >
                    <FileText size={13} />
                    <span>Word Report (.docx)</span>
                    <Download size={11} className="opacity-70 ml-0.5" />
                  </a>

                  <a
                    href={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/trades.csv`)}`}
                    download
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-950/70 text-emerald-300 border border-emerald-600/40 hover:bg-emerald-900/60 transition-colors shadow-xs"
                  >
                    <BarChart3 size={13} />
                    <span>Trades CSV</span>
                    <Download size={11} className="opacity-70 ml-0.5" />
                  </a>

                  <a
                    href={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/report.html`)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-cyan-950/70 text-cyan-300 border border-cyan-600/40 hover:bg-cyan-900/60 transition-colors shadow-xs"
                  >
                    <ExternalLink size={13} />
                    <span>MT5 HTML Report</span>
                  </a>

                  <a
                    href={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/screener_inputs.set`)}`}
                    download
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-950/70 text-amber-300 border border-amber-600/40 hover:bg-amber-900/60 transition-colors shadow-xs"
                  >
                    <Sliders size={13} />
                    <span>Inputs (.set)</span>
                    <Download size={11} className="opacity-70 ml-0.5" />
                  </a>
                </div>
              </div>

              {/* Chart Previews Tabs */}
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#232f46] pb-2">
                  <div className="flex items-center gap-2 text-xs font-semibold text-white">
                    <Image size={15} className="text-cyan-400" />
                    <span>Visual Analytics & Growth Curves:</span>
                  </div>

                  <div className="flex gap-1">
                    <button
                      onClick={() => setActiveChartTab('equity')}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${activeChartTab === 'equity' ? 'bg-amber-400 text-slate-950 font-bold' : 'bg-[#1a2540] text-slate-300 hover:text-white'}`}
                    >
                      📈 Equity Growth
                    </button>
                    <button
                      onClick={() => setActiveChartTab('heatmap')}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${activeChartTab === 'heatmap' ? 'bg-amber-400 text-slate-950 font-bold' : 'bg-[#1a2540] text-slate-300 hover:text-white'}`}
                    >
                      🗓️ Monthly Heatmap
                    </button>
                    <button
                      onClick={() => setActiveChartTab('profit')}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${activeChartTab === 'profit' ? 'bg-amber-400 text-slate-950 font-bold' : 'bg-[#1a2540] text-slate-300 hover:text-white'}`}
                    >
                      💵 Profit ($)
                    </button>
                    <button
                      onClick={() => setActiveChartTab('gain')}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${activeChartTab === 'gain' ? 'bg-amber-400 text-slate-950 font-bold' : 'bg-[#1a2540] text-slate-300 hover:text-white'}`}
                    >
                      📊 Return (%)
                    </button>
                  </div>
                </div>

                <div className="p-3 bg-[#0a0f1d] border border-[#232f46] rounded-xl flex items-center justify-center min-h-[380px]">
                  {activeChartTab === 'equity' && (
                    <img
                      src={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/chart_equity_growth.png`)}`}
                      alt="Equity Growth Chart"
                      className="max-h-[360px] w-auto object-contain rounded border border-[#232f46]"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                        const el = (e.target as HTMLElement).nextElementSibling;
                        if (el) (el as HTMLElement).style.display = 'flex';
                      }}
                    />
                  )}
                  {activeChartTab === 'heatmap' && (
                    <img
                      src={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/monthly_heatmap.png`)}`}
                      alt="Monthly Performance Heatmap"
                      className="max-h-[360px] w-auto object-contain rounded border border-[#232f46]"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                        const el = (e.target as HTMLElement).nextElementSibling;
                        if (el) (el as HTMLElement).style.display = 'flex';
                      }}
                    />
                  )}
                  {activeChartTab === 'profit' && (
                    <img
                      src={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/chart_profit_dollars.png`)}`}
                      alt="Profit Dollars Chart"
                      className="max-h-[360px] w-auto object-contain rounded border border-[#232f46]"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                        const el = (e.target as HTMLElement).nextElementSibling;
                        if (el) (el as HTMLElement).style.display = 'flex';
                      }}
                    />
                  )}
                  {activeChartTab === 'gain' && (
                    <img
                      src={`/api/markets-screened-file?path=${encodeURIComponent(`markets_screened/${selectedArtifactPair.symbol}/${selectedEa}/chart_percent_gain.png`)}`}
                      alt="Percent Gain Chart"
                      className="max-h-[360px] w-auto object-contain rounded border border-[#232f46]"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                        const el = (e.target as HTMLElement).nextElementSibling;
                        if (el) (el as HTMLElement).style.display = 'flex';
                      }}
                    />
                  )}
                  <div style={{ display: 'none' }} className="flex-col items-center justify-center p-8 text-center text-[#8b95a6] space-y-2">
                    <Activity size={32} className="text-amber-400/60" />
                    <p className="text-xs">Chart not available or generating in progress.</p>
                    <p className="text-[11px] text-slate-500 font-mono">Run screener on this pair to produce equity curve and heatmap artifacts.</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-[#243048] flex justify-end bg-[#0e1422]">
              <button
                onClick={() => setSelectedArtifactPair(null)}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-[#1e293b] hover:bg-[#283548] border border-[#334155] rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MARKETS_SCREENED REPOSITORY DRAWER ──────────────────────────────── */}
      {showMarketsDrawer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs">
          <div className="bg-[#121927] border border-[#2d3748] rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-[#243048] flex items-center justify-between bg-[#0e1422]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400">
                  <FolderOpen size={20} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">
                    AlphaForge markets_screened Repository
                  </h3>
                  <div className="text-xs text-[#8b95a6]">
                    Hierarchical structure: <code className="text-amber-300 font-mono">markets_screened/&lt;PAIR&gt;/&lt;STRATEGY&gt;/</code>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={fetchMarketsScreened}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#1a2540] transition-colors"
                  title="Refresh"
                >
                  <RefreshCw size={16} className={loadingMarkets ? "animate-spin" : ""} />
                </button>
                <button
                  onClick={() => setShowMarketsDrawer(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#1a2540] transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              {marketsData.length === 0 ? (
                <div className="p-12 text-center text-[#8b95a6] space-y-3">
                  <FolderOpen size={36} className="mx-auto text-slate-600" />
                  <p className="text-sm font-medium">No screened markets found in markets_screened/</p>
                  <p className="text-xs text-slate-500">
                    Run the Strategy Screener on pairs like EURJPY, USDJPY, EURUSD to populate backtest folders.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {marketsData.map((pairItem) => (
                    <div key={pairItem.symbol} className="p-4 bg-[#162032] border border-[#232f46] rounded-xl space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-base font-bold text-white">{pairItem.symbol}</span>
                          <span className="text-xs text-[#8b95a6]">({pairItem.strategies?.length || 0} strategies screened)</span>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {pairItem.strategies?.map((strat: any) => (
                          <div key={strat.strategy} className="p-3 bg-[#0f172a] border border-[#283548] rounded-lg flex items-center justify-between">
                            <div>
                              <div className="text-xs font-bold text-amber-300 font-mono">{strat.strategy}</div>
                              <div className="text-[11px] text-slate-400 mt-0.5">{strat.filesCount} artifact files</div>
                            </div>

                            <button
                              onClick={() => {
                                setShowMarketsDrawer(false);
                                setSelectedArtifactPair({
                                  symbol: pairItem.symbol,
                                  resolved_symbol: pairItem.symbol,
                                  status: 'Completed',
                                  net_profit: strat.summary?.net_profit || 0,
                                  profit_pct: strat.summary?.profit_pct || 0,
                                  profit_factor: strat.summary?.profit_factor || 0,
                                  max_dd_pct: strat.summary?.max_dd_pct || 0,
                                  total_trades: strat.summary?.total_trades || 0,
                                  win_rate: strat.summary?.win_rate || 0,
                                  sharpe: strat.summary?.sharpe || 0,
                                });
                              }}
                              className="px-2.5 py-1 text-xs font-semibold bg-[#1e293b] hover:bg-[#283548] text-amber-300 border border-amber-500/30 rounded transition-colors"
                            >
                              View
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-[#243048] flex justify-end bg-[#0e1422]">
              <button
                onClick={() => setShowMarketsDrawer(false)}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-[#1e293b] hover:bg-[#283548] border border-[#334155] rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
