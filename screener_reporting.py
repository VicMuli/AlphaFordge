"""
screener_reporting.py - Comprehensive Market Screener Reporting Engine
AlphaForge MT5 Quant Architecture

Generates full backtest artifacts in:
    markets_screened/<SYMBOL>/<EA>/
including:
    1. report.html (archived MT5 tester report)
    2. trades.csv (extracted deal-level trades with timestamps & PnL)
    3. chart_equity_growth.png (balance and equity curve)
    4. chart_profit_dollars.png (cumulative profit curve)
    5. chart_percent_gain.png (percentage gain curve)
    6. monthly_heatmap.png (monthly performance heatmap matching the specification)
    7. <EA>_<SYMBOL>_Research_Report.docx (Word Document research report with all required sections)
    8. summary.json (detailed performance metrics)
    9. screener_inputs.set (parameter file used)
"""

import os
import sys
import json
import math
import re
import shutil
import time
from pathlib import Path

# Safe imports for scientific and reporting packages
try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = None
    np = None

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.colors as mcolors
    from matplotlib.cm import ScalarMappable
except ImportError:
    plt = None

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, RGBColor, Pt
except ImportError:
    docx = None

from report_analysis import analyze


def _safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        f = float(str(v).replace("$", "").replace(",", "").replace("%", "").strip())
        return f if not math.isnan(f) else default
    except Exception:
        return default


def _safe_int(v, default=0):
    try:
        return int(_safe_float(v, default))
    except Exception:
        return default


def _fmt_money(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    val = float(value)
    if val < 0:
        return f"$-{abs(val):,.2f}"
    return f"${val:,.2f}"


def _fmt_pct(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{float(value):.2f}%"


def _fmt_ratio(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{float(value):.2f}"


def _seconds_to_duration(seconds):
    if seconds is None:
        return "N/A"
    try:
        sec = float(seconds)
        if math.isnan(sec) or sec < 0:
            return "N/A"
        sec = int(round(sec))
    except Exception:
        return str(seconds)

    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, s = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or (days == 0 and hours == 0):
        parts.append(f"{minutes}m")
    if days == 0 and hours == 0 and minutes == 0:
        parts.append(f"{s}s")
    return " ".join(parts)


def _set_cell_text(cell, text, bold=False, color_rgb=None, font_size=Pt(9.5)):
    cell.text = str(text)
    for p in cell.paragraphs:
        for r in p.runs:
            r.bold = bold
            r.font.size = font_size
            if color_rgb:
                r.font.color.rgb = color_rgb


def generate_monthly_performance_heatmap(
    deals_df,
    deposit: float,
    output_dir: Path,
    ea_name: str = "EA",
    symbol: str = "Symbol",
    from_date: str = "2013.01.01",
    to_date: str = "2026.07.03",
) -> Path | None:
    """
    Generates monthly performance heatmap strictly styled according to the specification:
    - Title: "Monthly Performance Heatmap" (bold)
    - X-axis: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec, Total
    - Y-axis: Years (e.g. 2013 to 2026)
    - RdYlGn colormap centered at 0 (pale yellow/cream at 0, green for positive, red for negative)
    - Black outline borders around every single cell
    - Cell text formatting:
        Line 1: "$357" or "$-129" or "$0"
        Line 2: "+14.3%" or "-5.2%" or "+0.0%"
    - Total column separated by a distinct vertical border, containing individual white boxed cells
      with bold dark green (positive) or dark red (negative) totals.
    - Colorbar on the right labeled "Monthly P&L ($)".
    """
    if plt is None or deals_df is None or (pd is not None and deals_df.empty):
        return None

    try:
        df = deals_df.copy()
        if "Time" not in df.columns or "Profit" not in df.columns:
            return None

        df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
        df["Profit"] = pd.to_numeric(df["Profit"], errors="coerce").fillna(0.0)
        df = df[df["Time"].notna()].sort_values("Time")

        # Exclude pure balance operations if flag is present
        if "IsBalanceOperation" in df.columns:
            df = df[~df["IsBalanceOperation"]]
        elif "Type" in df.columns:
            df = df[df["Type"].astype(str).str.lower() != "balance"]

        # Parse years range from date or data
        try:
            start_yr = int(from_date.split(".")[0])
        except Exception:
            start_yr = df["Time"].dt.year.min() if not df.empty else 2013

        try:
            end_yr = int(to_date.split(".")[0])
        except Exception:
            end_yr = df["Time"].dt.year.max() if not df.empty else 2026

        if not df.empty:
            data_min_yr = df["Time"].dt.year.min()
            data_max_yr = df["Time"].dt.year.max()
            start_yr = min(start_yr, data_min_yr)
            end_yr = max(end_yr, data_max_yr)

        all_years = list(range(start_yr, end_yr + 1))
        if not all_years:
            all_years = [2023, 2024, 2025, 2026]

        df["Year"] = df["Time"].dt.year
        df["Month"] = df["Time"].dt.month
        monthly_grouped = df.groupby(["Year", "Month"])["Profit"].sum()

        # Build matrix: shape (len(all_years), 13)
        matrix = np.zeros((len(all_years), 13), dtype=float)
        for r_idx, yr in enumerate(all_years):
            row_sum = 0.0
            for m_idx in range(1, 13):
                if (yr, m_idx) in monthly_grouped.index:
                    val = float(monthly_grouped.loc[(yr, m_idx)])
                else:
                    val = 0.0
                matrix[r_idx, m_idx - 1] = val
                row_sum += val
            matrix[r_idx, 12] = row_sum

        # Calculate symmetric vmax across months (exclude Total column from color normalization)
        month_vals = matrix[:, :12]
        vmax = float(np.max(np.abs(month_vals))) if month_vals.size else 1.0
        if vmax <= 0.0 or math.isnan(vmax):
            vmax = 100.0

        # Normalization centered at 0.0
        norm = mcolors.Normalize(vmin=-vmax, vmax=vmax)
        cmap = plt.cm.RdYlGn

        # Setup figure
        fig_height = max(4.5, 1.4 + 0.54 * len(all_years))
        fig, ax = plt.subplots(figsize=(14.2, fig_height), dpi=180)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")

        # Invert y-axis: earliest year at row 0 (top), latest year at bottom
        ax.set_xlim(-0.5, 12.5)
        ax.set_ylim(len(all_years) - 0.5, -0.5)

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total"]
        ax.set_xticks(range(13))
        ax.set_xticklabels(months, fontsize=10)
        ax.set_yticks(range(len(all_years)))
        ax.set_yticklabels([str(y) for y in all_years], fontsize=10)
        ax.set_xlabel("Month", fontsize=11, labelpad=8)
        ax.set_ylabel("Year", fontsize=11, labelpad=8)
        ax.set_title("Monthly Performance Heatmap", fontsize=14, fontweight="bold", pad=14)

        effective_deposit = deposit if deposit > 0 else 2500.0

        # Render cells for Jan..Dec (0..11)
        for r_idx in range(len(all_years)):
            for c_idx in range(12):
                val = matrix[r_idx, c_idx]
                pct = (val / effective_deposit) * 100.0

                cell_color = cmap(norm(val))
                rect = plt.Rectangle(
                    (c_idx - 0.5, r_idx - 0.5), 1.0, 1.0,
                    facecolor=cell_color, edgecolor="black", linewidth=0.5
                )
                ax.add_patch(rect)

                # Format dollar and percentage labels
                if val < 0:
                    val_str = f"$-{abs(int(round(val))):,}"
                elif val == 0:
                    val_str = "$0"
                else:
                    val_str = f"${int(round(val)):,}"

                pct_str = f"{pct:+.1f}%"
                ax.text(c_idx, r_idx, f"{val_str}\n{pct_str}", ha="center", va="center", fontsize=8.2, color="#000000")

            # Render Total column (c_idx = 12)
            tot_val = matrix[r_idx, 12]
            tot_pct = (tot_val / effective_deposit) * 100.0

            tot_rect = plt.Rectangle(
                (11.5, r_idx - 0.5), 1.0, 1.0,
                facecolor="#ffffff", edgecolor="black", linewidth=0.8
            )
            ax.add_patch(tot_rect)

            if tot_val < 0:
                tot_val_str = f"$-{abs(int(round(tot_val))):,}"
                tot_color = "#991b1b"  # Dark red
            elif tot_val == 0:
                tot_val_str = "$0"
                tot_color = "#000000"
            else:
                tot_val_str = f"${int(round(tot_val)):,}"
                tot_color = "#166534"  # Dark green

            tot_pct_str = f"{tot_pct:+.1f}%"
            ax.text(12, r_idx, f"{tot_val_str}\n{tot_pct_str}", ha="center", va="center",
                    fontsize=8.5, fontweight="bold", color=tot_color)

        # Thick vertical boundary between Dec and Total
        ax.axvline(11.5, color="black", linewidth=1.5)

        # Colorbar
        sm = ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, pad=0.03, aspect=24, shrink=0.94)
        cbar.set_label("Monthly P&L ($)", fontsize=11, labelpad=8)
        cbar.ax.tick_params(labelsize=9.5)

        fig.tight_layout()
        out_path = output_dir / "monthly_heatmap.png"
        fig.savefig(out_path, dpi=180, bbox_inches="tight", facecolor="#ffffff")
        plt.close(fig)
        return out_path
    except Exception as exc:
        if plt is not None:
            plt.close("all")
        print(f"  [WARN] Failed to generate monthly heatmap: {exc}")
        return None


def calculate_comprehensive_metrics(parsed_report: dict, deals_df, deposit: float, symbol: str) -> dict:
    """
    Extracts and calculates all metrics required across:
      1. Performance Overview
      2. Trade Statistics Breakdown
      3. Averages & Holding Times
    """
    curated = parsed_report.get("curated_summary", {}) if parsed_report else {}
    summary_raw = parsed_report.get("summary_raw", {}) if parsed_report else {}

    def _get_val(keys, default=None):
        for k in keys:
            if k in curated and curated[k] is not None:
                return curated[k]
            if k in summary_raw and summary_raw[k] is not None:
                return summary_raw[k]
        return default

    # Initial Deposit
    rep_dep = _safe_float(_get_val(["Initial Deposit", "Deposit"]))
    effective_deposit = rep_dep if rep_dep > 0 else (deposit if deposit > 0 else 2500.0)

    # Deals dataframe calculations
    trades_pnl = []
    holding_secs = []
    trade_dates = set()
    long_trades = []
    short_trades = []

    if deals_df is not None and not deals_df.empty and pd is not None:
        try:
            df = deals_df.copy()
            if "Time" in df.columns:
                df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
                for d in df["Time"].dropna().dt.date:
                    trade_dates.add(d)

            # Filter deals
            if "IsBalanceOperation" in df.columns:
                trade_deals = df[~df["IsBalanceOperation"]].copy()
            elif "Type" in df.columns:
                trade_deals = df[df["Type"].astype(str).str.lower() != "balance"].copy()
            else:
                trade_deals = df.copy()

            if "Profit" in trade_deals.columns:
                trade_deals["Profit"] = pd.to_numeric(trade_deals["Profit"], errors="coerce").fillna(0.0)
                # Closed trade pnl (trades where profit != 0, or direction is out)
                if "Direction" in trade_deals.columns:
                    closed = trade_deals[trade_deals["Direction"].astype(str).str.lower().isin(["out", "in/out"])]
                    if closed.empty:
                        closed = trade_deals[trade_deals["Profit"] != 0.0]
                else:
                    closed = trade_deals[trade_deals["Profit"] != 0.0]

                if closed.empty:
                    closed = trade_deals

                trades_pnl = [float(p) for p in closed["Profit"]]

                # Long vs Short
                dir_col = "Direction" if "Direction" in closed.columns else ("Type" if "Type" in closed.columns else None)
                if dir_col:
                    for _, row in closed.iterrows():
                        t_type = str(row[dir_col]).lower()
                        p = float(row["Profit"])
                        # In MT5 closing a buy deal has Type 'sell' or direction 'out'
                        if "buy" in t_type:
                            long_trades.append(p)
                        elif "sell" in t_type:
                            short_trades.append(p)

            # Holding time by position ticket
            if "Position" in trade_deals.columns:
                grouped = trade_deals.groupby("Position", dropna=True)
                for _, g in grouped:
                    if len(g) >= 2:
                        d_times = g["Time"].dropna().sort_values()
                        if len(d_times) >= 2:
                            dt = (d_times.iloc[-1] - d_times.iloc[0]).total_seconds()
                            if dt >= 0:
                                holding_secs.append(dt)
        except Exception as e:
            print(f"  [WARN] Deals metric computation notice: {e}")

    # Section 1: Performance Overview
    net_profit = _safe_float(_get_val(["Net Profit", "Total Net Profit"]))
    if net_profit == 0 and trades_pnl:
        net_profit = float(sum(trades_pnl))

    profit_pct = (net_profit / effective_deposit * 100.0) if effective_deposit else 0.0

    max_dd = _safe_float(_get_val(["Max Balance Drawdown ($)", "Balance Drawdown Maximal", "Max Drawdown"]))
    max_dd_pct = _safe_float(_get_val(["Max Balance Drawdown (%)", "Balance Drawdown Relative", "Max Drawdown %"]))

    pf = _safe_float(_get_val(["Profit Factor", "PF"]))
    rf = _safe_float(_get_val(["Recovery Factor", "RF"]))
    if rf == 0 and max_dd > 0 and net_profit > 0:
        rf = net_profit / max_dd

    ret_dd_ratio = (net_profit / max_dd) if (max_dd > 0 and net_profit != 0) else (float("inf") if max_dd == 0 and net_profit > 0 else 0.0)
    sharpe = _safe_float(_get_val(["Sharpe Ratio", "Sharpe"]))

    # Max consecutive wins / losses
    max_wins = _safe_int(_get_val(["Max Consecutive Wins (count)", "Maximum consecutive wins"]))
    max_losses = _safe_int(_get_val(["Max Consecutive Losses (count)", "Maximum consecutive losses"]))

    if (max_wins == 0 or max_losses == 0) and trades_pnl:
        c_w = c_l = m_w = m_l = 0
        for p in trades_pnl:
            if p > 0:
                c_w += 1
                c_l = 0
                m_w = max(m_w, c_w)
            elif p < 0:
                c_l += 1
                c_w = 0
                m_l = max(m_l, c_l)
            else:
                c_w = c_l = 0
        if max_wins == 0:
            max_wins = m_w
        if max_losses == 0:
            max_losses = m_l

    # Section 2: Trade Statistics Breakdown
    total_trades = _safe_int(_get_val(["Total Trades", "Trades"]))
    if total_trades == 0 and trades_pnl:
        total_trades = len(trades_pnl)

    win_trades_count = _safe_int(_get_val(["Profit Trades (count)", "Profit Trades", "Winning Trades"]))
    if win_trades_count == 0 and trades_pnl:
        win_trades_count = len([p for p in trades_pnl if p > 0])

    loss_trades_count = _safe_int(_get_val(["Loss Trades (count)", "Loss Trades", "Losing Trades"]))
    if loss_trades_count == 0 and trades_pnl:
        loss_trades_count = len([p for p in trades_pnl if p < 0])

    win_trades_pct = (win_trades_count / total_trades * 100.0) if total_trades else 0.0
    loss_trades_pct = (loss_trades_count / total_trades * 100.0) if total_trades else 0.0
    breakeven_trades = max(0, total_trades - win_trades_count - loss_trades_count)

    # Long / short counts & won %
    long_cnt = _safe_int(_get_val(["Long Trades (count)"])) or len(long_trades)
    long_win_pct = _safe_float(_get_val(["Long Trades Win %"]))
    if long_win_pct == 0 and long_trades:
        w_l = len([p for p in long_trades if p > 0])
        long_win_pct = (w_l / len(long_trades)) * 100.0

    short_cnt = _safe_int(_get_val(["Short Trades (count)"])) or len(short_trades)
    short_win_pct = _safe_float(_get_val(["Short Trades Win %"]))
    if short_win_pct == 0 and short_trades:
        w_s = len([p for p in short_trades if p > 0])
        short_win_pct = (w_s / len(short_trades)) * 100.0

    long_text = f"{long_cnt:,} ({long_win_pct:.2f}% won)" if long_cnt > 0 else f"{long_cnt} (0.00% won)"
    short_text = f"{short_cnt:,} ({short_win_pct:.2f}% won)" if short_cnt > 0 else f"{short_cnt} (0.00% won)"

    avg_win = _safe_float(_get_val(["Average Profit Trade", "Average profit trade", "Average Win"]))
    avg_loss = _safe_float(_get_val(["Average Loss Trade", "Average loss trade", "Average Loss"]))
    largest_win = _safe_float(_get_val(["Largest Profit Trade", "Largest profit trade"]))
    largest_loss = _safe_float(_get_val(["Largest Loss Trade", "Largest loss trade"]))

    if trades_pnl:
        pos_pnl = [p for p in trades_pnl if p > 0]
        neg_pnl = [p for p in trades_pnl if p < 0]
        if avg_win == 0 and pos_pnl:
            avg_win = float(sum(pos_pnl) / len(pos_pnl))
        if avg_loss == 0 and neg_pnl:
            avg_loss = float(sum(neg_pnl) / len(neg_pnl))
        if largest_win == 0 and pos_pnl:
            largest_win = float(max(pos_pnl))
        if largest_loss == 0 and neg_pnl:
            largest_loss = float(min(neg_pnl))

    gross_profit = _safe_float(_get_val(["Gross Profit"]))
    gross_loss = _safe_float(_get_val(["Gross Loss"]))
    if gross_profit == 0 and trades_pnl:
        gross_profit = float(sum(p for p in trades_pnl if p > 0))
    if gross_loss == 0 and trades_pnl:
        gross_loss = float(sum(p for p in trades_pnl if p < 0))

    if pf == 0 and gross_loss != 0:
        pf = abs(gross_profit / gross_loss)

    # Section 3: Averages & Holding Times
    trading_days = len(trade_dates)
    if trading_days == 0:
        trading_days = max(1, _safe_int(_get_val(["Historical Trading Days", "Trading Days"]), 1))

    # Average trades and profit per period
    avg_trades_month = (total_trades / trading_days * 21.0) if trading_days else (total_trades / 12.0)
    avg_profit_day = net_profit / trading_days if trading_days else 0.0
    avg_profit_month = avg_profit_day * 21.0
    avg_profit_year = avg_profit_day * 252.0

    min_hold_raw = _get_val(["Minimal Position Holding Time", "Minimal position holding time"])
    max_hold_raw = _get_val(["Maximal Position Holding Time", "Maximal position holding time"])
    avg_hold_raw = _get_val(["Average Position Holding Time", "Average position holding time"])

    if holding_secs:
        min_hold_str = _seconds_to_duration(min(holding_secs))
        max_hold_str = _seconds_to_duration(max(holding_secs))
        avg_hold_str = _seconds_to_duration(float(sum(holding_secs) / len(holding_secs)))
    else:
        min_hold_str = str(min_hold_raw) if min_hold_raw else "N/A"
        max_hold_str = str(max_hold_raw) if max_hold_raw else "N/A"
        avg_hold_str = str(avg_hold_raw) if avg_hold_raw else "N/A"

    return {
        # Section 1
        "market_symbol": symbol,
        "profit_loss_dollars": net_profit,
        "profit_loss_pct": profit_pct,
        "max_balance_dd": max_dd,
        "max_balance_dd_pct": max_dd_pct,
        "profit_factor": pf,
        "recovery_factor": rf,
        "return_dd_ratio": ret_dd_ratio,
        "sharpe_ratio": sharpe,
        "max_consecutive_wins": max_wins,
        "max_consecutive_losses": max_losses,

        # Section 2
        "total_trades": total_trades,
        "profit_trades": win_trades_count,
        "profit_trades_pct": win_trades_pct,
        "loss_trades": loss_trades_count,
        "loss_trades_pct": loss_trades_pct,
        "breakeven_trades": breakeven_trades,
        "long_trades_text": long_text,
        "short_trades_text": short_text,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_profit": largest_win,
        "largest_loss": largest_loss,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,

        # Section 3
        "avg_trades_month": avg_trades_month,
        "avg_profit_day": avg_profit_day,
        "avg_profit_month": avg_profit_month,
        "avg_profit_year": avg_profit_year,
        "min_hold_time": min_hold_str,
        "max_hold_time": max_hold_str,
        "avg_hold_time": avg_hold_str,
        "historical_trading_days": trading_days,

        # Meta
        "effective_deposit": effective_deposit,
    }


def create_screener_word_doc(
    doc_path: Path,
    ea_name: str,
    symbol: str,
    resolved_symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    deposit: float,
    metrics: dict,
    charts: dict,
    heatmap_path: Path | None,
    deals_df,
):
    """
    Creates complete Word Document research report with the exact sections and metrics requested:
    1. Performance Overview
    2. Trade Statistics Breakdown
    3. Averages & Holding Times
    4. Monthly Performance Heatmap ($ and %)
    5. Balance & Equity Growth Curves
    """
    if docx is None:
        print("  [WARN] python-docx is not installed; skipping docx generation.")
        return None

    try:
        doc = docx.Document()

        # Document Header
        title = doc.add_heading(f"Strategy Research Report: {ea_name} — {symbol}", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_sub = p_sub.add_run(f"Market: {symbol} | Timeframe: {period} | Initial Deposit: ${deposit:,.2f}")
        run_sub.font.size = Pt(10)
        run_sub.font.color.rgb = RGBColor(100, 116, 139)

        p_meta = doc.add_paragraph()
        p_meta.add_run(f"Strategy / EA:       {ea_name}\n")
        p_meta.add_run(f"Execution Symbol:    {symbol} (Resolved: {resolved_symbol or symbol})\n")
        p_meta.add_run(f"Backtest Date Range: {from_date} -> {to_date}\n")
        p_meta.add_run(f"Generated by:        AlphaForge MT5 Quant Engine\n")
        p_meta.runs[0].font.size = Pt(9.5)

        # ── 1. Performance Overview ──────────────────────────────────────────
        doc.add_heading("1. Performance Overview", level=1)
        tbl1 = doc.add_table(rows=0, cols=2)
        tbl1.style = "Table Grid"

        s1_rows = [
            ("Market / Symbol", metrics.get("market_symbol", symbol)),
            ("Profit / Loss ($)", _fmt_money(metrics.get("profit_loss_dollars"))),
            ("Profit / Loss (%)", _fmt_pct(metrics.get("profit_loss_pct"))),
            ("Max Balance Drawdown", _fmt_money(metrics.get("max_balance_dd"))),
            ("Max Balance Drawdown (%)", _fmt_pct(metrics.get("max_balance_dd_pct"))),
            ("Profit Factor", _fmt_ratio(metrics.get("profit_factor"))),
            ("Recovery Factor", _fmt_ratio(metrics.get("recovery_factor"))),
            ("Return / Drawdown Ratio", _fmt_ratio(metrics.get("return_dd_ratio"))),
            ("Sharpe Ratio", _fmt_ratio(metrics.get("sharpe_ratio"))),
            ("Max Consecutive Wins", f"{metrics.get('max_consecutive_wins', 0):,}"),
            ("Max Consecutive Losses", f"{metrics.get('max_consecutive_losses', 0):,}"),
        ]

        for label, val in s1_rows:
            cells = tbl1.add_row().cells
            _set_cell_text(cells[0], label, bold=True)
            _set_cell_text(cells[1], val)

        # ── 2. Trade Statistics Breakdown ────────────────────────────────────
        doc.add_heading("2. Trade Statistics Breakdown", level=1)
        tbl2 = doc.add_table(rows=0, cols=2)
        tbl2.style = "Table Grid"

        tot_tr = metrics.get("total_trades", 0)
        p_tr = metrics.get("profit_trades", 0)
        p_tr_pct = metrics.get("profit_trades_pct", 0.0)
        l_tr = metrics.get("loss_trades", 0)
        l_tr_pct = metrics.get("loss_trades_pct", 0.0)

        s2_rows = [
            ("Total Trades", f"{tot_tr:,}"),
            ("Total Profit Trades (Amt & %)", f"{p_tr:,} ({p_tr_pct:.2f}%)"),
            ("Total Loss Trades (Amt & %)", f"{l_tr:,} ({l_tr_pct:.2f}%)"),
            ("Breakeven Trades", f"{metrics.get('breakeven_trades', 0):,}"),
            ("Long Trades (Won %)", metrics.get("long_trades_text", "N/A")),
            ("Short Trades (Won %)", metrics.get("short_trades_text", "N/A")),
            ("Average Win per Trade", _fmt_money(metrics.get("avg_win"))),
            ("Average Loss per Trade", _fmt_money(metrics.get("avg_loss"))),
            ("Largest Profit Trade", _fmt_money(metrics.get("largest_profit"))),
            ("Largest Loss Trade", _fmt_money(metrics.get("largest_loss"))),
            ("Gross Profit", _fmt_money(metrics.get("gross_profit"))),
            ("Gross Loss", _fmt_money(metrics.get("gross_loss"))),
        ]

        for label, val in s2_rows:
            cells = tbl2.add_row().cells
            _set_cell_text(cells[0], label, bold=True)
            _set_cell_text(cells[1], val)

        # ── 3. Averages & Holding Times ──────────────────────────────────────
        doc.add_heading("3. Averages & Holding Times", level=1)
        tbl3 = doc.add_table(rows=0, cols=2)
        tbl3.style = "Table Grid"

        s3_rows = [
            ("Average Trades per Month", f"{metrics.get('avg_trades_month', 0.0):.2f}"),
            ("Average Profit per Day", _fmt_money(metrics.get("avg_profit_day"))),
            ("Average Profit per Month", _fmt_money(metrics.get("avg_profit_month"))),
            ("Average Profit per Year", _fmt_money(metrics.get("avg_profit_year"))),
            ("Min Position Holding Time", metrics.get("min_hold_time", "N/A")),
            ("Max Position Holding Time", metrics.get("max_hold_time", "N/A")),
            ("Avg Position Holding Time", metrics.get("avg_hold_time", "N/A")),
            ("Historical Trading Days", f"{metrics.get('historical_trading_days', 0):,}"),
        ]

        for label, val in s3_rows:
            cells = tbl3.add_row().cells
            _set_cell_text(cells[0], label, bold=True)
            _set_cell_text(cells[1], val)

        # ── 4. Monthly Performance Heatmap ($ and %) ─────────────────────────
        doc.add_heading("4. Monthly Performance Heatmap ($ and %)", level=1)
        if heatmap_path and Path(heatmap_path).exists():
            doc.add_picture(str(heatmap_path), width=Inches(6.5))
            cap = doc.add_paragraph(
                "Monthly P&L is shown in dollars with the corresponding percentage calculated relative to the initial deposit. "
                "The Total column displays the full annual profit and percentage return."
            )
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.runs[0].font.size = Pt(8.5)
            cap.runs[0].font.italic = True

        # Monthly Table Grid
        if deals_df is not None and not deals_df.empty and pd is not None:
            try:
                df = deals_df.copy()
                df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
                df["Profit"] = pd.to_numeric(df["Profit"], errors="coerce").fillna(0.0)
                if "IsBalanceOperation" in df.columns:
                    df = df[~df["IsBalanceOperation"]]
                elif "Type" in df.columns:
                    df = df[df["Type"].astype(str).str.lower() != "balance"]

                df["Year"] = df["Time"].dt.year
                df["Month"] = df["Time"].dt.month
                monthly_p = df.groupby(["Year", "Month"])["Profit"].sum().unstack(fill_value=0.0)

                if not monthly_p.empty:
                    m_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                    hm_tbl = doc.add_table(rows=1, cols=14)
                    hm_tbl.style = "Table Grid"
                    hdr_cells = hm_tbl.rows[0].cells
                    _set_cell_text(hdr_cells[0], "Year", bold=True, font_size=Pt(8.5))
                    for i, m_name in enumerate(m_names, start=1):
                        _set_cell_text(hdr_cells[i], m_name, bold=True, font_size=Pt(8.5))
                    _set_cell_text(hdr_cells[13], "Total", bold=True, font_size=Pt(8.5))

                    eff_dep = metrics.get("effective_deposit", deposit) or 2500.0

                    for yr in sorted(monthly_p.index):
                        row_cells = hm_tbl.add_row().cells
                        _set_cell_text(row_cells[0], str(yr), bold=True, font_size=Pt(8.0))
                        yr_tot = 0.0
                        for m_num in range(1, 13):
                            val = float(monthly_p.loc[yr, m_num]) if m_num in monthly_p.columns else 0.0
                            yr_tot += val
                            pct = (val / eff_dep * 100.0) if eff_dep else 0.0

                            c_rgb = RGBColor(0, 128, 0) if val > 0 else (RGBColor(192, 0, 0) if val < 0 else RGBColor(80, 80, 80))
                            _set_cell_text(row_cells[m_num], f"${int(round(val))}\n({pct:+.1f}%)", bold=False, color_rgb=c_rgb, font_size=Pt(7.5))

                        yr_pct = (yr_tot / eff_dep * 100.0) if eff_dep else 0.0
                        tot_rgb = RGBColor(0, 128, 0) if yr_tot >= 0 else RGBColor(192, 0, 0)
                        _set_cell_text(row_cells[13], f"${int(round(yr_tot)):,}\n({yr_pct:+.1f}%)", bold=True, color_rgb=tot_rgb, font_size=Pt(8.0))
            except Exception as e:
                print(f"  [WARN] Word monthly table generation notice: {e}")

        # ── 5. Balance & Equity Growth Curves ─────────────────────────────────
        doc.add_heading("5. Balance & Equity Growth Curves", level=1)
        if "chart_equity_growth" in charts and Path(charts["chart_equity_growth"]).exists():
            doc.add_picture(str(charts["chart_equity_growth"]), width=Inches(6.5))

        if "chart_profit_dollars" in charts and Path(charts["chart_profit_dollars"]).exists():
            doc.add_picture(str(charts["chart_profit_dollars"]), width=Inches(6.5))

        if "chart_percent_gain" in charts and Path(charts["chart_percent_gain"]).exists():
            doc.add_picture(str(charts["chart_percent_gain"]), width=Inches(6.5))

        doc.save(str(doc_path))
        return doc_path
    except Exception as exc:
        print(f"  [WARN] Failed creating Word report: {exc}")
        return None


def generate_screener_market_report(
    report_path: Path,
    output_dir: Path,
    ea_name: str,
    symbol: str,
    deposit: float = 2500.0,
    set_file: str = "",
    period: str = "M15",
    from_date: str = "2013.01.01",
    to_date: str = "2026.07.03",
    resolved_symbol: str = "",
) -> dict:
    """
    Extracts report metrics, deals, generates equity charts, monthly heatmap,
    Word document research report with all requested sections, and structured summary in:
        markets_screened/<SYMBOL>/<EA>/
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    res_data = {
        "symbol": symbol,
        "resolved_symbol": resolved_symbol or symbol,
        "ea_name": ea_name,
        "period": period,
        "date_range": f"{from_date} -> {to_date}",
        "deposit": deposit,
        "net_profit": 0.0,
        "profit_pct": 0.0,
        "profit_factor": 0.0,
        "max_dd_pct": 0.0,
        "max_dd_dollars": 0.0,
        "total_trades": 0,
        "win_rate": 0.0,
        "sharpe": 0.0,
        "recovery_factor": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "status": "Completed",
        "files": {},
    }

    report_path = Path(report_path)
    if not report_path.exists():
        res_data["status"] = "Failed"
        res_data["error"] = f"Report file not found: {report_path}"
        return res_data

    # 1. Archive MT5 HTML Report
    dest_report = output_dir / "report.html"
    try:
        dest_report.write_bytes(report_path.read_bytes())
        res_data["files"]["report_html"] = dest_report.name
    except Exception as e:
        print(f"  [WARN] Failed to copy report.html: {e}")

    # 2. Archive screener_inputs.set if provided
    if set_file and Path(set_file).exists():
        try:
            dest_set = output_dir / "screener_inputs.set"
            dest_set.write_bytes(Path(set_file).read_bytes())
            res_data["files"]["set_file"] = dest_set.name
        except Exception as e:
            print(f"  [WARN] Failed to copy set file: {e}")

    # 3. Parse report using report_analysis.py
    parsed_report = {}
    try:
        parsed_report = analyze(report_path)
    except Exception as e:
        print(f"  [WARN] analyze(report_path) notice: {e}")

    deals_df = parsed_report.get("deals") if parsed_report else None

    # 4. Save deals to trades.csv if available
    trades_csv_path = output_dir / "trades.csv"
    if deals_df is not None and not deals_df.empty:
        try:
            deals_df.to_csv(trades_csv_path, index=False)
            res_data["files"]["trades_csv"] = trades_csv_path.name
        except Exception as e:
            print(f"  [WARN] Failed to save trades.csv: {e}")

    # 5. Calculate all required metrics
    comp_metrics = calculate_comprehensive_metrics(
        parsed_report=parsed_report,
        deals_df=deals_df,
        deposit=deposit,
        symbol=symbol,
    )

    res_data.update({
        "net_profit": round(comp_metrics["profit_loss_dollars"], 2),
        "profit_pct": round(comp_metrics["profit_loss_pct"], 2),
        "profit_factor": round(comp_metrics["profit_factor"], 2),
        "max_dd_pct": round(comp_metrics["max_balance_dd_pct"], 1),
        "max_dd_dollars": round(comp_metrics["max_balance_dd"], 2),
        "total_trades": comp_metrics["total_trades"],
        "win_rate": round(comp_metrics["profit_trades_pct"], 1),
        "sharpe": round(comp_metrics["sharpe_ratio"], 2),
        "recovery_factor": round(comp_metrics["recovery_factor"], 2),
        "avg_win": round(comp_metrics["avg_win"], 2),
        "avg_loss": round(comp_metrics["avg_loss"], 2),
        "status": "Passed" if (comp_metrics["profit_loss_dollars"] > 0 and comp_metrics["total_trades"] >= 10) else ("Profitable" if comp_metrics["profit_loss_dollars"] > 0 else ("0 Trades" if comp_metrics["total_trades"] == 0 else "Unprofitable")),
        "metrics_breakdown": comp_metrics,
    })

    # 6. Generate Equity Charts (if matplotlib and deals_df are available)
    chart_paths = {}
    if plt is not None and deals_df is not None and not deals_df.empty and pd is not None:
        try:
            df = deals_df.copy()
            if "Time" in df.columns and "Balance" in df.columns:
                df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
                df["Balance"] = pd.to_numeric(df["Balance"], errors="coerce")
                valid = df["Time"].notna() & df["Balance"].notna()
                df = df[valid].sort_values("Time")

                if len(df) >= 2:
                    times = df["Time"]
                    balance = df["Balance"]
                    start_bal = balance.iloc[0] if balance.iloc[0] > 0 else deposit
                    cum_profit = balance - start_bal
                    gain_pct = (cum_profit / start_bal) * 100.0

                    # 6A: Equity Growth Chart
                    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)
                    ax.set_facecolor("#0a0e1a")
                    fig.patch.set_facecolor("#0f172a")
                    ax.plot(times, balance, color="#10b981", linewidth=1.8, label="Balance ($)")
                    ax.set_title(f"{ea_name} — {symbol} ({period}) Equity Curve", color="#f8fafc", fontsize=12, fontweight="bold", pad=12)
                    ax.set_xlabel("Date", color="#94a3b8", fontsize=10)
                    ax.set_ylabel("Account Balance ($)", color="#94a3b8", fontsize=10)
                    ax.tick_params(colors="#94a3b8", labelsize=8)
                    ax.grid(True, color="#1e293b", linestyle="--", alpha=0.6)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
                    plt.xticks(rotation=30)
                    fig.tight_layout()
                    c1_path = output_dir / "chart_equity_growth.png"
                    fig.savefig(c1_path, facecolor=fig.get_facecolor(), edgecolor="none")
                    plt.close(fig)
                    chart_paths["chart_equity_growth"] = c1_path
                    res_data["files"]["equity_growth_chart"] = c1_path.name

                    # 6B: Profit Dollars Chart
                    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)
                    ax.set_facecolor("#0a0e1a")
                    fig.patch.set_facecolor("#0f172a")
                    ax.plot(times, cum_profit, color="#38bdf8", linewidth=1.8, label="Net Profit ($)")
                    ax.axhline(0, color="#64748b", linestyle=":", linewidth=1)
                    ax.set_title(f"{ea_name} — {symbol} Cumulative Profit ($)", color="#f8fafc", fontsize=12, fontweight="bold", pad=12)
                    ax.set_xlabel("Date", color="#94a3b8", fontsize=10)
                    ax.set_ylabel("Profit / Loss ($)", color="#94a3b8", fontsize=10)
                    ax.tick_params(colors="#94a3b8", labelsize=8)
                    ax.grid(True, color="#1e293b", linestyle="--", alpha=0.6)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
                    plt.xticks(rotation=30)
                    fig.tight_layout()
                    c2_path = output_dir / "chart_profit_dollars.png"
                    fig.savefig(c2_path, facecolor=fig.get_facecolor(), edgecolor="none")
                    plt.close(fig)
                    chart_paths["chart_profit_dollars"] = c2_path
                    res_data["files"]["profit_dollars_chart"] = c2_path.name

                    # 6C: Percentage Gain Chart
                    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)
                    ax.set_facecolor("#0a0e1a")
                    fig.patch.set_facecolor("#0f172a")
                    ax.plot(times, gain_pct, color="#f59e0b", linewidth=1.8, label="Gain %")
                    ax.axhline(0, color="#64748b", linestyle=":", linewidth=1)
                    ax.set_title(f"{ea_name} — {symbol} Percent Gain Growth (%)", color="#f8fafc", fontsize=12, fontweight="bold", pad=12)
                    ax.set_xlabel("Date", color="#94a3b8", fontsize=10)
                    ax.set_ylabel("Gain (%)", color="#94a3b8", fontsize=10)
                    ax.tick_params(colors="#94a3b8", labelsize=8)
                    ax.grid(True, color="#1e293b", linestyle="--", alpha=0.6)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
                    plt.xticks(rotation=30)
                    fig.tight_layout()
                    c3_path = output_dir / "chart_percent_gain.png"
                    fig.savefig(c3_path, facecolor=fig.get_facecolor(), edgecolor="none")
                    plt.close(fig)
                    chart_paths["chart_percent_gain"] = c3_path
                    res_data["files"]["percent_gain_chart"] = c3_path.name
        except Exception as e:
            print(f"  [WARN] Chart generation notice: {e}")

    # 7. Generate Monthly Performance Heatmap matching uploaded design
    heatmap_file = generate_monthly_performance_heatmap(
        deals_df=deals_df,
        deposit=deposit,
        output_dir=output_dir,
        ea_name=ea_name,
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
    )
    if heatmap_file:
        res_data["files"]["monthly_heatmap"] = heatmap_file.name

    # 8. Generate Word Document (.docx) Research Report with all required sections
    doc_path = output_dir / f"{ea_name}_{symbol}_Research_Report.docx"
    created_doc = create_screener_word_doc(
        doc_path=doc_path,
        ea_name=ea_name,
        symbol=symbol,
        resolved_symbol=resolved_symbol,
        period=period,
        from_date=from_date,
        to_date=to_date,
        deposit=deposit,
        metrics=comp_metrics,
        charts=chart_paths,
        heatmap_path=heatmap_file,
        deals_df=deals_df,
    )
    if created_doc:
        res_data["files"]["word_report"] = doc_path.name

    # 9. Save structured summary.json in output_dir
    summary_path = output_dir / "summary.json"
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(res_data, f, indent=2)
        res_data["files"]["summary_json"] = summary_path.name
    except Exception as e:
        print(f"  [WARN] Failed to save summary.json: {e}")

    return res_data
