import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, RefreshCw, FileText, Code2, BarChart3, Square, Trash2, CheckCircle2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

interface ResearchedEA {
  name: string;
  folder: string;
  logicDoc: string | null;
  mq5File: string | null;
  ex5File: string | null;
  setFiles: string[];
  htmlReport: string | null;
  wordReport: string | null;
  charts: string[];
  summary: any | null;
}

export default function Research({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [eaList, setEaList] = useState<ResearchedEA[]>([]);
  const [selectedEA, setSelectedEA] = useState<string>('');
  const [baseDir, setBaseDir] = useState<string>('researched_strategies');

  const [params, setParams] = useState({
    name: config.active_ea || 'TRB',
    expert: config.expert || 'TRB V2.0.ex5',
    set_file: '(Default EA Inputs)',
    symbol: config.symbol || 'USDJPY Dukascopy',
    period: config.period || 'M15',
    from_date: config.train_from || '2013.01.01',
    to_date: config.holdout_to || '2026.07.03',
    deposit: config.deposit || '2500'
  });

  const fetchResearchedEAs = async () => {
    try {
      const res = await fetch('/api/researched-strategies');
      if (res.ok) {
        const data = await res.json();
        setBaseDir(data.baseDir || 'researched_strategies');
        const eas: ResearchedEA[] = data.eas || [];
        setEaList(eas);

        if (eas.length > 0) {
          const match = eas.find(e => e.name === selectedEA) || eas[0];
          applyEAToForm(match);
        } else {
          setSelectedEA(config.active_ea || 'TRB');
        }
      }
    } catch (err) {
      console.error('Error fetching researched strategies:', err);
    }
  };

  const applyEAToForm = (ea: ResearchedEA) => {
    setSelectedEA(ea.name);
    setParams(prev => ({
      ...prev,
      name: ea.name,
      expert: ea.ex5File || `${ea.name} V2.0.ex5`,
      set_file: ea.setFiles && ea.setFiles.length > 0 ? ea.setFiles[0] : '(Default EA Inputs)',
    }));
  };

  useEffect(() => {
    fetchResearchedEAs();
  }, [config]);

  const activeEAInfo = eaList.find(e => e.name === selectedEA);

  const handleSelectEA = (name: string) => {
    const found = eaList.find(e => e.name === name);
    if (found) {
      applyEAToForm(found);
    } else {
      setSelectedEA(name);
      setParams(prev => ({
        ...prev,
        name,
        expert: `${name} V2.0.ex5`,
        set_file: '(Default EA Inputs)'
      }));
    }
  };

  const handleRun = () => {
    const safeSetFile = params.set_file === '(Default EA Inputs)' ? '' : params.set_file;
    runScript('run_research_backtest.py', {
      envOverrides: {
        AF_STRATEGY_NAME: params.name,
        AF_EA_NAME: params.name,
        AF_SET_FILE: safeSetFile,
        AF_EXPERT: params.expert,
        AF_SYMBOL: params.symbol,
        AF_PERIOD: params.period,
        AF_FROM_DATE: params.from_date,
        AF_TO_DATE: params.to_date,
        AF_DEPOSIT: params.deposit,
        AF_RESEARCH_DIR: baseDir,
      },
      onDone: () => {
        fetchResearchedEAs();
      }
    });
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="🔬 Research Backtest" 
        subtitle="Manage researched strategies in researched_strategies/<EA>/ and run default baseline backtests" 
      />

      {/* Strategy Assets & Folder Overview Card */}
      <Card className="mb-1 border border-[#2d3748] bg-[#161f30]">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-[#2d3748]">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
              Researched EA:
            </span>
            {eaList.length > 0 ? (
              <select
                value={selectedEA}
                onChange={e => handleSelectEA(e.target.value)}
                className="bg-[#0f172a] text-sm text-cyan-400 font-semibold px-3 py-1.5 rounded border border-[#3b82f6]/40 focus:outline-none focus:border-cyan-400"
              >
                {eaList.map(e => (
                  <option key={e.name} value={e.name}>
                    {e.name}
                  </option>
                ))}
              </select>
            ) : (
              <span className="text-sm text-gray-400 font-mono bg-[#0f172a] px-3 py-1 rounded border border-[#2d3748]">
                {selectedEA || config.active_ea || 'TRB'}
              </span>
            )}
            <Button
              variant="secondary"
              onClick={fetchResearchedEAs}
              className="text-xs px-2.5 py-1 flex items-center gap-1.5"
            >
              <RefreshCw size={13} /> Refresh
            </Button>
          </div>

          <div className="text-xs text-gray-400 font-mono">
            Folder: <span className="text-gray-200">{baseDir}/{selectedEA}</span>
          </div>
        </div>

        {/* Assets Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3">
          {/* Strategy Logic Doc */}
          <div className="bg-[#0f172a] p-3 rounded border border-[#2d3748] flex items-start gap-3">
            <FileText size={20} className={activeEAInfo?.logicDoc ? "text-blue-400 shrink-0 mt-0.5" : "text-gray-500 shrink-0 mt-0.5"} />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider font-semibold text-gray-400">Strategy Logic Doc</div>
              <div className="text-xs font-medium text-gray-200 truncate mt-0.5" title={activeEAInfo?.logicDoc || "None found"}>
                {activeEAInfo?.logicDoc || <span className="text-gray-500 italic">None found in folder</span>}
              </div>
            </div>
          </div>

          {/* MQL5 Code */}
          <div className="bg-[#0f172a] p-3 rounded border border-[#2d3748] flex items-start gap-3">
            <Code2 size={20} className={activeEAInfo?.mq5File ? "text-cyan-400 shrink-0 mt-0.5" : "text-gray-500 shrink-0 mt-0.5"} />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider font-semibold text-gray-400">EA MQL5 Code</div>
              <div className="text-xs font-medium text-gray-200 truncate mt-0.5" title={activeEAInfo?.mq5File || "None found"}>
                {activeEAInfo?.mq5File || <span className="text-gray-500 italic">None found in folder</span>}
              </div>
            </div>
          </div>

          {/* Default Backtest Status */}
          <div className="bg-[#0f172a] p-3 rounded border border-[#2d3748] flex items-start gap-3">
            <BarChart3 size={20} className={activeEAInfo?.htmlReport ? "text-emerald-400 shrink-0 mt-0.5" : "text-gray-500 shrink-0 mt-0.5"} />
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider font-semibold text-gray-400">Default Backtest</div>
              <div className="text-xs font-medium text-gray-200 truncate mt-0.5">
                {activeEAInfo?.htmlReport ? (
                  <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                    <CheckCircle2 size={13} /> Completed
                    {activeEAInfo.summary?.metrics && (
                      <span className="text-gray-300 font-normal ml-1">
                        (${activeEAInfo.summary.metrics.net_profit?.toLocaleString() || 0} / PF {activeEAInfo.summary.metrics.profit_factor || 0})
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="text-gray-500 italic">Not run yet</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </Card>
      
      {/* Parameter Settings Form */}
      <Card className="mb-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
          <Input 
            label="Strategy / EA Name" 
            value={params.name} 
            onChange={e => setParams({...params, name: e.target.value})} 
          />
          <Input 
            label="Expert (.ex5)" 
            value={params.expert} 
            onChange={e => setParams({...params, expert: e.target.value})} 
          />
          <div className="flex items-center gap-2">
            <Input 
              label="Set File" 
              value={params.set_file} 
              className="flex-1" 
              onChange={e => setParams({...params, set_file: e.target.value})} 
            />
            <Button 
              variant="secondary" 
              onClick={() => setParams({...params, set_file: '(Default EA Inputs)'})}
              className="text-xs px-2.5 whitespace-nowrap"
            >
              EA Defaults
            </Button>
          </div>
          <Input 
            label="Symbol" 
            value={params.symbol} 
            onChange={e => setParams({...params, symbol: e.target.value})} 
          />
          <Input 
            label="Period" 
            value={params.period} 
            onChange={e => setParams({...params, period: e.target.value})} 
          />
          <Input 
            label="Deposit ($)" 
            value={params.deposit} 
            onChange={e => setParams({...params, deposit: e.target.value})} 
          />
          <Input 
            label="From Date" 
            value={params.from_date} 
            onChange={e => setParams({...params, from_date: e.target.value})} 
          />
          <Input 
            label="To Date" 
            value={params.to_date} 
            onChange={e => setParams({...params, to_date: e.target.value})} 
          />
        </div>

        <div className="flex flex-wrap items-center gap-3 mt-6 pt-4 border-t border-[#2d3748]">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={16} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleRun}>
              <Play size={16} /> Run Research Backtest
            </Button>
          )}
          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={16} /> Clear Log
          </Button>
          <Button 
            variant="secondary" 
            onClick={() => alert(`Target EA folder:\n${baseDir}/${params.name}`)}
          >
            <FolderOpen size={16} /> Open EA Folder
          </Button>
        </div>
      </Card>

      <div className="flex-1 min-h-[260px] flex flex-col">
        <LogViewer logs={logs} title="Research Backtest Output" />
      </div>
    </div>
  );
}
