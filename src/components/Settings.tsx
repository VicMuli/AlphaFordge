import React, { useState } from 'react';
import { Card, SectionHeader, Button } from './ui';
import { Save, CheckCircle2 } from 'lucide-react';

export default function Settings({ config, setConfig }: { config: any, setConfig: any }) {
  const [localConfig, setLocalConfig] = useState(config);
  const [isSaved, setIsSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Sync if parent config updates
  React.useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  const handleChange = (k: string, v: string) => {
    setLocalConfig({ ...localConfig, [k]: v });
    setIsSaved(false);
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
        setIsSaved(true);
        setTimeout(() => setIsSaved(false), 4000);
      } else {
        alert('Failed to save settings');
      }
    } catch (e: any) {
      alert(`Error saving settings: ${e.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const SETTINGS_GROUPS = [
    {
      title: "Terminal",
      fields: [
        { label: "Terminal Path", key: "terminal_path", width: "w-[400px]" },
        { label: "Data Dir", key: "terminal_data_dir", width: "w-[400px]" }
      ]
    },
    {
      title: "Account",
      fields: [
        { label: "Login ID", key: "login" },
        { label: "Password", key: "password", type: "password" },
        { label: "Server", key: "server" },
        { label: "Deposit", key: "deposit" },
        { label: "Currency", key: "currency" },
        { label: "Leverage", key: "leverage" }
      ]
    },
    {
      title: "Strategy",
      fields: [
        { label: "Expert File", key: "expert" },
        { label: "Active EA Code", key: "active_ea" },
        { label: "Symbol", key: "symbol" },
        { label: "Period", key: "period" }
      ]
    },
    {
      title: "Dates",
      fields: [
        { label: "Train From", key: "train_from" },
        { label: "Train To", key: "train_to" },
        { label: "Val From", key: "val_from" },
        { label: "Val To", key: "val_to" },
        { label: "Holdout From", key: "holdout_from" },
        { label: "Holdout To", key: "holdout_to" }
      ]
    },
    {
      title: "Monte Carlo",
      fields: [
        { label: "Simulations", key: "mc_simulations" },
        { label: "Max DD %", key: "mc_max_dd" },
        { label: "Daily DD %", key: "mc_daily_dd" },
        { label: "Phase 1 Target", key: "mc_phase1_target" },
        { label: "Phase 2 Target", key: "mc_phase2_target" }
      ]
    }
  ];

  return (
    <div className="flex flex-col h-full overflow-y-auto pb-12">
      <SectionHeader title="🔧 Settings & Configuration" subtitle="Global parameters for AlphaForge pipelines" />
      
      <div className="flex justify-end items-center gap-4 mb-6 sticky top-0 z-10 bg-[#111827] py-4 border-b border-[#2d3748]">
        {isSaved && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium">
            <CheckCircle2 size={18} />
            <span>Saved to config.json</span>
          </div>
        )}
        <Button onClick={handleSave} disabled={isSaving} className="shadow-lg shadow-black/50">
          <Save size={18} /> {isSaving ? 'Saving...' : 'Save All Settings'}
        </Button>
      </div>

      <div className="grid gap-6 max-w-4xl">
        {SETTINGS_GROUPS.map(group => (
          <Card key={group.title}>
            <h3 className="text-lg font-medium text-[#f59e0b] mb-6">{group.title}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
              {group.fields.map(f => (
                <div key={f.key} className={f.width === "w-[400px]" ? "col-span-1 md:col-span-2 flex items-center" : "flex items-center"}>
                  <label className="text-[#8b95a6] w-32 text-sm text-right shrink-0 mr-4">{f.label}</label>
                  <input
                    type={f.type || "text"}
                    value={localConfig[f.key] || ''}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                    className="bg-[#1a2235] border border-[#2d3748] text-[#f9fafb] rounded-lg px-3 py-2 flex-1 focus:outline-none focus:border-[#f59e0b] focus:ring-1 focus:ring-[#f59e0b]"
                  />
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
