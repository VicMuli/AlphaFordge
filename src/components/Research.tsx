import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, Search, Square, Trash2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function Research({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [params, setParams] = useState({
    name: 'My_Strategy_v1',
    expert: config.expert || 'TRB V2.0.ex5',
    set_file: 'my_strategy.set',
    symbol: config.symbol || 'USDJPY Dukascopy',
    period: config.period || 'M15',
    from_date: config.train_from || '2013.01.01',
    to_date: config.holdout_to || '2026.07.03',
    deposit: config.deposit || '2500'
  });

  useEffect(() => {
    if (config) {
      setParams(prev => ({
        ...prev,
        expert: config.expert || prev.expert,
        symbol: config.symbol || prev.symbol,
        period: config.period || prev.period,
        from_date: config.train_from || prev.from_date,
        to_date: config.holdout_to || prev.to_date,
        deposit: config.deposit || prev.deposit,
      }));
    }
  }, [config]);

  const handleRun = () => {
    runScript('run_research_backtest.py', {
      envOverrides: {
        AF_STRATEGY_NAME: params.name,
        AF_SET_FILE: params.set_file,
        AF_EXPERT: params.expert,
        AF_SYMBOL: params.symbol,
        AF_PERIOD: params.period,
        AF_FROM_DATE: params.from_date,
        AF_TO_DATE: params.to_date,
        AF_DEPOSIT: params.deposit,
      }
    });
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="🔬 Research Backtest" 
        subtitle="Run a default (un-optimised) backtest for a newly researched strategy" 
      />
      
      <Card className="mb-2">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
          <Input 
            label="Strategy Name" 
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
              onClick={() => alert(`Active set file: ${params.set_file}\nStored in your EA sets directory.`)}
              className="text-xs px-2.5 whitespace-nowrap"
            >
              <Search size={14} /> Browse
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
            onClick={() => alert(`Output folder:\n${config.research_dir || "researched_strategies"}/${params.name}`)}
          >
            <FolderOpen size={16} /> Open Output Folder
          </Button>
        </div>
      </Card>

      <div className="flex-1 min-h-[300px] flex flex-col">
        <LogViewer logs={logs} title="Research Backtest Output" />
      </div>
    </div>
  );
}
