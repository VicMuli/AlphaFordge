import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, RefreshCw, Square, Trash2 } from 'lucide-react';
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
  };

  const handleCandChange = (cand: string) => {
    setSelectedCand(cand);
    fetchSetFiles(selectedRun, cand);
  };

  const handleRun = () => {
    const normFrom = normalizeMt5Date(fromDate, '2013.01.01', false);
    const normTo = normalizeMt5Date(toDate, '2026.07.03', true);

    runScript('run_full_backtest.py', {
      patch: {
        patches: {
          TARGET_RUN_DIR: selectedRun || 'latest',
          TARGET_CANDIDATE: selectedCand || 'cand_001',
          TARGET_SYMBOL: selectedMarket || 'USDJPY',
          TARGET_EA: selectedEa || 'TRB',
          TARGET_SET_FILE: selectedSetFile || '',
          TARGET_FROM_DATE: normFrom,
          TARGET_TO_DATE: normTo,
        }
      },
      envOverrides: {
        AF_ACTIVE_EA: selectedEa || 'TRB',
        AF_SET_FILE: selectedSetFile || '',
        AF_SYMBOL: selectedMarket || 'USDJPY',
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
            onClick={() => alert(`Backtest output report folder:\n${config.work_dir || "optimization_runs"}/${selectedRun || "latest"}/passed_candidates/${selectedCand || "cand_001"}/full_backtest`)}
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
    </div>
  );
}
