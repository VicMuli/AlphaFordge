r"""
strategy_builder.py

Orchestrates the full MT5-native optimization pipeline:

  TRAIN         MT5 genetic optimization over the Train date range.
                Top N passes by OnTester() fitness are kept.
  VALIDATION    Each surviving parameter set is re-tested as a single
                backtest over the Validation date range. Passes that meet
                the Validation criteria proceed.
  HOLDOUT       Each Validation survivor is tested once on the Holdout
                date range. Passes that meet Holdout criteria proceed.
  MONTE CARLO   A combined (Train + Validation + Holdout) single backtest
                is run for each Holdout survivor. The deal log is extracted
                and fed into monte_carlo.certify_strategy() to check
                real funded-account safety.
  STORE         Strategies that clear all four gates are persisted to SQLite
                via strategy_store.py.

WHY MT5 HANDLES THE SPLITS (not Python)
  MT5's engine uses real tick data (or Every Tick based on Real Ticks for
  M1), applies the real spread/commission/swap model, and runs the EA's
  actual MQL5 logic. Any Python re-implementation of the same ORB logic
  will diverge from the real EA — different fill logic, different bar-index
  handling, different indicator precision — so a strategy that looks good in
  Python must be re-validated in MT5 from scratch. Removing the Python
  backtest layer eliminates that double-work entirely: the optimisation
  results you see ARE the MT5 results.

INDICATOR FILTER MANAGEMENT
  Indicator filters are added directly to the EA in MQL5. The MT5 parameter
  sweep handles toggling them on/off (via boolean EA inputs) and sweeping
  their parameters — this script just controls the date windows, the pass
  criteria, and the storage.

PASS CRITERIA
  TRAIN (from the MT5 optimization XML):
    - Profit Factor  >= 1.10
    - Sharpe Ratio   >= 0.50
    - Max Drawdown   <= 15.0%
    - Recovery Factor >= 1.3    (MT5 provides this natively)
    - Net Profit > 0

  VALIDATION and HOLDOUT (single-test HTML report):
    - Profit Factor  >= 1.0
    - Sharpe Ratio   >= 0.50
    - Max Drawdown   <= 15.0%
    - Net Profit > 0

  MONTE CARLO (via monte_carlo.certify_strategy()):
    - Phase 1 pass rate >= 60%
    - Phase 2 pass rate >= 60%
    - Combined pass rate >= 40%
    - Breach MaxDD rate  <= 15%
    - Breach Daily DD rate <= 10%
    etc. (configurable in monte_carlo.py DEFAULT_CERTIFICATION_THRESHOLDS)

Usage:
    from strategy_builder import run_mt5_strategy_search

    result = run_mt5_strategy_search(
        terminal_path=r"C:\Program Files\MetaTrader 5 IC Markets KE\terminal64.exe",
        terminal_data_dir=r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\<ID>",
        expert="ORB_EA.ex5",
        symbol="XAUUSD Dukascopy",
        period="M1",
        train_from="2013.01.01", train_to="2021.01.01",
        val_from="2021.01.01",   val_to="2024.01.01",
        holdout_from="2024.01.01", holdout_to="2026.07.03",
        fixed_params={"InpLotSize": 1.0, "InpMagicNumber": 20240101},
        opt_ranges={"InpTPRatio": (1.0, 0.5, 3.0), "InpSLBuffer": (0, 2, 20)},
        login="52909674", password="3F!@4rwo7wc02f", server="ICMarketsKE-Demo",
        deposit=100_000,
        top_n_train=20,
        work_dir=r"C:\MT5\opt_runs\xauusd_orb",
        symbol_key="XAUUSD",
        db_path="results.db",
    )
"""

import json
import time
import shutil
import datetime
import tempfile
from pathlib import Path

import pandas as pd

from mt5_optimizer import (
    generate_optimization_set_file,
    run_optimization,
    parse_optimization_results,
)
from mt5_runner import run_single_backtest
from report_analysis import analyze, compute_curated_summary
from monte_carlo import certify_strategy, print_certification_result
from strategy_store import (
    genome_signature,
    save_passed_strategy,
    is_strategy_stored,
    print_stored_strategies,
    init_strategy_store,
)


# ---------------------------------------------------------------------------
# Pass criteria applied to parsed MT5 data
# ---------------------------------------------------------------------------

def _avg_trades_per_month(trades: pd.DataFrame) -> float:
    """Replicates trades-per-month logic from the MQL5 EA's OnTester()."""
    if trades is None or trades.empty:
        return 0.0
    if isinstance(trades, pd.DataFrame):
        if "exit_time" in trades.columns:
            exit_times = pd.to_datetime(trades["exit_time"])
        elif "Time" in trades.columns:
            exit_times = pd.to_datetime(trades["Time"])
        else:
            return 0.0
        if exit_times.isna().all():
            return 0.0
        months_span = (
            (exit_times.max().year - exit_times.min().year) * 12
            + exit_times.max().month - exit_times.min().month + 1
        )
        return len(trades) / max(months_span, 1)
    return 0.0


def _months_between(start_str: str, end_str: str) -> float:
    """Calculate the fractional number of months between two YYYY.MM.DD date strings."""
    try:
        s = datetime.datetime.strptime(start_str.replace("-", ".").replace("/", "."), "%Y.%m.%d")
        e = datetime.datetime.strptime(end_str.replace("-", ".").replace("/", "."), "%Y.%m.%d")
        return (e.year - s.year) * 12 + e.month - s.month + (e.day - s.day) / 30.44
    except Exception:
        return 0.0


def get_qualification_criteria(phase: str = "train", custom_criteria: dict = None) -> dict:
    """
    Returns the qualification criteria dict for a given phase ('train', 'val', 'holdout').
    Reads from config.json if available, falling back to defaults.
    """
    defaults = {
        "train": {
            "min_profit_gain_pct": 30.0,
            "max_drawdown_pct": 20.0,
            "min_avg_trades_month": 1.0,
            "min_sharpe_ratio": 0.50,
            "min_ret_dd_ratio": 1.30,
            "min_profit_factor": 1.10,
            "min_net_profit": 0.0,
            "min_total_trades": 0,
            "min_win_rate_pct": 0.0,
        },
        "val": {
            "min_profit_gain_pct": 15.0,
            "max_drawdown_pct": 20.0,
            "min_avg_trades_month": 1.0,
            "min_sharpe_ratio": 0.50,
            "min_ret_dd_ratio": 1.00,
            "min_profit_factor": 1.00,
            "min_net_profit": 0.0,
            "min_total_trades": 0,
            "min_win_rate_pct": 0.0,
        },
        "holdout": {
            "min_profit_gain_pct": 15.0,
            "max_drawdown_pct": 20.0,
            "min_avg_trades_month": 1.0,
            "min_sharpe_ratio": 0.50,
            "min_ret_dd_ratio": 1.00,
            "min_profit_factor": 1.00,
            "min_net_profit": 0.0,
            "min_total_trades": 0,
            "min_win_rate_pct": 0.0,
        },
    }
    phase_key = phase.lower()
    if phase_key in ("validation", "val"):
        phase_key = "val"
    elif phase_key in ("hold_out", "holdout"):
        phase_key = "holdout"
    else:
        phase_key = "train"

    crit = dict(defaults.get(phase_key, defaults["train"]))

    # Load from config.json if present
    cfg_file = Path(__file__).resolve().parent / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r") as f:
                cfg_data = json.load(f)
                qc = cfg_data.get("qualification_criteria", {})
                if qc and isinstance(qc, dict):
                    phase_qc = qc.get(phase_key)
                    if phase_qc and isinstance(phase_qc, dict):
                        crit.update(phase_qc)
        except Exception:
            pass

    if custom_criteria and isinstance(custom_criteria, dict):
        crit.update(custom_criteria)

    return crit


def check_phase_criteria(
    phase: str,
    row_or_curated: dict,
    trades: pd.DataFrame = None,
    starting_capital: float = 100_000,
    months_span: float = 36.0,
    criteria: dict = None,
) -> tuple[bool, list[str]]:
    """
    Evaluates candidate metrics for a specific testing phase ('train', 'val', 'holdout').
    Supports both MT5 XML optimization pass rows and curated summary dicts.
    """
    crit = get_qualification_criteria(phase, criteria)

    if "curated" in row_or_curated and isinstance(row_or_curated["curated"], dict):
        curated_dict = row_or_curated["curated"]
        trades_df = row_or_curated.get("trades", trades)
    else:
        curated_dict = row_or_curated
        trades_df = trades

    def _f(key, default=None):
        v = curated_dict.get(key, default)
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    pf = _f("Profit Factor")
    sharpe = _f("Sharpe Ratio")
    max_dd = _f("Max Drawdown (%)") or _f("Max Balance Drawdown (%)")
    ret_dd = _f("Return/Drawdown Ratio") or _f("Recovery Factor")
    profit = _f("Profit") or _f("Net Profit")
    total_trades = _f("Total Trades") or _f("Trades")
    win_rate = _f("Win Rate %")

    reasons = []

    # 1. Profit Factor
    min_pf = crit.get("min_profit_factor")
    if min_pf is not None and float(min_pf) > 0:
        if pf is None or pf < float(min_pf):
            reasons.append(f"PF ({f'{pf:.2f}' if pf is not None else 'N/A'}) < {float(min_pf):.2f}")

    # 2. Sharpe Ratio
    min_sharpe = crit.get("min_sharpe_ratio")
    if min_sharpe is not None and float(min_sharpe) > 0:
        if sharpe is None or sharpe < float(min_sharpe):
            reasons.append(f"Sharpe ({f'{sharpe:.2f}' if sharpe is not None else 'N/A'}) < {float(min_sharpe):.2f}")

    # 3. Max Drawdown %
    max_dd_limit = crit.get("max_drawdown_pct")
    if max_dd_limit is not None and float(max_dd_limit) > 0:
        if max_dd is None or max_dd > float(max_dd_limit):
            reasons.append(f"MaxDD ({f'{max_dd:.1f}%' if max_dd is not None else 'N/A'}) > {float(max_dd_limit):.1f}%")

    # 4. Return/DD Ratio (Recovery Factor)
    min_ret_dd = crit.get("min_ret_dd_ratio")
    if min_ret_dd is not None and float(min_ret_dd) > 0:
        if ret_dd is None or ret_dd < float(min_ret_dd):
            reasons.append(f"Ret/DD ({f'{ret_dd:.2f}' if ret_dd is not None else 'N/A'}) < {float(min_ret_dd):.2f}")

    # 5. Net Profit
    min_net_profit = crit.get("min_net_profit", 0.0)
    if min_net_profit is not None:
        if profit is None or profit <= float(min_net_profit):
            reasons.append(f"Net Profit (${f'{profit:,.0f}' if profit is not None else '0'}) <= ${float(min_net_profit):,.0f}")

    # 6. Net Profit Gain %
    gain_pct = _f("Net Profit %")
    if gain_pct is None and profit is not None and starting_capital > 0:
        gain_pct = (profit / starting_capital) * 100
    min_gain = crit.get("min_profit_gain_pct")
    if min_gain is not None and float(min_gain) > 0:
        if gain_pct is None or gain_pct < float(min_gain):
            phase_name = "Train" if phase == "train" else ("Val" if phase == "val" else "Holdout")
            reasons.append(f"{phase_name} Gain ({f'{gain_pct:.1f}%' if gain_pct is not None else '0.0%'}) < {float(min_gain):.1f}%")

    # 7. Avg Trades Per Month
    avg_tpm = 0.0
    if trades_df is not None and not trades_df.empty:
        avg_tpm = _avg_trades_per_month(trades_df)
    elif total_trades is not None and months_span > 0:
        avg_tpm = total_trades / max(months_span, 0.01)
    min_tpm = crit.get("min_avg_trades_month")
    if min_tpm is not None and float(min_tpm) > 0:
        if avg_tpm < float(min_tpm):
            reasons.append(f"Avg Trades/Mo ({avg_tpm:.2f}) < {float(min_tpm):.1f}")

    # 8. Total Trades (Optional)
    min_trades = crit.get("min_total_trades")
    if min_trades is not None and float(min_trades) > 0:
        if total_trades is None or total_trades < float(min_trades):
            reasons.append(f"Total Trades ({int(total_trades) if total_trades is not None else 0}) < {int(min_trades)}")

    # 9. Win Rate % (Optional)
    min_wr = crit.get("min_win_rate_pct")
    if min_wr is not None and float(min_wr) > 0:
        if win_rate is None or win_rate < float(min_wr):
            reasons.append(f"Win Rate ({f'{win_rate:.1f}%' if win_rate is not None else '0.0%'}) < {float(min_wr):.1f}%")

    return len(reasons) == 0, reasons


def check_train_criteria(row: dict, starting_capital: float = 100_000, months_span: float = 96.0, criteria: dict = None) -> tuple:
    """
    Applied to a single row from parse_optimization_results() or curated summary dict.
    Returns (passed: bool, reasons: list[str])
    """
    return check_phase_criteria("train", row, None, starting_capital, months_span, criteria)


def check_oos_criteria(curated: dict, trades: pd.DataFrame = None, months_span: float = 36.0, starting_capital: float = 100_000, criteria: dict = None, phase: str = "val") -> tuple:
    """
    Applied to a curated summary dict for Validation and Holdout single-test reports.
    Returns (passed: bool, reasons: list[str])
    """
    return check_phase_criteria(phase, curated, trades, starting_capital, months_span, criteria)



# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _fmt_curated(curated: dict, label: str = "") -> str:
    """Return a compact one-line summary string of key metrics from curated dict."""
    if curated is None:
        return f"{label}  <no data>"
    net_p  = curated.get("Net Profit", 0.0) or 0.0
    sharpe = curated.get("Sharpe Ratio") or float("nan")
    pf     = curated.get("Profit Factor") or float("nan")
    wr     = curated.get("Win Rate %", 0.0) or 0.0
    trades = curated.get("Total Trades", 0)
    max_dd = curated.get("Max Balance Drawdown (%)", 0.0) or 0.0
    ret_dd = curated.get("Return/Drawdown Ratio") or float("nan")
    prefix = f"{label}  " if label else ""
    return (
        f"{prefix}"
        f"NetProfit=${net_p:,.0f}  "
        f"Sharpe={sharpe:.2f}  "
        f"PF={pf:.2f}  "
        f"WinRate={wr:.1f}%  "
        f"Trades={trades}  "
        f"Ret/DD={ret_dd:.2f}  "
        f"MaxDD={max_dd:.1f}%"
    )


def _params_to_genome(fixed_params: dict, opt_params: dict) -> dict:
    """
    Builds a lightweight 'genome' dict suitable for strategy_store from a
    combination of fixed_params and a specific optimised parameter set (one
    row from the MT5 optimization result). The 'genome' here just stores all
    parameter values — there is no Python-side filter structure.
    """
    params = {**fixed_params, **opt_params}
    # Wrap in the structure strategy_store.genome_signature() expects.
    # We re-use the 'params' key (strategy_store reads g.get('params') or
    # g.get('orb_params') for display).
    return {"params": params, "filters": {}}


def _fmt_set_value(v) -> str:
    """
    Format a parameter value for a .set file.
    - Integers (or floats that are whole numbers) are written without a decimal
      point so MT5 reads them as integers for `input int` EA parameters.
    - Floats are rounded to 8 significant digits to eliminate floating-point
      representation noise (e.g. 1.4999999999 → 1.5) that appears when MT5
      writes float params into the optimization XML.
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e12:
            return str(int(v))
        # Round to 8 significant figures to drop XML floating-point noise
        rounded = float(f"{v:.8g}")
        return str(rounded)
    return str(v)


def _make_single_test_set_file(all_params: dict, profiles_tester_dir: Path, filename: str) -> str:
    """Write a .set file with all parameters fixed (no ranges) for a single test.

    The file is written to profiles_tester_dir (the terminal's
    MQL5\\Profiles\\Tester\\ folder). Only the bare filename is passed to
    MT5 via the ini — MT5 always resolves ExpertParameters from that folder.
    """
    lines = []
    for name, value in all_params.items():
        lines.append(f"{name}={_fmt_set_value(value)}")
    content = "\n".join(lines) + "\n"
    profiles_tester_dir.mkdir(parents=True, exist_ok=True)
    set_path = profiles_tester_dir / filename
    set_path.write_text(content, encoding="utf-16")
    return filename  # return just the bare filename, not the full path


def _run_single_mt5_test(
    terminal_path: str,
    terminal_data_dir: str,
    expert: str,
    all_params: dict,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    deposit: float,
    currency: str,
    leverage: str,
    login: str,
    password: str,
    server: str,
    work_dir: Path,
    run_label: str,
    timeout: int = 1800,
) -> dict:
    """
    Writes a fixed .set file into the terminal's Profiles/Tester/ folder,
    launches a single MT5 backtest, waits for the HTML report, and parses
    it with report_analysis.analyze().

    Returns the full analyze() result dict (curated_summary, deals, etc.)
    Raises RuntimeError if the report is never produced.
    """
    # Set file must live in the terminal's Profiles/Tester/ folder and be
    # referenced by bare filename only — exactly how run_optimization.py works.
    profiles_tester_dir = Path(terminal_data_dir) / "MQL5" / "Profiles" / "Tester"
    set_filename = _make_single_test_set_file(
        all_params, profiles_tester_dir, filename=f"{run_label}.set"
    )
    report_name = run_label

    found_report = run_single_backtest(
        terminal_path=terminal_path,
        terminal_data_dir=terminal_data_dir,
        expert=expert,
        set_file=set_filename,  # bare filename only
        symbol=symbol,
        period=period,
        from_date=from_date,
        to_date=to_date,
        work_dir=str(work_dir),
        login=login,
        password=password,
        server=server,
        report_name=report_name,
        deposit=int(deposit),
        currency=currency,
        leverage=leverage,
        timeout=timeout,
    )

    result = analyze(found_report)

    # Verify MT5 actually used the parameters we intended.
    # ea_inputs contains what the HTML report says MT5 ran with.
    # If a parameter is missing or diverges, the .set file wasn't applied
    # correctly (wrong path, wrong encoding, or unknown parameter name).
    ea_inputs = result.get("ea_inputs", {})
    mismatches = []
    for k, intended in all_params.items():
        actual_str = ea_inputs.get(k)
        if actual_str is None:
            continue  # parameter not echoed in report (some builds omit some)
        try:
            actual = float(actual_str)
            intended_f = float(intended)
            if abs(actual - intended_f) > 1e-6 * max(1, abs(intended_f)):
                mismatches.append(f"  {k}: intended={intended_f}, MT5 used={actual}")
        except (TypeError, ValueError):
            if str(actual_str).strip() != str(intended).strip():
                mismatches.append(f"  {k}: intended={intended!r}, MT5 used={actual_str!r}")
    if mismatches:
        print(f"  [PARAM MISMATCH WARNING for {run_label}] — .set file may not have been applied:")
        for m in mismatches:
            print(m)

    return result


# ---------------------------------------------------------------------------
# Column-name normalisation for MT5 optimization XML columns
# ---------------------------------------------------------------------------

# MT5 names these columns differently across builds and locales. We try a
# prioritised list of candidate names for each metric; first match wins.
_COLUMN_CANDIDATES = {
    "Profit Factor":    ["Profit Factor", "ProfitFactor", "Profit factor"],
    "Sharpe Ratio":     ["Sharpe Ratio",  "SharpeRatio",  "Sharpe ratio"],
    "Max Drawdown (%)": ["Equity DD %",   "Max Drawdown (%)", "Drawdown %", "MaxDrawdown(%)"],
    "Recovery Factor":  ["Recovery Factor", "RecoveryFactor"],
    "Profit":           ["Profit", "Net Profit", "Total Net Profit"],
}


def _normalise_opt_row(row: pd.Series) -> dict:
    """
    Convert a row from parse_optimization_results() into a dict with
    canonical key names, tolerating different MT5 column naming schemes.
    Also carries over all original columns so individual EA parameter values
    (InpTPRatio etc.) are preserved for building the parameter set later.
    """
    d = row.to_dict()
    for canonical, candidates in _COLUMN_CANDIDATES.items():
        if canonical not in d:
            for c in candidates:
                if c in d:
                    d[canonical] = d[c]
                    break
    return d


def _extract_opt_ea_params(row_dict: dict, fixed_params: dict) -> dict:
    """
    Given a normalised optimisation row dict, extract only the keys that are
    NOT metric/result columns and NOT fixed params, to recover the specific EA
    input values MT5 tested in that pass.

    Skip set covers BOTH the canonical keys in _COLUMN_CANDIDATES AND all their
    variant aliases (e.g. "Equity DD %") — the XML uses variant names, not the
    canonical ones, so using only canonical names caused metric columns to slip
    through and be written into the single-test .set file as phantom EA params.
    """
    # All canonical metric names + every variant alias + known MT5 result columns
    _metric_variants = {v for vs in _COLUMN_CANDIDATES.values() for v in vs}
    skip = (
        set(_COLUMN_CANDIDATES.keys())
        | _metric_variants
        | {
            "Pass", "Result", "Trades",
            "Profit Trades (%)", "Loss Trades (%)", "Profit Trades", "Loss Trades",
            "Drawdown $", "Drawdown", "Expected Payoff",
            "Bars", "Ticks", "Initial Deposit", "Withdrawal",
            "Margin Level (%)", "Balance", "Equity",
            "Largest profit trade", "Largest loss trade",
            "Average profit trade", "Average loss trade",
            "Max Drawdown", "Max DD",
        }
    )
    ea_params = {}
    for k, v in row_dict.items():
        if k in skip:
            continue
        if k in fixed_params:
            continue  # fixed value already known; ignore XML duplicate
        ea_params[k] = _parse_opt_value(v)
    return ea_params


def _parse_opt_value(v):
    """
    Parse an optimization XML cell value, preserving integer types.
    MT5 writes integer EA parameters as whole numbers in the XML (e.g. "7").
    Casting them to float and then writing "7.0" to the .set file causes MT5
    to silently fall back to the EA's compiled default for `input int` params
    on some builds — causing the single-test parameters to differ from what
    was actually optimized.
    """
    if v is None:
        return v
    s = str(v).strip()
    # Try int first so "7" stays 7, not 7.0
    try:
        i = int(s)
        # Confirm the string really represents an integer (not "7.5")
        if str(i) == s or str(float(s)) == f"{i}.0":
            return i
    except (ValueError, TypeError):
        pass
    try:
        return float(s)
    except (ValueError, TypeError):
        return v


# ---------------------------------------------------------------------------
# MT5 → Python parameter name mapping for EA generation
# ---------------------------------------------------------------------------

# Maps MT5 EA input names → the Python param names that translate_to_mql5() reads.
_MT5_TO_PY_PARAMS = {
    "InpRangeStartHour":  "range_start_hour",
    "InpRangeEndHour":    "range_end_hour",
    "InpEntryCutoffHour": "entry_cutoff_hour",
    "InpSLBufferPips":    "sl_buffer_pips",
    "InpTPRatio":         "tp_r_multiple",
    "InpMaxRangePips":    "max_range_pips",
    "InpFixedLotSize":    "lot_size",
    "InpLotSize":         "lot_size",
    "InpPipSize":         None,     # passed as pip_size arg, not a params key
    "InpMagicNumber":     None,     # generated fresh by translate_to_mql5
    "InpCommission":      None,     # not an EA input in the generated template
}


def _mt5_params_to_py_params(all_params: dict) -> dict:
    """
    Convert a dict of MT5 EA input names (e.g. InpTPRatio) into the Python
    param-name dict that translate_to_mql5() reads (e.g. tp_r_multiple).
    Unknown MT5 keys are passed through unchanged so the translator emits
    them as dynamic input declarations.
    """
    py = {}
    for k, v in all_params.items():
        mapped = _MT5_TO_PY_PARAMS.get(k, k)   # default: keep as-is
        if mapped is None:
            continue    # explicitly excluded
        py[mapped] = v
    return py


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_mt5_strategy_search(
    # MT5 terminal
    terminal_path: str,
    terminal_data_dir: str,
    expert: str,
    # Symbol / timeframe
    symbol: str,
    period: str,
    # Date windows
    train_from: str,
    train_to: str,
    val_from: str,
    val_to: str,
    holdout_from: str,
    holdout_to: str,
    # EA parameters
    fixed_params: dict,
    opt_ranges: dict,
    # Account
    login: str,
    password: str,
    server: str,
    deposit: float = 100_000,
    currency: str = "USD",
    leverage: str = "1:100",
    # Search settings
    top_n_train: int = 20,
    optimization_mode: int = 2,           # 2 = fast genetic in MT5
    opt_timeout: int = 21_600,            # 6 h for the optimisation
    single_test_timeout: int = 1_800,     # 30 min per single test
    # Storage
    work_dir: str = "optimization_runs",
    symbol_key: str = None,
    db_path: str = "results.db",
    ea_output_dir: str = "generated_eas",
) -> dict:
    """
    Full MT5-native pipeline: Train optimise -> Validate survivors -> Holdout
    -> Monte Carlo -> Store.

    Parameters
    ----------
    fixed_params : dict
        EA inputs held constant across all optimization passes, e.g.
        {"InpLotSize": 1.0, "InpMagicNumber": 20240101}.
    opt_ranges : dict
        EA inputs to sweep, keyed by input name, values are
        (start, step, stop) tuples, e.g.
        {"InpTPRatio": (1.0, 0.5, 3.0), "InpSLBuffer": (0, 2, 20)}.
    top_n_train : int
        How many top Train-optimisation passes to carry forward to Validation.
    work_dir : str
        Base directory for all .ini / .set / report files from this run.
        Each invocation creates a timestamped subfolder inside this dir.

    Returns
    -------
    dict with keys:
        'train_results'   : raw DataFrame from parse_optimization_results()
        'val_survivors'   : list of dicts for passes that passed Validation
        'holdout_results' : list of dicts for passes that ran Holdout (pass or fail)
        'stored_ids'      : list of strategy_id integers saved to the DB
    """
    symbol_key = symbol_key or symbol
    init_strategy_store(db_path)

    run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(work_dir) / f"run_{run_ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    ea_dir = Path(ea_output_dir)
    ea_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"MT5 STRATEGY SEARCH  |  {symbol_key}  |  {run_ts}")
    print("=" * 70)
    print(f"  Expert    : {expert}")
    print(f"  Symbol    : {symbol}  |  Period: {period}")
    print(f"  Train     : {train_from} → {train_to}")
    print(f"  Validation: {val_from} → {val_to}")
    print(f"  Holdout   : {holdout_from} → {holdout_to}")
    print(f"  Fixed params : {fixed_params}")
    print(f"  Opt ranges   : {opt_ranges}")
    print(f"  Work dir  : {run_dir}")
    print()

    # ------------------------------------------------------------------
    # PHASE 1 — MT5 Optimization on Train data
    # ------------------------------------------------------------------
    print("─" * 70)
    print(f"PHASE 1: MT5 Optimization on TRAIN data ({train_from} → {train_to})")
    print("─" * 70)

    # Write the .set file directly into the terminal's Profiles/Tester/ folder.
    # MT5 requires ExpertParameters to be a bare filename resolved from there.
    profiles_tester_dir = Path(terminal_data_dir) / "MQL5" / "Profiles" / "Tester"
    profiles_tester_dir.mkdir(parents=True, exist_ok=True)
    train_set_filename = "strategy_builder_train_opt.set"
    train_set_path = profiles_tester_dir / train_set_filename

    generate_optimization_set_file(
        fixed_params=fixed_params,
        ranges=opt_ranges,
        output_path=str(train_set_path),
    )
    print(f"  Written .set file: {train_set_path}")

    train_report_path = run_optimization(
        terminal_path=terminal_path,
        terminal_data_dir=terminal_data_dir,
        expert=expert,
        set_file=train_set_filename,   # bare filename
        symbol=symbol,
        period=period,
        from_date=train_from,
        to_date=train_to,
        work_dir=str(run_dir / "train"),
        login=login,
        password=password,
        server=server,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        optimization_mode=optimization_mode,
        report_name="strategy_builder_train_opt",
        timeout=opt_timeout,
    )

    print(f"\nParsing optimization report: {train_report_path}")
    train_df = parse_optimization_results(train_report_path)
    print(f"  {len(train_df)} passes found in optimization report.")

    # Filter and rank Train passes
    train_pass_rows = []
    train_months = _months_between(train_from, train_to) or 96.0
    for _, row in train_df.iterrows():
        row_dict = _normalise_opt_row(row)
        passed, reasons = check_train_criteria(row_dict, starting_capital=deposit, months_span=train_months)
        if passed:
            train_pass_rows.append(row_dict)

    print(f"  {len(train_pass_rows)} / {len(train_df)} passes met Train criteria.")

    # If nothing passed strict criteria, warn but fall back to top N by Result
    if not train_pass_rows:
        print(
            f"  WARNING: 0 passes met all Train criteria. "
            f"Falling back to top {top_n_train} by MT5 Result score for Validation."
        )
        top_rows = [_normalise_opt_row(row) for _, row in train_df.head(top_n_train).iterrows()]
    else:
        # Take up to top_n_train from passes (already sorted by Result desc)
        top_rows = train_pass_rows[:top_n_train]

    print(f"\n  Taking top {len(top_rows)} candidates forward to Validation.")

    # ------------------------------------------------------------------
    # PHASE 2 — Validation single tests
    # ------------------------------------------------------------------
    print("\n" + "─" * 70)
    print(f"PHASE 2: Validation single tests ({val_from} → {val_to})")
    print("─" * 70)

    val_dir = run_dir / "validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    val_survivors = []
    for idx, row_dict in enumerate(top_rows):
        ea_params = _extract_opt_ea_params(row_dict, fixed_params)
        all_params = {**fixed_params, **ea_params}

        print(f"\n  [{idx + 1}/{len(top_rows)}] Params: {ea_params}")

        run_label = f"val_{idx + 1:03d}"
        try:
            val_result = _run_single_mt5_test(
                terminal_path=terminal_path,
                terminal_data_dir=terminal_data_dir,
                expert=expert,
                all_params=all_params,
                symbol=symbol,
                period=period,
                from_date=val_from,
                to_date=val_to,
                deposit=deposit,
                currency=currency,
                leverage=leverage,
                login=login,
                password=password,
                server=server,
                work_dir=val_dir,
                run_label=run_label,
                timeout=single_test_timeout,
            )
        except Exception as exc:
            print(f"    ERROR running Validation test: {exc}")
            continue

        curated = val_result["curated_summary"]
        val_deals = val_result.get("deals")
        val_trades = _deals_to_trades(val_deals) if val_deals is not None else None
        val_months = _months_between(val_from, val_to) or 36.0
        passed, reasons = check_oos_criteria(curated, trades=val_trades, months_span=val_months, starting_capital=deposit)
        status = "PASS" if passed else f"FAIL ({', '.join(reasons)})"
        print(f"    {_fmt_curated(curated, 'Val')}  ->  {status}")

        if passed:
            val_survivors.append({
                "ea_params": ea_params,
                "all_params": all_params,
                "train_row": row_dict,
                "val_result": val_result,
            })

    print(f"\n  {len(val_survivors)} / {len(top_rows)} passed Validation.")

    if not val_survivors:
        print("\nNo candidates passed Validation — stopping.")
        return {
            "train_results": train_df,
            "val_survivors": [],
            "holdout_results": [],
            "stored_ids": [],
        }

    # ------------------------------------------------------------------
    # PHASE 3 — Holdout single tests (one-time, untouched)
    # ------------------------------------------------------------------
    print("\n" + "─" * 70)
    print(f"PHASE 3: Holdout single tests ({holdout_from} → {holdout_to})")
    print("─" * 70)

    holdout_dir = run_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)

    holdout_results = []
    stored_ids = []

    for idx, survivor in enumerate(val_survivors):
        ea_params = survivor["ea_params"]
        all_params = survivor["all_params"]

        print(f"\n  [{idx + 1}/{len(val_survivors)}] Params: {ea_params}")

        run_label = f"holdout_{idx + 1:03d}"
        try:
            holdout_result = _run_single_mt5_test(
                terminal_path=terminal_path,
                terminal_data_dir=terminal_data_dir,
                expert=expert,
                all_params=all_params,
                symbol=symbol,
                period=period,
                from_date=holdout_from,
                to_date=holdout_to,
                deposit=deposit,
                currency=currency,
                leverage=leverage,
                login=login,
                password=password,
                server=server,
                work_dir=holdout_dir,
                run_label=run_label,
                timeout=single_test_timeout,
            )
        except Exception as exc:
            print(f"    ERROR running Holdout test: {exc}")
            holdout_results.append({**survivor, "holdout_result": None, "holdout_passed": False,
                                    "holdout_reasons": [str(exc)]})
            continue

        curated = holdout_result["curated_summary"]
        holdout_deals = holdout_result.get("deals")
        holdout_trades = _deals_to_trades(holdout_deals) if holdout_deals is not None else None
        holdout_months = _months_between(holdout_from, holdout_to) or 30.0
        passed, reasons = check_oos_criteria(curated, trades=holdout_trades, months_span=holdout_months, starting_capital=deposit, phase="holdout")
        status = "PASS" if passed else f"FAIL ({', '.join(reasons)})"
        print(f"    {_fmt_curated(curated, 'Holdout')}  ->  {status}")

        holdout_results.append({
            **survivor,
            "holdout_result": holdout_result,
            "holdout_passed": passed,
            "holdout_reasons": reasons,
        })

        if not passed:
            continue

        # ------------------------------------------------------------------
        # PHASE 4 — Combined full-period backtest + Monte Carlo
        # ------------------------------------------------------------------
        print(f"\n    -> Holdout PASSED. Running combined full-period backtest for Monte Carlo...")

        full_dir = run_dir / "full_period"
        full_dir.mkdir(parents=True, exist_ok=True)
        full_label = f"full_{idx + 1:03d}"

        try:
            full_result = _run_single_mt5_test(
                terminal_path=terminal_path,
                terminal_data_dir=terminal_data_dir,
                expert=expert,
                all_params=all_params,
                symbol=symbol,
                period=period,
                from_date=train_from,   # full span: Train start
                to_date=holdout_to,     # through: Holdout end
                deposit=deposit,
                currency=currency,
                leverage=leverage,
                login=login,
                password=password,
                server=server,
                work_dir=full_dir,
                run_label=full_label,
                timeout=single_test_timeout,
            )
        except Exception as exc:
            print(f"    ERROR running full-period backtest: {exc} — skipping Monte Carlo.")
            continue

        # Extract deals for Monte Carlo
        deals = full_result.get("deals")
        if deals is None or deals.empty:
            print("    -> No deals in full-period report — Monte Carlo skipped.")
            continue

        # Convert deals to trade-level DataFrame that monte_carlo expects:
        # it needs columns 'exit_time' and 'profit'. MT5 deals include both
        # entries and exits; we want only closing deals (out deals, type 'out'
        # or positive-volume exits). Filter to rows where Profit is not NaN
        # and != 0 (i.e. closing/settlement deals) and Direction is 'out'.
        mc_trades = _deals_to_trades(deals)
        if mc_trades.empty:
            print("    -> Could not extract trade profits from deals — Monte Carlo skipped.")
            continue

        print(f"    Running Monte Carlo certification ({len(mc_trades)} closed trades "
              f"over full period {train_from} → {holdout_to})...")

        mc_result = certify_strategy(mc_trades, starting_capital=deposit)
        print_certification_result(mc_result)

        if not mc_result["certified"]:
            print("    -> NOT stored: failed Monte Carlo certification.")
            continue

        # ------------------------------------------------------------------
        # PHASE 5 — Store in SQLite
        # ------------------------------------------------------------------
        genome = _params_to_genome(fixed_params, ea_params)

        # Build eval_result dicts matching what strategy_store.extract_phase_metrics expects.
        # Since we're using MT5 reports (no Python backtester trades), we pass
        # the curated dicts directly and empty deals.
        train_ev      = _make_eval_result(survivor["train_row"])
        val_ev        = _make_eval_result_from_curated(survivor["val_result"]["curated_summary"])
        holdout_ev    = _make_eval_result_from_curated(holdout_result["curated_summary"])

        sid = save_passed_strategy(
            db_path=db_path,
            symbol=symbol_key,
            genome=genome,
            train_ev=train_ev,
            val_ev=val_ev,
            holdout_ev=holdout_ev,
            strategy_type="ORB_MT5",
        )
        stored_ids.append(sid)
        print(f"    -> CERTIFIED AND STORED in '{db_path}' (Strategy ID #{sid})")

        # Generate .mq5 EA file for this certified strategy
        py_params = _mt5_params_to_py_params(all_params)
        ea_variant = {
            "params": py_params,
            "filters": {},
            "strategy_name": f"ORB_{symbol_key}_{sid:03d}",
        }
        ea_spec = {"name": f"ORB_{symbol_key}"}
        pip_size = float(fixed_params.get("InpPipSize", 0.0001 if "JPY" not in symbol_key else 0.01))
        ea_filename = str(ea_dir / f"ORB_{symbol_key}_{sid:03d}.mq5")
        try:
            translate_to_mql5(
                ea_variant,
                ea_spec,
                symbol=symbol_key,
                pip_size=pip_size,
                output_path=ea_filename,
            )
        except Exception as exc:
            print(f"    WARNING: EA generation failed: {exc}")

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"FINAL SUMMARY: {len(stored_ids)} strategy(ies) passed all gates and stored.")
    print("=" * 70)
    print_stored_strategies(db_path)

    if stored_ids:
        print(f"  Generated EAs written to: {ea_dir.resolve()}")

    return {
        "train_results":   train_df,
        "val_survivors":   val_survivors,
        "holdout_results": holdout_results,
        "stored_ids":      stored_ids,
        "ea_output_dir":   str(ea_dir.resolve()),
    }


# ---------------------------------------------------------------------------
# Helpers for converting MT5 report data into strategy_store-compatible dicts
# ---------------------------------------------------------------------------

def _deals_to_trades(deals: pd.DataFrame) -> pd.DataFrame:
    """
    Convert an MT5 deals DataFrame (from report_analysis._parse_deals) into a
    minimal trades DataFrame with 'exit_time' and 'profit' columns suitable for
    monte_carlo.trades_to_daily_pnl().

    MT5 deal rows include both entry deals (Direction='in', Profit=0 or None)
    and exit deals (Direction='out', Profit=non-zero). We keep only exit deals
    with a non-null, non-zero Profit and a valid Time.
    """
    df = deals.copy()
    if df.empty:
        return pd.DataFrame(columns=["exit_time", "profit"])

    # Normalise column names (MT5 may call it 'Direction' or 'Type')
    direction_col = None
    for candidate in ("Direction", "Type"):
        if candidate in df.columns:
            direction_col = candidate
            break

    if direction_col is not None:
        # Keep only exit / close deals
        out_mask = df[direction_col].str.lower().isin(["out", "close", "sell", "buy"])
        df = df[out_mask]

    # Keep rows with a real profit (entries have Profit == 0 or NaN)
    if "Profit" in df.columns:
        df = df[df["Profit"].notna() & (df["Profit"] != 0.0)]

    if df.empty:
        return pd.DataFrame(columns=["exit_time", "profit"])

    result = pd.DataFrame({
        "exit_time": pd.to_datetime(df["Time"]) if "Time" in df.columns else pd.NaT,
        "profit":    df["Profit"].astype(float),
    })
    return result.dropna(subset=["exit_time", "profit"]).reset_index(drop=True)


def _make_eval_result(train_row: dict) -> dict:
    """
    Build a minimal eval_result dict from a normalised optimisation XML row,
    mapping MT5 column names to the curated keys that strategy_store.extract_phase_metrics()
    reads. We pass an empty DataFrame for trades since the XML has no deal log.
    """
    def _f(key, default=0.0):
        v = train_row.get(key, default)
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    curated = {
        "Sharpe Ratio":              _f("Sharpe Ratio"),
        "Max Balance Drawdown (%)":  _f("Max Drawdown (%)"),
        "Return/Drawdown Ratio":     _f("Recovery Factor"),
        "Profit Factor":             _f("Profit Factor"),
        "Total Trades":              int(_f("Trades", 0)),
        "Net Profit":                _f("Profit"),
        "Win Rate %":                None,
        "Net Profit %":              None,
        "Max Balance Drawdown ($)":  None,
        "Recovery Factor":           _f("Recovery Factor"),
    }
    return {"curated": curated, "trades": pd.DataFrame()}


def _make_eval_result_from_curated(curated: dict) -> dict:
    """
    Wrap a curated summary dict (from report_analysis.compute_curated_summary)
    in the eval_result structure expected by strategy_store.extract_phase_metrics().
    Trades are empty because the per-phase single-test reports only provide
    summary stats (not a deal log used for trade-counting purposes here).
    """
    # Compute avg_trades_month from the curated summary if possible
    # strategy_store.extract_phase_metrics reads trades DataFrame for this;
    # we don't have individual trades per phase, so we leave trades empty and
    # let the caller deal with avg_trades_month being 0.
    return {"curated": curated, "trades": pd.DataFrame()}