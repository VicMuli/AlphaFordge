import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Package, Dices, FolderOpen, RefreshCw, Plus, Square, Trash2, X } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

interface CandidateRow {
  runDir: string;
  candidate: string;
  weight: string;
}

export default function Portfolio({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [portfolioName, setPortfolioName] = useState(`${config.quant_name || 'TRB'}_Quant_Portfolio_001`);
  const [candidateRows, setCandidateRows] = useState<CandidateRow[]>([
    { runDir: 'latest', candidate: 'cand_001', weight: '1.0' }
  ]);
  const [runs, setRuns] = useState<any[]>([]);
  const [portfolios, setPortfolios] = useState<string[]>([]);
  const [selectedMCPortfolio, setSelectedMCPortfolio] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const fetchWorkspace = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/workspace');
      if (res.ok) {
        const data = await res.json();
        const runList = data.runsDetailed || [];
        setRuns(runList);
        const portList = data.portfolios || [];
        setPortfolios(portList);
        if (portList.length > 0) {
          setSelectedMCPortfolio(portList[0]);
        }
        if (runList.length > 0 && candidateRows.length === 1 && candidateRows[0].runDir === 'latest') {
          const first = runList[0];
          setCandidateRows([
            {
              runDir: first.name,
              candidate: (first.candidates && first.candidates[0]) || 'cand_001',
              weight: '1.0'
            }
          ]);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkspace();
  }, []);

  const addRow = () => {
    const defaultRun = runs.length > 0 ? runs[0].name : 'latest';
    const defaultCand = runs.length > 0 && runs[0].candidates?.length > 0 ? runs[0].candidates[0] : 'cand_001';
    setCandidateRows(prev => [
      ...prev,
      { runDir: defaultRun, candidate: defaultCand, weight: '1.0' }
    ]);
  };

  const removeRow = (index: number) => {
    setCandidateRows(prev => prev.filter((_, idx) => idx !== index));
  };

  const updateRow = (index: number, field: keyof CandidateRow, value: string) => {
    setCandidateRows(prev => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      if (field === 'runDir') {
        const found = runs.find(r => r.name === value);
        if (found && found.candidates && found.candidates.length > 0) {
          next[index].candidate = found.candidates[0];
        }
      }
      return next;
    });
  };

  const handleBuild = () => {
    const formattedCandidates = candidateRows.map(row => ({
      run_dir: row.runDir,
      candidate: row.candidate,
      weight: parseFloat(row.weight) || 1.0,
    }));

    runScript('build_quant_portfolio.py', {
      patch: {
        patches: {
          PORTFOLIO_NAME: portfolioName,
          QUANT_NAME: config.quant_name || 'TRB',
        },
        candidates: formattedCandidates
      }
    });
  };

  const handleRunMC = () => {
    const targetName = selectedMCPortfolio || portfolioName;
    runScript('run_portfolio_montecarlo.py', {
      patch: {
        patches: {
          PORTFOLIO_NAME: targetName,
          QUANT_NAME: config.quant_name || 'TRB',
        }
      }
    });
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="📦 Portfolio Builder" 
        subtitle="Merge multiple candidates into a quant portfolio, then run Monte Carlo" 
      />
      
      <Card className="p-5">
        <div className="flex items-center gap-4 mb-5 max-w-xl">
          <label className="text-[#8b95a6] w-32 text-right text-xs font-semibold">Portfolio Name</label>
          <input 
            type="text" 
            value={portfolioName} 
            onChange={e => setPortfolioName(e.target.value)} 
            className="bg-[#1a2235] border border-[#2d3748] text-white rounded-lg px-3 py-2 flex-1 text-sm font-mono focus:outline-none focus:border-[#f59e0b]"
          />
        </div>
        
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[#f59e0b] text-xs font-bold uppercase tracking-wider">
              Candidates (run_dir | candidate | weight)
            </h3>
            <span className="text-[11px] text-[#8b95a6]">{candidateRows.length} candidates in basket</span>
          </div>

          <div className="bg-[#111827] border border-[#2d3748] rounded-lg p-3 space-y-2">
            {candidateRows.map((row, idx) => {
              const currentRun = runs.find(r => r.name === row.runDir);
              const cands = currentRun ? currentRun.candidates : [];

              return (
                <div key={idx} className="flex items-center gap-3">
                  <div className="w-8 text-center text-xs font-mono text-[#8b95a6]">#{idx + 1}</div>
                  
                  {/* Run Dir */}
                  <div className="flex-1">
                    {runs.length > 0 ? (
                      <select 
                        value={row.runDir} 
                        onChange={e => updateRow(idx, 'runDir', e.target.value)}
                        className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#f59e0b]"
                      >
                        {runs.map(r => (
                          <option key={r.name} value={r.name}>{r.name}</option>
                        ))}
                      </select>
                    ) : (
                      <input 
                        type="text" 
                        value={row.runDir} 
                        onChange={e => updateRow(idx, 'runDir', e.target.value)}
                        placeholder="run_dir"
                        className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono"
                      />
                    )}
                  </div>

                  {/* Candidate */}
                  <div className="w-48">
                    {cands && cands.length > 0 ? (
                      <select 
                        value={row.candidate} 
                        onChange={e => updateRow(idx, 'candidate', e.target.value)}
                        className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#f59e0b]"
                      >
                        {cands.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    ) : (
                      <input 
                        type="text" 
                        value={row.candidate} 
                        onChange={e => updateRow(idx, 'candidate', e.target.value)}
                        placeholder="cand_001"
                        className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2.5 py-1.5 text-xs font-mono"
                      />
                    )}
                  </div>

                  {/* Weight */}
                  <div className="w-24">
                    <input 
                      type="text" 
                      value={row.weight} 
                      onChange={e => updateRow(idx, 'weight', e.target.value)}
                      placeholder="Weight"
                      className="w-full bg-[#1a2235] border border-[#2d3748] text-white rounded px-2 py-1.5 text-xs text-center font-mono focus:outline-none focus:border-[#f59e0b]"
                    />
                  </div>

                  {/* Delete row */}
                  <button 
                    onClick={() => removeRow(idx)}
                    disabled={candidateRows.length === 1}
                    className="p-1.5 text-[#8b95a6] hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <X size={15} />
                  </button>
                </div>
              );
            })}
          </div>

          <Button variant="secondary" onClick={addRow} className="mt-2 text-xs py-1.5 px-3">
            <Plus size={14} /> Add Candidate
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-[#2d3748] mb-4">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={16} /> Stop Execution
            </Button>
          ) : (
            <>
              <Button onClick={handleBuild}>
                <Package size={16} /> Build Portfolio
              </Button>
              <Button variant="blue" onClick={handleRunMC}>
                <Dices size={16} /> Run Portfolio MC
              </Button>
            </>
          )}
          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={16} /> Clear Log
          </Button>
          <Button 
            variant="secondary" 
            onClick={() => alert(`Portfolio directory:\n${config.work_dir || "optimization_runs"}/Quant_Portfolios/${config.quant_name || "TRB"}_Quant_Portfolios/${portfolioName}`)}
          >
            <FolderOpen size={16} /> Open Portfolio Folder
          </Button>
        </div>

        <div className="flex items-center gap-3 bg-[#111827] p-3 rounded-lg border border-[#2d3748]">
          <label className="text-[#8b95a6] text-xs whitespace-nowrap font-medium">Run MC on Portfolio:</label>
          <select 
            value={selectedMCPortfolio} 
            onChange={e => setSelectedMCPortfolio(e.target.value)}
            className="bg-[#1a2235] border border-[#2d3748] text-white rounded px-3 py-1.5 text-xs flex-1 max-w-sm focus:outline-none focus:border-[#f59e0b]"
          >
            {portfolios.length > 0 ? (
              portfolios.map(p => (
                <option key={p} value={p}>{p}</option>
              ))
            ) : (
              <option value={portfolioName}>{portfolioName} (default)</option>
            )}
          </select>
          <Button variant="secondary" onClick={fetchWorkspace} disabled={loading} className="px-2.5 py-1 text-xs">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </Button>
        </div>
      </Card>

      <div className="flex-1 min-h-[300px] flex flex-col">
        <LogViewer logs={logs} title={`Portfolio Output ${isRunning ? '(Executing...)' : ''}`} />
      </div>
    </div>
  );
}
