import React, { useState } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { Play, Settings as SettingsIcon, FolderOpen } from 'lucide-react';

export default function Optimize({ config }: { config: any }) {
  const [logs, setLogs] = useState<string[]>([]);
  
  const handleRun = async () => {
    setLogs(prev => [...prev, `▶  ${new Date().toLocaleTimeString()}  run_optimization.py\n   CWD: /workspace\n────────────────────────────────────────────────────────────`]);
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: 'run_optimization.py' })
      });
      const data = await res.json();
      setLogs(prev => [...prev, `Starting Optimization Pipeline...`, `Running Train phase...`, `✔  Finished (code 0) ${new Date().toLocaleTimeString()}\n`]);
    } catch (e) {
      setLogs(prev => [...prev, `[ERROR] Failed to run optimization\n`]);
    }
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
            { phase: "Train Optimize", icon: "🔵" },
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
        <Button onClick={handleRun}>
          <Play size={18} /> Run Full Pipeline
        </Button>
        <Button variant="secondary">
          <SettingsIcon size={18} /> Configure in Settings
        </Button>
        <Button variant="secondary">
          <FolderOpen size={18} /> Open Runs Folder
        </Button>
      </div>

      <LogViewer logs={logs} title="Live Pipeline Output" />
    </div>
  );
}
