import { StrategyParam, IndicatorDefinition, StrategyOptConfig } from '../types';

export const DEFAULT_TRB_INDICATORS: IndicatorDefinition[] = [
  {
    id: 'ema',
    name: 'EMA Trend Filter',
    toggleParam: 'UseTrendFilter',
    enabled: true,
    optimize: false,
    description: 'Restricts trades to prevailing market trend direction (Buy above EMA, Sell below)',
    paramNames: ['EMAPeriod'],
  },
  {
    id: 'adx',
    name: 'ADX Volatility Filter',
    toggleParam: 'UseAdxFilter',
    enabled: true,
    optimize: true,
    description: 'Ensures breakout momentum is sufficiently strong before triggering entry',
    paramNames: ['AdxPeriod', 'AdxMin'],
  },
  {
    id: 'atr',
    name: 'ATR Range Filter',
    toggleParam: 'UseAtrFilter',
    enabled: true,
    optimize: true,
    description: 'Filters out low-volatility dead markets using Average True Range threshold',
    paramNames: ['AtrPeriod', 'AtrMinPips'],
  },
  {
    id: 'atr_trail',
    name: 'ATR Trailing Stop',
    toggleParam: 'UseAtrTrailingStop',
    enabled: false,
    optimize: false,
    description: 'Dynamic volatility-based trailing stop loss to lock in gains',
    paramNames: ['AtrTrailPeriod', 'AtrTrailMultiplier'],
  },
  {
    id: 'news',
    name: 'News Event Filter',
    toggleParam: 'UseNewsFilter',
    enabled: false,
    optimize: false,
    description: 'Avoids trading around scheduled high-impact economic news events',
    paramNames: ['NewsBlockMinutesBefore', 'NewsBlockMinutesAfter'],
  },
];

export const DEFAULT_TRB_PARAMS: StrategyParam[] = [
  // Core Strategy
  {
    name: 'LotSize',
    label: 'Fixed Lot Size',
    category: 'core',
    mode: 'fixed',
    fixedValue: 0.2,
    range: { start: 0.1, step: 0.05, stop: 0.5 },
    description: 'Default trade lot size when risk-based sizing is disabled',
  },
  {
    name: 'PipsOffset',
    label: 'Pips Offset',
    category: 'core',
    mode: 'fixed',
    fixedValue: 13,
    range: { start: 8, step: 1, stop: 20 },
    description: 'Buffer pips added above session high / below session low for pending orders',
  },
  {
    name: 'TPMultiplier',
    label: 'TP Multiplier',
    category: 'core',
    mode: 'fixed',
    fixedValue: 3.0,
    range: { start: 1.5, step: 0.5, stop: 4.5 },
    description: 'Take profit multiple relative to the measured breakout range',
  },
  {
    name: 'MinRangePips',
    label: 'Min Session Range (Pips)',
    category: 'core',
    mode: 'fixed',
    fixedValue: 25,
    range: { start: 15, step: 5, stop: 50 },
    description: 'Minimum required Tokyo session high-low range to place orders',
  },
  {
    name: 'MaxRangePips',
    label: 'Max Session Range (Pips)',
    category: 'core',
    mode: 'fixed',
    fixedValue: 180,
    range: { start: 100, step: 20, stop: 240 },
    description: 'Maximum allowable Tokyo session high-low range (avoids overextended days)',
  },
  {
    name: 'MagicNumber',
    label: 'Magic Number',
    category: 'core',
    mode: 'fixed',
    fixedValue: 881024,
    range: { start: 881000, step: 1, stop: 881050 },
    description: 'Unique EA order identifier for MetaTrader 5 position tracking',
  },

  // Timing & Session
  {
    name: 'StartHourGMT',
    label: 'Start Hour (GMT)',
    category: 'timing',
    mode: 'fixed',
    fixedValue: 0,
    range: { start: 0, step: 1, stop: 3 },
    description: 'Beginning hour of Tokyo session measurement period',
  },
  {
    name: 'EndHourGMT',
    label: 'End Hour (GMT)',
    category: 'timing',
    mode: 'fixed',
    fixedValue: 7,
    range: { start: 5, step: 1, stop: 9 },
    description: 'Ending hour of Tokyo session measurement when breakout orders are placed',
  },
  {
    name: 'CancelHourGMT',
    label: 'Cancel Hour (GMT)',
    category: 'timing',
    mode: 'fixed',
    fixedValue: 10,
    range: { start: 8, step: 1, stop: 14 },
    description: 'Hour to cancel unfilled pending breakout orders',
  },
  {
    name: 'CloseHourGMT',
    label: 'Close Hour (GMT)',
    category: 'timing',
    mode: 'fixed',
    fixedValue: 13,
    range: { start: 11, step: 1, stop: 17 },
    description: 'Hour to force-close any remaining open positions before London/NY overlap',
  },

  // Risk & Compliance
  {
    name: 'UseRiskBasedSizing',
    label: 'Risk-Based Sizing Toggle',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 0,
    range: { start: 0, step: 1, stop: 1 },
    description: 'Calculate lot size dynamically from stop loss distance & Risk Percent (0=Off, 1=On)',
  },
  {
    name: 'RiskPercent',
    label: 'Risk Percent (%)',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 1.0,
    range: { start: 0.25, step: 0.25, stop: 2.0 },
    description: 'Percentage of account equity risked per trade',
  },
  {
    name: 'UseMonthlyDDLimit',
    label: 'Monthly DD Limit Toggle',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 1,
    range: { start: 0, step: 1, stop: 1 },
    description: 'Compliance circuit-breaker: stop trading if monthly drawdown limit reached',
  },
  {
    name: 'MonthlyDDPercent',
    label: 'Monthly DD Limit (%)',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 3.0,
    range: { start: 2.0, step: 0.5, stop: 5.0 },
    description: 'Maximum allowable percentage drawdown within a calendar month',
  },
  {
    name: 'UseDailyLossLimit',
    label: 'Daily Loss Limit Toggle',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 1,
    range: { start: 0, step: 1, stop: 1 },
    description: 'Compliance circuit-breaker: halt trading for the day if daily limit reached',
  },
  {
    name: 'DailyLossPercent',
    label: 'Daily Loss Limit (%)',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 4.0,
    range: { start: 2.0, step: 0.5, stop: 6.0 },
    description: 'Maximum allowable percentage loss in a single trading day',
  },

  // Indicator Parameters
  {
    name: 'EMAPeriod',
    label: 'EMA Trend Period',
    category: 'indicator',
    indicatorId: 'ema',
    mode: 'fixed',
    fixedValue: 200,
    range: { start: 50, step: 25, stop: 300 },
    description: 'Exponential Moving Average period for trend filtering',
  },
  {
    name: 'AdxPeriod',
    label: 'ADX Period',
    category: 'indicator',
    indicatorId: 'adx',
    mode: 'optimize',
    fixedValue: 14,
    range: { start: 7, step: 1, stop: 21 },
    description: 'Average Directional Index calculation lookback bars',
  },
  {
    name: 'AdxMin',
    label: 'ADX Min Threshold',
    category: 'indicator',
    indicatorId: 'adx',
    mode: 'optimize',
    fixedValue: 20.0,
    range: { start: 15.0, step: 2.5, stop: 40.0 },
    description: 'Minimum required ADX value to confirm sufficient breakout trend power',
  },
  {
    name: 'AtrPeriod',
    label: 'ATR Period',
    category: 'indicator',
    indicatorId: 'atr',
    mode: 'optimize',
    fixedValue: 14,
    range: { start: 7, step: 1, stop: 21 },
    description: 'Average True Range lookback period',
  },
  {
    name: 'AtrMinPips',
    label: 'ATR Min (Pips)',
    category: 'indicator',
    indicatorId: 'atr',
    mode: 'optimize',
    fixedValue: 0.0,
    range: { start: 0.0, step: 2.0, stop: 30.0 },
    description: 'Minimum required ATR volatility in pips before entering a trade',
  },
  {
    name: 'AtrTrailPeriod',
    label: 'ATR Trail Period',
    category: 'indicator',
    indicatorId: 'atr_trail',
    mode: 'fixed',
    fixedValue: 14,
    range: { start: 7, step: 1, stop: 21 },
    description: 'ATR period for dynamic trailing stop loss calculations',
  },
  {
    name: 'AtrTrailMultiplier',
    label: 'ATR Trail Multiplier',
    category: 'indicator',
    indicatorId: 'atr_trail',
    mode: 'fixed',
    fixedValue: 2.0,
    range: { start: 1.0, step: 0.5, stop: 4.0 },
    description: 'Multiplier of ATR distance behind current market price for trailing stop',
  },
  {
    name: 'NewsBlockMinutesBefore',
    label: 'News Block Mins Before',
    category: 'indicator',
    indicatorId: 'news',
    mode: 'fixed',
    fixedValue: 30,
    range: { start: 15, step: 15, stop: 60 },
    description: 'Window in minutes prior to high impact news release to freeze new orders',
  },
  {
    name: 'NewsBlockMinutesAfter',
    label: 'News Block Mins After',
    category: 'indicator',
    indicatorId: 'news',
    mode: 'fixed',
    fixedValue: 30,
    range: { start: 15, step: 15, stop: 60 },
    description: 'Window in minutes after high impact news release before resuming orders',
  },
];

export const DEFAULT_ORB_INDICATORS: IndicatorDefinition[] = [
  {
    id: 'ema',
    name: 'EMA Filter',
    toggleParam: 'InpUseEmaFilter',
    enabled: true,
    optimize: false,
    description: 'Trade only in direction of EMA slope / trend',
    paramNames: ['InpEmaTradeWithTrend'],
  },
  {
    id: 'rsi',
    name: 'RSI Filter',
    toggleParam: 'InpUseRsiFilter',
    enabled: false,
    optimize: false,
    description: 'Avoid trading into overbought or oversold extremes',
    paramNames: ['InpRsiPeriod', 'InpRsiUpper', 'InpRsiLower'],
  },
  {
    id: 'atr',
    name: 'ATR Filter',
    toggleParam: 'InpUseAtrFilter',
    enabled: false,
    optimize: false,
    description: 'Requires minimum ATR threshold',
    paramNames: ['InpAtrPeriod', 'InpAtrMin'],
  },
  {
    id: 'adx',
    name: 'ADX Filter',
    toggleParam: 'InpUseAdxFilter',
    enabled: false,
    optimize: false,
    description: 'Requires minimum ADX strength',
    paramNames: ['InpAdxPeriod', 'InpAdxMin'],
  },
  {
    id: 'macd',
    name: 'MACD Filter',
    toggleParam: 'InpUseMacdFilter',
    enabled: true,
    optimize: true,
    description: 'Histogram confirmation filter',
    paramNames: ['InpMacdFast', 'InpMacdSlow', 'InpMacdSignal'],
  },
  {
    id: 'htf',
    name: 'Higher Timeframe Filter',
    toggleParam: 'InpUseHtfFilter',
    enabled: false,
    optimize: false,
    description: 'Higher timeframe EMA trend alignment',
    paramNames: ['InpHtfEmaPeriod'],
  },
];

export const DEFAULT_ORB_PARAMS: StrategyParam[] = [
  // Core Strategy
  {
    name: 'InpTPRatio',
    label: 'TP Ratio',
    category: 'core',
    mode: 'optimize',
    fixedValue: 1.5,
    range: { start: 1.0, step: 0.25, stop: 3.0 },
    description: 'Take profit ratio relative to breakout range',
  },
  {
    name: 'InpSLBufferPips',
    label: 'SL Buffer Pips',
    category: 'core',
    mode: 'optimize',
    fixedValue: 1,
    range: { start: 0, step: 1, stop: 10 },
    description: 'Stop loss buffer pips beyond range high/low',
  },
  {
    name: 'InpMaxRangePips',
    label: 'Max Range Pips',
    category: 'core',
    mode: 'optimize',
    fixedValue: 50,
    range: { start: 30, step: 10, stop: 150 },
    description: 'Maximum allowable breakout range in pips',
  },
  {
    name: 'InpFixedLotSize',
    label: 'Fixed Lot Size',
    category: 'core',
    mode: 'fixed',
    fixedValue: 1.0,
    range: { start: 0.1, step: 0.1, stop: 2.0 },
    description: 'Lot size if risk sizing is off',
  },
  {
    name: 'InpRiskPercent',
    label: 'Risk Percent (%)',
    category: 'risk',
    mode: 'optimize',
    fixedValue: 1.0,
    range: { start: 0.25, step: 0.25, stop: 2.0 },
    description: 'Risk percentage per trade',
  },
  {
    name: 'InpUseRiskBasedSizing',
    label: 'Use Risk Sizing',
    category: 'risk',
    mode: 'fixed',
    fixedValue: 1,
    range: { start: 0, step: 1, stop: 1 },
    description: 'Position sizing mode (1=Risk %, 0=Fixed)',
  },
  {
    name: 'InpUseRetestConfirmation',
    label: 'Retest Confirmation',
    category: 'core',
    mode: 'optimize',
    fixedValue: 0,
    range: { start: 0, step: 1, stop: 1 },
    description: 'Require breakout retest before entry (0=Off, 1=On)',
  },
  {
    name: 'InpRetestTolerancePips',
    label: 'Retest Tolerance Pips',
    category: 'core',
    mode: 'optimize',
    fixedValue: 1.0,
    range: { start: 0.5, step: 0.5, stop: 5.0 },
    description: 'Tolerance distance for price retest touch',
  },
  {
    name: 'InpRetestMaxBars',
    label: 'Retest Max Bars',
    category: 'core',
    mode: 'optimize',
    fixedValue: 10,
    range: { start: 5, step: 5, stop: 30 },
    description: 'Maximum candles to wait for retest touch',
  },
  {
    name: 'InpRangeStartHour',
    label: 'Range Start Hour',
    category: 'timing',
    mode: 'optimize',
    fixedValue: 8,
    range: { start: 6, step: 1, stop: 10 },
    description: 'Hour when range measurement begins',
  },
  {
    name: 'InpRangeEndHour',
    label: 'Range End Hour',
    category: 'timing',
    mode: 'optimize',
    fixedValue: 9,
    range: { start: 9, step: 1, stop: 12 },
    description: 'Hour when range measurement closes',
  },
  {
    name: 'InpEntryCutoffHour',
    label: 'Entry Cutoff Hour',
    category: 'timing',
    mode: 'optimize',
    fixedValue: 15,
    range: { start: 12, step: 1, stop: 20 },
    description: 'Last hour permitted to trigger a trade',
  },
  {
    name: 'InpMagicNumber',
    label: 'Magic Number',
    category: 'core',
    mode: 'fixed',
    fixedValue: 20240101,
    range: { start: 20240100, step: 1, stop: 20240200 },
    description: 'Order magic number',
  },

  // ORB Indicators
  {
    name: 'InpEmaTradeWithTrend',
    label: 'EMA Trend With/Against',
    category: 'indicator',
    indicatorId: 'ema',
    mode: 'fixed',
    fixedValue: 0,
    range: { start: 0, step: 1, stop: 1 },
    description: '0 = trade with trend, 1 = counter-trend',
  },
  {
    name: 'InpRsiPeriod',
    label: 'RSI Period',
    category: 'indicator',
    indicatorId: 'rsi',
    mode: 'fixed',
    fixedValue: 14,
    range: { start: 7, step: 1, stop: 21 },
    description: 'RSI lookback period',
  },
  {
    name: 'InpRsiUpper',
    label: 'RSI Upper Band',
    category: 'indicator',
    indicatorId: 'rsi',
    mode: 'fixed',
    fixedValue: 70.0,
    range: { start: 60.0, step: 2.5, stop: 85.0 },
    description: 'Overbought boundary',
  },
  {
    name: 'InpRsiLower',
    label: 'RSI Lower Band',
    category: 'indicator',
    indicatorId: 'rsi',
    mode: 'fixed',
    fixedValue: 30.0,
    range: { start: 15.0, step: 2.5, stop: 40.0 },
    description: 'Oversold boundary',
  },
  {
    name: 'InpAtrPeriod',
    label: 'ATR Period',
    category: 'indicator',
    indicatorId: 'atr',
    mode: 'fixed',
    fixedValue: 14,
    range: { start: 7, step: 1, stop: 21 },
    description: 'ATR period',
  },
  {
    name: 'InpAtrMin',
    label: 'ATR Min',
    category: 'indicator',
    indicatorId: 'atr',
    mode: 'fixed',
    fixedValue: 0.0,
    range: { start: 0.0, step: 0.5, stop: 5.0 },
    description: 'Minimum ATR threshold',
  },
  {
    name: 'InpAdxPeriod',
    label: 'ADX Period',
    category: 'indicator',
    indicatorId: 'adx',
    mode: 'fixed',
    fixedValue: 14,
    range: { start: 7, step: 1, stop: 21 },
    description: 'ADX period',
  },
  {
    name: 'InpAdxMin',
    label: 'ADX Min Level',
    category: 'indicator',
    indicatorId: 'adx',
    mode: 'fixed',
    fixedValue: 20.0,
    range: { start: 15.0, step: 2.5, stop: 40.0 },
    description: 'Minimum ADX strength',
  },
  {
    name: 'InpMacdFast',
    label: 'MACD Fast EMA',
    category: 'indicator',
    indicatorId: 'macd',
    mode: 'optimize',
    fixedValue: 12,
    range: { start: 6, step: 1, stop: 16 },
    description: 'MACD fast exponential moving average',
  },
  {
    name: 'InpMacdSlow',
    label: 'MACD Slow EMA',
    category: 'indicator',
    indicatorId: 'macd',
    mode: 'optimize',
    fixedValue: 26,
    range: { start: 18, step: 2, stop: 34 },
    description: 'MACD slow exponential moving average',
  },
  {
    name: 'InpMacdSignal',
    label: 'MACD Signal Period',
    category: 'indicator',
    indicatorId: 'macd',
    mode: 'optimize',
    fixedValue: 9,
    range: { start: 5, step: 1, stop: 13 },
    description: 'MACD signal line smoothing period',
  },
  {
    name: 'InpHtfEmaPeriod',
    label: 'HTF EMA Period',
    category: 'indicator',
    indicatorId: 'htf',
    mode: 'fixed',
    fixedValue: 50,
    range: { start: 20, step: 10, stop: 100 },
    description: 'Higher timeframe EMA lookback',
  },
];

/**
 * Builds clean export config for run_optimization.py
 */
export function buildOptimizationConfig(
  activeEa: string,
  params: StrategyParam[],
  indicators: IndicatorDefinition[]
): StrategyOptConfig {
  const fixed_params: Record<string, any> = {};
  const opt_ranges: Record<string, [number, number, number]> = {};
  const indicator_toggles: Record<string, number> = {};

  // Build toggles
  indicators.forEach(ind => {
    indicator_toggles[ind.toggleParam] = ind.enabled ? 1 : 0;
  });

  // Assign fixed vs optimize
  params.forEach(p => {
    // If parameter belongs to an indicator that is disabled, keep in fixed as 0 or default
    if (p.indicatorId) {
      const parentInd = indicators.find(i => i.id === p.indicatorId);
      if (parentInd && !parentInd.enabled) {
        // Disabled indicator
        fixed_params[p.name] = p.fixedValue;
        return;
      }
    }

    if (p.mode === 'fixed') {
      const numeric = Number(p.fixedValue);
      fixed_params[p.name] = !isNaN(numeric) && typeof p.fixedValue !== 'boolean' ? numeric : p.fixedValue;
    } else {
      const start = Number(p.range.start);
      const step = Number(p.range.step) > 0 ? Number(p.range.step) : 1;
      const stop = Number(p.range.stop) >= start ? Number(p.range.stop) : start;
      opt_ranges[p.name] = [start, step, stop];
    }
  });

  return {
    active_ea: activeEa,
    indicator_toggles,
    fixed_params,
    opt_ranges,
    params,
    indicators,
  };
}

export function getDefaultConfigForEa(ea: string): { params: StrategyParam[]; indicators: IndicatorDefinition[] } {
  if (ea?.toUpperCase() === 'ORB') {
    return {
      params: JSON.parse(JSON.stringify(DEFAULT_ORB_PARAMS)),
      indicators: JSON.parse(JSON.stringify(DEFAULT_ORB_INDICATORS)),
    };
  }
  return {
    params: JSON.parse(JSON.stringify(DEFAULT_TRB_PARAMS)),
    indicators: JSON.parse(JSON.stringify(DEFAULT_TRB_INDICATORS)),
  };
}
