r"""
monte_carlo.py

Monte Carlo simulation for estimating the probability of passing a prop-firm
challenge (default: The5ers High Stakes) versus breaching its drawdown rules,
based on YOUR actual historical daily P&L rather than a theoretical
distribution.

METHOD: block bootstrap. Rather than assuming daily returns are independent
(which would ignore real streakiness/volatility clustering in your actual
results), this resamples contiguous BLOCKS of consecutive historical trading
days (default 10 days per block), stitched together randomly, to build many
alternate "what could have happened" equity paths of the same statistical
character as your real backtest. This is a real simplification worth being
honest about: it assumes the future daily P&L distribution resembles your
backtest period's distribution, and it evaluates drawdown at daily-close
granularity only (it does NOT model intraday equity swings between trades
within the same day — a real account could touch a deeper intraday drawdown
than what shows up in end-of-day balance).

RULE DEFAULTS (per The5ers' own Help Center as of mid-2026 — CONFIRM these
match your specific account type/size before trusting the output, since
The5ers offers multiple High Stakes variants with different profit targets):
    - Max drawdown: 10% of INITIAL balance, static (not trailing off peak)
    - Daily drawdown: 5% of the previous day's closing balance
    - Profit target: 10% (New High Stakes Phase 1) / 5% (Phase 2) — or
      8%/5% if you're on "Classic High Stakes". Pass explicit values if
      these don't match your account.

Usage:
    from portfolio_analysis import build_portfolio
    from monte_carlo import run_monte_carlo, print_monte_carlo_summary

    portfolio = build_portfolio({...}, starting_capital=100_000)
    daily_pnl = portfolio["daily_equity"]["pnl"]

    result = run_monte_carlo(
        daily_pnl,
        starting_capital=100_000,
        profit_target_pct=10.0,   # Phase 1 target — rerun with 5.0 for Phase 2
        max_drawdown_pct=10.0,
        daily_drawdown_pct=5.0,
        num_simulations=5000,
        max_trading_days=250,
    )
    print_monte_carlo_summary(result)
"""

import numpy as np
import pandas as pd


def _build_synthetic_path(daily_values: np.ndarray, length: int, block_size: int, rng) -> np.ndarray:
    """Stitch random contiguous blocks of the real historical daily P&L
    together until reaching the requested length."""
    n = len(daily_values)
    if n <= block_size:
        # Not enough history for the requested block size — fall back to
        # plain i.i.d. resampling instead of block bootstrap.
        return rng.choice(daily_values, size=length, replace=True)

    chunks = []
    total = 0
    while total < length:
        start = rng.integers(0, n - block_size + 1)
        chunk = daily_values[start:start + block_size]
        chunks.append(chunk)
        total += block_size
    path = np.concatenate(chunks)[:length]
    return path


def trades_to_daily_pnl(trades: pd.DataFrame) -> pd.Series:
    """
    Converts a trades DataFrame (as produced by python_backtester.py /
    strategy_builder.py — one row per closed trade, with 'exit_time' and
    'profit' columns) into a daily $ P&L series suitable for run_monte_carlo().
    Multiple trades closing the same calendar day are summed into one value.
    """
    df = trades.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["date"] = df["exit_time"].dt.date
    daily = df.groupby("date")["profit"].sum()
    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


DEFAULT_CERTIFICATION_THRESHOLDS = {
    "phase1_pass_rate_min": 55.0,
    "phase2_pass_rate_min": 60.0,
    "combined_pass_rate_min": 40.0,
    "breach_max_dd_rate_max": 20.0,
    "breach_daily_dd_rate_max": 30.0,
    "max_dd_p90_max": 15.0,
    "max_dd_median_max": 8.0,
}


def check_monte_carlo_pass(phase1_result: dict, phase2_result: dict,
                            thresholds: dict = None) -> tuple:
    """
    Formal go/no-go gate for a strategy's Monte Carlo results, grounded in
    the actual funded-account rules (default thresholds assume a 10% static
    max drawdown / 5% daily drawdown account, e.g. The5ers High Stakes).

    Returns (passed: bool, metrics: dict, reasons: list[str] of failures).
    Combines BOTH phases into the pass/fail decision — a strategy is only
    "certified" if it clears both, since a real challenge attempt requires
    passing both in sequence.
    """
    t = {**DEFAULT_CERTIFICATION_THRESHOLDS, **(thresholds or {})}

    combined_pass_rate = (phase1_result["pass_rate_pct"] / 100) * (phase2_result["pass_rate_pct"] / 100) * 100
    worst_breach_max_dd = max(phase1_result["breach_max_dd_rate_pct"], phase2_result["breach_max_dd_rate_pct"])
    worst_breach_daily_dd = max(phase1_result["breach_daily_dd_rate_pct"], phase2_result["breach_daily_dd_rate_pct"])
    worst_max_dd_p90 = max(phase1_result["max_dd_p90_pct"], phase2_result["max_dd_p90_pct"])
    worst_max_dd_median = max(phase1_result["max_dd_median_pct"], phase2_result["max_dd_median_pct"])

    metrics = {
        "phase1_pass_rate": phase1_result["pass_rate_pct"],
        "phase2_pass_rate": phase2_result["pass_rate_pct"],
        "combined_pass_rate": combined_pass_rate,
        "worst_breach_max_dd_rate": worst_breach_max_dd,
        "worst_breach_daily_dd_rate": worst_breach_daily_dd,
        "worst_max_dd_p90": worst_max_dd_p90,
        "worst_max_dd_median": worst_max_dd_median,
    }

    reasons = []
    if phase1_result["pass_rate_pct"] < t["phase1_pass_rate_min"]:
        reasons.append(f"Phase1 pass rate ({phase1_result['pass_rate_pct']:.1f}%) < {t['phase1_pass_rate_min']}%")
    if phase2_result["pass_rate_pct"] < t["phase2_pass_rate_min"]:
        reasons.append(f"Phase2 pass rate ({phase2_result['pass_rate_pct']:.1f}%) < {t['phase2_pass_rate_min']}%")
    if combined_pass_rate < t["combined_pass_rate_min"]:
        reasons.append(f"Combined pass rate ({combined_pass_rate:.1f}%) < {t['combined_pass_rate_min']}%")
    if worst_breach_max_dd > t["breach_max_dd_rate_max"]:
        reasons.append(f"Breach MaxDD rate ({worst_breach_max_dd:.1f}%) > {t['breach_max_dd_rate_max']}%")
    if worst_breach_daily_dd > t["breach_daily_dd_rate_max"]:
        reasons.append(f"Breach DailyDD rate ({worst_breach_daily_dd:.1f}%) > {t['breach_daily_dd_rate_max']}%")
    if worst_max_dd_p90 > t["max_dd_p90_max"]:
        reasons.append(f"90th %ile MaxDD ({worst_max_dd_p90:.1f}%) > {t['max_dd_p90_max']}%")
    if worst_max_dd_median > t["max_dd_median_max"]:
        reasons.append(f"Median MaxDD ({worst_max_dd_median:.1f}%) > {t['max_dd_median_max']}%")

    return (len(reasons) == 0), metrics, reasons


def certify_strategy(trades: pd.DataFrame, starting_capital: float = 100_000,
                      max_drawdown_pct: float = 10.0, daily_drawdown_pct: float = 5.0,
                      phase1_target_pct: float = 10.0, phase2_target_pct: float = 5.0,
                      num_simulations: int = 5000, max_trading_days: int = 250,
                      thresholds: dict = None, random_seed: int = 42) -> dict:
    """
    Full Monte Carlo certification for one strategy's trades. Converts trades
    to a daily P&L series, runs Phase 1 and Phase 2 simulations, and applies
    check_monte_carlo_pass(). This is the step that should run AFTER a
    strategy has already passed strategy_builder.py's Train/Validation/
    Holdout gate — that gate checks the strategy is real; this one checks
    whether it's actually safe to risk on the funded account.
    """
    daily_pnl = trades_to_daily_pnl(trades)

    phase1 = run_monte_carlo(
        daily_pnl, starting_capital=starting_capital,
        profit_target_pct=phase1_target_pct, max_drawdown_pct=max_drawdown_pct,
        daily_drawdown_pct=daily_drawdown_pct, num_simulations=num_simulations,
        max_trading_days=max_trading_days, random_seed=random_seed,
    )
    phase2 = run_monte_carlo(
        daily_pnl, starting_capital=starting_capital,
        profit_target_pct=phase2_target_pct, max_drawdown_pct=max_drawdown_pct,
        daily_drawdown_pct=daily_drawdown_pct, num_simulations=num_simulations,
        max_trading_days=max_trading_days, random_seed=random_seed,
    )

    passed, metrics, reasons = check_monte_carlo_pass(phase1, phase2, thresholds)

    return {
        "certified": passed,
        "metrics": metrics,
        "reasons": reasons,
        "phase1": phase1,
        "phase2": phase2,
    }


def print_certification_result(result: dict) -> None:
    if "phase1" in result:
        print_monte_carlo_summary(result["phase1"])
    if "phase2" in result:
        print_monte_carlo_summary(result["phase2"])

    m = result["metrics"]
    print("=" * 70)
    print("MONTE CARLO CERTIFICATION")
    print("=" * 70)
    print(f"Phase 1 pass rate:          {m['phase1_pass_rate']:.1f}%")
    print(f"Phase 2 pass rate:          {m['phase2_pass_rate']:.1f}%")
    print(f"Combined pass rate:         {m['combined_pass_rate']:.1f}%")
    print(f"Worst breach MaxDD rate:    {m['worst_breach_max_dd_rate']:.1f}%")
    print(f"Worst breach DailyDD rate:  {m['worst_breach_daily_dd_rate']:.1f}%")
    print(f"Worst 90th %ile MaxDD:      {m['worst_max_dd_p90']:.1f}%")
    print(f"Worst median MaxDD:         {m['worst_max_dd_median']:.1f}%")
    print("-" * 70)
    if result["certified"]:
        print("RESULT: CERTIFIED — clears all Monte Carlo thresholds")
    else:
        print("RESULT: NOT CERTIFIED")
        for r in result["reasons"]:
            print(f"  - {r}")
    print("=" * 70)


def run_monte_carlo(
    daily_pnl,
    starting_capital: float,
    profit_target_pct: float = 10.0,
    max_drawdown_pct: float = 10.0,
    daily_drawdown_pct: float = 5.0,
    num_simulations: int = 5000,
    max_trading_days: int = 250,
    block_size: int = 10,
    random_seed: int = None,
) -> dict:
    """
    daily_pnl: pandas Series or array of historical daily $ P&L (e.g.
        portfolio["daily_equity"]["pnl"] from portfolio_analysis.py).
    """
    values = np.asarray(daily_pnl, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) == 0:
        raise ValueError("daily_pnl has no valid data to resample from")

    rng = np.random.default_rng(random_seed)

    # Historical average is still useful context; best/worst single day is
    # now computed from the simulation output itself (see below), not this
    # raw historical series — the simulations exercise far more day-samples.
    hist_avg_day = float(np.mean(values))

    max_dd_floor = starting_capital * (1 - max_drawdown_pct / 100)
    profit_target_level = starting_capital * (1 + profit_target_pct / 100)

    outcomes = []          # 'passed' / 'breached_max_dd' / 'breached_daily_dd' / 'incomplete'
    days_to_pass = []
    max_dd_pct_per_sim = []
    all_simulated_days = []  # every day's pnl actually visited, across all sims

    for _ in range(num_simulations):
        path = _build_synthetic_path(values, max_trading_days, block_size, rng)

        balance = starting_capital
        prev_day_close = starting_capital
        peak = starting_capital
        sim_max_dd_pct = 0.0
        outcome = "incomplete"
        pass_day = None

        for day_idx, pnl_today in enumerate(path, start=1):
            balance += pnl_today
            all_simulated_days.append(pnl_today)
            peak = max(peak, balance)
            sim_max_dd_pct = max(sim_max_dd_pct, (peak - balance) / peak * 100 if peak else 0)

            # Daily drawdown check (vs previous day's close)
            if balance < prev_day_close * (1 - daily_drawdown_pct / 100):
                outcome = "breached_daily_dd"
                break

            # Absolute max drawdown check (static floor off initial balance)
            if balance <= max_dd_floor:
                outcome = "breached_max_dd"
                break

            # Profit target check
            if balance >= profit_target_level:
                outcome = "passed"
                pass_day = day_idx
                break

            prev_day_close = balance

        outcomes.append(outcome)
        max_dd_pct_per_sim.append(sim_max_dd_pct)
        if pass_day is not None:
            days_to_pass.append(pass_day)

    outcomes = pd.Series(outcomes)
    counts = outcomes.value_counts()
    total = len(outcomes)

    def rate(label):
        return (counts.get(label, 0) / total) * 100

    days_to_pass_arr = np.array(days_to_pass) if days_to_pass else np.array([])
    max_dd_arr = np.array(max_dd_pct_per_sim)

    sim_days_arr = np.array(all_simulated_days)
    sim_best_day = float(np.max(sim_days_arr))
    sim_worst_day = float(np.min(sim_days_arr))
    sim_gains = sim_days_arr[sim_days_arr > 0]
    sim_losses = sim_days_arr[sim_days_arr < 0]
    # "95th percentile" framed the way it's most useful for risk sizing:
    # sim_p95_profit_day = only 5% of simulated days gained MORE than this
    # sim_p95_loss_day    = only 5% of simulated days lost MORE than this (in magnitude)
    sim_p95_profit_day = float(np.percentile(sim_gains, 95)) if len(sim_gains) else None
    sim_p95_loss_day = float(np.percentile(sim_losses, 5)) if len(sim_losses) else None

    return {
        "num_simulations": total,
        "pass_rate_pct": rate("passed"),
        "breach_max_dd_rate_pct": rate("breached_max_dd"),
        "breach_daily_dd_rate_pct": rate("breached_daily_dd"),
        "incomplete_rate_pct": rate("incomplete"),
        "days_to_pass_median": np.median(days_to_pass_arr) if len(days_to_pass_arr) else None,
        "days_to_pass_p10": np.percentile(days_to_pass_arr, 10) if len(days_to_pass_arr) else None,
        "days_to_pass_p90": np.percentile(days_to_pass_arr, 90) if len(days_to_pass_arr) else None,
        "max_dd_median_pct": np.median(max_dd_arr),
        "max_dd_p90_pct": np.percentile(max_dd_arr, 90),
        "max_dd_p99_pct": np.percentile(max_dd_arr, 99),
        "hist_best_day_dollar": sim_best_day,
        "hist_best_day_pct": sim_best_day / starting_capital * 100,
        "hist_worst_day_dollar": sim_worst_day,
        "hist_worst_day_pct": sim_worst_day / starting_capital * 100,
        "hist_avg_day_dollar": hist_avg_day,
        "hist_avg_day_pct": hist_avg_day / starting_capital * 100,
        "sim_p95_profit_day_dollar": sim_p95_profit_day,
        "sim_p95_profit_day_pct": (sim_p95_profit_day / starting_capital * 100) if sim_p95_profit_day is not None else None,
        "sim_p95_loss_day_dollar": sim_p95_loss_day,
        "sim_p95_loss_day_pct": (sim_p95_loss_day / starting_capital * 100) if sim_p95_loss_day is not None else None,
        "params": {
            "starting_capital": starting_capital,
            "profit_target_pct": profit_target_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "daily_drawdown_pct": daily_drawdown_pct,
            "max_trading_days": max_trading_days,
            "block_size": block_size,
        },
    }


def print_monte_carlo_summary(result: dict) -> None:
    p = result["params"]
    print("=" * 70)
    print("MONTE CARLO SIMULATION — PROP CHALLENGE PASS/BREACH PROBABILITY")
    print("=" * 70)
    print(f"Simulations run:           {result['num_simulations']:,}")
    print(f"Starting capital:          {p['starting_capital']:,.2f}")
    print(f"Profit target:             {p['profit_target_pct']}%")
    print(f"Max drawdown limit:        {p['max_drawdown_pct']}% (static, off initial balance)")
    print(f"Daily drawdown limit:      {p['daily_drawdown_pct']}% (off previous day's close)")
    print(f"Max trading days simulated:{p['max_trading_days']}")
    print(f"Resample block size:       {p['block_size']} trading days")
    print("-" * 70)
    print(f"Pass rate:                 {result['pass_rate_pct']:.2f}%")
    print(f"Breached max drawdown:     {result['breach_max_dd_rate_pct']:.2f}%")
    print(f"Breached daily drawdown:   {result['breach_daily_dd_rate_pct']:.2f}%")
    print(f"Incomplete (neither):      {result['incomplete_rate_pct']:.2f}%")
    print("-" * 70)
    if result["days_to_pass_median"] is not None:
        print(f"Days to pass (median):     {result['days_to_pass_median']:.0f}")
        print(f"Days to pass (10th-90th):  {result['days_to_pass_p10']:.0f} - {result['days_to_pass_p90']:.0f}")
    else:
        print("Days to pass:              no simulations passed")
    print(f"Max drawdown reached (median across all sims): {result['max_dd_median_pct']:.2f}%")
    print(f"Max drawdown reached (90th percentile):        {result['max_dd_p90_pct']:.2f}%")
    print(f"Max drawdown reached (99th percentile):         {result['max_dd_p99_pct']:.2f}%")
    print("-" * 70)
    print("LARGEST SINGLE-DAY MOVES (across all simulated days, not just the backtest)")
    print(f"Largest Profit Day:        {result['hist_best_day_dollar']:,.2f} ({result['hist_best_day_pct']:.2f}%)")
    print(f"Largest Loss Day:          {result['hist_worst_day_dollar']:,.2f} ({result['hist_worst_day_pct']:.2f}%)")
    print(f"Average Daily Gain/Loss:   {result['hist_avg_day_dollar']:,.2f} ({result['hist_avg_day_pct']:.2f}%)  "
          f"(from the historical backtest)")
    print("-" * 70)
    print("ACROSS ALL SIMULATED DAYS (every day visited across all "
          f"{result['num_simulations']:,} simulations)")
    if result["sim_p95_profit_day_dollar"] is not None:
        print(f"95th Percentile Profit Day: {result['sim_p95_profit_day_dollar']:,.2f} "
              f"({result['sim_p95_profit_day_pct']:.2f}%)  — only 5% of days gained more than this")
    if result["sim_p95_loss_day_dollar"] is not None:
        print(f"95th Percentile Loss Day:   {result['sim_p95_loss_day_dollar']:,.2f} "
              f"({result['sim_p95_loss_day_pct']:.2f}%)  — only 5% of days lost more than this")
    print("=" * 70)
    print("Reminder: this resamples YOUR historical daily P&L distribution.")
    print("It assumes future behavior resembles the backtest period and only")
    print("checks drawdown at end-of-day granularity, not intraday swings.")


def run_risk_sweep(
    daily_pnl,
    starting_capital: float,
    scale_factors,
    sizing_type: str = "fixed_lot",   # "fixed_lot" or "pct_risk"
    base_value: float = None,         # e.g. 1.0 (lot) or 1.0 (% risk) — used only for labeling
    profit_target_pct: float = 10.0,
    max_drawdown_pct: float = 10.0,
    daily_drawdown_pct: float = 5.0,
    num_simulations: int = 5000,
    max_trading_days: int = 250,
    block_size: int = 10,
    random_seed: int = None,
) -> pd.DataFrame:
    """
    Runs run_monte_carlo() once per scale factor, scaling the historical daily
    $ P&L by each factor as a proxy for a different position size.

    IMPORTANT APPROXIMATION: this assumes $ P&L scales linearly with position
    size — a reasonable first-order approximation for BOTH fixed-lot sizing
    (doubling lots roughly doubles $ profit/loss and per-lot commission) and
    %-risk sizing (doubling risk% roughly doubles the position size computed
    off a given balance). What it does NOT capture: for %-risk sizing, the
    real EA recalculates lot size off the CURRENT (compounding) balance at
    each trade, so the true effect of a risk% change compounds differently
    over a long backtest than a flat linear rescale of the whole P&L series.
    Treat this as a solid directional screening tool to narrow down a range,
    not as a substitute for re-running the actual MT5 backtest at the
    specific lot/risk% you end up choosing.
    """
    rows = []
    for scale in scale_factors:
        scaled_pnl = np.asarray(daily_pnl, dtype=float) * scale
        result = run_monte_carlo(
            scaled_pnl,
            starting_capital=starting_capital,
            profit_target_pct=profit_target_pct,
            max_drawdown_pct=max_drawdown_pct,
            daily_drawdown_pct=daily_drawdown_pct,
            num_simulations=num_simulations,
            max_trading_days=max_trading_days,
            block_size=block_size,
            random_seed=random_seed,
        )

        if base_value is not None:
            scaled_value = base_value * scale
            label = f"{scaled_value:.2f} lot" if sizing_type == "fixed_lot" else f"{scaled_value:.2f}% risk"
        else:
            label = f"{scale:.2f}x"

        rows.append({
            "scale": scale,
            "label": label,
            "pass_rate_pct": result["pass_rate_pct"],
            "breach_max_dd_rate_pct": result["breach_max_dd_rate_pct"],
            "breach_daily_dd_rate_pct": result["breach_daily_dd_rate_pct"],
            "incomplete_rate_pct": result["incomplete_rate_pct"],
            "days_to_pass_median": result["days_to_pass_median"],
            "max_dd_median_pct": result["max_dd_median_pct"],
            "max_dd_p90_pct": result["max_dd_p90_pct"],
        })

    return pd.DataFrame(rows)


def print_risk_sweep_table(df: pd.DataFrame) -> None:
    print("=" * 100)
    print("RISK-SCALING SWEEP (proxy for different fixed-lot sizes or %-risk settings)")
    print("=" * 100)
    display = df.copy()
    for col in ["pass_rate_pct", "breach_max_dd_rate_pct", "breach_daily_dd_rate_pct",
                "incomplete_rate_pct", "max_dd_median_pct", "max_dd_p90_pct"]:
        display[col] = display[col].map(lambda x: f"{x:.2f}%")
    display["days_to_pass_median"] = display["days_to_pass_median"].map(
        lambda x: f"{x:.0f}" if pd.notna(x) else "-")
    display = display.rename(columns={
        "label": "Size",
        "pass_rate_pct": "Pass %",
        "breach_max_dd_rate_pct": "Breach MaxDD %",
        "breach_daily_dd_rate_pct": "Breach Daily %",
        "incomplete_rate_pct": "Incomplete %",
        "days_to_pass_median": "Median Days",
        "max_dd_median_pct": "Median MaxDD",
        "max_dd_p90_pct": "90th %ile MaxDD",
    })
    print(display[["Size", "Pass %", "Breach MaxDD %", "Breach Daily %", "Incomplete %",
                    "Median Days", "Median MaxDD", "90th %ile MaxDD"]].to_string(index=False))
    print("\nApproximation note: $ P&L scaled linearly per size — see run_risk_sweep()")
    print("docstring for what this does and doesn't capture, especially for %-risk sizing.")


if __name__ == "__main__":
    import sys
    import json
    from portfolio_analysis import build_portfolio

    if len(sys.argv) < 2:
        print("Usage: python monte_carlo.py <config.json> [starting_capital] [profit_target_pct]")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        paths = json.load(f)

    cap = float(sys.argv[2]) if len(sys.argv) > 2 else 100_000.0
    target = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

    portfolio = build_portfolio(paths, starting_capital=cap)
    result = run_monte_carlo(
        portfolio["daily_equity"]["pnl"],
        starting_capital=cap,
        profit_target_pct=target,
    )
    print_monte_carlo_summary(result)