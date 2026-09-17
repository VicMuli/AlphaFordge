import React, { useState } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Plus, RefreshCw, FolderOpen, Play } from 'lucide-react';

export default function Strategies({ config }: { config: any }) {
  const [logs, setLogs] = useState<string[]>([]);
  
  const handleBuild = async () => {
    setLogs(prev => [...prev, `▶  ${new Date().toLocaleTimeString()}  strategy_builder.py\n   CWD: /workspace\n────────────────────────────────────────────────────────────`]);
    setTimeout(() => {
      setLogs(prev => [...prev, `✔  Finished (code 0) ${new Date().toLocaleTimeString()}\n`]);
    }, 1000);
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="🗂 Strategy Management" subtitle="Manage your base algorithmic strategies" />
      
      <Card className="mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <h3 className="text-lg font-medium text-white mb-4">Create New Strategy</h3>
            <div className="space-y-4">
              <Input label="Strategy Name" placeholder="e.g. TrendFollower_V2" />
              <Input label="Base Symbol" defaultValue={config.symbol} />
              <Input label="Timeframe" defaultValue={config.period} />
              <div className="flex gap-4 pt-4">
                <Button onClick={handleBuild}>
                  <Plus size={18} /> Create Strategy Structure
                </Button>
              </div>
            </div>
          </div>
          
          <div>
            <h3 className="text-lg font-medium text-white mb-4">Existing Strategies</h3>
            <div className="bg-[#1a2235] border border-[#2d3748] rounded-lg p-4 h-48 overflow-y-auto mb-4 text-[#8b95a6] text-sm flex items-center justify-center">
              No custom strategies found in /strategies.
            </div>
            <div className="flex gap-4">
              <Button variant="secondary">
                <RefreshCw size={18} /> Refresh List
              </Button>
              <Button variant="secondary">
                <FolderOpen size={18} /> Open Strategies Folder
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <LogViewer logs={logs} title="Strategy Builder Output" />
    </div>
  );
}
