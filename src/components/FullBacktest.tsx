import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, RefreshCw, Square, Trash2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function FullBacktest({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  
  const handleRun = () => {
    runScript('run_full_backtest.py');
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="📋 Full Backtest" subtitle="Run a full-period backtest with advanced charts & Word report for a candidate" />
      
      <Card className="mb-6">
        <div className="grid gap-6 max-w-2xl mb-8">
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-32 text-right text-sm">Run Directory</label>
            <select className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1">
              <option>(none)</option>
            </select>
          </div>
          
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-32 text-right text-sm">Candidate</label>
            <select className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1">
              <option>(none found)</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-6 mb-8">
          <Input label="From Date" defaultValue={config.train_from} className="w-48 [&>label]:w-auto" />
          <Input label="To Date" defaultValue={config.holdout_to} className="w-48 [&>label]:w-auto" />
          <Input label="Deposit" defaultValue={config.deposit || "2500"} className="w-32 [&>label]:w-auto" />
          <Input label="Lot Size" defaultValue={config.lot_size || ""} className="w-32 [&>label]:w-auto" />
          <Input label="Risk %" defaultValue={config.risk_pct || ""} className="w-32 [&>label]:w-auto" />
        </div>

        <div className="flex gap-4">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={18} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleRun}>
              <Play size={18} /> Run Full Backtest
            </Button>
          )}
          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={18} /> Clear Log
          </Button>
          <Button variant="secondary">
            <FolderOpen size={18} /> Open Output
          </Button>
          <Button variant="secondary">
            <RefreshCw size={18} /> Refresh
          </Button>
        </div>
      </Card>

      <LogViewer logs={logs} title={`Full Backtest Output ${isRunning ? '(Executing...)' : ''}`} />
    </div>
  );
}
