import React, { useState } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { RefreshCw, FolderOpen } from 'lucide-react';

export default function Dashboard({ config }: { config: any }) {
  const [logs, setLogs] = useState<string[]>([]);
  
  const handleRefresh = () => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Refreshing workspace stats...`, "Workspace data loaded successfully."]);
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="🏠 Dashboard" subtitle="Overview of your AlphaForge workspace" />
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <Card>
          <div className="text-3xl mb-4">📁</div>
          <div className="text-3xl font-bold text-[#f59e0b] mb-1">12</div>
          <div className="text-sm text-[#8b95a6]">Optimization Runs</div>
        </Card>
        <Card>
          <div className="text-3xl mb-4">✅</div>
          <div className="text-3xl font-bold text-[#f59e0b] mb-1">45</div>
          <div className="text-sm text-[#8b95a6]">Passed Candidates</div>
        </Card>
        <Card>
          <div className="text-3xl mb-4">📦</div>
          <div className="text-3xl font-bold text-[#f59e0b] mb-1">3</div>
          <div className="text-sm text-[#8b95a6]">Portfolios Built</div>
        </Card>
        <Card>
          <div className="text-3xl mb-4">🔬</div>
          <div className="text-3xl font-bold text-[#f59e0b] mb-1">8</div>
          <div className="text-sm text-[#8b95a6]">Researched Strategies</div>
        </Card>
      </div>

      <div className="flex gap-4 mb-8">
        <Button onClick={handleRefresh}>
          <RefreshCw size={18} /> Refresh
        </Button>
        <Button variant="secondary">
          <FolderOpen size={18} /> Open Work Dir
        </Button>
        <Button variant="secondary">
          <FolderOpen size={18} /> Open Research Dir
        </Button>
      </div>

      <LogViewer logs={logs} title="Recent Optimization Runs" />
    </div>
  );
}
