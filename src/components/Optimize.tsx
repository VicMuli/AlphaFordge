import { Card, SectionHeader, Button, LogViewer } from './ui';
import { Play, Settings as SettingsIcon, FolderOpen, Square, Trash2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function Optimize({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  
  const handleRun = () => {
    runScript('run_optimization.py');
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="⚙ Optimization Pipeline" subtitle="Train → Validation → Holdout → Monte Carlo certification" />
      
      <Card className="mb-6">
        <div className="grid grid-cols-4 gap-6">
          <div>
            <div className="text-sm text-[#8b95a6] mb-1">EA / Expert</div>
            <div className="font-medium">{config.active_ea || '?'} – {config.expert || ''}</div>
          </div>
          <div>
            <div className="text-sm text-[#8b95a6] mb-1">Symbol</div>
            <div className="font-medium">{config.symbol || ''} {config.period || ''}</div>
          </div>
          <div>
            <div className="text-sm text-[#8b95a6] mb-1">Date Range</div>
            <div className="font-medium">{config.train_from || ''} → {config.holdout_to || ''}</div>
          </div>
          <div>
            <div className="text-sm text-[#8b95a6] mb-1">Deposit</div>
            <div className="font-medium">${config.deposit || '2500'} {config.currency || 'USD'}</div>
          </div>
        </div>
      </Card>

      <Card className="mb-6">
        <div className="flex justify-between max-w-3xl">
          {[
            { phase: "Train Optimize", icon: isRunning ? "⏳" : "🔵" },
            { phase: "Val / Holdout", icon: "🔵" },
            { phase: "Monte Carlo", icon: "🔵" },
            { phase: "Passed →", icon: "🔵" }
          ].map((item, i) => (
            <div key={i} className="flex flex-col items-center">
              <div className="text-2xl mb-2">{item.icon}</div>
              <div className="text-sm text-[#8b95a6] whitespace-pre-wrap text-center">{item.phase}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="flex gap-4 mb-6">
        {isRunning ? (
          <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
            <Square size={18} /> Stop Execution
          </Button>
        ) : (
          <Button onClick={handleRun}>
            <Play size={18} /> Run Full Pipeline
          </Button>
        )}
        <Button variant="secondary" onClick={clearLogs}>
          <Trash2 size={18} /> Clear Log
        </Button>
        <Button variant="secondary">
          <FolderOpen size={18} /> Open Runs Folder
        </Button>
      </div>

      <LogViewer logs={logs} title={`Live Pipeline Output ${isRunning ? '(Executing...)' : ''}`} />
    </div>
  );
}
