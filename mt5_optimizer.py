r"""
mt5_optimizer.py

Automates MT5's built-in Optimization mode (local multi-agent — MT5 uses
your PC's CPU cores automatically once optimization starts; no separate
"engine" to build for that part). This is genuinely different from
mt5_runner.py's single-test automation: different .ini settings, a
parameter-RANGE .set file instead of one fixed .set, and a different
report format (an XML with one row per tested combination, not an HTML
single-run report).

HONESTY NOTE ON THIS MODULE: the .set range-file format and the
optimization XML report schema below are written from documentation/
training knowledge, NOT verified against a live MT5 instance (unlike the
EA logic elsewhere in this pipeline, which was verified in Python where
possible). Compile/run this for real and send back whatever the actual
.set format MT5 expects or the actual exported XML looks like if either
doesn't work — same iterative fix pattern used for the earlier EA/script
issues.

REQUIRES: the EA must have OnTester() defined (mql5_translator.py now
generates this) and the .ini must set OptimizationCriterion=6 so MT5
ranks passes by OUR fitness score, not a generic built-in metric.

Usage:
    from mt5_optimizer import (
        generate_optimization_set_file, run_optimization, parse_optimization_results
    )

    generate_optimization_set_file(
        fixed_params={"InpFixedLotSize": 0.10, "InpPipSize": 0.0001, "InpMagicNumber": 20240101},
        ranges={
            "InpTPRatio": (1.0, 0.25, 3.0),        # (start, step, stop)
            "InpSLBufferPips": (0, 1, 10),
            "InpRangeEndHour": (9, 1, 12),
        },
        output_path=r"C:\...\MQL5\Profiles\Tester\ORB_opt.set",
    )

    report_path = run_optimization(
        terminal_path=r"C:\...\terminal64.exe",
        terminal_data_dir=r"C:\...\Terminal\<id>",
        expert="ORBEU1.ex5",
        set_file="ORB_opt.set",
        symbol="EURUSD dukascopy",   # the Custom Symbol built from Dukascopy data
        period="M1",
        from_date="2013.01.01", to_date="2026.07.03",
        deposit=100_000,
        work_dir=r"C:\...\opt_runs\eurusd_orb",
        login="...", password="...", server="ICMarketsKE-Demo",
        report_name="orb_opt_report",
    )

    results_df = parse_optimization_results(report_path)
    print(results_df.sort_values("Result", ascending=False).head(20))
"""

import os
import sys
import shutil
import re
import time
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# Prevent Windows console UnicodeEncodeError
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd


# ---------------------------------------------------------------------------
# EA & Parameter Synchronization
# ---------------------------------------------------------------------------

def sync_ea_to_mt5(expert: str, terminal_data_dir: str, terminal_path: str = None) -> str:
    """
    Ensures that the requested EA (.ex5) exists in <terminal_data_dir>/MQL5/Experts/.
    If not found in MT5 Experts, searches researched_strategies/, strategies/, or workspace.
    If only .mq5 exists, attempts to compile it with metaeditor64.exe if available.
    Returns the resolved filename inside MQL5/Experts.
    """
    clean_expert = Path(expert).name
    if not clean_expert.lower().endswith(".ex5"):
        clean_expert += ".ex5"
    ea_stem = clean_expert[:-4]

    mt5_experts_dir = Path(terminal_data_dir) / "MQL5" / "Experts"
    mt5_experts_dir.mkdir(parents=True, exist_ok=True)
    target_path = mt5_experts_dir / clean_expert

    # If already present in MT5 Experts and non-empty, return
    if target_path.is_file() and target_path.stat().st_size > 0:
        return clean_expert

    # Search for matching .ex5 in workspace folders
    workspace_dir = Path(__file__).resolve().parent
    search_dirs = [
        workspace_dir / "researched_strategies",
        workspace_dir / "strategies",
        workspace_dir,
    ]

    found_ex5 = None
    found_mq5 = None

    for sdir in search_dirs:
        if not sdir.exists():
            continue
        for sub in sdir.rglob("*"):
            if sub.is_file():
                if sub.name.lower() == clean_expert.lower():
                    found_ex5 = sub
                    break
                elif sub.name.lower() == f"{ea_stem.lower()}.mq5":
                    found_mq5 = sub
        if found_ex5:
            break

    if found_ex5:
        try:
            shutil.copy2(found_ex5, target_path)
            print(f"  [OK] Synchronized EA binary to MT5 Experts: {clean_expert} (from {found_ex5.parent.name})")
            return clean_expert
        except Exception as e:
            print(f"  [WARN] Failed to copy {found_ex5} to {target_path}: {e}")

    # If no .ex5, try compiling .mq5 with MetaEditor
    if found_mq5 and terminal_path:
        metaeditor_path = Path(terminal_path).parent / "metaeditor64.exe"
        if metaeditor_path.exists():
            print(f"  [>] Compiling {found_mq5.name} with MetaEditor...")
            compile_log = mt5_experts_dir / "compile.log"
            cmd_comp = [str(metaeditor_path), f"/compile:{found_mq5}", f"/log:{compile_log}"]
            try:
                subprocess.run(cmd_comp, capture_output=True, text=True, timeout=60)
                expected_ex5 = found_mq5.with_suffix(".ex5")
                if expected_ex5.exists():
                    shutil.copy2(expected_ex5, target_path)
                    print(f"  [OK] Compiled and synchronized {clean_expert} to MT5 Experts!")
                    return clean_expert
            except Exception as ce:
                print(f"  [WARN] MetaEditor compilation failed: {ce}")

    if not target_path.exists() or target_path.stat().st_size == 0:
        print(f"  [WARN] EA binary '{clean_expert}' not found in MT5 Experts directory ({mt5_experts_dir}).")

    return clean_expert


def _read_latest_mt5_tester_log(terminal_data_dir: str) -> str:
    """Reads the most recent MT5 tester log to extract termination / error details."""
    tester_logs_dir = Path(terminal_data_dir) / "Tester" / "logs"
    mql5_logs_dir = Path(terminal_data_dir) / "MQL5" / "Logs"

    candidate_files = []
    for ldir in (tester_logs_dir, mql5_logs_dir):
        if ldir.exists():
            candidate_files.extend(list(ldir.glob("*.log")))

    if not candidate_files:
        return "(No MT5 log files found in Tester/logs or MQL5/Logs)"

    candidate_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    newest_log = candidate_files[0]

    try:
        content = ""
        for enc in ("utf-16", "utf-16-le", "utf-8", "cp1252", "latin-1"):
            try:
                content = newest_log.read_text(encoding=enc, errors="replace")
                break
            except Exception:
                continue

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        tail = lines[-25:] if len(lines) > 25 else lines
        return f"Log file ({newest_log.name}):\n" + "\n".join(f"    {ln}" for ln in tail)
    except Exception as e:
        return f"(Could not read {newest_log}: {e})"


# ---------------------------------------------------------------------------
# .set range-file generation
# ---------------------------------------------------------------------------

def _fmt_set_val(v) -> str:
    """Format a scalar value for a .set file line, writing whole numbers as integers."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e12:
            return str(int(v))
        return str(float(f"{v:.8g}"))
    return str(v)


def generate_optimization_set_file(fixed_params: dict, ranges: dict, output_path: str) -> str:
    """
    Writes an MT5 .set file mixing fixed input values and optimization
    ranges. MT5's documented format for a parameter that should be VARIED
    during optimization is:
        ParamName=start_value||start||step||stop||Y
    and for a FIXED (non-optimized) parameter, just:
        ParamName=value

    IMPORTANT: output_path must be inside the terminal's
    MQL5\\Profiles\\Tester\\ folder. MT5 only accepts a bare filename
    (no path) in ExpertParameters — it always looks in that folder.

    fixed_params: {input_name: value} — held constant across all passes
    ranges: {input_name: (start, step, stop)} — swept across all passes
    """
    lines = []
    for name, value in fixed_params.items():
        lines.append(f"{name}={_fmt_set_val(value)}")

    for name, (start, step, stop) in ranges.items():
        s, st, e = _fmt_set_val(start), _fmt_set_val(step), _fmt_set_val(stop)
        lines.append(f"{name}={s}||{s}||{st}||{e}||Y")

    content = "\n".join(lines) + "\n"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # MT5 .set files must be UTF-16LE with BOM — verified requirement.
    output_path.write_text(content, encoding="utf-16")
    return str(output_path)


# ---------------------------------------------------------------------------
# ini generation + launch
# ---------------------------------------------------------------------------

OPTIMIZATION_INI_TEMPLATE = """[Common]
Login={login}
Password={password}
Server={server}

[Tester]
Expert={expert}
ExpertParameters={set_file}
Symbol={symbol}
Period={period}
Model=1
FromDate={from_date}
ToDate={to_date}
ForwardMode=0
Deposit={deposit}
Currency={currency}
Leverage={leverage}
Optimization={optimization_mode}
OptimizationCriterion=6
ExecutionMode=0
Report={report_name}
ReplaceReport=1
ShutdownTerminal=1
Visual=0
"""


def run_optimization(terminal_path: str, terminal_data_dir: str, expert: str, set_file: str,
                      symbol: str, period: str, from_date: str, to_date: str, work_dir: str,
                      login: str, password: str, server: str, report_name: str = "opt_report",
                      deposit: float = 100_000, currency: str = "USD", leverage: str = "1:100",
                      optimization_mode: int = 2, timeout: int = 21600, poll: int = 5) -> Path:
    """
    optimization_mode: 2 = fast genetic algorithm (recommended for large
        parameter spaces — MT5's own genetic search, separate from and in
        addition to the Python GA used in the earlier screening stage).
        1 = slow complete/exhaustive algorithm (tests every combination —
        only practical for small ranges).
    timeout default is 6 hours — optimization runs are much longer than
    single tests; raise this further for large parameter spaces or long
    date ranges.

    IMPORTANT path conventions (MT5 is strict about these):
      set_file         — must be just the FILENAME (e.g. 'ORB_opt.set'),
                         NOT a full path. MT5 always looks in its own
                         MQL5\\Profiles\\Tester\\ folder for .set files.
      report_name      — just a bare name (no extension, no path). MT5
                         writes <report_name>.xml into terminal_data_dir.

    Returns the path to the resulting XML report once found and stable.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Synchronize compiled EA (.ex5) to MT5 Experts directory if needed
    expert_filename = sync_ea_to_mt5(expert, terminal_data_dir, terminal_path)

    # 2. Validate .set file in Profiles/Tester/ and ensure at least one parameter is varied
    set_file_name = Path(set_file).name
    profiles_tester_dir = Path(terminal_data_dir) / "MQL5" / "Profiles" / "Tester"
    set_path = profiles_tester_dir / set_file_name

    if set_path.exists():
        try:
            set_txt = ""
            for enc in ("utf-16", "utf-16-le", "utf-8", "cp1252"):
                try:
                    set_txt = set_path.read_text(encoding=enc)
                    break
                except Exception:
                    continue
            has_opt = any("||Y" in line or "||y" in line for line in set_txt.splitlines())
            if not has_opt:
                raise ValueError(
                    f"Parameter file '{set_file_name}' contains NO parameters enabled for optimization (no lines with '||Y').\n"
                    f"MT5 Strategy Tester will immediately open and close if no parameters are varied.\n"
                    f"Please enable at least one parameter for optimization in the Optimize tab."
                )
        except ValueError:
            raise
        except Exception as ex:
            print(f"  [INFO] Parameter check: {ex}")
    else:
        print(f"  [WARN] Parameter file '{set_file_name}' not yet found in {profiles_tester_dir}")

    ini_content = OPTIMIZATION_INI_TEMPLATE.format(
        login=login, password=password, server=server,
        expert=expert_filename, set_file=set_file_name, symbol=symbol, period=period,
        from_date=from_date, to_date=to_date, deposit=int(deposit),
        currency=currency, leverage=leverage,
        optimization_mode=optimization_mode, report_name=report_name,
    )
    ini_path = work_dir / "optimize.ini"
    # MT5 .ini files must also be UTF-16 — same requirement as .set files.
    # Writing as default encoding causes MT5 to silently ignore the file
    # and immediately close.
    ini_path.write_text(ini_content, encoding="utf-16")

    # MT5 writes the report to <terminal_data_dir>\<report_name>.xml
    report_xml  = Path(terminal_data_dir) / f"{report_name}.xml"
    report_html = Path(terminal_data_dir) / f"{report_name}.html"
    candidates = [report_xml, report_html]
    for c in candidates:
        if c.exists():
            c.unlink()

    cmd = [terminal_path, f"/config:{ini_path}"]
    print(f"\nLaunching optimization:")
    print(f"  Command  : {cmd}")
    print(f"  Expert   : {expert_filename}")
    print(f"  Symbol   : {symbol}  |  Period: {period}")
    print(f"  Dates    : {from_date} -> {to_date}")
    print(f"  .ini     : {ini_path}")
    print(f"  .set     : {set_file_name}  (in Profiles/Tester/)")
    print(f"  Report   : {report_xml}")
    print("MT5 terminal launched. Monitoring optimization progress...")
    proc = subprocess.Popen(cmd)

    found = _wait_for_stable_file(candidates, timeout=timeout, poll=poll, proc=proc, terminal_data_dir=terminal_data_dir)
    return found


def _wait_for_stable_file(candidate_paths: list, timeout: int, poll: int,
                          proc: subprocess.Popen = None, terminal_data_dir: str = None) -> Path:
    print(f"Waiting for optimization report at one of: {[str(p) for p in candidate_paths]}")
    start = time.time()
    last_size = -1
    stable_checks = 0
    found_path = None

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        existing = [p for p in candidate_paths if p.exists()]
        if existing:
            found_path = existing[0]
            try:
                size = found_path.stat().st_size
            except OSError:
                size = -1
            print(f"  [{elapsed}s] found {found_path.name}, size={size} bytes")
            if size == last_size and size > 0:
                stable_checks += 1
                if stable_checks >= 3:
                    print(f"  [{elapsed}s] report stable, proceeding")
                    return found_path
            else:
                stable_checks = 0
            last_size = size
        else:
            # Check if MT5 process exited prematurely!
            if proc is not None and proc.poll() is not None:
                # MT5 terminal process has closed!
                time.sleep(2)
                existing = [p for p in candidate_paths if p.exists()]
                if existing and existing[0].stat().st_size > 0:
                    return existing[0]

                # MT5 closed without generating any report
                log_info = _read_latest_mt5_tester_log(terminal_data_dir) if terminal_data_dir else ""
                error_msg = (
                    f"\n[ERROR] MT5 terminal closed immediately without generating an optimization report! (Exit code: {proc.returncode})\n"
                    f"Possible causes:\n"
                    f"  1. The EA (.ex5) binary failed to load or is not compiled\n"
                    f"  2. No parameters were enabled for optimization in the .set file (must contain ||Y)\n"
                    f"  3. Symbol '{candidate_paths[0].stem}' or chart data is missing from Market Watch\n"
                    f"  4. MT5 account login failed\n\n"
                    f"--- MT5 Strategy Tester Log ---\n{log_info}\n"
                    f"-------------------------------\n"
                )
                print(error_msg)
                raise RuntimeError(error_msg)

            print(f"  [{elapsed}s] optimization in progress (terminal running)...")
        time.sleep(poll)

    raise TimeoutError(f"Optimization report never appeared or stabilized within {timeout}s. "
                        f"Checked: {candidate_paths}")


# ---------------------------------------------------------------------------
# Results parsing
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_optimization_results(report_path) -> pd.DataFrame:
    """
    Parses MT5's optimization report. MT5 exports optimization results as
    a SpreadsheetML (Excel 2003 XML) file: one header Row naming each
    varied parameter plus result columns (Pass, Result, Profit, etc.), then
    one Row per tested combination. Namespace-tolerant (strips any XML
    namespace prefix before matching tag names, since the exact namespace
    URI isn't independently verified here).

    Returns a DataFrame, one row per optimization pass, sorted by the
    'Result' column (our OnTester() fitness score) descending.
    """
    report_path = Path(report_path)
    tree = ET.parse(report_path)
    root = tree.getroot()

    rows = []
    for elem in root.iter():
        if _strip_ns(elem.tag) == "Row":
            cells = []
            for cell in elem:
                if _strip_ns(cell.tag) != "Cell":
                    continue
                data_elem = None
                for child in cell:
                    if _strip_ns(child.tag) == "Data":
                        data_elem = child
                        break
                cells.append(data_elem.text if data_elem is not None else None)
            if cells:
                rows.append(cells)

    if not rows:
        raise ValueError(
            f"No <Row>/<Cell>/<Data> elements found in {report_path}. The actual XML "
            f"schema may differ from what this parser expects — share the file (or its "
            f"first ~30 lines) so the parser can be corrected against the real format."
        )

    header = rows[0]
    data_rows = rows[1:]

    df = pd.DataFrame(data_rows, columns=header)
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass  # leave non-numeric columns (if any) as-is

    if "Result" in df.columns:
        df = df.sort_values("Result", ascending=False).reset_index(drop=True)

    return df


def print_top_results(df: pd.DataFrame, n: int = 20) -> None:
    print("=" * 90)
    print(f"TOP {n} OPTIMIZATION PASSES (by OnTester() fitness score)")
    print("=" * 90)
    print(df.head(n).to_string(index=False))