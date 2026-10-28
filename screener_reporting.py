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
    6. monthly_heatmap.png (monthly performance heatmap matrix)
    7. <EA>_<SYMBOL>_Research_Report.docx (Word Document research report)
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
    Word document research report, and structured summary in:
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

    curated = parsed_report.get("curated_summary", {}) if parsed_report else {}
    deals_df = parsed_report.get("deals") if parsed_report else None

    # Base metrics from curated summary
    net_p = _safe_float(curated.get("Net Profit") or curated.get("Total Net Profit"))
    trades_count = _safe_int(curated.get("Total Trades"))
    pf = _safe_float(curated.get("Profit Factor"))
    dd_pct = _safe_float(curated.get("Max Balance Drawdown (%)") or curated.get("Balance Drawdown Relative"))
    dd_dollars = _safe_float(curated.get("Max Balance Drawdown ($)") or curated.get("Balance Drawdown Maximal"))
    wr = _safe_float(curated.get("Win Rate %") or curated.get("Profit Trades (% of total)"))
    sharpe = _safe_float(curated.get("Sharpe Ratio"))
    rec_factor = _safe_float(curated.get("Recovery Factor"))

    # 4. Save deals to trades.csv if available
    trades_csv_path = output_dir / "trades.csv"
    if deals_df is not None and not deals_df.empty:
        try:
            deals_df.to_csv(trades_csv_path, index=False)
            res_data["files"]["trades_csv"] = trades_csv_path.name
        except Exception as e:
            print(f"  [WARN] Failed to save trades.csv: {e}")

    # 5. Calculate derived metrics from deals_df if available
    if deals_df is not None and not deals_df.empty and pd is not None:
        try:
            df = deals_df.copy()
            if "Profit" in df.columns:
                df["Profit"] = pd.to_numeric(df["Profit"], errors="coerce").fillna(0.0)
                win_trades = df[df["Profit"] > 0]
                loss_trades = df[df["Profit"] < 0]
                if trades_count == 0:
                    trades_count = len(df[df["Profit"] != 0])
                if len(win_trades) > 0:
                    res_data["avg_win"] = round(float(win_trades["Profit"].mean()), 2)
                if len(loss_trades) > 0:
                    res_data["avg_loss"] = round(float(loss_trades["Profit"].mean()), 2)
                if trades_count > 0 and wr == 0:
                    wr = round((len(win_trades) / trades_count) * 100.0, 1)
                if net_p == 0 and "Balance" in df.columns:
                    b_num = pd.to_numeric(df["Balance"], errors="coerce").dropna()
                    if len(b_num) >= 2:
                        net_p = round(float(b_num.iloc[-1] - b_num.iloc[0]), 2)
        except Exception as e:
            print(f"  [WARN] Derived deals calculation notice: {e}")

    profit_pct = round((net_p / deposit) * 100.0, 2) if deposit > 0 else 0.0

    res_data.update({
        "net_profit": round(net_p, 2),
        "profit_pct": profit_pct,
        "profit_factor": round(pf, 2),
        "max_dd_pct": round(dd_pct, 1),
        "max_dd_dollars": round(dd_dollars, 2),
        "total_trades": trades_count,
        "win_rate": round(wr, 1),
        "sharpe": round(sharpe, 2),
        "recovery_factor": round(rec_factor, 2),
        "status": "Passed" if (net_p > 0 and trades_count >= 10) else ("Profitable" if net_p > 0 else ("0 Trades" if trades_count == 0 else "Unprofitable")),
    })

    # 6. Generate Equity Charts (if matplotlib and deals_df are available)
    chart_files = {}
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
                    chart_files["chart_equity_growth"] = c1_path.name

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
                    chart_files["chart_profit_dollars"] = c2_path.name

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
                    chart_files["chart_percent_gain"] = c3_path.name

                    # 6D: Monthly Heatmap
                    if "Profit" in df.columns:
                        df["Year"] = df["Time"].dt.year
                        df["Month"] = df["Time"].dt.month
                        monthly_pnl = df.groupby(["Year", "Month"])["Profit"].sum().unstack(fill_value=0)
                        if not monthly_pnl.empty:
                            years = list(monthly_pnl.index)
                            matrix = np.zeros((len(years), 13), dtype=float)
                            for yr_idx, yr in enumerate(years):
                                for m_idx in range(1, 13):
                                    if m_idx in monthly_pnl.columns:
                                        matrix[yr_idx, m_idx - 1] = float(monthly_pnl.loc[yr, m_idx])
                                matrix[yr_idx, 12] = matrix[yr_idx, :12].sum()

                            fig, ax = plt.subplots(figsize=(11, max(3.0, 0.9 + 0.45 * len(years))), dpi=150)
                            vmax = float(np.max(np.abs(matrix[:, :12]))) if matrix.size else 1.0
                            if vmax == 0:
                                vmax = 1.0
                            ax.imshow(matrix[:, :12], aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax,
                                      extent=(-0.5, 11.5, len(years) - 0.5, -0.5))
                            ax.set_xlim(-0.5, 12.5)
                            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Total"]
                            ax.set_xticks(range(13))
                            ax.set_xticklabels(months, fontsize=9, fontweight="bold")
                            ax.set_yticks(range(len(years)))
                            ax.set_yticklabels([str(y) for y in years], fontsize=9, fontweight="bold")
                            ax.set_title(f"{ea_name} — {symbol} Monthly P&L ($)", fontsize=12, fontweight="bold", pad=12)

                            for yr_idx in range(len(years)):
                                for m_idx in range(12):
                                    v = matrix[yr_idx, m_idx]
                                    if v != 0:
                                        ax.text(m_idx, yr_idx, f"{int(v)}", ha="center", va="center",
                                                fontsize=8, color="#000" if abs(v) < vmax * 0.7 else "#fff")
                                tot = matrix[yr_idx, 12]
                                ax.text(12, yr_idx, f"${int(tot):,}", ha="center", va="center",
                                        fontsize=8, fontweight="bold", color="#10b981" if tot >= 0 else "#ef4444")

                            fig.tight_layout()
                            h_path = output_dir / "monthly_heatmap.png"
                            fig.savefig(h_path, bbox_inches="tight")
                            plt.close(fig)
                            chart_files["monthly_heatmap"] = h_path.name
        except Exception as e:
            print(f"  [WARN] Chart/Heatmap generation notice: {e}")

    res_data["files"].update(chart_files)

    # 7. Generate Word Document (.docx) Research Report
    if docx is not None:
        try:
            doc = docx.Document()
            title = doc.add_heading(f"Strategy Research Report: {ea_name} — {symbol}", 0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER

            p_meta = doc.add_paragraph()
            p_meta.add_run(f"Symbol: {symbol} (MT5: {resolved_symbol or symbol})\n")
            p_meta.add_run(f"Timeframe: {period} | Date Range: {from_date} -> {to_date}\n")
            p_meta.add_run(f"Deposit: ${deposit:,.2f} | Net Profit: ${net_p:,.2f} ({profit_pct:.1f}%)\n")
            p_meta.add_run(f"Generated by AlphaForge Strategy Screener\n")

            # Performance Summary Table
            doc.add_heading("1. Executive Performance Metrics", level=1)
            tbl = doc.add_table(rows=7, cols=2)
            tbl.style = "Table Grid"
            metrics_rows = [
                ("Net Profit", f"${net_p:,.2f} ({profit_pct:.1f}%)"),
                ("Profit Factor", f"{pf:.2f}"),
                ("Total Closed Trades", str(trades_count)),
                ("Win Rate", f"{wr:.1f}%"),
                ("Max Balance Drawdown", f"${dd_dollars:,.2f} ({dd_pct:.1f}%)"),
                ("Sharpe Ratio", f"{sharpe:.2f}"),
                ("Recovery Factor", f"{rec_factor:.2f}"),
            ]
            for idx, (label, val) in enumerate(metrics_rows):
                row_cells = tbl.rows[idx].cells
                row_cells[0].text = label
                row_cells[1].text = val

            # Embed charts if created
            if "chart_equity_growth" in chart_files:
                doc.add_heading("2. Balance & Equity Growth Curve", level=1)
                doc.add_picture(str(output_dir / chart_files["chart_equity_growth"]), width=Inches(6.2))

            if "monthly_heatmap" in chart_files:
                doc.add_heading("3. Monthly Performance Heatmap", level=1)
                doc.add_picture(str(output_dir / chart_files["monthly_heatmap"]), width=Inches(6.2))

            doc_path = output_dir / f"{ea_name}_{symbol}_Research_Report.docx"
            doc.save(str(doc_path))
            res_data["files"]["word_doc"] = doc_path.name
        except Exception as e:
            print(f"  [WARN] Word document generation notice: {e}")

    # 8. Save structured summary.json in output_dir
    summary_path = output_dir / "summary.json"
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(res_data, f, indent=2)
        res_data["files"]["summary_json"] = summary_path.name
    except Exception as e:
        print(f"  [WARN] Failed to save summary.json: {e}")

    return res_data
