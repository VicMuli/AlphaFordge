"""
run_optimization.py - Multi-Symbol Strategy Optimization & Validation Pipeline

Flow
----
  1. MT5 genetic optimization over Train period
  2. Top-N passes -> Train / Validation / Holdout single backtests (sequential gates)
  3. Survivors -> Monte Carlo certification  (printed to terminal + Word doc per candidate)
  4. MC survivors -> copied into 'passed_candidates' folder for manual Walk Forward testing
     Walk Forward stability testing is run MANUALLY one-by-one after the pipeline completes.
"""

import sys
import datetime
import json
import time
from pathlib import Path

# Prevent Windows console UnicodeEncodeError when running on cp1252 / charmap environments
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd
try:
    import docx
except ImportError:
    pass

# -- project imports ---------------------------------------------------------
from mt5_optimizer import (
    generate_optimization_set_file,
    run_optimization as _run_mt5_opt,
    parse_optimization_results,
    print_top_results,
)
from mt5_runner import run_single_backtest
from report_analysis import analyze
from monte_carlo import certify_strategy, print_certification_result
from walk_forward import (
    generate_rolling_windows,
    run_walk_forward,
    build_walk_forward_table,
    compute_stability_stats,
    _print_stability_report,
)
from strategy_builder import (
    check_train_criteria,
    check_oos_criteria,
    check_phase_criteria,
    get_qualification_criteria,
    _normalise_opt_row,
    _extract_opt_ea_params,
    _deals_to_trades,
    _make_single_test_set_file,
    _fmt_curated,
)

# ===========================================================================
#  USER CONFIGURATION - edit everything in this block before running
# ===========================================================================

TERMINAL_PATH     = r'C:\Users\HP\AppData\Roaming\MetaTrader\terminal64.exe'
TERMINAL_DATA_DIR = r'C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\CDE1ED2F37049DA2E508A3C44B675D09'

EXPERT     = 'TRB V2.0.ex5'
PERIOD     = 'M15'

LOGIN    = 52909674
PASSWORD = '3F!@4rwo7wc02f'
SERVER   = 'ICMarketsKE-Demo'

DEPOSIT  = 2500
CURRENCY = 'USD'
LEVERAGE = '1:100'

_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_FILE = _SCRIPT_DIR / "config.json"
_CFG = {}
if _CONFIG_FILE.exists():
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as _f:
            _CFG = json.load(_f)
    except Exception:
        pass

# -- MULTI-EA SWITCHBOARD ---------------------------------------------------
# Change ACTIVE_EA to run the pipeline against a different Expert Advisor.
# Loads active_ea from config.json (or defaults to 'TRB').
ACTIVE_EA = _CFG.get("active_ea", "TRB").upper()

# -- MULTI-SYMBOL SWITCHBOARD ----------------------------------------------
# Change TARGET_SYMBOL to run optimization for different Forex markets.
_cfg_sym = _CFG.get("symbol_key") or _CFG.get("symbol", "USDJPY")
if " " in _cfg_sym:
    _cfg_sym = _cfg_sym.split()[0].upper()
TARGET_SYMBOL = _cfg_sym if _cfg_sym in ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "XAUUSD"] else "USDJPY"

# Shared across EAs -- just the MT5 symbol name and its pip size. Anything
# EA-specific (which parameters get optimized, over what range) lives in
# that EA's own section below instead, since ORB and TRB don't share an
# input schema at all.
SYMBOL_CONFIGS = {
    "EURUSD": {"symbol_mt5": "EURUSD dukascopy", "pip_size": 0.0001},
    "GBPUSD": {"symbol_mt5": "GBPUSD dukascopy", "pip_size": 0.0001},
    "USDJPY": {"symbol_mt5": "USDJPY Dukascopy", "pip_size": 0.01},
    "EURJPY": {"symbol_mt5": "EURJPY Dukascopy", "pip_size": 0.01},
    "XAUUSD": {"symbol_mt5": "XAUUSD dukascopy", "pip_size": 0.10},
}

# Resolve active symbol parameters
_active_cfg = SYMBOL_CONFIGS[TARGET_SYMBOL]
SYMBOL      = 'USDJPY Dukascopy'
SYMBOL_KEY  = 'USDPY'
PIP_SIZE    = _active_cfg["pip_size"]


# -- Core (non-indicator) fixed params, ORB -------------------------------
ORB_CORE_FIXED_PARAMS = {
    "InpMagicNumber":       20240101,
    "InpMinTotalTrades":    30,
    "InpMinTradesPerMonth": 5.0,
    "InpMaxDDSoftPct":      10.0,
    "InpUseRiskBasedSizing": 1,
    "InpFixedLotSize":       1,
}

# ORB's per-symbol InpMaxRangePips search range (start, step, stop)
ORB_MAX_RANGE_OPT_BY_SYMBOL = {
    "EURUSD": (30, 10, 150),
    "GBPUSD": (40, 10, 200),
    "USDJPY": (30, 10, 150),
    "EURJPY": (40, 10, 200),
    "XAUUSD": (50, 25, 500),
}

# -- Core (non-indicator) optimization ranges, ORB  (start, step, stop) ----
ORB_CORE_OPT_RANGES_BASE = {
    "InpTPRatio":         (1.0, 0.25, 3.0),
    "InpSLBufferPips":    (0,   1,    10),
    "InpRangeStartHour":  (6,   1,    10),
    "InpRangeEndHour":    (9,   1,    12),
    "InpEntryCutoffHour": (12,  1,    20),
    "InpRiskPercent":     (0.25, 0.25, 2.0),

    # -- Break-and-retest confluence, tested as a base parameter --
    # InpUseRetestConfirmation is (0, 1, 1) -- a genuine 0/1 toggle, not a
    # numeric range -- so the optimizer itself decides whether requiring a
    # retest helps at all, rather than forcing it on and only tuning its
    # sub-parameters. InpRetestTolerancePips/InpRetestMaxBars still get
    # swept across their full range even for genomes where the toggle
    # lands on 0 (they're simply inert in that case) -- mildly wasteful
    # but harmless, and simpler than conditioning one param's range on
    # another's value within a single flat genetic search.
    "InpUseRetestConfirmation": (0,   1,   1),
    "InpRetestTolerancePips":   (0.5, 0.5, 5.0),
    "InpRetestMaxBars":         (5,   5,   30),
}

# ===========================================================================
#  ORB INDICATOR FILTER SWITCHBOARD
# ===========================================================================
ORB_INDICATOR_FILTERS = {
    "ema": {
        "toggle":     "InpUseEmaFilter",
        "enabled":    True,
        "optimize":   False,
        "defaults":   {"InpEmaTradeWithTrend": 0},
        "ranges":     {"InpEmaTradeWithTrend": (0, 1, 1)},
    },
    "rsi": {
        "toggle":     "InpUseRsiFilter",
        "enabled":    False,
        "optimize":   False,
        "defaults":   {"InpRsiPeriod": 14, "InpRsiUpper": 70.0, "InpRsiLower": 30.0},
        "ranges": {
            "InpRsiPeriod": (7,  1,   21),
            "InpRsiUpper":  (60, 2.5, 85),
            "InpRsiLower":  (15, 2.5, 40),
        },
    },
    "atr": {
        "toggle":     "InpUseAtrFilter",
        "enabled":    False,
        "optimize":   False,
        "defaults":   {"InpAtrPeriod": 14, "InpAtrMin": 0.0},
        "ranges": {
            "InpAtrPeriod": (7,   1,   21),
            "InpAtrMin":    (0,   0.5, 5.0),
        },
    },
    "adx": {
        "toggle":     "InpUseAdxFilter",
        "enabled":    False,
        "optimize":   False,
        "defaults":   {"InpAdxPeriod": 14, "InpAdxMin": 20.0},
        "ranges": {
            "InpAdxPeriod": (7,  1,   21),
            "InpAdxMin":    (15, 2.5, 40),
        },
    },
    "macd": {
        "toggle":     "InpUseMacdFilter",
        "enabled":    True,
        "optimize":   True,
        "defaults":   {"InpMacdFast": 12, "InpMacdSlow": 26, "InpMacdSignal": 9},
        "ranges": {
            "InpMacdFast":   (6,  1, 16),
            "InpMacdSlow":   (18, 2, 34),
            "InpMacdSignal": (5,  1, 13),
        },
    },
    "htf": {
        "toggle":     "InpUseHtfFilter",
        "enabled":    False,
        "optimize":   False,
        "defaults":   {"InpHtfEmaPeriod": 50},
        "ranges":     {"InpHtfEmaPeriod": (20, 10, 100)},
    },
}


def _build_fixed_and_ranges(core_fixed: dict, core_ranges: dict,
                             indicator_filters: dict) -> tuple[dict, dict]:
    """EA-agnostic: merges a core fixed dict + core ranges dict with a
    toggle/optimize/defaults/ranges indicator-filter switchboard. Used by
    every EA's builder function below -- the switchboard MECHANISM is
    shared, but each EA supplies its own core dicts and its own filter
    grid, so nothing about one EA's filters leaks into another's."""
    fixed  = dict(core_fixed)
    ranges = dict(core_ranges)

    active_optimizing = []
    for name, cfg in indicator_filters.items():
        fixed[cfg["toggle"]] = 1 if cfg["enabled"] else 0

        if cfg["enabled"] and cfg["optimize"]:
            ranges.update(cfg["ranges"])
            active_optimizing.append(name)
        else:
            fixed.update(cfg["defaults"])

    if len(active_optimizing) > 1:
        print(f"  Indicator round: optimizing {active_optimizing} TOGETHER as a pair/group.")
    elif active_optimizing:
        print(f"  Indicator round: optimizing [{active_optimizing[0]}]")

    return fixed, ranges


def _build_orb_fixed_and_ranges(symbol_key: str, pip_size: float) -> tuple[dict, dict]:
    fixed = dict(ORB_CORE_FIXED_PARAMS)
    fixed["InpPipSize"] = pip_size
    ranges = dict(ORB_CORE_OPT_RANGES_BASE)
    ranges["InpMaxRangePips"] = ORB_MAX_RANGE_OPT_BY_SYMBOL[symbol_key]
    return _build_fixed_and_ranges(fixed, ranges, ORB_INDICATOR_FILTERS)


# ===========================================================================
#  TRB (Tokyo Range Breakout) -- USDJPY / EURJPY only
# ===========================================================================
# TRB has no InpPipSize input (computes pip size internally from
# SYMBOL_DIGITS), so unlike ORB's builder there's no pip_size injection
# step here -- it's accepted as a parameter only for a consistent function
# signature across EA_CONFIGS["build"] entries.

# -- Core (non-filter) fixed params, TRB -----------------------------------
# Risk/compliance controls -- FIXED, not optimized, and NOT part of the
# indicator-filter switchboard below. These exist for account preservation
# and prop-firm rule compliance, not to chase backtest performance --
# letting the optimizer loosen them in search of a better-looking curve
# would defeat their entire purpose. (Unlike the switchboard's filters,
# there's no meaningful "test with this off" experiment to run on these.)
#
# BASE-PARAMETER ROUND CLOSED (USDJPY): the values below are the winning
# combination that cleared train/val/holdout, now frozen so the indicator
# round below can't drift them. If you ever point this same config at
# EURJPY, revisit LotSize/PipsOffset/TPMultiplier/MinRangePips/MaxRangePips
# specifically -- these were tuned for USDJPY's range characteristics, not
# EURJPY's (which historically runs a wider Tokyo-session range).
#
# GAP FIXED HERE: UseRiskBasedSizing/RiskPercent were added to the EA but
# never wired into this file, so the base-parameter round that produced
# these numbers ran with RiskPercent stuck at the EA's compiled default
# (1.0%) for every single pass -- it was never actually searched. Added
# below as a genuine optimizable range this round, since the sizing
# question isn't actually settled yet, just untested across values.
TRB_CORE_FIXED_PARAMS = {
    "MagicNumber":       881024,
    "UseMonthlyDDLimit": 1,
    "MonthlyDDPercent":  3.0,
    "UseDailyLossLimit": 1,
    "DailyLossPercent":  4.0,

    # -- Winning base parameters (USDJPY), frozen --
    "LotSize":         0.2,    # fallback only now -- see UseRiskBasedSizing below
    "PipsOffset":      13,
    "TPMultiplier":    3.0,
    "StartHourGMT":    0,
    "EndHourGMT":      7,
    "CancelHourGMT":   10,
    "CloseHourGMT":    13,
    "MinRangePips":    25,
    "MaxRangePips":    180,

    "UseRiskBasedSizing": 0,
}

# ===========================================================================
#  TRB INDICATOR FILTER SWITCHBOARD
# ===========================================================================
# Same toggle/optimize/defaults/ranges mechanism as ORB's, but TRB's own
# filters -- entirely separate grid, nothing shared with ORB_INDICATOR_FILTERS.
# Only genuinely optional, tunable confirmation layers live here (things
# with a real "what if this were off" experiment); the hard compliance
# controls (daily/monthly DD) stay in TRB_CORE_FIXED_PARAMS above, since
# there's no meaningful experiment to run by turning those off.
TRB_INDICATOR_FILTERS = {
    "ema": {
        "toggle":     "UseTrendFilter",
        "enabled":    True,     # held fixed ON at its existing default -- not under test this round
        "optimize":   False,
        "defaults":   {"EMAPeriod": 200},
        "ranges":     {"EMAPeriod": (50, 25, 300)},
        # NOTE: unlike ORB's EMA filter, TRB's trend direction isn't a
        # separate input -- it's hardcoded trend-following (buy only above
        # EMA, sell only below) in PlaceTokyoOrders(). No InpEmaTradeWithTrend
        # equivalent exists to expose here without editing the .mq5 first.
    },
    "news": {
        "toggle":     "UseNewsFilter",
        "enabled":    False,     # held fixed ON at its existing default -- not under test this round
        "optimize":   False,
        "defaults":   {"NewsBlockMinutesBefore": 30, "NewsBlockMinutesAfter": 30},
        "ranges": {
            "NewsBlockMinutesBefore": (15, 15, 60),
            "NewsBlockMinutesAfter":  (15, 15, 60),
        },
        # CAVEAT (see earlier notes): the hardcoded news-event table only
        # covers 2025-2026, so this filter is a no-op for essentially all
        # of TRAIN (2013-2021) and most of VAL (2021-2024) regardless of
        # what this toggle/ranges say -- it only does anything once the
        # backtest reaches populated dates.
    },
    "risk_sizing": {
        "toggle":     "UseRiskBasedSizing",
        "enabled":    False,     # held fixed ON -- see gap note above; RiskPercent itself IS under test
        "optimize":   False,
        "defaults":   {"RiskPercent": 1.0},
        "ranges":     {"RiskPercent": (0.25, 0.25, 2.0)},
    },
    "adx": {
        "toggle":     "UseAdxFilter",
        "enabled":    True,     # <-- THIS ROUND: testing ADX + ATR + ATR-trail together
        "optimize":   True,
        "defaults":   {"AdxPeriod": 14, "AdxMin": 20.0},
        "ranges": {
            "AdxPeriod": (7,  1,   21),
            "AdxMin":    (15, 2.5, 40),
        },
    },
    "atr": {
        "toggle":     "UseAtrFilter",
        "enabled":    True,
        "optimize":   True,
        "defaults":   {"AtrPeriod": 14, "AtrMinPips": 0.0},
        "ranges": {
            "AtrPeriod":  (7, 1,   21),
            # NOTE: USDJPY's pip size (0.01) means M15 ATR values run much
            # larger in raw "pips" than ORB's EURUSD M1 ATR did -- this
            # range is a reasonable starting guess, not derived from an
            # actual observed ATR distribution for this pair/timeframe.
            # Check the first pass's ATR values and narrow this if the
            # search is spending most of its time outside where the real
            # data actually lives.
            "AtrMinPips": (0, 2, 30),
        },
    },
    "atr_trail": {
        "toggle":     "UseAtrTrailingStop",
        "enabled":    False,
        "optimize":   False,
        "defaults":   {"AtrTrailPeriod": 14, "AtrTrailMultiplier": 2.0},
        "ranges": {
            "AtrTrailPeriod":     (7,   1,   21),
            "AtrTrailMultiplier": (1.0, 0.5, 4.0),
        },
    },
}


def _build_trb_fixed_and_ranges(symbol_key: str, pip_size: float) -> tuple[dict, dict]:
    fixed  = dict(TRB_CORE_FIXED_PARAMS)
    ranges = {}   # base params are now frozen (see TRB_CORE_FIXED_PARAMS) -- only the
                  # indicator switchboard's active entries contribute to OPT_RANGES this round
    return _build_fixed_and_ranges(fixed, ranges, TRB_INDICATOR_FILTERS)


# ===========================================================================
#  EA REGISTRY -- resolves ACTIVE_EA into an expert file, valid symbol list,

#  and a fixed/optimizable-parameter builder function.
# ===========================================================================
EA_CONFIGS = {
    "ORB": {
        "expert":        "ORBEU1.ex5",
        "valid_symbols": ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "XAUUSD"],
        "build":         _build_orb_fixed_and_ranges,
    },
    "TRB": {
        "expert":        "TRB v1.8.ex5",
        "valid_symbols": ["USDJPY", "EURJPY"],
        "build":         _build_trb_fixed_and_ranges,
    },
}

if ACTIVE_EA not in EA_CONFIGS:
    ea_folder = _SCRIPT_DIR / "researched_strategies" / ACTIVE_EA
    if ea_folder.exists():
        ex5_files = list(ea_folder.glob("*.ex5"))
        expert_file = ex5_files[0].name if ex5_files else f"{ACTIVE_EA}.ex5"

        def _build_dynamic_mql5(symbol_key: str, pip_size: float) -> tuple[dict, dict]:
            try:
                import mql5_parser
                parsed = mql5_parser.get_strategy_mql5_config(ACTIVE_EA)
                fixed = {}
                ranges = {}
                for ind in parsed.get("indicators", []):
                    fixed[ind["toggleParam"]] = 1 if ind.get("enabled") else 0
                for p in parsed.get("params", []):
                    if p.get("mode") == "optimize":
                        rng = p.get("range", {})
                        ranges[p["name"]] = (rng.get("start", 0), rng.get("step", 1), rng.get("stop", 10))
                    else:
                        fixed[p["name"]] = p.get("fixedValue", 0)
                return fixed, ranges
            except Exception:
                return {}, {}

        EA_CONFIGS[ACTIVE_EA] = {
            "expert": expert_file,
            "valid_symbols": list(SYMBOL_CONFIGS.keys()),
            "build": _build_dynamic_mql5,
        }
    else:
        raise SystemExit(f"Unknown ACTIVE_EA '{ACTIVE_EA}'. Choices: {list(EA_CONFIGS)} or any folder in researched_strategies")

_ea_cfg = EA_CONFIGS[ACTIVE_EA]
if TARGET_SYMBOL not in _ea_cfg["valid_symbols"]:
    raise SystemExit(
        f"TARGET_SYMBOL '{TARGET_SYMBOL}' is not valid for ACTIVE_EA '{ACTIVE_EA}'.\n"
        f"{ACTIVE_EA} is only set up for: {_ea_cfg['valid_symbols']}\n"
        f"Either change TARGET_SYMBOL, or switch ACTIVE_EA."
    )

EXPERT = _CFG.get("expert") or _ea_cfg.get("expert", f"{ACTIVE_EA}.ex5")

# -- Date windows ---------------------------------------------------------
TRAIN_FROM   = '2013.01.01'
TRAIN_TO     = '2022.01.01'
VAL_FROM     = '2022.01.01'
VAL_TO       = '2024.01.01'
HOLDOUT_FROM = '2024.01.01'
HOLDOUT_TO   = '2026.07.03'


def _months_between(from_str: str, to_str: str) -> float:
    """Months (average-length) between two 'YYYY.MM.DD' date strings, used
    for the trades-per-month check inside _gate()."""
    d1 = datetime.datetime.strptime(from_str, "%Y.%m.%d")
    d2 = datetime.datetime.strptime(to_str, "%Y.%m.%d")
    return (d2 - d1).days / 30.4375   # average days per month (365.25 / 12)


TRAIN_MONTHS   = _months_between(TRAIN_FROM, TRAIN_TO)
VAL_MONTHS     = _months_between(VAL_FROM, VAL_TO)
HOLDOUT_MONTHS = _months_between(HOLDOUT_FROM, HOLDOUT_TO)

# Dynamic Work Directory based on EA + Symbol, so ORB and TRB runs (and
# different symbols within each) never collide or overwrite each other.
_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_FILE = _SCRIPT_DIR / "config.json"
_BASE_WORK_DIR = _SCRIPT_DIR / "optimization_runs"
if _CONFIG_FILE.exists():
    try:
        with open(_CONFIG_FILE, "r") as _f:
            _cfg = json.load(_f)
            if _cfg.get("work_dir") and "MT5 runner" not in _cfg.get("work_dir"):
                _BASE_WORK_DIR = Path(_cfg["work_dir"])
    except Exception:
        pass

def _apply_optimization_config_overrides(fixed: dict, ranges: dict, cfg: dict, active_ea: str) -> tuple[dict, dict]:
    """
    Applies user-configured fixed parameters and optimization ranges from config.json.
    Allows adjusting which indicator or core strategy parameters should be fixed
    and the parameter ranges to optimize.
    """
    fixed = dict(fixed)
    ranges = dict(ranges)
    opt_cfg = cfg.get("optimization_params", {})
    if not opt_cfg:
        return fixed, ranges

    ea_cfg = opt_cfg.get(active_ea, opt_cfg)

    # 1. Indicator toggles
    toggles = ea_cfg.get("indicator_toggles", {})
    if isinstance(toggles, dict):
        for toggle_param, is_active in toggles.items():
            val = 1 if (is_active is True or is_active == 1 or str(is_active).lower() in ("true", "1", "yes")) else 0
            fixed[toggle_param] = val

    # 2. Structured params list
    params_list = ea_cfg.get("params", [])
    if isinstance(params_list, list):
        for p in params_list:
            if not isinstance(p, dict):
                continue
            name = p.get("name")
            if not name:
                continue
            mode = p.get("mode", "fixed")
            if mode == "fixed":
                ranges.pop(name, None)
                val = p.get("value", p.get("fixedValue", fixed.get(name, 0)))
                try:
                    if isinstance(val, str):
                        val = float(val) if "." in val else int(val)
                except ValueError:
                    pass
                fixed[name] = val
            elif mode == "optimize":
                fixed.pop(name, None)
                rng = p.get("range", {})
                if isinstance(rng, dict):
                    start = float(rng.get("start", 0))
                    step = float(rng.get("step", 1))
                    stop = float(rng.get("stop", 10))
                elif isinstance(rng, (list, tuple)) and len(rng) == 3:
                    start, step, stop = float(rng[0]), float(rng[1]), float(rng[2])
                else:
                    start = float(p.get("start", 0))
                    step = float(p.get("step", 1))
                    stop = float(p.get("stop", 10))
                if start.is_integer() and step.is_integer() and stop.is_integer():
                    ranges[name] = (int(start), int(step), int(stop))
                else:
                    ranges[name] = (start, step, stop)

    # 3. Direct fixed_params overrides
    if "fixed_params" in ea_cfg and isinstance(ea_cfg["fixed_params"], dict):
        for k, v in ea_cfg["fixed_params"].items():
            ranges.pop(k, None)
            try:
                if isinstance(v, str):
                    v = float(v) if "." in v else int(v)
            except ValueError:
                pass
            fixed[k] = v

    # 4. Direct opt_ranges overrides
    if "opt_ranges" in ea_cfg and isinstance(ea_cfg["opt_ranges"], dict):
        for k, r in ea_cfg["opt_ranges"].items():
            if isinstance(r, (list, tuple)) and len(r) == 3:
                fixed.pop(k, None)
                start, step, stop = float(r[0]), float(r[1]), float(r[2])
                if start.is_integer() and step.is_integer() and stop.is_integer():
                    ranges[k] = (int(start), int(step), int(stop))
                else:
                    ranges[k] = (start, step, stop)

    return fixed, ranges


WORK_DIR = str(_BASE_WORK_DIR / f"{ACTIVE_EA.lower()}_{SYMBOL_KEY.lower()}")

FIXED_PARAMS, OPT_RANGES = _ea_cfg["build"](SYMBOL_KEY, PIP_SIZE)

# Apply user overrides from config.json (configured in Optimize tab)
if "_cfg" in locals() and _cfg:
    FIXED_PARAMS, OPT_RANGES = _apply_optimization_config_overrides(
        FIXED_PARAMS, OPT_RANGES, _cfg, ACTIVE_EA
    )

CRITERIA_CFG = _cfg.get("qualification_criteria", {}) if "_cfg" in locals() and _cfg else {}

# -- Pipeline settings -----------------------------------------------------
TOP_N_TRAIN         = 20
OPTIMIZATION_MODE   = 2
OPT_TIMEOUT         = 21600
SINGLE_TEST_TIMEOUT = 100

# -- Walk Forward ----------------------------------------------------------
WF_WINDOW_MONTHS  = 12
WF_STEP_MONTHS    = 6
WF_MIN_PASS_RATE  = 70.0

# -- Monte Carlo -----------------------------------------------------------
MC_NUM_SIMULATIONS   = 5_000
MC_MAX_DD_PCT        = 10.0
MC_DAILY_DD_PCT      = 5.0
MC_PHASE1_TARGET_PCT = 8.0
MC_PHASE2_TARGET_PCT = 5.0

# -- Terminal-launch reliability ------------------------------------------
RETRY_COUNT                     = 3
RETRY_DELAY_SECONDS             = 20
KILL_STALE_TERMINAL_BEFORE_RUN  = True


def _kill_stale_terminal_for_this_data_dir() -> None:
    try:
        import psutil
    except ImportError:
        print("  (psutil not installed - skipping stale-terminal check)")
        return

    target = str(Path(TERMINAL_DATA_DIR)).lower()
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            if "terminal64" not in name:
                continue
            cmdline = " ".join(proc.info["cmdline"] or []).lower()
            if target in cmdline:
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        print(f"  Closed {killed} stale terminal64.exe process(es) tied to this data dir.")
        time.sleep(3)


def _with_retries(fn, label: str, retries: int = RETRY_COUNT,
                   delay: int = RETRY_DELAY_SECONDS):
    for attempt in range(1, retries + 1):
        if attempt > 1 and KILL_STALE_TERMINAL_BEFORE_RUN:
            _kill_stale_terminal_for_this_data_dir()
        try:
            result = fn()
        except Exception as exc:
            print(f"  [{label}] attempt {attempt}/{retries} raised: {exc}")
            result = None

        if result is not None:
            if attempt > 1:
                print(f"  [{label}] succeeded on attempt {attempt}/{retries}.")
            return result

        if attempt < retries:
            print(f"  [{label}] attempt {attempt}/{retries} produced no result - retrying in {delay}s...")
            time.sleep(delay)
        else:
            print(f"  [{label}] FAILED after {retries} attempts.")
    return None


def _run_single(all_params: dict, from_date: str, to_date: str,
                run_dir: Path, run_label: str) -> dict | None:
    profiles_tester_dir = Path(TERMINAL_DATA_DIR) / "MQL5" / "Profiles" / "Tester"
    set_filename = _make_single_test_set_file(
        all_params, profiles_tester_dir, filename=f"{run_label}.set"
    )

    def _launch():
        return run_single_backtest(
            terminal_path=TERMINAL_PATH,
            terminal_data_dir=TERMINAL_DATA_DIR,
            expert=EXPERT,
            set_file=set_filename,
            symbol=SYMBOL, period=PERIOD,
            from_date=from_date, to_date=to_date,
            work_dir=str(run_dir),
            login=LOGIN, password=PASSWORD, server=SERVER,
            report_name=run_label,
            deposit=int(DEPOSIT),
            currency=CURRENCY, leverage=LEVERAGE,
            timeout=SINGLE_TEST_TIMEOUT,
        )

    report = _with_retries(_launch, label=f"Single backtest [{run_label}]")
    if report is None:
        return None
    try:
        return analyze(report)
    except Exception as exc:
        print(f"    ERROR analyzing report: {exc}")
        return None


def _gate(result: dict | None, label: str, months_span: float, is_train: bool = False) -> tuple[bool, dict]:
    if result is None:
        print(f"  [{label:8s}]  ERROR - backtest did not produce a report")
        return False, {}
    curated = result["curated_summary"]
    deals = result.get("deals")
    trades = _deals_to_trades(deals) if (deals is not None and not deals.empty) else None
    
    label_upper = label.strip().upper()
    if is_train or label_upper == "TRAIN":
        phase = "train"
    elif label_upper in ("VAL", "VALIDATION"):
        phase = "val"
    elif label_upper in ("HOLDOUT", "HOLD_OUT"):
        phase = "holdout"
    else:
        phase = "val"

    crit = CRITERIA_CFG.get(phase) if "CRITERIA_CFG" in globals() else None
    passed, reasons = check_phase_criteria(
        phase=phase,
        row_or_curated=curated,
        trades=trades,
        starting_capital=DEPOSIT,
        months_span=months_span,
        criteria=crit,
    )
        
    status = "PASS" if passed else f"FAIL ({', '.join(reasons)})"
    print(f"  [{label:8s}] {_fmt_curated(curated)}  ->  {status}")
    return passed, curated


def _print_phase_detail(label: str, period: str, c: dict) -> None:
    def f(v):
        return f"{v:,.2f}" if isinstance(v, (int, float)) and v is not None else "-"
    print(f"\n  -- {label}  ({period})")
    print(f"     Total Trades:         {c.get('Total Trades', '-')}")
    print(f"     Net Profit:           {f(c.get('Net Profit'))}  ({f(c.get('Net Profit %'))}%)")
    print(f"     Profit Factor:        {f(c.get('Profit Factor'))}")
    print(f"     Win Rate:             {f(c.get('Win Rate %'))}%")
    print(f"     Sharpe Ratio:         {f(c.get('Sharpe Ratio'))}")
    print(f"     Max Balance DD ($):   {f(c.get('Max Balance Drawdown ($)'))}")
    print(f"     Max Balance DD (%):   {f(c.get('Max Balance Drawdown (%)'))}%")
    print(f"     Recovery Factor:      {f(c.get('Recovery Factor'))}")
    print(f"     Return/DD Ratio:      {f(c.get('Return/Drawdown Ratio'))}")
    print(f"     Largest Win / Loss:   {f(c.get('Largest Profit Trade'))}  /  {f(c.get('Largest Loss Trade'))}")
    print(f"     Avg Win  / Avg Loss:  {f(c.get('Average Profit Trade'))}  /  {f(c.get('Average Loss Trade'))}")


def _build_excel_mc(run_ts: str, run_dir: Path, mc_passed: list) -> Path:
    """Excel summary for candidates that passed Monte Carlo.
    WF columns are intentionally omitted here -- WF is run manually."""
    xl_path = run_dir / f"mc_passed_{run_ts}.xlsx"
    periods = {
        "Train":        f"{TRAIN_FROM} -> {TRAIN_TO}",
        "Val":          f"{VAL_FROM} -> {VAL_TO}",
        "Holdout":      f"{HOLDOUT_FROM} -> {HOLDOUT_TO}",
        "Full History": f"{TRAIN_FROM} -> {HOLDOUT_TO}",
    }
    bt_metrics = [
        "Total Trades", "Net Profit", "Net Profit %", "Win Rate %",
        "Profit Factor", "Sharpe Ratio", "Recovery Factor",
        "Return/Drawdown Ratio", "Max Balance Drawdown ($)",
        "Max Balance Drawdown (%)", "Largest Profit Trade", "Largest Loss Trade",
        "Average Profit Trade", "Average Loss Trade",
    ]

    with pd.ExcelWriter(xl_path, engine="openpyxl") as writer:
        rows = []
        for s in mc_passed:
            row = {"Candidate #": s["cand_n"], "Symbol": SYMBOL_KEY, "EA": EXPERT}
            row.update(s["ea_params"])
            for ph in ("Train", "Val", "Holdout", "Full History"):
                c = s["curated"][ph]
                tag = ph[:4].replace(" ", "")
                row[f"{tag} NetProfit($)"] = c.get("Net Profit")
                row[f"{tag} NetProfit%"]   = c.get("Net Profit %")
                row[f"{tag} Trades"]       = c.get("Total Trades")
                row[f"{tag} WinRate%"]     = c.get("Win Rate %")
                row[f"{tag} PF"]           = c.get("Profit Factor")
                row[f"{tag} Sharpe"]       = c.get("Sharpe Ratio")
                row[f"{tag} MaxDD%"]       = c.get("Max Balance Drawdown (%)")
                row[f"{tag} RecovFactor"]  = c.get("Recovery Factor")
            mc = s["mc_result"]["metrics"]
            row["MC Phase1%"]      = mc.get("phase1_pass_rate")
            row["MC Phase2%"]      = mc.get("phase2_pass_rate")
            row["MC Combined%"]    = mc.get("combined_pass_rate")
            row["MC BreachMaxDD%"] = mc.get("worst_breach_max_dd_rate")
            row["MC BreachDaily%"] = mc.get("worst_breach_daily_dd_rate")
            rows.append(row)
        pd.DataFrame(rows).to_excel(writer, sheet_name="Summary", index=False)

        pd.DataFrame([
            {"Candidate #": s["cand_n"], **s["all_params"]} for s in mc_passed
        ]).to_excel(writer, sheet_name="Parameters", index=False)

        detail_rows = []
        for s in mc_passed:
            for ph, period_str in periods.items():
                row = {"Candidate #": s["cand_n"], "Phase": ph, "Period": period_str}
                for m in bt_metrics:
                    row[m] = s["curated"][ph].get(m)
                detail_rows.append(row)
        pd.DataFrame(detail_rows).to_excel(writer, sheet_name="Backtest Details", index=False)

        mc_rows = []
        for s in mc_passed:
            row = {"Candidate #": s["cand_n"]}
            row.update(s["mc_result"]["metrics"])
            mc_rows.append(row)
        pd.DataFrame(mc_rows).to_excel(writer, sheet_name="Monte Carlo", index=False)

    return xl_path


def _mc_phase_section(doc, phase_result, label):
    """Write a full run_monte_carlo() result dict as a titled section in doc."""
    p = phase_result.get("params", {})
    doc.add_heading(label, level=1)

    doc.add_heading("Simulation Parameters", level=2)
    doc.add_paragraph(f"Simulations run:             {phase_result.get('num_simulations', 0):,}")
    doc.add_paragraph(f"Starting capital:            {p.get('starting_capital', 0):,.2f}")
    doc.add_paragraph(f"Profit target:               {p.get('profit_target_pct', 0)}%")
    doc.add_paragraph(f"Max drawdown limit:          {p.get('max_drawdown_pct', 0)}%  (static, off initial balance)")
    doc.add_paragraph(f"Daily drawdown limit:        {p.get('daily_drawdown_pct', 0)}%  (off previous day close)")
    doc.add_paragraph(f"Max trading days simulated:  {p.get('max_trading_days', 0)}")
    doc.add_paragraph(f"Resample block size:         {p.get('block_size', 0)} trading days")

    doc.add_heading("Outcome Rates", level=2)
    doc.add_paragraph(f"Pass rate:                   {phase_result.get('pass_rate_pct', 0):.2f}%")
    doc.add_paragraph(f"Breached max drawdown:       {phase_result.get('breach_max_dd_rate_pct', 0):.2f}%")
    doc.add_paragraph(f"Breached daily drawdown:     {phase_result.get('breach_daily_dd_rate_pct', 0):.2f}%")
    doc.add_paragraph(f"Incomplete (neither):        {phase_result.get('incomplete_rate_pct', 0):.2f}%")

    doc.add_heading("Days to Pass", level=2)
    if phase_result.get('days_to_pass_median') is not None:
        doc.add_paragraph(f"Median:                      {phase_result.get('days_to_pass_median'):.0f}")
        doc.add_paragraph(f"10th - 90th percentile:     {phase_result.get('days_to_pass_p10'):.0f}  -  {phase_result.get('days_to_pass_p90'):.0f}")
    else:
        doc.add_paragraph("Days to pass:                no simulations passed")

    doc.add_heading("Drawdown Distribution (across all simulations)", level=2)
    doc.add_paragraph(f"Max DD reached (median):     {phase_result.get('max_dd_median_pct', 0):.2f}%")
    doc.add_paragraph(f"Max DD reached (90th pct):   {phase_result.get('max_dd_p90_pct', 0):.2f}%")
    doc.add_paragraph(f"Max DD reached (99th pct):   {phase_result.get('max_dd_p99_pct', 0):.2f}%")

    doc.add_heading("Single-Day Move Stats", level=2)
    doc.add_paragraph(f"Largest profit day:          {phase_result.get('hist_best_day_dollar', 0):,.2f}  ({phase_result.get('hist_best_day_pct', 0):.2f}%)")
    doc.add_paragraph(f"Largest loss day:            {phase_result.get('hist_worst_day_dollar', 0):,.2f}  ({phase_result.get('hist_worst_day_pct', 0):.2f}%)")
    doc.add_paragraph(f"Average daily gain/loss:     {phase_result.get('hist_avg_day_dollar', 0):,.2f}  ({phase_result.get('hist_avg_day_pct', 0):.2f}%)")
    p95_profit = phase_result.get('sim_p95_profit_day_dollar')
    p95_loss   = phase_result.get('sim_p95_loss_day_dollar')
    if p95_profit is not None:
        doc.add_paragraph(f"95th pct profit day:         {p95_profit:,.2f}  ({phase_result.get('sim_p95_profit_day_pct', 0):.2f}%)  — only 5% of days gained more")
    if p95_loss is not None:
        doc.add_paragraph(f"95th pct loss day:           {p95_loss:,.2f}  ({phase_result.get('sim_p95_loss_day_pct', 0):.2f}%)  — only 5% of days lost more")


def _create_mc_word_doc(cand_dir, mc_result, cand_n):
    if 'docx' not in globals(): return
    doc = docx.Document()
    doc.add_heading(f"Monte Carlo Full Results — Candidate {cand_n}", 0)

    # -- Phase 1 full detail --------------------------------------------------
    if "phase1" in mc_result:
        _mc_phase_section(doc, mc_result["phase1"], "PHASE 1 — Full Simulation Results")

    # -- Phase 2 full detail --------------------------------------------------
    if "phase2" in mc_result:
        _mc_phase_section(doc, mc_result["phase2"], "PHASE 2 — Full Simulation Results")

    # -- Combined certification verdict ---------------------------------------
    doc.add_heading("CERTIFICATION VERDICT", level=1)
    m = mc_result.get("metrics", {})
    doc.add_paragraph(f"Phase 1 pass rate:           {m.get('phase1_pass_rate', 0):.2f}%")
    doc.add_paragraph(f"Phase 2 pass rate:           {m.get('phase2_pass_rate', 0):.2f}%")
    doc.add_paragraph(f"Combined pass rate:          {m.get('combined_pass_rate', 0):.2f}%")
    doc.add_paragraph(f"Worst breach Max DD rate:    {m.get('worst_breach_max_dd_rate', 0):.2f}%")
    doc.add_paragraph(f"Worst breach Daily DD rate:  {m.get('worst_breach_daily_dd_rate', 0):.2f}%")
    doc.add_paragraph(f"Worst 90th pct Max DD:       {m.get('worst_max_dd_p90', 0):.2f}%")
    doc.add_paragraph(f"Worst median Max DD:         {m.get('worst_max_dd_median', 0):.2f}%")
    if mc_result.get("certified", False):
        doc.add_paragraph("RESULT: CERTIFIED — clears all Monte Carlo thresholds")
    else:
        doc.add_paragraph("RESULT: NOT CERTIFIED")
        for r in mc_result.get("reasons", []):
            doc.add_paragraph(f"  - {r}")

    doc.add_paragraph(
        "Reminder: this resamples YOUR historical daily P&L distribution. "
        "It assumes future behaviour resembles the backtest period and only "
        "checks drawdown at end-of-day granularity, not intraday swings."
    )

    doc.save(cand_dir / "MonteCarlo_Summary.docx")


def _create_wf_word_doc(cand_dir, wf_stats, wf_table, cand_n):
    if 'docx' not in globals(): return
    doc = docx.Document()
    doc.add_heading(f"Walk Forward Full Results — Candidate {cand_n}", 0)

    doc.add_paragraph(
        "Fixed parameters tested across rolling time windows. "
        "Consistent profitability across windows is evidence the edge generalises. "
        "Performance collapsing in several windows is a real overfitting warning."
    )

    # -- Per-window table (all columns) ----------------------------------------
    doc.add_heading("Window-by-Window Results", level=1)
    cols = list(wf_table.columns)
    tbl = doc.add_table(rows=1, cols=len(cols))
    tbl.style = 'Table Grid'
    for i, col in enumerate(cols):
        tbl.rows[0].cells[i].text = str(col)
    for _, row in wf_table.iterrows():
        cells = tbl.add_row().cells
        for i, col in enumerate(cols):
            val = row.get(col, '')
            if isinstance(val, float):
                cells[i].text = f"{val:,.2f}"
            else:
                cells[i].text = str(val)

    # -- Stability stats (all fields) -----------------------------------------
    doc.add_heading("Stability Statistics", level=1)
    doc.add_paragraph(f"Total windows:               {wf_stats.get('total_windows', 0)}")
    doc.add_paragraph(f"Profitable windows:          {wf_stats.get('profitable_windows', 0)} ({wf_stats.get('profitable_windows_pct', 0):.2f}%)")
    doc.add_paragraph(f"Net Profit — mean ($):       {wf_stats.get('net_profit_mean', 0):,.2f}")
    doc.add_paragraph(f"Net Profit — std ($):        {wf_stats.get('net_profit_std', 0):,.2f}")
    cv_dollar = wf_stats.get('net_profit_cv')
    if cv_dollar is not None:
        doc.add_paragraph(f"Net Profit CV ($-based):     {cv_dollar:.2f}")
    doc.add_paragraph(f"Net Profit — mean (%):       {wf_stats.get('net_profit_pct_mean', 0):.2f}%")
    doc.add_paragraph(f"Net Profit — std (%):        {wf_stats.get('net_profit_pct_std', 0):.2f}%")
    cv_pct = wf_stats.get('net_profit_pct_cv')
    if cv_pct is not None:
        doc.add_paragraph(f"Net Profit CV (%-based):     {cv_pct:.2f}  (below 1.0 = consistent)")
    doc.add_paragraph(f"Profit Factor — mean:        {wf_stats.get('profit_factor_mean', 0):.2f}")
    doc.add_paragraph(f"Worst window:                #{wf_stats.get('worst_window_index', '?')} ({wf_stats.get('worst_window_profit', 0):,.2f})")
    doc.add_paragraph(f"Best window:                 #{wf_stats.get('best_window_index', '?')} ({wf_stats.get('best_window_profit', 0):,.2f})")

    doc.add_paragraph(
        "Read as: consistent profit factor / positive net profit across most windows = real, "
        "generalising edge. One or two great windows carrying an otherwise flat/negative set = "
        "likely overfit to a specific period or regime."
    )

    doc.save(cand_dir / "WalkForward_Summary.docx")

def _create_certified_word_doc(run_dir, certified):
    if 'docx' not in globals(): return
    doc = docx.Document()
    doc.add_heading("Certified Candidates", 0)
    doc.add_paragraph(f"Total fully certified candidates: {len(certified)}")
    
    for cand in certified:
        doc.add_heading(f"Strategy ID: {cand['idx']} (Candidate {cand.get('cand_n', 'N/A')})", level=1)
        doc.add_paragraph(f"Params: {cand['params_display']}")
        c_full = cand['curated'].get('Full History', {})
        doc.add_paragraph(f"Full History Net Profit: {c_full.get('Net Profit', 0):.2f}")
        doc.add_paragraph(f"Full History Max DD %: {c_full.get('Max Balance Drawdown (%)', 0):.2f}%")
        
    doc.save(run_dir / "Certified_Candidates.docx")


def main():
    run_ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(WORK_DIR) / f"run_{run_ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    profiles_tester_dir = Path(TERMINAL_DATA_DIR) / "MQL5" / "Profiles" / "Tester"

    print("=" * 72)
    print(f"STRATEGY OPTIMIZATION PIPELINE  |  {ACTIVE_EA} on {SYMBOL_KEY}  |  {run_ts}")
    print("=" * 72)
    print(f"  EA:       {EXPERT}   Symbol: {SYMBOL} (PipSize: {PIP_SIZE})   Period: {PERIOD}")
    print(f"  Train:    {TRAIN_FROM} -> {TRAIN_TO}")
    print(f"  Val:      {VAL_FROM} -> {VAL_TO}")
    print(f"  Holdout:  {HOLDOUT_FROM} -> {HOLDOUT_TO}")
    print(f"  Deposit:  ${DEPOSIT:,} {CURRENCY}   Leverage: {LEVERAGE}")
    print(f"  Work dir: {run_dir}")

    # PHASE 1 - MT5 Optimization
    print("\n" + "-" * 72)
    print(f"PHASE 1  Optimization (Train)  {TRAIN_FROM} -> {TRAIN_TO}")
    print("-" * 72)

    opt_set_path = profiles_tester_dir / "run_opt_strategy.set"

    print("=" * 72)
    print(f"  STRATEGY OPTIMIZATION PARAMETERS ({ACTIVE_EA} | {SYMBOL_KEY})")
    print("=" * 72)
    print(f"  [RANGES TO OPTIMIZE] ({len(OPT_RANGES)} parameters varied in MT5):")
    for k, rng in OPT_RANGES.items():
        st, sp, so = rng
        passes = int(abs(so - st) / sp) + 1 if sp > 0 else 1
        print(f"    • {k}: {st} -> {so} (step: {sp} | ~{passes} values)")
    print(f"  [FIXED PARAMETERS] ({len(FIXED_PARAMS)} parameters held constant):")
    for k in sorted(FIXED_PARAMS.keys()):
        print(f"    • {k} = {FIXED_PARAMS[k]}")
    print("=" * 72)

    generate_optimization_set_file(
        fixed_params=FIXED_PARAMS,
        ranges=OPT_RANGES,
        output_path=str(opt_set_path),
    )

    opt_report = _with_retries(
        lambda: _run_mt5_opt(
            terminal_path=TERMINAL_PATH,
            terminal_data_dir=TERMINAL_DATA_DIR,
            expert=EXPERT,
            set_file="run_opt_strategy.set",
            symbol=SYMBOL, period=PERIOD,
            from_date=TRAIN_FROM, to_date=TRAIN_TO,
            work_dir=str(run_dir / "opt"),
            login=LOGIN, password=PASSWORD, server=SERVER,
            report_name="opt_train_report",
            deposit=DEPOSIT, currency=CURRENCY, leverage=LEVERAGE,
            optimization_mode=OPTIMIZATION_MODE,
            timeout=OPT_TIMEOUT,
        ),
        label="Phase 1 Optimization",
    )
    if opt_report is None:
        print("\nABORTING: Optimization phase produced no report.")
        return

    train_df = parse_optimization_results(opt_report)
    print(f"\n  {len(train_df)} passes found.")
    print_top_results(train_df, n=min(25, len(train_df)))

    csv_path = run_dir / "opt_all_passes.csv"
    train_df.to_csv(csv_path, index=False)

    print(f"\n{'='*72}\nCANDIDATE QUALIFICATION GATES (Configured via Optimize Tab)\n{'='*72}")
    for ph in ("train", "val", "holdout"):
        c = get_qualification_criteria(ph, CRITERIA_CFG.get(ph) if "CRITERIA_CFG" in globals() else None)
        print(f"  [{ph.upper():7s}] Gain% >= {c['min_profit_gain_pct']:.1f}% | MaxDD <= {c['max_drawdown_pct']:.1f}% | "
              f"PF >= {c['min_profit_factor']:.2f} | Sharpe >= {c['min_sharpe_ratio']:.2f} | "
              f"Ret/DD >= {c['min_ret_dd_ratio']:.2f} | Trades/Mo >= {c['min_avg_trades_month']:.1f}")
    print(f"{'='*72}")

    candidates = []
    train_crit = CRITERIA_CFG.get("train") if "CRITERIA_CFG" in globals() else None
    for _, row in train_df.iterrows():
        row_dict = _normalise_opt_row(row)
        passed, _ = check_train_criteria(row_dict, starting_capital=DEPOSIT, months_span=TRAIN_MONTHS, criteria=train_crit)
        if passed:
            candidates.append(row_dict)

    if not candidates:
        print(f"\n  WARNING: 0 passes met Train criteria - using top {TOP_N_TRAIN} by Result score.")
        candidates = [_normalise_opt_row(r) for _, r in train_df.head(TOP_N_TRAIN).iterrows()]
    else:
        candidates = candidates[:TOP_N_TRAIN]

    # ── PHASE 1: BACKTESTING (Train, Val, Holdout, Full) ─────────────
    print(f"\n{'='*72}\nPHASE 1: BACKTESTING (Train, Val, Holdout, Full)\n{'='*72}")
    passed_bt_candidates = []

    for cand_n, row_dict in enumerate(candidates, start=1):
        ea_params  = _extract_opt_ea_params(row_dict, FIXED_PARAMS)
        all_params = {**FIXED_PARAMS, **ea_params}

        print(f"\n{'#'*72}")
        print(f"  Candidate {cand_n}/{len(candidates)} ({SYMBOL_KEY})")
        print(f"  Optimized params: {ea_params}")
        print(f"{'#'*72}")

        cand_dir = run_dir / f"cand_{cand_n:03d}"
        cand_dir.mkdir(exist_ok=True)

        # 2A Train
        res_train = _run_single(all_params, TRAIN_FROM, TRAIN_TO, cand_dir / "train", f"c{cand_n:03d}_train")
        train_ok, train_c = _gate(res_train, "TRAIN", months_span=TRAIN_MONTHS, is_train=True)
        if not train_ok: continue
        _print_phase_detail("TRAIN", f"{TRAIN_FROM} -> {TRAIN_TO}", train_c)

        # 2B Validation
        res_val = _run_single(all_params, VAL_FROM, VAL_TO, cand_dir / "val", f"c{cand_n:03d}_val")
        val_ok, val_c = _gate(res_val, "VAL", months_span=VAL_MONTHS)
        if not val_ok: continue
        _print_phase_detail("VALIDATION", f"{VAL_FROM} -> {VAL_TO}", val_c)

        # 2C Holdout
        res_hold = _run_single(all_params, HOLDOUT_FROM, HOLDOUT_TO, cand_dir / "holdout", f"c{cand_n:03d}_holdout")
        hold_ok, hold_c = _gate(res_hold, "HOLDOUT", months_span=HOLDOUT_MONTHS)
        if not hold_ok: continue
        _print_phase_detail("HOLDOUT", f"{HOLDOUT_FROM} -> {HOLDOUT_TO}", hold_c)

        # 3A Full History
        res_full = _run_single(all_params, TRAIN_FROM, HOLDOUT_TO, cand_dir / "full", f"c{cand_n:03d}_full")
        if res_full is None: continue
        full_c = res_full["curated_summary"]
        
        # Print Full History details
        _print_phase_detail("FULL HISTORY", f"{TRAIN_FROM} -> {HOLDOUT_TO}", full_c)
        
        passed_bt_candidates.append({
            "cand_n": cand_n,
            "row_dict": row_dict,
            "ea_params": ea_params,
            "all_params": all_params,
            "cand_dir": cand_dir,
            "train_c": train_c,
            "val_c": val_c,
            "hold_c": hold_c,
            "full_c": full_c,
            "res_full": res_full
        })
        
    # ── PHASE 2: MONTE CARLO ─────────────
    print(f"\n{'='*72}\nPHASE 2: MONTE CARLO ({len(passed_bt_candidates)} passed Backtesting)\n{'='*72}")
    passed_mc_candidates = []
    
    for cand in passed_bt_candidates:
        cand_n = cand["cand_n"]
        res_full = cand["res_full"]
        
        print(f"\n  Running Monte Carlo for Candidate {cand_n}...")
        deals = res_full.get("deals")
        mc_trades = _deals_to_trades(deals) if (deals is not None and not deals.empty) else None
        if mc_trades is None or mc_trades.empty: continue

        mc_result = certify_strategy(
            mc_trades,
            starting_capital=float(DEPOSIT),
            max_drawdown_pct=MC_MAX_DD_PCT,
            daily_drawdown_pct=MC_DAILY_DD_PCT,
            phase1_target_pct=MC_PHASE1_TARGET_PCT,
            phase2_target_pct=MC_PHASE2_TARGET_PCT,
            num_simulations=MC_NUM_SIMULATIONS,
        )
        print_certification_result(mc_result)
        _create_mc_word_doc(cand["cand_dir"], mc_result, cand_n)
        
        if not mc_result["certified"]: continue
        
        print(f"  Candidate {cand_n} PASSED Monte Carlo.")
        passed_mc_candidates.append({
            **cand,
            "mc_result": mc_result
        })

    # ── END OF AUTOMATED PIPELINE ─────────────────────────────────────────────
    # Walk Forward stability testing is performed MANUALLY on each passing
    # candidate. Results should be saved inside the candidate's own folder.
    # ──────────────────────────────────────────────────────────────────────────

    print("\n" + "=" * 72)
    print(f"PIPELINE COMPLETE  |  {ACTIVE_EA} on {SYMBOL_KEY}  |  {run_ts}")
    print(f"  Backtesting gate:  {len(passed_bt_candidates)} candidate(s) passed")
    print(f"  Monte Carlo gate:  {len(passed_mc_candidates)} candidate(s) passed")
    print("  Walk Forward:      MANUAL  (run each candidate's .set file by hand)")
    print("=" * 72)

    if not passed_mc_candidates:
        print("\n  No candidates passed Monte Carlo. Nothing to copy.")
        return

    # ── Create 'passed_candidates' folder and copy each MC-passing candidate ──
    passed_dir = run_dir / "passed_candidates"
    passed_dir.mkdir(exist_ok=True)

    import shutil
    for cand in passed_mc_candidates:
        cand_n   = cand["cand_n"]
        cand_dir = cand["cand_dir"]
        dest     = passed_dir / f"cand_{cand_n:03d}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(str(cand_dir), str(dest))
        print(f"  Copied cand_{cand_n:03d} -> passed_candidates/cand_{cand_n:03d}")

    print(f"\n  Passed candidates folder: {passed_dir}")
    print("  Each folder contains:")
    print("    - Backtest reports for Train / Val / Holdout / Full History")
    print("    - MonteCarlo_Summary.docx")
    print("    - (place your manual WalkForward_Summary.docx here after WF testing)")

    # ── MC-only Excel summary ──────────────────────────────────────────────────
    xl_path = _build_excel_mc(run_ts, run_dir, passed_mc_candidates)
    print(f"\n  MC summary saved: {xl_path}")


if __name__ == "__main__":
    main()