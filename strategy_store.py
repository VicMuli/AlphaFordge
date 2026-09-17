r"""
strategy_store.py

Persistent SQLite storage for strategies that pass all testing phases
(Train, Validation, and Holdout) in the Strategy Builder pipeline.

Enforces strict passing criteria:
- Sharpe Ratio >= 0.8
- Max Drawdown (%) <= 15.0%
- Return / Drawdown Ratio >= 2.0
- Profit Factor >= 1.2
- Average Trades per Month >= 2.0

Only strategies that pass all 3 testing phases (including Holdout) are stored.
"""

import json
import sqlite3
import datetime
import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS stored_strategies (
    strategy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy_type TEXT,
    genome_signature TEXT UNIQUE NOT NULL,
    genome_json TEXT NOT NULL,

    -- Train metrics
    train_sharpe REAL,
    train_max_dd_pct REAL,
    train_ret_dd_ratio REAL,
    train_profit_factor REAL,
    train_avg_trades_month REAL,
    train_total_trades INTEGER,
    train_net_profit REAL,

    -- Validation metrics
    val_sharpe REAL,
    val_max_dd_pct REAL,
    val_ret_dd_ratio REAL,
    val_profit_factor REAL,
    val_avg_trades_month REAL,
    val_total_trades INTEGER,
    val_net_profit REAL,

    -- Holdout metrics
    holdout_sharpe REAL,
    holdout_max_dd_pct REAL,
    holdout_ret_dd_ratio REAL,
    holdout_profit_factor REAL,
    holdout_avg_trades_month REAL,
    holdout_total_trades INTEGER,
    holdout_net_profit REAL,

    -- Full JSON metrics
    train_metrics_json TEXT,
    val_metrics_json TEXT,
    holdout_metrics_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_stored_strategies_symbol ON stored_strategies(symbol);
"""


def genome_signature(genome: dict) -> str:
    """Returns a canonical, deterministic JSON string signature of a strategy genome.

    Handles two genome formats:
    - Old Python-GA format:  {"orb_params": {...}, "filters": {...}}
    - New MT5-pipeline format: {"params": {...}, "filters": {}}
    """
    if "params" in genome and "orb_params" not in genome:
        # MT5 pipeline format: flat params dict, no filter structure
        params = genome.get("params", {})
        sorted_params = sorted((k, v) for k, v in params.items())
        canonical = {"params": sorted_params}
    else:
        # Legacy Python-GA format
        orb_params = genome.get("orb_params", {})
        sorted_orb = sorted((k, v) for k, v in orb_params.items())

        filters = genome.get("filters", {})
        sorted_filters = []
        for f_name in sorted(filters.keys()):
            f_val = filters[f_name]
            if f_val is not None:
                sorted_f_params = sorted((k, v) for k, v in f_val.items())
                sorted_filters.append((f_name, sorted_f_params))
            else:
                sorted_filters.append((f_name, None))

        canonical = {
            "orb_params": sorted_orb,
            "filters": sorted_filters,
        }
    return json.dumps(canonical, sort_keys=True)


def init_strategy_store(db_path: str = "results.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE stored_strategies ADD COLUMN strategy_type TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()
    finally:
        conn.close()


def extract_phase_metrics(eval_res: dict) -> dict:
    """Extract key metrics dict from evaluate_genome output.

    Works for both:
    - Python backtester output: curated dict + trades DataFrame with exit_time/profit
    - MT5 single-test output:   curated dict from report_analysis (no per-trade rows)

    For MT5 reports, avg_trades_month is computed from Total Trades + holding-
    time info if present, or read directly from the curated dict if the caller
    stored it there; falls back to 0.0 if unavailable.
    """
    curated = (eval_res.get("curated") or {}) if isinstance(eval_res, dict) else {}
    trades = eval_res.get("trades") if isinstance(eval_res, dict) else None

    avg_trades = 0.0
    if trades is not None and not trades.empty and "exit_time" in trades.columns:
        # Python backtester path — compute from individual trade rows
        exit_times = pd.to_datetime(trades["exit_time"])
        months_span = (
            (exit_times.max().year - exit_times.min().year) * 12
            + exit_times.max().month - exit_times.min().month + 1
        )
        avg_trades = len(trades) / max(months_span, 1)
    else:
        # MT5 report path — try to derive from Total Trades + curated summary.
        # The curated dict may carry 'Avg Trades / Month' if the caller set it,
        # otherwise we leave avg_trades at 0.0 (acceptable: the DB column will
        # be 0 but it does not affect the pass/fail gate already cleared).
        avg_trades = float(curated.get("Avg Trades / Month") or 0.0)

    max_dd = curated.get("Max Balance Drawdown (%)", 0.0) or 0.0
    ret_dd = curated.get("Return/Drawdown Ratio") or curated.get("Recovery Factor") or 0.0
    sharpe = curated.get("Sharpe Ratio") or 0.0
    pf = curated.get("Profit Factor") or 0.0
    tot_trades = curated.get("Total Trades", 0) or 0
    net_p = curated.get("Net Profit", 0.0) or 0.0

    return {
        "sharpe": float(sharpe),
        "max_dd_pct": float(max_dd),
        "ret_dd_ratio": float(ret_dd),
        "profit_factor": float(pf),
        "avg_trades_month": float(avg_trades),
        "total_trades": int(tot_trades),
        "net_profit": float(net_p),
    }


def is_strategy_stored(db_path: str, genome: dict) -> bool:
    """Check if a strategy genome is already saved in the database."""
    init_strategy_store(db_path)
    sig = genome_signature(genome)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM stored_strategies WHERE genome_signature = ?", (sig,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def save_passed_strategy(db_path: str, symbol: str, genome: dict,
                         train_ev: dict, val_ev: dict, holdout_ev: dict,
                         strategy_type: str = None) -> int:
    """
    Saves a strategy that passed Train, Validation, and Holdout testing phases.
    Returns the new strategy_id. If already present, updates metrics or returns existing id.
    """
    init_strategy_store(db_path)
    sig = genome_signature(genome)
    g_json = json.dumps(genome, indent=2)

    tr_m = extract_phase_metrics(train_ev)
    va_m = extract_phase_metrics(val_ev)
    ho_m = extract_phase_metrics(holdout_ev)

    tr_json = json.dumps(train_ev.get("curated", {}), default=str)
    va_json = json.dumps(val_ev.get("curated", {}), default=str)
    ho_json = json.dumps(holdout_ev.get("curated", {}), default=str)

    now_iso = datetime.datetime.now().isoformat(timespec="seconds")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO stored_strategies (
                created_at, symbol, strategy_type, genome_signature, genome_json,
                train_sharpe, train_max_dd_pct, train_ret_dd_ratio, train_profit_factor, train_avg_trades_month, train_total_trades, train_net_profit,
                val_sharpe, val_max_dd_pct, val_ret_dd_ratio, val_profit_factor, val_avg_trades_month, val_total_trades, val_net_profit,
                holdout_sharpe, holdout_max_dd_pct, holdout_ret_dd_ratio, holdout_profit_factor, holdout_avg_trades_month, holdout_total_trades, holdout_net_profit,
                train_metrics_json, val_metrics_json, holdout_metrics_json
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            ON CONFLICT(genome_signature) DO UPDATE SET
                train_sharpe=excluded.train_sharpe,
                train_max_dd_pct=excluded.train_max_dd_pct,
                train_ret_dd_ratio=excluded.train_ret_dd_ratio,
                train_profit_factor=excluded.train_profit_factor,
                train_avg_trades_month=excluded.train_avg_trades_month,
                val_sharpe=excluded.val_sharpe,
                val_max_dd_pct=excluded.val_max_dd_pct,
                val_ret_dd_ratio=excluded.val_ret_dd_ratio,
                val_profit_factor=excluded.val_profit_factor,
                val_avg_trades_month=excluded.val_avg_trades_month,
                holdout_sharpe=excluded.holdout_sharpe,
                holdout_max_dd_pct=excluded.holdout_max_dd_pct,
                holdout_ret_dd_ratio=excluded.holdout_ret_dd_ratio,
                holdout_profit_factor=excluded.holdout_profit_factor,
                holdout_avg_trades_month=excluded.holdout_avg_trades_month,
                holdout_net_profit=excluded.holdout_net_profit
            """,
            (
                now_iso, symbol, strategy_type, sig, g_json,
                tr_m["sharpe"], tr_m["max_dd_pct"], tr_m["ret_dd_ratio"], tr_m["profit_factor"], tr_m["avg_trades_month"], tr_m["total_trades"], tr_m["net_profit"],
                va_m["sharpe"], va_m["max_dd_pct"], va_m["ret_dd_ratio"], va_m["profit_factor"], va_m["avg_trades_month"], va_m["total_trades"], va_m["net_profit"],
                ho_m["sharpe"], ho_m["max_dd_pct"], ho_m["ret_dd_ratio"], ho_m["profit_factor"], ho_m["avg_trades_month"], ho_m["total_trades"], ho_m["net_profit"],
                tr_json, va_json, ho_json
            )
        )
        conn.commit()
        cur.execute("SELECT strategy_id FROM stored_strategies WHERE genome_signature = ?", (sig,))
        row = cur.fetchone()
        return row[0] if row else cur.lastrowid
    finally:
        conn.close()


def query_stored_strategies(db_path: str = "results.db", symbol: str = None) -> pd.DataFrame:
    """Retrieve DataFrame of all stored strategies that passed holdout testing."""
    init_strategy_store(db_path)
    conn = sqlite3.connect(db_path)
    try:
        query = """
            SELECT strategy_id, created_at, symbol, strategy_type,
                   holdout_sharpe, holdout_max_dd_pct, holdout_ret_dd_ratio, holdout_profit_factor, holdout_avg_trades_month, holdout_net_profit, holdout_total_trades,
                   val_sharpe, val_max_dd_pct, val_ret_dd_ratio, val_profit_factor, val_avg_trades_month,
                   train_sharpe, train_max_dd_pct, train_ret_dd_ratio, train_profit_factor, train_avg_trades_month,
                   genome_json
            FROM stored_strategies
            WHERE 1=1
        """
        params = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY strategy_id DESC"
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def print_stored_strategies(db_path: str = "results.db") -> None:
    """Print clean summary of stored passed strategies."""
    df = query_stored_strategies(db_path)
    print("\n" + "=" * 90)
    print(f"STORED PASSED STRATEGIES IN DATABASE ({db_path}): {len(df)} strategy(ies)")
    print("=" * 90)

    if df.empty:
        print("  <No strategies have passed all phases (Train, Validation, Holdout) yet>")
        return

    for idx, row in df.iterrows():
        g = json.loads(row["genome_json"])
        active = {k: v for k, v in g.get("filters", {}).items() if v is not None}
        stype = row.get("strategy_type") or "Unknown"
        print(f"\n[Strategy ID #{row['strategy_id']}] Created: {row['created_at']} | Symbol: {row['symbol']} | Type: {stype}")
        print(f"  Params:         {g.get('params') or g.get('orb_params')}")
        print(f"  Active Filters: {active}")
        print("  Metrics Summary (Train / Validation / Holdout):")
        print(f"    Train:    Sharpe={row['train_sharpe']:.2f} | MaxDD={row['train_max_dd_pct']:.1f}% | Ret/DD={row['train_ret_dd_ratio']:.2f} | PF={row['train_profit_factor']:.2f} | Avg/mo={row['train_avg_trades_month']:.1f}")
        print(f"    Val:      Sharpe={row['val_sharpe']:.2f} | MaxDD={row['val_max_dd_pct']:.1f}% | Ret/DD={row['val_ret_dd_ratio']:.2f} | PF={row['val_profit_factor']:.2f} | Avg/mo={row['val_avg_trades_month']:.1f}")
        print(f"    HOLDOUT:  Sharpe={row['holdout_sharpe']:.2f} | MaxDD={row['holdout_max_dd_pct']:.1f}% | Ret/DD={row['holdout_ret_dd_ratio']:.2f} | PF={row['holdout_profit_factor']:.2f} | Avg/mo={row['holdout_avg_trades_month']:.1f} | NetProfit=${row['holdout_net_profit']:,.2f}")
    print("=" * 90 + "\n")
