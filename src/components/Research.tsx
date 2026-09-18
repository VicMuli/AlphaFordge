import { useState } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, Search, Square, Trash2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function Research({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [params, setParams] = useState({
    name: 'My_Strategy_v1',
    expert: config.expert || '',
    set_file: 'my_strategy.set',
    symbol: config.symbol || '',
    period: config.period || '',
    from_date: config.train_from || '',
    to_date: config.holdout_to || '',
    deposit: config.deposit || '2500'
  });

  const handleRun = () => {
    runScript('run_research_backtest.py');
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="🔬 Research Backtest" subtitle="Run a default (un-optimised) backtest for a newly researched strategy" />
      
      <Card className="mb-6">
        <div className="grid gap-4 max-w-2xl">
          <Input label="Strategy Name" value={params.name} onChange={e => setParams({...params, name: e.target.value})} />
          <Input label="Expert (.ex5)" value={params.expert} onChange={e => setParams({...params, expert: e.target.value})} />
          <div className="flex gap-4">
            <Input label="Set File" value={params.set_file} className="flex-1" onChange={e => setParams({...params, set_file: e.target.value})} />
            <Button variant="secondary"><Search size={16} /> Browse .set</Button>
          </div>
          <Input label="Symbol" value={params.symbol} onChange={e => setParams({...params, symbol: e.target.value})} />
          <Input label="Period" value={params.period} onChange={e => setParams({...params, period: e.target.value})} />
          <Input label="From Date" value={params.from_date} onChange={e => setParams({...params, from_date: e.target.value})} />
          <Input label="To Date" value={params.to_date} onChange={e => setParams({...params, to_date: e.target.value})} />
          <Input label="Deposit ($)" value={params.deposit} onChange={e => setParams({...params, deposit: e.target.value})} />
        </div>

        <div className="flex gap-4 mt-8">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={18} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleRun}>
              <Play size={18} /> Run Research Backtest
            </Button>
          )}
          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={18} /> Clear Log
          </Button>
          <Button variant="secondary">
            <FolderOpen size={18} /> Open Output Folder
          </Button>
        </div>
      </Card>

      <LogViewer logs={logs} title={`Research Backtest Output ${isRunning ? '(Executing...)' : ''}`} />
    </div>
  );
}
