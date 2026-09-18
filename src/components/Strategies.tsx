import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, Input, LogViewer } from './ui';
import { Plus, RefreshCw, FolderOpen, Square, Trash2, FileText, Folder } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function Strategies({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [workspace, setWorkspace] = useState<any>({
    researchedStrategies: [],
    strategyFiles: [],
  });
  const [loading, setLoading] = useState(false);
  const [newStrategyName, setNewStrategyName] = useState('');

  const fetchStrategies = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/workspace');
      if (res.ok) {
        const data = await res.json();
        setWorkspace(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStrategies();
  }, []);

  const handleBuild = () => {
    runScript('strategy_builder.py', {
      envOverrides: {
        AF_NEW_STRATEGY: newStrategyName || 'Custom_Strategy',
        AF_SYMBOL: config.symbol || 'USDJPY Dukascopy',
        AF_PERIOD: config.period || 'M15',
      }
    });
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="🗂 Strategies Browser" 
        subtitle="Browse researched strategies and optimized strategy outputs" 
      />
      
      {/* Two side-by-side library cards matching app.py StrategiesPanel */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-2">
        {/* Left: Researched Strategies */}
        <Card className="p-4 flex flex-col h-72">
          <div className="flex items-center justify-between mb-2">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                <span className="text-amber-400">🔬</span> Researched Strategies
              </h3>
              <p className="text-[11px] text-[#8b95a6] truncate max-w-xs">
                Folder: {config.research_dir || "researched_strategies"}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <Button 
                variant="secondary" 
                onClick={fetchStrategies} 
                disabled={loading}
                className="px-2 py-1 text-xs"
              >
                <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              </Button>
              <Button 
                variant="secondary" 
                onClick={() => alert(`Researched folder path:\n${config.research_dir || "researched_strategies"}`)}
                className="px-2.5 py-1 text-xs"
              >
                <FolderOpen size={12} /> Open
              </Button>
            </div>
          </div>

          <div className="bg-[#060912] border border-[#2d3748] rounded-lg p-3 flex-1 overflow-y-auto font-mono text-xs text-[#8b95a6] space-y-1.5">
            {workspace.researchedStrategies && workspace.researchedStrategies.length > 0 ? (
              workspace.researchedStrategies.map((item: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-1.5 bg-[#111827] rounded border border-[#1f2937] hover:border-[#f59e0b] transition-colors">
                  <div className="flex items-center gap-2 text-white">
                    {item.isDir ? <Folder size={14} className="text-amber-400" /> : <FileText size={14} className="text-blue-400" />}
                    <span className="truncate">{item.name}</span>
                  </div>
                  <span className="text-[10px] text-[#8b95a6]">
                    {item.isDir ? `${item.itemsCount} items` : item.mtime}
                  </span>
                </div>
              ))
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-4">
                <p className="text-xs text-[#8b95a6]">No researched strategies found.</p>
                <p className="text-[11px] text-[#556072] mt-1">Run a test from the &quot;🔬 Research&quot; tab to populate.</p>
              </div>
            )}
          </div>
        </Card>

        {/* Right: Strategies Library */}
        <Card className="p-4 flex flex-col h-72">
          <div className="flex items-center justify-between mb-2">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                <span className="text-blue-400">📦</span> Strategies Library
              </h3>
              <p className="text-[11px] text-[#8b95a6] truncate max-w-xs">
                Folder: {config.strategies_dir || "strategies"}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <Button 
                variant="secondary" 
                onClick={fetchStrategies} 
                disabled={loading}
                className="px-2 py-1 text-xs"
              >
                <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
              </Button>
              <Button 
                variant="secondary" 
                onClick={() => alert(`Strategies folder path:\n${config.strategies_dir || "strategies"}`)}
                className="px-2.5 py-1 text-xs"
              >
                <FolderOpen size={12} /> Open
              </Button>
            </div>
          </div>

          <div className="bg-[#060912] border border-[#2d3748] rounded-lg p-3 flex-1 overflow-y-auto font-mono text-xs text-[#8b95a6] space-y-1.5">
            {workspace.strategyFiles && workspace.strategyFiles.length > 0 ? (
              workspace.strategyFiles.map((item: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-1.5 bg-[#111827] rounded border border-[#1f2937] hover:border-[#3b82f6] transition-colors">
                  <div className="flex items-center gap-2 text-white">
                    {item.isDir ? <Folder size={14} className="text-amber-400" /> : <FileText size={14} className="text-blue-400" />}
                    <span className="truncate">{item.name}</span>
                  </div>
                  <span className="text-[10px] text-[#8b95a6]">
                    {item.isDir ? `${item.itemsCount} items` : item.mtime}
                  </span>
                </div>
              ))
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center p-4">
                <p className="text-xs text-[#8b95a6]">No strategy files found in strategies directory.</p>
                <p className="text-[11px] text-[#556072] mt-1">Add .ex5 or Python rule sets to compile.</p>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Strategy Builder Launcher */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 flex-1 min-w-[240px]">
            <label className="text-xs text-[#8b95a6] font-semibold whitespace-nowrap">Build Strategy:</label>
            <input 
              type="text" 
              placeholder="e.g. TrendFollower_V2" 
              value={newStrategyName} 
              onChange={e => setNewStrategyName(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-white rounded px-3 py-1.5 text-xs flex-1 focus:outline-none focus:border-[#f59e0b]"
            />
          </div>

          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700 py-1.5 text-xs">
              <Square size={14} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleBuild} className="py-1.5 text-xs">
              <Plus size={14} /> Run Strategy Builder
            </Button>
          )}

          <Button variant="secondary" onClick={clearLogs} className="py-1.5 text-xs">
            <Trash2 size={14} /> Clear Log
          </Button>
        </div>
      </Card>

      <div className="flex-1 min-h-[260px] flex flex-col">
        <LogViewer logs={logs} title={`Strategy Builder Terminal Output ${isRunning ? '(Running...)' : ''}`} />
      </div>
    </div>
  );
}
