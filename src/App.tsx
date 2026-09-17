import { useState, useEffect } from 'react';
import { Home, Microscope, Settings as SettingsIcon, TrendingUp, ClipboardList, Package, FolderTree, Wrench } from 'lucide-react';
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
  { id: 'dashboard', label: 'Dashboard', icon: Home },
  { id: 'research', label: 'Research', icon: Microscope },
  { id: 'optimize', label: 'Optimize', icon: SettingsIcon },
  { id: 'walkforward', label: 'Walk Forward', icon: TrendingUp },
  { id: 'fullbacktest', label: 'Full Backtest', icon: ClipboardList },
  { id: 'portfolio', label: 'Portfolio', icon: Package },
  { id: 'strategies', label: 'Strategies', icon: FolderTree },
  { id: 'settings', label: 'Settings', icon: Wrench },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [config, setConfig] = useState<any>({});

  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(data => setConfig(data))
      .catch(console.error);
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard config={config} />;
      case 'research': return <Research config={config} />;
      case 'optimize': return <Optimize config={config} />;
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
      {/* Sidebar */}
      <div className="w-64 bg-[#060912] border-r border-[#2d3748] flex flex-col">
        <div className="p-6">
          <h1 className="text-xl font-bold tracking-wider text-white">AlphaForge v1.0</h1>
          <p className="text-xs text-[#8b95a6] mt-1">MT5 Quant Optimizer</p>
        </div>
        <nav className="flex-1 px-4 space-y-2 mt-4 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive 
                    ? 'bg-[#1a2540] text-[#f59e0b]' 
                    : 'text-[#8b95a6] hover:bg-[#253352] hover:text-white'
                }`}
              >
                <Icon size={20} />
                <span className="font-medium">{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-[#111827] overflow-y-auto relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="min-h-full p-8"
          >
            {renderContent()}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
