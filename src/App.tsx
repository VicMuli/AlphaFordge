import { useState, useEffect } from 'react';
import { 
  Home, 
  Microscope, 
  Settings as SettingsIcon, 
  TrendingUp, 
  ClipboardList, 
  Package, 
  FolderTree, 
  Wrench,
  Zap,
  Terminal,
  Square,
  GitBranch,
  Laptop,
  CheckCircle2,
  X
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

// Components
import Dashboard from './components/Dashboard';
import Research from './components/Research';
import Optimize from './components/Optimize';
import WalkForward from './components/WalkForward';
import FullBacktest from './components/FullBacktest';
import Portfolio from './components/Portfolio';
import Strategies from './components/Strategies';
import Settings from './components/Settings';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: Home, prefix: '🏠' },
  { id: 'research', label: 'Research', icon: Microscope, prefix: '🔬' },
  { id: 'optimize', label: 'Optimize', icon: SettingsIcon, prefix: '⚙' },
  { id: 'walkforward', label: 'Walk Forward', icon: TrendingUp, prefix: '📈' },
  { id: 'fullbacktest', label: 'Full Backtest', icon: ClipboardList, prefix: '📋' },
  { id: 'portfolio', label: 'Portfolio', icon: Package, prefix: '📦' },
  { id: 'strategies', label: 'Strategies', icon: FolderTree, prefix: '🗂' },
  { id: 'settings', label: 'Settings', icon: Wrench, prefix: '🔧' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [config, setConfig] = useState<any>({});
  const [serverStatus, setServerStatus] = useState<{ isRunning: boolean; script: string | null }>({
    isRunning: false,
    script: null,
  });
  const [showSyncModal, setShowSyncModal] = useState(false);

  // Poll status periodically
  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(data => setConfig(data))
      .catch(console.error);

    const checkStatus = async () => {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const data = await res.json();
          setServerStatus(data);
        }
      } catch (err) {
        // silent
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleStopActiveProcess = async () => {
    try {
      await fetch('/api/stop', { method: 'POST' });
      setServerStatus({ isRunning: false, script: null });
    } catch (e) {
      console.error(e);
    }
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard config={config} />;
      case 'research': return <Research config={config} />;
      case 'optimize': return <Optimize config={config} onNavigateToSettings={() => setActiveTab('settings')} />;
      case 'walkforward': return <WalkForward config={config} />;
      case 'fullbacktest': return <FullBacktest config={config} />;
      case 'portfolio': return <Portfolio config={config} />;
      case 'strategies': return <Strategies config={config} />;
      case 'settings': return <Settings config={config} setConfig={setConfig} />;
      default: return <Dashboard config={config} />;
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#0a0e1a] text-[#f9fafb] font-sans overflow-hidden">
      {/* Sidebar matching app.py */}
      <div className="w-64 bg-[#060912] border-r border-[#2d3748] flex flex-col justify-between shrink-0">
        <div>
          {/* Brand Header */}
          <div className="p-5 border-b border-[#1f2937]">
            <div className="flex items-center gap-2">
              <Zap className="text-[#f59e0b] fill-[#f59e0b]" size={22} />
              <h1 className="text-lg font-extrabold tracking-wider text-white">AlphaForge</h1>
            </div>
            <p className="text-[11px] text-[#8b95a6] mt-0.5 pl-7 font-medium">MT5 Quant Platform</p>
            <div className="mt-3 inline-block px-2 py-0.5 bg-[#1f2937] text-[#8b95a6] text-[10px] font-mono rounded">
              v1.0 | app.py preview
            </div>
          </div>

          {/* Navigation */}
          <nav className="p-3 space-y-1 mt-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all ${
                    isActive 
                      ? 'bg-[#1a2540] text-[#f59e0b] border border-[#f59e0b]/30 shadow-xs' 
                      : 'text-[#8b95a6] hover:bg-[#1a2235] hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon size={16} className={isActive ? 'text-[#f59e0b]' : 'text-[#8b95a6]'} />
                    <span>{item.label}</span>
                  </div>
                  {isActive && <div className="w-1.5 h-1.5 rounded-full bg-[#f59e0b]"></div>}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Local PC & Git helper card */}
        <div className="p-3 border-t border-[#1f2937] bg-[#0a0e1a]/80">
          <button 
            onClick={() => setShowSyncModal(true)}
            className="w-full p-2.5 rounded-lg bg-[#111827] border border-[#2d3748] hover:border-[#f59e0b] transition-colors text-left flex items-center gap-2.5"
          >
            <Laptop size={16} className="text-[#f59e0b] shrink-0" />
            <div className="overflow-hidden">
              <div className="text-[11px] font-semibold text-white truncate">Local MT5 &amp; Git Sync</div>
              <div className="text-[10px] text-[#8b95a6] truncate">Run: python app.py</div>
            </div>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col bg-[#111827] overflow-hidden">
        {/* Top bar with active process status */}
        <div className="h-12 bg-[#060912] border-b border-[#2d3748] px-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-[#8b95a6]">Active EA:</span>
            <span className="text-[#f59e0b] font-bold">{config.active_ea || 'TRB'}</span>
            <span className="text-[#2d3748]">|</span>
            <span className="text-[#8b95a6]">Symbol:</span>
            <span className="text-white font-medium">{config.symbol || 'USDJPY Dukascopy'}</span>
            <span className="text-[#2d3748]">|</span>
            <span className="text-[#8b95a6]">Period:</span>
            <span className="text-white font-medium">{config.period || 'M15'}</span>
          </div>

          <div className="flex items-center gap-3">
            {serverStatus.isRunning && (
              <div className="flex items-center gap-2 bg-amber-950/60 border border-amber-600/40 px-2.5 py-1 rounded text-xs">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                </span>
                <span className="text-amber-300 font-mono text-[11px]">
                  Running: {serverStatus.script}
                </span>
                <button
                  onClick={handleStopActiveProcess}
                  className="ml-1 p-0.5 text-red-400 hover:text-red-300"
                  title="Stop Process"
                >
                  <Square size={12} />
                </button>
              </div>
            )}

            <button
              onClick={() => setShowSyncModal(true)}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-[#8b95a6] hover:text-white bg-[#1a2235] rounded border border-[#2d3748] transition-colors"
            >
              <GitBranch size={13} className="text-[#f59e0b]" />
              <span>Git Sync Info</span>
            </button>
          </div>
        </div>

        {/* Viewport */}
        <div className="flex-1 overflow-y-auto p-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.15 }}
              className="min-h-full max-w-7xl mx-auto"
            >
              {renderContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Git Sync & Local MT5 Modal */}
      {showSyncModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111827] border border-[#2d3748] rounded-xl w-full max-w-xl overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-[#2d3748] bg-[#060912]">
              <div className="flex items-center gap-2 font-bold text-white text-sm">
                <Laptop size={18} className="text-[#f59e0b]" />
                Local Windows MT5 &amp; Git Sync Workflow
              </div>
              <button 
                onClick={() => setShowSyncModal(false)}
                className="text-[#8b95a6] hover:text-white p-1"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs text-[#8b95a6] leading-relaxed">
              <div className="p-3 bg-[#1a2235] border border-[#2d3748] rounded-lg text-white">
                <div className="font-semibold text-[#f59e0b] mb-1">Architecture Overview:</div>
                This web preview showcases the exact functionality, tabs, and layout of your desktop <span className="font-mono text-amber-300">app.py</span> application. Both interfaces read from the same <span className="font-mono text-amber-300">config.json</span> and execute the same backend Python scripts.
              </div>

              <div>
                <div className="font-semibold text-white mb-1.5 flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-[#f59e0b] text-[#060912] flex items-center justify-center text-[10px] font-bold">1</span>
                  Pulling changes to your local Windows PC:
                </div>
                <div className="bg-[#060912] border border-[#2d3748] rounded p-2.5 font-mono text-emerald-400 select-all">
                  git pull origin main
                </div>
              </div>

              <div>
                <div className="font-semibold text-white mb-1.5 flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-[#f59e0b] text-[#060912] flex items-center justify-center text-[10px] font-bold">2</span>
                  Running MT5 desktop interface on Windows:
                </div>
                <div className="bg-[#060912] border border-[#2d3748] rounded p-2.5 font-mono text-emerald-400 select-all">
                  python app.py
                </div>
                <p className="mt-1 text-[11px]">
                  When you run <span className="text-white font-mono">python app.py</span> locally on Windows, it will launch the native desktop GUI and connect directly to your installed MetaTrader 5 terminal!
                </p>
              </div>

              <div>
                <div className="font-semibold text-white mb-1.5 flex items-center gap-1.5">
                  <span className="w-4 h-4 rounded-full bg-[#f59e0b] text-[#060912] flex items-center justify-center text-[10px] font-bold">3</span>
                  Saving and applying settings:
                </div>
                <p className="text-[11px]">
                  Use the <span className="text-white font-semibold">Settings</span> tab in either interface. Clicking <span className="text-amber-400 font-semibold">Save Config</span> updates <span className="text-white font-mono">config.json</span>, and clicking <span className="text-blue-400 font-semibold">🔁 Apply to Scripts</span> automatically patches your Python pipeline scripts.
                </p>
              </div>
            </div>

            <div className="p-3 border-t border-[#2d3748] bg-[#060912] flex justify-end">
              <button
                onClick={() => setShowSyncModal(false)}
                className="px-4 py-2 bg-[#f59e0b] hover:bg-[#d97706] text-[#0a0e1a] rounded-lg font-bold text-xs"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
