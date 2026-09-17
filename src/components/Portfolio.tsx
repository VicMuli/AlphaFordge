import React, { useState } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Package, Dices, FolderOpen, RefreshCw, Plus } from 'lucide-react';

export default function Portfolio({ config }: { config: any }) {
  const [logs, setLogs] = useState<string[]>([]);
  
  const handleBuild = async () => {
    setLogs(prev => [...prev, `▶  ${new Date().toLocaleTimeString()}  build_quant_portfolio.py\n   CWD: /workspace\n────────────────────────────────────────────────────────────`]);
    setTimeout(() => {
      setLogs(prev => [...prev, `✔  Finished (code 0) ${new Date().toLocaleTimeString()}\n`]);
    }, 1000);
  };

  const handleRunMC = async () => {
    setLogs(prev => [...prev, `▶  ${new Date().toLocaleTimeString()}  run_portfolio_montecarlo.py\n   CWD: /workspace\n────────────────────────────────────────────────────────────`]);
    setTimeout(() => {
      setLogs(prev => [...prev, `✔  Finished (code 0) ${new Date().toLocaleTimeString()}\n`]);
    }, 1500);
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="📦 Portfolio Builder" subtitle="Merge multiple candidates into a quant portfolio, then run Monte Carlo" />
      
      <Card className="mb-6">
        <Input label="Portfolio Name" defaultValue={`${config.quant_name || 'TRB'}_Quant_Portfolio_001`} className="max-w-xl mb-6" />
        
        <div className="mb-6">
          <h3 className="text-[#f59e0b] font-medium mb-4">Candidates (run_dir | candidate | weight)</h3>
          <div className="bg-[#1a2235] border border-[#2d3748] rounded-lg p-4 min-h-[150px] mb-4 flex flex-col gap-3">
            <div className="flex gap-4">
              <select className="bg-[#111827] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1">
                <option>(none)</option>
              </select>
              <select className="bg-[#111827] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1">
                <option>(none)</option>
              </select>
              <input type="text" defaultValue="1.0" className="bg-[#111827] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 w-24 text-center" />
            </div>
          </div>
          <Button variant="secondary" className="w-48"><Plus size={16} /> Add Candidate</Button>
        </div>

        <div className="flex gap-4 mb-8">
          <Button onClick={handleBuild}>
            <Package size={18} /> Build Portfolio
          </Button>
          <Button variant="blue" onClick={handleRunMC}>
            <Dices size={18} /> Run Portfolio MC
          </Button>
          <Button variant="secondary">
            <FolderOpen size={18} /> Open Portfolio Folder
          </Button>
        </div>

        <div className="flex items-center gap-4 bg-[#1a2235] p-4 rounded-lg">
          <label className="text-[#8b95a6] text-sm whitespace-nowrap">Run MC on Portfolio:</label>
          <select className="bg-[#111827] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 w-64">
            <option>(none)</option>
          </select>
          <Button variant="secondary" className="px-3"><RefreshCw size={16} /></Button>
        </div>
      </Card>

      <LogViewer logs={logs} title="Portfolio Output" />
    </div>
  );
}
