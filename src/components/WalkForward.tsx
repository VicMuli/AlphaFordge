import { useState, useEffect } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { Play, FolderOpen, RefreshCw, Square, Trash2 } from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';

export default function WalkForward({ config }: { config: any }) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRun, setSelectedRun] = useState<string>('');
  const [candidates, setCandidates] = useState<string[]>([]);
  const [selectedCand, setSelectedCand] = useState<string>('');
  const [windowMonths, setWindowMonths] = useState<string>(config.wf_window_months || '12');
  const [stepMonths, setStepMonths] = useState<string>(config.wf_step_months || '6');
  const [loading, setLoading] = useState(false);

  const fetchLists = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/workspace');
      if (res.ok) {
        const data = await res.json();
        const runList = data.runsDetailed || [];
        setRuns(runList);
        if (runList.length > 0) {
          const first = runList[0];
          setSelectedRun(first.name);
          setCandidates(first.candidates || []);
          if (first.candidates && first.candidates.length > 0) {
            setSelectedCand(first.candidates[0]);
          } else {
            setSelectedCand('');
          }
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLists();
  }, []);

  const handleRunChange = (runName: string) => {
    setSelectedRun(runName);
    const found = runs.find(r => r.name === runName);
    const cands = found ? found.candidates : [];
    setCandidates(cands || []);
    if (cands && cands.length > 0) {
      setSelectedCand(cands[0]);
    } else {
      setSelectedCand('');
    }
  };

  const handleRun = () => {
    runScript('run_wf_pipeline.py', {
      patch: {
        patches: {
          TARGET_RUN_DIR: selectedRun || 'latest',
          TARGET_CANDIDATE: selectedCand || 'cand_001',
          WF_WINDOW_MONTHS: Number(windowMonths) || 12,
          WF_STEP_MONTHS: Number(stepMonths) || 6,
        }
      }
    });
  };

  return (
    <div className="flex flex-col h-full space-y-4">
      <SectionHeader 
        title="📈 Walk Forward Stability Testing" 
        subtitle="Test a candidate across rolling time windows — run one at a time" 
      />
      
      <Card className="p-5">
        <div className="grid gap-4 max-w-2xl mb-6">
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Run Directory</label>
            <div className="flex-1 flex gap-2">
              <select 
                value={selectedRun} 
                onChange={e => handleRunChange(e.target.value)}
                className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
              >
                {runs.length > 0 ? (
                  runs.map(r => (
                    <option key={r.name} value={r.name}>
                      {r.name} ({r.passedCandidates} passed)
                    </option>
                  ))
                ) : (
                  <option value="latest">latest (or select when runs exist)</option>
                )}
              </select>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Candidate</label>
            <select 
              value={selectedCand} 
              onChange={e => setSelectedCand(e.target.value)}
              className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 text-sm focus:outline-none focus:border-[#f59e0b]"
            >
              {candidates.length > 0 ? (
                candidates.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))
              ) : (
                <option value="cand_001">cand_001 (default)</option>
              )}
            </select>
          </div>

          <div className="flex items-center gap-4">
            <label className="text-[#8b95a6] w-36 text-right text-xs font-semibold">Window / Step (months)</label>
            <div className="flex items-center gap-2">
              <input 
                type="text" 
                value={windowMonths} 
                onChange={e => setWindowMonths(e.target.value)}
                className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-1.5 w-16 text-center text-sm font-mono" 
              />
              <span className="text-[#8b95a6]">/</span>
              <input 
                type="text" 
                value={stepMonths} 
                onChange={e => setStepMonths(e.target.value)}
                className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-1.5 w-16 text-center text-sm font-mono" 
              />
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-4 border-t border-[#2d3748]">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={16} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleRun}>
              <Play size={16} /> Run WF Testing
            </Button>
          )}
          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={16} /> Clear Log
          </Button>
          <Button 
            variant="secondary" 
            onClick={() => alert(`Candidate directory:\n${config.work_dir || "optimization_runs"}/${selectedRun || "latest"}/passed_candidates/${selectedCand || "cand_001"}`)}
          >
            <FolderOpen size={16} /> Open Candidate Folder
          </Button>
          <Button variant="secondary" onClick={fetchLists} disabled={loading}>
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} /> Refresh Lists
          </Button>
        </div>
      </Card>

      <div className="flex-1 min-h-[300px] flex flex-col">
        <LogViewer logs={logs} title={`WF Testing Output ${isRunning ? '(Executing...)' : ''}`} />
      </div>
    </div>
  );
}
