import React, { useState } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Play, FolderOpen, RefreshCw } from 'lucide-react';

export default function WalkForward({ config }: { config: any }) {
  const [logs, setLogs] = useState<string[]>([]);
  
  const handleRun = async () => {
    setLogs(prev => [...prev, `▶  ${new Date().toLocaleTimeString()}  run_wf_pipeline.py\n   CWD: /workspace\n────────────────────────────────────────────────────────────`]);
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: 'run_wf_pipeline.py' })
      });
      setLogs(prev => [...prev, `✔  Finished (code 0) ${new Date().toLocaleTimeString()}\n`]);
    } catch (e) {
      setLogs(prev => [...prev, `[ERROR] Failed to run walk forward\n`]);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="📈 Walk Forward Stability Testing" subtitle="Test a candidate across rolling time windows — run one at a time" />
      
      <Card className="mb-6">
        <div className="grid gap-6 max-w-2xl mb-8">
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-32 text-right text-sm">Run Directory</label>
            <select className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 focus:outline-none focus:border-[#f59e0b] focus:ring-1 focus:ring-[#f59e0b]">
              <option>latest</option>
            </select>
          </div>
          
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-32 text-right text-sm">Candidate</label>
            <select className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 focus:outline-none focus:border-[#f59e0b] focus:ring-1 focus:ring-[#f59e0b]">
              <option>(none found)</option>
            </select>
          </div>

          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-48 text-right text-sm">Window / Step (months)</label>
            <input type="text" defaultValue={config.wf_window_months || "12"} className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 w-20 text-center" />
            <span className="text-[#8b95a6]">/</span>
            <input type="text" defaultValue={config.wf_step_months || "6"} className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 w-20 text-center" />
          </div>
        </div>

        <div className="flex gap-4">
          <Button onClick={handleRun}>
            <Play size={18} /> Run WF Testing
          </Button>
          <Button variant="secondary">
            <FolderOpen size={18} /> Open Candidate Folder
          </Button>
          <Button variant="secondary">
            <RefreshCw size={18} /> Refresh Lists
          </Button>
        </div>
      </Card>

      <LogViewer logs={logs} title="WF Testing Output" />
    </div>
  );
}
