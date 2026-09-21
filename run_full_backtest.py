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

import io
import json
import math
import re
import shutil
import time
from pathlib import Path

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


def _parse_number(value):
    """Parse MT5 number formatting, including commas/currency/parentheses."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return np.nan

    s = str(value).replace("\xa0", " ").strip()
    if not s:
        return np.nan

    negative_accounting = s.startswith("(") and s.endswith(")")
    s = s.strip("()")

    # Preserve decimal separator expected in MT5 reports; strip other symbols.
    s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-+eE]", "", s)
    if s in {"", ".", "-", "+", "-.", "+."}:
        return np.nan

    try:
        n = float(s)
        return -abs(n) if negative_accounting else n
    except ValueError:
        return np.nan


def _parse_table_with_bs(soup):
    """Fallback parser for MT5 HTML when pandas cannot recognise the table."""
    if soup is None:
        return []

    parsed_tables = []

    for table_no, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Search the first few rows for a genuine header containing Time + Profit.
        header_idx = None
        header_cells = None
        for idx, row in enumerate(rows[:8]):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            norms = [_normalise_label(c) for c in cells]
            has_time = any(x in norms or any(a in x for a in ("time", "date")) for x in norms)
            has_profit = any("profit" in x or x in {"p/l", "pl"} for x in norms)
            if has_time and has_profit:
                header_idx = idx
                header_cells = cells
                break

        if header_idx is None:
            continue

        data = []
        for row in rows[header_idx + 1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            if len(cells) < len(header_cells):
                cells += [""] * (len(header_cells) - len(cells))
            data.append(cells[:len(header_cells)])

        if data:
            df = pd.DataFrame(data, columns=header_cells)
            df.attrs["source_table"] = table_no
            parsed_tables.append(df)

    return parsed_tables


def _load_html_tables(html_path: Path):
    """Load HTML tables with pandas first, BeautifulSoup fallback second."""
    html = _read_html_text(html_path)
    tables = []

    try:
        pandas_tables = pd.read_html(io.StringIO(html))
        for i, df in enumerate(pandas_tables):
            df = _flatten_columns(df)
            df.attrs["source_table"] = i
            tables.append(df)
    except Exception as exc:
        print(f"      [INFO] pandas.read_html could not parse report: {exc}")

    # If pandas did not give us a suitable trade table, use BS as a second parser.
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        bs_tables = _parse_table_with_bs(soup)
        if bs_tables:
            tables.extend(bs_tables)

    return tables


def _looks_like_mt5_date(value) -> bool:
    """Return True for common MT5 report date/time strings."""
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    if not re.match(r"^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}(?:\s|$)", s):
        return False
    dt = pd.to_datetime(s, errors="coerce")
    return not pd.isna(dt)


def _extract_headered_deal_candidates(soup):
    """Extract deal rows from normal HTML tables whose headers are identifiable."""
    candidates = []
    if soup is None:
        return candidates
    for table_no, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_pos = None
        headers = None
        for idx, row in enumerate(rows[:15]):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            norms = [_normalise_label(c) for c in cells]
            has_time = any(
                x == "time" or x.startswith("time ") or x in {"date", "datetime", "date/time"}
                or x.startswith("date ") for x in norms
            )
            has_profit = any(x == "profit" or x in {"p/l", "pl"} or "profit" in x for x in norms)
            if has_time and has_profit:
                header_pos, headers = idx, cells
                break
        if header_pos is None:
            continue
        data = []
        for row in rows[header_pos + 1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            data.append(cells[:len(headers)])
        if data:
            candidates.append((table_no, headers, data, "headered"))
    return candidates


def _extract_headerless_deal_candidates(soup):
    """Fallback parser for MT5 reports whose headers are missing or localized."""
    candidates = []
    if soup is None:
        return candidates

    row_groups = []
    for table_no, table in enumerate(soup.find_all("table")):
        rows = []
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            row_groups.append((table_no, rows))

    # Also scan every row globally. MT5 reports can contain nested/irregular
    # tables where the deal rows are not exposed as one normal table.
    all_rows = []
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        if cells:
            all_rows.append(cells)
    if all_rows:
        row_groups.append(("global", all_rows))

    for table_no, rows in row_groups:
        date_rows = []
        for cells in rows:
            date_idx = next((i for i, v in enumerate(cells) if _looks_like_mt5_date(v)), None)
            if date_idx is not None and len(cells) >= 5:
                date_rows.append((cells, date_idx))
        if len(date_rows) < 3:
            continue

        max_len = max(len(cells) for cells, _ in date_rows)
        score_by_idx = {}
        for idx in range(max_len):
            parsed = []
            for cells, _ in date_rows:
                if idx < len(cells):
                    n = _parse_number(cells[idx])
                    if not pd.isna(n):
                        parsed.append(float(n))
            if len(parsed) < max(3, int(len(date_rows) * 0.50)):
                continue
            mixed_sign = any(v > 0 for v in parsed) and any(v < 0 for v in parsed)
            nonzero_ratio = sum(v != 0 for v in parsed) / len(parsed)
            positional_bonus = {8: 1.0, 9: 1.0, 10: 5.0, 11: 1.5, 12: 0.5}.get(idx, 0.0)
            score = (len(parsed) / len(date_rows)) * 5.0 + (2.0 if mixed_sign else 0.0)
            score += nonzero_ratio + positional_bonus
            score_by_idx[idx] = score
        if not score_by_idx:
            continue

        profit_idx = max(score_by_idx, key=score_by_idx.get)
        balance_idx = profit_idx + 1 if profit_idx + 1 < max_len else None
        commission_idx = profit_idx - 2 if profit_idx - 2 >= 0 else None
        swap_idx = profit_idx - 1 if profit_idx - 1 >= 0 else None

        # Standard MT5 deal table usually puts Profit at column 10 and Balance at 11.
        if max_len > 10:
            parsed10 = []
            for cells, _ in date_rows:
                n = _parse_number(cells[10]) if len(cells) > 10 else np.nan
                if not pd.isna(n):
                    parsed10.append(float(n))
            if len(parsed10) >= max(3, int(len(date_rows) * 0.60)):
                mixed10 = any(v > 0 for v in parsed10) and any(v < 0 for v in parsed10)
                if mixed10 or len(parsed10) >= len(date_rows) * 0.85:
                    profit_idx = 10
                    balance_idx = 11 if max_len > 11 else None
                    commission_idx = 8 if max_len > 8 else None
                    swap_idx = 9 if max_len > 9 else None

        # Try to recover a buy/sell Type (Direction) column so Long/Short
        # trade breakdown does not have to fall back to "N/A". MT5 deal
        # tables commonly place this a few columns after the date/time.
        exclude_idx = {date_idx, profit_idx, balance_idx, commission_idx, swap_idx}
        type_idx, best_type_ratio = None, 0.0
        for idx in range(max_len):
            if idx in exclude_idx:
                continue
            values = [cells[idx].strip().lower() for cells, _ in date_rows if idx < len(cells)]
            if not values:
                continue
            hits = sum(1 for v in values if "buy" in v or "sell" in v)
            ratio = hits / len(values)
            if ratio > 0.5 and ratio > best_type_ratio:
                best_type_ratio = ratio
                type_idx = idx

        headers = ["Time", "Profit", "Balance", "Commission", "Swap"]
        if type_idx is not None:
            headers.append("Type")

        data = []
        for cells, date_idx in date_rows:
            original = list(cells) + [""] * (max_len - len(cells))
            row = [
                original[date_idx],
                original[profit_idx] if profit_idx < len(original) else "",
                original[balance_idx] if balance_idx is not None and balance_idx < len(original) else "",
                original[commission_idx] if commission_idx is not None and commission_idx < len(original) else "",
                original[swap_idx] if swap_idx is not None and swap_idx < len(original) else "",
            ]
            if type_idx is not None:
                row.append(original[type_idx] if type_idx < len(original) else "")
            data.append(row)

        candidates.append((table_no, headers, data,
                          f"headerless(profit_col={profit_idx}, rows={len(data)})"))
    return candidates


def parse_mt5_html_for_deals(html_path: Path, deposit: float = None):
    """Extract MT5 deal-level data, including difficult/localized report layouts."""
    try:
        html = _read_html_text(html_path)
        soup = BeautifulSoup(html, "html.parser") if BeautifulSoup is not None else None
        if soup is None:
            print("    [ERROR] BeautifulSoup is unavailable; cannot parse the MT5 report.")
            return None

        candidates = _extract_headered_deal_candidates(soup)
        if not candidates:
            print("    [INFO] Standard MT5 headers were not detected; using raw-row fallback parser...")
            candidates = _extract_headerless_deal_candidates(soup)

        if not candidates:
            print("    [ERROR] Could not identify MT5 deal rows (timestamp + numeric P&L data).")
            return None

        best_df = None
        best_score = -1
        best_meta = None
        for table_no, headers, rows, mode in candidates:
            df = pd.DataFrame(rows, columns=headers)
            if df.empty:
                continue
            df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
            df["Profit"] = df["Profit"].apply(_parse_number)
            for col in ["Balance", "Commission", "Swap"]:
                if col in df.columns:
                    df[col] = df[col].apply(_parse_number)
            valid = df["Time"].notna() & df["Profit"].notna()
            valid_count = int(valid.sum())
            if valid_count < 3:
                continue
            score = valid_count + min(len(df), 100) / 1000.0
            if "Balance" in df.columns:
                score += 10 * float(df["Balance"].notna().mean())
            if "Commission" in df.columns:
                score += 2
            if "Swap" in df.columns:
                score += 2
            if mode == "headered":
                score += 3
            if score > best_score:
                best_score = score
                best_df = df.loc[valid].copy()
                best_meta = (table_no, mode)

        # A malformed/localized header can create a false-positive candidate.
        # In that case, run the raw-row parser as a second pass.
        if best_df is None or best_df.empty:
            fallback_candidates = _extract_headerless_deal_candidates(soup)
            if fallback_candidates:
                best_df = None
                best_score = -1
                best_meta = None
                for table_no, headers, rows, mode in fallback_candidates:
                    fdf = pd.DataFrame(rows, columns=headers)
                    if fdf.empty:
                        continue
                    fdf["Time"] = pd.to_datetime(fdf["Time"], errors="coerce")
                    fdf["Profit"] = fdf["Profit"].apply(_parse_number)
                    for col in ["Balance", "Commission", "Swap"]:
                        if col in fdf.columns:
                            fdf[col] = fdf[col].apply(_parse_number)
                    valid = fdf["Time"].notna() & fdf["Profit"].notna()
                    valid_count = int(valid.sum())
                    if valid_count < 3:
                        continue
                    score = valid_count + (10 * float(fdf["Balance"].notna().mean()) if "Balance" in fdf.columns else 0)
                    if score > best_score:
                        best_score = score
                        best_df = fdf.loc[valid].copy()
                        best_meta = (table_no, mode)

        if best_df is None or best_df.empty:
            print("    [ERROR] Deal rows were found, but no valid timestamp + P&L records survived parsing.")
            print("             The MT5 HTML appears not to expose deal rows in a parseable form.")
            print("             Save/export the tester report with the Deals section included.")
            return None

        df = best_df.sort_values("Time").reset_index(drop=True)
        if "Commission" not in df.columns:
            df["Commission"] = 0.0
        else:
            df["Commission"] = df["Commission"].fillna(0.0)
        if "Swap" not in df.columns:
            df["Swap"] = 0.0
        else:
            df["Swap"] = df["Swap"].fillna(0.0)
        if "Balance" in df.columns:
            df["Balance"] = pd.to_numeric(df["Balance"], errors="coerce")

        if "Type" in df.columns:
            type_text = df["Type"].astype(str).str.lower()
            df["IsBalanceOperation"] = type_text.str.contains(
                r"balance|credit|deposit|withdraw|charge|transfer", regex=True, na=False
            )
        else:
            df["IsBalanceOperation"] = False

        # Heuristic safety net: every MT5 tester report opens with an initial
        # deposit/balance entry. When the report's Type/Direction column was
        # not captured (this happens routinely with the headerless fallback
        # parser, which only recovers Time/Profit/Balance/Commission/Swap),
        # that deposit row is otherwise indistinguishable from a real trade
        # and silently inflates Gross Profit, Profit Factor, Largest Profit
        # Trade, consecutive-win streaks, and the first month of the heatmap
        # by the full deposit amount. Flag it explicitly: it is always the
        # very first chronological entry and its Profit is numerically equal
        # to the account's starting deposit.
        if DEPOSIT_OVERRIDE:
            first_time = df["Time"].min()
            is_first_row = df["Time"] == first_time
            matches_deposit = np.isclose(df["Profit"].fillna(0.0), float(DEPOSIT_OVERRIDE), atol=0.01)
            newly_flagged = int((is_first_row & matches_deposit & ~df["IsBalanceOperation"]).sum())
            df.loc[is_first_row & matches_deposit, "IsBalanceOperation"] = True
            if newly_flagged:
                print(f"       Detected and excluded {newly_flagged} initial deposit row(s) "
                      f"(Profit == deposit of {float(DEPOSIT_OVERRIDE):,.2f}) that were not tagged as a balance operation.")

        # Build net per-row P&L before creating the stored trade dataframe.
        df["NetTradePnl"] = df["Profit"] + df["Commission"] + df["Swap"]

        trade_df = df.loc[~df["IsBalanceOperation"]].copy()
        if trade_df.empty:
            trade_df = df.copy()

        balance_usable = False
        if "Balance" in df.columns:
            finite_balance = df["Balance"].replace([np.inf, -np.inf], np.nan).dropna()
            if len(finite_balance) >= 3:
                pnl_movement = (df["Profit"] + df["Commission"] + df["Swap"]).abs().sum()
                balance_movement = finite_balance.max() - finite_balance.min()
                balance_usable = bool(balance_movement > 0 or pnl_movement == 0)

        if balance_usable:
            df["Balance"] = df["Balance"].ffill()
            balance_reconstructed = False
        else:
            net_change = df["Profit"].fillna(0.0) + df["Commission"] + df["Swap"]
            df["Balance"] = float(DEPOSIT_OVERRIDE) + net_change.cumsum()
            balance_reconstructed = True

        df.attrs["trade_df"] = trade_df
        df.attrs["balance_reconstructed"] = balance_reconstructed
        df.attrs["source_table"] = best_meta[0]
        df.attrs["parser_mode"] = best_meta[1]
        df.attrs["parsed_rows"] = len(df)

        print(f"    -> MT5 deal data identified via {best_meta[1]} parser (table {best_meta[0]}); parsed {len(df):,} rows.")
        if balance_reconstructed:
            print("       Balance reconstructed from Profit + Commission + Swap.")
        else:
            print("       Using MT5-reported Balance values for drawdown/equity calculations.")
        print(f"       Date range: {df['Time'].min()} -> {df['Time'].max()} | P&L range: {df['Profit'].min():,.2f} -> {df['Profit'].max():,.2f}")
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
    return deals_df.copy()


def calculate_derived_metrics(deals_df: pd.DataFrame, deposit: float) -> dict:
    """Calculate metrics directly from parsed MT5 rows so missing report fields don't become zero."""
    result = {}
    if deals_df is None or deals_df.empty:
        return result

    df = deals_df.sort_values("Time").copy()
    trades = _get_trade_rows(df).sort_values("Time").copy()
    pnl_all = pd.to_numeric(trades["NetTradePnl"], errors="coerce").fillna(0.0)

    # MT5 can export opening and closing deals as separate rows. Opening rows
    # commonly have zero Profit, so result/trade statistics use non-zero P&L
    # rows. The official MT5 Total Trades figure is preferred in the document
    # when report_analysis.analyze() successfully provides it.
    nonzero_mask = pnl_all != 0.0
    pnl = pnl_all[nonzero_mask].reset_index(drop=True)

    # Account-level P&L.
    balance = pd.to_numeric(df["Balance"], errors="coerce").dropna()
    if not balance.empty:
        total_net_profit = float(balance.iloc[-1] - deposit)
    else:
        total_net_profit = float(pnl.sum())

    # Balance drawdown from the actual balance curve.
    equity = pd.to_numeric(df["Balance"], errors="coerce").to_numpy(dtype=float)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(np.max(dd)) if len(dd) else 0.0
    max_dd_index = int(np.argmax(dd)) if len(dd) else 0
    peak_index = int(np.argmax(equity[: max_dd_index + 1])) if len(equity) else 0
    dd_pct_at_peak = (max_dd / equity[peak_index] * 100.0) if len(equity) and equity[peak_index] != 0 else 0.0

    positive = pnl[pnl > 0]
    negative = pnl[pnl < 0]
    breakeven = pnl[pnl == 0]

    gross_profit = float(positive.sum())
    gross_loss = float(negative.sum())
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else float("inf")
    recovery_factor = total_net_profit / max_dd if max_dd > 0 else float("inf")

    # Consecutive results.
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

    total_trades_from_deals = int(len(pnl))

    # Daily account returns for a defensible Sharpe fallback.
    daily = df.groupby(df["Time"].dt.date)["NetTradePnl"].sum()
    daily_returns = daily / float(deposit) if deposit else pd.Series(dtype=float)
    if len(daily_returns) >= 2 and daily_returns.std(ddof=1) > 0:
        sharpe = float((daily_returns.mean() / daily_returns.std(ddof=1)) * math.sqrt(252))
    else:
        sharpe = 0.0

    result.update(
        {
            "total_net_profit": total_net_profit,
            "profit_pct": (total_net_profit / deposit * 100.0) if deposit else 0.0,
            "max_dd": max_dd,
            "max_dd_pct": dd_pct_at_peak,
            "profit_factor": profit_factor,
            "recovery_factor": recovery_factor,
            "sharpe": sharpe,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": total_trades_from_deals,
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

    # Holding time from position IDs when available.
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

    # Long/short breakdown when Direction or Type is present.
    dir_col = "Direction" if "Direction" in trades.columns else ("Type" if "Type" in trades.columns else None)
    if dir_col:
        # `pnl` was filtered to non-zero rows and reset to a 0..n-1 index, so
        # the label series must go through the exact same filter + reset
        # before it can be used as a boolean mask against `pnl` — otherwise
        # pandas raises "Unalignable boolean Series" because the two series
        # carry different index values.
        labels = trades[dir_col].astype(str).str.lower()
        labels = labels[nonzero_mask].reset_index(drop=True)
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


def extract_metric(raw_metrics: dict, aliases, default=0.0):
    """Case-insensitive metric lookup supporting nested analyze() output."""
    flat = _flatten_metric_dict(raw_metrics)
    norm_map = {_normalise_label(k): v for k, v in flat.items()}
    aliases_norm = [_normalise_label(a) for a in aliases]

    for alias in aliases_norm:
        if alias in norm_map:
            n = _parse_number(norm_map[alias])
            return float(n) if not pd.isna(n) else default

    for alias in aliases_norm:
        for key, value in norm_map.items():
            if alias in key or key in alias:
                n = _parse_number(value)
                if not pd.isna(n):
                    return float(n)

    return default


def extract_string(raw_metrics: dict, aliases, default="N/A"):
    flat = _flatten_metric_dict(raw_metrics)
    norm_map = {_normalise_label(k): v for k, v in flat.items()}
    aliases_norm = [_normalise_label(a) for a in aliases]

    for alias in aliases_norm:
        if alias in norm_map:
            return str(norm_map[alias])
    for alias in aliases_norm:
        for key, value in norm_map.items():
            if alias in key or key in alias:
                return str(value)
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

        cumulative_profit = numeric_balance - float(deposit)
        pct_gain = (
            cumulative_profit / float(deposit) * 100.0
            if deposit
            else np.zeros_like(cumulative_profit)
        )

        # Matplotlib 3.9+ removed pyplot.plot_date().
        # pyplot.plot() is the supported replacement and handles datetime x-values.
        x = times.to_numpy()

        # 1. Total dollar P/L
        try:
            plt.figure(figsize=(10.5, 5.2))
            plt.plot(x, cumulative_profit, "-", linewidth=1.5)
            plt.axhline(0, linestyle="--", linewidth=1.0)
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
            plt.plot(x, numeric_balance, "-", linewidth=1.5, label="Balance")
            plt.axhline(
                float(deposit),
                linestyle="--",
                linewidth=1.0,
                label="Initial Deposit",
            )
            plt.title("Equity / Balance Growth", fontsize=12, fontweight="bold")
            plt.xlabel("Time")
            plt.ylabel("Account Balance")
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
            plt.plot(x, pct_gain, "-", linewidth=1.5)
            plt.axhline(0, linestyle="--", linewidth=1.0)
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

    trades = _get_trade_rows(deals_df).copy()
    if trades.empty:
        return None, None

    trades["Year"] = trades["Time"].dt.year
    trades["Month"] = trades["Time"].dt.month
    monthly = trades.groupby(["Year", "Month"])["NetTradePnl"].sum().unstack(fill_value=0)
    monthly = monthly.sort_index()

    # Ensure all months are present in the plot. Column 12 (index 12) holds
    # the year-end total, appended after December.
    all_years = list(monthly.index)
    matrix = np.zeros((len(all_years), 13), dtype=float)
    for r, year in enumerate(all_years):
        for month in range(1, 13):
            if month in monthly.columns:
                matrix[r, month - 1] = float(monthly.loc[year, month])
        matrix[r, 12] = matrix[r, :12].sum()

    fig, ax = plt.subplots(figsize=(13.4, max(3.2, 1.0 + 0.55 * len(all_years))))
    # Color scale is based on the monthly cells only, so a large year total
    # doesn't wash out the month-to-month color contrast.
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

    # Vertical divider between the monthly cells and the year-end Total column.
    ax.axvline(11.5, color="black", linewidth=1.2)

    for r in range(matrix.shape[0]):
        for c in range(12):
            value = matrix[r, c]
            pct = (value / deposit * 100.0) if deposit else 0.0
            ax.text(c, r, f"${value:,.0f}\n{pct:+.1f}%", ha="center", va="center", fontsize=8)

        total_value = matrix[r, 12]
        total_pct = (total_value / deposit * 100.0) if deposit else 0.0
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

    # Start with report_analysis values, then prefer reliable deal-derived values.
    # This prevents zeros from an incomplete summary parser from overwriting actual data.
    total_net_profit = derived.get("total_net_profit", extract_metric(raw_metrics, ["Total Net Profit", "Net Profit"]))
    profit_pct = derived.get("profit_pct", (total_net_profit / deposit * 100.0 if deposit else 0.0))
    max_dd = derived.get("max_dd", extract_metric(raw_metrics, ["Balance Drawdown Maximal", "Max Drawdown", "Drawdown"]))
    max_dd_pct = derived.get("max_dd_pct", 0.0)
    pf = derived.get("profit_factor", extract_metric(raw_metrics, ["Profit Factor", "PF"]))
    rf = derived.get("recovery_factor", extract_metric(raw_metrics, ["Recovery Factor", "RF"]))
    sharpe = extract_metric(raw_metrics, ["Sharpe Ratio", "Sharpe"], default=derived.get("sharpe", 0.0))

    summary_total_trades = extract_metric(raw_metrics, ["Total Trades", "Trades"], default=0.0)
    summary_profit_trades = extract_metric(raw_metrics, ["Profit Trades (% of total)", "Profit Trades", "Winning Trades"], default=0.0)
    summary_loss_trades = extract_metric(raw_metrics, ["Loss trades (% of total)", "Loss Trades", "Losing Trades"], default=0.0)

    # Prefer the official summary count for Total Trades because MT5 can expose
    # separate opening/closing deal rows. Fall back to parsed deal results only
    # when the summary parser did not provide a usable count.
    total_trades = int(round(summary_total_trades)) if summary_total_trades > 0 else int(derived.get("total_trades", 0))
    profit_trades = int(round(summary_profit_trades)) if summary_profit_trades > 0 else int(derived.get("profit_trades", 0))
    loss_trades = int(round(summary_loss_trades)) if summary_loss_trades > 0 else int(derived.get("loss_trades", 0))
    breakeven_trades = max(0, total_trades - profit_trades - loss_trades)

    raw_win_rate = extract_metric(raw_metrics, ["Win Rate", "Profit Trades %"], default=0.0)
    profit_trades_pct = (profit_trades / total_trades * 100.0) if total_trades else raw_win_rate
    loss_trades_pct = (loss_trades / total_trades * 100.0) if total_trades else extract_metric(raw_metrics, ["Loss Trades %"], default=0.0)

    avg_win = derived.get("avg_win", extract_metric(raw_metrics, ["Average profit trade", "Average Profit"]))
    avg_loss = derived.get("avg_loss", extract_metric(raw_metrics, ["Average loss trade", "Average Loss"]))
    max_win = derived.get("largest_profit", extract_metric(raw_metrics, ["Largest profit trade", "Largest Profit"]))
    max_loss = derived.get("largest_loss", extract_metric(raw_metrics, ["Largest loss trade", "Largest Loss"]))

    consec_wins = derived.get("max_consecutive_wins", extract_metric(raw_metrics, ["Maximum consecutive wins", "Max consec wins"]))
    consec_losses = derived.get("max_consecutive_losses", extract_metric(raw_metrics, ["Maximum consecutive losses", "Max consec losses"]))

    long_text = "N/A"
    short_text = "N/A"
    if "long_count" in derived:
        long_text = f"{derived['long_count']} ({derived['long_win_rate']:.2f}% won)"
    if "short_count" in derived:
        short_text = f"{derived['short_count']} ({derived['short_win_rate']:.2f}% won)"

    start_dt = pd.to_datetime(BT_START)
    end_dt = pd.to_datetime(BT_END)
    days_in_test = max(1, (end_dt - start_dt).days)
    avg_trades_day = total_trades / days_in_test if days_in_test else 0.0
    avg_trades_month = avg_trades_day * 30.44
    avg_prof_day = total_net_profit / days_in_test if days_in_test else 0.0
    avg_prof_month = avg_prof_day * 30.44
    avg_prof_year = avg_prof_day * 365.25

    min_hold = _seconds_to_duration(derived.get("min_hold")) if "min_hold" in derived else extract_string(raw_metrics, ["Minimal position holding time"])
    max_hold = _seconds_to_duration(derived.get("max_hold")) if "max_hold" in derived else extract_string(raw_metrics, ["Maximal position holding time"])
    avg_hold = _seconds_to_duration(derived.get("avg_hold")) if "avg_hold" in derived else extract_string(raw_metrics, ["Average position holding time"])

    # 1. Performance overview
    doc.add_heading("1. Performance Overview", level=1)
    rows = [
        ("Market / Symbol", str(SYMBOL_OVERRIDE)),
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
        ("Gross Profit", _fmt_money(derived.get("gross_profit", extract_metric(raw_metrics, ["Gross Profit"])) )),
        ("Gross Loss", _fmt_money(derived.get("gross_loss", extract_metric(raw_metrics, ["Gross Loss"])) )),
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
                pct = value / deposit * 100.0 if deposit else 0.0
                _set_cell_text(cells[month_no], f"${value:,.0f}\n({pct:+.1f}%)")
                for p in cells[month_no].paragraphs:
                    for run in p.runs:
                        if value > 0:
                            run.font.color.rgb = RGBColor(0, 128, 0)
                        elif value < 0:
                            run.font.color.rgb = RGBColor(192, 0, 0)

            year_pct = year_total / deposit * 100.0 if deposit else 0.0
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
        f"Balance source: {'reconstructed from Profit + Commission + Swap' if reconstructed else 'MT5-reported Balance column'}.",
        "Max drawdown is calculated from the chronological balance curve as peak balance minus subsequent trough balance.",
        "Trade statistics are calculated from parsed trading rows and therefore do not depend solely on the MT5 summary table parser.",
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

    # 2. If target_run not found or empty / "latest", search across candidate folders
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
            with open(gen_set, "w", encoding="utf-16-le") as f:
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

    print(f"\n  --> Launching MetaTrader 5 Full Backtest (Market: {SYMBOL_OVERRIDE})...")
    try:
        report_html = run_single_backtest(
            terminal_path=TERMINAL_PATH,
            terminal_data_dir=TERMINAL_DATA_DIR,
            expert=EXPERT,
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

    print(f"  --> MT5 HTML Report: {report_html}")

    print("  --> Analyzing MT5 Summary Metrics...")
    try:
        raw_metrics = analyze(report_html)
        if not isinstance(raw_metrics, dict):
            raw_metrics = {}
    except Exception as exc:
        print(f"      [WARNING] report_analysis.analyze failed: {exc}")
        raw_metrics = {}

    print("  --> Extracting Deal Data for Drawdown, Charts & Heatmap...")
    deals_df = parse_mt5_html_for_deals(Path(report_html), deposit=float(DEPOSIT_OVERRIDE))

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