"""
run_portfolio_montecarlo.py - Prop-Firm Monte Carlo Simulation Runner for Quant Portfolios

What this does
---------------
Takes a portfolio folder already produced by build_quant_portfolio.py and runs a
prop-firm-rules Monte Carlo simulation on its combined trade stream, then writes
the results to a Word document inside that same portfolio folder.

Unlike a generic "randomise the equity curve" Monte Carlo, this one evaluates each
simulated path against actual prop-firm pass/fail mechanics:

  * Static max drawdown  - a hard floor at a fixed % below the INITIAL balance.
                           Touch it and the account is dead, no recovery.
  * Daily drawdown       - a floor at a fixed % below each trading DAY'S starting
                           balance, re-evaluated every day.
  * Phase profit target  - the % gain needed to pass.
  * Optional day limit   - fail if the target isn't reached in time.

Every simulated path is walked trade-by-trade in chronological order so the daily
drawdown rule can be checked against real day boundaries, and a path is stopped
the moment it breaches - exactly as a prop firm would close the account.

Randomisation methods
----------------------
  "resample"  - bootstrap: draw trades WITH replacement (default). Models "what if
                a different but statistically similar sequence of trades occurred".
  "shuffle"   - permutation: same trades, random order, no replacement. Models
                "what if these exact trades had arrived in a different order".
                Preserves the true total P&L of the backtest.
  "skip"      - randomly drop a % of trades, keep the rest in original order.
                Models missed trades from downtime, latency, or filters.

Trade timestamps (and therefore the real trades-per-day structure) are preserved
from the actual backtest, with the randomised P&L mapped onto them. That keeps the
daily-drawdown check realistic rather than assuming one trade per day.

Usage
-----
Edit the USER CONFIGURATION block below - point PORTFOLIO_DIR at the portfolio you
want to test (or set QUANT_NAME/PORTFOLIO_NAME and let it resolve the path) - then:

    python run_portfolio_montecarlo.py

Output written into the portfolio folder:

    <Portfolio>_MonteCarlo_Report.docx
    mc_equity_paths.png
    mc_final_return_hist.png
    mc_max_drawdown_hist.png
    mc_days_to_target_hist.png
    montecarlo_results.csv
"""

import sys
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

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except ImportError:
    docx = None
    print("WARNING: python-docx not installed. Run: pip install python-docx")


# ===========================================================================
# USER CONFIGURATION
# ===========================================================================

# --- Which portfolio to simulate -------------------------------------------
# Option A: give the full path to the portfolio folder directly.
PORTFOLIO_DIR = None

# Option B: leave PORTFOLIO_DIR = None and set these instead; the script will
# resolve <WORK_DIR>/Quant_Portfolios/<QUANT_NAME>_Quant_Portfolios/<PORTFOLIO_NAME>.
QUANT_NAME = "TRB"
PORTFOLIO_NAME = "TRB_Quant_Portfolio_001"

# --- Simulation settings ----------------------------------------------------
N_SIMULATIONS = 5000
RANDOM_SEED = 42

# "resample" (bootstrap w/ replacement), "shuffle" (permutation), or "skip".
MC_METHOD = "resample"

# Only used when MC_METHOD == "skip": fraction of trades randomly dropped.
SKIP_FRACTION = 0.10

# Optional: multiply every trade's P&L by a random factor each simulation to
# model slippage/spread variance. 0.0 disables it. 0.10 = +/-10% per-trade noise.
PNL_NOISE = 0.0

# How many trades each simulated path runs (None = same count as the backtest).
TRADES_PER_SIM = None


# --- Prop firm rule set -----------------------------------------------------
# Defaults below match The5ers High Stakes: 10% static max DD, 5% daily DD,
# Phase 1 target 10%, Phase 2 target 5%.
PROP_FIRM_NAME = "The5ers High Stakes"

STATIC_MAX_DD_PCT = 10.0   # hard floor, % below the INITIAL balance
DAILY_DD_PCT = 5.0         # floor, % below each day's STARTING balance

PHASES = [
    {"name": "Phase 1", "target_pct": 8.0, "max_days": None},
    {"name": "Phase 2", "target_pct": 5.0, "max_days": None},
]

# Account size the prop rules are evaluated on. None = use the portfolio's own
# deposit from portfolio_manifest.json.
ACCOUNT_SIZE = None


# ===========================================================================
# PORTFOLIO LOADING
# ===========================================================================


def resolve_portfolio_dir() -> Path | None:
    """Locate the portfolio folder from either the explicit path or quant/name pair."""
    if PORTFOLIO_DIR:
        p = Path(PORTFOLIO_DIR)
        if p.exists():
            return p
        print(f"ERROR: PORTFOLIO_DIR does not exist: {p}")
        return None

    try:
        from run_optimization import WORK_DIR
    except ImportError:
        print("ERROR: PORTFOLIO_DIR not set and run_optimization.WORK_DIR not importable.")
        return None

    p = Path(WORK_DIR) / "Quant_Portfolios" / f"{QUANT_NAME}_Quant_Portfolios" / PORTFOLIO_NAME
    if p.exists():
        return p

    # Fallback search across work directories
    work_path = Path(WORK_DIR)
    script_dir = Path(__file__).parent.resolve()
    search_roots = [
        work_path,
        work_path.parent,
        script_dir / "Multi_Market_Quant_Portfolio",
        script_dir / "MultiMarket portfolio",
        script_dir / "Quant_Portfolios",
        script_dir / "optimization_runs",
        script_dir,
    ]
    env_out = os.environ.get("AF_PORTFOLIO_OUTPUT_DIR", "").strip()
    if env_out:
        p_env = Path(env_out)
        if not p_env.is_absolute():
            p_env = script_dir / env_out
        if p_env.exists() and p_env not in search_roots:
            search_roots.insert(0, p_env)
    for root in search_roots:
        if root.exists():
            try:
                cand = root / PORTFOLIO_NAME
                if cand.exists() and cand.is_dir() and ((cand / "combined_trades.csv").exists() or (cand / "portfolio_manifest.json").exists()):
                    return cand
                for match in root.rglob(PORTFOLIO_NAME):
                    if match.is_dir() and ((match / "combined_trades.csv").exists() or (match / "portfolio_manifest.json").exists()):
                        return match
            except OSError:
                pass

    print(f"ERROR: Resolved portfolio folder does not exist: {p}")
    return None


def load_portfolio(portfolio_dir: Path):
    """Read the combined trade stream and deposit for a built portfolio."""
    trades_csv = portfolio_dir / "combined_trades.csv"
    if not trades_csv.exists():
        print(f"ERROR: {trades_csv.name} not found in {portfolio_dir}.")
        print("       Re-run build_quant_portfolio.py for this portfolio to generate it.")
        return None, None, None

    trades = pd.read_csv(trades_csv)
    trades["Time"] = pd.to_datetime(trades["Time"], errors="coerce")
    trades = trades.dropna(subset=["Time"]).sort_values("Time").reset_index(drop=True)
    trades["NetPnl"] = pd.to_numeric(trades["NetPnl"], errors="coerce").fillna(0.0)

    deposit = None
    manifest_path = portfolio_dir / "portfolio_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            deposit = float(manifest.get("deposit")) if manifest.get("deposit") else None
        except Exception as exc:
            print(f"    [WARNING] Could not read portfolio_manifest.json: {exc}")

    if ACCOUNT_SIZE:
        deposit = float(ACCOUNT_SIZE)
    if not deposit:
        deposit = 2500.0
        print(f"    [WARNING] No deposit found; defaulting to ${deposit:,.2f}.")

    return trades, deposit, manifest


# ===========================================================================
# SIMULATION CORE
# ===========================================================================


def build_pnl_matrix(pnl: np.ndarray, n_sims: int, n_trades: int, rng: np.random.Generator) -> np.ndarray:
    """Generate the (n_sims x n_trades) randomised P&L matrix for the chosen method."""
    source_n = len(pnl)

    if MC_METHOD == "resample":
        idx = rng.integers(0, source_n, size=(n_sims, n_trades))
        matrix = pnl[idx]

    elif MC_METHOD == "shuffle":
        matrix = np.empty((n_sims, n_trades), dtype=float)
        for i in range(n_sims):
            perm = rng.permutation(source_n)[:n_trades]
            row = pnl[perm]
            if len(row) < n_trades:
                # Requested more trades than exist; tile the permutation out.
                reps = int(np.ceil(n_trades / max(len(row), 1)))
                row = np.tile(row, reps)[:n_trades]
            matrix[i] = row

    elif MC_METHOD == "skip":
        matrix = np.empty((n_sims, n_trades), dtype=float)
        for i in range(n_sims):
            keep = rng.random(source_n) >= SKIP_FRACTION
            row = pnl[keep]
            if len(row) == 0:
                row = np.zeros(1)
            if len(row) < n_trades:
                reps = int(np.ceil(n_trades / len(row)))
                row = np.tile(row, reps)[:n_trades]
            matrix[i] = row[:n_trades]

    else:
        raise ValueError(f"Unknown MC_METHOD: {MC_METHOD!r}. Use 'resample', 'shuffle', or 'skip'.")

    if PNL_NOISE and PNL_NOISE > 0:
        noise = 1.0 + rng.uniform(-PNL_NOISE, PNL_NOISE, size=matrix.shape)
        matrix = matrix * noise

    return matrix


def evaluate_path(pnl_path: np.ndarray, day_index: np.ndarray, day_starts: np.ndarray,
                  deposit: float, target_pct: float, max_days):
    """
    Walk one simulated path trade-by-trade under prop firm rules.

    Returns a dict describing how the account ended: passed, breached on the
    static floor, breached on a daily floor, or ran out of road.

    day_index maps each trade to its day number; day_starts[d] is True on the
    first trade of a new day, which is when the daily floor is re-based.
    """
    static_floor = deposit * (1.0 - STATIC_MAX_DD_PCT / 100.0)
    target_balance = deposit * (1.0 + target_pct / 100.0)

    balance = deposit
    peak = deposit
    max_dd = 0.0
    day_start_balance = deposit
    daily_floor = day_start_balance * (1.0 - DAILY_DD_PCT / 100.0)

    result = {
        "outcome": "incomplete",
        "final_balance": deposit,
        "final_return_pct": 0.0,
        "max_dd_pct": 0.0,
        "trades_taken": 0,
        "days_taken": 0,
    }

    for i in range(len(pnl_path)):
        # Re-base the daily floor at the start of each new trading day.
        if day_starts[i]:
            day_start_balance = balance
            daily_floor = day_start_balance * (1.0 - DAILY_DD_PCT / 100.0)

        balance += pnl_path[i]

        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

        day_no = int(day_index[i]) + 1

        if balance <= static_floor:
            result.update({
                "outcome": "breach_static",
                "final_balance": balance,
                "final_return_pct": (balance / deposit - 1.0) * 100.0,
                "max_dd_pct": max_dd,
                "trades_taken": i + 1,
                "days_taken": day_no,
            })
            return result

        if balance <= daily_floor:
            result.update({
                "outcome": "breach_daily",
                "final_balance": balance,
                "final_return_pct": (balance / deposit - 1.0) * 100.0,
                "max_dd_pct": max_dd,
                "trades_taken": i + 1,
                "days_taken": day_no,
            })
            return result

        if balance >= target_balance:
            result.update({
                "outcome": "passed",
                "final_balance": balance,
                "final_return_pct": (balance / deposit - 1.0) * 100.0,
                "max_dd_pct": max_dd,
                "trades_taken": i + 1,
                "days_taken": day_no,
            })
            return result

        if max_days is not None and day_no > max_days:
            result.update({
                "outcome": "timeout",
                "final_balance": balance,
                "final_return_pct": (balance / deposit - 1.0) * 100.0,
                "max_dd_pct": max_dd,
                "trades_taken": i + 1,
                "days_taken": day_no,
            })
            return result

    result.update({
        "outcome": "no_target",
        "final_balance": balance,
        "final_return_pct": (balance / deposit - 1.0) * 100.0,
        "max_dd_pct": max_dd,
        "trades_taken": len(pnl_path),
        "days_taken": int(day_index[-1]) + 1 if len(day_index) else 0,
    })
    return result


def run_phase_simulation(pnl_matrix, day_index, day_starts, deposit, phase):
    """Evaluate every simulated path for one phase's rule set."""
    rows = []
    for i in range(pnl_matrix.shape[0]):
        rows.append(
            evaluate_path(
                pnl_matrix[i],
                day_index,
                day_starts,
                deposit,
                phase["target_pct"],
                phase["max_days"],
            )
        )
    return pd.DataFrame(rows)


def summarise_phase(results: pd.DataFrame) -> dict:
    n = len(results)
    counts = results["outcome"].value_counts().to_dict()
    passed = counts.get("passed", 0)
    breach_static = counts.get("breach_static", 0)
    breach_daily = counts.get("breach_daily", 0)
    timeout = counts.get("timeout", 0)
    no_target = counts.get("no_target", 0)

    passed_rows = results[results["outcome"] == "passed"]

    return {
        "n": n,
        "pass_rate": passed / n * 100.0 if n else 0.0,
        "breach_any_rate": (breach_static + breach_daily) / n * 100.0 if n else 0.0,
        "breach_static_rate": breach_static / n * 100.0 if n else 0.0,
        "breach_daily_rate": breach_daily / n * 100.0 if n else 0.0,
        "timeout_rate": timeout / n * 100.0 if n else 0.0,
        "no_target_rate": no_target / n * 100.0 if n else 0.0,
        "median_days_to_pass": float(passed_rows["days_taken"].median()) if len(passed_rows) else float("nan"),
        "p90_days_to_pass": float(passed_rows["days_taken"].quantile(0.90)) if len(passed_rows) else float("nan"),
        "median_trades_to_pass": float(passed_rows["trades_taken"].median()) if len(passed_rows) else float("nan"),
        "median_max_dd": float(results["max_dd_pct"].median()),
        "p95_max_dd": float(results["max_dd_pct"].quantile(0.95)),
        "worst_max_dd": float(results["max_dd_pct"].max()),
    }


def run_unconstrained_paths(pnl_matrix, deposit):
    """Full-length equity paths with no phase stop, for distribution/curve charts."""
    equity = deposit + np.cumsum(pnl_matrix, axis=1)
    final_balance = equity[:, -1]
    running_peak = np.maximum.accumulate(equity, axis=1)
    dd_pct = (running_peak - equity) / np.where(running_peak > 0, running_peak, 1.0) * 100.0
    return {
        "equity": equity,
        "final_return_pct": (final_balance / deposit - 1.0) * 100.0,
        "max_dd_pct": dd_pct.max(axis=1),
    }


# ===========================================================================
# CHARTS
# ===========================================================================


def chart_equity_paths(equity, deposit, actual_equity, output_dir: Path, max_paths=250):
    try:
        fig, ax = plt.subplots(figsize=(10.5, 5.5))
        n_show = min(max_paths, equity.shape[0])
        for i in range(n_show):
            ax.plot(equity[i], color="steelblue", alpha=0.06, linewidth=0.7)

        pct = np.percentile(equity, [5, 50, 95], axis=0)
        ax.plot(pct[1], color="black", linewidth=2.0, label="Median path")
        ax.plot(pct[0], color="darkred", linewidth=1.5, linestyle="--", label="5th percentile")
        ax.plot(pct[2], color="darkgreen", linewidth=1.5, linestyle="--", label="95th percentile")

        if actual_equity is not None:
            ax.plot(actual_equity, color="orange", linewidth=2.0, label="Actual backtest")

        floor = deposit * (1.0 - STATIC_MAX_DD_PCT / 100.0)
        ax.axhline(floor, color="red", linewidth=1.4, linestyle=":",
                   label=f"Static DD floor ({STATIC_MAX_DD_PCT:.0f}%)")
        ax.axhline(deposit, color="gray", linewidth=1.0, linestyle="--")

        ax.set_title(f"Monte Carlo Equity Paths ({MC_METHOD}, n={equity.shape[0]:,})",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Trade Number")
        ax.set_ylabel("Balance ($)")
        ax.legend(fontsize=8, loc="upper left")
        path = output_dir / "mc_equity_paths.png"
        fig.tight_layout()
        fig.savefig(path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        return path
    except Exception as exc:
        plt.close("all")
        print(f"    [WARNING] Equity path chart failed: {exc}")
        return None


def chart_histogram(values, title, xlabel, output_dir: Path, filename,
                    actual_value=None, vlines=None, color="steelblue"):
    try:
        values = np.asarray(values)
        values = values[np.isfinite(values)]
        if values.size == 0:
            return None

        fig, ax = plt.subplots(figsize=(9.5, 4.8))
        ax.hist(values, bins=60, color=color, edgecolor="white", alpha=0.85)
        ax.axvline(float(np.median(values)), color="black", linewidth=1.8,
                   label=f"Median {np.median(values):,.2f}")

        for pct, style in [(5, "--"), (95, "--")]:
            v = float(np.percentile(values, pct))
            ax.axvline(v, color="dimgray", linestyle=style, linewidth=1.2,
                       label=f"P{pct} {v:,.2f}")

        if actual_value is not None and np.isfinite(actual_value):
            ax.axvline(float(actual_value), color="orange", linewidth=2.0,
                       label=f"Actual {actual_value:,.2f}")

        for v, lbl, col in (vlines or []):
            ax.axvline(v, color=col, linestyle=":", linewidth=1.8, label=lbl)

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Simulations")
        ax.legend(fontsize=8)
        path = output_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        return path
    except Exception as exc:
        plt.close("all")
        print(f"    [WARNING] Histogram '{filename}' failed: {exc}")
        return None


# ===========================================================================
# WORD REPORT
# ===========================================================================


def _set_cell_text(cell, text, bold=False):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(str(text))
    run.bold = bold


def _shade_cell(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _add_kv_table(doc, rows):
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for key, value in rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], key, bold=True)
        _set_cell_text(cells[1], value)
    return table


def _rate_shade(pct):
    """Green >=70%, amber 40-70%, red <40% - a rough prop-readiness read."""
    if pct >= 70.0:
        return "C6EFCE"
    if pct >= 40.0:
        return "FFEB9C"
    return "FFC7CE"


def create_montecarlo_word_doc(doc_path, portfolio_name, manifest, deposit, trades,
                               phase_summaries, phase_results, uncon, charts, actual):
    if docx is None:
        print("    [ERROR] python-docx not installed; cannot create Word report.")
        return None

    doc = docx.Document()
    title = doc.add_heading(f"Monte Carlo Simulation Report - {portfolio_name}", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(
        f"{N_SIMULATIONS:,} simulated paths generated from the portfolio's combined trade "
        f"stream using the '{MC_METHOD}' method, evaluated against {PROP_FIRM_NAME} rules "
        f"on a ${deposit:,.2f} account."
    )

    # 1. Setup
    doc.add_heading("1. Simulation Setup", level=1)
    method_desc = {
        "resample": "Bootstrap - trades drawn with replacement (different but statistically similar sequences)",
        "shuffle": "Permutation - same trades in random order (preserves the backtest's true total P&L)",
        "skip": f"Random skip - {SKIP_FRACTION:.0%} of trades randomly dropped, original order kept",
    }.get(MC_METHOD, MC_METHOD)

    rows = [
        ("Portfolio", portfolio_name),
        ("Account Size", f"${deposit:,.2f}"),
        ("Simulations", f"{N_SIMULATIONS:,}"),
        ("Randomisation Method", method_desc),
        ("Per-Trade P&L Noise", f"±{PNL_NOISE:.0%}" if PNL_NOISE else "None"),
        ("Trades per Simulation", f"{len(trades):,}" if TRADES_PER_SIM is None else f"{TRADES_PER_SIM:,}"),
        ("Source Trade Stream Rows", f"{len(trades):,}"),
        ("Random Seed", str(RANDOM_SEED)),
    ]
    candidates = manifest.get("candidates", [])
    if candidates:
        rows.append(("Candidates in Portfolio",
                     ", ".join(f"{c.get('candidate')} ({c.get('run_dir')})" for c in candidates)))
    _add_kv_table(doc, rows)

    # 2. Prop rules
    doc.add_heading("2. Prop Firm Rule Set Applied", level=1)
    rule_rows = [
        ("Firm / Programme", PROP_FIRM_NAME),
        ("Static Max Drawdown", f"{STATIC_MAX_DD_PCT:.2f}% below initial balance "
                                f"(floor = ${deposit * (1 - STATIC_MAX_DD_PCT / 100):,.2f})"),
        ("Daily Drawdown", f"{DAILY_DD_PCT:.2f}% below each day's starting balance"),
    ]
    for phase in PHASES:
        limit = "No limit" if phase["max_days"] is None else f"{phase['max_days']} days"
        rule_rows.append((f"{phase['name']} Target", f"{phase['target_pct']:.2f}% (time limit: {limit})"))
    _add_kv_table(doc, rule_rows)
    doc.add_paragraph(
        "Each simulated path is walked trade-by-trade in chronological order. The daily floor "
        "is re-based at the start of every trading day using the real day boundaries from the "
        "backtest. A path stops the moment it hits the target (pass) or breaches a floor (fail), "
        "mirroring how the firm would actually close the account."
    )

    # 3. Phase results
    doc.add_heading("3. Prop Firm Phase Outcomes", level=1)
    ptable = doc.add_table(rows=1, cols=7)
    ptable.style = "Table Grid"
    header = ptable.rows[0].cells
    for i, label in enumerate(["Phase", "Target", "Pass Rate", "Static Breach",
                               "Daily Breach", "No Target Hit", "Median Days to Pass"]):
        _set_cell_text(header[i], label, bold=True)

    for phase in PHASES:
        s = phase_summaries[phase["name"]]
        cells = ptable.add_row().cells
        _set_cell_text(cells[0], phase["name"], bold=True)
        _set_cell_text(cells[1], f"{phase['target_pct']:.1f}%")
        _set_cell_text(cells[2], f"{s['pass_rate']:.2f}%", bold=True)
        _shade_cell(cells[2], _rate_shade(s["pass_rate"]))
        _set_cell_text(cells[3], f"{s['breach_static_rate']:.2f}%")
        _set_cell_text(cells[4], f"{s['breach_daily_rate']:.2f}%")
        _set_cell_text(cells[5], f"{s['no_target_rate'] + s['timeout_rate']:.2f}%")
        _set_cell_text(cells[6], "N/A" if not np.isfinite(s["median_days_to_pass"])
                       else f"{s['median_days_to_pass']:,.0f}")

    doc.add_paragraph()
    for phase in PHASES:
        s = phase_summaries[phase["name"]]
        doc.add_paragraph(f"{phase['name']} detail", style="Heading 3")
        _add_kv_table(doc, [
            ("Pass Rate", f"{s['pass_rate']:.2f}%"),
            ("Any Breach Rate", f"{s['breach_any_rate']:.2f}%"),
            ("  - Static Max DD Breach", f"{s['breach_static_rate']:.2f}%"),
            ("  - Daily DD Breach", f"{s['breach_daily_rate']:.2f}%"),
            ("Ran Out of Trades Without Target", f"{s['no_target_rate']:.2f}%"),
            ("Timed Out", f"{s['timeout_rate']:.2f}%"),
            ("Median Days to Pass", "N/A" if not np.isfinite(s["median_days_to_pass"])
             else f"{s['median_days_to_pass']:,.0f}"),
            ("90th Percentile Days to Pass", "N/A" if not np.isfinite(s["p90_days_to_pass"])
             else f"{s['p90_days_to_pass']:,.0f}"),
            ("Median Trades to Pass", "N/A" if not np.isfinite(s["median_trades_to_pass"])
             else f"{s['median_trades_to_pass']:,.0f}"),
        ])

    # 4. Distribution stats
    doc.add_heading("4. Full-Run Distribution (No Phase Stop)", level=1)
    doc.add_paragraph(
        "These figures run every path to its full length without stopping at a target or "
        "breach, to show the raw return and drawdown distribution of the strategy mix itself."
    )
    fr = uncon["final_return_pct"]
    dd = uncon["max_dd_pct"]
    _add_kv_table(doc, [
        ("Median Final Return", f"{np.median(fr):+.2f}%"),
        ("Mean Final Return", f"{np.mean(fr):+.2f}%"),
        ("5th Percentile Return", f"{np.percentile(fr, 5):+.2f}%"),
        ("95th Percentile Return", f"{np.percentile(fr, 95):+.2f}%"),
        ("Probability of Profit", f"{(fr > 0).mean() * 100.0:.2f}%"),
        ("Actual Backtest Return", f"{actual['return_pct']:+.2f}%"),
        ("Median Max Drawdown", f"{np.median(dd):.2f}%"),
        ("95th Percentile Max Drawdown", f"{np.percentile(dd, 95):.2f}%"),
        ("Worst Max Drawdown", f"{dd.max():.2f}%"),
        ("Actual Backtest Max Drawdown", f"{actual['max_dd_pct']:.2f}%"),
        (f"Paths Exceeding {STATIC_MAX_DD_PCT:.0f}% DD",
         f"{(dd > STATIC_MAX_DD_PCT).mean() * 100.0:.2f}%"),
    ])

    # 5. Charts
    doc.add_heading("5. Charts", level=1)
    chart_captions = [
        ("equity_paths", "Simulated Equity Paths vs Actual Backtest"),
        ("final_return", "Distribution of Final Returns"),
        ("max_dd", "Distribution of Maximum Drawdowns"),
        ("days_to_target", "Days to Reach Phase 1 Target (passing paths only)"),
    ]
    for key, caption in chart_captions:
        path = charts.get(key)
        if path and Path(path).exists():
            doc.add_paragraph(caption).runs[0].bold = True
            doc.add_picture(str(path), width=Inches(6.6))

    # 6. Interpretation
    doc.add_heading("6. How to Read This", level=1)
    p1 = phase_summaries[PHASES[0]["name"]]
    notes = [
        f"Phase 1 pass rate of {p1['pass_rate']:.1f}% is the headline number: out of "
        f"{N_SIMULATIONS:,} alternate histories of this portfolio, that is the share that "
        f"reached the {PHASES[0]['target_pct']:.0f}% target without breaching a floor first.",
        f"Breach mix matters as much as the pass rate. This run failed "
        f"{p1['breach_static_rate']:.1f}% of paths on the static {STATIC_MAX_DD_PCT:.0f}% floor "
        f"and {p1['breach_daily_rate']:.1f}% on the {DAILY_DD_PCT:.0f}% daily floor. Daily-floor "
        f"failures usually point to position sizing or trade clustering within a day rather than "
        f"a broken edge.",
        "The 'resample' method draws trades with replacement, so a path can repeat bad trades and "
        "produce sequences worse than anything in the backtest. That is intentional - it is the "
        "point of the exercise, and it is why the pass rate here will always look worse than the "
        "single historical run.",
        "The 'shuffle' method preserves the exact trade set and therefore the true total P&L; "
        "differences between shuffle and resample results isolate how much of the outcome depends "
        "on trade ORDER versus trade SELECTION.",
        "A single backtest is one sample. Treat the distribution here, not the historical curve, "
        "as the realistic expectation for a live funded account.",
    ]
    for n in notes:
        doc.add_paragraph(n)

    try:
        doc.save(doc_path)
        return doc_path
    except PermissionError:
        alt = doc_path.parent / f"{doc_path.stem}_{int(time.time())}.docx"
        doc.save(alt)
        print(f"    [WARNING] Target Word file is locked. Saved: {alt.name}")
        return alt


# ===========================================================================
# RUNNER
# ===========================================================================


def main():
    print("=" * 76)
    print(" PORTFOLIO MONTE CARLO SIMULATION RUNNER")
    print("=" * 76)

    portfolio_dir = resolve_portfolio_dir()
    if portfolio_dir is None:
        return

    portfolio_name = portfolio_dir.name
    print(f"  Portfolio:   {portfolio_name}")
    print(f"  Folder:      {portfolio_dir}")

    trades, deposit, manifest = load_portfolio(portfolio_dir)
    if trades is None or trades.empty:
        return

    print(f"  Account:     ${deposit:,.2f}")
    print(f"  Trade rows:  {len(trades):,}")
    print(f"  Method:      {MC_METHOD}  |  Simulations: {N_SIMULATIONS:,}")

    pnl = trades["NetPnl"].to_numpy(dtype=float)

    # Real day structure, so the daily-drawdown rule is evaluated against actual
    # trading days rather than an artificial one-trade-per-day assumption.
    days = trades["Time"].dt.normalize()
    day_codes = pd.factorize(days)[0]
    day_starts = np.concatenate(([True], day_codes[1:] != day_codes[:-1]))

    n_trades = TRADES_PER_SIM if TRADES_PER_SIM else len(pnl)
    if n_trades != len(pnl):
        # Day mapping must cover exactly n_trades entries.
        reps = int(np.ceil(n_trades / len(day_codes)))
        day_codes = np.tile(day_codes, reps)[:n_trades]
        day_starts = np.concatenate(([True], day_codes[1:] != day_codes[:-1]))

    rng = np.random.default_rng(RANDOM_SEED)

    print("\n  --> Generating randomised P&L matrix...")
    t0 = time.time()
    pnl_matrix = build_pnl_matrix(pnl, N_SIMULATIONS, n_trades, rng)
    print(f"      Matrix {pnl_matrix.shape[0]:,} x {pnl_matrix.shape[1]:,} built in {time.time() - t0:.1f}s")

    print("  --> Running full-length paths (no phase stop)...")
    uncon = run_unconstrained_paths(pnl_matrix, deposit)

    actual_equity = deposit + np.cumsum(pnl)
    actual_peak = np.maximum.accumulate(actual_equity)
    actual = {
        "return_pct": (actual_equity[-1] / deposit - 1.0) * 100.0,
        "max_dd_pct": float(((actual_peak - actual_equity) / actual_peak * 100.0).max()),
    }
    print(f"      Actual backtest: {actual['return_pct']:+.2f}% return, {actual['max_dd_pct']:.2f}% max DD")
    print(f"      MC median:       {np.median(uncon['final_return_pct']):+.2f}% return, "
          f"{np.median(uncon['max_dd_pct']):.2f}% max DD")

    print("  --> Evaluating prop firm phases...")
    phase_summaries, phase_results = {}, {}
    for phase in PHASES:
        t0 = time.time()
        res = run_phase_simulation(pnl_matrix, day_codes, day_starts, deposit, phase)
        summ = summarise_phase(res)
        phase_results[phase["name"]] = res
        phase_summaries[phase["name"]] = summ
        print(f"      {phase['name']} (target {phase['target_pct']:.1f}%): "
              f"pass {summ['pass_rate']:.2f}% | static breach {summ['breach_static_rate']:.2f}% | "
              f"daily breach {summ['breach_daily_rate']:.2f}%  [{time.time() - t0:.1f}s]")

    print("  --> Generating charts...")
    charts = {}
    charts["equity_paths"] = chart_equity_paths(uncon["equity"], deposit, actual_equity, portfolio_dir)
    charts["final_return"] = chart_histogram(
        uncon["final_return_pct"], "Distribution of Final Returns", "Final Return (%)",
        portfolio_dir, "mc_final_return_hist.png", actual_value=actual["return_pct"],
        vlines=[(0.0, "Breakeven", "red")], color="seagreen")
    charts["max_dd"] = chart_histogram(
        uncon["max_dd_pct"], "Distribution of Maximum Drawdowns", "Max Drawdown (%)",
        portfolio_dir, "mc_max_drawdown_hist.png", actual_value=actual["max_dd_pct"],
        vlines=[(STATIC_MAX_DD_PCT, f"Static limit {STATIC_MAX_DD_PCT:.0f}%", "red")],
        color="indianred")

    first_phase = PHASES[0]["name"]
    passed = phase_results[first_phase][phase_results[first_phase]["outcome"] == "passed"]
    if len(passed):
        charts["days_to_target"] = chart_histogram(
            passed["days_taken"].to_numpy(dtype=float),
            f"Days to Reach {first_phase} Target ({PHASES[0]['target_pct']:.0f}%)",
            "Trading Days", portfolio_dir, "mc_days_to_target_hist.png", color="steelblue")

    print("  --> Saving results CSV...")
    export = pd.DataFrame({
        "sim": np.arange(1, N_SIMULATIONS + 1),
        "final_return_pct": uncon["final_return_pct"],
        "max_dd_pct": uncon["max_dd_pct"],
    })
    for phase in PHASES:
        res = phase_results[phase["name"]]
        tag = phase["name"].lower().replace(" ", "")
        export[f"{tag}_outcome"] = res["outcome"].to_numpy()
        export[f"{tag}_days"] = res["days_taken"].to_numpy()
        export[f"{tag}_return_pct"] = res["final_return_pct"].to_numpy()
    export.to_csv(portfolio_dir / "montecarlo_results.csv", index=False)

    print("  --> Compiling Word report...")
    safe_port_name = portfolio_name.replace("/", "_").replace("\\", "_")
    doc_path = create_montecarlo_word_doc(
        doc_path=portfolio_dir / f"{safe_port_name}_MonteCarlo_Report.docx",
        portfolio_name=portfolio_name,
        manifest=manifest,
        deposit=deposit,
        trades=trades,
        phase_summaries=phase_summaries,
        phase_results=phase_results,
        uncon=uncon,
        charts=charts,
        actual=actual,
    )

    print("\n" + "=" * 76)
    print(f" MONTE CARLO COMPLETE: {portfolio_name}")
    for phase in PHASES:
        s = phase_summaries[phase["name"]]
        print(f"   {phase['name']} pass rate: {s['pass_rate']:.2f}%  "
              f"(static breach {s['breach_static_rate']:.2f}%, daily breach {s['breach_daily_rate']:.2f}%)")
    if doc_path:
        print(f" Word Report: {doc_path}")
    print(f" Results CSV: {portfolio_dir / 'montecarlo_results.csv'}")
    print("=" * 76)


if __name__ == "__main__":
    main()