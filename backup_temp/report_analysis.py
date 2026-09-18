r"""
report_analysis.py

Parses an MT5 Strategy Tester .htm/.html report directly (no pandas.read_html —
this report's HTML layout confuses it) and produces:
  - a curated, human-readable performance summary
  - monthly and yearly dollar/percentage performance, computed from the
    Deals table's running Balance column

Usage:
    from report_analysis import analyze

    result = analyze(r"C:\Users\HP\Desktop\MT5 runner\xaub_run_003\auto_report.htm")
    print_summary(result)
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Low-level parsing
# ---------------------------------------------------------------------------

def _read_html_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _parse_ea_inputs(table) -> dict:
    """The report's Settings block lists every actual input value used for
    this run (e.g. 'KCerPeriod1=20'). These rows have an empty label cell,
    which the generic key:value pairing above skips — so we extract them
    directly by pattern-matching bold cell text, independent of row layout.
    This is what actually verifies which parameters MT5 used, versus what
    you intended in your .set file."""
    inputs = {}
    for b in table.find_all("b"):
        text = b.get_text(strip=True)
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", text)
        if m:
            inputs[m.group(1)] = m.group(2)
    return inputs


def _parse_settings_and_results(table) -> dict:
    """First table: Settings + Results key/value blocks."""
    summary = {}
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        i = 0
        while i < len(cells) - 1:
            label = cells[i]
            if label.endswith(":"):
                key = label[:-1].strip()
                value = cells[i + 1]
                if key:
                    summary[key] = value
                i += 2
            else:
                i += 1
    return summary


def _parse_deals(table) -> pd.DataFrame:
    """Second table contains both an Orders section and a Deals section.
    We only want Deals (it has running Balance + realized Profit)."""
    deals_header_th = None
    for th in table.find_all("th"):
        if th.get_text(strip=True) == "Deals":
            deals_header_th = th
            break
    if deals_header_th is None:
        raise ValueError("Could not find 'Deals' section in report")

    header_tr = deals_header_th.find_parent("tr")
    rows = []
    columns = None
    for tr in header_tr.find_next_siblings("tr"):
        if tr.find("th"):
            break  # hit another section header — stop
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if columns is None:
            # This is the column-name row (Time, Deal, Symbol, Type, ...)
            columns = cells
            continue
        if len(cells) == len(columns):
            rows.append(cells)

    df = pd.DataFrame(rows, columns=columns)
    return _clean_deals(df)


def _to_float(s: str):
    s = (s or "").strip().replace(" ", "").replace("\xa0", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean_deals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Time" in df.columns:
        df["Time"] = pd.to_datetime(df["Time"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    for col in ("Volume", "Price", "Commission", "Swap", "Profit", "Balance"):
        if col in df.columns:
            df[col] = df[col].apply(_to_float)
    return df


def parse_report(path) -> dict:
    path = Path(path)
    html = _read_html_text(path)
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        raise ValueError(f"Expected at least 2 tables in report, found {len(tables)}")

    summary_raw = _parse_settings_and_results(tables[0])
    ea_inputs = _parse_ea_inputs(tables[0])
    deals = _parse_deals(tables[1])

    return {"summary_raw": summary_raw, "ea_inputs": ea_inputs, "deals": deals}


# ---------------------------------------------------------------------------
# Curated summary
# ---------------------------------------------------------------------------

def _split_paren(s: str):
    """'104 (57.69%)' -> ('104', '57.69%'); '7 (4 739.69)' -> ('7', '4 739.69')"""
    if s is None:
        return None, None
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", s.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return s.strip(), None


def _pct(s):
    if s is None:
        return None
    return _to_float(s.rstrip("%"))


def compute_curated_summary(parsed: dict) -> dict:
    raw = parsed["summary_raw"]
    deals = parsed["deals"]

    def get(key):
        return raw.get(key)

    short_main, short_extra = _split_paren(get("Short Trades (won %)"))
    long_main, long_extra = _split_paren(get("Long Trades (won %)"))
    profit_main, profit_extra = _split_paren(get("Profit Trades (% of total)"))
    loss_main, loss_extra = _split_paren(get("Loss Trades (% of total)"))
    bal_dd_main, bal_dd_extra = _split_paren(get("Balance Drawdown Maximal"))
    maxwin_main, maxwin_extra = _split_paren(get("Maximum consecutive wins ($)"))
    maxloss_main, maxloss_extra = _split_paren(get("Maximum consecutive losses ($)"))

    net_profit = _to_float(get("Total Net Profit"))
    bal_dd_abs = _to_float(bal_dd_main)

    final_balance = None
    initial_balance = None
    if "Balance" in deals.columns:
        bal_series = deals["Balance"].dropna()
        if len(bal_series):
            final_balance = bal_series.iloc[-1]
            initial_balance = bal_series.iloc[0]

    net_profit_pct = None
    if net_profit is not None and initial_balance:
        net_profit_pct = (net_profit / initial_balance) * 100

    curated = {
        "Total Trades": int(_to_float(get("Total Trades")) or 0),
        "Long Trades (count)": int(_to_float(long_main) or 0),
        "Long Trades Win %": _pct(long_extra),
        "Short Trades (count)": int(_to_float(short_main) or 0),
        "Short Trades Win %": _pct(short_extra),
        "Profit Trades (count)": int(_to_float(profit_main) or 0),
        "Profit Trades %": _pct(profit_extra),
        "Loss Trades (count)": int(_to_float(loss_main) or 0),
        "Loss Trades %": _pct(loss_extra),
        "Win Rate %": _pct(profit_extra),
        "Net Profit": net_profit,
        "Net Profit %": net_profit_pct,
        "Final Balance": final_balance,
        "Max Balance Drawdown ($)": bal_dd_abs,
        "Max Balance Drawdown (%)": _pct(bal_dd_extra),
        "Profit Factor": _to_float(get("Profit Factor")),
        "Sharpe Ratio": _to_float(get("Sharpe Ratio")),
        "Recovery Factor": _to_float(get("Recovery Factor")),
        "Return/Drawdown Ratio": (net_profit / bal_dd_abs) if (net_profit and bal_dd_abs) else None,
        "Largest Profit Trade": _to_float(get("Largest profit trade")),
        "Largest Loss Trade": _to_float(get("Largest loss trade")),
        "Average Profit Trade": _to_float(get("Average profit trade")),
        "Average Loss Trade": _to_float(get("Average loss trade")),
        "Max Consecutive Wins (count)": int(_to_float(maxwin_main) or 0),
        "Max Consecutive Wins ($)": _to_float(maxwin_extra),
        "Max Consecutive Losses (count)": int(_to_float(maxloss_main) or 0),
        "Max Consecutive Losses ($)": _to_float(maxloss_extra),
        "Minimal Position Holding Time": get("Minimal position holding time"),
        "Maximal Position Holding Time": get("Maximal position holding time"),
        "Average Position Holding Time": get("Average position holding time"),
    }
    return curated


# ---------------------------------------------------------------------------
# Monthly / yearly performance from the Deals balance trail
# ---------------------------------------------------------------------------

def compute_period_performance(deals: pd.DataFrame):
    df = deals.dropna(subset=["Balance", "Time"]).sort_values("Time").copy()
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    initial_balance = df["Balance"].iloc[0]

    def _period_table(period_freq: str, label: str) -> pd.DataFrame:
        df["_period"] = df["Time"].dt.to_period(period_freq)
        grouped = df.groupby("_period")["Balance"].last().to_frame("end_balance")
        grouped["start_balance"] = grouped["end_balance"].shift(1)
        grouped["start_balance"] = grouped["start_balance"].fillna(initial_balance)
        grouped["dollar_change"] = grouped["end_balance"] - grouped["start_balance"]
        grouped["pct_change"] = (grouped["dollar_change"] / grouped["start_balance"]) * 100
        grouped.index.name = label
        return grouped.reset_index()

    monthly = _period_table("M", "Month")
    yearly = _period_table("Y", "Year")
    return monthly, yearly


# ---------------------------------------------------------------------------
# Top-level convenience + printing
# ---------------------------------------------------------------------------

def analyze(path) -> dict:
    parsed = parse_report(path)
    curated = compute_curated_summary(parsed)
    monthly, yearly = compute_period_performance(parsed["deals"])
    return {
        "curated_summary": curated,
        "ea_inputs": parsed["ea_inputs"],
        "monthly": monthly,
        "yearly": yearly,
        "deals": parsed["deals"],  # kept for anyone who wants the raw trades later
    }


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def print_summary(result: dict) -> None:
    c = result["curated_summary"]

    print("=" * 60)
    print("EA INPUTS ACTUALLY USED THIS RUN")
    print("=" * 60)
    for k, v in result["ea_inputs"].items():
        print(f"  {k} = {v}")
    print("(Compare this against your .set file — if these don't match")
    print(" what you saved, the .set file isn't being applied.)")
    print()

    print("=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    print(f"Total Trades:              {c['Total Trades']}")
    print(f"  Long  (won %):           {c['Long Trades (count)']} ({_fmt(c['Long Trades Win %'])}%)")
    print(f"  Short (won %):           {c['Short Trades (count)']} ({_fmt(c['Short Trades Win %'])}%)")
    print(f"  Profit trades:           {c['Profit Trades (count)']} ({_fmt(c['Profit Trades %'])}%)")
    print(f"  Loss trades:             {c['Loss Trades (count)']} ({_fmt(c['Loss Trades %'])}%)")
    print(f"Win Rate:                  {_fmt(c['Win Rate %'])}%")
    print("-" * 60)
    print(f"Net Profit:                {_fmt(c['Net Profit'])} ({_fmt(c['Net Profit %'])}%)")
    print(f"Final Balance:             {_fmt(c['Final Balance'])}")
    print(f"Max Balance Drawdown:      {_fmt(c['Max Balance Drawdown ($)'])} "
          f"({_fmt(c['Max Balance Drawdown (%)'])}%)")
    print("-" * 60)
    print(f"Profit Factor:             {_fmt(c['Profit Factor'])}")
    print(f"Sharpe Ratio:              {_fmt(c['Sharpe Ratio'])}")
    print(f"Recovery Factor:           {_fmt(c['Recovery Factor'])}")
    print(f"Return/Drawdown Ratio:     {_fmt(c['Return/Drawdown Ratio'])}")
    print("-" * 60)
    print(f"Largest Profit Trade:      {_fmt(c['Largest Profit Trade'])}")
    print(f"Largest Loss Trade:        {_fmt(c['Largest Loss Trade'])}")
    print(f"Average Profit Trade:      {_fmt(c['Average Profit Trade'])}")
    print(f"Average Loss Trade:        {_fmt(c['Average Loss Trade'])}")
    print("-" * 60)
    print(f"Max Consecutive Wins:      {c['Max Consecutive Wins (count)']} "
          f"({_fmt(c['Max Consecutive Wins ($)'])})")
    print(f"Max Consecutive Losses:    {c['Max Consecutive Losses (count)']} "
          f"({_fmt(c['Max Consecutive Losses ($)'])})")
    print("-" * 60)
    print(f"Min Position Holding Time: {c['Minimal Position Holding Time']}")
    print(f"Max Position Holding Time: {c['Maximal Position Holding Time']}")
    print(f"Avg Position Holding Time: {c['Average Position Holding Time']}")
    print("=" * 60)

    print("\nYEARLY PERFORMANCE (full history)")
    yearly = result["yearly"]
    for _, row in yearly.iterrows():
        print(f"  {row['Year']}: {row['dollar_change']:>12,.2f}  ({row['pct_change']:>7.2f}%)")

    print("\nMONTHLY PERFORMANCE (full history)")
    monthly = result["monthly"]
    current_year = None
    for _, row in monthly.iterrows():
        month_period = row["Month"]
        year = month_period.year
        if year != current_year:
            if current_year is not None:
                year_row = yearly[yearly["Year"].astype(str) == str(current_year)]
                if len(year_row):
                    yr = year_row.iloc[0]
                    print(f"  {'':>7} {'-'*10} year total: {yr['dollar_change']:>12,.2f}  "
                          f"({yr['pct_change']:>7.2f}%)")
            print(f"  {year}:")
            current_year = year
        print(f"    {month_period.strftime('%b')}: {row['dollar_change']:>12,.2f}  "
              f"({row['pct_change']:>7.2f}%)")
    # print the final year's total after the loop ends
    if current_year is not None:
        year_row = yearly[yearly["Year"].astype(str) == str(current_year)]
        if len(year_row):
            yr = year_row.iloc[0]
            print(f"  {'':>7} {'-'*10} year total: {yr['dollar_change']:>12,.2f}  "
                  f"({yr['pct_change']:>7.2f}%)")


if __name__ == "__main__":
    import sys
    result = analyze(sys.argv[1])
    print_summary(result)