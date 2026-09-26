import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { 
  Package, 
  Dices, 
  FolderOpen, 
  RefreshCw, 
  Plus, 
  Square, 
  Trash2, 
  X, 
  FileText, 
  CheckCircle2, 
  BarChart2, 
  Layers,
  ArrowRight,
  TrendingUp,
  FileSpreadsheet
} from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

interface CandidateRow {
  runDir: string;
  candidate: string;
  weight: string;
}

interface PortfolioDetail {
  name: string;
  path: string;
  manifest: any;
  charts: string[];
  docxFiles: string[];
  hasTrades: boolean;
  candidateCount: number;
  tradeCount: number;
  createdUtc: string | null;
  deposit: number;
}

export default function Portfolio({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [portfolioName, setPortfolioName] = useState(`${config.quant_name || 'TRB'}_Quant_Portfolio_001`);
  const [outputFolder, setOutputFolder] = useState<string>('Multi_Market_Quant_Portfolio');
  const [candidateRows, setCandidateRows] = useState<CandidateRow[]>([
    { runDir: 'latest', candidate: 'cand_014', weight: '1.0' }
  ]);
  const [runs, setRuns] = useState<any[]>([]);
  const [portfolios, setPortfolios] = useState<string[]>([]);
  const [detailedPortfolios, setDetailedPortfolios] = useState<PortfolioDetail[]>([]);
  const [selectedMCPortfolio, setSelectedMCPortfolio] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [activeView, setActiveView] = useState<'builder' | 'library'>('library');

  const fetchWorkspace = async () => {
    setLoading(true);
    try {
      // Fetch basic runs
      const res = await fetch('/api/workspace');
      if (res.ok) {
        const data = await res.json();
        const runList = data.runsDetailed || [];
        setRuns(runList);
        const portList = data.portfolios || [];
        setPortfolios(portList);
        if (portList.length > 0 && !selectedMCPortfolio) {
          setSelectedMCPortfolio(portList[0]);
        }
      }

      // Fetch detailed portfolios
      const detRes = await fetch('/api/portfolios-detailed');
      if (detRes.ok) {
        const detData = await detRes.json();
        setDetailedPortfolios(detData.portfolios || []);
        if (detData.portfolios?.length > 0 && !selectedMCPortfolio) {
          setSelectedMCPortfolio(detData.portfolios[0].name);
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
    const defaultCand = runs.length > 0 && runs[0].candidates?.length > 0 ? runs[0].candidates[0] : 'cand_014';
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
    const cleanPortName = (portfolioName || 'Quant_Portfolio_001')
      .replace(/[/\\:]+/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_+|_+$/g, '');

    const formattedCandidates = candidateRows.map(row => {
      const runObj = runs.find(r => r.name === row.runDir || r.path === row.runDir);
      let detectedMarket: string | undefined = undefined;
      const combined = `${row.runDir} ${runObj?.path || ''} ${row.candidate}`.toLowerCase();
      for (const mkt of ['eurjpy', 'usdjpy', 'gbpjpy', 'audusd', 'eurusd', 'xauusd', 'btcusd']) {
        if (combined.includes(mkt)) {
          detectedMarket = mkt.toUpperCase();
          break;
        }
      }
      return {
        run_dir: row.runDir,
        run_path: runObj?.path,
        candidate: row.candidate,
        weight: parseFloat(row.weight) || 1.0,
        ...(detectedMarket ? { market: detectedMarket } : {}),
      };
    });

    runScript('build_quant_portfolio.py', {
      patch: {
        patches: {
          PORTFOLIO_NAME: cleanPortName,
          QUANT_NAME: config.quant_name || 'TRB',
          TARGET_OUTPUT_DIR: outputFolder || 'Multi_Market_Quant_Portfolio',
        },
        candidates: formattedCandidates
      },
      envOverrides: {
        AF_PORTFOLIO_OUTPUT_DIR: outputFolder || 'Multi_Market_Quant_Portfolio',
      },
      onDone: () => {
        fetchWorkspace();
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
      },
      onDone: () => {
        fetchWorkspace();
      }
    });
  };

  const loadPortfolioIntoBuilder = (p: PortfolioDetail) => {
    setPortfolioName(p.name);
    if (p.manifest?.candidates && p.manifest.candidates.length > 0) {
      setCandidateRows(p.manifest.candidates.map((c: any) => ({
        runDir: c.run_dir || 'latest',
        candidate: c.candidate,
        weight: String(c.weight || 1.0)
      })));
    }
    setActiveView('builder');
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <SectionHeader 
          title="📦 Portfolio Engine" 
          subtitle="Assemble multiple strategy candidates into a unified quant portfolio and stress-test performance" 
        />

        <div className="flex items-center gap-2">
          {/* Tab Switcher */}
          <div className="flex items-center bg-[#111827] p-1 rounded-lg border border-[#2d3748] text-xs">
            <button
              onClick={() => setActiveView('library')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors flex items-center gap-1.5 ${
                activeView === 'library' 
                  ? 'bg-[#f59e0b] text-black font-bold' 
                  : 'text-[#8b95a6] hover:text-white'
              }`}
            >
              <Package size={14} />
              <span>Built Portfolios ({detailedPortfolios.length})</span>
            </button>

            <button
              onClick={() => setActiveView('builder')}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors flex items-center gap-1.5 ${
                activeView === 'builder' 
                  ? 'bg-[#f59e0b] text-black font-bold' 
                  : 'text-[#8b95a6] hover:text-white'
              }`}
            >
              <Plus size={14} />
              <span>New Basket Builder</span>
            </button>
          </div>

          <Button variant="secondary" onClick={fetchWorkspace} disabled={loading} className="text-xs py-1.5 px-2.5">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </Button>
        </div>
      </div>

      {/* VIEW: Built Portfolios Library */}
      {activeView === 'library' && (
        <div className="space-y-4">
          {detailedPortfolios.length > 0 ? (
            <div className="grid grid-cols-1 gap-4">
              {detailedPortfolios.map((p) => (
                <Card key={p.name} className="p-5 border border-[#2d3748] bg-[#111827]">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between pb-4 mb-4 border-b border-[#2d3748] gap-4">
                    <div className="flex items-center gap-3">
                      <div className="p-3 rounded-xl bg-amber-500/20 text-[#f59e0b] border border-amber-500/30">
                        <Package size={24} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-bold text-white tracking-wide">{p.name}</h3>
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950/60 border border-emerald-600/40 text-emerald-400 font-semibold">
                            READY
                          </span>
                        </div>
                        <p className="text-xs text-[#8b95a6] font-mono mt-0.5">
                          {p.path} {p.createdUtc ? `• Created ${new Date(p.createdUtc).toLocaleDateString()}` : ''}
                        </p>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <Button 
                        variant="blue" 
                        onClick={() => {
                          setSelectedMCPortfolio(p.name);
                          handleRunMC();
                        }} 
                        className="text-xs py-2 px-3"
                      >
                        <Dices size={14} />
                        <span>Run Portfolio MC</span>
                      </Button>

                      <Button 
                        variant="secondary" 
                        onClick={() => loadPortfolioIntoBuilder(p)} 
                        className="text-xs py-2 px-3 border-[#2d3748]"
                      >
                        <Layers size={14} />
                        <span>Edit / Clone Basket</span>
                      </Button>
                    </div>
                  </div>

                  {/* Portfolio Stats Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                    <div className="bg-[#1a2235] p-3 rounded-lg border border-[#2d3748]">
                      <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Candidate Basket</span>
                      <span className="text-sm font-bold font-mono text-white">
                        {p.candidateCount} strategies
                      </span>
                    </div>

                    <div className="bg-[#1a2235] p-3 rounded-lg border border-[#2d3748]">
                      <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Completed Trades</span>
                      <span className="text-sm font-bold font-mono text-amber-400">
                        {p.tradeCount ? p.tradeCount.toLocaleString() : 'Simulated'}
                      </span>
                    </div>

                    <div className="bg-[#1a2235] p-3 rounded-lg border border-[#2d3748]">
                      <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Backtest Horizon</span>
                      <span className="text-xs font-bold font-mono text-white">
                        {p.manifest?.backtest_range ? `${p.manifest.backtest_range[0]} → ${p.manifest.backtest_range[1]}` : '2013 - 2026'}
                      </span>
                    </div>

                    <div className="bg-[#1a2235] p-3 rounded-lg border border-[#2d3748]">
                      <span className="text-[10px] text-[#8b95a6] uppercase tracking-wider block">Account Capital</span>
                      <span className="text-sm font-bold font-mono text-emerald-400">
                        ${p.deposit ? p.deposit.toLocaleString() : '2,500'}
                      </span>
                    </div>
                  </div>

                  {/* Candidates List in Portfolio */}
                  {p.manifest?.candidates && (
                    <div className="mb-4">
                      <h4 className="text-xs font-bold text-[#8b95a6] uppercase tracking-wider mb-2">
                        Allocated Candidates & Weights
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {p.manifest.candidates.map((cand: any, cIdx: number) => (
                          <div 
                            key={cIdx} 
                            className="bg-[#1a2235] border border-[#2d3748] rounded px-2.5 py-1 text-xs font-mono flex items-center gap-2"
                          >
                            <span className="text-white font-bold">{cand.candidate}</span>
                            <span className="text-amber-400 font-semibold">w={cand.weight}</span>
                            {cand.completed_trade_count && (
                              <span className="text-[10px] text-[#8b95a6]">({cand.completed_trade_count} trades)</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Generated Reports & Artifacts */}
                  <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-[#2d3748] text-xs">
                    <span className="text-[#8b95a6] font-medium">Artifacts:</span>
                    {(p.docxFiles || []).map((doc, dIdx) => (
                      <span key={dIdx} className="bg-[#1a2235] text-blue-300 px-2.5 py-1 rounded border border-[#2d3748] flex items-center gap-1.5 font-mono">
                        <FileText size={12} />
                        {doc}
                      </span>
                    ))}
                    {p.hasTrades && (
                      <span className="bg-[#1a2235] text-emerald-300 px-2.5 py-1 rounded border border-[#2d3748] flex items-center gap-1.5 font-mono">
                        <FileSpreadsheet size={12} />
                        combined_trades.csv
                      </span>
                    )}
                    {p.charts && p.charts.length > 0 && (
                      <span className="bg-[#1a2235] text-amber-300 px-2.5 py-1 rounded border border-[#2d3748] flex items-center gap-1.5 font-mono">
                        <BarChart2 size={12} />
                        {p.charts.length} chart images generated
                      </span>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="p-8 text-center border border-[#2d3748] bg-[#111827]">
              <Package size={36} className="mx-auto text-[#64748b] mb-3" />
              <h3 className="text-base font-bold text-white mb-1">No Portfolios Found Yet</h3>
              <p className="text-xs text-[#8b95a6] max-w-md mx-auto mb-4">
                Build your first quant portfolio by combining surviving candidates from your optimization runs.
              </p>
              <Button onClick={() => setActiveView('builder')} className="text-xs py-2 px-4 mx-auto">
                <Plus size={14} /> Open Portfolio Builder
              </Button>
            </Card>
          )}
        </div>
      )}

      {/* VIEW: New Basket Builder */}
      {activeView === 'builder' && (
        <Card className="p-5 border border-[#2d3748]">
          <div className="flex items-center gap-4 mb-3 max-w-xl">
            <label className="text-[#8b95a6] w-32 text-right text-xs font-semibold">Portfolio Name</label>
            <input 
              type="text" 
              value={portfolioName} 
              onChange={e => setPortfolioName(e.target.value)} 
              className="bg-[#1a2235] border border-[#2d3748] text-white rounded-lg px-3 py-2 flex-1 text-sm font-mono focus:outline-none focus:border-[#f59e0b]"
            />
          </div>

          <div className="flex items-center gap-4 mb-5 max-w-xl">
            <label className="text-[#8b95a6] w-32 text-right text-xs font-semibold">Output Folder</label>
            <input 
              type="text" 
              value={outputFolder} 
              onChange={e => setOutputFolder(e.target.value)} 
              placeholder="Multi_Market_Quant_Portfolio"
              className="bg-[#1a2235] border border-[#2d3748] text-white rounded-lg px-3 py-2 flex-1 text-sm font-mono focus:outline-none focus:border-[#f59e0b]"
            />
            <button
              type="button"
              onClick={() => setOutputFolder('Multi_Market_Quant_Portfolio')}
              className="text-[11px] px-2 py-1 bg-[#1e293b] hover:bg-[#334155] text-amber-300 rounded border border-[#2d3748] whitespace-nowrap"
            >
              Default Folder
            </button>
          </div>
          
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[#f59e0b] text-xs font-bold uppercase tracking-wider">
                Candidates Basket (run_dir | candidate | weight)
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
                          placeholder="cand_014"
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

          <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-[#2d3748]">
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
          </div>
        </Card>
      )}

      {/* Upgraded Terminal with Fullscreen & Easy Up/Down Scrolling */}
      <div className="flex-1 min-h-[380px] flex flex-col">
        <LogViewer 
          logs={logs} 
          title={`Portfolio Terminal ${isRunning ? '(Executing...)' : ''}`}
          isRunning={isRunning}
          onClear={clearLogs}
        />
      </div>
    </div>
  );
}
