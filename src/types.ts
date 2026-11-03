export interface ParamRange {
  start: number;
  step: number;
  stop: number;
}

export interface ParamOption {
  value: string | number | boolean;
  label: string;
}

export interface StrategyParam {
  id?: string;
  name: string;
  label: string;
  type?: string;
  category: 'core' | 'timing' | 'risk' | 'indicator' | 'custom';
  indicatorId?: string;
  mode: 'fixed' | 'optimize';
  fixedValue: number | string | boolean;
  currentValue?: number | string | boolean;
  range: ParamRange;
  description?: string;
  isCustom?: boolean;
  isDropdown?: boolean;
  options?: Array<ParamOption | string>;
  optionValues?: Array<string | number | boolean>;
  isModified?: boolean;
}

export interface IndicatorDefinition {
  id: string;
  name: string;
  toggleParam: string;
  enabled: boolean;
  optimize: boolean;
  description: string;
  paramNames: string[];
}

export interface StrategyOptConfig {
  active_ea: string;
  indicator_toggles: Record<string, number | boolean>;
  fixed_params: Record<string, any>;
  opt_ranges: Record<string, [number, number, number]>;
  params: StrategyParam[];
  indicators: IndicatorDefinition[];
}

export interface PhaseQualificationCriteria {
  min_profit_gain_pct: number;
  max_drawdown_pct: number;
  min_avg_trades_month: number;
  min_sharpe_ratio: number;
  min_ret_dd_ratio: number;
  min_profit_factor: number;
  min_net_profit: number;
  min_total_trades: number;
  min_win_rate_pct: number;
}

export interface AllQualificationCriteria {
  train: PhaseQualificationCriteria;
  val: PhaseQualificationCriteria;
  holdout: PhaseQualificationCriteria;
}
