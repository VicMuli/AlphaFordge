"""
run_screener.py - Multi-Pair Strategy Screener Runner

Runs backtests for an EA across multiple currency pairs / market symbols.
Aggregates performance metrics (Net Profit, Profit Factor, Drawdown, Win Rate, Trades)
into a screener leaderboard manifest and terminal summary table.
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path

# Prevent Windows console UnicodeEncodeError
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_SCRIPT_DIR = Path(__file__).parent.resolve()
_CONFIG_PATH = _SCRIPT_DIR / "config.json"

_cfg = {}
if _CONFIG_PATH.exists():
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
    except Exception as e:
        print(f"  [WARN] Failed to load config.json: {e}")

from mt5_runner import run_single_backtest, normalize_mt5_date, resolve_mt5_symbol
from report_analysis import analyze


def run_strategy_screener(
    ea_name: str,
    symbols: list[str],
    period: str = "M15",
    from_date: str = "2013.01.01",
    to_date: str = "2026.07.03",
    deposit: float = 2500.0,
    set_file: str = "",
    expert: str = "",
):
    print("=" * 76)
    print("  🚀 ALPHA FORGE STRATEGY SCREENER")
    print("=" * 76)
    print(f"  EA Name      : {ea_name}")
    print(f"  Pairs to Test: {', '.join(symbols)}")
    print(f"  Timeframe    : {period}")
    print(f"  Date Range   : {from_date} -> {to_date}")
    print(f"  Deposit      : ${deposit:,.2f}")
    print("=" * 76 + "\n")

    terminal_path = _cfg.get("terminal_path", r"C:\Users\HP\AppData\Roaming\MetaTrader\terminal64.exe")
    terminal_data_dir = _cfg.get("terminal_data_dir", r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\CDE1ED2F37049DA2E508A3C44B675D09")
    login = int(_cfg.get("login", 52909674))
    password = _cfg.get("password", "3F!@4rwo7wc02f")
    server = _cfg.get("server", "ICMarketsKE-Demo")
    currency = _cfg.get("currency", "USD")
    leverage = _cfg.get("leverage", "1:100")
    timeout = int(_cfg.get("single_test_timeout", 1800))

    base_dir = _SCRIPT_DIR / "researched_strategies" / ea_name
    screener_dir = base_dir / "screener"
    screener_dir.mkdir(parents=True, exist_ok=True)

    # Resolve expert binary
    if not expert:
        expert = _cfg.get("expert", f"{ea_name}.ex5")
    if not expert.lower().endswith(".ex5"):
        expert += ".ex5"

    # Check for custom screener inputs set file
    if not set_file:
        custom_set = screener_dir / "screener_inputs.set"
        if custom_set.exists():
            set_file = str(custom_set)
            print(f"  ⚙ Strategy Inputs: Using custom parameters ({custom_set.name})")
        else:
            print("  ⚙ Strategy Inputs: Using EA compiled defaults")
    else:
        print(f"  ⚙ Strategy Inputs: {Path(set_file).name}")

    norm_from = normalize_mt5_date(from_date, default="2013.01.01", is_end=False)
    norm_to = normalize_mt5_date(to_date, default="2026.07.03", is_end=True)

    results = []

    for i, raw_sym in enumerate(symbols, 1):
        clean_sym = raw_sym.strip()
        if not clean_sym:
            continue

        resolved_sym = resolve_mt5_symbol(clean_sym, terminal_data_dir=terminal_data_dir)
        print(f"\n[{i}/{len(symbols)}] ▶ Screening Pair: {clean_sym} -> MT5 Symbol: {resolved_sym}...")

        pair_report_name = f"screen_{ea_name}_{clean_sym.replace(' ', '_')}"

        res_item = {
            "symbol": clean_sym,
            "resolved_symbol": resolved_sym,
            "status": "Running",
            "net_profit": 0.0,
            "profit_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "error": None,
        }

        try:
            report_path = run_single_backtest(
                terminal_path=terminal_path,
                terminal_data_dir=terminal_data_dir,
                expert=expert,
                set_file=set_file,
                symbol=resolved_sym,
                period=period,
                from_date=norm_from,
                to_date=norm_to,
                work_dir=str(screener_dir),
                login=login,
                password=password,
                server=server,
                report_name=pair_report_name,
                deposit=int(deposit),
                currency=currency,
                leverage=leverage,
                timeout=timeout,
            )

            # Analyze report
            parsed_analysis = analyze(report_path)
            curated = parsed_analysis.get("curated_summary", {})

            net_p = float(curated.get("Net Profit") or 0.0)
            trades = int(curated.get("Total Trades") or 0)
            pf = float(curated.get("Profit Factor") or 0.0)
            dd_pct = float(curated.get("Max Balance Drawdown (%)") or 0.0)
            wr = float(curated.get("Win Rate %") or 0.0)
            sharpe = float(curated.get("Sharpe Ratio") or 0.0)
            pct = (net_p / deposit) * 100.0 if deposit > 0 else 0.0

            res_item.update({
                "status": "Passed" if (net_p > 0 and trades >= 10) else ("Profitable" if net_p > 0 else ("0 Trades" if trades == 0 else "Unprofitable")),
                "net_profit": net_p,
                "profit_pct": pct,
                "profit_factor": pf,
                "max_dd_pct": dd_pct,
                "total_trades": trades,
                "win_rate": wr,
                "sharpe": sharpe,
                "report_file": report_path.name,
            })
            print(f"  ✔ Result: Net Profit=${net_p:,.2f} ({pct:.1f}%) | PF={pf:.2f} | Trades={trades} | DD={dd_pct:.1f}%")

        except Exception as exc:
            err_msg = str(exc)
            print(f"  ✖ Error screening {clean_sym}: {err_msg}")
            res_item["status"] = "Failed"
            res_item["error"] = err_msg

        results.append(res_item)

        # Update intermediate manifest so UI can read progress in real time
        manifest = {
            "ea_name": ea_name,
            "expert": expert,
            "period": period,
            "date_range": f"{norm_from} -> {norm_to}",
            "deposit": deposit,
            "pairs_total": len(symbols),
            "pairs_completed": len(results),
            "results": results,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }
        with open(screener_dir / "screener_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    # Final Leaderboard Output
    print("\n" + "=" * 80)
    print(f"  🏁 STRATEGY SCREENER LEADERBOARD -- {ea_name}")
    print("=" * 80)
    print(f"  {'Symbol':<12} | {'Status':<12} | {'Net Profit':>12} | {'Return':>8} | {'PF':>6} | {'Trades':>6} | {'Max DD':>8}")
    print("-" * 80)

    # Sort by Net Profit descending
    sorted_results = sorted(results, key=lambda x: x["net_profit"], reverse=True)
    for r in sorted_results:
        print(f"  {r['symbol']:<12} | {r['status']:<12} | ${r['net_profit']:>11,.2f} | {r['profit_pct']:>7.1f}% | {r['profit_factor']:>6.2f} | {r['total_trades']:>6} | {r['max_dd_pct']:>7.1f}%")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Pair Strategy Screener")
    parser.add_argument("--ea", type=str, default=os.environ.get("AF_ACTIVE_EA", _cfg.get("active_ea", "TRB")))
    parser.add_argument("--symbols", type=str, default=os.environ.get("AF_SYMBOLS", "USDJPY,EURUSD,EURJPY,GBPUSD,XAUUSD"))
    parser.add_argument("--period", type=str, default=os.environ.get("AF_PERIOD", _cfg.get("period", "M15")))
    parser.add_argument("--from-date", type=str, default=os.environ.get("AF_BT_START", _cfg.get("train_from", "2013.01.01")))
    parser.add_argument("--to-date", type=str, default=os.environ.get("AF_BT_END", _cfg.get("holdout_to", "2026.07.03")))
    parser.add_argument("--deposit", type=float, default=float(os.environ.get("AF_DEPOSIT", _cfg.get("deposit", "2500"))))
    parser.add_argument("--set-file", type=str, default=os.environ.get("AF_SET_FILE", ""))
    parser.add_argument("--expert", type=str, default=os.environ.get("AF_EXPERT", ""))

    args = parser.parse_args()
    sym_list = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not sym_list:
        sym_list = ["USDJPY", "EURUSD", "EURJPY", "GBPUSD", "XAUUSD"]

    run_strategy_screener(
        ea_name=args.ea,
        symbols=sym_list,
        period=args.period,
        from_date=args.from_date,
        to_date=args.to_date,
        deposit=args.deposit,
        set_file=args.set_file,
        expert=args.expert,
    )
