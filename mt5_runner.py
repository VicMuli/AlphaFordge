r"""
mt5_runner.py

First building block of the personal quant analysis tool.
Automates a single headless MT5 Strategy Tester run and returns the path
to the resulting report file. Parsing/analysis is handled separately by
report_analysis.py — see that module for the curated summary and
monthly/yearly performance breakdown.

Usage:
    from mt5_runner import run_single_backtest
    from report_analysis import analyze, print_summary

    report_path = run_single_backtest(
        terminal_path=r"C:\Program Files\MetaTrader 5 IC Markets KE\terminal64.exe",
        terminal_data_dir=r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\<your-id>",
        expert="XAUB Quant 1.ex5",
        set_file="Q1.set",
        symbol="XAUUSD Dukascopy",
        period="H1",
        from_date="2012.12.31",
        to_date="2026.07.03",
        deposit=100000,
        work_dir=r"C:\MT5\AutoTests\run_001",
        login="52909674",
        password="3F!@4rwo7wc02f",
        server="ICMarketsKE-Demo",
    )

    result = analyze(report_path)
    print_summary(result)
"""

import os
import time
import subprocess
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "tester_template.ini"


def _generate_ini(work_dir: Path, **kwargs) -> Path:
    template = TEMPLATE_PATH.read_text()
    ini_content = template.format(**kwargs)
    ini_path = work_dir / "run.ini"
    # MT5 .ini files must be UTF-16 — writing with the default system encoding
    # causes MT5 to silently ignore the file and immediately close the terminal.
    ini_path.write_text(ini_content, encoding="utf-16")
    return ini_path


def _wait_for_report(report_path_options, timeout: int = 1800, poll: int = 3,
                      open_check_timeout: int = None) -> Path:
    """
    report_path_options: list of candidate Paths (e.g. .htm and .html variants).
    Waits until one of them appears and stabilizes in size, returns that Path.
    open_check_timeout: if the report file has not appeared within this many
    seconds, raise TimeoutError immediately (e.g. MT5 terminal never opened).
    """
    print(f"Waiting for report at one of: {[str(p) for p in report_path_options]}")
    start = time.time()
    last_size = -1
    stable_checks = 0
    found_path = None
    file_appeared = False

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            existing = [p for p in report_path_options if p.exists()]
            if existing:
                file_appeared = True
                found_path = existing[0]
                size = found_path.stat().st_size
                print(f"  [{elapsed}s] found {found_path.name}, size={size} bytes "
                      f"(last={last_size}, stable_checks={stable_checks})")
                if size == last_size and size > 0:
                    stable_checks += 1
                    if stable_checks >= 2:
                        print(f"  [{elapsed}s] report stable, proceeding")
                        return found_path
                else:
                    stable_checks = 0
                last_size = size
            else:
                print(f"  [{elapsed}s] not found yet")
                # Early-abort: terminal never opened within the check window
                if (not file_appeared
                        and open_check_timeout is not None
                        and elapsed >= open_check_timeout):
                    raise TimeoutError(
                        f"MT5 terminal did not produce a report file within "
                        f"{open_check_timeout}s — aborting early. "
                        f"Checked: {report_path_options}"
                    )
        except OSError as e:
            print(f"  [{elapsed}s] transient read error (file likely locked): {e}")
        time.sleep(poll)

    raise TimeoutError(f"Report never appeared or stabilized. Checked: {report_path_options}")


def run_single_backtest(
    terminal_path: str,
    terminal_data_dir: str,
    expert: str,
    set_file: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    work_dir: str,
    login: str,
    password: str,
    server: str,
    report_name: str = "auto_report",
    deposit: int = 100000,
    currency: str = "USD",
    leverage: str = "1:100",
    timeout: int = 1800,
    open_check_timeout: int = None,
) -> dict:
    """
    terminal_data_dir: the terminal's own data folder, e.g.
        r"C:\\Users\\HP\\AppData\\Roaming\\MetaTrader\\Terminal\\CDE1ED2F37049DA2E508A3C44B675D09"
    MT5 only ever writes tester reports into <terminal_data_dir>\\MQL5\\Files\\,
    and only accepts a bare filename (no path, no extension) for the Report= ini key.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Where MT5 will actually write the report — extension varies (.htm or .html)
    # depending on build, so we watch both candidates rather than assuming one.
    report_html = Path(terminal_data_dir) / f"{report_name}.html"
    report_htm = Path(terminal_data_dir) / f"{report_name}.htm"
    candidates = [report_html, report_htm]

    ini_path = _generate_ini(
        work_dir,
        login=login,
        password=password,
        server=server,
        expert=expert,
        set_file=set_file,
        symbol=symbol,
        period=period,
        from_date=from_date,
        to_date=to_date,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        report_name=report_name,
    )

    # Delete any stale reports from a previous run so we don't parse old data
    for candidate in candidates:
        if candidate.exists():
            candidate.unlink()

    cmd = [terminal_path, f"/config:{ini_path}"]
    print(f"Launching: {cmd}")
    subprocess.Popen(cmd)

    found_report = _wait_for_report(candidates, timeout=timeout,
                                     open_check_timeout=open_check_timeout)

    # Copy the report into work_dir too, so each run's results are archived
    # alongside their trades.csv rather than getting overwritten next run
    archived_copy = work_dir / found_report.name
    archived_copy.write_bytes(found_report.read_bytes())

    return found_report  # hand off to report_analysis.analyze() for parsing


if __name__ == "__main__":
    # Smoke test stub — fill in real paths/credentials and run once manually
    # against an EA whose stats you already know, to validate the parser
    # matches what you see when you save the report by hand in MT5.
    pass