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
  Clock
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

  useEffect(() => {
    if (selectedEa) {
      fetchScreenerResults(selectedEa);
    }
  }, [selectedEa]);

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

    runScript('run_screener.py', {
      args: `--ea "${selectedEa}" --symbols "${symbolsStr}" --period "${period}" --from-date "${normFrom}" --to-date "${normTo}" --deposit ${deposit} ${setFile ? `--set-file "${setFile}"` : ''}`,
      envOverrides: {
        AF_ACTIVE_EA: selectedEa,
        AF_SYMBOLS: symbolsStr,
        AF_PERIOD: period,
        AF_BT_START: normFrom,
        AF_BT_END: normTo,
        AF_DEPOSIT: deposit,
        AF_SET_FILE: setFile,
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
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-gray-400 text-xs">
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
    </div>
  );
}
