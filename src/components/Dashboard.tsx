import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button } from './ui';
import { RefreshCw, FolderOpen, X, Terminal, CheckCircle2 } from 'lucide-react';

export default function Dashboard({ config }: { config: any }) {
  const [workspace, setWorkspace] = useState<any>({
    totalRuns: 0,
    totalPassed: 0,
    portfolios: [],
    recentRuns: [],
    researchedStrategies: [],
    strategyFiles: [],
  });
  const [loading, setLoading] = useState(false);
  const [modalTitle, setModalTitle] = useState<string | null>(null);
  const [modalItems, setModalItems] = useState<any[]>([]);

  const fetchWorkspace = async () => {
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
    fetchWorkspace();
  }, []);

  const openWorkDirModal = () => {
    setModalTitle("Work Directory (optimization_runs)");
    setModalItems(
      workspace.recentRuns.length > 0
        ? workspace.recentRuns.map((r: any) => ({
            name: r.name,
            subtitle: `${r.passedCandidates} passed candidates`,
            details: r.candidates ? `${r.candidates.length} total candidates` : undefined,
          }))
        : [{ name: "optimization_runs/trb_usdjpy", subtitle: "Active symbol folder" }]
    );
  };

  const openResearchDirModal = () => {
    setModalTitle("Researched Strategies Directory");
    setModalItems(
      workspace.researchedStrategies.length > 0
        ? workspace.researchedStrategies.map((item: any) => ({
            name: item.name,
            subtitle: `${item.itemsCount || 0} items | Modified: ${item.mtime}`,
          }))
        : [{ name: "researched_strategies", subtitle: "Folder ready for new strategy backtests" }]
    );
  };

  return (
    <div className="flex flex-col h-full">
      <SectionHeader title="🏠  Dashboard" subtitle="Overview of your AlphaForge workspace" />
      
      {/* Stat cards matching app.py */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="flex flex-col items-center justify-center text-center p-5">
          <div className="text-3xl mb-2">📁</div>
          <div className="text-2xl font-bold text-[#f59e0b] mb-1">
            {loading ? "..." : workspace.totalRuns}
          </div>
          <div className="text-xs font-medium text-[#8b95a6]">Optimization Runs</div>
        </Card>

        <Card className="flex flex-col items-center justify-center text-center p-5">
          <div className="text-3xl mb-2">✅</div>
          <div className="text-2xl font-bold text-[#f59e0b] mb-1">
            {loading ? "..." : workspace.totalPassed}
          </div>
          <div className="text-xs font-medium text-[#8b95a6]">Passed Candidates</div>
        </Card>

        <Card className="flex flex-col items-center justify-center text-center p-5">
          <div className="text-3xl mb-2">📦</div>
          <div className="text-2xl font-bold text-[#f59e0b] mb-1">
            {loading ? "..." : (workspace.portfolios?.length || 0)}
          </div>
          <div className="text-xs font-medium text-[#8b95a6]">Portfolios Built</div>
        </Card>

        <Card className="flex flex-col items-center justify-center text-center p-5">
          <div className="text-3xl mb-2">🔬</div>
          <div className="text-2xl font-bold text-[#f59e0b] mb-1">
            {loading ? "..." : (workspace.researchedStrategies?.length || 0)}
          </div>
          <div className="text-xs font-medium text-[#8b95a6]">Researched Strategies</div>
        </Card>
      </div>

      {/* Recent Optimization Runs box */}
      <Card className="mb-6 flex-1 flex flex-col min-h-[220px]">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-[#f59e0b]">Recent Optimization Runs</h3>
          <span className="text-xs text-[#8b95a6]">
            Path: {config.work_dir || "optimization_runs"}
          </span>
        </div>
        <div className="bg-[#060912] border border-[#2d3748] rounded-lg p-4 flex-1 overflow-y-auto font-mono text-xs text-[#a8d8a8] leading-relaxed">
          {workspace.recentRuns && workspace.recentRuns.length > 0 ? (
            workspace.recentRuns.map((r: any, idx: number) => (
              <div key={idx} className="py-0.5">
                &nbsp;&nbsp;{r.name}&nbsp;&nbsp;&nbsp;passed candidates: {r.passedCandidates}
              </div>
            ))
          ) : (
            <div className="text-[#8b95a6] py-1">
              &nbsp;&nbsp;No optimization runs recorded in workspace yet.
              <br />
              &nbsp;&nbsp;Launch a run from the &quot;⚙ Optimize&quot; tab or run <span className="text-[#f59e0b]">python app.py</span> locally on Windows.
            </div>
          )}
        </div>
      </Card>

      {/* Quick Action Buttons */}
      <div className="flex flex-wrap gap-4 mb-4">
        <Button onClick={fetchWorkspace} disabled={loading} className="w-36">
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Refresh
        </Button>
        <Button variant="secondary" onClick={openWorkDirModal}>
          <FolderOpen size={16} /> Open Work Dir
        </Button>
        <Button variant="secondary" onClick={openResearchDirModal}>
          <FolderOpen size={16} /> Open Research Dir
        </Button>
      </div>

      {/* Directory items modal */}
      {modalTitle && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111827] border border-[#2d3748] rounded-xl w-full max-w-lg overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-[#2d3748] bg-[#060912]">
              <div className="flex items-center gap-2 font-semibold text-white text-sm">
                <FolderOpen size={18} className="text-[#f59e0b]" />
                {modalTitle}
              </div>
              <button onClick={() => setModalTitle(null)} className="text-[#8b95a6] hover:text-white p-1">
                <X size={18} />
              </button>
            </div>
            <div className="p-4 max-h-80 overflow-y-auto space-y-2 font-mono text-xs">
              {modalItems.map((item, i) => (
                <div key={i} className="p-3 bg-[#1a2235] border border-[#2d3748] rounded flex flex-col gap-1">
                  <div className="font-medium text-white flex items-center gap-2">
                    <span className="text-amber-400">📁</span> {item.name}
                  </div>
                  {item.subtitle && <div className="text-[#8b95a6] text-[11px]">{item.subtitle}</div>}
                  {item.details && <div className="text-emerald-400 text-[11px]">{item.details}</div>}
                </div>
              ))}
            </div>
            <div className="p-3 border-t border-[#2d3748] bg-[#060912] flex justify-end">
              <Button variant="secondary" onClick={() => setModalTitle(null)} className="text-xs py-1.5 px-3">
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
