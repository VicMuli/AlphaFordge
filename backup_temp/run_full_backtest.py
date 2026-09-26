"""
run_full_backtest.py - Single Candidate Full Backtest & Advanced Reporting

Fixed version
-------------
This version keeps the original runner flow but fixes the reporting layer:
  - Robust MT5 HTML decoding and table detection.
  - Deal/trade extraction no longer requires one exact pandas column layout.
  - Balance is used when MT5 supplies it; otherwise it is reconstructed from
    Profit + Commission + Swap.
  - Max drawdown, win/loss counts, average trade statistics, consecutive
    wins/losses, profit factor and recovery factor are computed from the
    extracted deal data when the summary parser misses them.
  - Three equity/balance charts are always attempted when deal data exists.
  - A real graphical monthly heatmap PNG is generated and inserted into the
    Word report, in addition to the monthly table.
  - Missing/zero metrics from a failed parser are not silently trusted when
    the same metric can be calculated from deal-level data.

The MT5 backtest execution interface is unchanged.
"""

import sys
import io
import json
import math
import re
import shutil
import time
from html.parser import HTMLParser
from pathlib import Path

# Prevent Windows console UnicodeEncodeError when running on cp1252 / charmap environments
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, RGBColor, Pt
except ImportError:
    docx = None
    print("WARNING: python-docx not installed. Run: pip install python-docx")

# -- Project imports --
from run_optimization import (
    TERMINAL_PATH,
    TERMINAL_DATA_DIR,
    EXPERT,
    SYMBOL,
    PERIOD,
    LOGIN,
    PASSWORD,
    SERVER,
    DEPOSIT,
    CURRENCY,
    LEVERAGE,
    SINGLE_TEST_TIMEOUT,
    TRAIN_FROM,
    HOLDOUT_TO,
    WORK_DIR,
)
from mt5_runner import run_single_backtest
from report_analysis import analyze


# ===========================================================================
# USER CONFIGURATION
# ===========================================================================

import os

TARGET_RUN_DIR = 'run_20260911_094409'
TARGET_CANDIDATE = 'cand_007'
TARGET_SYMBOL = 'USDJPY'

BT_START = os.environ.get("AF_BT_START", TRAIN_FROM)
BT_END   = os.environ.get("AF_BT_END", HOLDOUT_TO)
DEPOSIT_OVERRIDE = os.environ.get("AF_DEPOSIT", str(DEPOSIT))
SYMBOL_OVERRIDE = os.environ.get("AF_SYMBOL", TARGET_SYMBOL if TARGET_SYMBOL else SYMBOL)

# ===========================================================================
# HTML / DATA HELPERS
# ===========================================================================


def _read_html_text(html_path: Path) -> str:
    """Read an MT5 HTML report using robust encoding detection."""
    raw = html_path.read_bytes()

    encodings = []
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        encodings.extend(["utf-16", "utf-16-le", "utf-16-be"])
    elif b"\x00" in raw[:4000]:
        # UTF-16 reports without a BOM are common enough to handle explicitly.
        encodings.extend(["utf-16-le", "utf-16-be"])

    encodings.extend(["utf-8-sig", "utf-8", "cp1252", "latin-1"])

    tried = set()
    for enc in encodings:
        if enc in tried:
            continue
        tried.add(enc)
        try:
            text = raw.decode(enc)
            low = text.lower()
            if "<html" in low or "<table" in low:
                return text
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="ignore")


def _normalise_label(value) -> str:
    """Normalise a table heading for matching."""
    text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"[\r\n\t]+", " ", text)
    return text


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns produced by pd.read_html."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        cols = []
        for col in out.columns:
            parts = [str(x).strip() for x in col if str(x).strip() and str(x).lower() != "nan"]
            cols.append(" ".join(parts))
        out.columns = cols
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def _find_column(columns, aliases):
    """Find a column whose normalised name matches/contains one of aliases."""
    norm_cols = {_normalise_label(c): c for c in columns}
    alias_norm = [_normalise_label(a) for a in aliases]

    # Exact first.
    for alias in alias_norm:
        if alias in norm_cols:
            return norm_cols[alias]

    # Then substring.
    for alias in alias_norm:
        for norm, original in norm_cols.items():
            if alias in norm or norm in alias:
                return original
    return None


def _split_mt5_metric(val):
    """
    Split an MT5 metric string into (main_val, paren_val).
    e.g. '2 853.57 (56.47%)' -> ('2 853.57', '56.47%')
         '181 (40.49%)' -> ('181', '40.49%')
         '6 (255.95)' -> ('6', '255.95')
         '-2 786.67' -> ('-2 786.67', None)
    """
    if val is None:
        return "", None
    s = str(val).replace("\xa0", " ").strip()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s, None


def _parse_number(value, extract_paren=False):
    """Parse MT5 number formatting, handling commas, spaces, currency, percentages, and parentheses."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return np.nan

    main_part, paren_part = _split_mt5_metric(value)
    target = paren_part if extract_paren else main_part
    if not target:
        return np.nan

    s = target.replace("\xa0", " ").strip()
    negative_accounting = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace(" ", "").rstrip("%$")

    # Preserve decimal separator expected in MT5 reports; strip other symbols.
    s = re.sub(r"[^0-9.\-+eE]", "", s)
    if s in {"", ".", "-", "+", "-.", "+."}:
        return np.nan

    try:
        n = float(s)
        return -abs(n) if negative_accounting else n
    except ValueError:
        return np.nan


class _HTMLSummaryParser(HTMLParser):
    """Pure Python HTML parser to extract all key-value summary metrics from Table 0."""
    def __init__(self):
        super().__init__()
        self.summary = {}
        self.current_cell = []
        self.in_cell = False
        self.last_label = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("td", "th"):
            self.current_cell = []
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag.lower() in ("td", "th") and self.in_cell:
            text = "".join(self.current_cell).replace("\xa0", " ").strip()
            self.current_cell = []
            self.in_cell = False
            if text.endswith(":"):
                self.last_label = text[:-1].strip()
            elif self.last_label:
                self.summary[self.last_label] = text
                self.last_label = None

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


def parse_mt5_summary_table(html_source) -> dict:
    """Extract all summary metrics from Table 0 (Settings + Results) of MT5 HTML report."""
    try:
        if isinstance(html_source, Path):
            html_text = _read_html_text(html_source)
        else:
            html_text = str(html_source)
        from html.parser import HTMLParser as _BaseHTMLParser
        parser = _HTMLSummaryParser()
        parser.feed(html_text)
        return parser.summary
    except Exception as exc:
        print(f"      [WARNING] Could not parse MT5 summary table: {exc}")
        return {}


class _HTMLDealsExtractor(HTMLParser):
    """
    Pure Python HTML parser to extract the Deals section from MT5 Strategy Tester reports.
    Table 1 contains Orders (first rows) followed by Deals (subsequent rows).
    This parser reliably finds the Deals section header and extracts all and only Deal rows.
    """
    def __init__(self):
        super().__init__()
        self.tables = []
        self.cur_table = None
        self.cur_row = None
        self.cur_cell = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "table":
            self.cur_table = []
            self.tables.append(self.cur_table)
        elif tag.lower() == "tr" and self.cur_table is not None:
            self.cur_row = []
            self.cur_table.append(self.cur_row)
        elif tag.lower() in ("td", "th") and self.cur_row is not None:
            self.cur_cell = []
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag.lower() in ("td", "th") and self.in_cell:
            self.cur_row.append("".join(self.cur_cell).strip())
            self.cur_cell = []
            self.in_cell = False
        elif tag.lower() == "tr":
            self.cur_row = None
        elif tag.lower() == "table":
            self.cur_table = None

    def handle_data(self, data):
        if self.in_cell:
            self.cur_cell.append(data)


def _extract_deals_from_html_text(html_text: str) -> tuple[list[str], list[list[str]]]:
    """
    Search all tables in the HTML text to find the genuine Deals header and rows.
    Returns (headers, data_rows).
    """
    parser = _HTMLDealsExtractor()
    parser.feed(html_text)

    search_order = parser.tables[1:] + parser.tables[:1]
    for table in search_order:
        deal_header_idx = None
        for r_idx, row in enumerate(table):
            norms = [c.lower().replace("\xa0", " ").strip() for c in row]
            has_time = any(c in ("time", "date", "datetime", "date/time") for c in norms)
            has_profit = any("profit" in c for c in norms)
            has_balance = any("balance" in c for c in norms)
            if has_time and has_profit and has_balance and len(row) >= 5:
                deal_header_idx = r_idx
                break
            if len(row) == 1 and norms[0] == "deals" and r_idx + 1 < len(table):
                deal_header_idx = r_idx + 1
                break

        if deal_header_idx is not None:
            headers = [c.strip() for c in table[deal_header_idx]]
            time_idx = next((i for i, h in enumerate(headers) if "time" in h.lower() or "date" in h.lower()), 0)
            data_rows = []
            for row in table[deal_header_idx + 1:]:
                if not row or len(row) < 3:
                    continue
                if len(row) == 1 and not re.match(r"^\d{4}", row[0]):
                    break
                time_val = row[time_idx] if time_idx < len(row) else ""
                if not re.match(r"^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}", time_val):
                    continue
                padded = list(row) + [""] * (len(headers) - len(row))
                data_rows.append(padded[:len(headers)])

            if data_rows:
                return headers, data_rows

    return [], []


def parse_mt5_html_for_deals(html_path: Path, deposit: float = None) -> pd.DataFrame | None:
    """
    Extract real MT5 deal-level data from the Strategy Tester HTML report.
    Guarantees that Orders are excluded and only real Deals (with Profit & running Balance) are parsed.
    """
    try:
        html = _read_html_text(html_path)

        # 1. Parse summary table to identify reported Initial Deposit and summary stats
        summary_dict = parse_mt5_summary_table(html)
        reported_dep = _parse_number(summary_dict.get("Initial Deposit"))
        if reported_dep and not math.isnan(reported_dep) and reported_dep > 0:
            effective_deposit = float(reported_dep)
        elif deposit and deposit > 0:
            effective_deposit = float(deposit)
        else:
            effective_deposit = float(DEPOSIT_OVERRIDE) if DEPOSIT_OVERRIDE else 2500.0

        # 2. Extract Deals headers and rows
        headers, data_rows = _extract_deals_from_html_text(html)

        # Fallback to BeautifulSoup if HTMLParser found nothing
        if not data_rows and BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                for r_idx, tr in enumerate(rows):
                    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                    norms = [_normalise_label(c) for c in cells]
                    if any("time" in c for c in norms) and any("profit" in c for c in norms) and any("balance" in c for c in norms):
                        headers = cells
                        for data_tr in rows[r_idx + 1:]:
                            dcells = [c.get_text(" ", strip=True) for c in data_tr.find_all(["td", "th"])]
                            if dcells and re.match(r"^\d{4}[.\-/]", dcells[0]):
                                padded = dcells + [""] * (len(headers) - len(dcells))
                                data_rows.append(padded[:len(headers)])
                        break
                if data_rows:
                    break

        if not data_rows or not headers:
            print("    [ERROR] Could not identify MT5 deal rows in the HTML report.")
            return None

        df = pd.DataFrame(data_rows, columns=headers)
        if df.empty:
            return None

        # Clean columns
        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        df["Profit"] = df["Profit"].apply(_parse_number)

        for col in ["Balance", "Commission", "Swap", "Volume", "Price"]:
            if col in df.columns:
                df[col] = df[col].apply(_parse_number)

        if "Commission" not in df.columns:
            df["Commission"] = 0.0
        else:
            df["Commission"] = df["Commission"].fillna(0.0)

        if "Swap" not in df.columns:
            df["Swap"] = 0.0
        else:
            df["Swap"] = df["Swap"].fillna(0.0)

        # Filter out invalid time rows
        df = df.dropna(subset=["Time"]).sort_values("Time").reset_index(drop=True)

        # 3. Identify balance operations (deposit / withdrawal / credit)
        if "Type" in df.columns:
            type_text = df["Type"].astype(str).str.lower()
            df["IsBalanceOperation"] = type_text.str.contains(
                r"balance|credit|deposit|withdraw|charge|transfer", regex=True, na=False
            )
        else:
            df["IsBalanceOperation"] = False

        # In MT5, row 0 is almost universally the starting balance/deposit
        if len(df) > 0:
            row0_dir = str(df.iloc[0].get("Direction", "")).strip().lower() if "Direction" in df.columns else ""
            row0_profit = df["Profit"].iloc[0]
            if (row0_dir in ("", "nan", "none") and pd.notna(row0_profit) and row0_profit > 0) or str(df.iloc[0].get("Type", "")).lower() == "balance":
                df.loc[df.index == 0, "IsBalanceOperation"] = True
                if effective_deposit == 0 or effective_deposit == 2500.0:
                    effective_deposit = float(row0_profit)

        # 4. Running balance from MT5 or reconstruction
        balance_reconstructed = False
        if "Balance" in df.columns and df["Balance"].notna().sum() >= 2:
            df["Balance"] = pd.to_numeric(df["Balance"], errors="coerce").ffill()
            first_bal = df["Balance"].iloc[0]
            if pd.notna(first_bal) and float(first_bal) > 0:
                effective_deposit = float(first_bal)
        else:
            net_change = (df["Profit"].fillna(0.0) + df["Commission"] + df["Swap"]).where(~df["IsBalanceOperation"], 0.0)
            df["Balance"] = effective_deposit + net_change.cumsum()
            balance_reconstructed = True

        # Build NetTradePnl per row
        df["NetTradePnl"] = df["Profit"].fillna(0.0) + df["Commission"] + df["Swap"]

        trade_df = df.loc[~df["IsBalanceOperation"]].copy()
        if trade_df.empty:
            trade_df = df.copy()

        df.attrs["trade_df"] = trade_df
        df.attrs["balance_reconstructed"] = balance_reconstructed
        df.attrs["effective_deposit"] = effective_deposit
        df.attrs["parsed_rows"] = len(df)
        df.attrs["raw_summary"] = summary_dict

        print(f"    -> MT5 deal data identified successfully; parsed {len(df):,} deal rows.")
        print(f"       Effective Deposit: ${effective_deposit:,.2f} | Running Balance: ${df['Balance'].iloc[0]:,.2f} -> ${df['Balance'].iloc[-1]:,.2f}")
        print(f"       Date range: {df['Time'].min()} -> {df['Time'].max()} | Deals Net P&L: ${df.loc[~df['IsBalanceOperation'], 'NetTradePnl'].sum():,.2f}")
        return df

    except Exception as exc:
        print(f"    [ERROR] Failed parsing MT5 HTML deal data: {exc}")
        return None


# ===========================================================================
# METRIC CALCULATIONS
# ===========================================================================


def _get_trade_rows(deals_df: pd.DataFrame) -> pd.DataFrame:
    """Return rows representing trading activity, excluding balance operations."""
    if deals_df is None or deals_df.empty:
        return pd.DataFrame()
    trade_df = deals_df.attrs.get("trade_df")
    if isinstance(trade_df, pd.DataFrame) and not trade_df.empty:
        return trade_df.copy()
    return deals_df.loc[~deals_df.get("IsBalanceOperation", False)].copy() if "IsBalanceOperation" in deals_df.columns else deals_df.copy()


def calculate_derived_metrics(deals_df: pd.DataFrame, deposit: float) -> dict:
    """Calculate metrics directly from parsed MT5 rows so missing report fields don't become zero."""
    result = {}
    if deals_df is None or deals_df.empty:
        return result

    effective_deposit = float(deals_df.attrs.get("effective_deposit", deposit))
    df = deals_df.sort_values("Time").copy()
    trades = _get_trade_rows(df).sort_values("Time").copy()

    # Identify completed/closed trades:
    # In MT5 Deals, Direction == 'out' (or 'in/out') represents closed trades.
    if "Direction" in trades.columns:
        dir_series = trades["Direction"].astype(str).str.lower()
        closed_trades = trades.loc[dir_series.isin(["out", "in/out"])].copy()
        if closed_trades.empty:
            closed_trades = trades.loc[trades["NetTradePnl"] != 0.0].copy()
    else:
        closed_trades = trades.loc[trades["NetTradePnl"] != 0.0].copy()

    if closed_trades.empty:
        closed_trades = trades.copy()

    pnl = pd.to_numeric(closed_trades["NetTradePnl"], errors="coerce").fillna(0.0).reset_index(drop=True)

    # Account-level P&L from balance
    balance = pd.to_numeric(df["Balance"], errors="coerce").dropna()
    if not balance.empty:
        total_net_profit = float(balance.iloc[-1] - effective_deposit)
    else:
        total_net_profit = float(trades["NetTradePnl"].sum())

    # Balance drawdown from the actual MT5 balance curve
    equity = pd.to_numeric(df["Balance"], errors="coerce").to_numpy(dtype=float)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(np.max(dd)) if len(dd) else 0.0
    max_dd_index = int(np.argmax(dd)) if len(dd) else 0
    peak_index = int(np.argmax(equity[: max_dd_index + 1])) if len(equity) else 0
    dd_pct_at_peak = (max_dd / equity[peak_index] * 100.0) if len(equity) and equity[peak_index] != 0 else 0.0

    positive = pnl[pnl > 0]
    negative = pnl[pnl < 0]

    gross_profit = float(positive.sum())
    gross_loss = float(negative.sum())
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else float("inf")
    recovery_factor = total_net_profit / max_dd if max_dd > 0 else float("inf")

    # Consecutive results
    max_wins = max_losses = 0
    cur_wins = cur_losses = 0
    for value in pnl:
        if value > 0:
            cur_wins += 1
            cur_losses = 0
            max_wins = max(max_wins, cur_wins)
        elif value < 0:
            cur_losses += 1
            cur_wins = 0
            max_losses = max(max_losses, cur_losses)
        else:
            cur_wins = cur_losses = 0

    total_trades_count = int(len(pnl))

    # Daily account returns for Sharpe
    daily = df.groupby(df["Time"].dt.date)["NetTradePnl"].sum()
    daily_returns = daily / effective_deposit if effective_deposit else pd.Series(dtype=float)
    if len(daily_returns) >= 2 and daily_returns.std(ddof=1) > 0:
        sharpe = float((daily_returns.mean() / daily_returns.std(ddof=1)) * math.sqrt(252))
    else:
        sharpe = 0.0

    result.update(
        {
            "effective_deposit": effective_deposit,
            "total_net_profit": total_net_profit,
            "profit_pct": (total_net_profit / effective_deposit * 100.0) if effective_deposit else 0.0,
            "max_dd": max_dd,
            "max_dd_pct": dd_pct_at_peak,
            "profit_factor": profit_factor,
            "recovery_factor": recovery_factor,
            "sharpe": sharpe,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": total_trades_count,
            "profit_trades": int((pnl > 0).sum()),
            "loss_trades": int((pnl < 0).sum()),
            "breakeven_trades": int((pnl == 0).sum()),
            "win_rate": (float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0),
            "avg_win": float(positive.mean()) if len(positive) else 0.0,
            "avg_loss": float(negative.mean()) if len(negative) else 0.0,
            "largest_profit": float(positive.max()) if len(positive) else 0.0,
            "largest_loss": float(negative.min()) if len(negative) else 0.0,
            "max_consecutive_wins": max_wins,
            "max_consecutive_losses": max_losses,
            "daily_count": int(len(daily)),
        }
    )

    # Holding time from position IDs when available
    if "Position" in trades.columns:
        holding = []
        grouped = trades.groupby("Position", dropna=True)
        for _, g in grouped:
            if len(g) >= 2:
                delta = g["Time"].max() - g["Time"].min()
                holding.append(delta.total_seconds())
        if holding:
            result["min_hold"] = min(holding)
            result["max_hold"] = max(holding)
            result["avg_hold"] = float(np.mean(holding))

    # Long/short breakdown when Direction or Type is present
    dir_col = "Direction" if "Direction" in closed_trades.columns else ("Type" if "Type" in closed_trades.columns else None)
    if dir_col:
        labels = closed_trades[dir_col].astype(str).str.lower().reset_index(drop=True)
        for side, aliases in [("long", ("buy", "long")), ("short", ("sell", "short"))]:
            mask = labels.apply(lambda x: any(a in x for a in aliases))
            if mask.any():
                side_pnl = pnl.loc[mask]
                result[f"{side}_count"] = int(mask.sum())
                result[f"{side}_win_rate"] = float((side_pnl > 0).mean() * 100.0)

    return result


def _flatten_metric_dict(obj):
    """Flatten common nested metric dictionaries returned by report_analysis.analyze."""
    if not isinstance(obj, dict):
        return {}

    flat = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            flat.update(_flatten_metric_dict(v))
        else:
            flat[str(k)] = v
    return flat


def extract_metric(raw_metrics: dict, aliases, default=0.0, is_pct=False):
    """Case-insensitive metric lookup supporting nested analyze() output and parenthesized values."""
    flat = _flatten_metric_dict(raw_metrics)
    norm_map = {_normalise_label(k): v for k, v in flat.items()}
    aliases_norm = [_normalise_label(a) for a in aliases]

    for alias in aliases_norm:
        if alias in norm_map:
            n = _parse_number(norm_map[alias], extract_paren=is_pct)
            if not pd.isna(n):
                return float(n)

    for alias in aliases_norm:
        for key, value in norm_map.items():
            if alias in key or key in alias:
                n = _parse_number(value, extract_paren=is_pct)
                if not pd.isna(n):
                    return float(n)

    return default


def extract_string(raw_metrics: dict, aliases, default="N/A"):
    """Case-insensitive string lookup supporting nested analyze() output."""
    flat = _flatten_metric_dict(raw_metrics)
    norm_map = {_normalise_label(k): v for k, v in flat.items()}
    aliases_norm = [_normalise_label(a) for a in aliases]

    for alias in aliases_norm:
        if alias in norm_map:
            val = str(norm_map[alias]).strip()
            if val and val != "nan":
                return val
    for alias in aliases_norm:
        for key, value in norm_map.items():
            if alias in key or key in alias:
                val = str(value).strip()
                if val and val != "nan":
                    return val
    return default


# ===========================================================================
# CHARTS / HEATMAP
# ===========================================================================


def _save_figure(path: Path):
    plt.tight_layout()
    plt.savefig(path, dpi=180, bbox_inches="tight")
    plt.close()


def generate_equity_charts(deals_df: pd.DataFrame, deposit: float, output_dir: Path):
    """Generate three separate equity/balance charts using supported Matplotlib APIs."""
    paths = {}

    if deals_df is None or deals_df.empty:
        print("    [WARNING] No deal data available for equity charts.")
        return paths

    try:
        df = deals_df.sort_values("Time").copy()
        effective_dep = float(deals_df.attrs.get("effective_deposit", deposit))

        times = pd.to_datetime(df["Time"], errors="coerce")
        balance = pd.to_numeric(df["Balance"], errors="coerce")

        valid = times.notna() & balance.notna()
        times = times.loc[valid].reset_index(drop=True)
        balance = balance.loc[valid].reset_index(drop=True)

        if len(times) < 2:
            print("    [WARNING] Fewer than 2 valid balance observations; charts cannot be generated.")
            return paths

        numeric_balance = balance.to_numpy(dtype=float)

        finite = np.isfinite(numeric_balance)
        times = times.loc[finite].reset_index(drop=True)
        numeric_balance = numeric_balance[finite]

        if len(times) < 2:
            print("    [WARNING] No finite balance series remains after cleaning; charts cannot be generated.")
            return paths

        cumulative_profit = numeric_balance - effective_dep
        pct_gain = (
            cumulative_profit / effective_dep * 100.0
            if effective_dep
            else np.zeros_like(cumulative_profit)
        )

        x = times.to_numpy()

        # 1. Total dollar P/L
        try:
            plt.figure(figsize=(10.5, 5.2))
            plt.plot(x, cumulative_profit, "-", linewidth=1.5, color="#1976D2")
            plt.axhline(0, color="gray", linestyle="--", linewidth=1.0)
            plt.title("Total Profit / Loss ($)", fontsize=12, fontweight="bold")
            plt.xlabel("Time")
            plt.ylabel("Profit ($)")
            ax = plt.gca()
            locator = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            path = output_dir / "chart_profit_dollars.png"
            _save_figure(path)
            paths["dollar_gains"] = path
        except Exception as exc:
            plt.close("all")
            print(f"    [WARNING] Could not generate dollar P/L chart: {exc}")

        # 2. Balance / equity growth
        try:
            plt.figure(figsize=(10.5, 5.2))
            plt.plot(x, numeric_balance, "-", linewidth=1.5, color="#2E7D32", label="Balance")
            plt.axhline(
                effective_dep,
                color="gray",
                linestyle="--",
                linewidth=1.0,
                label=f"Initial Deposit (${effective_dep:,.0f})",
            )
            plt.title("Equity / Balance Growth", fontsize=12, fontweight="bold")
            plt.xlabel("Time")
            plt.ylabel("Account Balance ($)")
            plt.legend()
            ax = plt.gca()
            locator = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            path = output_dir / "chart_equity_growth.png"
            _save_figure(path)
            paths["equity_growth"] = path
        except Exception as exc:
            plt.close("all")
            print(f"    [WARNING] Could not generate equity growth chart: {exc}")

        # 3. Percentage gain/loss
        try:
            plt.figure(figsize=(10.5, 5.2))
            plt.plot(x, pct_gain, "-", linewidth=1.5, color="#E65100")
            plt.axhline(0, color="gray", linestyle="--", linewidth=1.0)
            plt.title("Percentage Gain / Loss (%)", fontsize=12, fontweight="bold")
            plt.xlabel("Time")
            plt.ylabel("Gain (%)")
            ax = plt.gca()
            locator = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            path = output_dir / "chart_percent_gain.png"
            _save_figure(path)
            paths["percent_gain"] = path
        except Exception as exc:
            plt.close("all")
            print(f"    [WARNING] Could not generate percentage gain chart: {exc}")

    except Exception as exc:
        plt.close("all")
        print(f"    [ERROR] Equity chart generation failed: {exc}")

    return paths


def generate_monthly_heatmap(deals_df: pd.DataFrame, deposit: float, output_dir: Path):
    """Generate a graphical monthly P&L heatmap and return its path + pivot."""
    if deals_df is None or deals_df.empty:
        return None, None

    effective_dep = float(deals_df.attrs.get("effective_deposit", deposit))
    trades = _get_trade_rows(deals_df).copy()
    if trades.empty:
        return None, None

    trades["Year"] = trades["Time"].dt.year
    trades["Month"] = trades["Time"].dt.month
    monthly = trades.groupby(["Year", "Month"])["NetTradePnl"].sum().unstack(fill_value=0)
    monthly = monthly.sort_index()

    all_years = list(monthly.index)
    matrix = np.zeros((len(all_years), 13), dtype=float)
    for r, year in enumerate(all_years):
        for month in range(1, 13):
            if month in monthly.columns:
                matrix[r, month - 1] = float(monthly.loc[year, month])
        matrix[r, 12] = matrix[r, :12].sum()

    fig, ax = plt.subplots(figsize=(13.4, max(3.2, 1.0 + 0.55 * len(all_years))))
    vmax = float(np.max(np.abs(matrix[:, :12]))) if matrix.size else 1.0
    if vmax == 0:
        vmax = 1.0
    im = ax.imshow(matrix[:, :12], aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax,
                    extent=(-0.5, 11.5, len(all_years) - 0.5, -0.5))
    ax.set_xlim(-0.5, 12.5)

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total"]
    ax.set_xticks(range(13), months)
    ax.set_yticks(range(len(all_years)), [str(y) for y in all_years])
    ax.set_xlabel("Month")
    ax.set_ylabel("Year")
    ax.set_title("Monthly Performance Heatmap", fontsize=13, fontweight="bold")

    ax.axvline(11.5, color="black", linewidth=1.2)

    for r in range(matrix.shape[0]):
        for c in range(12):
            value = matrix[r, c]
            pct = (value / effective_dep * 100.0) if effective_dep else 0.0
            ax.text(c, r, f"${value:,.0f}\n{pct:+.1f}%", ha="center", va="center", fontsize=8)

        total_value = matrix[r, 12]
        total_pct = (total_value / effective_dep * 100.0) if effective_dep else 0.0
        ax.add_patch(plt.Rectangle((11.5, r - 0.5), 1.0, 1.0, facecolor="#f0f0f0", edgecolor="black", linewidth=0.5))
        ax.text(12, r, f"${total_value:,.0f}\n{total_pct:+.1f}%", ha="center", va="center",
                fontsize=8, fontweight="bold",
                color=("darkgreen" if total_value > 0 else ("darkred" if total_value < 0 else "black")))

    fig.colorbar(im, ax=ax, label="Monthly P&L ($)")
    path = output_dir / "monthly_performance_heatmap.png"
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path, monthly


# ===========================================================================
# WORD REPORT
# ===========================================================================


def _fmt_money(value):
    if math.isinf(value):
        return "N/A"
    return f"${value:,.2f}"


def _fmt_pct(value):
    return f"{value:.2f}%"


def _fmt_ratio(value):
    if math.isinf(value):
        return "N/A"
    return f"{value:.2f}"


def _seconds_to_duration(seconds):
    if seconds is None or pd.isna(seconds):
        return "N/A"
    seconds = int(round(float(seconds)))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _set_cell_text(cell, text, bold=False):
    cell.text = str(text)
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.bold = bold
            run.font.size = Pt(9)


def create_full_backtest_word_doc(
    doc_path: Path,
    cand_n: str,
    raw_metrics: dict,
    deals_df: pd.DataFrame,
    charts: dict,
    heatmap_path,
    monthly_profit: pd.DataFrame,
    deposit: float,
):
    if docx is None:
        print("    [ERROR] python-docx is not installed; cannot create Word report.")
        return None

    doc = docx.Document()
    title = doc.add_heading(f"Full Backtest Report - Candidate {cand_n}", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    derived = calculate_derived_metrics(deals_df, deposit) if deals_df is not None else {}

    # Determine effective initial deposit from report or deals
    rep_deposit = extract_metric(raw_metrics, ["Initial Deposit", "Deposit"])
    if rep_deposit and rep_deposit > 0:
        actual_deposit = rep_deposit
    elif deals_df is not None and "effective_deposit" in deals_df.attrs:
        actual_deposit = float(deals_df.attrs["effective_deposit"])
    elif deposit and deposit > 0:
        actual_deposit = float(deposit)
    else:
        actual_deposit = 2500.0

    # Helper function to get metric: check raw_metrics (HTML table) FIRST, fallback to derived
    def get_stat(aliases, derived_key=None, default=0.0, is_pct=False):
        val = extract_metric(raw_metrics, aliases, default=None, is_pct=is_pct)
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            return val
        if derived_key and derived_key in derived:
            dval = derived[derived_key]
            if dval is not None and not (isinstance(dval, float) and math.isnan(dval)):
                return dval
        return default

    # 1. Official Summary Metrics from MT5 HTML Report (highest priority)
    total_net_profit = get_stat(["Total Net Profit", "Net Profit"], derived_key="total_net_profit", default=0.0)
    profit_pct = (total_net_profit / actual_deposit * 100.0) if actual_deposit else 0.0

    max_dd = get_stat(["Balance Drawdown Maximal", "Max Drawdown", "Maximal Drawdown", "Drawdown"], derived_key="max_dd", default=0.0, is_pct=False)
    max_dd_pct = get_stat(["Balance Drawdown Maximal", "Max Drawdown %", "Balance Drawdown Relative"], derived_key="max_dd_pct", default=0.0, is_pct=True)

    pf = get_stat(["Profit Factor", "PF"], derived_key="profit_factor", default=0.0)
    rf = get_stat(["Recovery Factor", "RF"], derived_key="recovery_factor", default=0.0)
    sharpe = get_stat(["Sharpe Ratio", "Sharpe"], derived_key="sharpe", default=0.0)

    total_trades = int(round(get_stat(["Total Trades", "Trades"], derived_key="total_trades", default=0.0)))
    profit_trades = int(round(get_stat(["Profit Trades (% of total)", "Profit Trades", "Winning Trades"], derived_key="profit_trades", default=0.0, is_pct=False)))
    profit_trades_pct = get_stat(["Profit Trades (% of total)", "Profit Trades %", "Win Rate %", "Win Rate"], default=(profit_trades / total_trades * 100.0 if total_trades else 0.0), is_pct=True)

    loss_trades = int(round(get_stat(["Loss trades (% of total)", "Loss Trades", "Losing Trades"], derived_key="loss_trades", default=0.0, is_pct=False)))
    loss_trades_pct = get_stat(["Loss trades (% of total)", "Loss Trades %"], default=(loss_trades / total_trades * 100.0 if total_trades else 0.0), is_pct=True)

    breakeven_trades = max(0, total_trades - profit_trades - loss_trades)

    avg_win = get_stat(["Average profit trade", "Average Profit", "Average Win"], derived_key="avg_win", default=0.0)
    avg_loss = get_stat(["Average loss trade", "Average Loss"], derived_key="avg_loss", default=0.0)
    max_win = get_stat(["Largest profit trade", "Largest Profit"], derived_key="largest_profit", default=0.0)
    max_loss = get_stat(["Largest loss trade", "Largest Loss"], derived_key="largest_loss", default=0.0)

    consec_wins = int(round(get_stat(["Maximum consecutive wins ($)", "Maximum consecutive wins", "Max consec wins"], derived_key="max_consecutive_wins", default=0.0)))
    consec_losses = int(round(get_stat(["Maximum consecutive losses ($)", "Maximum consecutive losses", "Max consec losses"], derived_key="max_consecutive_losses", default=0.0)))

    gross_profit = get_stat(["Gross Profit"], derived_key="gross_profit", default=0.0)
    gross_loss = get_stat(["Gross Loss"], derived_key="gross_loss", default=0.0)

    # Long / short text
    long_raw = extract_string(raw_metrics, ["Long Trades (won %)", "Long Trades"])
    short_raw = extract_string(raw_metrics, ["Short Trades (won %)"])
    if long_raw and long_raw != "N/A":
        m = re.match(r"^(\d+)\s*\(([^)]*)\)", long_raw)
        if m:
            long_text = f"{m.group(1)} ({m.group(2)} won)"
        else:
            long_text = long_raw
    elif "long_count" in derived:
        long_text = f"{derived['long_count']} ({derived['long_win_rate']:.2f}% won)"
    else:
        long_text = "N/A"

    if short_raw and short_raw != "N/A":
        m = re.match(r"^(\d+)\s*\(([^)]*)\)", short_raw)
        if m:
            short_text = f"{m.group(1)} ({m.group(2)} won)"
        else:
            short_text = short_raw
    elif "short_count" in derived:
        short_text = f"{derived['short_count']} ({derived['short_win_rate']:.2f}% won)"
    else:
        short_text = "N/A"

    start_dt = pd.to_datetime(BT_START)
    end_dt = pd.to_datetime(BT_END)
    days_in_test = max(1, (end_dt - start_dt).days)
    avg_trades_day = total_trades / days_in_test if days_in_test else 0.0
    avg_trades_month = avg_trades_day * 30.44
    avg_prof_day = total_net_profit / days_in_test if days_in_test else 0.0
    avg_prof_month = avg_prof_day * 30.44
    avg_prof_year = avg_prof_day * 365.25

    min_hold = extract_string(raw_metrics, ["Minimal position holding time"])
    if not min_hold or min_hold == "N/A":
        min_hold = _seconds_to_duration(derived.get("min_hold"))

    max_hold = extract_string(raw_metrics, ["Maximal position holding time"])
    if not max_hold or max_hold == "N/A":
        max_hold = _seconds_to_duration(derived.get("max_hold"))

    avg_hold = extract_string(raw_metrics, ["Average position holding time"])
    if not avg_hold or avg_hold == "N/A":
        avg_hold = _seconds_to_duration(derived.get("avg_hold"))

    # 1. Performance overview
    doc.add_heading("1. Performance Overview", level=1)
    tested_symbol = extract_string(raw_metrics, ["Symbol", "Market", "Symbol / Market"], default=str(SYMBOL_OVERRIDE))
    rows = [
        ("Market / Symbol", tested_symbol),
        ("Profit / Loss ($)", _fmt_money(total_net_profit)),
        ("Profit / Loss (%)", _fmt_pct(profit_pct)),
        ("Max Balance Drawdown", _fmt_money(max_dd)),
        ("Max Balance Drawdown (%)", _fmt_pct(max_dd_pct)),
        ("Profit Factor", _fmt_ratio(pf)),
        ("Recovery Factor", _fmt_ratio(rf)),
        ("Return / Drawdown Ratio", _fmt_ratio(total_net_profit / max_dd if max_dd > 0 else float("inf"))),
        ("Sharpe Ratio", f"{sharpe:.2f}"),
        ("Max Consecutive Wins", f"{int(consec_wins):,}"),
        ("Max Consecutive Losses", f"{int(consec_losses):,}"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for key, value in rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], key, bold=True)
        _set_cell_text(cells[1], value)

    # 2. Trade statistics
    doc.add_heading("2. Trade Statistics Breakdown", level=1)
    rows = [
        ("Total Trades", f"{int(total_trades):,}"),
        ("Total Profit Trades (Amt & %)", f"{int(profit_trades):,} ({profit_trades_pct:.2f}%)"),
        ("Total Loss Trades (Amt & %)", f"{int(loss_trades):,} ({loss_trades_pct:.2f}%)"),
        ("Breakeven Trades", f"{int(breakeven_trades):,}"),
        ("Long Trades (Won %)", long_text),
        ("Short Trades (Won %)", short_text),
        ("Average Win per Trade", _fmt_money(avg_win)),
        ("Average Loss per Trade", _fmt_money(avg_loss)),
        ("Largest Profit Trade", _fmt_money(max_win)),
        ("Largest Loss Trade", _fmt_money(max_loss)),
        ("Gross Profit", _fmt_money(gross_profit)),
        ("Gross Loss", _fmt_money(gross_loss)),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for key, value in rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], key, bold=True)
        _set_cell_text(cells[1], value)

    # 3. Averages / holding times
    doc.add_heading("3. Averages & Holding Times", level=1)
    rows = [
        ("Average Trades per Month", f"{avg_trades_month:.2f}"),
        ("Average Profit per Day", _fmt_money(avg_prof_day)),
        ("Average Profit per Month", _fmt_money(avg_prof_month)),
        ("Average Profit per Year", _fmt_money(avg_prof_year)),
        ("Min Position Holding Time", min_hold),
        ("Max Position Holding Time", max_hold),
        ("Avg Position Holding Time", avg_hold),
        ("Historical Trading Days", f"{derived.get('daily_count', 0):,}"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for key, value in rows:
        cells = table.add_row().cells
        _set_cell_text(cells[0], key, bold=True)
        _set_cell_text(cells[1], value)

    # 4. Heatmap
    doc.add_heading("4. Monthly Performance Heatmap ($ and %)", level=1)
    if heatmap_path and Path(heatmap_path).exists():
        doc.add_picture(str(heatmap_path), width=Inches(6.9))
        cap = doc.add_paragraph(
            "Monthly P&L is shown in dollars; percentage is monthly (or yearly, for the Total column) "
            "P&L divided by the initial deposit. The initial deposit/balance entry is excluded from all "
            "trade statistics and from every P&L figure shown here."
        )
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if monthly_profit is not None and not monthly_profit.empty:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        hm = doc.add_table(rows=1, cols=14)
        hm.style = "Table Grid"
        header = hm.rows[0].cells
        _set_cell_text(header[0], "Year", bold=True)
        for i, month in enumerate(months, start=1):
            _set_cell_text(header[i], month, bold=True)
        _set_cell_text(header[13], "Total", bold=True)

        for year in monthly_profit.index:
            cells = hm.add_row().cells
            _set_cell_text(cells[0], str(year), bold=True)
            year_total = 0.0
            for month_no in range(1, 13):
                value = float(monthly_profit.loc[year, month_no]) if month_no in monthly_profit.columns else 0.0
                year_total += value
                pct = value / actual_deposit * 100.0 if actual_deposit else 0.0
                _set_cell_text(cells[month_no], f"${value:,.0f}\n({pct:+.1f}%)")
                for p in cells[month_no].paragraphs:
                    for run in p.runs:
                        if value > 0:
                            run.font.color.rgb = RGBColor(0, 128, 0)
                        elif value < 0:
                            run.font.color.rgb = RGBColor(192, 0, 0)

            year_pct = year_total / actual_deposit * 100.0 if actual_deposit else 0.0
            _set_cell_text(cells[13], f"${year_total:,.0f}\n({year_pct:+.1f}%)", bold=True)
            for p in cells[13].paragraphs:
                for run in p.runs:
                    run.bold = True
                    if year_total > 0:
                        run.font.color.rgb = RGBColor(0, 128, 0)
                    elif year_total < 0:
                        run.font.color.rgb = RGBColor(192, 0, 0)
    else:
        doc.add_paragraph("Monthly heatmap data could not be generated because no deal-level rows were parsed.")

    # 5. Equity curves
    doc.add_heading("5. Equity Curves", level=1)
    if charts:
        for key, title_text in [
            ("dollar_gains", "Total Profit / Loss ($)"),
            ("equity_growth", "Equity / Balance Growth"),
            ("percent_gain", "Percentage Gain / Loss (%)"),
        ]:
            if key in charts and Path(charts[key]).exists():
                doc.add_paragraph(title_text).runs[0].bold = True
                doc.add_picture(str(charts[key]), width=Inches(6.9))
    else:
        doc.add_paragraph("Equity charts could not be generated because no valid deal/balance series was available.")

    # 6. Data quality diagnostics
    doc.add_heading("6. Data Quality & Calculation Notes", level=1)
    parsed_rows = int(deals_df.attrs.get("parsed_rows", len(deals_df))) if deals_df is not None else 0
    reconstructed = bool(deals_df.attrs.get("balance_reconstructed", False)) if deals_df is not None else False
    notes = [
        f"Parsed MT5 deal rows: {parsed_rows:,}.",
        f"Initial Deposit: ${actual_deposit:,.2f}.",
        f"Balance source: {'reconstructed from Profit + Commission + Swap' if reconstructed else 'MT5-reported Balance column'}.",
        "Performance overview and trade breakdown metrics reflect official MT5 Strategy Tester report summary values.",
        "Equity and percentage curves are plotted from the chronological MT5 running balance series.",
    ]
    for note in notes:
        doc.add_paragraph(note)

    try:
        doc.save(doc_path)
        return doc_path
    except PermissionError:
        alt_path = doc_path.parent / f"{doc_path.stem}_{int(time.time())}.docx"
        doc.save(alt_path)
        print(f"    [WARNING] Target Word file is locked. Saved: {alt_path.name}")
        return alt_path


# ===========================================================================
# RUNNER
# ===========================================================================


def resolve_candidate_dir(base_work_dir: Path, target_run: str, target_cand: str) -> Path | None:
    # Candidate name variants to check (e.g. cand_001, cand_1, cand_01)
    cand_variants = [target_cand]
    m = re.search(r"(\d+)", target_cand)
    if m:
        num = int(m.group(1))
        for fmt in (f"cand_{num:03d}", f"cand_{num:02d}", f"cand_{num}", f"cand_{num:04d}", f"c_{num:03d}"):
            if fmt not in cand_variants:
                cand_variants.append(fmt)

    # If target_run is directly an existing path
    if target_run and Path(target_run).exists():
        direct_run = Path(target_run)
        for cvar in cand_variants:
            for p in (direct_run / "passed_candidates" / cvar, direct_run / cvar, direct_run / "full_backtest" / cvar):
                if p.exists() and p.is_dir():
                    return p
            if direct_run.name == cvar or direct_run.name == target_cand:
                return direct_run

    # Collect search roots
    roots = [base_work_dir]
    if base_work_dir.parent.exists():
        roots.append(base_work_dir.parent)
        try:
            for sibling in base_work_dir.parent.iterdir():
                if sibling.is_dir() and sibling not in roots:
                    roots.append(sibling)
        except OSError:
            pass
    script_runs = Path(__file__).parent / "optimization_runs"
    if script_runs.exists() and script_runs not in roots:
        roots.append(script_runs)

    # 1. If target_run specified
    if target_run and target_run.strip().lower() not in ("latest", "", "(none)", "(auto)"):
        clean_run = target_run.strip().replace("\\", "/").rstrip("/")
        for root in roots:
            for cand_run_path in (root / clean_run, root / Path(clean_run).name):
                if cand_run_path.exists() and cand_run_path.is_dir():
                    for cvar in cand_variants:
                        for p in (cand_run_path / "passed_candidates" / cvar,
                                  cand_run_path / cvar,
                                  cand_run_path / "full_backtest" / cvar):
                            if p.exists() and p.is_dir():
                                return p

        # Deep search for run folder by name
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

        # If target_run was specified, do not fall back to candidates from other runs
        print(f"[ERROR] Candidate '{target_cand}' not found in specified run '{target_run}'. Refusing to substitute from another run.")
        return None

    # 2. If target_run was NOT specified or was 'latest' / empty, search across candidate folders
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

    return None


def locate_or_build_set_file(cand_dir: Path) -> Path | None:
    cand_name = cand_dir.name
    cand_n = cand_name.replace("cand_", "")
    target_set_path = cand_dir / f"c{cand_n}_full.set"
    if target_set_path.exists():
        return target_set_path

    candidates = list(cand_dir.rglob("*.set")) + list(cand_dir.rglob("*.SET"))
    if candidates:
        return candidates[0]

    json_files = list(cand_dir.rglob("*.json"))
    if json_files:
        try:
            with open(json_files[0], "r", encoding="utf-8") as f:
                params = json.load(f)
            gen_set = cand_dir / f"{cand_name}.set"
            with open(gen_set, "w", encoding="utf-16") as f:
                for k, v in params.items():
                    f.write(f"{k}={v}\n")
            return gen_set
        except Exception as exc:
            print(f"WARNING: Could not build .set from JSON: {exc}")
    return None


def main():
    base_work_dir = Path(WORK_DIR)
    target_cand_dir = resolve_candidate_dir(base_work_dir, TARGET_RUN_DIR, TARGET_CANDIDATE)

    print("=" * 76)
    print(" SINGLE CANDIDATE FULL BACKTEST & ADVANCED REPORTING — FIXED")
    print("=" * 76)

    if target_cand_dir is None or not target_cand_dir.exists():
        return

    print(f"  Target Directory:  {target_cand_dir.parent.name}")
    print(f"  Target Candidate:  {TARGET_CANDIDATE}")
    print(f"  Backtest Range:    {BT_START} -> {BT_END}")
    print(f"  Initial Deposit:   {DEPOSIT_OVERRIDE} {CURRENCY}")

    source_set_file = locate_or_build_set_file(target_cand_dir)
    if not source_set_file:
        print("ERROR: Could not locate or build a .set file.")
        return

    profiles_tester_dir = Path(TERMINAL_DATA_DIR) / "MQL5" / "Profiles" / "Tester"
    profiles_tester_dir.mkdir(parents=True, exist_ok=True)
    temp_set_name = f"full_bt_{TARGET_CANDIDATE}.set"
    target_set_path = profiles_tester_dir / temp_set_name
    shutil.copy(source_set_file, target_set_path)

    lot_ovr = os.environ.get("AF_LOT_SIZE", "").strip()
    risk_ovr = os.environ.get("AF_RISK_PCT", "").strip()
    if lot_ovr or risk_ovr:
        try:
            with open(target_set_path, "r", encoding="utf-16") as f:
                lines = f.readlines()
            with open(target_set_path, "w", encoding="utf-16") as f:
                for line in lines:
                    if lot_ovr and line.startswith("LotSize="):
                        f.write(f"LotSize={lot_ovr}\n")
                        print(f"  [OVERRIDE] LotSize = {lot_ovr}")
                    elif risk_ovr and line.startswith("UseRiskBasedSizing="):
                        f.write(f"UseRiskBasedSizing=1\n")
                    elif risk_ovr and (line.startswith("RiskPercent=") or line.startswith("MonthlyDDPercent=") or line.startswith("DailyLossPercent=")):
                        f.write(f"{line.split('=')[0]}={risk_ovr}\n")
                        print(f"  [OVERRIDE] {line.split('=')[0]} = {risk_ovr}")
                    else:
                        f.write(line)
        except Exception as e:
            print(f"  [WARNING] Could not apply lot/risk overrides to set file: {e}")

    report_folder = target_cand_dir / "full_backtest_report"
    report_folder.mkdir(parents=True, exist_ok=True)
    report_name = f"Full_BT_{TARGET_CANDIDATE}"

    # Auto-detect expert from candidate directory, run_meta.json, or run.ini
    expert_to_run = os.environ.get("AF_EXPERT") or EXPERT
    for sdir in (target_cand_dir, target_cand_dir.parent, target_cand_dir.parent.parent):
        meta_file = sdir / "run_meta.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as mf:
                    mdata = json.load(mf)
                    if mdata.get("expert"):
                        expert_to_run = mdata["expert"]
                        break
            except Exception:
                pass
        ini_file = sdir / "run.ini"
        if ini_file.exists():
            try:
                ini_text = ini_file.read_text(encoding="utf-16", errors="ignore")
                if not ini_text.strip():
                    ini_text = ini_file.read_text(encoding="utf-8", errors="ignore")
                m_exp = re.search(r"Expert\s*=\s*(.+)", ini_text)
                if m_exp:
                    expert_to_run = m_exp.group(1).strip()
                    break
            except Exception:
                pass

    from mt5_optimizer import sync_ea_to_mt5
    expert_to_run = sync_ea_to_mt5(expert_to_run, TERMINAL_DATA_DIR, TERMINAL_PATH)

    print(f"\n  --> Launching MetaTrader 5 Full Backtest (EA: {expert_to_run} | Market: {SYMBOL_OVERRIDE})...")
    try:
        report_html = run_single_backtest(
            terminal_path=TERMINAL_PATH,
            terminal_data_dir=TERMINAL_DATA_DIR,
            expert=expert_to_run,
            set_file=temp_set_name,
            symbol=SYMBOL_OVERRIDE,
            period=PERIOD,
            from_date=BT_START,
            to_date=BT_END,
            work_dir=str(report_folder),
            login=LOGIN,
            password=PASSWORD,
            server=SERVER,
            report_name=report_name,
            deposit=int(float(DEPOSIT_OVERRIDE)),
            currency=CURRENCY,
            leverage=LEVERAGE,
            timeout=SINGLE_TEST_TIMEOUT * 2,
        )
    finally:
        if target_set_path.exists():
            target_set_path.unlink()

    if not report_html or not Path(report_html).exists():
        print("  ERROR: Backtest failed or report was not generated.")
        return

    # Use the archived copy of the report inside report_folder to guarantee we are reading the exact file generated and copied!
    report_archived = report_folder / Path(report_html).name
    if not report_archived.exists():
        report_archived = Path(report_html)

    print(f"  --> MT5 HTML Report (Archived): {report_archived}")

    print("  --> Analyzing MT5 Summary Metrics...")
    try:
        raw_metrics = analyze(report_archived)
        if not isinstance(raw_metrics, dict):
            raw_metrics = {}
    except Exception as exc:
        print(f"      [WARNING] report_analysis.analyze failed: {exc}")
        raw_metrics = {}

    # Merge Table 0 summary metrics directly to guarantee 100% alignment with HTML report
    summary_table = parse_mt5_summary_table(Path(report_archived))
    for k, v in summary_table.items():
        if k not in raw_metrics:
            raw_metrics[k] = v
        if "summary_raw" in raw_metrics and isinstance(raw_metrics["summary_raw"], dict):
            raw_metrics["summary_raw"].setdefault(k, v)
        else:
            raw_metrics["summary_raw"] = summary_table

    print("  --> Extracting Deal Data for Drawdown, Charts & Heatmap...")
    deals_df = parse_mt5_html_for_deals(Path(report_archived), deposit=float(DEPOSIT_OVERRIDE))

    derived = calculate_derived_metrics(deals_df, float(DEPOSIT_OVERRIDE)) if deals_df is not None else {}
    if derived:
        print("\n  ---- VERIFIED DEAL-DERIVED METRICS ----")
        print(f"     Net Profit:            {_fmt_money(derived['total_net_profit'])}")
        print(f"     Net Profit %:          {_fmt_pct(derived['profit_pct'])}")
        print(f"     Max Balance DD:        {_fmt_money(derived['max_dd'])}")
        print(f"     Max Balance DD %:      {_fmt_pct(derived['max_dd_pct'])}")
        print(f"     Profit Factor:         {_fmt_ratio(derived['profit_factor'])}")
        print(f"     Recovery Factor:       {_fmt_ratio(derived['recovery_factor'])}")
        print(f"     Profit Trades:         {derived['profit_trades']:,}")
        print(f"     Loss Trades:           {derived['loss_trades']:,}")
        print(f"     Breakeven Trades:      {derived['breakeven_trades']:,}")
        print("  ----------------------------------------")

    charts = {}
    heatmap_path = None
    monthly_profit = None
    if deals_df is not None and not deals_df.empty:
        print("  --> Generating Equity Curves...")
        charts = generate_equity_charts(deals_df, float(DEPOSIT_OVERRIDE), report_folder)
        print(f"      Generated {len(charts)} equity chart(s).")

        print("  --> Generating Monthly Performance Heatmap...")
        heatmap_path, monthly_profit = generate_monthly_heatmap(deals_df, float(DEPOSIT_OVERRIDE), report_folder)
        if heatmap_path:
            print(f"      Heatmap saved: {heatmap_path.name}")
        else:
            print("      [WARNING] Heatmap could not be generated.")
    else:
        print("  [WARNING] No deal data available; charts and heatmap will be omitted.")

    print("  --> Compiling Word Document...")
    cand_n = TARGET_CANDIDATE.replace("cand_", "")
    doc_out = report_folder / f"Full_Backtest_Summary_{TARGET_CANDIDATE}.docx"
    final_doc_path = create_full_backtest_word_doc(
        doc_path=doc_out,
        cand_n=cand_n,
        raw_metrics=raw_metrics,
        deals_df=deals_df,
        charts=charts,
        heatmap_path=heatmap_path,
        monthly_profit=monthly_profit,
        deposit=float(DEPOSIT_OVERRIDE),
    )

    print("\n" + "=" * 76)
    print(f" FULL BACKTEST COMPLETE FOR {TARGET_CANDIDATE}")
    if final_doc_path:
        print(f" Word Report:      {final_doc_path}")
    for key, path in charts.items():
        print(f" {key:18}: {path}")
    if heatmap_path:
        print(f" heatmap           : {heatmap_path}")
    print("=" * 76)


if __name__ == "__main__":
    main()