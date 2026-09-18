import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { Play, Settings as SettingsIcon, FolderOpen, Square, Trash2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function Optimize({ 
  config, 
  onNavigateToSettings 
}: { 
  config: any; 
  onNavigateToSettings?: () => void; 
}) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [currentPhase, setCurrentPhase] = useState<number>(0);

  useEffect(() => {
    if (!isRunning) {
      if (logs.some(l => l.includes('[FINISHED] Process exited with code 0'))) {
        setCurrentPhase(4);
      }
      return;
    }

    const fullLog = logs.join('\n');
    if (fullLog.includes('Monte Carlo') || fullLog.includes('certif')) {
      setCurrentPhase(3);
    } else if (fullLog.includes('Validation') || fullLog.includes('Holdout')) {
      setCurrentPhase(2);
    } else if (fullLog.includes('Train') || fullLog.includes('genetic') || isRunning) {
      setCurrentPhase(1);
    }
  }, [logs, isRunning]);

  const handleRun = () => {
    setCurrentPhase(1);
    runScript('run_optimization.py');
  };

  const phases = [
    { label: "Train Optimize", phaseNum: 1 },
    { label: "Val / Holdout", phaseNum: 2 },
    { label: "Monte Carlo", phaseNum: 3 },
    { label: "Passed →", phaseNum: 4 },
  ];

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="⚙ Optimization Pipeline" 
        subtitle="Train → Validation → Holdout → Monte Carlo certification" 
      />
      
      {/* Config Summary Card */}
      <Card className="p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div className="border-r border-[#2d3748] pr-2">
            <div className="text-[#8b95a6] mb-1 font-medium">EA / Expert</div>
            <div className="font-semibold text-white truncate">
              {config.active_ea || 'TRB'} – {config.expert || 'TRB V2.0.ex5'}
            </div>
          </div>
          <div className="border-r border-[#2d3748] pr-2">
            <div className="text-[#8b95a6] mb-1 font-medium">Symbol</div>
            <div className="font-semibold text-white">
              {config.symbol || 'USDJPY Dukascopy'} ({config.period || 'M15'})
            </div>
          </div>
          <div className="border-r border-[#2d3748] pr-2">
            <div className="text-[#8b95a6] mb-1 font-medium">Date Range</div>
            <div className="font-semibold text-white">
              {config.train_from || '2013.01.01'} → {config.holdout_to || '2026.07.03'}
            </div>
          </div>
          <div>
            <div className="text-[#8b95a6] mb-1 font-medium">Deposit</div>
            <div className="font-semibold text-white">
              ${config.deposit || '2500'} {config.currency || 'USD'} ({config.leverage || '1:100'})
            </div>
          </div>
        </div>
      </Card>

      {/* Phase Progression */}
      <Card className="p-4">
        <div className="flex items-center justify-between max-w-2xl mx-auto px-4">
          {phases.map((item, idx) => {
            const isCurrent = isRunning && currentPhase === item.phaseNum;
            const isCompleted = currentPhase > item.phaseNum;
            return (
              <div key={idx} className="flex flex-col items-center gap-1.5">
                <div className="text-xl">
                  {isCurrent ? "⏳" : isCompleted ? "✅" : "🔵"}
                </div>
                <div className={`text-xs text-center font-medium ${
                  isCurrent ? "text-[#f59e0b] font-bold" : isCompleted ? "text-emerald-400" : "text-[#8b95a6]"
                }`}>
                  {item.label}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-3">
        {isRunning ? (
          <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
            <Square size={16} /> Stop Execution
          </Button>
        ) : (
          <Button onClick={handleRun}>
            <Play size={16} /> Run Full Pipeline
          </Button>
        )}
        {onNavigateToSettings && (
          <Button variant="secondary" onClick={onNavigateToSettings}>
            <SettingsIcon size={16} /> Configure in Settings
          </Button>
        )}
        <Button variant="secondary" onClick={clearLogs}>
          <Trash2 size={16} /> Clear Log
        </Button>
        <Button 
          variant="secondary" 
          onClick={() => alert(`Optimization runs folder:\n${config.work_dir || "optimization_runs"}`)}
        >
          <FolderOpen size={16} /> Open Runs Folder
        </Button>
      </div>

      {/* Live Log */}
      <div className="flex-1 min-h-[300px] flex flex-col">
        <LogViewer logs={logs} title={`Live Pipeline Output ${isRunning ? '(Running...)' : ''}`} />
      </div>
    </div>
  );
}
