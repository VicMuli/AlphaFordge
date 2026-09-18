import React, { useState, useEffect } from 'react';
import { Card, SectionHeader, Button } from './ui';
import { Save, RefreshCw, CheckCircle2, RotateCcw } from 'lucide-react';

export default function Settings({ config, setConfig }: { config: any, setConfig: any }) {
  const [localConfig, setLocalConfig] = useState(config);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  const handleChange = (k: string, v: string) => {
    setLocalConfig((prev: any) => ({ ...prev, [k]: v }));
    setStatusMessage(null);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localConfig)
      });
      if (res.ok) {
        setConfig(localConfig);
        setStatusMessage('✔ Config saved to config.json');
        setTimeout(() => setStatusMessage(null), 5000);
      } else {
        setStatusMessage('✖ Failed to save config');
      }
    } catch (e: any) {
      setStatusMessage(`✖ Error: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleApplyToScripts = async () => {
    setIsApplying(true);
    try {
      const res = await fetch('/api/apply-scripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localConfig)
      });
      if (res.ok) {
        setConfig(localConfig);
        setStatusMessage('✔ Configuration applied to Python scripts & saved to config.json');
        setTimeout(() => setStatusMessage(null), 6000);
      } else {
        setStatusMessage('✖ Failed to apply to scripts');
      }
    } catch (e: any) {
      setStatusMessage(`✖ Error: ${e.message}`);
    } finally {
      setIsApplying(false);
    }
  };

  const handleResetDefaults = () => {
    if (confirm('Reset settings to standard defaults?')) {
      const defaults = {
        terminal_path: "C:\\Users\\HP\\AppData\\Roaming\\MetaTrader\\terminal64.exe",
        terminal_data_dir: "C:\\Users\\HP\\AppData\\Roaming\\MetaQuotes\\Terminal\\CDE1ED2F37049DA2E508A3C44B675D09",
        active_ea: "TRB",
        expert: "TRB V2.0.ex5",
        symbol: "USDJPY Dukascopy",
        symbol_key: "USDPY",
        period: "M15",
        pip_size: "0.001",
        train_from: "2013.01.01",
        train_to: "2022.01.01",
        val_from: "2022.01.01",
        val_to: "2024.01.01",
        holdout_from: "2024.01.01",
        holdout_to: "2026.07.03",
        deposit: "2500",
        currency: "USD",
        leverage: "1:100",
        login: "52909674",
        password: "3F!@4rwo7wc02f",
        server: "ICMarketsKE-Demo",
        top_n_train: "20",
        opt_timeout: "21600",
        single_test_timeout: "100",
        wf_window_months: "12",
        wf_step_months: "6",
        mc_simulations: "5000",
        mc_max_dd: "10.0",
        mc_daily_dd: "5.0",
        mc_phase1_target: "8.0",
        mc_phase2_target: "5.0",
        work_dir: "C:\\Users\\HP\\Desktop\\MT5 runner\\optimization_runs",
        quant_name: "TRB",
        research_dir: "C:\\Users\\HP\\Desktop\\MT5 runner\\researched_strategies",
        strategies_dir: "C:\\Users\\HP\\Desktop\\MT5 runner\\strategies"
      };
      setLocalConfig(defaults);
      setStatusMessage('Defaults restored. Click Save Config to commit.');
    }
  };

  const GROUPS = [
    {
      title: "MT5 Terminal",
      fields: [
        { label: "Terminal Path (.exe)", key: "terminal_path", span: 2 },
        { label: "Terminal Data Dir", key: "terminal_data_dir", span: 2 },
        { label: "Login", key: "login" },
        { label: "Password", key: "password", type: "password" },
        { label: "Server", key: "server" },
      ]
    },
    {
      title: "EA & Symbol",
      fields: [
        { label: "Active EA Name", key: "active_ea" },
        { label: "Expert Filename (.ex5)", key: "expert" },
        { label: "Symbol", key: "symbol" },
        { label: "Symbol Key", key: "symbol_key" },
        { label: "Period", key: "period" },
        { label: "Pip Size", key: "pip_size" },
      ]
    },
    {
      title: "Date Ranges",
      fields: [
        { label: "Train From", key: "train_from" },
        { label: "Train To", key: "train_to" },
        { label: "Val From", key: "val_from" },
        { label: "Val To", key: "val_to" },
        { label: "Holdout From", key: "holdout_from" },
        { label: "Holdout To", key: "holdout_to" },
      ]
    },
    {
      title: "Account & Pipeline",
      fields: [
        { label: "Deposit ($)", key: "deposit" },
        { label: "Currency", key: "currency" },
        { label: "Leverage", key: "leverage" },
        { label: "Top N Train Passes", key: "top_n_train" },
        { label: "Opt Timeout (s)", key: "opt_timeout" },
        { label: "Single Test Timeout (s)", key: "single_test_timeout" },
      ]
    },
    {
      title: "Walk Forward & Monte Carlo",
      fields: [
        { label: "WF Window Months", key: "wf_window_months" },
        { label: "WF Step Months", key: "wf_step_months" },
        { label: "MC Simulations", key: "mc_simulations" },
        { label: "MC Max DD %", key: "mc_max_dd" },
        { label: "MC Daily DD %", key: "mc_daily_dd" },
        { label: "MC Phase 1 Target %", key: "mc_phase1_target" },
        { label: "MC Phase 2 Target %", key: "mc_phase2_target" },
      ]
    },
    {
      title: "Folder Paths",
      fields: [
        { label: "Work Dir", key: "work_dir", span: 2 },
        { label: "Research Dir", key: "research_dir", span: 2 },
        { label: "Strategies Dir", key: "strategies_dir", span: 2 },
        { label: "Quant Name Prefix", key: "quant_name" },
      ]
    },
  ];

  return (
    <div className="flex flex-col h-full space-y-4 pb-12">
      <SectionHeader 
        title="🔧 Settings" 
        subtitle="Configure AlphaForge — changes are saved to config.json and can be applied to scripts" 
      />

      {/* Top action bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-[#111827] border border-[#2d3748] rounded-xl">
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleSave} disabled={isSaving}>
            <Save size={16} /> Save Config
          </Button>
          <Button variant="blue" onClick={handleApplyToScripts} disabled={isApplying}>
            <RefreshCw size={16} className={isApplying ? "animate-spin" : ""} /> 🔁 Apply to Scripts
          </Button>
          <Button variant="secondary" onClick={handleResetDefaults}>
            <RotateCcw size={16} /> Reset Defaults
          </Button>
        </div>

        {statusMessage && (
          <div className={`text-xs font-mono px-3 py-1.5 rounded-lg border ${
            statusMessage.includes('✔') 
              ? 'bg-emerald-950/50 border-emerald-600/50 text-emerald-400' 
              : 'bg-amber-950/50 border-amber-600/50 text-amber-300'
          }`}>
            {statusMessage}
          </div>
        )}
      </div>

      {/* Settings Grid */}
      <div className="space-y-6">
        {GROUPS.map((group, gIdx) => (
          <Card key={gIdx} className="p-5">
            <h3 className="text-sm font-bold text-[#f59e0b] uppercase tracking-wider mb-4 pb-2 border-b border-[#2d3748]">
              {group.title}
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {group.fields.map((field: any, fIdx: number) => {
                const isDoubleSpan = field.span === 2;
                return (
                  <div 
                    key={fIdx} 
                    className={`flex flex-col gap-1.5 ${isDoubleSpan ? 'md:col-span-2' : ''}`}
                  >
                    <label className="text-[11px] text-[#8b95a6] font-medium">
                      {field.label}
                    </label>
                    <input
                      type={field.type || "text"}
                      value={localConfig[field.key] !== undefined ? localConfig[field.key] : ""}
                      onChange={e => handleChange(field.key, e.target.value)}
                      className="bg-[#1a2235] border border-[#2d3748] text-white rounded-lg px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-[#f59e0b] focus:ring-1 focus:ring-[#f59e0b]"
                    />
                  </div>
                );
              })}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
