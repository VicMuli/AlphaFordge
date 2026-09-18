r"""
walk_forward.py

Tests whether a strategy's FIXED parameters (the .set file you've already
chosen) perform consistently across different rolling time windows, or
whether performance is concentrated in/dependent on one lucky period —
a direct, practical overfitting check.

THIS IS NOT walk-forward OPTIMIZATION. It does not re-tune parameters per
window. It runs the SAME parameters repeatedly across consecutive slices
of history and compares the results. If performance holds up reasonably
well window to window, that's evidence the edge generalizes rather than
being curve-fit to one period. If performance collapses or flips sign in
several windows, that's a real overfitting warning sign — the same kind of
regime-dependency problem already flagged with the JPY mean-reversion and
Ultimate Oscillator EAs.

(True walk-forward OPTIMIZATION — re-optimizing parameters per in-sample
window, then testing on the following out-of-sample window, then rolling
forward — requires automating MT5's Optimization mode, which is a
meaningfully bigger build with a different report/results format. This
module can be extended to that later if useful.)

Usage:
    from mt5_runner import run_single_backtest
    from report_analysis import analyze
    from walk_forward import generate_rolling_windows, run_walk_forward, print_walk_forward_summary

    windows = generate_rolling_windows("2016.01.01", "2026.01.01", window_months=12, step_months=6)

    base_kwargs = dict(
        terminal_path=r"C:\Users\HP\AppData\Roaming\MetaTrader\terminal64.exe",
        terminal_data_dir=r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\CDE1ED2F37049DA2E508A3C44B675D09",
        expert="XAUB Quant 1.ex5",
        set_file="Q1.set",
        symbol="XAUUSD Dukascopy",
        period="H1",
        deposit=100000,
        login="52909674",
        password="3F!@4rwo7wc02f",
        server="ICMarketsKE-Demo",
    )

    results = run_walk_forward(
        run_single_backtest, analyze, base_kwargs, windows,
        base_work_dir=r"C:\Users\HP\Desktop\AlphaFordge\walk_forward_xaub1",
    )
    print_walk_forward_summary(results)
"""

from datetime import date
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Window generation
# ---------------------------------------------------------------------------

def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, 28)  # avoid month-length edge cases (Feb, etc.)
    return date(year, month, day)


def generate_rolling_windows(overall_from: str, overall_to: str,
                              window_months: int = 12, step_months: int = 6) -> list:
    """
    Dates in MT5 format 'YYYY.MM.DD'. Returns a list of (from_str, to_str)
    tuples, each window_months long, stepping forward step_months at a time,
    stopping once a window would extend past overall_to.
    """
    start = date(*map(int, overall_from.split(".")))
    end = date(*map(int, overall_to.split(".")))

    windows = []
    cursor = start
    while True:
        window_end = _add_months(cursor, window_months)
        if window_end > end:
            break
        windows.append((cursor.strftime("%Y.%m.%d"), window_end.strftime("%Y.%m.%d")))
        cursor = _add_months(cursor, step_months)
    return windows


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_walk_forward(run_single_backtest_fn, analyze_fn, base_kwargs: dict,
                      windows: list, base_work_dir: str,
                      db_path: str = None, wf_run_config: dict = None,
                      store_deals: bool = False) -> list:
    """
    run_single_backtest_fn: pass mt5_runner.run_single_backtest
    analyze_fn: pass report_analysis.analyze
    base_kwargs: everything run_single_backtest needs EXCEPT from_date,
        to_date, work_dir, report_name (those are set per window here).
    db_path / wf_run_config: OPTIONAL. If both are given, each window's
        result is also stored directly in results_db.py's database (via
        insert_run), tagged with wf_run_config's strategy_name so it can
        later be pulled back out with load_walk_forward_table_from_db()
        instead of needing to keep deals.csv files around. wf_run_config
        needs at least: strategy_name, symbol, period, set_file, expert,
        deposit. store_deals defaults to False here since a walk-forward
        batch can have many windows — set True only if you need the full
        trade list per window later.
    Returns a list of dicts, one per window, each with the window dates,
    the curated_summary, and monthly/yearly DataFrames from report_analysis.
    """
    results = []
    for i, (from_date, to_date) in enumerate(windows, start=1):
        window_work_dir = f"{base_work_dir}\\window_{i:03d}"
        report_name = f"wf_window_{i:03d}"

        print(f"Running window {i}/{len(windows)}: {from_date} to {to_date} ...")

        report_path = run_single_backtest_fn(
            **base_kwargs,
            from_date=from_date,
            to_date=to_date,
            work_dir=window_work_dir,
            report_name=report_name,
        )
        analyzed = analyze_fn(report_path)

        run_id = None
        if db_path is not None and wf_run_config is not None:
            from results_db import insert_run
            run_config = dict(wf_run_config)
            run_config["from_date"] = from_date
            run_config["to_date"] = to_date
            run_config["report_path"] = str(report_path)
            run_config["notes"] = f"walk-forward window {i}/{len(windows)}"
            run_id = insert_run(db_path, run_config, analyzed, store_deals=store_deals)

        results.append({
            "window_index": i,
            "from_date": from_date,
            "to_date": to_date,
            "curated_summary": analyzed["curated_summary"],
            "monthly": analyzed["monthly"],
            "yearly": analyzed["yearly"],
            "run_id": run_id,
        })
        print(f"  -> Net Profit: {analyzed['curated_summary']['Net Profit']:,.2f}  "
              f"Profit Factor: {analyzed['curated_summary']['Profit Factor']}  "
              f"Trades: {analyzed['curated_summary']['Total Trades']}"
              + (f"  [stored as run_id={run_id}]" if run_id else ""))

    return results


def load_walk_forward_table_from_db(db_path: str, strategy_name: str) -> pd.DataFrame:
    """
    Rebuilds the same table build_walk_forward_table() produces, but pulled
    straight from results_db.py's database instead of needing the original
    in-memory results list — e.g. in a later session, without rerunning
    anything. Assumes all windows for this strategy were stored under the
    same strategy_name (as run_walk_forward's db_path/wf_run_config does),
    and orders windows chronologically by from_date.
    """
    from results_db import query_runs

    df = query_runs(db_path, strategy_name=strategy_name)
    if df.empty:
        raise ValueError(f"No stored runs found for strategy_name='{strategy_name}' in {db_path}")

    df = df.sort_values("from_date").reset_index(drop=True)
    table = pd.DataFrame({
        "Window": range(1, len(df) + 1),
        "From": df["from_date"],
        "To": df["to_date"],
        "Trades": df["total_trades"],
        "Net Profit": df["net_profit"],
        "Net Profit %": df["net_profit_pct"],
        "Profit Factor": df["profit_factor"],
        "Sharpe": df["sharpe_ratio"],
        "Max DD %": df["max_dd_pct"],
        "Win Rate %": df["win_rate_pct"],
    })
    return table


# ---------------------------------------------------------------------------
# Aggregation / stability analysis
# ---------------------------------------------------------------------------

def build_walk_forward_table(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        c = r["curated_summary"]
        rows.append({
            "Window": r["window_index"],
            "From": r["from_date"],
            "To": r["to_date"],
            "Trades": c["Total Trades"],
            "Net Profit": c["Net Profit"],
            "Net Profit %": c.get("Net Profit %"),
            "Profit Factor": c["Profit Factor"],
            "Sharpe": c["Sharpe Ratio"],
            "Max DD %": c["Max Balance Drawdown (%)"],
            "Win Rate %": c["Win Rate %"],
        })
    return pd.DataFrame(rows)


def compute_stability_stats(table: pd.DataFrame) -> dict:
    def cv(series):
        """Coefficient of variation — lower means more consistent across windows.
        Undefined (returns None) if the mean is ~0, since CV blows up meaninglessly there."""
        m = series.mean()
        if m == 0 or pd.isna(m):
            return None
        return float(series.std() / abs(m))

    profitable_windows = int((table["Net Profit"] > 0).sum())
    total_windows = len(table)

    return {
        "total_windows": total_windows,
        "profitable_windows": profitable_windows,
        "profitable_windows_pct": (profitable_windows / total_windows * 100) if total_windows else None,
        "net_profit_mean": table["Net Profit"].mean(),
        "net_profit_std": table["Net Profit"].std(),
        "net_profit_cv": cv(table["Net Profit"]),
        "net_profit_pct_mean": table["Net Profit %"].mean(),
        "net_profit_pct_std": table["Net Profit %"].std(),
        "net_profit_pct_cv": cv(table["Net Profit %"]),
        "profit_factor_mean": table["Profit Factor"].mean(),
        "profit_factor_cv": cv(table["Profit Factor"]),
        "worst_window_profit": table["Net Profit"].min(),
        "worst_window_index": table.loc[table["Net Profit"].idxmin(), "Window"],
        "best_window_profit": table["Net Profit"].max(),
        "best_window_index": table.loc[table["Net Profit"].idxmax(), "Window"],
    }


def print_walk_forward_summary(results: list) -> None:
    table = build_walk_forward_table(results)
    _print_stability_report(table)


def print_walk_forward_summary_from_db(db_path: str, strategy_name: str) -> None:
    """Same output as print_walk_forward_summary(), but rebuilt straight
    from stored runs in results_db.py — no need to keep the original
    results list around or rerun anything."""
    table = load_walk_forward_table_from_db(db_path, strategy_name)
    _print_stability_report(table)


def _print_stability_report(table: pd.DataFrame) -> None:
    stats = compute_stability_stats(table)

    print("=" * 90)
    print("WALK-FORWARD STABILITY TEST (fixed parameters across rolling windows)")
    print("=" * 90)
    print(table.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    print("-" * 90)
    print(f"Windows profitable:        {stats['profitable_windows']}/{stats['total_windows']} "
          f"({stats['profitable_windows_pct']:.1f}%)")
    print(f"Net Profit — mean/std ($): {stats['net_profit_mean']:,.2f} / {stats['net_profit_std']:,.2f}")
    if stats["net_profit_cv"] is not None:
        print(f"Net Profit CV ($-based):   {stats['net_profit_cv']:.2f}")
    print(f"Net Profit — mean/std (%): {stats['net_profit_pct_mean']:.2f}% / {stats['net_profit_pct_std']:.2f}%")
    if stats["net_profit_pct_cv"] is not None:
        print(f"Net Profit CV (%-based):   {stats['net_profit_pct_cv']:.2f} "
              f"(lower = more consistent; above ~1.0 means swings are as large as "
              f"the average itself — a real overfitting warning sign)")
    print("(The $-based CV can be distorted by fixed-lot strategies over long periods where")
    print(" the underlying instrument's price changed a lot — e.g. gold rising several-fold")
    print(" makes later windows' $ swings mechanically larger regardless of edge quality.")
    print(" The %-based CV is the more apples-to-apples comparison across windows.)")
    print(f"Profit Factor — mean:      {stats['profit_factor_mean']:.2f}")
    print(f"Worst window:              #{stats['worst_window_index']} ({stats['worst_window_profit']:,.2f})")
    print(f"Best window:               #{stats['best_window_index']} ({stats['best_window_profit']:,.2f})")
    print("=" * 90)
    print("Read this as: consistent profit factor / positive net profit across most")
    print("windows = a real, generalizing edge. One or two great windows carrying an")
    print("otherwise flat/negative set = likely overfit to a specific period or regime.")