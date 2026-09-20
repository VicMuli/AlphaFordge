import { useState, useEffect, useMemo } from 'react';
import { Card, SectionHeader, Button, LogViewer } from './ui';
import { 
  Play, 
  Settings as SettingsIcon, 
  FolderOpen, 
  Square, 
  Trash2, 
  Save, 
  RotateCcw, 
  Plus, 
  Search, 
  Sliders, 
  CheckCircle2, 
  Lock, 
  Zap, 
  Layers, 
  Filter, 
  Clock, 
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Info,
  Target,
  Award,
  TrendingUp,
  Activity,
  Percent,
  Copy,
  Sparkles,
  Scale,
  ShieldCheck,
  DollarSign
} from 'lucide-react';
import { useScriptRunner } from '../useScriptRunner';
import { 
  StrategyParam, 
  IndicatorDefinition, 
  AllQualificationCriteria, 
  PhaseQualificationCriteria 
} from '../types';
import { 
  getDefaultConfigForEa, 
  buildOptimizationConfig 
} from '../constants/optimizationParams';

export const DEFAULT_QUALIFICATION_CRITERIA: AllQualificationCriteria = {
  train: {
    min_profit_gain_pct: 30.0,
    max_drawdown_pct: 20.0,
    min_avg_trades_month: 1.0,
    min_sharpe_ratio: 0.50,
    min_ret_dd_ratio: 1.30,
    min_profit_factor: 1.10,
    min_net_profit: 0.0,
    min_total_trades: 0,
    min_win_rate_pct: 0.0,
  },
  val: {
    min_profit_gain_pct: 15.0,
    max_drawdown_pct: 20.0,
    min_avg_trades_month: 1.0,
    min_sharpe_ratio: 0.50,
    min_ret_dd_ratio: 1.00,
    min_profit_factor: 1.00,
    min_net_profit: 0.0,
    min_total_trades: 0,
    min_win_rate_pct: 0.0,
  },
  holdout: {
    min_profit_gain_pct: 15.0,
    max_drawdown_pct: 20.0,
    min_avg_trades_month: 1.0,
    min_sharpe_ratio: 0.50,
    min_ret_dd_ratio: 1.00,
    min_profit_factor: 1.00,
    min_net_profit: 0.0,
    min_total_trades: 0,
    min_win_rate_pct: 0.0,
  },
};

export const CRITERIA_METRICS: {
  key: keyof PhaseQualificationCriteria;
  label: string;
  unit: string;
  step: number;
  min: number;
  max?: number;
  description: string;
  badge: string;
  category: 'returns' | 'risk' | 'quality' | 'frequency';
}[] = [
  {
    key: 'min_profit_gain_pct',
    label: 'Net Profit Gain %',
    unit: '%',
    step: 1.0,
    min: 0,
    max: 500,
    description: 'Minimum % return over starting capital during the testing window',
    badge: 'Profit',
    category: 'returns',
  },
  {
    key: 'max_drawdown_pct',
    label: 'Max Drawdown %',
    unit: '%',
    step: 0.5,
    min: 1,
    max: 100,
    description: 'Maximum allowable balance/equity drawdown percentage (lower is stricter)',
    badge: 'Risk',
    category: 'risk',
  },
  {
    key: 'min_profit_factor',
    label: 'Profit Factor (PF)',
    unit: 'ratio',
    step: 0.05,
    min: 0.5,
    max: 20,
    description: 'Gross win dollars divided by gross loss dollars (1.0 = break-even)',
    badge: 'PF',
    category: 'quality',
  },
  {
    key: 'min_sharpe_ratio',
    label: 'Sharpe Ratio',
    unit: 'ratio',
    step: 0.05,
    min: 0,
    max: 10,
    description: 'Annualized risk-adjusted excess return per unit of volatility',
    badge: 'Sharpe',
    category: 'quality',
  },
  {
    key: 'min_ret_dd_ratio',
    label: 'Return / DD Ratio',
    unit: 'ratio',
    step: 0.1,
    min: 0,
    max: 50,
    description: 'Recovery factor: Net profit dollars divided by max drawdown dollars',
    badge: 'Ret/DD',
    category: 'quality',
  },
  {
    key: 'min_avg_trades_month',
    label: 'Avg Trades / Month',
    unit: 'tr/mo',
    step: 0.1,
    min: 0,
    max: 200,
    description: 'Minimum monthly trade execution density to ensure statistical validity',
    badge: 'Activity',
    category: 'frequency',
  },
  {
    key: 'min_net_profit',
    label: 'Net Profit Floor ($)',
    unit: '$',
    step: 500,
    min: 0,
    description: 'Absolute dollar net profit threshold ($0 = candidate must end positive)',
    badge: 'Dollars',
    category: 'returns',
  },
  {
    key: 'min_total_trades',
    label: 'Min Total Trades',
    unit: 'trades',
    step: 5,
    min: 0,
    max: 5000,
    description: 'Absolute minimum executed trade count (0 = disabled)',
    badge: 'Volume',
    category: 'frequency',
  },
  {
    key: 'min_win_rate_pct',
    label: 'Min Win Rate %',
    unit: '%',
    step: 1.0,
    min: 0,
    max: 100,
    description: 'Minimum % of closed trades that were profitable (0 = disabled)',
    badge: 'Win Rate',
    category: 'quality',
  },
];

export default function Optimize({ 
  config, 
  onNavigateToSettings 
}: { 
  config: any; 
  onNavigateToSettings?: () => void; 
}) {
  const { logs, isRunning, runScript, stopScript, clearLogs } = useScriptRunner();
  const [currentPhase, setCurrentPhase] = useState<number>(0);

  // Active strategy (TRB vs ORB)
  const activeEa = ((config?.active_ea || 'TRB') as string).toUpperCase();

  // State for parameters and indicators
  const [params, setParams] = useState<StrategyParam[]>([]);
  const [indicators, setIndicators] = useState<IndicatorDefinition[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [showIndicatorsGrid, setShowIndicatorsGrid] = useState<boolean>(true);

  // Form state for adding custom parameter
  const [newParam, setNewParam] = useState<Partial<StrategyParam>>({
    name: '',
    label: '',
    category: 'custom',
    mode: 'fixed',
    fixedValue: 1.0,
    range: { start: 1.0, step: 0.5, stop: 3.0 },
    description: '',
  });

  // Candidate Qualification Gates State (Train, Val, Holdout)
  const [criteria, setCriteria] = useState<AllQualificationCriteria>(DEFAULT_QUALIFICATION_CRITERIA);
  const [criteriaSaveStatus, setCriteriaSaveStatus] = useState<string | null>(null);
  const [criteriaViewMode, setCriteriaViewMode] = useState<'matrix' | 'train' | 'val' | 'holdout'>('matrix');
  const [showCriteriaCard, setShowCriteriaCard] = useState<boolean>(true);
  const [hasUnsavedCriteria, setHasUnsavedCriteria] = useState<boolean>(false);

  // Load qualification criteria from backend config.json
  useEffect(() => {
    let isMounted = true;
    const fetchCriteria = async () => {
      try {
        const res = await fetch('/api/qualification-criteria');
        if (res.ok && isMounted) {
          const json = await res.json();
          if (json.criteria) {
            setCriteria({
              train: { ...DEFAULT_QUALIFICATION_CRITERIA.train, ...json.criteria.train },
              val: { ...DEFAULT_QUALIFICATION_CRITERIA.val, ...json.criteria.val },
              holdout: { ...DEFAULT_QUALIFICATION_CRITERIA.holdout, ...json.criteria.holdout },
            });
          }
        }
      } catch (e) {
        console.error('Failed to fetch qualification criteria', e);
      }
    };
    fetchCriteria();
    return () => { isMounted = false; };
  }, []);

  const handleCriteriaChange = (
    phase: 'train' | 'val' | 'holdout',
    field: keyof PhaseQualificationCriteria,
    val: number
  ) => {
    setCriteria(prev => ({
      ...prev,
      [phase]: {
        ...prev[phase],
        [field]: isNaN(val) ? 0 : val,
      },
    }));
    setHasUnsavedCriteria(true);
    setCriteriaSaveStatus(null);
  };

  const handleSaveCriteria = async () => {
    try {
      setCriteriaSaveStatus('saving');
      const res = await fetch('/api/qualification-criteria', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ criteria }),
      });
      if (res.ok) {
        setCriteriaSaveStatus('saved');
        setHasUnsavedCriteria(false);
        setTimeout(() => setCriteriaSaveStatus(null), 3500);
      } else {
        setCriteriaSaveStatus('error');
      }
    } catch (e) {
      console.error('Failed to save qualification criteria', e);
      setCriteriaSaveStatus('error');
    }
  };

  const applyCriteriaPreset = (presetKey: 'balanced' | 'prop' | 'hft' | 'relaxed') => {
    if (presetKey === 'balanced') {
      setCriteria(DEFAULT_QUALIFICATION_CRITERIA);
    } else if (presetKey === 'prop') {
      setCriteria({
        train: {
          min_profit_gain_pct: 20.0,
          max_drawdown_pct: 8.0,
          min_avg_trades_month: 2.0,
          min_sharpe_ratio: 0.90,
          min_ret_dd_ratio: 2.50,
          min_profit_factor: 1.35,
          min_net_profit: 0.0,
          min_total_trades: 0,
          min_win_rate_pct: 45.0,
        },
        val: {
          min_profit_gain_pct: 10.0,
          max_drawdown_pct: 8.0,
          min_avg_trades_month: 1.5,
          min_sharpe_ratio: 0.75,
          min_ret_dd_ratio: 1.50,
          min_profit_factor: 1.20,
          min_net_profit: 0.0,
          min_total_trades: 0,
          min_win_rate_pct: 40.0,
        },
        holdout: {
          min_profit_gain_pct: 10.0,
          max_drawdown_pct: 8.0,
          min_avg_trades_month: 1.5,
          min_sharpe_ratio: 0.75,
          min_ret_dd_ratio: 1.50,
          min_profit_factor: 1.20,
          min_net_profit: 0.0,
          min_total_trades: 0,
          min_win_rate_pct: 40.0,
        },
      });
    } else if (presetKey === 'hft') {
      setCriteria({
        train: {
          min_profit_gain_pct: 25.0,
          max_drawdown_pct: 15.0,
          min_avg_trades_month: 4.0,
          min_sharpe_ratio: 0.60,
          min_ret_dd_ratio: 1.50,
          min_profit_factor: 1.15,
          min_net_profit: 0.0,
          min_total_trades: 50,
          min_win_rate_pct: 0.0,
        },
        val: {
          min_profit_gain_pct: 12.0,
          max_drawdown_pct: 15.0,
          min_avg_trades_month: 3.5,
          min_sharpe_ratio: 0.50,
          min_ret_dd_ratio: 1.10,
          min_profit_factor: 1.05,
          min_net_profit: 0.0,
          min_total_trades: 25,
          min_win_rate_pct: 0.0,
        },
        holdout: {
          min_profit_gain_pct: 12.0,
          max_drawdown_pct: 15.0,
          min_avg_trades_month: 3.5,
          min_sharpe_ratio: 0.50,
          min_ret_dd_ratio: 1.10,
          min_profit_factor: 1.05,
          min_net_profit: 0.0,
          min_total_trades: 25,
          min_win_rate_pct: 0.0,
        },
      });
    } else if (presetKey === 'relaxed') {
      setCriteria({
        train: {
          min_profit_gain_pct: 10.0,
          max_drawdown_pct: 30.0,
          min_avg_trades_month: 0.5,
          min_sharpe_ratio: 0.25,
          min_ret_dd_ratio: 0.75,
          min_profit_factor: 1.05,
          min_net_profit: 0.0,
          min_total_trades: 0,
          min_win_rate_pct: 0.0,
        },
        val: {
          min_profit_gain_pct: 5.0,
          max_drawdown_pct: 30.0,
          min_avg_trades_month: 0.5,
          min_sharpe_ratio: 0.20,
          min_ret_dd_ratio: 0.50,
          min_profit_factor: 1.00,
          min_net_profit: 0.0,
          min_total_trades: 0,
          min_win_rate_pct: 0.0,
        },
        holdout: {
          min_profit_gain_pct: 5.0,
          max_drawdown_pct: 30.0,
          min_avg_trades_month: 0.5,
          min_sharpe_ratio: 0.20,
          min_ret_dd_ratio: 0.50,
          min_profit_factor: 1.00,
          min_net_profit: 0.0,
          min_total_trades: 0,
          min_win_rate_pct: 0.0,
        },
      });
    }
    setHasUnsavedCriteria(true);
    setCriteriaSaveStatus(null);
  };

  const copyTrainToOos = (applyDecay: boolean = true) => {
    const t = criteria.train;
    const factor = applyDecay ? 0.5 : 1.0;
    const oos: PhaseQualificationCriteria = {
      min_profit_gain_pct: Math.round(t.min_profit_gain_pct * factor * 10) / 10,
      max_drawdown_pct: t.max_drawdown_pct,
      min_avg_trades_month: Math.round(t.min_avg_trades_month * (applyDecay ? 0.8 : 1.0) * 10) / 10,
      min_sharpe_ratio: Math.round(t.min_sharpe_ratio * (applyDecay ? 0.8 : 1.0) * 100) / 100,
      min_ret_dd_ratio: Math.round(t.min_ret_dd_ratio * (applyDecay ? 0.75 : 1.0) * 100) / 100,
      min_profit_factor: Math.max(1.0, Math.round(t.min_profit_factor * (applyDecay ? 0.9 : 1.0) * 100) / 100),
      min_net_profit: t.min_net_profit,
      min_total_trades: Math.round(t.min_total_trades * factor),
      min_win_rate_pct: Math.round(t.min_win_rate_pct * (applyDecay ? 0.9 : 1.0)),
    };
    setCriteria(prev => ({
      ...prev,
      val: { ...oos },
      holdout: { ...oos },
    }));
    setHasUnsavedCriteria(true);
    setCriteriaSaveStatus(null);
  };

  // Load saved optimization configuration from backend or fallback to EA defaults
  useEffect(() => {
    let isMounted = true;
    const loadParams = async () => {
      const defaults = getDefaultConfigForEa(activeEa);
      let mergedParams: StrategyParam[] = defaults.params;
      let mergedIndicators: IndicatorDefinition[] = defaults.indicators;

      try {
        const res = await fetch(`/api/optimization-params?ea=${activeEa}`);
        if (res.ok) {
          const json = await res.json();
          const savedData = json.data;
          if (savedData) {
            // 1. Merge indicators
            if (Array.isArray(savedData.indicators) && savedData.indicators.length > 0) {
              const savedIndMap = new Map<string, any>(
                savedData.indicators.map((i: any) => [i.id || i.toggleParam, i])
              );
              mergedIndicators = mergedIndicators.map(ind => {
                const s = savedIndMap.get(ind.id) || savedIndMap.get(ind.toggleParam);
                return s ? { ...ind, enabled: !!s.enabled, optimize: s.optimize !== undefined ? !!s.optimize : ind.optimize } : ind;
              });
            } else if (savedData.indicator_toggles) {
              mergedIndicators = mergedIndicators.map(ind => ({
                ...ind,
                enabled: savedData.indicator_toggles[ind.toggleParam] !== undefined
                  ? Boolean(savedData.indicator_toggles[ind.toggleParam])
                  : ind.enabled
              }));
            }

            // 2. Merge fixed_params and opt_ranges
            const fixedDict = savedData.fixed_params || {};
            const rangesDict = savedData.opt_ranges || {};

            mergedParams = mergedParams.map(p => {
              const updated = { ...p };
              if (fixedDict[p.name] !== undefined) {
                updated.mode = 'fixed';
                updated.fixedValue = fixedDict[p.name];
              }
              if (rangesDict[p.name] !== undefined && Array.isArray(rangesDict[p.name]) && rangesDict[p.name].length === 3) {
                updated.mode = 'optimize';
                updated.range = {
                  start: Number(rangesDict[p.name][0]) || 0,
                  step: Number(rangesDict[p.name][1]) || 1,
                  stop: Number(rangesDict[p.name][2]) || 10,
                };
              }
              return updated;
            });

            // 3. Merge detailed params array (while preserving full metadata like category, label, etc.)
            if (Array.isArray(savedData.params) && savedData.params.length > 0) {
              const savedParamMap = new Map<string, any>(savedData.params.map((p: any) => [p.name, p]));

              mergedParams = mergedParams.map(p => {
                const s = savedParamMap.get(p.name);
                if (!s) return p;
                return {
                  ...p,
                  category: s.category || p.category || 'core',
                  label: s.label || p.label || p.name,
                  description: s.description || p.description || '',
                  mode: s.mode === 'optimize' ? 'optimize' : 'fixed',
                  fixedValue: s.fixedValue !== undefined ? s.fixedValue : (s.value !== undefined ? s.value : p.fixedValue),
                  range: s.range ? {
                    start: Number(s.range.start) || p.range.start,
                    step: Number(s.range.step) || p.range.step,
                    stop: Number(s.range.stop) || p.range.stop,
                  } : p.range,
                };
              });

              // Also preserve custom params added by user
              savedData.params.forEach((s: any) => {
                if (s.name && !mergedParams.some(p => p.name === s.name)) {
                  mergedParams.push({
                    name: s.name,
                    label: s.label || s.name,
                    category: s.category || 'custom',
                    mode: s.mode === 'optimize' ? 'optimize' : 'fixed',
                    fixedValue: s.fixedValue !== undefined ? s.fixedValue : 1,
                    range: s.range ? {
                      start: Number(s.range.start) || 1,
                      step: Number(s.range.step) || 1,
                      stop: Number(s.range.stop) || 10,
                    } : { start: 1, step: 1, stop: 10 },
                    description: s.description || 'Custom parameter',
                    isCustom: true,
                  });
                }
              });
            }
          }
        }
      } catch (err) {
        console.warn('Could not fetch saved optimization params, loading defaults:', err);
      }

      if (isMounted) {
        setParams(mergedParams);
        setIndicators(mergedIndicators);
      }
    };

    loadParams();
    return () => { isMounted = false; };
  }, [activeEa]);

  // Phase tracker from pipeline logs
  useEffect(() => {
    if (!isRunning) {
      if (logs.some(l => l.includes('[FINISHED] Process exited with code 0'))) {
        setCurrentPhase(4);
      }
      return;
    }

    const fullLog = logs.join('\n');
    if (fullLog.includes('Monte Carlo') || fullLog.includes('certif')) {
      setCurrentPhase(3);
    } else if (fullLog.includes('Validation') || fullLog.includes('Holdout')) {
      setCurrentPhase(2);
    } else if (fullLog.includes('Train') || fullLog.includes('genetic') || isRunning) {
      setCurrentPhase(1);
    }
  }, [logs, isRunning]);

  // Save parameters to backend
  const handleSaveParams = async () => {
    try {
      setSaveStatus('saving');
      const payload = buildOptimizationConfig(activeEa, params, indicators);
      const res = await fetch('/api/optimization-params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activeEa, payload }),
      });

      if (res.ok) {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus(null), 3000);
      } else {
        setSaveStatus('error');
      }
    } catch (e) {
      console.error(e);
      setSaveStatus('error');
    }
  };

  // Reset to default EA recommendations
  const handleResetDefaults = () => {
    const defaults = getDefaultConfigForEa(activeEa);
    setParams(defaults.params);
    setIndicators(defaults.indicators);
    setSaveStatus('reset');
    setTimeout(() => setSaveStatus(null), 3000);
  };

  // Presets
  const applyPreset = (preset: 'core_only' | 'indicators_only' | 'explore_all') => {
    setParams(prev => prev.map(p => {
      if (preset === 'core_only') {
        if (p.category === 'core' || p.category === 'timing') {
          return { ...p, mode: 'optimize' };
        }
        return { ...p, mode: 'fixed' };
      } else if (preset === 'indicators_only') {
        if (p.category === 'indicator') {
          return { ...p, mode: 'optimize' };
        }
        return { ...p, mode: 'fixed' };
      } else if (preset === 'explore_all') {
        if (p.name !== 'MagicNumber' && !p.name.includes('Magic') && p.category !== 'risk') {
          return { ...p, mode: 'optimize' };
        }
      }
      return p;
    }));
  };

  // Toggle single parameter mode (fixed <-> optimize)
  const toggleParamMode = (name: string) => {
    setParams(prev => prev.map(p => {
      if (p.name === name) {
        const nextMode = p.mode === 'fixed' ? 'optimize' : 'fixed';
        return { ...p, mode: nextMode };
      }
      return p;
    }));
  };

  // Update fixed value
  const updateFixedValue = (name: string, value: string | number) => {
    setParams(prev => prev.map(p => {
      if (p.name === name) {
        return { ...p, fixedValue: value };
      }
      return p;
    }));
  };

  // Update range fields (start, step, stop)
  const updateRangeField = (name: string, field: 'start' | 'step' | 'stop', value: number) => {
    setParams(prev => prev.map(p => {
      if (p.name === name) {
        return {
          ...p,
          range: {
            ...p.range,
            [field]: value,
          },
        };
      }
      return p;
    }));
  };

  // Toggle indicator enabled / disabled
  const toggleIndicatorEnabled = (indId: string) => {
    setIndicators(prev => prev.map(ind => {
      if (ind.id === indId) {
        const nextEnabled = !ind.enabled;
        return { ...ind, enabled: nextEnabled };
      }
      return ind;
    }));
  };

  // Toggle all params for an indicator between Fixed and Optimize
  const toggleIndicatorMode = (indId: string) => {
    const ind = indicators.find(i => i.id === indId);
    if (!ind) return;
    const nextOptimize = !ind.optimize;

    setIndicators(prev => prev.map(i => i.id === indId ? { ...i, optimize: nextOptimize } : i));
    setParams(prev => prev.map(p => {
      if (p.indicatorId === indId) {
        return { ...p, mode: nextOptimize ? 'optimize' : 'fixed' };
      }
      return p;
    }));
  };

  // Add custom parameter
  const handleAddCustomParam = () => {
    if (!newParam.name || !newParam.name.trim()) return;
    const cleanName = newParam.name.trim();

    const created: StrategyParam = {
      name: cleanName,
      label: newParam.label?.trim() || cleanName,
      category: (newParam.category as any) || 'custom',
      mode: newParam.mode || 'fixed',
      fixedValue: newParam.fixedValue !== undefined ? newParam.fixedValue : 1.0,
      range: newParam.range || { start: 1.0, step: 0.5, stop: 5.0 },
      description: newParam.description || 'User-defined parameter',
      isCustom: true,
    };

    setParams(prev => [...prev, created]);
    setShowAddModal(false);
    setNewParam({
      name: '',
      label: '',
      category: 'custom',
      mode: 'fixed',
      fixedValue: 1.0,
      range: { start: 1.0, step: 0.5, stop: 3.0 },
      description: '',
    });
  };

  // Remove custom parameter
  const handleRemoveParam = (name: string) => {
    setParams(prev => prev.filter(p => p.name !== name));
  };

  // Calculation of active search space stats
  const stats = useMemo(() => {
    const optimizingParams = params.filter(p => {
      if (p.mode !== 'optimize') return false;
      if (p.indicatorId) {
        const ind = indicators.find(i => i.id === p.indicatorId);
        return ind ? ind.enabled : true;
      }
      return true;
    });

    const fixedParams = params.filter(p => !optimizingParams.includes(p));

    let totalCombinations = 1;
    optimizingParams.forEach(p => {
      const start = Number(p.range?.start) || 0;
      const step = (p.range?.step && Number(p.range.step) > 0) ? Number(p.range.step) : 1;
      const stop = p.range?.stop !== undefined ? Number(p.range.stop) : start;
      const count = Math.max(1, Math.floor((stop - start) / step) + 1);
      totalCombinations *= count;
    });

    const activeInds = indicators.filter(i => i.enabled).length;

    return {
      numOptimizing: optimizingParams.length,
      numFixed: fixedParams.length,
      totalCombinations,
      activeInds,
    };
  }, [params, indicators]);

  // Filtered parameters based on active category & search query
  const filteredParams = useMemo(() => {
    return params.filter(p => {
      if (!p) return false;
      const category = p.category || 'custom';
      if (activeCategory !== 'all' && category !== activeCategory) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchName = (p.name || '').toLowerCase().includes(q);
        const matchLabel = (p.label || '').toLowerCase().includes(q);
        const matchDesc = (p.description || '').toLowerCase().includes(q);
        return matchName || matchLabel || matchDesc;
      }
      return true;
    });
  }, [params, activeCategory, searchQuery]);

  const handleRun = async () => {
    // Auto-save any pending parameters and qualification criteria first
    await handleSaveParams();
    await handleSaveCriteria();
    setCurrentPhase(1);
    runScript('run_optimization.py');
  };

  const phases = [
    { label: "Train Optimize", phaseNum: 1 },
    { label: "Val / Holdout", phaseNum: 2 },
    { label: "Monte Carlo", phaseNum: 3 },
    { label: "Passed →", phaseNum: 4 },
  ];

  return (
    <div className="flex flex-col h-full space-y-4 pb-8 overflow-y-auto">
      <SectionHeader 
        title="⚙ Optimization Pipeline & Strategy Parameters" 
        subtitle={`Adjust indicator filters, fixed parameters, and parameter ranges for ${activeEa} before executing`} 
      />
      
      {/* Top Banner: Strategy & Config Overview */}
      <Card className="p-4 border border-[#2d3748] bg-[#141b2d]">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs flex-1">
            <div className="border-r border-[#2d3748] pr-2">
              <div className="text-[#8b95a6] mb-1 font-medium">Strategy / EA</div>
              <div className="font-semibold text-white flex items-center gap-1.5">
                <span className="px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 font-mono text-[11px] border border-blue-700">
                  {activeEa}
                </span>
                <span className="truncate">{config.expert || `${activeEa} Strategy.ex5`}</span>
              </div>
            </div>
            <div className="border-r border-[#2d3748] pr-2">
              <div className="text-[#8b95a6] mb-1 font-medium">Symbol & Timeframe</div>
              <div className="font-semibold text-white">
                {config.symbol || 'USDJPY Dukascopy'} ({config.period || 'M15'})
              </div>
            </div>
            <div className="border-r border-[#2d3748] pr-2">
              <div className="text-[#8b95a6] mb-1 font-medium">Testing Windows</div>
              <div className="font-semibold text-white">
                {config.train_from || '2013.01.01'} → {config.holdout_to || '2026.07.03'}
              </div>
            </div>
            <div>
              <div className="text-[#8b95a6] mb-1 font-medium">Deposit & Leverage</div>
              <div className="font-semibold text-white">
                ${config.deposit || '2500'} {config.currency || 'USD'} ({config.leverage || '1:100'})
              </div>
            </div>
          </div>

          {/* Quick Stats Pill */}
          <div className="flex items-center gap-2 bg-[#0d1322] px-3 py-2 rounded-lg border border-[#232f48] text-xs">
            <div className="flex items-center gap-1 text-amber-400 font-semibold">
              <Zap size={14} />
              <span>{stats.numOptimizing}</span>
              <span className="text-[#8b95a6] font-normal">optimizing</span>
            </div>
            <span className="text-[#2d3748]">•</span>
            <div className="flex items-center gap-1 text-slate-300 font-semibold">
              <Lock size={13} className="text-slate-400" />
              <span>{stats.numFixed}</span>
              <span className="text-[#8b95a6] font-normal">fixed</span>
            </div>
            <span className="text-[#2d3748]">•</span>
            <div className="flex items-center gap-1 text-emerald-400 font-semibold">
              <Filter size={13} />
              <span>{stats.activeInds}/{indicators.length}</span>
              <span className="text-[#8b95a6] font-normal">indicators</span>
            </div>
          </div>
        </div>
      </Card>

      {/* ─────────────────────────────────────────────────────────────
          SECTION 1: INDICATOR FILTERS SWITCHBOARD
          ───────────────────────────────────────────────────────────── */}
      <Card className="p-4 border border-[#232f48]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Filter size={16} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">Indicator Filter Switchboard</h3>
              <p className="text-xs text-[#8b95a6]">Enable or disable indicator filters, and select whether their inputs are held fixed or optimized</p>
            </div>
          </div>
          <button 
            onClick={() => setShowIndicatorsGrid(!showIndicatorsGrid)}
            className="text-xs text-[#8b95a6] hover:text-white flex items-center gap-1 px-2 py-1 rounded bg-[#131b2e] border border-[#232f48]"
          >
            {showIndicatorsGrid ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            <span>{showIndicatorsGrid ? 'Collapse' : 'Expand'}</span>
          </button>
        </div>

        {showIndicatorsGrid && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 pt-1">
            {indicators.map(ind => {
              const indicatorParams = params.filter(p => p.indicatorId === ind.id);
              const anyOptimizing = indicatorParams.some(p => p.mode === 'optimize');

              return (
                <div 
                  key={ind.id} 
                  className={`p-3 rounded-lg border transition-all ${
                    ind.enabled 
                      ? 'bg-[#151d30] border-emerald-800/60 shadow-sm' 
                      : 'bg-[#0f1523] border-[#222c40] opacity-60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                      <input 
                        type="checkbox"
                        checked={ind.enabled}
                        onChange={() => toggleIndicatorEnabled(ind.id)}
                        className="w-4 h-4 rounded border-[#38455e] text-emerald-500 bg-[#0a0e1a] focus:ring-emerald-500 focus:ring-1 cursor-pointer accent-emerald-500"
                      />
                      <span className={`text-sm font-semibold ${ind.enabled ? 'text-white' : 'text-[#8b95a6]'}`}>
                        {ind.name}
                      </span>
                    </label>

                    {ind.enabled && (
                      <button
                        onClick={() => toggleIndicatorMode(ind.id)}
                        className={`text-[11px] px-2 py-0.5 rounded font-medium transition-colors flex items-center gap-1 ${
                          anyOptimizing
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30'
                            : 'bg-slate-700/50 text-slate-300 border border-slate-600 hover:bg-slate-700'
                        }`}
                        title="Toggle all parameters of this indicator between Fixed and Optimize"
                      >
                        {anyOptimizing ? <Zap size={11} /> : <Lock size={11} />}
                        <span>{anyOptimizing ? 'Optimizing' : 'Fixed'}</span>
                      </button>
                    )}
                  </div>

                  <p className="text-[11px] text-[#8b95a6] line-clamp-2 mb-2 leading-relaxed">
                    {ind.description}
                  </p>

                  <div className="text-[11px] font-mono text-[#a0aec0] flex flex-wrap items-center gap-1 pt-1 border-t border-[#232f48]/70">
                    <span className="text-[#64748b]">Params:</span>
                    {indicatorParams.map(p => (
                      <span 
                        key={p.name}
                        className={`px-1.5 py-0.5 rounded text-[10px] ${
                          !ind.enabled 
                            ? 'bg-[#1a2336] text-[#64748b]' 
                            : p.mode === 'optimize' 
                              ? 'bg-amber-950/70 text-amber-300 border border-amber-800/60 font-semibold' 
                              : 'bg-[#1c263b] text-slate-300 border border-[#2d3a54]'
                        }`}
                      >
                        {p.name} {p.mode === 'optimize' ? `(${p.range.start}..${p.range.stop})` : `=${p.fixedValue}`}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ─────────────────────────────────────────────────────────────
          SECTION 2: PARAMETER ADJUSTMENT TABLE (FIXED VS OPTIMIZE)
          ───────────────────────────────────────────────────────────── */}
      <Card className="p-4 border border-[#232f48]">
        {/* Header & Controls */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <Sliders size={16} />
              </div>
              <h3 className="text-sm font-semibold text-white">Strategy Parameters Configuration</h3>
            </div>
            <p className="text-xs text-[#8b95a6] mt-0.5">
              Set each parameter to either <span className="text-slate-300 font-medium">Fixed</span> (constant value) or <span className="text-amber-400 font-medium">Optimize</span> (Start, Step, Stop range)
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleSaveParams}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 shadow-sm ${
                saveStatus === 'saved'
                  ? 'bg-emerald-600 text-white'
                  : 'bg-[#2563eb] hover:bg-[#1d4ed8] text-white border border-blue-500/40'
              }`}
            >
              {saveStatus === 'saved' ? <CheckCircle2 size={14} /> : <Save size={14} />}
              <span>{saveStatus === 'saved' ? 'Saved to Pipeline!' : 'Save & Apply Parameters'}</span>
            </button>

            <button
              onClick={handleResetDefaults}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#1a2336] hover:bg-[#222f48] text-[#cbd5e1] border border-[#2d3a54] flex items-center gap-1.5 transition-colors"
              title="Reset all parameters back to EA recommended defaults"
            >
              <RotateCcw size={13} />
              <span>Reset Defaults</span>
            </button>

            <button
              onClick={() => setShowAddModal(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#1e293b] hover:bg-[#2e3e57] text-[#f1f5f9] border border-[#3b4d6e] flex items-center gap-1.5 transition-colors"
            >
              <Plus size={14} />
              <span>Add Custom Param</span>
            </button>
          </div>
        </div>

        {/* Presets & Filter Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-2 pb-3 border-t border-b border-[#232f48]">
          {/* Category Tabs */}
          <div className="flex items-center gap-1 overflow-x-auto text-xs py-1">
            {[
              { id: 'all', label: 'All Parameters', count: params.length },
              { id: 'core', label: 'Core Strategy', count: params.filter(p => (p.category || 'custom') === 'core').length },
              { id: 'timing', label: 'Timing', count: params.filter(p => (p.category || 'custom') === 'timing').length },
              { id: 'risk', label: 'Risk & Compliance', count: params.filter(p => (p.category || 'custom') === 'risk').length },
              { id: 'indicator', label: 'Indicators', count: params.filter(p => (p.category || 'custom') === 'indicator').length },
              { id: 'custom', label: 'Custom', count: params.filter(p => (p.category || 'custom') === 'custom').length },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveCategory(tab.id)}
                className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap font-medium ${
                  activeCategory === tab.id
                    ? 'bg-[#3b82f6] text-white shadow-sm'
                    : 'text-[#8b95a6] hover:text-white hover:bg-[#1a2336]'
                }`}
              >
                {tab.label} <span className="text-[10px] opacity-75">({tab.count})</span>
              </button>
            ))}
          </div>

          {/* Search Input & Quick Presets */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1 md:w-52">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#64748b]" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Filter by name..."
                className="w-full pl-8 pr-2.5 py-1 text-xs bg-[#101726] border border-[#232f48] rounded-md text-white placeholder-[#64748b] focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Quick Preset buttons */}
            <div className="hidden lg:flex items-center gap-1 text-[11px]">
              <span className="text-[#64748b] mr-1">Presets:</span>
              <button
                onClick={() => applyPreset('core_only')}
                className="px-2 py-1 rounded bg-[#162035] hover:bg-[#202d4a] text-[#94a3b8] hover:text-white border border-[#232f48]"
                title="Optimize Core Strategy, hold Indicators fixed"
              >
                Core Only
              </button>
              <button
                onClick={() => applyPreset('indicators_only')}
                className="px-2 py-1 rounded bg-[#162035] hover:bg-[#202d4a] text-[#94a3b8] hover:text-white border border-[#232f48]"
                title="Optimize Indicator Filters, hold Core Strategy fixed"
              >
                Indicators Only
              </button>
              <button
                onClick={() => applyPreset('explore_all')}
                className="px-2 py-1 rounded bg-[#162035] hover:bg-[#202d4a] text-[#94a3b8] hover:text-white border border-[#232f48]"
                title="Optimize both Core Strategy and Indicator Filters"
              >
                Explore All
              </button>
            </div>
          </div>
        </div>

        {/* Parameters List Table */}
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#232f48] text-[#8b95a6] font-medium">
                <th className="py-2.5 px-3">Parameter</th>
                <th className="py-2.5 px-2">Category</th>
                <th className="py-2.5 px-3 text-center">Mode</th>
                <th className="py-2.5 px-3">Configuration</th>
                <th className="py-2.5 px-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e273a]">
              {filteredParams.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-[#8b95a6]">
                    No parameters found matching category "{activeCategory}" {searchQuery && `and search "${searchQuery}"`}
                  </td>
                </tr>
              ) : (
                filteredParams.map(p => {
                  const isOptimizing = p.mode === 'optimize';
                  const cat = p.category || 'custom';
                  const startVal = Number(p.range?.start) || 0;
                  const stepVal = (p.range?.step && Number(p.range.step) > 0) ? Number(p.range.step) : 1;
                  const stopVal = p.range?.stop !== undefined ? Number(p.range.stop) : startVal;
                  const stepCount = Math.max(1, Math.floor((stopVal - startVal) / stepVal) + 1);

                  // Check if parent indicator is disabled
                  let isParentDisabled = false;
                  if (p.indicatorId) {
                    const ind = indicators.find(i => i.id === p.indicatorId);
                    if (ind && !ind.enabled) isParentDisabled = true;
                  }

                  return (
                    <tr 
                      key={p.name} 
                      className={`hover:bg-[#162032]/60 transition-colors ${
                        isParentDisabled ? 'opacity-40 bg-[#0d121c]' : ''
                      }`}
                    >
                      {/* Name & Description */}
                      <td className="py-2.5 px-3 min-w-[200px]">
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono font-semibold text-white">{p.name}</span>
                          {p.isCustom && (
                            <span className="px-1 py-0.2 rounded text-[9px] bg-purple-900/60 text-purple-300 border border-purple-700">
                              Custom
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-[#8b95a6] truncate max-w-xs" title={p.description || p.label}>
                          {p.label || p.description}
                        </div>
                      </td>

                      {/* Category Badge */}
                      <td className="py-2.5 px-2 whitespace-nowrap">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                          cat === 'core' 
                            ? 'bg-blue-900/40 text-blue-300 border border-blue-800/60' 
                            : cat === 'timing'
                              ? 'bg-cyan-900/40 text-cyan-300 border border-cyan-800/60'
                              : cat === 'risk'
                                ? 'bg-red-900/40 text-red-300 border border-red-800/60'
                                : cat === 'indicator'
                                  ? 'bg-emerald-900/40 text-emerald-300 border border-emerald-800/60'
                                  : 'bg-purple-900/40 text-purple-300 border border-purple-800/60'
                        }`}>
                          {cat.toUpperCase()}
                        </span>
                      </td>

                      {/* Mode Toggle Selector */}
                      <td className="py-2.5 px-3 text-center whitespace-nowrap">
                        <div className="inline-flex rounded-lg p-0.5 bg-[#0f1626] border border-[#232f48]">
                          <button
                            type="button"
                            onClick={() => toggleParamMode(p.name)}
                            disabled={isParentDisabled}
                            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                              !isOptimizing
                                ? 'bg-[#232f48] text-white shadow-sm'
                                : 'text-[#8b95a6] hover:text-white'
                            }`}
                          >
                            <Lock size={11} className={!isOptimizing ? 'text-slate-300' : ''} />
                            <span>Fixed</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => toggleParamMode(p.name)}
                            disabled={isParentDisabled}
                            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
                              isOptimizing
                                ? 'bg-amber-500 text-slate-950 font-bold shadow-sm'
                                : 'text-[#8b95a6] hover:text-white'
                            }`}
                          >
                            <Zap size={11} className={isOptimizing ? 'text-slate-950' : ''} />
                            <span>Optimize</span>
                          </button>
                        </div>
                      </td>

                      {/* Configuration Controls (Fixed value vs Range) */}
                      <td className="py-2.5 px-3">
                        {!isOptimizing ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={p.fixedValue !== undefined ? p.fixedValue : ''}
                              onChange={e => updateFixedValue(p.name, e.target.value)}
                              disabled={isParentDisabled}
                              className="w-28 px-2.5 py-1 bg-[#0a0f1d] border border-[#2d3a54] rounded text-white font-mono text-xs focus:outline-none focus:border-blue-500"
                              placeholder="Value"
                            />
                            <span className="text-[11px] text-[#64748b]">
                              {isParentDisabled ? '(Indicator disabled)' : 'Fixed constant for all passes'}
                            </span>
                          </div>
                        ) : (
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="flex items-center gap-1">
                              <span className="text-[11px] text-[#8b95a6]">Start:</span>
                              <input
                                type="number"
                                step="any"
                                value={p.range?.start !== undefined ? p.range.start : 0}
                                onChange={e => updateRangeField(p.name, 'start', parseFloat(e.target.value) || 0)}
                                disabled={isParentDisabled}
                                className="w-20 px-2 py-1 bg-[#0a0f1d] border border-amber-900/60 rounded text-amber-200 font-mono text-xs focus:outline-none focus:border-amber-500"
                              />
                            </div>
                            <div className="flex items-center gap-1">
                              <span className="text-[11px] text-[#8b95a6]">Step:</span>
                              <input
                                type="number"
                                step="any"
                                value={p.range?.step !== undefined ? p.range.step : 1}
                                onChange={e => updateRangeField(p.name, 'step', parseFloat(e.target.value) || 1)}
                                disabled={isParentDisabled}
                                className="w-18 px-2 py-1 bg-[#0a0f1d] border border-amber-900/60 rounded text-amber-200 font-mono text-xs focus:outline-none focus:border-amber-500"
                              />
                            </div>
                            <div className="flex items-center gap-1">
                              <span className="text-[11px] text-[#8b95a6]">Stop:</span>
                              <input
                                type="number"
                                step="any"
                                value={p.range?.stop !== undefined ? p.range.stop : 0}
                                onChange={e => updateRangeField(p.name, 'stop', parseFloat(e.target.value) || 0)}
                                disabled={isParentDisabled}
                                className="w-20 px-2 py-1 bg-[#0a0f1d] border border-amber-900/60 rounded text-amber-200 font-mono text-xs focus:outline-none focus:border-amber-500"
                              />
                            </div>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-950/60 text-amber-300 border border-amber-800/40">
                              ~{stepCount} steps
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-2.5 px-2 text-right">
                        {p.isCustom ? (
                          <button
                            onClick={() => handleRemoveParam(p.name)}
                            className="p-1 rounded text-red-400 hover:text-red-300 hover:bg-red-950/40 transition-colors"
                            title="Delete custom parameter"
                          >
                            <Trash2 size={14} />
                          </button>
                        ) : (
                          <span className="text-[#334155] text-xs font-mono select-none">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ─────────────────────────────────────────────────────────────
          SECTION 3: CANDIDATE QUALIFICATION GATES (TRAIN, VAL & HOLDOUT)
          ───────────────────────────────────────────────────────────── */}
      <Card className="p-4 border border-[#232f48] shadow-lg">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-[#232f48]">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mt-0.5">
              <Target size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">
                  Candidate Qualification Gates (Pass / Fail Criteria)
                </h3>
                {hasUnsavedCriteria && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
                    Unsaved Changes
                  </span>
                )}
              </div>
              <p className="text-xs text-[#8b95a6] mt-0.5">
                Set required metrics for candidates to qualify through <span className="text-blue-300 font-medium">Train</span> (in-sample optimization XML), <span className="text-emerald-300 font-medium">Validation</span> (OOS 1), and <span className="text-purple-300 font-medium">Holdout</span> (OOS 2).
              </p>
            </div>
          </div>

          {/* Quick Actions & Save */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleSaveCriteria}
              disabled={criteriaSaveStatus === 'saving'}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 shadow-sm ${
                criteriaSaveStatus === 'saved'
                  ? 'bg-emerald-600 text-white'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-500/40'
              }`}
            >
              {criteriaSaveStatus === 'saved' ? <CheckCircle2 size={14} /> : <Save size={14} />}
              <span>{criteriaSaveStatus === 'saved' ? 'Saved to Pipeline!' : criteriaSaveStatus === 'saving' ? 'Saving...' : 'Save Qualification Gates'}</span>
            </button>

            <button
              type="button"
              onClick={() => setShowCriteriaCard(!showCriteriaCard)}
              className="p-1.5 rounded-lg text-[#8b95a6] hover:text-white bg-[#151d30] border border-[#232f48] transition-colors"
              title={showCriteriaCard ? 'Collapse section' : 'Expand section'}
            >
              {showCriteriaCard ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>
        </div>

        {showCriteriaCard && (
          <div className="mt-3 space-y-3">
            {/* Presets & Mode Tabs Bar */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 p-2.5 rounded-lg bg-[#0d1322] border border-[#232f48]">
              {/* Mode Tabs */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setCriteriaViewMode('matrix')}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${
                    criteriaViewMode === 'matrix'
                      ? 'bg-[#2563eb] text-white shadow-sm'
                      : 'text-[#8b95a6] hover:text-white hover:bg-[#1a2336]'
                  }`}
                >
                  <Scale size={13} />
                  <span>Comparative Matrix</span>
                </button>
                <button
                  type="button"
                  onClick={() => setCriteriaViewMode('train')}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${
                    criteriaViewMode === 'train'
                      ? 'bg-blue-600/30 text-blue-300 border border-blue-500/50'
                      : 'text-[#8b95a6] hover:text-white hover:bg-[#1a2336]'
                  }`}
                >
                  <Target size={13} />
                  <span>Train Gate</span>
                </button>
                <button
                  type="button"
                  onClick={() => setCriteriaViewMode('val')}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${
                    criteriaViewMode === 'val'
                      ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/50'
                      : 'text-[#8b95a6] hover:text-white hover:bg-[#1a2336]'
                  }`}
                >
                  <ShieldCheck size={13} />
                  <span>Validation Gate</span>
                </button>
                <button
                  type="button"
                  onClick={() => setCriteriaViewMode('holdout')}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5 ${
                    criteriaViewMode === 'holdout'
                      ? 'bg-purple-600/30 text-purple-300 border border-purple-500/50'
                      : 'text-[#8b95a6] hover:text-white hover:bg-[#1a2336]'
                  }`}
                >
                  <Award size={13} />
                  <span>Holdout Gate</span>
                </button>
              </div>

              {/* Quick Preset Buttons */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] text-[#64748b] mr-1 flex items-center gap-1">
                  <Sparkles size={12} /> Presets:
                </span>
                <button
                  type="button"
                  onClick={() => applyCriteriaPreset('balanced')}
                  className="px-2 py-0.5 rounded text-[11px] font-medium bg-[#1a2336] text-slate-300 hover:text-white hover:bg-[#222f48] border border-[#2a3854] transition-colors"
                  title="Standard industry multi-phase parameters (Gain 30/15%, MaxDD 20%, PF 1.10/1.0)"
                >
                  Balanced (Default)
                </button>
                <button
                  type="button"
                  onClick={() => applyCriteriaPreset('prop')}
                  className="px-2 py-0.5 rounded text-[11px] font-medium bg-[#1a2336] text-amber-300 hover:text-amber-200 hover:bg-[#222f48] border border-amber-900/40 transition-colors"
                  title="Strict risk controls (MaxDD <= 8%, Sharpe >= 0.90, PF >= 1.35)"
                >
                  Prop Firm (MaxDD 8%)
                </button>
                <button
                  type="button"
                  onClick={() => applyCriteriaPreset('hft')}
                  className="px-2 py-0.5 rounded text-[11px] font-medium bg-[#1a2336] text-cyan-300 hover:text-cyan-200 hover:bg-[#222f48] border border-cyan-900/40 transition-colors"
                  title="Higher minimum trade density (>=4 trades/month, min 50 total trades)"
                >
                  High Frequency
                </button>
                <button
                  type="button"
                  onClick={() => applyCriteriaPreset('relaxed')}
                  className="px-2 py-0.5 rounded text-[11px] font-medium bg-[#1a2336] text-slate-400 hover:text-white hover:bg-[#222f48] border border-[#2a3854] transition-colors"
                  title="Lenient thresholds to observe candidate distribution"
                >
                  Relaxed
                </button>

                <div className="h-4 w-px bg-[#232f48] mx-1" />

                <button
                  type="button"
                  onClick={() => copyTrainToOos(true)}
                  className="px-2 py-0.5 rounded text-[11px] font-medium bg-[#162138] text-blue-300 hover:text-blue-200 hover:bg-[#1e2d4d] border border-blue-800/40 transition-colors flex items-center gap-1"
                  title="Copies Train criteria to Validation & Holdout with standard 50% out-of-sample decay"
                >
                  <Copy size={11} />
                  <span>Copy Train to OOS (50% Decay)</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setCriteria(DEFAULT_QUALIFICATION_CRITERIA);
                    setHasUnsavedCriteria(true);
                  }}
                  className="p-1 rounded text-[#8b95a6] hover:text-white hover:bg-[#1e273a] transition-colors"
                  title="Reset all thresholds to factory defaults"
                >
                  <RotateCcw size={13} />
                </button>
              </div>
            </div>

            {/* VIEW MODE 1: COMPARATIVE MATRIX (SIDE-BY-SIDE ALL 3 PHASES) */}
            {criteriaViewMode === 'matrix' && (
              <div className="overflow-x-auto rounded-lg border border-[#232f48]">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-[#0f1523] border-b border-[#232f48] text-[#8b95a6] font-medium">
                      <th className="py-2.5 px-3 min-w-[180px]">Qualification Metric</th>
                      <th className="py-2.5 px-2 text-center w-24">Type</th>
                      <th className="py-2.5 px-3 bg-blue-950/20 text-blue-300 min-w-[140px] text-center border-l border-[#232f48]">
                        <div className="flex items-center justify-center gap-1.5 font-semibold">
                          <Target size={13} />
                          <span>Train (In-Sample)</span>
                        </div>
                        <div className="text-[10px] text-blue-400/70 font-normal">Optimization Report</div>
                      </th>
                      <th className="py-2.5 px-3 bg-emerald-950/20 text-emerald-300 min-w-[140px] text-center border-l border-[#232f48]">
                        <div className="flex items-center justify-center gap-1.5 font-semibold">
                          <ShieldCheck size={13} />
                          <span>Validation (OOS 1)</span>
                        </div>
                        <div className="text-[10px] text-emerald-400/70 font-normal">Forward Backtest</div>
                      </th>
                      <th className="py-2.5 px-3 bg-purple-950/20 text-purple-300 min-w-[140px] text-center border-l border-[#232f48]">
                        <div className="flex items-center justify-center gap-1.5 font-semibold">
                          <Award size={13} />
                          <span>Holdout (OOS 2)</span>
                        </div>
                        <div className="text-[10px] text-purple-400/70 font-normal">Blind Final Gate</div>
                      </th>
                      <th className="py-2.5 px-3 min-w-[220px] border-l border-[#232f48]">Guidance & Impact</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1e273a] bg-[#0b101d]">
                    {CRITERIA_METRICS.map(m => {
                      const trainVal = criteria.train[m.key] ?? 0;
                      const valVal = criteria.val[m.key] ?? 0;
                      const holdoutVal = criteria.holdout[m.key] ?? 0;

                      return (
                        <tr key={m.key} className="hover:bg-[#141c2c] transition-colors">
                          {/* Metric Label & Badge */}
                          <td className="py-2 px-3">
                            <div className="font-semibold text-white flex items-center gap-1.5">
                              <span>{m.label}</span>
                            </div>
                            <div className="text-[11px] text-[#8b95a6] leading-tight">
                              {m.description}
                            </div>
                          </td>

                          {/* Category Badge */}
                          <td className="py-2 px-2 text-center">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              m.category === 'risk' 
                                ? 'bg-rose-950/60 text-rose-300 border border-rose-800/40' 
                                : m.category === 'returns' 
                                ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/40'
                                : m.category === 'quality'
                                ? 'bg-indigo-950/60 text-indigo-300 border border-indigo-800/40'
                                : 'bg-cyan-950/60 text-cyan-300 border border-cyan-800/40'
                            }`}>
                              {m.badge}
                            </span>
                          </td>

                          {/* Train Input */}
                          <td className="py-2 px-3 bg-blue-950/10 border-l border-[#232f48]">
                            <div className="flex items-center justify-center gap-1">
                              <span className="text-[11px] font-mono text-blue-400 select-none">
                                {m.key === 'max_drawdown_pct' ? '≤' : '≥'}
                              </span>
                              <input
                                type="number"
                                step={m.step}
                                min={m.min}
                                max={m.max}
                                value={trainVal}
                                onChange={e => handleCriteriaChange('train', m.key, parseFloat(e.target.value))}
                                className="w-20 px-2 py-1 bg-[#090d16] border border-blue-800/50 rounded text-center text-blue-200 font-mono text-xs focus:outline-none focus:border-blue-400"
                              />
                              <span className="text-[10px] text-[#64748b] font-mono">{m.unit}</span>
                            </div>
                          </td>

                          {/* Validation Input */}
                          <td className="py-2 px-3 bg-emerald-950/10 border-l border-[#232f48]">
                            <div className="flex items-center justify-center gap-1">
                              <span className="text-[11px] font-mono text-emerald-400 select-none">
                                {m.key === 'max_drawdown_pct' ? '≤' : '≥'}
                              </span>
                              <input
                                type="number"
                                step={m.step}
                                min={m.min}
                                max={m.max}
                                value={valVal}
                                onChange={e => handleCriteriaChange('val', m.key, parseFloat(e.target.value))}
                                className="w-20 px-2 py-1 bg-[#090d16] border border-emerald-800/50 rounded text-center text-emerald-200 font-mono text-xs focus:outline-none focus:border-emerald-400"
                              />
                              <span className="text-[10px] text-[#64748b] font-mono">{m.unit}</span>
                            </div>
                          </td>

                          {/* Holdout Input */}
                          <td className="py-2 px-3 bg-purple-950/10 border-l border-[#232f48]">
                            <div className="flex items-center justify-center gap-1">
                              <span className="text-[11px] font-mono text-purple-400 select-none">
                                {m.key === 'max_drawdown_pct' ? '≤' : '≥'}
                              </span>
                              <input
                                type="number"
                                step={m.step}
                                min={m.min}
                                max={m.max}
                                value={holdoutVal}
                                onChange={e => handleCriteriaChange('holdout', m.key, parseFloat(e.target.value))}
                                className="w-20 px-2 py-1 bg-[#090d16] border border-purple-800/50 rounded text-center text-purple-200 font-mono text-xs focus:outline-none focus:border-purple-400"
                              />
                              <span className="text-[10px] text-[#64748b] font-mono">{m.unit}</span>
                            </div>
                          </td>

                          {/* Metric Guidance */}
                          <td className="py-2 px-3 text-[11px] text-[#8b95a6] border-l border-[#232f48]">
                            {m.key === 'min_profit_gain_pct' && (
                              <span>Expect ~50% decay between Train and OOS. Train 30% → Val 15% is standard.</span>
                            )}
                            {m.key === 'max_drawdown_pct' && (
                              <span className="text-amber-300/90 font-medium">Critical safety gate: candidates exceeding this DD % are disqualified immediately.</span>
                            )}
                            {m.key === 'min_profit_factor' && (
                              <span>PF &gt; 1.0 means net profitable. Val PF &gt;= 1.0 ensures strategy broke even out-of-sample.</span>
                            )}
                            {m.key === 'min_sharpe_ratio' && (
                              <span>Sharpe &gt;= 0.50 denotes acceptable risk-adjusted returns; &gt;= 1.0 is institutional grade.</span>
                            )}
                            {m.key === 'min_ret_dd_ratio' && (
                              <span>Recovery factor &gt; 1.0 means total profits exceeded maximum drawdown dollars.</span>
                            )}
                            {m.key === 'min_avg_trades_month' && (
                              <span>Ensures statistical sample size; eliminates "lucky" 1-2 trade outliers.</span>
                            )}
                            {m.key === 'min_net_profit' && (
                              <span>Absolute floor ($0 = must not finish in net negative dollar loss).</span>
                            )}
                            {m.key === 'min_total_trades' && (
                              <span>{trainVal > 0 ? `Requires at least ${trainVal} trades in period.` : 'Disabled (0 trades).'}</span>
                            )}
                            {m.key === 'min_win_rate_pct' && (
                              <span>{trainVal > 0 ? `Requires at least ${trainVal}% win rate.` : 'Disabled (any win rate with positive edge).'}</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* VIEW MODE 2: INDIVIDUAL PHASE CARD VIEWS (TRAIN, VAL, OR HOLDOUT) */}
            {criteriaViewMode !== 'matrix' && (
              <div className="p-4 rounded-lg bg-[#0d1322] border border-[#232f48]">
                {/* Phase Info Banner */}
                <div className={`p-3 rounded-lg border mb-4 flex items-start gap-3 ${
                  criteriaViewMode === 'train'
                    ? 'bg-blue-950/30 border-blue-800/40 text-blue-200'
                    : criteriaViewMode === 'val'
                    ? 'bg-emerald-950/30 border-emerald-800/40 text-emerald-200'
                    : 'bg-purple-950/30 border-purple-800/40 text-purple-200'
                }`}>
                  <div className="p-2 rounded-md bg-black/30 mt-0.5">
                    {criteriaViewMode === 'train' ? <Target size={18} /> : criteriaViewMode === 'val' ? <ShieldCheck size={18} /> : <Award size={18} />}
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold capitalize">
                      {criteriaViewMode === 'train' && 'Train Optimization Screening Gate (In-Sample)'}
                      {criteriaViewMode === 'val' && 'Validation Forward Backtest Gate (Out-of-Sample 1)'}
                      {criteriaViewMode === 'holdout' && 'Holdout Final Blind Gate (Out-of-Sample 2)'}
                    </h4>
                    <p className="text-xs text-[#8b95a6] mt-0.5">
                      {criteriaViewMode === 'train' && 'Applied to every row in the MT5 multi-pass optimization XML report. Only passes satisfying all active rules advance to single-test Validation.'}
                      {criteriaViewMode === 'val' && 'Applied to the full detailed forward backtest run on untouched validation data. Disqualifies curve-fitted parameter candidates.'}
                      {criteriaViewMode === 'holdout' && 'Final blind hurdle on the most recent holdout dataset. Survivors here are certified and exported to Monte Carlo stress testing.'}
                    </p>
                  </div>
                </div>

                {/* Grid of Metric Inputs */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {CRITERIA_METRICS.map(m => {
                    const currentVal = criteria[criteriaViewMode][m.key] ?? 0;
                    return (
                      <div 
                        key={m.key} 
                        className="p-3 rounded-lg bg-[#0a0e1a] border border-[#222c40] hover:border-[#38455e] transition-colors"
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <label className="text-xs font-semibold text-white">
                            {m.label}
                          </label>
                          <span className={`px-1.5 py-0.2 rounded text-[10px] font-medium ${
                            m.category === 'risk' 
                              ? 'bg-rose-950/60 text-rose-300 border border-rose-800/40' 
                              : m.category === 'returns' 
                              ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/40'
                              : 'bg-indigo-950/60 text-indigo-300 border border-indigo-800/40'
                          }`}>
                            {m.badge}
                          </span>
                        </div>
                        <p className="text-[11px] text-[#8b95a6] line-clamp-1 mb-2">
                          {m.description}
                        </p>

                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-mono text-[#64748b]">
                            {m.key === 'max_drawdown_pct' ? 'Max:' : 'Min:'}
                          </span>
                          <input
                            type="number"
                            step={m.step}
                            min={m.min}
                            max={m.max}
                            value={currentVal}
                            onChange={e => handleCriteriaChange(criteriaViewMode, m.key, parseFloat(e.target.value))}
                            className="flex-1 px-2.5 py-1.5 bg-[#121827] border border-[#2d3a54] rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500"
                          />
                          <span className="text-xs text-[#8b95a6] font-mono w-14 text-right">
                            {m.unit}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Status Footer */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2 px-1 text-[11px] text-[#64748b]">
              <div className="flex items-center gap-4">
                <span>
                  Active Train Gate: <strong className="text-blue-300">Gain &ge; {criteria.train.min_profit_gain_pct}%</strong>, <strong className="text-rose-300">MaxDD &le; {criteria.train.max_drawdown_pct}%</strong>, <strong className="text-slate-300">PF &ge; {criteria.train.min_profit_factor}</strong>
                </span>
                <span className="hidden md:inline">|</span>
                <span className="hidden md:inline">
                  Validation: <strong className="text-emerald-300">Gain &ge; {criteria.val.min_profit_gain_pct}%</strong>, <strong className="text-rose-300">MaxDD &le; {criteria.val.max_drawdown_pct}%</strong>
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-[#8b95a6]">
                <CheckCircle2 size={12} className="text-emerald-400" />
                <span>Synchronized with pipeline and strategy_builder.py</span>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* ─────────────────────────────────────────────────────────────
          SECTION 4: PIPELINE EXECUTION & STATUS
          ───────────────────────────────────────────────────────────── */}
      <Card className="p-4 border border-[#232f48]">
        {/* Phase Progression */}
        <div className="flex items-center justify-between max-w-2xl mx-auto px-4 mb-4">
          {phases.map((item, idx) => {
            const isCurrent = isRunning && currentPhase === item.phaseNum;
            const isCompleted = currentPhase > item.phaseNum;
            return (
              <div key={idx} className="flex flex-col items-center gap-1.5">
                <div className="text-xl">
                  {isCurrent ? "⏳" : isCompleted ? "✅" : "🔵"}
                </div>
                <div className={`text-xs text-center font-medium ${
                  isCurrent ? "text-[#f59e0b] font-bold" : isCompleted ? "text-emerald-400" : "text-[#8b95a6]"
                }`}>
                  {item.label}
                </div>
              </div>
            );
          })}
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-[#232f48]">
          {isRunning ? (
            <Button onClick={stopScript} variant="blue" className="bg-red-600 hover:bg-red-700">
              <Square size={16} /> Stop Execution
            </Button>
          ) : (
            <Button onClick={handleRun}>
              <Play size={16} /> Run Full Pipeline
            </Button>
          )}

          <Button 
            variant="secondary" 
            onClick={async () => {
              await handleSaveParams();
              await handleSaveCriteria();
            }}
            className={(saveStatus === 'saved' || criteriaSaveStatus === 'saved') ? 'border-emerald-500 text-emerald-400' : ''}
          >
            <Save size={16} /> Save All (Params & Gates)
          </Button>

          {onNavigateToSettings && (
            <Button variant="secondary" onClick={onNavigateToSettings}>
              <SettingsIcon size={16} /> Configure in Settings
            </Button>
          )}

          <Button variant="secondary" onClick={clearLogs}>
            <Trash2 size={16} /> Clear Log
          </Button>

          <Button 
            variant="secondary" 
            onClick={() => alert(`Optimization runs directory:\n${config.work_dir || "optimization_runs"}`)}
          >
            <FolderOpen size={16} /> Open Runs Folder
          </Button>
        </div>
      </Card>

      {/* Live Log Viewer */}
      <div className="min-h-[320px] flex flex-col">
        <LogViewer logs={logs} title={`Live Pipeline Output ${isRunning ? '(Running MT5 Strategy Tester...)' : ''}`} />
      </div>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: ADD CUSTOM PARAMETER
          ───────────────────────────────────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-[#141d30] border border-[#2d3a54] rounded-xl w-full max-w-md p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[#232f48] pb-3">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded bg-purple-500/20 text-purple-300">
                  <Plus size={16} />
                </div>
                <h3 className="text-base font-semibold text-white">Add Strategy Parameter</h3>
              </div>
              <button 
                onClick={() => setShowAddModal(false)}
                className="text-[#8b95a6] hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-[#8b95a6] mb-1 font-medium">Parameter Name (exact EA input name)</label>
                <input
                  type="text"
                  value={newParam.name || ''}
                  onChange={e => setNewParam({ ...newParam, name: e.target.value })}
                  placeholder="e.g. InpBreakoutFilter"
                  className="w-full px-3 py-2 bg-[#0d1322] border border-[#232f48] rounded-lg text-white font-mono focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-[#8b95a6] mb-1 font-medium">Label / Description</label>
                <input
                  type="text"
                  value={newParam.label || ''}
                  onChange={e => setNewParam({ ...newParam, label: e.target.value })}
                  placeholder="e.g. Breakout Filter Threshold"
                  className="w-full px-3 py-2 bg-[#0d1322] border border-[#232f48] rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#8b95a6] mb-1 font-medium">Category</label>
                  <select
                    value={newParam.category || 'custom'}
                    onChange={e => setNewParam({ ...newParam, category: e.target.value as any })}
                    className="w-full px-2.5 py-2 bg-[#0d1322] border border-[#232f48] rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="core">Core Strategy</option>
                    <option value="timing">Session / Timing</option>
                    <option value="risk">Risk & Compliance</option>
                    <option value="indicator">Indicator Filter</option>
                    <option value="custom">Custom</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[#8b95a6] mb-1 font-medium">Mode</label>
                  <select
                    value={newParam.mode || 'fixed'}
                    onChange={e => setNewParam({ ...newParam, mode: e.target.value as any })}
                    className="w-full px-2.5 py-2 bg-[#0d1322] border border-[#232f48] rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="fixed">Fixed (Constant)</option>
                    <option value="optimize">Optimize (Range)</option>
                  </select>
                </div>
              </div>

              {newParam.mode === 'fixed' ? (
                <div>
                  <label className="block text-[#8b95a6] mb-1 font-medium">Fixed Value</label>
                  <input
                    type="text"
                    value={newParam.fixedValue !== undefined ? newParam.fixedValue : ''}
                    onChange={e => setNewParam({ ...newParam, fixedValue: e.target.value })}
                    placeholder="e.g. 15 or 1.5"
                    className="w-full px-3 py-2 bg-[#0d1322] border border-[#232f48] rounded-lg text-white font-mono focus:outline-none focus:border-blue-500"
                  />
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-[#8b95a6] mb-1 font-medium">Start</label>
                    <input
                      type="number"
                      step="any"
                      value={newParam.range?.start || 0}
                      onChange={e => setNewParam({ 
                        ...newParam, 
                        range: { ...newParam.range!, start: parseFloat(e.target.value) || 0 } 
                      })}
                      className="w-full px-2.5 py-1.5 bg-[#0d1322] border border-amber-800/60 rounded-lg text-amber-200 font-mono focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[#8b95a6] mb-1 font-medium">Step</label>
                    <input
                      type="number"
                      step="any"
                      value={newParam.range?.step || 1}
                      onChange={e => setNewParam({ 
                        ...newParam, 
                        range: { ...newParam.range!, step: parseFloat(e.target.value) || 1 } 
                      })}
                      className="w-full px-2.5 py-1.5 bg-[#0d1322] border border-amber-800/60 rounded-lg text-amber-200 font-mono focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[#8b95a6] mb-1 font-medium">Stop</label>
                    <input
                      type="number"
                      step="any"
                      value={newParam.range?.stop || 10}
                      onChange={e => setNewParam({ 
                        ...newParam, 
                        range: { ...newParam.range!, stop: parseFloat(e.target.value) || 10 } 
                      })}
                      className="w-full px-2.5 py-1.5 bg-[#0d1322] border border-amber-800/60 rounded-lg text-amber-200 font-mono focus:outline-none focus:border-amber-500"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#232f48]">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-[#8b95a6] hover:text-white hover:bg-[#1f293d]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleAddCustomParam}
                disabled={!newParam.name || !newParam.name.trim()}
                className="px-4 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white"
              >
                Add Parameter
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
