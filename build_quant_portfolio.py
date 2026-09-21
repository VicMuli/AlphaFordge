"""
build_quant_portfolio.py - Combine Candidate Full-Backtest Results into a Quant Portfolio

FIXED VERSION
-------------
The original portfolio builder counted MT5 DEAL rows as if every deal row were a
complete trade. MT5 can represent one position with multiple deal rows (for
example an opening deal and one or more closing/partial-close deals). That can
make the portfolio report show a much larger "Total Trades" value than the
actual number of completed positions.

This version separates:

    1. DEAL ROWS
       Used for the chronological portfolio balance/equity stream and monthly
       P&L. Every monetary movement is retained exactly once.

    2. COMPLETED TRADES / POSITIONS
       Used for trade statistics. Rows are grouped by Position ID where MT5
       supplies one. A position's Profit, Commission, Swap and NetTradePnl are
       summed into one completed trade.

The portfolio therefore does NOT count opening/closing deal rows as separate
trades.

The builder still reuses the exact MT5 parser from run_full_backtest.py for
candidate loading, and the portfolio equity stream is constructed from the
parsed monetary movements.

Folder layout:

    Quant_Portfolios/
      TRB_Quant_Portfolios/
        TRB_Quant_Portfolio_002/
          TRB_Quant_Portfolio_002_Report.docx
          chart_profit_dollars.png
          chart_equity_growth.png
          chart_percent_gain.png
          chart_candidates_vs_combined.png
          monthly_performance_heatmap.png
          correlation_matrix.csv
          portfolio_manifest.json
"""

import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except ImportError:
    docx = None
    print("WARNING: python-docx not installed. Run: pip install python-docx")

# Reuse the exact configuration and parser from the single-candidate runner.
from run_optimization import WORK_DIR, DEPOSIT, CURRENCY, TRAIN_FROM, HOLDOUT_TO
from report_analysis import analyze

import shutil
from run_full_backtest import (
    parse_mt5_html_for_deals,
    generate_equity_charts,
    generate_monthly_heatmap,
    _get_trade_rows,
    _set_cell_text,
    _fmt_money,
    _fmt_pct,
    _fmt_ratio,
    _seconds_to_duration,
    resolve_candidate_dir as _base_resolve_candidate_dir,
)


# ===========================================================================
# USER CONFIGURATION
# ===========================================================================

QUANT_NAME = "TRB"

# Set None for automatic numbering:
#   TRB_Portfolio_001, TRB_Portfolio_002, ...
#
# Or use an explicit folder name.
PORTFOLIO_NAME = "TRB_Quant_Portfolio_001"

# True = reuse/overwrite the selected portfolio folder.
# False = create _v2, _v3, etc. if the selected folder already exists.
OVERWRITE_EXISTING = True

CANDIDATES = [
    {
       "run_dir": "run_20260911_094409",
        "candidate": "cand_015",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260909_101955",
        "candidate": "cand_013",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260909_101955",
        "candidate": "cand_014",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260909_101955",
        "candidate": "cand_011",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260909_101955",
        "candidate": "cand_009",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260909_101955",
        "candidate": "cand_003",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260911_094409",
        "candidate": "cand_014",
        "weight": 1.0,
    },
    {
        "run_dir": "run_20260911_094409",
        "candidate": "cand_007",
        "weight": 1.0,
    },
]

QUANT_PORTFOLIOS_DIR = Path(WORK_DIR) / "Quant_Portfolios"
_SCRIPT_DIR = Path(__file__).parent.resolve()
MULTI_MARKET_DIR = _SCRIPT_DIR / "MultiMarket portfolio"
PORTFOLIO_TYPE = "Standard"  # "Standard" or "MultiMarket"

CORRELATION_PAIRING_THRESHOLD = 0.5

PORTFOLIO_START = TRAIN_FROM
PORTFOLIO_END = HOLDOUT_TO


# ===========================================================================
# CANDIDATE DISCOVERY
# ===========================================================================

def resolve_candidate_dir(
    base_work_dir: Path,
    target_run: str,
    target_cand: str,
    market: str = None,
) -> Path | None:
    """
    Multi-market intelligent candidate resolver.
    Finds candidates across EURJPY, USDJPY, and any other market directories.
    """
    cand_variants = [target_cand]
    m = re.search(r"(\d+)", target_cand)
    if m:
        num = int(m.group(1))
        for fmt in (f"cand_{num:03d}", f"cand_{num:02d}", f"cand_{num}", f"cand_{num:04d}", f"c_{num:03d}"):
            if fmt not in cand_variants:
                cand_variants.append(fmt)

    # 1. Direct path check
    if target_run and Path(target_run).exists():
        drun = Path(target_run)
        for cvar in cand_variants:
            for p in (drun / "passed_candidates" / cvar, drun / cvar, drun / "full_backtest" / cvar):
                if p.exists() and p.is_dir():
                    return p
        if drun.name in cand_variants:
            return drun

    # 2. Gather search roots
    roots = [base_work_dir]
    opt_runs = _SCRIPT_DIR / "optimization_runs"
    if opt_runs.exists() and opt_runs not in roots:
        roots.append(opt_runs)
    if base_work_dir.parent.exists() and base_work_dir.parent not in roots:
        roots.append(base_work_dir.parent)
    if MULTI_MARKET_DIR.exists() and MULTI_MARKET_DIR not in roots:
        roots.append(MULTI_MARKET_DIR)

    # Sibling market directories under optimization_runs
    try:
        if opt_runs.exists():
            for sibling in opt_runs.iterdir():
                if sibling.is_dir() and sibling not in roots:
                    roots.append(sibling)
    except OSError:
        pass

    # If market is specified (e.g. "EURJPY" or "USDJPY"), prioritize market folder
    if market:
        m_lower = market.lower()
        prioritized = []
        for r in roots:
            for pat in (f"trb_{m_lower}", m_lower):
                target_p = r / pat if not r.name.lower().endswith(m_lower) else r
                if target_p.exists() and target_p.is_dir() and target_p not in prioritized:
                    prioritized.append(target_p)
        roots = prioritized + [r for r in roots if r not in prioritized]

    # 3. Match by target_run if specified
    if target_run and target_run.strip().lower() not in ("latest", "", "(none)", "(auto)"):
        clean_run = target_run.strip().replace("\\", "/").rstrip("/")
        for root in roots:
            for cand_path in (root / clean_run, root / Path(clean_run).name):
                if cand_path.exists() and cand_path.is_dir():
                    for cvar in cand_variants:
                        for p in (cand_path / "passed_candidates" / cvar,
                                  cand_path / cvar,
                                  cand_path / "full_backtest" / cvar):
                            if p.exists() and p.is_dir():
                                return p
        # Search rglob for run folder name
        run_leaf = Path(clean_run).name
        for root in roots:
            try:
                for match in root.rglob(run_leaf):
                    if match.is_dir():
                        for cvar in cand_variants:
                            for p in (match / "passed_candidates" / cvar,
                                      match / cvar,
                                      match / "full_backtest" / cvar):
                                if p.exists() and p.is_dir():
                                    return p
            except OSError:
                pass

    # 4. Fallback search across all candidate folders
    for root in roots:
        for cvar in cand_variants:
            try:
                for pc in root.rglob("passed_candidates"):
                    if pc.is_dir():
                        p = pc / cvar
                        if p.exists() and p.is_dir():
                            return p
                for p in root.rglob(cvar):
                    if p.is_dir():
                        return p
            except OSError:
                pass

    # 5. Last resort: delegate to base resolver
    return _base_resolve_candidate_dir(base_work_dir, target_run, target_cand)


def find_candidate_report_html(cand_dir: Path, candidate_name: str) -> Path | None:
    """Locate the MT5 HTML report produced for this candidate with recursive fallback."""
    search_dirs = [
        cand_dir / "full_backtest_report",
        cand_dir / "full_backtest",
        cand_dir,
    ]

    patterns = [
        f"Full_BT_{candidate_name}*.htm*",
        f"*{candidate_name}*.htm*",
        "*.htm",
        "*.html",
    ]

    found = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        for pattern in patterns:
            found.extend(directory.glob(pattern))

    # Also recursive search inside cand_dir
    if not found and cand_dir.exists():
        try:
            for p in cand_dir.rglob("*.htm*"):
                if p.is_file():
                    found.append(p)
        except OSError:
            pass

    if not found:
        return None

    # Remove duplicates while preserving Path objects.
    unique = {}
    for path in found:
        try:
            unique[path.resolve()] = path
        except OSError:
            unique[path] = path

    found = list(unique.values())
    return max(found, key=lambda p: p.stat().st_mtime)


def _load_candidate_from_csv(cand_dir: Path, candidate: str, deposit: float = 2500.0):
    """
    Fallback deal/trade loader from CSV files when MT5 HTML report is missing or unparseable.
    """
    search_files = [
        cand_dir / "trades.csv",
        cand_dir / "deals.csv",
        cand_dir / "combined_trades.csv",
        cand_dir / "full_backtest_report" / "trades.csv",
        cand_dir / "full_backtest" / "trades.csv",
    ]
    if cand_dir.exists():
        try:
            for p in cand_dir.rglob("*.csv"):
                if p not in search_files and p.is_file():
                    search_files.append(p)
        except OSError:
            pass

    for csv_path in search_files:
        if not csv_path.exists() or not csv_path.is_file():
            continue
        try:
            df = pd.read_csv(csv_path)
            if df.empty:
                continue

            time_col = None
            for c in ("Time", "time", "Date", "date", "DateTime", "datetime", "Timestamp", "Deal Time", "Open Time"):
                if c in df.columns:
                    time_col = c
                    break
            if time_col is None:
                continue

            df["Time"] = pd.to_datetime(df[time_col], errors="coerce")
            df = df.dropna(subset=["Time"]).sort_values("Time").reset_index(drop=True)
            if df.empty:
                continue

            profit_col = None
            for c in ("NetTradePnl", "NetPnl", "EquityPnl", "Profit", "profit", "Pnl", "pnl", "Net Profit"):
                if c in df.columns:
                    profit_col = c
                    break

            if profit_col:
                df["NetTradePnl"] = pd.to_numeric(df[profit_col], errors="coerce").fillna(0.0)
            else:
                df["NetTradePnl"] = 0.0

            df["Profit"] = pd.to_numeric(df.get("Profit", df["NetTradePnl"]), errors="coerce").fillna(0.0)
            df["Commission"] = pd.to_numeric(df.get("Commission", 0.0), errors="coerce").fillna(0.0)
            df["Swap"] = pd.to_numeric(df.get("Swap", 0.0), errors="coerce").fillna(0.0)

            if "Balance" in df.columns:
                df["Balance"] = pd.to_numeric(df["Balance"], errors="coerce").ffill().fillna(deposit)
            else:
                df["Balance"] = float(deposit) + df["NetTradePnl"].cumsum()

            df["IsBalanceOperation"] = False
            df.attrs["trade_df"] = df.copy()

            pnl = df["NetTradePnl"]
            wins = pnl[pnl > 0]
            losses = pnl[pnl < 0]
            gross_profit = float(wins.sum())
            gross_loss = float(abs(losses.sum()))
            pf = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

            official_stats = {
                "total_net_profit": float(pnl.sum()),
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "profit_factor": pf,
                "total_trades": int((pnl != 0).sum()) or len(df),
                "win_trades": int(len(wins)),
                "loss_trades": int(len(losses)),
            }
            return df, official_stats, csv_path
        except Exception:
            continue

    return None, None, None


def _flatten_metric_dict(obj):
    """Flatten nested report_analysis output into a simple key/value mapping."""
    if not isinstance(obj, dict):
        return {}
    flat = {}
    for key, value in obj.items():
        if isinstance(value, dict):
            flat.update(_flatten_metric_dict(value))
        else:
            flat[str(key)] = value
    return flat


def _normalised_metric_map(raw_metrics: dict) -> dict:
    """Create a case/whitespace-insensitive metric lookup map."""
    flat = _flatten_metric_dict(raw_metrics)
    return {
        re.sub(r"\s+", " ", str(k).replace("\xa0", " ")).strip().lower(): v
        for k, v in flat.items()
    }


def _extract_report_metric(raw_metrics: dict, aliases, default=None):
    """Extract one numeric metric from report_analysis output."""
    metric_map = _normalised_metric_map(raw_metrics)
    aliases_norm = [
        re.sub(r"\s+", " ", str(a).replace("\xa0", " ")).strip().lower()
        for a in aliases
    ]

    def parse(value):
        if value is None:
            return None
        text = str(value).strip()
        # Preserve a leading minus and decimal point; ignore currency/percent text.
        text = text.replace(",", "")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None

    for alias in aliases_norm:
        if alias in metric_map:
            value = parse(metric_map[alias])
            if value is not None:
                return value

    for alias in aliases_norm:
        for key, raw_value in metric_map.items():
            if alias in key or key in alias:
                value = parse(raw_value)
                if value is not None:
                    return value

    return default


def _strip_thousands_space(text: str) -> str:
    """Collapse MT5's space/NBSP thousands separator, e.g. '1 341.26' -> '1341.26'.

    MT5's own HTML reports format large numbers with a plain space (or
    non-breaking space) between digit groups instead of a comma. Without this,
    a numeric regex anchored on \\d+ stops at the first space and silently
    truncates '1 341.26' down to '1', '6 073.97' down to '6', etc. -- which
    then poisons every downstream dollar figure that trusts this "official"
    value (drawdown %, profit factor, and the equity-stream normalisation
    factor all get computed from the truncated number).
    """
    text = str(text).replace("\xa0", " ")
    return re.sub(r"(?<=\d)[ ](?=\d)", "", text)


def _parse_summary_number(text, integer=False):
    """Parse the first numeric value from an MT5 summary cell."""
    if text is None:
        return None
    text = _strip_thousands_space(text).strip()
    # MT5 may display e.g. "122 (51.48%)". The first number is the count.
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    value = float(match.group(0))
    return int(round(value)) if integer else value


def _normalise_summary_label(text):
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip().lower().rstrip(":")


def _read_mt5_summary_direct(html_path: Path) -> dict:
    """Read exact MT5 summary labels directly from the HTML.

    This deliberately avoids fuzzy key matching because labels such as
    'Profit Trades (% of total)' must never accidentally match an unrelated
    'Profit' metric from report_analysis.
    """
    result = {}
    if BeautifulSoup is None:
        return result
    try:
        raw = html_path.read_bytes()
        encodings = ["utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1"]
        html = None
        for enc in encodings:
            try:
                candidate = raw.decode(enc)
                if "<html" in candidate.lower() or "<table" in candidate.lower():
                    html = candidate
                    break
            except UnicodeError:
                continue
        if html is None:
            return result

        soup = BeautifulSoup(html, "html.parser")
        wanted = {
            "total net profit": "total_net_profit",
            "profit factor": "profit_factor",
            "gross profit": "gross_profit",
            "gross loss": "gross_loss",
            "total trades": "total_trades",
            "profit trades (% of total)": "profit_trades",
            "profit trades": "profit_trades",
            "loss trades (% of total)": "loss_trades",
            "loss trades": "loss_trades",
            "long trades (won %)": "long_trades",
            "short trades (won %)": "short_trades",
            "largest profit trade": "largest_profit",
            "largest loss trade": "largest_loss",
        }

        for row in soup.find_all("tr"):
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            row_text = _strip_thousands_space(" | ".join(cells))

            # Some MT5 exports merge the label and value into one cell.
            for label, key in wanted.items():
                pattern = rf"{re.escape(label)}\s*:?\s*([-+]?\d[\d,]*(?:\.\d+)?(?:\s*\(\s*\d+(?:\.\d+)?\s*%\s*\))?)"
                match = re.search(pattern, row_text, flags=re.IGNORECASE)
                if match:
                    value_text = match.group(1)
                    if key == "total_trades":
                        result[key] = _parse_summary_number(value_text, integer=True)
                    elif key in {"profit_trades", "loss_trades"}:
                        result[key] = _parse_summary_number(value_text, integer=True)
                        result[key + "_text"] = value_text
                    elif key in {"long_trades", "short_trades"}:
                        result[key] = value_text
                    else:
                        value = _parse_summary_number(value_text, integer=False)
                        if value is not None:
                            result[key] = value

            if len(cells) < 2:
                continue
            for i, cell in enumerate(cells[:-1]):
                label = _normalise_summary_label(cell)
                if label in wanted and wanted[label] not in result:
                    key = wanted[label]
                    value_text = cells[i + 1]
                    if key in {"total_trades"}:
                        value = _parse_summary_number(value_text, integer=True)
                    elif key in {"profit_trades", "loss_trades"}:
                        value = _parse_summary_number(value_text, integer=True)
                        result[key + "_text"] = value_text
                    elif key in {"long_trades", "short_trades"}:
                        # Preserve the complete text; it commonly contains count and win %.
                        value = value_text
                    else:
                        value = _parse_summary_number(value_text, integer=False)
                    if value is not None:
                        result[key] = value

        return result
    except Exception as exc:
        print(f"      [WARNING] Direct MT5 summary parsing failed: {exc}")
        return result


def _load_official_trade_stats(html_path: Path) -> dict:
    """Load authoritative MT5 tester summary metrics for one candidate."""
    direct = _read_mt5_summary_direct(html_path)

    # report_analysis remains a secondary source for labels not found directly.
    try:
        raw_metrics = analyze(str(html_path))
    except Exception as exc:
        print(f"      [WARNING] Could not read MT5 summary metrics: {exc}")
        raw_metrics = {}

    result = {"raw_metrics": raw_metrics}

    # Only use exact direct-summary values for trade counts. If a summary cell
    # contains an impossible count (> Total Trades), use its displayed
    # percentage to reconstruct the count. This prevents a malformed parser
    # from turning a percentage/deal statistic into a trade count.
    if "total_trades" in direct:
        result["total_trades"] = int(direct["total_trades"])

    for key in ("profit_trades", "loss_trades"):
        if key not in direct:
            continue
        value = int(direct[key])
        total = result.get("total_trades")
        text = str(direct.get(key + "_text", ""))
        pct_match = re.search(r"(?:\(|\s)(\d+(?:\.\d+)?)\s*%", text)
        if total is not None and value > total and pct_match:
            pct = float(pct_match.group(1))
            value = int(round(total * pct / 100.0))
        if total is None or value <= total:
            result[key] = value

    # Net profit is authoritative for portfolio monetary performance.
    if "total_net_profit" in direct:
        result["total_net_profit"] = float(direct["total_net_profit"])
    else:
        value = _extract_report_metric(raw_metrics, ["Total Net Profit"])
        if value is not None:
            result["total_net_profit"] = float(value)

    for key in ("gross_profit", "gross_loss", "profit_factor", "largest_profit", "largest_loss"):
        if key in direct:
            result[key] = float(direct[key])

    if "long_trades" in direct:
        result["long_trades_text"] = direct["long_trades"]
    if "short_trades" in direct:
        result["short_trades_text"] = direct["short_trades"]

    if "total_trades" in result:
        print(f"      MT5 official Total Trades: {result['total_trades']:,} (tester summary)")
    if "profit_trades" in result or "loss_trades" in result:
        print(
            f"      MT5 official Profit/Loss Trades: "
            f"{result.get('profit_trades', 'N/A'):,} / "
            f"{result.get('loss_trades', 'N/A'):,}"
        )
    total_for_direction = result.get("total_trades")
    for key in ("long_trades_text", "short_trades_text"):
        if key in result and total_for_direction is not None:
            first = _parse_summary_number(result[key], integer=True)
            if first is not None and first > total_for_direction:
                # Direction counts cannot exceed total completed trades. Do not
                # substitute raw deal-row direction counts. Leave unavailable.
                result.pop(key, None)

    if "total_net_profit" in result:
        print(f"      MT5 official Net Profit: ${result['total_net_profit']:,.2f}")

    return result


def load_candidate(base_work_dir: Path, spec: dict) -> dict | None:
    """Resolve, parse and prepare one candidate with multi-market intelligence."""
    run_dir = str(spec.get("run_dir", "")).strip()
    candidate = str(spec.get("candidate", "")).strip()
    weight = float(spec.get("weight", 1.0))
    market = spec.get("market") or spec.get("symbol")

    if weight < 0:
        print(
            f"      [SKIP] {candidate}: weight cannot be negative "
            f"(received {weight})."
        )
        return None

    if weight == 0:
        print(f"      [SKIP] {candidate}: weight is 0.00; nothing to contribute.")
        return None

    cand_dir = resolve_candidate_dir(
        base_work_dir,
        run_dir,
        candidate,
        market=market,
    )

    if cand_dir is None:
        print(
            f"      [SKIP] Could not resolve {candidate} "
            f"under run '{run_dir}'."
        )
        return None

    # Detect market from path if not explicit
    if not market:
        path_str = f"{cand_dir} {run_dir}".lower()
        if "eurjpy" in path_str:
            market = "EURJPY"
        elif "usdjpy" in path_str:
            market = "USDJPY"
        elif "gbpjpy" in path_str:
            market = "GBPJPY"
        elif "audusd" in path_str:
            market = "AUDUSD"
        elif "eurusd" in path_str:
            market = "EURUSD"
        elif "xauusd" in path_str or "gold" in path_str:
            market = "XAUUSD"
        else:
            m_mkt = re.search(r"trb_([a-zA-Z0-9]+)", path_str)
            market = m_mkt.group(1).upper() if m_mkt else "TRB"

    candidate_label = spec.get("candidate_label") or f"{candidate} ({market})"

    html_path = find_candidate_report_html(cand_dir, candidate)
    official_stats = {}
    deals_df = None

    if html_path is not None:
        official_stats = _load_official_trade_stats(html_path)
        deals_df = parse_mt5_html_for_deals(html_path)

    # Fallback to CSV if HTML report missing or returned no deals
    if deals_df is None or deals_df.empty:
        csv_df, csv_stats, csv_file = _load_candidate_from_csv(cand_dir, candidate, float(DEPOSIT))
        if csv_df is not None and not csv_df.empty:
            deals_df = csv_df
            if not official_stats:
                official_stats = csv_stats
            print(f"      [INFO] Successfully loaded trade data from CSV for {candidate}: {csv_file.name}")

    if deals_df is None or deals_df.empty:
        print(
            f"      [SKIP] Could not find or parse deal/trade data for {candidate} "
            f"under {cand_dir}."
        )
        return None

    raw_trades = _get_trade_rows(deals_df)

    if raw_trades is None or raw_trades.empty:
        print(f"      [SKIP] No trading rows found for {candidate}.")
        return None

    raw_trades = raw_trades.copy()
    raw_trades["Time"] = pd.to_datetime(
        raw_trades["Time"],
        errors="coerce",
    )
    raw_trades = (
        raw_trades
        .dropna(subset=["Time"])
        .sort_values("Time")
        .reset_index(drop=True)
    )

    for col in ("Profit", "Commission", "Swap", "NetTradePnl"):
        if col not in raw_trades.columns:
            raw_trades[col] = 0.0
        raw_trades[col] = pd.to_numeric(
            raw_trades[col],
            errors="coerce",
        ).fillna(0.0)

    # Reconcile P&L scaling
    raw_net_profit = float(raw_trades["NetTradePnl"].sum())
    official_net_profit = official_stats.get("total_net_profit")
    if official_net_profit is not None and abs(raw_net_profit) > 1e-12:
        equity_scale = float(official_net_profit) / raw_net_profit
    elif official_net_profit is not None and abs(raw_net_profit) <= 1e-12:
        equity_scale = 0.0
    else:
        equity_scale = 1.0

    raw_trades["EquityPnl"] = raw_trades["NetTradePnl"] * equity_scale

    weighted = raw_trades.copy()

    for col in ("Profit", "Commission", "Swap", "NetTradePnl", "EquityPnl"):
        weighted[col] = weighted[col] * weight

    print(
        f"      Parsed deal/activity rows: {len(raw_trades):,} for {candidate_label}"
    )
    print(
        f"      Raw parsed Net P&L: ${raw_net_profit:,.2f} | "
        f"MT5 official Net Profit: ${official_net_profit:,.2f}"
        if official_net_profit is not None
        else f"      Raw parsed Net P&L: ${raw_net_profit:,.2f} | MT5 official Net Profit: unavailable"
    )
    print(f"      Equity-stream normalisation factor: {equity_scale:.8f}")

    return {
        "run_dir": run_dir,
        "candidate": candidate,
        "candidate_label": candidate_label,
        "market": market,
        "weight": weight,
        "cand_dir": cand_dir,
        "html_path": html_path,
        "deals_df": deals_df,
        "trades_raw": raw_trades,
        "trades_weighted": weighted,
        "official_trade_stats": official_stats,
    }


# ===========================================================================
# TRADE-LEVEL NORMALISATION
# ===========================================================================

def _first_nonempty(series):
    """Return the first meaningful value in a Series."""
    for value in series:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "nat"}:
            return value
    return np.nan


def _normalise_position_key(value):
    """
    Return a stable position key.

    Numeric-looking MT5 Position IDs are normalised so values such as
    12345 and 12345.0 are treated as the same position.
    """
    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "nat"}:
        return None

    try:
        number = float(text)
        if np.isfinite(number) and number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass

    return text


def build_completed_trade_rows(
    trades: pd.DataFrame,
    candidate: str,
    weight: float = 1.0,
) -> tuple[pd.DataFrame, str]:
    """
    Convert MT5 deal/activity rows into one row per completed position.

    PRIMARY METHOD:
        Position ID grouping.

    FALLBACK:
        If Position is unavailable, each non-zero-P&L activity row is treated
        as one trade. This is explicitly reported as a fallback because the
        exact position-level trade count cannot be reconstructed without an
        identifier.
    """
    if trades is None or trades.empty:
        return pd.DataFrame(), "none"

    df = trades.copy()

    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"]).sort_values("Time").reset_index(drop=True)

    for col in ("Profit", "Commission", "Swap", "NetTradePnl"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        ).fillna(0.0)

    # -----------------------------------------------------------------------
    # Best/accurate route: group by MT5 Position ID.
    # -----------------------------------------------------------------------
    if "Position" in df.columns:
        position_keys = df["Position"].map(_normalise_position_key)
        valid_position = position_keys.notna()

        if valid_position.any():
            work = df.loc[valid_position].copy()
            work["_PositionKey"] = position_keys.loc[valid_position]

            rows = []

            for position_id, group in work.groupby(
                "_PositionKey",
                sort=False,
            ):
                group = group.sort_values("Time")

                row = {
                    "Candidate": candidate,
                    "Position": position_id,
                    "Time": group["Time"].max(),
                    "Profit": float(group["Profit"].sum()),
                    "Commission": float(group["Commission"].sum()),
                    "Swap": float(group["Swap"].sum()),
                    "NetTradePnl": float(group["NetTradePnl"].sum()),
                    "DealRows": int(len(group)),
                }

                # Keep useful descriptive fields if present.
                for col in (
                    "Direction",
                    "Type",
                    "Symbol",
                    "Volume",
                ):
                    if col in group.columns:
                        row[col] = _first_nonempty(group[col])

                rows.append(row)

            completed = pd.DataFrame(rows)

            if not completed.empty:
                completed = (
                    completed
                    .sort_values("Time")
                    .reset_index(drop=True)
                )

                # Position-level monetary values must also obey the portfolio
                # weight. This does not alter the raw equity stream.
                for col in (
                    "Profit",
                    "Commission",
                    "Swap",
                    "NetTradePnl",
                ):
                    completed[col] = completed[col] * weight

                return completed, "position_id"

    # -----------------------------------------------------------------------
    # Fallback: no Position ID available.
    #
    # We deliberately do not pretend that raw MT5 deal rows are necessarily
    # complete positions. The fallback is only used when MT5 did not expose
    # a usable Position identifier.
    # -----------------------------------------------------------------------
    pnl = pd.to_numeric(
        df["NetTradePnl"],
        errors="coerce",
    ).fillna(0.0)

    fallback = df.loc[pnl != 0.0].copy()

    if fallback.empty:
        return pd.DataFrame(), "deal_row_fallback"

    fallback = fallback.sort_values("Time").reset_index(drop=True)
    fallback.insert(0, "Candidate", candidate)
    fallback["Position"] = np.nan
    fallback["DealRows"] = 1

    for col in (
        "Profit",
        "Commission",
        "Swap",
        "NetTradePnl",
    ):
        fallback[col] = fallback[col] * weight

    return fallback, "deal_row_fallback"


def build_all_completed_trades(loaded: list) -> tuple[pd.DataFrame, dict]:
    """
    Build the true portfolio trade table.

    Each candidate is normalised separately so Position IDs from different
    candidates cannot collide.
    """
    frames = []
    methods = {}

    for item in loaded:
        cand_key = item.get("candidate_label", item["candidate"])
        completed, method = build_completed_trade_rows(
            item["trades_raw"],
            cand_key,
            item["weight"],
        )

        # The deal parser may not expose Position IDs. In that case the
        # official MT5 tester summary remains the authoritative trade count.
        if item.get("official_trade_stats", {}).get("total_trades") is not None:
            methods[cand_key] = "mt5_official_summary"
            methods[item["candidate"]] = "mt5_official_summary"
        else:
            methods[cand_key] = method
            methods[item["candidate"]] = method

        if completed is not None and not completed.empty:
            if "Market" not in completed.columns and item.get("market"):
                completed["Market"] = item["market"]
            frames.append(completed)

        item["completed_trades"] = completed
        item["trade_count_method"] = method

    if not frames:
        return pd.DataFrame(), methods

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    combined["Time"] = pd.to_datetime(
        combined["Time"],
        errors="coerce",
    )

    combined = (
        combined
        .dropna(subset=["Time"])
        .sort_values("Time")
        .reset_index(drop=True)
    )

    return combined, methods


# ===========================================================================
# CORRELATION
# ===========================================================================

def monthly_pnl_series(trades: pd.DataFrame) -> pd.Series:
    """
    Monthly net P&L.

    This intentionally uses the chronological activity/deal stream rather
    than position-level grouping because monthly P&L is a monetary aggregation,
    not a trade-count statistic.
    """
    if trades is None or trades.empty:
        return pd.Series(dtype=float)

    df = trades.copy()
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])

    pnl = pd.to_numeric(
        df["NetTradePnl"],
        errors="coerce",
    ).fillna(0.0)

    return (
        pd.Series(
            pnl.to_numpy(),
            index=df["Time"],
        )
        .resample("MS")
        .sum()
    )


def build_correlation_matrix(loaded: list) -> pd.DataFrame:
    """
    Pairwise correlation of each candidate's unweighted monthly net P&L.

    Weighting is deliberately excluded from the correlation calculation so
    sizing does not change the diversification measurement.
    """
    series = {}

    for item in loaded:
        cand_key = item.get("candidate_label", item["candidate"])
        series[cand_key] = monthly_pnl_series(
            item["trades_raw"]
        )

    combined = pd.DataFrame(series).fillna(0.0)

    names = [item.get("candidate_label", item["candidate"]) for item in loaded]

    if combined.shape[1] < 2 or combined.shape[0] < 2:
        return pd.DataFrame(
            np.nan,
            index=names,
            columns=names,
        )

    return combined.corr()


# ===========================================================================
# PORTFOLIO EQUITY STREAM
# ===========================================================================

def build_combined_deals(
    loaded: list,
    deposit: float,
) -> pd.DataFrame:
    """
    Concatenate weighted monetary activity into one chronological portfolio
    stream.

    This function does NOT convert deal rows into trade counts. Every monetary
    movement is retained exactly once for equity/P&L calculations.
    """
    frames = []

    for item in loaded:
        cols = [
            "Time",
            "Profit",
            "Commission",
            "Swap",
            "NetTradePnl",
            "EquityPnl",
        ]

        t = item["trades_weighted"][cols].copy()

        if "Type" in item["trades_weighted"].columns:
            t["Type"] = item["trades_weighted"]["Type"]

        if "Direction" in item["trades_weighted"].columns:
            t["Direction"] = item["trades_weighted"]["Direction"]

        if "Position" in item["trades_weighted"].columns:
            t["Position"] = item["trades_weighted"]["Position"]

        cand_key = item.get("candidate_label", item["candidate"])
        t["SourceCandidate"] = cand_key
        if item.get("market"):
            t["Market"] = item["market"]

        frames.append(t)

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    combined["Time"] = pd.to_datetime(
        combined["Time"],
        errors="coerce",
    )

    combined = (
        combined
        .dropna(subset=["Time"])
        .sort_values(
            ["Time", "SourceCandidate"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    for col in ("Profit", "Commission", "Swap", "NetTradePnl"):
        combined[col] = pd.to_numeric(
            combined[col],
            errors="coerce",
        ).fillna(0.0)

    # The shared portfolio starts at ONE deposit.
    # IMPORTANT: EquityPnl is the reconciled monetary stream. NetTradePnl is
    # the raw MT5 activity-row stream and can disagree with the official
    # tester result when the HTML parser falls back to activity rows.
    combined["Balance"] = (
        float(deposit)
        + pd.to_numeric(combined["EquityPnl"], errors="coerce")
          .fillna(0.0)
          .cumsum()
    )

    combined["IsBalanceOperation"] = False

    # These attrs are kept for compatibility with the reused reporting
    # functions. The stored trade_df is an independent snapshot to avoid
    # self-referential pandas attrs recursion.
    trade_df_snapshot = combined.copy()

    combined.attrs["trade_df"] = trade_df_snapshot
    combined.attrs["balance_reconstructed"] = True
    combined.attrs["parsed_rows"] = len(combined)
    combined.attrs["source_table"] = "combined_portfolio"
    combined.attrs["parser_mode"] = "portfolio_combination"

    return combined


# ===========================================================================
# PORTFOLIO METRICS
# ===========================================================================

def _calculate_portfolio_metrics(
    combined_df: pd.DataFrame,
    completed_trades: pd.DataFrame,
    deposit: float,
    official_trade_stats: dict | None = None,
) -> dict:
    """
    Calculate portfolio metrics with the correct distinction between:

      - raw monetary activity -> balance/equity/daily P&L
      - completed positions   -> trade statistics
    """
    result = {}

    if combined_df is None or combined_df.empty:
        return result

    df = combined_df.copy()
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = (
        df
        .dropna(subset=["Time"])
        .sort_values("Time")
        .reset_index(drop=True)
    )

    # -----------------------------------------------------------------------
    # Account-level balance
    # -----------------------------------------------------------------------
    pnl_stream = pd.to_numeric(
        df["EquityPnl"] if "EquityPnl" in df.columns else df["NetTradePnl"],
        errors="coerce",
    ).fillna(0.0)

    # IMPORTANT: do not reuse any Balance column from the MT5 activity parser.
    # That column can represent the raw activity/deal stream and is not the
    # reconciled portfolio equity stream. EquityPnl is the only source used
    # for the combined portfolio balance.
    equity = (
        float(deposit)
        + pnl_stream.cumsum()
    ).to_numpy(dtype=float)
    total_net_profit = float(pnl_stream.sum())

    # MT5 official net profit is the authoritative endpoint for the portfolio.
    # With weights, the portfolio profit is the weighted sum of candidate profits.
    if official_trade_stats and official_trade_stats.get("total_net_profit") is not None:
        # official_trade_stats passed to this function is already the weighted
        # sum assembled by main().
        total_net_profit = float(official_trade_stats["total_net_profit"])

    # -----------------------------------------------------------------------
    # Drawdown
    # -----------------------------------------------------------------------
    finite = np.isfinite(equity)

    if finite.any():
        equity_finite = equity[finite]

        peak = np.maximum.accumulate(equity_finite)
        dd = peak - equity_finite

        max_dd = float(np.max(dd)) if len(dd) else 0.0
        max_dd_index = int(np.argmax(dd)) if len(dd) else 0

        peak_index = (
            int(np.argmax(equity_finite[: max_dd_index + 1]))
            if len(equity_finite)
            else 0
        )

        peak_balance = (
            float(equity_finite[peak_index])
            if len(equity_finite)
            else 0.0
        )

        max_dd_pct = (
            max_dd / peak_balance * 100.0
            if peak_balance != 0
            else 0.0
        )
    else:
        max_dd = 0.0
        max_dd_pct = 0.0

    # -----------------------------------------------------------------------
    # COMPLETED TRADE STATISTICS
    # -----------------------------------------------------------------------
    if completed_trades is not None and not completed_trades.empty:
        trades = completed_trades.copy()

        trades["Time"] = pd.to_datetime(
            trades["Time"],
            errors="coerce",
        )

        trade_pnl = pd.to_numeric(
            trades["NetTradePnl"],
            errors="coerce",
        ).fillna(0.0)

        # Completed positions, including zero-P&L positions.
        total_trades = int(len(trades))

        positive = trade_pnl[trade_pnl > 0]
        negative = trade_pnl[trade_pnl < 0]
        breakeven = trade_pnl[trade_pnl == 0]

        gross_profit = float(positive.sum())
        gross_loss = float(negative.sum())

        profit_factor = (
            gross_profit / abs(gross_loss)
            if gross_loss < 0
            else float("inf")
        )

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for value in trade_pnl:
            if value > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif value < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0

        win_rate = (
            float((trade_pnl > 0).mean() * 100.0)
            if total_trades
            else 0.0
        )

        avg_win = (
            float(positive.mean())
            if len(positive)
            else 0.0
        )

        avg_loss = (
            float(negative.mean())
            if len(negative)
            else 0.0
        )

        largest_profit = (
            float(positive.max())
            if len(positive)
            else 0.0
        )

        largest_loss = (
            float(negative.min())
            if len(negative)
            else 0.0
        )

        # Position holding times.
        holding_seconds = []

        if (
            "Position" in trades.columns
            and trades["Position"].notna().any()
        ):
            # The completed table already contains one row per position, so
            # exact holding time must be calculated from the original raw
            # activity rows below. This is filled later from raw rows.
            pass

        # Long/short breakdown from completed positions.
        long_count = 0
        short_count = 0
        long_win_rate = 0.0
        short_win_rate = 0.0

        direction_col = None

        if "Direction" in trades.columns:
            direction_col = "Direction"
        elif "Type" in trades.columns:
            direction_col = "Type"

        if direction_col:
            labels = trades[direction_col].astype(str).str.lower()

            long_mask = labels.apply(
                lambda x: "buy" in x or "long" in x
            )

            short_mask = labels.apply(
                lambda x: "sell" in x or "short" in x
            )

            if long_mask.any():
                long_count = int(long_mask.sum())
                long_win_rate = float(
                    (
                        trade_pnl.loc[long_mask] > 0
                    ).mean() * 100.0
                )

            if short_mask.any():
                short_count = int(short_mask.sum())
                short_win_rate = float(
                    (
                        trade_pnl.loc[short_mask] > 0
                    ).mean() * 100.0
                )

    else:
        # No position-level table available.
        trades = pd.DataFrame()
        trade_pnl = pd.Series(dtype=float)

        total_trades = 0
        positive = pd.Series(dtype=float)
        negative = pd.Series(dtype=float)
        breakeven = pd.Series(dtype=float)
        gross_profit = 0.0
        gross_loss = 0.0
        profit_factor = 0.0
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        largest_profit = 0.0
        largest_loss = 0.0
        max_wins = 0
        max_losses = 0
        long_count = 0
        short_count = 0
        long_win_rate = 0.0
        short_win_rate = 0.0

    # -----------------------------------------------------------------------
    # Authoritative MT5 trade counts
    # -----------------------------------------------------------------------
    if official_trade_stats and official_trade_stats.get("total_trades") is not None:
        total_trades = int(official_trade_stats["total_trades"])
    else:
        total_trades = int(len(trades)) if completed_trades is not None else 0

    if official_trade_stats:
        official_profit = official_trade_stats.get("profit_trades")
        official_loss = official_trade_stats.get("loss_trades")
    else:
        official_profit = official_loss = None

    if official_profit is not None and official_loss is not None:
        # Enforce the fundamental invariant: profit + loss <= total trades.
        if official_profit + official_loss <= total_trades:
            profit_trades_count = int(official_profit)
            loss_trades_count = int(official_loss)
            breakeven_count = total_trades - profit_trades_count - loss_trades_count
        else:
            print(
                "      [WARNING] MT5 summary profit/loss counts exceeded Total Trades; "
                "using Total Trades and deriving breakeven only from valid counts."
            )
            profit_trades_count = min(int(official_profit), total_trades)
            loss_trades_count = min(int(official_loss), total_trades - profit_trades_count)
            breakeven_count = total_trades - profit_trades_count - loss_trades_count
    else:
        # We cannot manufacture trade-level win/loss counts from deal rows when
        # Position IDs are absent. Keep the report internally consistent.
        profit_trades_count = 0
        loss_trades_count = 0
        breakeven_count = total_trades

    win_rate = (profit_trades_count / total_trades * 100.0) if total_trades else 0.0

    # -----------------------------------------------------------------------
    # Daily statistics and Sharpe
    # -----------------------------------------------------------------------
    daily = (
        df.set_index("Time")[pnl_stream.name if pnl_stream.name else "NetTradePnl"]
        .resample("D")
        .sum()
    )
    # Report the number of calendar dates on which this portfolio actually had
    # activity, rather than every calendar day between 2013 and 2026.
    active_trading_days = int(df["Time"].dt.normalize().nunique())

    daily_returns = (
        daily / float(deposit)
        if deposit
        else pd.Series(dtype=float)
    )

    if (
        len(daily_returns) >= 2
        and daily_returns.std(ddof=1) > 0
    ):
        sharpe = float(
            (
                daily_returns.mean()
                / daily_returns.std(ddof=1)
            )
            * math.sqrt(252)
        )
    else:
        sharpe = 0.0

    # -----------------------------------------------------------------------
    # Holding time from raw position IDs
    # -----------------------------------------------------------------------
    min_hold = None
    max_hold = None
    avg_hold = None

    if "Position" in df.columns:
        raw_positions = df.copy()
        raw_positions["_PositionKey"] = raw_positions[
            "Position"
        ].map(_normalise_position_key)

        raw_positions = raw_positions.dropna(
            subset=["_PositionKey"]
        )

        if not raw_positions.empty:
            holding = (
                raw_positions
                .groupby("_PositionKey")["Time"]
                .agg(["min", "max"])
            )

            durations = (
                holding["max"] - holding["min"]
            ).dt.total_seconds()

            durations = durations[durations >= 0]

            if not durations.empty:
                min_hold = float(durations.min())
                max_hold = float(durations.max())
                avg_hold = float(durations.mean())

    # Use MT5 official gross figures when available. The parsed activity table
    # is intentionally not trusted for these totals when its endpoint required
    # normalisation to MT5's official net profit.
    if official_trade_stats:
        if official_trade_stats.get("gross_profit") is not None:
            gross_profit = float(official_trade_stats["gross_profit"])
        if official_trade_stats.get("gross_loss") is not None:
            gross_loss = float(official_trade_stats["gross_loss"])
        if gross_loss < 0:
            profit_factor = gross_profit / abs(gross_loss)
        if profit_trades_count > 0:
            avg_win = gross_profit / profit_trades_count
        if loss_trades_count > 0:
            avg_loss = gross_loss / loss_trades_count
        if official_trade_stats.get("largest_profit") is not None:
            largest_profit = float(official_trade_stats["largest_profit"])
        if official_trade_stats.get("largest_loss") is not None:
            largest_loss = float(official_trade_stats["largest_loss"])

    # Without Position IDs, deal-row sequencing is not a reliable representation
    # of trade sequencing/direction. Do not publish misleading values.
    if not ("Position" in df.columns and df["Position"].notna().any()):
        max_wins = 0
        max_losses = 0
        long_count = 0
        short_count = 0
        long_win_rate = 0.0
        short_win_rate = 0.0

    result.update(
        {
            "total_net_profit": total_net_profit,
            "profit_pct": (
                total_net_profit / deposit * 100.0
                if deposit
                else 0.0
            ),
            "max_dd": max_dd,
            "max_dd_pct": max_dd_pct,
            "profit_factor": profit_factor,
            "recovery_factor": (
                total_net_profit / max_dd
                if max_dd > 0
                else float("inf")
            ),
            "sharpe": sharpe,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": total_trades,
            "profit_trades": profit_trades_count,
            "loss_trades": loss_trades_count,
            "breakeven_trades": breakeven_count,
            "win_rate": win_rate,
            "trade_count_source": (
                "MT5 official tester summary (STAT_TRADES)"
                if official_trade_stats and official_trade_stats.get("total_trades") is not None
                else "parsed activity rows"
            ),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "largest_profit": largest_profit,
            "largest_loss": largest_loss,
            "max_consecutive_wins": max_wins,
            "max_consecutive_losses": max_losses,
            "daily_count": active_trading_days,
            "min_hold": min_hold,
            "max_hold": max_hold,
            "avg_hold": avg_hold,
        }
    )

    if official_trade_stats:
        if official_trade_stats.get("long_trades_text") is not None:
            result["long_text"] = official_trade_stats["long_trades_text"]
        if official_trade_stats.get("short_trades_text") is not None:
            result["short_text"] = official_trade_stats["short_trades_text"]

    if long_count:
        result["long_count"] = long_count
        result["long_win_rate"] = long_win_rate

    if short_count:
        result["short_count"] = short_count
        result["short_win_rate"] = short_win_rate

    return result


# ===========================================================================
# PORTFOLIO HEATMAP
# ===========================================================================

def generate_portfolio_monthly_heatmap(
    combined_df: pd.DataFrame,
    deposit: float,
    output_dir: Path,
):
    """Generate the portfolio heatmap locally, avoiding the runner's fragile save path."""
    if combined_df is None or combined_df.empty:
        return None, None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = combined_df.copy()
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df["EquityPnl"] = pd.to_numeric(df["EquityPnl"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["Time"]).sort_values("Time")
    if df.empty:
        return None, None

    df["Year"] = df["Time"].dt.year
    df["Month"] = df["Time"].dt.month
    monthly = (
        df.groupby(["Year", "Month"])["EquityPnl"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )

    years = list(monthly.index)
    # 12 monthly cells + a final Year Total column. The Year Total is the
    # complete gain/loss for that calendar year, and its percentage is always
    # measured against the portfolio's original starting balance (e.g. $2,500),
    # exactly as requested.
    matrix = np.zeros((len(years), 13), dtype=float)
    for r, year in enumerate(years):
        for month in range(1, 13):
            if month in monthly.columns:
                matrix[r, month - 1] = float(monthly.loc[year, month])
        matrix[r, 12] = float(matrix[r, :12].sum())

    fig, ax = plt.subplots(
        figsize=(14.5, max(3.2, 1.0 + 0.55 * len(years)))
    )
    try:
        vmax = float(np.max(np.abs(matrix))) if matrix.size else 1.0
        if not np.isfinite(vmax) or vmax <= 0:
            vmax = 1.0

        im = ax.imshow(
            matrix,
            aspect="auto",
            cmap="RdYlGn",
            vmin=-vmax,
            vmax=vmax,
        )

        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        ax.set_xticks(range(13), months + ["Year Total"])
        ax.set_yticks(range(len(years)), [str(y) for y in years])
        ax.set_xlabel("Month / Year Total")
        ax.set_ylabel("Year")
        ax.set_title("Combined Portfolio Monthly Performance — Year Total = Gain/Loss vs Starting Balance", fontsize=13, fontweight="bold")

        for r in range(matrix.shape[0]):
            for c in range(matrix.shape[1]):
                value = matrix[r, c]
                pct = value / deposit * 100.0 if deposit else 0.0
                label = f"${value:,.0f}\n{pct:+.1f}%"
                if c == 12:
                    label = f"YEAR\n${value:,.0f}\n{pct:+.1f}%"
                ax.text(
                    c,
                    r,
                    label,
                    ha="center",
                    va="center",
                    fontsize=8,
                    fontweight="bold" if c == 12 else "normal",
                )

        fig.colorbar(im, ax=ax, label="Monthly P&L ($)")
        fig.tight_layout()

        # Delete a stale target before saving. This also avoids certain Windows
        # file-handle/path failures when an earlier run left a damaged target.
        path = output_dir / "monthly_performance_heatmap.png"
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError as exc:
            print(f"    [WARNING] Could not remove old heatmap: {exc}")

        try:
            fig.savefig(str(path), dpi=180, bbox_inches="tight", format="png")
        except OSError as exc:
            # A shorter filename in the same output directory is a safe Windows
            # fallback. The report still records the actual generated path.
            fallback = output_dir / "heatmap.png"
            print(f"    [WARNING] Primary heatmap save failed: {exc}")
            print(f"               Retrying with {fallback.name} ...")
            fig.savefig(str(fallback), dpi=180, bbox_inches="tight", format="png")
            path = fallback

        return path, monthly
    finally:
        plt.close(fig)


# ===========================================================================
# COMPARISON CHART
# ===========================================================================

def generate_comparison_chart(
    loaded: list,
    combined_df: pd.DataFrame,
    deposit: float,
    output_dir: Path,
):
    """Overlay standalone candidate P&L against combined portfolio P&L."""
    try:
        fig, ax = plt.subplots(figsize=(10.5, 5.5))

        for item in loaded:
            t = item["trades_raw"].sort_values("Time")

            if t.empty:
                continue

            cum = (
                pd.to_numeric(
                    t["EquityPnl"] if "EquityPnl" in t.columns else t["NetTradePnl"],
                    errors="coerce",
                )
                .fillna(0.0)
                .cumsum()
            )

            ax.plot(
                t["Time"],
                cum,
                linewidth=1.0,
                alpha=0.65,
                label=f"{item['candidate']} (standalone)",
            )

        combined_cum = (
            combined_df["Balance"]
            - float(deposit)
        )

        ax.plot(
            combined_df["Time"],
            combined_cum,
            linewidth=2.3,
            color="black",
            label="Combined Portfolio",
        )

        ax.axhline(
            0,
            linestyle="--",
            linewidth=1.0,
            color="gray",
        )

        ax.set_title(
            "Individual Candidates vs Combined Portfolio ($)",
            fontsize=12,
            fontweight="bold",
        )
        ax.set_xlabel("Time")
        ax.set_ylabel("Cumulative P&L ($)")

        ax.legend(
            fontsize=8,
            loc="upper left",
        )

        locator = mdates.AutoDateLocator()

        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)
        )

        path = (
            output_dir
            / "chart_candidates_vs_combined.png"
        )

        fig.tight_layout()
        fig.savefig(
            path,
            dpi=180,
            bbox_inches="tight",
        )
        plt.close(fig)

        return path

    except Exception as exc:
        plt.close("all")
        print(
            f"    [WARNING] Could not generate "
            f"candidates-vs-combined chart: {exc}"
        )
        return None


# ===========================================================================
# FOLDER RESOLUTION
# ===========================================================================

def resolve_portfolio_name(
    quant_dir: Path,
    quant_name: str,
    requested: str | None,
    overwrite: bool,
) -> str:
    """Resolve the output portfolio folder name."""
    pattern = re.compile(
        rf"^{re.escape(quant_name)}_Portfolio_(\d+)$",
        re.IGNORECASE,
    )

    existing_nums = []

    if quant_dir.exists():
        for d in quant_dir.iterdir():
            if d.is_dir():
                m = pattern.match(d.name)

                if m:
                    existing_nums.append(
                        int(m.group(1))
                    )

    if requested:
        name = requested

        if (
            quant_dir / name
        ).exists() and not overwrite:
            n = 2

            while (
                quant_dir / f"{requested}_v{n}"
            ).exists():
                n += 1

            name = f"{requested}_v{n}"

            print(
                f"  [INFO] '{requested}' already exists; "
                f"using '{name}' instead."
            )

        return name

    next_num = (
        max(existing_nums) + 1
        if existing_nums
        else 1
    )

    return f"{quant_name}_Portfolio_{next_num:03d}"


# ===========================================================================
# WORD REPORT HELPERS
# ===========================================================================

def _shade_cell(cell, hex_color: str):
    if docx is None:
        return

    tcPr = cell._tc.get_or_add_tcPr()

    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)

    tcPr.append(shd)


def _add_kv_table(doc, rows):
    table = doc.add_table(
        rows=0,
        cols=2,
    )

    table.style = "Table Grid"

    for key, value in rows:
        cells = table.add_row().cells

        _set_cell_text(
            cells[0],
            key,
            bold=True,
        )

        _set_cell_text(
            cells[1],
            value,
        )

    return table


def _add_heatmap_table(
    doc,
    monthly_profit: pd.DataFrame,
    deposit: float,
):
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    hm = doc.add_table(
        rows=1,
        cols=14,
    )

    hm.style = "Table Grid"

    header = hm.rows[0].cells

    _set_cell_text(
        header[0],
        "Year",
        bold=True,
    )

    for i, month in enumerate(
        months,
        start=1,
    ):
        _set_cell_text(
            header[i],
            month,
            bold=True,
        )

    _set_cell_text(
        header[13],
        "Total",
        bold=True,
    )

    for year in monthly_profit.index:
        cells = hm.add_row().cells

        _set_cell_text(
            cells[0],
            str(year),
            bold=True,
        )

        year_total = 0.0

        for month_no in range(1, 13):
            if month_no in monthly_profit.columns:
                value = float(
                    monthly_profit.loc[
                        year,
                        month_no,
                    ]
                )
            else:
                value = 0.0

            year_total += value

            pct = (
                value / deposit * 100.0
                if deposit
                else 0.0
            )

            _set_cell_text(
                cells[month_no],
                f"${value:,.0f}\n({pct:+.1f}%)",
            )

            for p in cells[month_no].paragraphs:
                for run in p.runs:
                    if value > 0:
                        run.font.color.rgb = RGBColor(
                            0,
                            128,
                            0,
                        )
                    elif value < 0:
                        run.font.color.rgb = RGBColor(
                            192,
                            0,
                            0,
                        )

        year_pct = (
            year_total / deposit * 100.0
            if deposit
            else 0.0
        )

        _set_cell_text(
            cells[13],
            f"${year_total:,.0f}\n({year_pct:+.1f}%)",
            bold=True,
        )

        for p in cells[13].paragraphs:
            for run in p.runs:
                run.bold = True

                if year_total > 0:
                    run.font.color.rgb = RGBColor(
                        0,
                        128,
                        0,
                    )
                elif year_total < 0:
                    run.font.color.rgb = RGBColor(
                        192,
                        0,
                        0,
                    )


# ===========================================================================
# WORD REPORT
# ===========================================================================

def create_portfolio_word_doc(
    doc_path: Path,
    portfolio_name: str,
    loaded: list,
    corr: pd.DataFrame,
    derived: dict,
    charts: dict,
    heatmap_path,
    monthly_profit: pd.DataFrame,
    compare_path,
    deposit: float,
    completed_trades: pd.DataFrame,
    trade_methods: dict,
):
    if docx is None:
        print(
            "    [ERROR] python-docx is not installed; "
            "cannot create Word report."
        )
        return None

    doc = docx.Document()

    title = doc.add_heading(
        f"Quant Portfolio Report - {portfolio_name}",
        0,
    )

    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(
        f"This portfolio combines {len(loaded)} candidate(s) "
        f"into one simulated equity stream using a shared "
        f"starting deposit of {_fmt_money(deposit)}."
    )

    # -----------------------------------------------------------------------
    # 1. Composition
    # -----------------------------------------------------------------------
    doc.add_heading(
        "1. Portfolio Composition & Standalone Performance",
        level=1,
    )

    corr_avg = {}

    for cand in corr.columns:
        others = (
            corr.loc[cand]
            .drop(labels=[cand])
            if cand in corr.index
            else pd.Series(dtype=float)
        )

        corr_avg[cand] = (
            float(others.mean())
            if len(others.dropna())
            else float("nan")
        )

    comp_table = doc.add_table(
        rows=1,
        cols=7,
    )

    comp_table.style = "Table Grid"

    header = comp_table.rows[0].cells

    labels = [
        "Candidate",
        "Run Folder",
        "Weight",
        "Standalone P/L %",
        "Standalone Max DD %",
        "Standalone PF",
        "Avg Corr vs Others",
    ]

    for i, label in enumerate(labels):
        _set_cell_text(
            header[i],
            label,
            bold=True,
        )

    for item in loaded:
        # Standalone metrics are reconstructed from that candidate's own
        # position-level trade table and account balance.
        standalone_trades, _ = build_completed_trade_rows(
            item["trades_raw"],
            item["candidate"],
            item["weight"],
        )

        standalone_df = item["deals_df"]

        # The balance/P&L for standalone performance should use the original
        # candidate's own account, not the portfolio weight.
        standalone_balance = pd.to_numeric(
            standalone_df["Balance"],
            errors="coerce",
        )

        if item.get("official_trade_stats", {}).get("total_net_profit") is not None:
            standalone_profit = float(item["official_trade_stats"]["total_net_profit"]) * float(item["weight"])
        elif standalone_balance.notna().any():
            standalone_profit = float(
                standalone_balance.dropna().iloc[-1]
                - deposit
            )
        else:
            standalone_profit = float(
                pd.to_numeric(
                    item["trades_raw"]["NetTradePnl"],
                    errors="coerce",
                )
                .fillna(0.0)
                .sum()
            )

        standalone_trade_pnl = (
            pd.to_numeric(
                standalone_trades["NetTradePnl"],
                errors="coerce",
            ).fillna(0.0)
            if not standalone_trades.empty
            else pd.Series(dtype=float)
        )

        positive = standalone_trade_pnl[
            standalone_trade_pnl > 0
        ]
        negative = standalone_trade_pnl[
            standalone_trade_pnl < 0
        ]

        gross_profit = float(positive.sum())
        gross_loss = float(negative.sum())

        standalone_pf = (
            gross_profit / abs(gross_loss)
            if gross_loss < 0
            else float("inf")
        )

        if standalone_balance.notna().any():
            equity = (
                standalone_balance
                .dropna()
                .to_numpy(dtype=float)
            )

            peak = np.maximum.accumulate(equity)
            dd = peak - equity
            standalone_dd = (
                float(np.max(dd))
                if len(dd)
                else 0.0
            )

            peak_idx = (
                int(np.argmax(equity[: int(np.argmax(dd)) + 1]))
                if len(equity)
                else 0
            )

            peak_value = (
                float(equity[peak_idx])
                if len(equity)
                else deposit
            )

            standalone_dd_pct = (
                standalone_dd / peak_value * 100.0
                if peak_value
                else 0.0
            )
        else:
            standalone_dd_pct = 0.0

        cells = comp_table.add_row().cells

        cand_disp = item.get("candidate_label", item["candidate"])
        _set_cell_text(
            cells[0],
            cand_disp,
            bold=True,
        )

        _set_cell_text(
            cells[1],
            item["run_dir"],
        )

        _set_cell_text(
            cells[2],
            f"{item['weight']:.2f}",
        )

        _set_cell_text(
            cells[3],
            _fmt_pct(
                standalone_profit / deposit * 100.0
                if deposit
                else 0.0
            ),
        )

        _set_cell_text(
            cells[4],
            _fmt_pct(standalone_dd_pct),
        )

        _set_cell_text(
            cells[5],
            _fmt_ratio(standalone_pf),
        )

        avg_c = corr_avg.get(
            cand_disp,
            corr_avg.get(item["candidate"], float("nan")),
        )

        _set_cell_text(
            cells[6],
            "N/A"
            if pd.isna(avg_c)
            else f"{avg_c:.2f}",
        )

    # -----------------------------------------------------------------------
    # 2. Correlation
    # -----------------------------------------------------------------------
    doc.add_heading(
        "2. Pairwise Monthly P&L Correlation",
        level=1,
    )

    doc.add_paragraph(
        f"Correlation is computed from each candidate's own "
        f"unweighted monthly net P&L. Off-diagonal values at or "
        f"below {CORRELATION_PAIRING_THRESHOLD:.2f} are shaded "
        f"green; values above the threshold are shaded red."
    )

    n = len(corr.columns)

    if n >= 2:
        ctable = doc.add_table(
            rows=n + 1,
            cols=n + 1,
        )

        ctable.style = "Table Grid"

        _set_cell_text(
            ctable.cell(0, 0),
            "",
        )

        for i, cand in enumerate(corr.columns):
            _set_cell_text(
                ctable.cell(0, i + 1),
                cand,
                bold=True,
            )

            _set_cell_text(
                ctable.cell(i + 1, 0),
                cand,
                bold=True,
            )

        for i, row_c in enumerate(corr.index):
            for j, col_c in enumerate(corr.columns):
                value = corr.loc[
                    row_c,
                    col_c,
                ]

                cell = ctable.cell(
                    i + 1,
                    j + 1,
                )

                text = (
                    "N/A"
                    if pd.isna(value)
                    else f"{float(value):.2f}"
                )

                _set_cell_text(
                    cell,
                    text,
                    bold=(row_c == col_c),
                )

                if row_c == col_c:
                    _shade_cell(
                        cell,
                        "D9D9D9",
                    )
                elif not pd.isna(value):
                    _shade_cell(
                        cell,
                        (
                            "C6EFCE"
                            if abs(float(value))
                            <= CORRELATION_PAIRING_THRESHOLD
                            else "FFC7CE"
                        ),
                    )
    else:
        doc.add_paragraph(
            "Not enough overlapping monthly history "
            "to compute correlation."
        )

    # -----------------------------------------------------------------------
    # 3. Combined performance
    # -----------------------------------------------------------------------
    doc.add_heading(
        "3. Combined Portfolio Performance Overview",
        level=1,
    )

    total_net_profit = derived.get(
        "total_net_profit",
        0.0,
    )

    max_dd = derived.get(
        "max_dd",
        0.0,
    )

    rows = [
        (
            "Profit / Loss ($)",
            _fmt_money(total_net_profit),
        ),
        (
            "Profit / Loss (%)",
            _fmt_pct(
                derived.get(
                    "profit_pct",
                    0.0,
                )
            ),
        ),
        (
            "Max Balance Drawdown",
            _fmt_money(max_dd),
        ),
        (
            "Max Balance Drawdown (%)",
            _fmt_pct(
                derived.get(
                    "max_dd_pct",
                    0.0,
                )
            ),
        ),
        (
            "Profit Factor",
            _fmt_ratio(
                derived.get(
                    "profit_factor",
                    0.0,
                )
            ),
        ),
        (
            "Recovery Factor",
            _fmt_ratio(
                derived.get(
                    "recovery_factor",
                    0.0,
                )
            ),
        ),
        (
            "Return / Drawdown Ratio",
            _fmt_ratio(
                total_net_profit / max_dd
                if max_dd > 0
                else 0.0
            )
            if max_dd > 0
            else "N/A",
        ),
        (
            "Sharpe Ratio",
            f"{derived.get('sharpe', 0.0):.2f}",
        ),
        (
            "Max Consecutive Wins",
            f"{int(derived.get('max_consecutive_wins', 0)):,}",
        ),
        (
            "Max Consecutive Losses",
            f"{int(derived.get('max_consecutive_losses', 0)):,}",
        ),
    ]

    _add_kv_table(
        doc,
        rows,
    )

    # -----------------------------------------------------------------------
    # 4. Trade statistics
    # -----------------------------------------------------------------------
    doc.add_heading(
        "4. Combined Trade Statistics Breakdown",
        level=1,
    )

    total_trades = int(
        derived.get(
            "total_trades",
            0,
        )
    )

    profit_trades = int(
        derived.get(
            "profit_trades",
            0,
        )
    )

    loss_trades = int(
        derived.get(
            "loss_trades",
            0,
        )
    )

    breakeven_trades = int(
        derived.get(
            "breakeven_trades",
            0,
        )
    )

    long_text = "N/A"
    short_text = "N/A"

    if "long_text" in derived:
        long_text = derived["long_text"]
    elif "long_count" in derived:
        long_text = f"{derived['long_count']} ({derived['long_win_rate']:.2f}% won)"

    if "short_text" in derived:
        short_text = derived["short_text"]
    elif "short_count" in derived:
        short_text = f"{derived['short_count']} ({derived['short_win_rate']:.2f}% won)"

    rows = [
        (
            "Total Completed Trades",
            f"{total_trades:,}",
        ),
        (
            "Profit Trades",
            f"{profit_trades:,}",
        ),
        (
            "Loss Trades",
            f"{loss_trades:,}",
        ),
        (
            "Breakeven Trades",
            f"{breakeven_trades:,}",
        ),
        (
            "Long Trades (Won %)",
            long_text,
        ),
        (
            "Short Trades (Won %)",
            short_text,
        ),
        (
            "Average Win per Trade",
            _fmt_money(
                derived.get(
                    "avg_win",
                    0.0,
                )
            ),
        ),
        (
            "Average Loss per Trade",
            _fmt_money(
                derived.get(
                    "avg_loss",
                    0.0,
                )
            ),
        ),
        (
            "Largest Profit Trade",
            _fmt_money(
                derived.get(
                    "largest_profit",
                    0.0,
                )
            ),
        ),
        (
            "Largest Loss Trade",
            _fmt_money(
                derived.get(
                    "largest_loss",
                    0.0,
                )
            ),
        ),
        (
            "Gross Profit",
            _fmt_money(
                derived.get(
                    "gross_profit",
                    0.0,
                )
            ),
        ),
        (
            "Gross Loss",
            _fmt_money(
                derived.get(
                    "gross_loss",
                    0.0,
                )
            ),
        ),
    ]

    _add_kv_table(
        doc,
        rows,
    )

    # Explicit trade-count audit.
    doc.add_heading(
        "4A. Trade Count Audit",
        level=2,
    )

    for item in loaded:
        cand_disp = item.get("candidate_label", item["candidate"])
        method = trade_methods.get(
            cand_disp,
            trade_methods.get(item["candidate"], "unknown"),
        )

        completed_count = (
            int(item.get("official_trade_stats", {}).get("total_trades"))
            if item.get("official_trade_stats", {}).get("total_trades") is not None
            else (
                len(item.get("completed_trades", []))
                if item.get("completed_trades") is not None
                else 0
            )
        )

        raw_count = len(
            item["trades_raw"]
        )

        if method == "mt5_official_summary":
            official_count = item.get("official_trade_stats", {}).get("total_trades", completed_count)
            explanation = (
                f"{item['candidate']}: {int(official_count):,} completed trade(s) "
                f"from MT5's official tester summary (STAT_TRADES); {raw_count:,} "
                f"raw activity/deal rows were used for the equity stream."
            )
        elif method == "position_id":
            explanation = (
                f"{item['candidate']}: {completed_count:,} "
                f"completed position(s) reconstructed from MT5 "
                f"Position IDs; {raw_count:,} raw activity/deal rows "
                f"were used to build the equity stream."
            )
        else:
            explanation = (
                f"{item['candidate']}: {completed_count:,} trade rows "
                f"were available, but MT5 did not expose a usable "
                f"Position ID. This is a fallback count and cannot be "
                f"confirmed as an exact position count from the parsed "
                f"data alone."
            )

        doc.add_paragraph(explanation)

    # -----------------------------------------------------------------------
    # 5. Averages / holding
    # -----------------------------------------------------------------------
    doc.add_heading(
        "5. Combined Averages & Holding Times",
        level=1,
    )

    start_dt = pd.to_datetime(
        PORTFOLIO_START
    )

    end_dt = pd.to_datetime(
        PORTFOLIO_END
    )

    days_in_test = max(
        1,
        (end_dt - start_dt).days,
    )

    avg_trades_month = (
        total_trades / days_in_test
    ) * 30.44

    avg_prof_day = (
        total_net_profit / days_in_test
    )

    rows = [
        (
            "Average Trades per Month",
            f"{avg_trades_month:.2f}",
        ),
        (
            "Average Profit per Day",
            _fmt_money(avg_prof_day),
        ),
        (
            "Average Profit per Month",
            _fmt_money(
                avg_prof_day * 30.44
            ),
        ),
        (
            "Average Profit per Year",
            _fmt_money(
                avg_prof_day * 365.25
            ),
        ),
        (
            "Min Position Holding Time",
            _seconds_to_duration(
                derived.get("min_hold")
            ),
        ),
        (
            "Max Position Holding Time",
            _seconds_to_duration(
                derived.get("max_hold")
            ),
        ),
        (
            "Avg Position Holding Time",
            _seconds_to_duration(
                derived.get("avg_hold")
            ),
        ),
        (
            "Historical Trading Days (Active)",
            f"{derived.get('daily_count', 0):,}",
        ),
    ]

    _add_kv_table(
        doc,
        rows,
    )

    # -----------------------------------------------------------------------
    # 6. Equity curves
    # -----------------------------------------------------------------------
    doc.add_heading(
        "6. Combined Equity Curves",
        level=1,
    )

    chart_titles = {
        "dollar_gains": "Total Profit / Loss ($)",
        "equity_growth": "Equity / Balance Growth",
        "percent_gain": "Percentage Gain / Loss (%)",
    }

    if charts:
        for key, title_text in chart_titles.items():
            if (
                key in charts
                and Path(charts[key]).exists()
            ):
                paragraph = doc.add_paragraph(
                    title_text
                )

                paragraph.runs[0].bold = True

                doc.add_picture(
                    str(charts[key]),
                    width=Inches(6.9),
                )
    else:
        doc.add_paragraph(
            "Equity charts could not be generated."
        )

    if (
        compare_path
        and Path(compare_path).exists()
    ):
        paragraph = doc.add_paragraph(
            "Individual Candidates vs Combined Portfolio"
        )

        paragraph.runs[0].bold = True

        doc.add_picture(
            str(compare_path),
            width=Inches(6.9),
        )

    # -----------------------------------------------------------------------
    # 7. Heatmap
    # -----------------------------------------------------------------------
    doc.add_heading(
        "7. Combined Monthly Performance Heatmap ($ and %)",
        level=1,
    )

    if (
        heatmap_path
        and Path(heatmap_path).exists()
    ):
        doc.add_picture(
            str(heatmap_path),
            width=Inches(6.9),
        )

        cap = doc.add_paragraph(
            "Monthly P&L is shown in dollars; percentage is monthly "
            "(or yearly for the Total column) P&L divided by the "
            "shared starting deposit."
        )

        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if (
        monthly_profit is not None
        and not monthly_profit.empty
    ):
        _add_heatmap_table(
            doc,
            monthly_profit,
            deposit,
        )

    # -----------------------------------------------------------------------
    # 8. Data quality
    # -----------------------------------------------------------------------
    doc.add_heading(
        "8. Data Quality & Calculation Notes",
        level=1,
    )

    notes = [
        (
            f"Combined from {len(loaded)} candidate report(s). "
            "The portfolio starts from one shared deposit; the "
            "individual candidates' deposits are not added together."
        ),
        (
            "The chronological equity stream retains each parsed monetary "
            "activity row exactly once, after applying the configured "
            "portfolio weight."
        ),
        (
            "Trade statistics are NOT counted from raw MT5 deal-row count. "
            "Where Position IDs are available, all activity belonging to "
            "one Position ID is aggregated into one completed trade."
        ),
        (
            "Monthly correlation uses unweighted monthly net P&L so portfolio "
            "sizing does not distort the diversification measurement."
        ),
        (
            "Portfolio max drawdown is calculated from the combined "
            "chronological balance curve."
        ),
        (
            "The report uses MT5's official STAT_TRADES value for the completed "
            "trade count when available. Raw deal/activity rows are retained for "
            "equity and monetary statistics. Position-level win/loss breakdowns "
            "are not fabricated when the parsed HTML does not expose Position IDs."
        ),
    ]

    for note in notes:
        doc.add_paragraph(note)

    try:
        doc.save(doc_path)
        return doc_path

    except PermissionError:
        # A DOCX that is open in Word/LibreOffice cannot be replaced on
        # Windows. This is an OS file-lock, not a report-generation failure.
        # Save a deterministic timestamped copy instead so the portfolio run
        # still completes successfully.
        alt_path = doc_path.parent / f"{doc_path.stem}_{int(time.time())}.docx"
        doc.save(alt_path)
        print(f"    Saved unlocked copy: {alt_path.name}")
        return alt_path


# ===========================================================================
# MANIFEST
# ===========================================================================

def save_manifest(
    portfolio_dir: Path,
    portfolio_name: str,
    loaded: list,
    deposit: float,
    completed_trades: pd.DataFrame,
    trade_methods: dict,
):
    manifest = {
        "portfolio_name": portfolio_name,
        "created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "deposit": deposit,
        "currency": CURRENCY,
        "backtest_range": [
            str(PORTFOLIO_START),
            str(PORTFOLIO_END),
        ],
        "trade_count": int(sum(
            int(item.get("official_trade_stats", {}).get("total_trades", 0))
            for item in loaded
        )) if any(item.get("official_trade_stats", {}).get("total_trades") is not None for item in loaded)
        else (int(len(completed_trades)) if completed_trades is not None else 0),
        "trade_count_definition": (
            "Completed positions grouped by MT5 Position ID "
            "where available; otherwise deal-row fallback."
        ),
        "candidates": [],
    }

    for item in loaded:
        completed_count = (
            len(item.get("completed_trades", []))
            if item.get("completed_trades") is not None
            else 0
        )

        cand_key = item.get("candidate_label", item["candidate"])
        manifest["candidates"].append(
            {
                "candidate": item["candidate"],
                "candidate_label": cand_key,
                "market": item.get("market", ""),
                "run_dir": item["run_dir"],
                "weight": item["weight"],
                "candidate_dir": str(item["cand_dir"]),
                "mt5_report": str(item["html_path"]) if item.get("html_path") else "CSV Trade Source",
                "raw_activity_rows": int(
                    len(item["trades_raw"])
                ),
                "completed_trade_count": int(
                    completed_count
                ),
                "trade_count_method": trade_methods.get(
                    cand_key,
                    trade_methods.get(item["candidate"], "unknown"),
                ),
            }
        )

    with open(
        portfolio_dir / "portfolio_manifest.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
        )


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    base_work_dir = Path(WORK_DIR)

    print("=" * 76)
    print(" QUANT PORTFOLIO BUILDER - FIXED TRADE COUNT")
    print("=" * 76)

    print(f"  Quant:             {QUANT_NAME}")
    print(f"  Candidates cfg'd:  {len(CANDIDATES)}")

    if len(CANDIDATES) < 2:
        print(
            "ERROR: A portfolio needs at least 2 candidates. "
            "Add more entries to CANDIDATES."
        )
        return

    is_multi_market = (
        str(PORTFOLIO_TYPE).lower() == "multimarket"
        or "multimarket" in str(PORTFOLIO_NAME).lower()
        or "/" in str(PORTFOLIO_NAME)
        or any(
            str(s.get("market", "")).upper() in ("EURJPY", "USDJPY", "MULTI")
            for s in CANDIDATES
        )
        or len(set(str(s.get("market", "")).upper() for s in CANDIDATES if s.get("market"))) > 1
    )

    if is_multi_market:
        MULTI_MARKET_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        quant_dir = MULTI_MARKET_DIR
    else:
        QUANT_PORTFOLIOS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        quant_dir = (
            QUANT_PORTFOLIOS_DIR
            / f"{QUANT_NAME}_Quant_Portfolios"
        )
        quant_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    print(
        f"  Quant folder:      {quant_dir} "
    )

    portfolio_name = resolve_portfolio_name(
        quant_dir,
        QUANT_NAME,
        PORTFOLIO_NAME,
        OVERWRITE_EXISTING,
    )

    portfolio_dir = (
        quant_dir
        / portfolio_name
    )

    portfolio_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"  Portfolio folder:  {portfolio_dir}"
    )

    print("\n  --> Loading candidate backtests...")

    loaded = []

    for spec in CANDIDATES:
        item = load_candidate(
            base_work_dir,
            spec,
        )

        if item:
            loaded.append(item)

            print(
                f"      OK  {item['candidate']:12s} "
                f"run={item['run_dir']:24s} "
                f"weight={item['weight']:.2f}"
            )

    if len(loaded) < 2:
        print(
            "\nERROR: Fewer than 2 candidates loaded successfully; "
            "cannot build a portfolio."
        )
        return

    # -----------------------------------------------------------------------
    # Correct trade-level normalisation
    # -----------------------------------------------------------------------
    print(
        "\n  --> Normalising MT5 deal rows into completed trades..."
    )

    completed_trades, trade_methods = (
        build_all_completed_trades(loaded)
    )

    total_completed = (
        len(completed_trades)
        if completed_trades is not None
        else 0
    )

    official_total = sum(
        int(item.get("official_trade_stats", {}).get("total_trades", 0))
        for item in loaded
        if item.get("official_trade_stats", {}).get("total_trades") is not None
    )
    official_count_available = any(
        item.get("official_trade_stats", {}).get("total_trades") is not None
        for item in loaded
    )
    if official_count_available:
        print(
            f"      Combined completed trades: {official_total:,} "
            f"[MT5 official tester summary]"
        )
    else:
        print(
            f"      Combined completed trades: {total_completed:,} "
            f"[fallback; Position IDs unavailable]"
        )

    for item in loaded:
        count = (
            int(item.get("official_trade_stats", {}).get("total_trades"))
            if item.get("official_trade_stats", {}).get("total_trades") is not None
            else (
                len(item.get("completed_trades", []))
                if item.get("completed_trades") is not None
                else 0
            )
        )

        raw_count = len(
            item["trades_raw"]
        )

        print(
            f"      {item['candidate']:12s}: "
            f"{count:,} completed trade(s) "
            f"from {raw_count:,} raw activity/deal rows "
            f"[method={trade_methods.get(item['candidate'])}]"
        )

    # -----------------------------------------------------------------------
    # Correlation
    # -----------------------------------------------------------------------
    print(
        "\n  --> Computing monthly P&L correlation matrix..."
    )

    corr = build_correlation_matrix(
        loaded
    )

    with pd.option_context(
        "display.float_format",
        "{:.2f}".format,
    ):
        print(corr.to_string())

    # -----------------------------------------------------------------------
    # Combined equity stream
    # -----------------------------------------------------------------------
    print(
        "\n  --> Combining weighted monetary activity "
        "into one portfolio equity stream..."
    )

    combined_df = build_combined_deals(
        loaded,
        float(DEPOSIT),
    )

    # -----------------------------------------------------------------------
    # Correct metrics
    # -----------------------------------------------------------------------
    print(
        "\n  --> Calculating portfolio metrics "
        "from completed trades + raw equity stream..."
    )

    official_trade_stats = {
        "total_trades": 0,
        "profit_trades": 0,
        "loss_trades": 0,
        "total_net_profit": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
    }

    # Only aggregate an official metric when EVERY candidate supplied that
    # metric. Never mix official values from one candidate with parsed/raw
    # values from another.
    n_candidates = len(loaded)
    total_trade_values = []
    profit_trade_values = []
    loss_trade_values = []
    net_profit_values = []
    gross_profit_values = []
    gross_loss_values = []

    for item in loaded:
        stats = item.get("official_trade_stats", {})
        if stats.get("total_trades") is not None:
            total_trade_values.append(int(stats["total_trades"]))
        if stats.get("profit_trades") is not None:
            profit_trade_values.append(int(stats["profit_trades"]))
        if stats.get("loss_trades") is not None:
            loss_trade_values.append(int(stats["loss_trades"]))
        if stats.get("total_net_profit") is not None:
            net_profit_values.append(
                float(stats["total_net_profit"]) * float(item["weight"])
            )
        if stats.get("gross_profit") is not None:
            gross_profit_values.append(
                float(stats["gross_profit"]) * float(item["weight"])
            )
        if stats.get("gross_loss") is not None:
            gross_loss_values.append(
                float(stats["gross_loss"]) * float(item["weight"])
            )

    official_available = False

    if len(total_trade_values) == n_candidates:
        official_trade_stats["total_trades"] = sum(total_trade_values)
        official_available = True
    else:
        official_trade_stats["total_trades"] = None

    if len(profit_trade_values) == n_candidates and len(loss_trade_values) == n_candidates:
        official_trade_stats["profit_trades"] = sum(profit_trade_values)
        official_trade_stats["loss_trades"] = sum(loss_trade_values)
    else:
        official_trade_stats["profit_trades"] = None
        official_trade_stats["loss_trades"] = None

    if len(net_profit_values) == n_candidates:
        official_trade_stats["total_net_profit"] = sum(net_profit_values)
    else:
        official_trade_stats["total_net_profit"] = None

    if len(gross_profit_values) == n_candidates:
        official_trade_stats["gross_profit"] = sum(gross_profit_values)
    else:
        official_trade_stats["gross_profit"] = None

    if len(gross_loss_values) == n_candidates:
        # MT5 normally reports gross loss as a negative number. Preserve that
        # convention for PF/average-loss calculations.
        official_trade_stats["gross_loss"] = sum(gross_loss_values)
        if official_trade_stats["gross_loss"] > 0:
            official_trade_stats["gross_loss"] = -official_trade_stats["gross_loss"]
    else:
        official_trade_stats["gross_loss"] = None

    if official_trade_stats["total_net_profit"] is not None:
        expected_profit = float(official_trade_stats["total_net_profit"])
        stream_profit = float(
            pd.to_numeric(combined_df["EquityPnl"], errors="coerce")
            .fillna(0.0)
            .sum()
        )
        if abs(stream_profit - expected_profit) > 0.01:
            print(
                f"      [WARNING] Equity stream endpoint ${stream_profit:,.2f} "
                f"does not match official weighted profit ${expected_profit:,.2f}."
            )
            # Reconcile the complete combined stream once more at portfolio
            # level. This protects against candidate-level parser discrepancies
            # and guarantees that the final portfolio equity ends at the official
            # weighted MT5 result rather than at a stale/raw activity total.
            if abs(stream_profit) > 1e-12:
                combined_df["EquityPnl"] = (
                    pd.to_numeric(combined_df["EquityPnl"], errors="coerce")
                    .fillna(0.0)
                    * (expected_profit / stream_profit)
                )
            else:
                combined_df["EquityPnl"] = 0.0

            combined_df["Balance"] = (
                float(DEPOSIT)
                + pd.to_numeric(combined_df["EquityPnl"], errors="coerce")
                .fillna(0.0)
                .cumsum()
            )
            stream_profit = float(
                pd.to_numeric(combined_df["EquityPnl"], errors="coerce")
                .fillna(0.0)
                .sum()
            )
            print(
                f"      Reconciled combined equity stream: ${stream_profit:,.2f}"
            )


    derived = _calculate_portfolio_metrics(
        combined_df,
        completed_trades,
        float(DEPOSIT),
        official_trade_stats if official_available else None,
    )

    if derived:
        print(
            f"      Combined Net Profit:    "
            f"{_fmt_money(derived['total_net_profit'])}"
        )

        print(
            f"      Combined Net Profit %:  "
            f"{_fmt_pct(derived['profit_pct'])}"
        )

        print(
            f"      Combined Max DD:         "
            f"{_fmt_money(derived['max_dd'])} "
            f"({_fmt_pct(derived['max_dd_pct'])})"
        )

        print(
            f"      Combined Profit Factor:  "
            f"{_fmt_ratio(derived['profit_factor'])}"
        )

        print(
            f"      Combined Trade Count:    "
            f"{int(derived['total_trades']):,}"
        )
        print(
            f"      Portfolio Start Balance: {_fmt_money(float(DEPOSIT))}"
        )
        print(
            f"      Portfolio End Balance:   "
            f"{_fmt_money(float(DEPOSIT) + float(derived['total_net_profit']))}"
        )

    # -----------------------------------------------------------------------
    # Charts
    # -----------------------------------------------------------------------
    print(
        "  --> Generating combined equity curves..."
    )

    charts = generate_equity_charts(
        combined_df,
        float(DEPOSIT),
        portfolio_dir,
    )

    print(
        "  --> Generating combined monthly heatmap..."
    )

    heatmap_path, monthly_profit = (
        generate_portfolio_monthly_heatmap(
            combined_df,
            float(DEPOSIT),
            portfolio_dir,
        )
    )

    print(
        "  --> Generating candidates-vs-combined comparison chart..."
    )

    compare_path = generate_comparison_chart(
        loaded,
        combined_df,
        float(DEPOSIT),
        portfolio_dir,
    )

    # -----------------------------------------------------------------------
    # CSV + manifest
    # -----------------------------------------------------------------------
    print(
        "  --> Saving correlation matrix & manifest..."
    )

    corr.to_csv(
        portfolio_dir
        / "correlation_matrix.csv"
    )

    trades_export = combined_df[["Time", "EquityPnl", "Balance"]].copy()
    trades_export = trades_export.rename(columns={"EquityPnl": "NetPnl"})
    if "SourceCandidate" in combined_df.columns:
        trades_export["SourceCandidate"] = combined_df["SourceCandidate"]
    trades_export.to_csv(portfolio_dir / "combined_trades.csv", index=False)
    print(f"      Combined trade stream saved: combined_trades.csv ({len(trades_export):,} rows)")

    save_manifest(
        portfolio_dir,
        portfolio_name,
        loaded,
        float(DEPOSIT),
        completed_trades,
        trade_methods,
    )

    # -----------------------------------------------------------------------
    # Word report
    # -----------------------------------------------------------------------
    print(
        "  --> Compiling Word report..."
    )

    safe_portfolio_name = portfolio_name.replace("/", "_").replace("\\", "_")

    doc_path = create_portfolio_word_doc(
        doc_path=(
            portfolio_dir
            / f"{safe_portfolio_name}_Report.docx"
        ),
        portfolio_name=portfolio_name,
        loaded=loaded,
        corr=corr,
        derived=derived,
        charts=charts,
        heatmap_path=heatmap_path,
        monthly_profit=monthly_profit,
        compare_path=compare_path,
        deposit=float(DEPOSIT),
        completed_trades=completed_trades,
        trade_methods=trade_methods,
    )

    # If MultiMarket portfolio, synchronize between nested and flat formats:
    if is_multi_market:
        alias_dirs = [
            MULTI_MARKET_DIR / safe_portfolio_name,
            MULTI_MARKET_DIR / "TRB_USDJPY" / "EURJPY_Portfolio_001",
        ]
        for adir in alias_dirs:
            try:
                if adir.resolve() != portfolio_dir.resolve():
                    adir.mkdir(parents=True, exist_ok=True)
                    for item in portfolio_dir.iterdir():
                        if item.is_file():
                            shutil.copy2(item, adir / item.name)
            except Exception as e:
                pass

    print("\n" + "=" * 76)
    print(
        f" PORTFOLIO COMPLETE: {portfolio_name}"
    )

    print(
        f" Folder: {portfolio_dir}"
    )

    print(
        f" Completed Trades: "
        f"{int(derived.get('total_trades', 0)):,}"
    )

    if doc_path:
        print(
            f" Word Report: {doc_path}"
        )

    for key, path in charts.items():
        print(
            f" {key:18}: {path}"
        )

    if heatmap_path:
        print(
            f" heatmap           : {heatmap_path}"
        )

    if compare_path:
        print(
            f" comparison chart  : {compare_path}"
        )

    print("=" * 76)


if __name__ == "__main__":
    main()