import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, RefreshCw, Square, Trash2, X } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function FullBacktest({ config }: { config: any }) {
  const MARKETS = ['USDJPY', 'EURJPY', 'EURUSD', 'GBPUSD', 'XAUUSD'];
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>('');
  const [candidates, setCandidates] = useState<string[]>([]);
  const [selectedCand, setSelectedCand] = useState<string>('');
  const [eas, setEas] = useState<string[]>(['TRB', 'ORB']);
  const [selectedEa, setSelectedEa] = useState<string>(config?.active_ea || 'TRB');
  const [setFiles, setSetFiles] = useState<string[]>([]);
  const [selectedSetFile, setSelectedSetFile] = useState<string>('');
  const [selectedMarket, setSelectedMarket] = useState<string>(config.symbol || 'USDJPY');
  const [fromDate, setFromDate] = useState<string>(config.train_from || '2013.01.01');
  const [toDate, setToDate] = useState<string>(config.holdout_to || '2026.07.03');
  const [deposit, setDeposit] = useState<string>(config.deposit || '2500');
  const [lotSize, setLotSize] = useState<string>('');
  const [riskPct, setRiskPct] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [showOutputModal, setShowOutputModal] = useState(false);

  const normalizeMt5Date = (val: string, fallback: string, isEnd: boolean): string => {
    if (!val || !val.trim()) return fallback;
    let s = val.trim();
    for (const sep of [' to ', ' - ', ' -> ', '..']) {
      if (s.includes(sep)) {
        const parts = s.split(sep);
        s = isEnd ? parts[1].trim() : parts[0].trim();
        break;
      }
    }
    const rangeMatch = s.match(/^(\d{4})\s*[-/]\s*(\d{4})$/);
    if (rangeMatch) {
      s = isEnd ? rangeMatch[2] : rangeMatch[1];
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

  const fetchSetFiles = async (run: string, candidate: string) => {
    if (!candidate) {
      setSetFiles([]);
      setSelectedSetFile('');
      return;
    }
    try {
      const res = await fetch(`/api/candidate-set-files?run=${encodeURIComponent(run)}&candidate=${encodeURIComponent(candidate)}`);
      if (res.ok) {
        const data = await res.json();
        const files: string[] = data.setFiles || [];
        setSetFiles(files);
        if (files.length > 0) {
          setSelectedSetFile(files[0]);
        } else {
          const num = candidate.replace('cand_', '');
          setSelectedSetFile(`c${num}_full.set`);
        }
      }
    } catch (e) {
      console.error('Error fetching set files:', e);
    }
  };

  const fetchLists = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/workspace');
      if (res.ok) {
        const data = await res.json();
        const runList = data.runsDetailed || [];
        setRuns(runList);
        if (data.availableEas && data.availableEas.length > 0) {
          setEas(data.availableEas);
          if (!selectedEa || !data.availableEas.includes(selectedEa)) {
            setSelectedEa(data.availableEas[0]);
          }
        }
        if (runList.length > 0) {
          const first = runList[0];
          setSelectedRun(first.name);
          setCandidates(first.candidates || []);
          if (first.candidates && first.candidates.length > 0) {
            const firstCand = first.candidates[0];
            setSelectedCand(firstCand);
            fetchSetFiles(first.name, firstCand);
          } else {
            setSelectedCand('');
            setSetFiles([]);
            setSelectedSetFile('');
          }
          if (first.meta) {
            if (first.meta.ea) {
              setEas(prev => prev.includes(first.meta.ea) ? prev : [first.meta.ea, ...prev]);
              setSelectedEa(first.meta.ea);
            }
            const detectedSym = first.meta.symbol_key || first.meta.symbol;
            if (detectedSym) {
              const symKey = detectedSym.split(' ')[0].toUpperCase();
              setSelectedMarket(symKey);
            }
            if (first.meta.train_from) setFromDate(first.meta.train_from);
            if (first.meta.holdout_to) setToDate(first.meta.holdout_to);
          }
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLists();
  }, []);

  useEffect(() => {
    if (config) {
      if (config.train_from) setFromDate(config.train_from);
      if (config.holdout_to) setToDate(config.holdout_to);
      if (config.deposit) setDeposit(config.deposit);
      if (config.active_ea && !selectedEa) setSelectedEa(config.active_ea);
    }
  }, [config]);

  const handleRunChange = (runName: string) => {
    setSelectedRun(runName);
    const found = runs.find(r => r.name === runName);
    const cands = found ? found.candidates : [];
    setCandidates(cands || []);
    if (cands && cands.length > 0) {
      const cand = cands[0];
      setSelectedCand(cand);
      fetchSetFiles(runName, cand);
    } else {
      setSelectedCand('');
      setSetFiles([]);
      setSelectedSetFile('');
    }

    // Auto-detect EA, symbol, and date range from run metadata (matching app.py exactly)
    if (found?.meta) {
      if (found.meta.ea) {
        setEas(prev => prev.includes(found.meta.ea) ? prev : [found.meta.ea, ...prev]);
        setSelectedEa(found.meta.ea);
      }
      const detectedSym = found.meta.symbol_key || found.meta.symbol;
      if (detectedSym) {
        const symKey = detectedSym.split(' ')[0].toUpperCase();
        setSelectedMarket(symKey);
      }
      if (found.meta.train_from) {
        setFromDate(found.meta.train_from);
      }
      if (found.meta.holdout_to) {
        setToDate(found.meta.holdout_to);
      }
    }
  };

  const handleCandChange = (cand: string) => {
    setSelectedCand(cand);
    fetchSetFiles(selectedRun, cand);
  };

  const resolveMarketSymbol = (market: string): string => {
    const map: Record<string, string> = {
      'EURUSD': 'EURUSD dukascopy',
      'GBPUSD': 'GBPUSD dukascopy',
      'USDJPY': 'USDJPY Dukascopy',
      'EURJPY': 'EURJPY Dukascopy',
      'XAUUSD': 'XAUUSD dukascopy',
    };
    const m = (market || 'USDJPY').trim();
    if (m.toLowerCase().includes('dukascopy')) return m;
    const key = m.split(' ')[0].toUpperCase();
    return map[key] || m;
  };

  const handleRun = () => {
    let rawFrom = (fromDate || '').trim() || (config?.train_from || '2013.01.01');
    let rawTo = (toDate || '').trim() || (config?.holdout_to || '2026.07.03');

    // Handle range syntax if entered in From Date (e.g. "2013-2026", "2013 to 2026", "2013..2026", "2013 -> 2026")
    let foundSep = false;
    for (const sep of [' to ', ' - ', ' -> ', '..']) {
      if (rawFrom.includes(sep)) {
        const parts = rawFrom.split(sep);
        rawFrom = parts[0].trim();
        rawTo = parts[1].trim();
        foundSep = true;
        break;
      }
    }
    if (!foundSep) {
      const mRange = rawFrom.match(/^(\d{4})\s*[-/]\s*(\d{4})$/);
      if (mRange) {
        rawFrom = mRange[1];
        rawTo = mRange[2];
      }
    }

    const normFrom = normalizeMt5Date(rawFrom, '2013.01.01', false);
    const normTo = normalizeMt5Date(rawTo, '2026.07.03', true);
    const resolvedSymbol = resolveMarketSymbol(selectedMarket);

    // Reflect normalized dates back in UI for clarity (matching app.py)
    setFromDate(normFrom);
    setToDate(normTo);

    runScript('run_full_backtest.py', {
      patch: {
        patches: {
          TARGET_RUN_DIR: selectedRun || 'latest',
          TARGET_CANDIDATE: selectedCand || 'cand_001',
          TARGET_SYMBOL: resolvedSymbol,
          TARGET_EA: selectedEa || 'TRB',
          TARGET_SET_FILE: selectedSetFile || '',
          TARGET_FROM_DATE: normFrom,
          TARGET_TO_DATE: normTo,
        }
      },
      envOverrides: {
        AF_ACTIVE_EA: selectedEa || 'TRB',
        AF_SET_FILE: selectedSetFile || '',
        AF_SYMBOL: resolvedSymbol,
        AF_BT_START: normFrom,
        AF_BT_END: normTo,
        AF_DEPOSIT: deposit,
        AF_LOT_SIZE: lotSize,
        AF_RISK_PCT: riskPct,
      }
    });
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="📋 Full Backtest" 
        subtitle="Run a full-period backtest with advanced charts & Word report for a candidate" 
      />
      
      <Card className="p-5">
        <div className="grid gap-4 max-w-2xl mb-4">
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Run Directory</label>
            <select 
              value={selectedRun} 
              onChange={e => handleRunChange(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
            >
              {runs.length > 0 ? (
                runs.map(r => (
                  <option key={r.name} value={r.name}>
                    {r.name} ({r.passedCandidates} passed)
                  </option>
                ))
              ) : (
                <option value="latest">latest (or select when runs exist)</option>
              )}
            </select>
          </div>
          
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Candidate</label>
            <select 
              value={selectedCand} 
              onChange={e => handleCandChange(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
            >
              {candidates.length > 0 ? (
                candidates.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))
              ) : (
                <option value="cand_001">cand_001 (default)</option>
              )}
            </select>
          </div>

          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Candidate .set File</label>
            <select 
              value={selectedSetFile} 
              onChange={e => setSelectedSetFile(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
            >
              {setFiles.length > 0 ? (
                setFiles.map(f => (
                  <option key={f} value={f}>{f}</option>
                ))
              ) : (
                <option value={selectedSetFile || `c001_full.set`}>
                  {selectedSetFile || `c001_full.set`} (default)
                </option>
              )}
            </select>
          </div>

          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Strategy / EA</label>
            <select 
              value={selectedEa} 
              onChange={e => setSelectedEa(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
            >
              {eas.map(ea => (
                <option key={ea} value={ea}>{ea}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Market / Symbol</label>
            <select 
              value={selectedMarket} 
              onChange={e => setSelectedMarket(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
            >
              {MARKETS.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6 p-4 bg-[#111827] border border-[#2d3748] rounded-lg">
          <div>
            <label className="text-[11px] text-[#8b95a6] block mb-1">From Date</label>
            <input 
              type="text" 
              value={fromDate} 
              onChange={e => setFromDate(e.target.value)} 
              className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono" 
            />
          </div>
          <div>
            <label className="text-[11px] text-[#8b95a6] block mb-1">To Date</label>
            <input 
              type="text" 
              value={toDate} 
              onChange={e => setToDate(e.target.value)} 
              className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono" 
            />
          </div>
          <div>
            <label className="text-[11px] text-[#8b95a6] block mb-1">Deposit ($)</label>
            <input 
              type="text" 
              value={deposit} 
              onChange={e => setDeposit(e.target.value)} 
              className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono" 
            />
          </div>
          <div>
            <label className="text-[11px] text-[#8b95a6] block mb-1">Lot Size</label>
            <input 
              type="text" 
              placeholder="(EA default)"
              value={lotSize} 
              onChange={e => setLotSize(e.target.value)} 
              className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono" 
            />
          </div>
          <div>
            <label className="text-[11px] text-[#8b95a6] block mb-1">Risk %</label>
            <input 
              type="text" 
              placeholder="(EA default)"
              value={riskPct} 
              onChange={e => setRiskPct(e.target.value)} 
              className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono" 
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-[#2d3748]">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={16} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleRun}>
              <Play size={16} /> Run Full Backtest
            </Button>
          )}
          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={16} /> Clear Log
          </Button>
          <Button 
            variant="secondary" 
            onClick={() => setShowOutputModal(true)}
          >
            <FolderOpen size={16} /> Open Output
          </Button>
          <Button variant="secondary" onClick={fetchLists} disabled={loading}>
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>
      </Card>

      <div className="flex-1 min-h-[300px] flex flex-col">
        <LogViewer logs={logs} title={`Full Backtest Output ${isRunning ? '(Executing...)' : ''}`} />
      </div>

      {showOutputModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111827] border border-[#2d3748] rounded-xl w-full max-w-lg overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-[#2d3748] bg-[#060912]">
              <div className="flex items-center gap-2 font-bold text-white text-sm">
                <FolderOpen size={18} className="text-[#f59e0b]" />
                Full Backtest Output Directory
              </div>
              <button 
                onClick={() => setShowOutputModal(false)}
                className="text-[#8b95a6] hover:text-white p-1"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-3 text-xs text-[#8b95a6]">
              <p>Generated backtest reports, charts, and summary documents are saved to:</p>
              <div className="p-3 bg-[#060912] border border-[#2d3748] rounded font-mono text-amber-300 break-all select-all">
                {`${config.work_dir || "optimization_runs"}/${selectedRun || "latest"}/passed_candidates/${selectedCand || "cand_001"}/full_backtest`}
              </div>
              <p className="text-[11px]">
                On your Windows machine, open File Explorer and paste this path to access the Word report (.docx), HTML report, and monthly heatmaps.
              </p>
            </div>
            <div className="p-3 border-t border-[#2d3748] bg-[#060912] flex justify-end">
              <button
                onClick={() => setShowOutputModal(false)}
                className="px-4 py-2 bg-[#f59e0b] hover:bg-[#d97706] text-[#0a0e1a] rounded-lg font-bold text-xs"
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
