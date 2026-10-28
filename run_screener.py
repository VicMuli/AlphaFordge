"""
run_screener.py - Multi-Pair Strategy Screener Runner
AlphaForge MT5 Quant Engine

Runs backtests for a selected EA across multiple currency pairs / market symbols.
Guarantees:
  1. The selected strategy binary (.ex5) is strictly used (no fallback to other EAs in config.json).
  2. Custom parameter and indicator inputs (.set) are synced in UTF-16LE and loaded into MT5.
  3. Every screened pair archives complete artifacts into:
     markets_screened/<SYMBOL>/<STRATEGY>/
     - report.html
     - trades.csv
     - chart_equity_growth.png
     - chart_profit_dollars.png
     - chart_percent_gain.png
     - monthly_heatmap.png
     - <STRATEGY>_<SYMBOL>_Research_Report.docx
     - summary.json
     - screener_inputs.set
"""

import os
import sys
import time
import json
import re
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

from mt5_runner import run_single_backtest, normalize_mt5_date, resolve_mt5_symbol, sync_ea_to_mt5
from report_analysis import analyze
from screener_reporting import generate_screener_market_report


def resolve_strategy_binary(ea_name: str, cfg: dict = None) -> tuple[str, Path, str]:
    """
    Given an EA name (e.g. 'TRB', 'TRB V2.0', 'LRB V1.0', 'HA V1.0'),
    locate its exact folder in researched_strategies/ or strategies/,
    and find its corresponding .ex5 binary.
    
    Returns: (actual_ea_name, strategy_dir, expert_filename)
    """
    clean_ea = re.sub(r'\.(ex5|mq5)$', '', ea_name, flags=re.IGNORECASE).strip().lower()
    search_dirs = [
        _SCRIPT_DIR / "researched_strategies",
        _SCRIPT_DIR / "strategies",
        _SCRIPT_DIR,
    ]
    if cfg and cfg.get("research_dir"):
        search_dirs.insert(0, Path(cfg["research_dir"]))

    matched_folder = None
    found_ex5 = None
    actual_ea_name = ea_name

    for sdir in search_dirs:
        if not sdir.exists():
            continue

        # Check direct .ex5 files
        for f in sdir.glob("*.ex5"):
            f_low = f.stem.lower()
            if f_low == clean_ea or f_low.startswith(clean_ea) or clean_ea.startswith(f_low):
                found_ex5 = f.name
                actual_ea_name = f.stem
                matched_folder = sdir
                break
        if found_ex5:
            break

        # Check subfolders
        for sub in sdir.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                sub_low = sub.name.lower()
                if sub_low == clean_ea or sub_low.startswith(clean_ea) or clean_ea.startswith(sub_low) or clean_ea in sub_low:
                    matched_folder = sub
                    actual_ea_name = sub.name
                    ex5s = list(sub.glob("*.ex5"))
                    if ex5s:
                        found_ex5 = ex5s[0].name
                        break
                    mq5s = list(sub.glob("*.mq5"))
                    if mq5s:
                        found_ex5 = mq5s[0].stem + ".ex5"
                        break
        if found_ex5:
            break

    if not found_ex5:
        found_ex5 = f"{ea_name}.ex5"
        if not matched_folder:
            matched_folder = _SCRIPT_DIR / "researched_strategies" / ea_name

    return actual_ea_name, matched_folder, found_ex5


def resolve_screener_set_file(
    ea_name: str,
    strategy_dir: Path,
    set_file_arg: str = "",
    terminal_data_dir: str = "",
) -> tuple[str, str]:
    """
    Resolves the .set file to use for screener runs.
    Ensures UTF-16LE formatting and synchronization to MT5 Profiles/Tester.
    Returns: (full_set_path, set_filename)
    """
    candidate_paths = []
    if set_file_arg and set_file_arg.strip():
        candidate_paths.append(Path(set_file_arg.strip()))

    env_set = os.environ.get("AF_SET_FILE", "").strip()
    if env_set:
        candidate_paths.append(Path(env_set))

    if strategy_dir and strategy_dir.exists():
        candidate_paths.append(strategy_dir / "screener" / "screener_inputs.set")
        candidate_paths.append(strategy_dir / "screener_inputs.set")
        candidate_paths.append(strategy_dir / f"{strategy_dir.name}.set")

    # Check researched_strategies/<ea>/screener/
    candidate_paths.append(_SCRIPT_DIR / "researched_strategies" / ea_name / "screener" / "screener_inputs.set")

    # Check if a screener_inputs.json exists but .set does not
    for p in list(candidate_paths):
        json_p = p.with_suffix(".json")
        if json_p.exists() and not p.exists():
            try:
                with open(json_p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                set_lines = [
                    f"; AlphaForge Auto-Generated Screener Set File",
                    f"; EA: {ea_name}",
                    f"; Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
                    "",
                    "; --- Indicator Filters ---",
                ]
                for ind in data.get("indicators", []):
                    if ind.get("toggleParam"):
                        set_lines.append(f"{ind['toggleParam']}={1 if ind.get('enabled') else 0}")
                set_lines.append("")
                set_lines.append("; --- Parameters ---")
                for k, v in data.get("params", {}).items():
                    out_v = 1 if v is True else (0 if v is False else v)
                    set_lines.append(f"{k}={out_v}")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("\n".join(set_lines) + "\n", encoding="utf-16")
            except Exception as e:
                print(f"  [WARN] Failed to compile JSON to set file: {e}")

    # Find first existing set file
    for p in candidate_paths:
        if p.exists() and p.is_file():
            set_filename = p.name
            # Synchronize to MT5 Profiles/Tester in UTF-16LE
            if terminal_data_dir:
                try:
                    prof_dir = Path(terminal_data_dir) / "MQL5" / "Profiles" / "Tester"
                    prof_dir.mkdir(parents=True, exist_ok=True)
                    raw_bytes = p.read_bytes()
                    if not (raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff')):
                        try:
                            txt = raw_bytes.decode('utf-8')
                        except Exception:
                            txt = raw_bytes.decode('latin-1', errors='replace')
                        raw_bytes = ('\ufeff' + txt).encode('utf-16le')
                    (prof_dir / set_filename).write_bytes(raw_bytes)
                except Exception as e:
                    print(f"  [WARN] Failed to sync set file to Profiles/Tester: {e}")

            return str(p), set_filename

    return "", ""


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
    print("=" * 80)
    print("  🚀 ALPHA FORGE MULTI-PAIR STRATEGY SCREENER")
    print("=" * 80)

    terminal_path = _cfg.get("terminal_path", r"C:\Users\HP\AppData\Roaming\MetaTrader\terminal64.exe")
    terminal_data_dir = _cfg.get("terminal_data_dir", r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\CDE1ED2F37049DA2E508A3C44B675D09")
    login = int(_cfg.get("login", 52909674))
    password = _cfg.get("password", "3F!@4rwo7wc02f")
    server = _cfg.get("server", "ICMarketsKE-Demo")
    currency = _cfg.get("currency", "USD")
    leverage = _cfg.get("leverage", "1:100")
    timeout = int(_cfg.get("single_test_timeout", 1800))

    # 1. Strictly resolve EA and binary (prevents fallback to other strategies)
    actual_ea_name, strategy_dir, expert_filename = resolve_strategy_binary(ea_name, _cfg)
    if expert and expert.strip():
        expert_filename = expert.strip()
        if not expert_filename.lower().endswith(".ex5"):
            expert_filename += ".ex5"

    screener_dir = strategy_dir / "screener"
    screener_dir.mkdir(parents=True, exist_ok=True)

    # 2. Strictly resolve parameter & indicator inputs .set file
    resolved_set_path, set_filename = resolve_screener_set_file(
        ea_name=actual_ea_name,
        strategy_dir=strategy_dir,
        set_file_arg=set_file,
        terminal_data_dir=terminal_data_dir,
    )

    norm_from = normalize_mt5_date(from_date, default="2013.01.01", is_end=False)
    norm_to = normalize_mt5_date(to_date, default="2026.07.03", is_end=True)

    print(f"  EA Strategy  : {actual_ea_name} (Requested: {ea_name})")
    print(f"  EA Binary    : {expert_filename}")
    print(f"  Inputs / Set : {set_filename if set_filename else 'Compiled MQL5 Defaults'}")
    if resolved_set_path:
        print(f"  Set File Path: {resolved_set_path}")
    print(f"  Pairs to Test: {', '.join(symbols)}")
    print(f"  Timeframe    : {period}")
    print(f"  Date Range   : {norm_from} -> {norm_to}")
    print(f"  Deposit      : ${deposit:,.2f}")
    print("=" * 80 + "\n")

    # Output root: markets_screened/
    markets_screened_base = _SCRIPT_DIR / "markets_screened"
    markets_screened_base.mkdir(parents=True, exist_ok=True)

    results = []

    for i, raw_sym in enumerate(symbols, 1):
        clean_sym = raw_sym.strip().upper()
        if not clean_sym:
            continue

        resolved_sym = resolve_mt5_symbol(clean_sym, terminal_data_dir=terminal_data_dir)
        print(f"\n[{i}/{len(symbols)}] ▶ Screening Pair: {clean_sym} -> MT5 Symbol: {resolved_sym}...")

        pair_report_name = f"screen_{actual_ea_name}_{clean_sym.replace(' ', '_')}"

        # Per-market per-strategy directory: markets_screened/<SYMBOL>/<STRATEGY>/
        pair_out_dir = markets_screened_base / clean_sym / actual_ea_name
        pair_out_dir.mkdir(parents=True, exist_ok=True)

        res_item = {
            "symbol": clean_sym,
            "resolved_symbol": resolved_sym,
            "ea_name": actual_ea_name,
            "status": "Running",
            "net_profit": 0.0,
            "profit_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "markets_screened_dir": str(pair_out_dir.relative_to(_SCRIPT_DIR)),
            "files": {},
            "error": None,
        }

        try:
            report_path = run_single_backtest(
                terminal_path=terminal_path,
                terminal_data_dir=terminal_data_dir,
                expert=expert_filename,
                set_file=resolved_set_path,
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

            # Generate full backtest artifacts in markets_screened/<PAIR>/<EA>/
            rep_data = generate_screener_market_report(
                report_path=report_path,
                output_dir=pair_out_dir,
                ea_name=actual_ea_name,
                symbol=clean_sym,
                deposit=deposit,
                set_file=resolved_set_path,
                period=period,
                from_date=norm_from,
                to_date=norm_to,
                resolved_symbol=resolved_sym,
            )

            res_item.update({
                "status": rep_data.get("status", "Completed"),
                "net_profit": rep_data.get("net_profit", 0.0),
                "profit_pct": rep_data.get("profit_pct", 0.0),
                "profit_factor": rep_data.get("profit_factor", 0.0),
                "max_dd_pct": rep_data.get("max_dd_pct", 0.0),
                "total_trades": rep_data.get("total_trades", 0),
                "win_rate": rep_data.get("win_rate", 0.0),
                "sharpe": rep_data.get("sharpe", 0.0),
                "recovery_factor": rep_data.get("recovery_factor", 0.0),
                "files": rep_data.get("files", {}),
            })

            print(f"  ✔ Result: Net Profit=${res_item['net_profit']:,.2f} ({res_item['profit_pct']:.1f}%) | "
                  f"PF={res_item['profit_factor']:.2f} | Trades={res_item['total_trades']} | DD={res_item['max_dd_pct']:.1f}%")
            print(f"  📁 Artifacts saved in: markets_screened/{clean_sym}/{actual_ea_name}/")
            for ftype, fname in res_item.get("files", {}).items():
                print(f"     • {ftype:<20}: {fname}")

        except Exception as exc:
            err_msg = str(exc)
            print(f"  ✖ Error screening {clean_sym}: {err_msg}")
            res_item["status"] = "Failed"
            res_item["error"] = err_msg

        results.append(res_item)

        # Update manifest in both strategy directory and markets_screened/
        manifest = {
            "ea_name": actual_ea_name,
            "expert": expert_filename,
            "set_file": set_filename if set_filename else "defaults",
            "period": period,
            "date_range": f"{norm_from} -> {norm_to}",
            "deposit": deposit,
            "pairs_total": len(symbols),
            "pairs_completed": len(results),
            "results": results,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }

        try:
            with open(screener_dir / "screener_manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            with open(markets_screened_base / "screener_manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass

    # Final Leaderboard Output
    print("\n" + "=" * 84)
    print(f"  🏁 STRATEGY SCREENER LEADERBOARD -- {actual_ea_name}")
    print(f"  Input Mode: {set_filename if set_filename else 'Compiled Defaults'}")
    print("=" * 84)
    print(f"  {'Symbol':<12} | {'Status':<12} | {'Net Profit':>12} | {'Return':>8} | {'PF':>6} | {'Trades':>6} | {'Max DD':>8}")
    print("-" * 84)

    sorted_results = sorted(results, key=lambda x: x.get("net_profit", 0.0), reverse=True)
    for r in sorted_results:
        print(f"  {r['symbol']:<12} | {r['status']:<12} | ${r['net_profit']:>11,.2f} | {r['profit_pct']:>7.1f}% | {r['profit_factor']:>6.2f} | {r['total_trades']:>6} | {r['max_dd_pct']:>7.1f}%")
    print("=" * 84 + "\n")


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
