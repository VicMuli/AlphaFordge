#!/usr/bin/env python3
"""
app.py — AlphaForge v1.0
MT5 Quant Optimizer & Portfolio Builder — Professional Desktop GUI

Run with:
    python app.py
"""

import os, sys, json, re, subprocess, threading, time, shutil
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    print("ERROR: customtkinter not installed.\nRun:  pip install customtkinter")
    sys.exit(1)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Theme
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = dict(
    bg       = "#0a0e1a",
    sidebar  = "#060912",
    panel    = "#111827",
    card     = "#1f2937",
    accent   = "#f59e0b",
    blue     = "#3b82f6",
    success  = "#10b981",
    danger   = "#ef4444",
    text     = "#f9fafb",
    sub      = "#8b95a6",
    border   = "#2d3748",
    inp      = "#1a2235",
    nav_act  = "#1a2540",
    hover    = "#253352",
)

FH1  = None
FH2  = None
FH3  = None
FB   = None
FMO  = None
FSM  = None

SCRIPT_DIR  = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

DEFAULT_CONFIG = {
    "terminal_path":      r"C:\Users\HP\AppData\Roaming\MetaTrader\terminal64.exe",
    "terminal_data_dir":  r"C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\CDE1ED2F37049DA2E508A3C44B675D09",
    "active_ea":          "TRB",
    "expert":             "TRB V1.7.ex5",
    "symbol":             "USDJPY Dukascopy",
    "symbol_key":         "USDJPY",
    "period":             "M15",
    "pip_size":           "0.001",
    "train_from":         "2013.01.01",
    "train_to":           "2022.01.01",
    "val_from":           "2022.01.01",
    "val_to":             "2024.01.01",
    "holdout_from":       "2024.01.01",
    "holdout_to":         "2026.07.03",
    "deposit":            "2500",
    "currency":           "USD",
    "leverage":           "1:100",
    "login":              "",
    "password":           "",
    "server":             "ICMarketsKE-Demo",
    "top_n_train":        "20",
    "opt_timeout":        "21600",
    "single_test_timeout": "200",
    "wf_window_months":   "12",
    "wf_step_months":     "6",
    "mc_simulations":     "5000",
    "mc_max_dd":          "10.0",
    "mc_daily_dd":        "5.0",
    "mc_phase1_target":   "8.0",
    "mc_phase2_target":   "5.0",
    "mc_block_size":      "10",
    "mc_max_days":        "250",
    "mc_no_max_days":     "false",
    "work_dir":           str(SCRIPT_DIR / "optimization_runs"),
    "quant_name":         "TRB",
    "research_dir":       str(SCRIPT_DIR / "researched_strategies"),
    "strategies_dir":     str(SCRIPT_DIR / "strategies"),
    "ui_zoom":            "1.0",
}

NAV_ITEMS = [
    ("🏠", "Dashboard",    "dashboard"),
    ("🔬", "Research",     "research"),
    ("⚙",  "Optimize",    "optimize"),
    ("🎲", "Monte Carlo",  "montecarlo"),
    ("📈", "Walk Forward", "walkforward"),
    ("📋", "Full Backtest","fullbacktest"),
    ("📦", "Portfolio",    "portfolio"),
    ("🗂",  "Strategies",  "strategies"),
    ("🔧", "Settings",     "settings"),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Shared helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                cfg.update(loaded)
        except Exception:
            pass

    # Ensure paths always resolve to the active project folder (AlphaFordge),
    # replacing any obsolete references to "MT5 runner"
    migrated = False
    for k, subfolder in [
        ("work_dir", "optimization_runs"),
        ("research_dir", "researched_strategies"),
        ("strategies_dir", "strategies"),
    ]:
        curr_val = str(cfg.get(k, ""))
        if "MT5 runner" in curr_val or not curr_val:
            cfg[k] = str(SCRIPT_DIR / subfolder)
            migrated = True

    if migrated:
        save_config(cfg)

    return cfg


def save_config(cfg: dict) -> bool:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


def is_valid_optimization_run(d: Path) -> bool:
    """Verify that a directory is an actual optimization run folder."""
    if not d.is_dir():
        return False
    name = d.name
    name_lower = name.lower()

    # Must start with run_
    if not name_lower.startswith("run_"):
        return False

    # Exclude non-run script output folders, tools, or scratch dirs
    excluded_names = {
        "run_optimization", "run_full_backtest", "run_research_backtest",
        "run_portfolio_montecarlo", "run_wf_pipeline", "run_can_monte_carlo",
        "run_post_optimization", "run_opt", "run_tester", "run_temp", "run_archive"
    }
    if name_lower in excluded_names:
        return False

    # Must NOT be a nested subfolder of another run, candidate, or portfolio
    for parent in d.parents:
        pname = parent.name.lower()
        if pname.startswith("run_") or pname.startswith("cand_") or pname == "passed_candidates":
            return False
        if "quant_portfolios" in pname or "researched_strategies" in pname:
            return False

    # Positive confirmation:
    # 1. Standard timestamp format run_YYYYMMDD_HHMMSS or run_\d+
    if re.match(r"^run_\d{8}_\d{6}$", name) or re.match(r"^run_\d+$", name):
        return True

    # 2. Contains passed_candidates folder or direct cand_XXX candidate folders
    if (d / "passed_candidates").is_dir():
        return True
    try:
        if any(sub.is_dir() and sub.name.startswith("cand_") for sub in d.iterdir()):
            return True
    except OSError:
        pass

    # 3. Contains optimization output markers (opt_all_passes.csv, opt dir, docx report)
    if (d / "opt_all_passes.csv").exists() or (d / "opt").is_dir() or (d / "Certified_Candidates.docx").exists():
        return True
    try:
        if any(f.is_file() and f.name.startswith("mc_passed_") for f in d.iterdir()):
            return True
    except OSError:
        pass

    return False


def _resolve_work_dir(work_dir: str) -> Path:
    if not work_dir or "MT5 runner" in str(work_dir):
        return SCRIPT_DIR / "optimization_runs"
    p = Path(work_dir)
    if not p.exists() and (SCRIPT_DIR / "optimization_runs").exists():
        return SCRIPT_DIR / "optimization_runs"
    return p


def get_run_dirs(work_dir: str) -> list:
    """Return sorted list of valid optimization run directory names."""
    p = _resolve_work_dir(work_dir)
    if not p.exists():
        return []

    valid_runs = []

    # 1. Direct children of work_dir
    try:
        for d in p.iterdir():
            if is_valid_optimization_run(d):
                valid_runs.append(d)
            elif d.is_dir() and not d.name.startswith(".") and d.name != "Quant_Portfolios":
                # Check one level deeper (e.g. work_dir/<symbol_ea>/run_*)
                try:
                    for sub in d.iterdir():
                        if is_valid_optimization_run(sub):
                            valid_runs.append(sub)
                except OSError:
                    pass
    except OSError:
        return []

    # Deduplicate and sort descending (latest first)
    unique_names = sorted(list({d.name for d in valid_runs}), reverse=True)
    return unique_names


def find_run_path(work_dir: str, run_dir: str) -> Path | None:
    """Find the Path for a given run directory name."""
    if not run_dir:
        return None
    p = _resolve_work_dir(work_dir)
    if not p.exists():
        return None

    # Direct match in work_dir
    cand = p / run_dir
    if cand.exists() and cand.is_dir() and is_valid_optimization_run(cand):
        return cand

    # Match in 1 level subfolders (e.g. work_dir/trb_usdjpy/run_...)
    try:
        for sub in p.iterdir():
            if sub.is_dir() and sub.name != "Quant_Portfolios":
                nested = sub / run_dir
                if nested.exists() and nested.is_dir() and is_valid_optimization_run(nested):
                    return nested
    except OSError:
        pass

    # Fallback to rglob if placed deeper
    try:
        for found in p.rglob(run_dir):
            if is_valid_optimization_run(found):
                return found
    except OSError:
        pass

    # Generic directory fallback if name matches
    try:
        fallback_found = [d for d in p.rglob(run_dir) if d.is_dir()]
        return fallback_found[0] if fallback_found else None
    except OSError:
        return None


def get_candidates(work_dir: str, run_dir: str) -> list:
    rp = find_run_path(work_dir, run_dir)
    if not rp or not rp.exists():
        return []
    pc = rp / "passed_candidates"
    cands = []
    if pc.exists() and pc.is_dir():
        cands = sorted([d.name for d in pc.iterdir() if d.is_dir() and d.name.startswith("cand_")])
    if not cands:
        cands = sorted([d.name for d in rp.iterdir() if d.is_dir() and d.name.startswith("cand_")])
    return cands


def is_valid_portfolio_dir(d: Path) -> bool:
    """Verify that a directory is an actual quant portfolio folder (not a parent container)."""
    if not d.is_dir():
        return False
    name_lower = d.name.lower()
    # Exclude parent container directories
    if name_lower in ("quant_portfolios", "portfolios", "multimarket portfolio", "multimarket_portfolio") or name_lower.endswith("_quant_portfolios") or name_lower.endswith("_portfolios"):
        return False
    # Check for portfolio files
    if (d / "portfolio_manifest.json").exists() or (d / "combined_trades.csv").exists():
        return True
    if any(f.is_file() and (f.name.endswith("_Report.docx") or f.name.startswith("chart_") or f.name == "correlation_matrix.csv") for f in d.iterdir()):
        return True
    pname = d.parent.name.lower()
    if "quant_portfolios" in pname or pname == "quant_portfolios" or "multimarket" in pname:
        return True
    if "portfolio_" in name_lower or "portfolio" in name_lower:
        return True
    return False


def get_portfolios(work_dir: str, quant_name: str = "") -> list:
    """Return sorted list of valid portfolio directory names found under work_dir and MultiMarket portfolio."""
    base = _resolve_work_dir(work_dir)
    found_dirs: list[Path] = []
    script_dir = Path(__file__).parent.resolve()

    # 1. MultiMarket portfolio directories
    mm_dirs = [
        script_dir / "Multi_Market_Quant_Portfolio",
        script_dir / "MultiMarket portfolio",
        base / "Multi_Market_Quant_Portfolio",
        base / "MultiMarket portfolio",
    ]
    for mm in mm_dirs:
        if mm.exists() and mm.is_dir():
            for item in mm.iterdir():
                if is_valid_portfolio_dir(item):
                    found_dirs.append(item)
                elif item.is_dir():
                    for sub in item.iterdir():
                        if is_valid_portfolio_dir(sub):
                            found_dirs.append(sub)

    # 2. Direct standard location: base / Quant_Portfolios / {quant_name}_Quant_Portfolios
    if base.exists():
        if quant_name:
            direct = base / "Quant_Portfolios" / f"{quant_name}_Quant_Portfolios"
            if direct.exists() and direct.is_dir():
                for d in direct.iterdir():
                    if is_valid_portfolio_dir(d):
                        found_dirs.append(d)

        # 3. Check 1-level subfolders (e.g. base / trb_usdjpy / Quant_Portfolios / ...)
        try:
            for sub in base.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    qp = sub / "Quant_Portfolios"
                    if qp.exists() and qp.is_dir():
                        if quant_name:
                            qsub = qp / f"{quant_name}_Quant_Portfolios"
                            if qsub.exists() and qsub.is_dir():
                                for d in qsub.iterdir():
                                    if is_valid_portfolio_dir(d):
                                        found_dirs.append(d)
                        for sub2 in qp.iterdir():
                            if is_valid_portfolio_dir(sub2):
                                found_dirs.append(sub2)
                            elif sub2.is_dir():
                                for sub3 in sub2.iterdir():
                                    if is_valid_portfolio_dir(sub3):
                                        found_dirs.append(sub3)
        except OSError:
            pass

        # 4. Search via rglob for any Quant_Portfolios or portfolio_manifest.json under base
        try:
            for qp in base.rglob("Quant_Portfolios"):
                if qp.is_dir():
                    for item in qp.iterdir():
                        if is_valid_portfolio_dir(item):
                            found_dirs.append(item)
                        elif item.is_dir():
                            for item2 in item.iterdir():
                                if is_valid_portfolio_dir(item2):
                                    found_dirs.append(item2)
        except OSError:
            pass

        try:
            for manifest in base.rglob("portfolio_manifest.json"):
                if is_valid_portfolio_dir(manifest.parent):
                    found_dirs.append(manifest.parent)
            for trades in base.rglob("combined_trades.csv"):
                if is_valid_portfolio_dir(trades.parent):
                    found_dirs.append(trades.parent)
        except OSError:
            pass

    # Deduplicate and register names (including relative path for nested folders)
    unique_names = {}
    for d in found_dirs:
        unique_names[d.name] = d
        if d.parent.name and d.parent.name not in ("Quant_Portfolios", "MultiMarket portfolio") and not d.parent.name.endswith("_Quant_Portfolios"):
            unique_names[f"{d.parent.name}/{d.name}"] = d

    return sorted(list(unique_names.keys()), reverse=True)


def find_portfolio_path(work_dir: str, quant_name: str, port_name: str) -> Path | None:
    """Find the exact directory Path for a given portfolio name across all locations."""
    if not port_name or port_name == "(none)":
        return None
    base = _resolve_work_dir(work_dir)
    script_dir = Path(__file__).parent.resolve()

    # 1. MultiMarket portfolio checks
    mm_dirs = [
        script_dir / "Multi_Market_Quant_Portfolio",
        script_dir / "MultiMarket portfolio",
        base / "Multi_Market_Quant_Portfolio",
        base / "MultiMarket portfolio",
    ]
    for mm in mm_dirs:
        if mm.exists() and mm.is_dir():
            # Exact folder match
            cand = mm / port_name
            if cand.exists() and is_valid_portfolio_dir(cand):
                return cand
            # Nested path match (e.g. TRB_USDJPY/EURJPY_Portfolio_001)
            parts = port_name.replace("\\", "/").split("/")
            if len(parts) > 1:
                cand_nested = mm.joinpath(*parts)
                if cand_nested.exists() and is_valid_portfolio_dir(cand_nested):
                    return cand_nested
            # Scan subfolders
            for sub in mm.iterdir():
                if sub.is_dir():
                    if sub.name == port_name and is_valid_portfolio_dir(sub):
                        return sub
                    cand_child = sub / port_name
                    if cand_child.exists() and is_valid_portfolio_dir(cand_child):
                        return cand_child
                    for sub2 in sub.iterdir():
                        if sub2.is_dir() and sub2.name == port_name and is_valid_portfolio_dir(sub2):
                            return sub2

    # 2. Direct standard location: base / Quant_Portfolios / {quant_name}_Quant_Portfolios / port_name
    if base.exists():
        if quant_name:
            cand = base / "Quant_Portfolios" / f"{quant_name}_Quant_Portfolios" / port_name
            if cand.exists() and is_valid_portfolio_dir(cand):
                return cand

        # 3. Check in subfolders (e.g. base / trb_usdjpy / Quant_Portfolios / ...)
        try:
            for sub in base.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    cand = sub / "Quant_Portfolios" / f"{quant_name}_Quant_Portfolios" / port_name
                    if cand.exists() and is_valid_portfolio_dir(cand):
                        return cand
                    cand2 = sub / "Quant_Portfolios" / port_name
                    if cand2.exists() and is_valid_portfolio_dir(cand2):
                        return cand2
        except OSError:
            pass

        # 4. Search via rglob
        try:
            target_leaf = Path(port_name).name
            for found in base.rglob(target_leaf):
                if is_valid_portfolio_dir(found):
                    return found
        except OSError:
            pass

    return None


def patch_script(script_path: Path, patches: dict):
    """Patch constant assignments (CONSTANT = value) in a Python script file."""
    try:
        text = script_path.read_text(encoding="utf-8")
        for var, val in patches.items():
            if isinstance(val, str):
                try:
                    float(val)
                    new_val = str(val)
                except ValueError:
                    new_val = repr(val)
            else:
                new_val = str(val)
            pattern  = rf"^({re.escape(var)}\s*=\s*).*$"
            # Use a lambda to avoid backslash escape processing in replacement string
            text     = re.sub(pattern, lambda m, v=new_val: f"{m.group(1)}{v}", text, flags=re.MULTILINE)
        script_path.write_text(text, encoding="utf-8")
        return True
    except Exception as e:
        print(f"patch_script ERROR: {e}")
        return False


def open_in_file_manager(path_obj: Path | str):
    """Safely open file or directory in the system file manager/viewer across OSes."""
    p = Path(path_obj) if not isinstance(path_obj, Path) else path_obj
    p_str = str(p)
    try:
        if sys.platform == "win32":
            os.startfile(p_str)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p_str])
        else:
            subprocess.Popen(["xdg-open", p_str])
    except Exception as e:
        print(f"Could not open path {p_str}: {e}")


def get_all_candidates_summary(work_dir: str, run_filter: str = None) -> list[dict]:
    """Find all candidate directories across work_dir and return metadata."""
    base = _resolve_work_dir(work_dir)
    if not base.exists():
        return []

    results = []

    def _inspect_cand(cand_dir: Path, run_name: str = ""):
        cid = cand_dir.name
        if not cid.startswith("cand_"):
            return
        trades_file = cand_dir / "trades.csv"
        has_trades = trades_file.exists()
        if not has_trades:
            try:
                has_trades = any(
                    f.suffix.lower() in (".csv", ".htm", ".html", ".xml") and
                    ("report" in f.name.lower() or "backtest" in f.name.lower() or "trades" in f.name.lower())
                    for f in cand_dir.iterdir() if f.is_file()
                )
            except Exception:
                has_trades = False

        mc_file = cand_dir / "monte_carlo_results.json"
        is_cert = None
        pass_rate = None
        worst_dd = None
        if mc_file.exists():
            try:
                with open(mc_file, "r", encoding="utf-8") as f:
                    mc_data = json.load(f)
                    is_cert = mc_data.get("is_certified")
                    pass_rate = mc_data.get("combined_pass_rate")
                    worst_dd = mc_data.get("worst_breach_max_dd")
            except Exception:
                pass

        results.append({
            "id": cid,
            "dir": cand_dir,
            "run": run_name,
            "has_trades": bool(has_trades),
            "has_mc": mc_file.exists(),
            "is_certified": is_cert,
            "pass_rate": pass_rate,
            "worst_dd": worst_dd
        })

    # If run_filter is specified and not Auto
    if run_filter and run_filter not in ("(Auto-detect across workspace)", "(none)", "latest", ""):
        rpath = find_run_path(work_dir, run_filter)
        if rpath and rpath.exists():
            pc = rpath / "passed_candidates"
            if pc.exists() and pc.is_dir():
                for d in sorted(pc.iterdir()):
                    if d.is_dir() and d.name.startswith("cand_"):
                        _inspect_cand(d, run_filter)
            for d in sorted(rpath.iterdir()):
                if d.is_dir() and d.name.startswith("cand_"):
                    if not any(r["id"] == d.name for r in results):
                        _inspect_cand(d, run_filter)
            return results

    # Otherwise scan recursively
    try:
        for p in base.rglob("passed_candidates"):
            if p.is_dir():
                run_name = p.parent.name
                for d in sorted(p.iterdir()):
                    if d.is_dir() and d.name.startswith("cand_"):
                        _inspect_cand(d, run_name)
        for d in base.rglob("cand_*"):
            if d.is_dir() and not any(r["dir"] == d for r in results):
                run_name = d.parent.name if d.parent.name != "passed_candidates" else d.parent.parent.name
                _inspect_cand(d, run_name)
    except Exception:
        pass

    results.sort(key=lambda x: x["id"])
    return results


def find_candidate_path(work_dir: str, candidate_name: str, run_dir: str = None) -> Path | None:
    """Resolve candidate directory path given candidate ID and optional run_dir."""
    if not candidate_name:
        return None
    base = _resolve_work_dir(work_dir)
    if not base.exists():
        return None

    if run_dir and run_dir not in ("(Auto-detect across workspace)", "(none)", "latest", ""):
        rpath = find_run_path(work_dir, run_dir)
        if rpath:
            p1 = rpath / "passed_candidates" / candidate_name
            if p1.exists() and p1.is_dir():
                return p1
            p2 = rpath / candidate_name
            if p2.exists() and p2.is_dir():
                return p2

    # Check passed_candidates across base
    for pc in base.rglob("passed_candidates"):
        if pc.is_dir():
            target = pc / candidate_name
            if target.exists() and target.is_dir():
                return target

    # Check directly
    for d in base.rglob(candidate_name):
        if d.is_dir() and d.name == candidate_name:
            return d

    return None


import tkinter as tk

def _add_context_menu(widget, is_text=False):
    def _copy():
        try:
            target.clipboard_clear()
            if is_text:
                target.clipboard_append(target.get("sel.first", "sel.last"))
            else:
                target.clipboard_append(target.selection_get())
        except Exception:
            pass

    def _paste():
        try:
            text = target.clipboard_get()
            if is_text:
                target.insert("insert", text)
            else:
                target.insert("insert", text)
        except Exception:
            pass

    def show_menu(event):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Copy", command=_copy)
        menu.add_command(label="Cut", command=lambda: target.event_generate("<<Cut>>"))
        menu.add_command(label="Paste", command=_paste)
        menu.tk_popup(event.x_root, event.y_root)
        
    # Bind to the underlying tkinter widget
    target = widget._textbox if is_text else widget._entry
    target.bind("<Button-3>", show_menu)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Reusable UI primitives
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12, **kw)


def make_label(parent, text, font=None, color=None, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font or FB,
                        text_color=color or C["text"], **kw)


def make_btn(parent, text, cmd, color=None, hover=None, width=140, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(parent, text=text, command=cmd, width=width,
                         fg_color=color or C["accent"],
                         hover_color=hover or "#d97706",
                         text_color="#0a0e1a", font=FH3, corner_radius=8, **kw)


def make_entry(parent, placeholder="", width=240, show=None, **kw) -> ctk.CTkEntry:
    e = ctk.CTkEntry(parent, width=width, placeholder_text=placeholder,
                     fg_color=C["inp"], border_color=C["border"],
                     text_color=C["text"], font=FB, corner_radius=8, **kw)
    if show:
        e.configure(show=show)
    _add_context_menu(e, is_text=False)
    return e


def make_log(parent, height=220, **kw) -> ctk.CTkTextbox:
    tb = ctk.CTkTextbox(parent, height=height, fg_color=C["sidebar"],
                        text_color="#a8d8a8", font=FMO, corner_radius=8,
                        border_width=1, border_color=C["border"], **kw)
    tb.configure(state="disabled")
    _add_context_menu(tb, is_text=True)
    return tb


def make_section_header(parent, title, subtitle="") -> ctk.CTkFrame:
    f = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(f, text=title, font=FH1, text_color=C["text"]).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(f, text=subtitle, font=FB, text_color=C["sub"]).pack(anchor="w", pady=(2, 0))
    sep = ctk.CTkFrame(f, height=1, fg_color=C["border"])
    sep.pack(fill="x", pady=(10, 0))
    return f


def make_field_row(parent, label, widget, label_width=180) -> ctk.CTkFrame:
    f = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(f, text=label, font=FB, text_color=C["sub"],
                 width=label_width, anchor="e").pack(side="left", padx=(0, 12))
    widget.pack(side="left")
    return f


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Subprocess runner (all panels share this mixin)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SubprocessMixin:
    """Provides threaded subprocess + log streaming utilities."""

    def log_append(self, widget: ctk.CTkTextbox, text: str):
        def _do():
            widget.configure(state="normal")
            widget.insert("end", text)
            widget.see("end")
            widget.configure(state="disabled")
        widget.after(0, _do)

    def log_clear(self, widget: ctk.CTkTextbox):
        def _do():
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")
        widget.after(0, _do)

    def run_script(self, script_name: str, log_widget: ctk.CTkTextbox,
                   env_extra: dict = None, args: list = None,
                   on_done=None):
        """Launch a script in a daemon thread, streaming output to log_widget."""
        script_path = SCRIPT_DIR / script_name
        if not script_path.exists():
            self.log_append(log_widget, f"[ERROR] Script not found: {script_path}\n")
            return

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if env_extra:
            env.update(env_extra)

        cmd = [sys.executable, str(script_path)] + (args or [])

        # Notify app status if available
        if hasattr(self, "app") and hasattr(self.app, "set_process_status"):
            self.app.set_process_status(script_name)

        def _worker():
            self.log_append(log_widget,
                f"▶  {datetime.now().strftime('%H:%M:%S')}  {script_name}\n"
                f"   CWD: {SCRIPT_DIR}\n{'─'*60}\n")
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    cwd=str(SCRIPT_DIR), env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32" else 0,
                )
                for line in iter(proc.stdout.readline, ""):
                    self.log_append(log_widget, line)
                proc.wait()
                self.log_append(log_widget,
                    f"\n{'─'*60}\n✔  Finished  (code {proc.returncode})  "
                    f"{datetime.now().strftime('%H:%M:%S')}\n")
                if hasattr(self, "app") and hasattr(self.app, "set_process_status"):
                    self.app.after(0, lambda: self.app.set_process_status(None))
                if on_done:
                    log_widget.after(0, on_done)
            except Exception as exc:
                self.log_append(log_widget, f"\n[ERROR] {exc}\n")
                if hasattr(self, "app") and hasattr(self.app, "set_process_status"):
                    self.app.after(0, lambda: self.app.set_process_status(None))

        threading.Thread(target=_worker, daemon=True).start()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2-Way (Vertical & Horizontal) Scrollable Container
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DualScrollableContainer(ctk.CTkFrame):
    """
    Container providing both vertical (down and up) and horizontal (sideways)
    scrolling for full application visibility across varying screen sizes.
    """
    def __init__(self, master, fg_color=None, **kwargs):
        super().__init__(master, fg_color=fg_color or C["panel"], corner_radius=0, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Underlying 2D canvas
        self._canvas = tk.Canvas(
            self,
            bg=C["panel"],
            highlightthickness=0,
            bd=0
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")

        # Vertical scrollbar (right edge, scrolls down and up)
        self._v_scrollbar = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self._canvas.yview,
            width=14,
            fg_color="#0a0e1a",
            button_color="#232f48",
            button_hover_color=C["accent"]
        )
        self._v_scrollbar.grid(row=0, column=1, sticky="ns")

        # Horizontal scrollbar (bottom edge, scrolls sideways)
        self._h_scrollbar = ctk.CTkScrollbar(
            self,
            orientation="horizontal",
            command=self._canvas.xview,
            height=14,
            fg_color="#0a0e1a",
            button_color="#232f48",
            button_hover_color=C["accent"]
        )
        self._h_scrollbar.grid(row=1, column=0, sticky="ew")

        # Corner filler where scrollbars meet
        self._corner = ctk.CTkFrame(
            self,
            width=14,
            height=14,
            fg_color="#0a0e1a",
            corner_radius=0
        )
        self._corner.grid(row=1, column=1, sticky="nsew")

        self._canvas.configure(
            xscrollcommand=self._h_scrollbar.set,
            yscrollcommand=self._v_scrollbar.set
        )

        # Viewport frame holding the active panel
        self.viewport = ctk.CTkFrame(self._canvas, fg_color=C["panel"], corner_radius=0)
        self.viewport.grid_columnconfigure(0, weight=1)
        self.viewport.grid_rowconfigure(0, weight=1)
        self._window_id = self._canvas.create_window((0, 0), window=self.viewport, anchor="nw")

        self._current_w = None
        self._current_h = None

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self.viewport.bind("<Configure>", self._on_viewport_configure)

    def _update_scroll_region(self):
        try:
            canv_w = self._canvas.winfo_width()
            canv_h = self._canvas.winfo_height()
            if canv_w <= 1 or canv_h <= 1:
                return

            req_w = self.viewport.winfo_reqwidth()
            req_h = self.viewport.winfo_reqheight()

            # Ensure viewport matches or exceeds canvas dimensions
            target_w = max(canv_w, req_w, 980)
            target_h = max(canv_h, req_h)

            if target_w != self._current_w or target_h != self._current_h:
                self._current_w = target_w
                self._current_h = target_h
                self._canvas.itemconfigure(self._window_id, width=target_w, height=target_h)
                self._canvas.configure(scrollregion=(0, 0, target_w, target_h))
        except Exception:
            pass

    def _on_canvas_configure(self, event=None):
        self._update_scroll_region()

    def _on_viewport_configure(self, event=None):
        self._update_scroll_region()

    def update_scroll(self):
        self._current_w = None
        self._current_h = None
        self.after_idle(self._update_scroll_region)

    def scroll_to_top_left(self):
        self._canvas.xview_moveto(0.0)
        self._canvas.yview_moveto(0.0)

    def scroll_to_top(self):
        self._canvas.yview_moveto(0.0)

    def scroll_to_bottom(self):
        self._canvas.yview_moveto(1.0)

    def scroll_to_left(self):
        self._canvas.xview_moveto(0.0)

    def scroll_to_right(self):
        self._canvas.xview_moveto(1.0)

    def scroll_up(self, units=3):
        self._canvas.yview_scroll(-units, "units")

    def scroll_down(self, units=3):
        self._canvas.yview_scroll(units, "units")

    def scroll_left(self, units=3):
        self._canvas.xview_scroll(-units, "units")

    def scroll_right(self, units=3):
        self._canvas.xview_scroll(units, "units")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Panel base
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class BasePanel(ctk.CTkFrame, SubprocessMixin):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=C["panel"], corner_radius=0)
        self.app = app

    @property
    def cfg(self):
        return self.app.config


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dashboard Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DashboardPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))

        # Header
        hdr = make_section_header(self, "🏠  Dashboard",
                                   "Overview of your AlphaForge workspace")
        hdr.grid(row=0, column=0, sticky="ew", **pad)

        # Stats row
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.grid(row=1, column=0, sticky="ew", padx=32, pady=(24, 0))
        self._stat_cards = {}
        for i, (icon, label, key) in enumerate([
            ("📁", "Optimization Runs",   "runs"),
            ("✅", "Passed Candidates",   "passed"),
            ("📦", "Portfolios Built",    "portfolios"),
            ("🔬", "Researched Strategies","research"),
        ]):
            card = make_card(stats_frame, width=180, height=110)
            card.grid(row=0, column=i, padx=(0, 16), sticky="nsew")
            stats_frame.columnconfigure(i, weight=1)
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont("Segoe UI", 28)).pack(pady=(16, 4))
            val_lbl = ctk.CTkLabel(card, text="—", font=FH2, text_color=C["accent"])
            val_lbl.pack()
            ctk.CTkLabel(card, text=label, font=FSM, text_color=C["sub"]).pack(pady=(2, 12))
            self._stat_cards[key] = val_lbl

        # Recent runs
        recent_card = make_card(self)
        recent_card.grid(row=2, column=0, sticky="nsew", padx=32, pady=(24, 0))
        recent_card.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        make_label(recent_card, "Recent Optimization Runs", font=FH2,
                   color=C["accent"]).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))
        self._recent_box = make_log(recent_card, height=160)
        self._recent_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Refresh + quick actions
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.grid(row=3, column=0, sticky="ew", padx=32, pady=(20, 28))
        make_btn(action_row, "⟳  Refresh", self.refresh, width=130).pack(side="left", padx=(0, 16))
        make_btn(action_row, "📂 Open Work Dir",
                 lambda: os.startfile(self.cfg.get("work_dir", str(SCRIPT_DIR))),
                 color=C["card"], hover=C["hover"], width=160).pack(side="left", padx=(0, 16))
        make_btn(action_row, "📂 Open Research Dir",
                 lambda: os.startfile(self.cfg.get("research_dir",
                     str(SCRIPT_DIR / "researched_strategies"))),
                 color=C["card"], hover=C["hover"], width=170).pack(side="left")

        self.refresh()

    def refresh(self):
        cfg  = self.cfg
        wdir = cfg.get("work_dir", "")
        rdir = cfg.get("research_dir", "")

        runs   = get_run_dirs(wdir)
        passed = 0
        for r in runs:
            rp = find_run_path(wdir, r)
            if rp:
                pdir = rp / "passed_candidates"
                if pdir.exists():
                    passed += len([d for d in pdir.iterdir() if d.is_dir() and d.name.startswith("cand_")])
                else:
                    passed += len([d for d in rp.iterdir() if d.is_dir() and d.name.startswith("cand_")])
                    
        portfolios = len(get_portfolios(wdir, cfg.get("quant_name", "TRB")))
        research   = len(list(Path(rdir).iterdir())) if Path(rdir).exists() else 0

        self._stat_cards["runs"].configure(text=str(len(runs)))
        self._stat_cards["passed"].configure(text=str(passed))
        self._stat_cards["portfolios"].configure(text=str(portfolios))
        self._stat_cards["research"].configure(text=str(research))

        self._recent_box.configure(state="normal")
        self._recent_box.delete("1.0", "end")
        for r in runs[:12]:
            rp = find_run_path(wdir, r)
            if rp:
                pdir = rp / "passed_candidates"
                if pdir.exists():
                    pc = len([d for d in pdir.iterdir() if d.is_dir() and d.name.startswith("cand_")])
                else:
                    pc = len([d for d in rp.iterdir() if d.is_dir() and d.name.startswith("cand_")])
                self._recent_box.insert("end", f"  📁 {r}   passed candidates: {pc}\n")
        if not runs:
            self._recent_box.insert("end", "  No optimization runs found.\n")

        ports = get_portfolios(wdir, cfg.get("quant_name", "TRB"))
        if ports:
            self._recent_box.insert("end", "\n  📦 Built Quant Portfolios:\n")
            for p_name in ports:
                p_path = find_portfolio_path(wdir, cfg.get("quant_name", "TRB"), p_name)
                c_info = ""
                if p_path:
                    mf = p_path / "portfolio_manifest.json"
                    if mf.exists():
                        try:
                            with open(mf, "r") as mff:
                                mdata = json.load(mff)
                                c_count = len(mdata.get("candidates", []))
                                c_info = f" ({c_count} candidates)"
                        except Exception:
                            pass
                self._recent_box.insert("end", f"    • {p_name}{c_info}\n")
        self._recent_box.configure(state="disabled")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Research Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ResearchPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._ea_data = {}
        self._build()

    def _set(self, entry, val):
        entry.delete(0, "end")
        entry.insert(0, str(val))

    def _get_research_base(self) -> Path:
        custom = self.cfg.get("research_dir", "")
        if custom and Path(custom).exists():
            return Path(custom)
        base = SCRIPT_DIR / "researched_strategies"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _scan_researched_folders(self):
        base = self._get_research_base()
        ea_dict = {}
        if base.exists():
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    docs = list(d.glob("*.docx")) + list(d.glob("*.doc"))
                    mq5s = list(d.glob("*.mq5"))
                    ex5s = list(d.glob("*.ex5"))
                    sets = list(d.glob("*.set"))
                    htmls = list(d.glob("*_default.html")) + list(d.glob("*.html")) + list(d.glob("*.htm"))
                    word_reports = [f for f in docs if "report" in f.name.lower()]
                    logic_docs = [f for f in docs if "report" not in f.name.lower()]

                    summary_file = d / f"{d.name}_summary.json"
                    summary_data = None
                    if summary_file.exists():
                        try:
                            with open(summary_file, "r", encoding="utf-8") as f:
                                summary_data = json.load(f)
                        except Exception:
                            pass

                    ea_dict[d.name] = {
                        "path": d,
                        "logic_doc": logic_docs[0] if logic_docs else (docs[0] if docs else None),
                        "mq5": mq5s[0] if mq5s else None,
                        "ex5": ex5s[0] if ex5s else None,
                        "sets": sets,
                        "html_report": htmls[0] if htmls else None,
                        "word_report": word_reports[0] if word_reports else None,
                        "summary": summary_data,
                    }
        self._ea_data = ea_dict
        folder_names = list(ea_dict.keys())
        default_ea = self.cfg.get("active_ea", "TRB")
        if not folder_names:
            folder_names = [default_ea]
        return folder_names

    def _build(self):
        pad = dict(padx=32, pady=(24, 0))
        make_section_header(self, "🔬  Research Backtest",
            "Manage researched strategies in researched_strategies/<EA>/ and run default baseline backtests"
        ).grid(row=0, column=0, sticky="ew", **pad)

        ea_list = self._scan_researched_folders()
        default_selected = ea_list[0] if ea_list else self.cfg.get("active_ea", "TRB")

        # ── 1. Strategy Assets & Overview Card ─────────────────────────────────
        assets_card = make_card(self)
        assets_card.grid(row=1, column=0, sticky="ew", padx=32, pady=(16, 0))
        assets_card.columnconfigure(1, weight=1)

        # EA selector row
        sel_row = ctk.CTkFrame(assets_card, fg_color="transparent")
        sel_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 10))
        ctk.CTkLabel(sel_row, text="Select Researched EA:", font=FB, text_color=C["sub"]).pack(side="left", padx=(0, 10))

        self._ea_combo = ctk.CTkComboBox(
            sel_row, values=ea_list, width=240,
            command=self._on_ea_selected
        )
        self._ea_combo.set(default_selected)
        self._ea_combo.pack(side="left", padx=(0, 10))

        make_btn(sel_row, "🔄 Refresh Folders", self._refresh_folders,
                 color=C["card"], hover=C["hover"], width=130).pack(side="left", padx=(0, 8))
        make_btn(sel_row, "📂 Open EA Folder", self._open_output,
                 color=C["card"], hover=C["hover"], width=130).pack(side="left")

        # Asset details row
        self._asset_frame = ctk.CTkFrame(assets_card, fg_color="#1a202c", corner_radius=8)
        self._asset_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 16))
        self._asset_frame.columnconfigure((0, 1, 2), weight=1)

        self._lbl_logic_doc = ctk.CTkLabel(self._asset_frame, text="📄 Logic Doc: Checking...", font=FB, text_color=C["sub"], anchor="w")
        self._lbl_logic_doc.grid(row=0, column=0, sticky="w", padx=14, pady=8)
        self._btn_open_doc = make_btn(self._asset_frame, "Open Word Doc", self._open_logic_doc,
                                      color=C["card"], hover=C["hover"], width=110)
        self._btn_open_doc.grid(row=0, column=1, sticky="w", padx=4, pady=8)

        self._lbl_mq5 = ctk.CTkLabel(self._asset_frame, text="💻 MQL5 Code: Checking...", font=FB, text_color=C["sub"], anchor="w")
        self._lbl_mq5.grid(row=1, column=0, sticky="w", padx=14, pady=8)
        self._btn_open_mq5 = make_btn(self._asset_frame, "Open MQL5", self._open_mq5_code,
                                      color=C["card"], hover=C["hover"], width=110)
        self._btn_open_mq5.grid(row=1, column=1, sticky="w", padx=4, pady=8)

        self._lbl_bt_status = ctk.CTkLabel(self._asset_frame, text="📊 Default Backtest: Checking...", font=FB, text_color=C["sub"], anchor="w")
        self._lbl_bt_status.grid(row=2, column=0, sticky="w", padx=14, pady=8)
        btn_box = ctk.CTkFrame(self._asset_frame, fg_color="transparent")
        btn_box.grid(row=2, column=1, columnspan=2, sticky="w", padx=4, pady=8)
        self._btn_open_html = make_btn(btn_box, "HTML Report", self._open_html_report,
                                       color=C["card"], hover=C["hover"], width=105)
        self._btn_open_html.pack(side="left", padx=(0, 6))
        self._btn_open_rep_doc = make_btn(btn_box, "Word Report", self._open_word_report,
                                          color=C["card"], hover=C["hover"], width=105)
        self._btn_open_rep_doc.pack(side="left")

        # ── 2. Backtest Parameters Form Card ──────────────────────────────────
        form = make_card(self)
        form.grid(row=2, column=0, sticky="ew", padx=32, pady=(16, 0))

        cfg = self.cfg
        default_expert = cfg.get("expert", f"{default_selected} V2.0.ex5")
        fields = [
            ("Strategy / EA Name", default_selected,          "name"),
            ("Expert (.ex5)",      default_expert,            "expert"),
            ("Set File",           "(Default EA Inputs)",     "set_file"),
            ("Symbol",             cfg.get("symbol",""),      "symbol"),
            ("Period",             cfg.get("period",""),      "period"),
            ("From Date",          cfg.get("train_from",""),  "from_date"),
            ("To Date",            cfg.get("holdout_to",""),  "to_date"),
            ("Deposit ($)",        cfg.get("deposit","2500"), "deposit"),
        ]
        self._entries = {}
        for i, (label, default, key) in enumerate(fields):
            row_f = ctk.CTkFrame(form, fg_color="transparent")
            row_f.grid(row=i, column=0, sticky="ew", padx=20, pady=5)
            ctk.CTkLabel(row_f, text=label, font=FB, text_color=C["sub"],
                         width=150, anchor="e").pack(side="left", padx=(0,12))
            e = make_entry(row_f, placeholder=default, width=360)
            e.insert(0, default)
            e.pack(side="left")
            self._entries[key] = e
            if key == "set_file":
                make_btn(row_f, "Browse .set", self._browse_set,
                         color=C["card"], hover=C["hover"], width=110).pack(side="left", padx=(8,0))
                make_btn(row_f, "Use Defaults", lambda: self._set(self._entries["set_file"], "(Default EA Inputs)"),
                         color=C["card"], hover=C["hover"], width=100).pack(side="left", padx=(6,0))

        # Run Buttons Row
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=len(fields), column=0, sticky="ew", padx=20, pady=(14, 16))
        make_btn(btn_row, "▶  Run Research Backtest", self._run, width=230).pack(side="left")
        make_btn(btn_row, "📂 Open EA Folder",
                 self._open_output, color=C["card"], hover=C["hover"], width=160).pack(side="left", padx=(12,0))

        # ── 3. Live Output Log ────────────────────────────────────────────────
        log_card = make_card(self)
        log_card.grid(row=3, column=0, sticky="nsew", padx=32, pady=(16, 24))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        make_label(log_card, "Live Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self._log = make_log(log_card, height=220)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

        # Initial populate
        self._update_asset_view(default_selected)

    def _refresh_folders(self):
        ea_list = self._scan_researched_folders()
        self._ea_combo.configure(values=ea_list)
        current = self._ea_combo.get()
        if current not in ea_list and ea_list:
            current = ea_list[0]
            self._ea_combo.set(current)
        self._update_asset_view(current)

    def _on_ea_selected(self, choice):
        self._update_asset_view(choice)

    def _update_asset_view(self, ea_name):
        ea_info = self._ea_data.get(ea_name, {})
        self._set(self._entries["name"], ea_name)

        # Update expert input
        if ea_info.get("ex5"):
            self._set(self._entries["expert"], ea_info["ex5"].name)
        else:
            expert_val = self._entries["expert"].get()
            if not expert_val or ea_name.lower() in expert_val.lower():
                self._set(self._entries["expert"], f"{ea_name} V2.0.ex5")

        # Update set file
        if ea_info.get("sets"):
            self._set(self._entries["set_file"], ea_info["sets"][0].name)
        else:
            self._set(self._entries["set_file"], "(Default EA Inputs)")

        # Logic doc status
        if ea_info.get("logic_doc"):
            doc_name = ea_info["logic_doc"].name
            self._lbl_logic_doc.configure(text=f"📄 Strategy Logic: {doc_name}", text_color=C["text"])
            self._btn_open_doc.configure(state="normal")
        else:
            self._lbl_logic_doc.configure(text="📄 Strategy Logic: None found in folder", text_color=C["sub"])
            self._btn_open_doc.configure(state="disabled")

        # MQL5 code status
        if ea_info.get("mq5"):
            mq5_name = ea_info["mq5"].name
            self._lbl_mq5.configure(text=f"💻 MQL5 Code: {mq5_name}", text_color=C["text"])
            self._btn_open_mq5.configure(state="normal")
        else:
            self._lbl_mq5.configure(text="💻 MQL5 Code: None found in folder", text_color=C["sub"])
            self._btn_open_mq5.configure(state="disabled")

        # Backtest status
        has_html = ea_info.get("html_report")
        has_word = ea_info.get("word_report")
        summary = ea_info.get("summary")

        if has_html or summary:
            if summary and "metrics" in summary:
                m = summary["metrics"]
                status_txt = f"📊 Backtest: ✔ Completed (Profit: ${m.get('net_profit', 0):,.2f} | PF: {m.get('profit_factor', 0):.2f} | DD: {m.get('max_drawdown_pct', 0):.1f}%)"
            else:
                status_txt = "📊 Backtest: ✔ Completed (Report available)"
            self._lbl_bt_status.configure(text=status_txt, text_color="#10b981")
            self._btn_open_html.configure(state="normal" if has_html else "disabled")
            self._btn_open_rep_doc.configure(state="normal" if has_word else "disabled")
        else:
            self._lbl_bt_status.configure(text="📊 Backtest: Not run yet for this EA", text_color=C["sub"])
            self._btn_open_html.configure(state="disabled")
            self._btn_open_rep_doc.configure(state="disabled")

    def _open_file_safely(self, target_path):
        if not target_path or not Path(target_path).exists():
            messagebox.showinfo("Not Found", f"File not found: {target_path}")
            return
        p_str = str(Path(target_path).resolve())
        try:
            if sys.platform == "win32":
                os.startfile(p_str)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p_str])
            else:
                subprocess.Popen(["xdg-open", p_str])
        except Exception as e:
            messagebox.showerror("Open Error", f"Could not open file:\n{e}")

    def _open_logic_doc(self):
        ea_name = self._ea_combo.get().strip()
        info = self._ea_data.get(ea_name, {})
        if info.get("logic_doc"):
            self._open_file_safely(info["logic_doc"])
        else:
            messagebox.showinfo("No Document", "No strategy logic document found in this EA folder.")

    def _open_mq5_code(self):
        ea_name = self._ea_combo.get().strip()
        info = self._ea_data.get(ea_name, {})
        if info.get("mq5"):
            self._open_file_safely(info["mq5"])
        else:
            messagebox.showinfo("No MQL5 Code", "No .mq5 file found in this EA folder.")

    def _open_html_report(self):
        ea_name = self._ea_combo.get().strip()
        info = self._ea_data.get(ea_name, {})
        if info.get("html_report"):
            self._open_file_safely(info["html_report"])
        else:
            messagebox.showinfo("No Report", "No backtest HTML report found. Run the research backtest first.")

    def _open_word_report(self):
        ea_name = self._ea_combo.get().strip()
        info = self._ea_data.get(ea_name, {})
        if info.get("word_report"):
            self._open_file_safely(info["word_report"])
        else:
            messagebox.showinfo("No Report", "No Word backtest report found. Run the research backtest first.")

    def _browse_set(self):
        f = filedialog.askopenfilename(
            title="Select .set file",
            filetypes=[("SET files", "*.set"), ("All files", "*.*")]
        )
        if f:
            self._entries["set_file"].delete(0, "end")
            self._entries["set_file"].insert(0, Path(f).name)

    def _get_vals(self):
        return {k: e.get().strip() for k, e in self._entries.items()}

    def _run(self):
        v = self._get_vals()
        ea_name = v.get("name", "").strip()
        if not ea_name:
            messagebox.showwarning("Missing", "Strategy / EA Name is required.")
            return

        expert_val = v.get("expert", "").strip()
        if not expert_val.lower().endswith(".ex5"):
            expert_val += ".ex5"

        set_val = v.get("set_file", "").strip()
        if set_val in ("(Default EA Inputs)", "(none)", "default"):
            set_val = ""

        self.log_clear(self._log)

        base_dir = self._get_research_base()
        target_ea_dir = base_dir / ea_name
        target_ea_dir.mkdir(parents=True, exist_ok=True)

        env_extra = {
            "AF_STRATEGY_NAME": ea_name,
            "AF_EA_NAME":       ea_name,
            "AF_EXPERT":        expert_val,
            "AF_SET_FILE":      set_val,
            "AF_SYMBOL":        v["symbol"],
            "AF_PERIOD":        v["period"],
            "AF_FROM_DATE":     v["from_date"],
            "AF_TO_DATE":       v["to_date"],
            "AF_DEPOSIT":       v["deposit"],
            "AF_RESEARCH_DIR":  str(base_dir),
        }

        def on_done():
            self._refresh_folders()

        self.run_script("run_research_backtest.py", self._log, env_extra=env_extra, on_done=on_done)

    def _open_output(self):
        v = self._get_vals()
        name = v.get("name", "").strip() or self._ea_combo.get().strip() or "TRB"
        base_dir = self._get_research_base()
        out_dir = base_dir / name
        out_dir.mkdir(parents=True, exist_ok=True)
        self._open_file_safely(out_dir)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Optimization Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OptimizePanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.active_ea = self.cfg.get("active_ea", "TRB").upper()
        self._build()

    def _get_researched_eas(self) -> list[str]:
        base = SCRIPT_DIR / "researched_strategies"
        eas = []
        if base.exists():
            for d in sorted(base.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    eas.append(d.name)
        if not eas:
            eas = ["TRB", "ORB"]
        elif "TRB" not in eas:
            eas.append("TRB")
        return eas

    def _get_mql5_status_text(self, ea: str) -> str:
        base = SCRIPT_DIR / "researched_strategies"
        target_folder = None
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and d.name.lower() == ea.lower():
                    target_folder = d
                    break
        if target_folder and target_folder.exists():
            mq5s = list(target_folder.glob("*.mq5"))
            if mq5s:
                try:
                    import mql5_parser
                    cfg = mql5_parser.get_strategy_mql5_config(ea)
                    inds = len(cfg.get("indicators", []))
                    params = len(cfg.get("params", []))
                    return f"MQL5: {mq5s[0].name} ({inds} filters, {params} params)"
                except Exception:
                    return f"MQL5: {mq5s[0].name}"
        return f"MQL5: researched_strategies/{ea}/{ea}.mq5"

    def _on_ea_selected(self, new_ea: str):
        self.active_ea = new_ea.strip()
        self.cfg["active_ea"] = self.active_ea
        self.cfg["quant_name"] = self.active_ea

        # Search flexibly in researched_strategies / strategies
        clean_ea = re.sub(r'\.(ex5|mq5)$', '', self.active_ea, flags=re.IGNORECASE).strip().lower()
        search_dirs = [
            SCRIPT_DIR / "researched_strategies",
            SCRIPT_DIR / "strategies",
            SCRIPT_DIR,
        ]
        if self.cfg.get("research_dir"):
            search_dirs.insert(0, Path(self.cfg["research_dir"]))

        found_ex5 = None
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            # Check direct .ex5 in directory
            for f in sdir.glob("*.ex5"):
                low = f.stem.lower()
                if low == clean_ea or low.startswith(clean_ea) or clean_ea.startswith(low):
                    found_ex5 = f.name
                    break
            if found_ex5:
                break
            for sub in sdir.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    sub_low = sub.name.lower()
                    if sub_low == clean_ea or sub_low.startswith(clean_ea) or clean_ea.startswith(sub_low) or clean_ea in sub_low:
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

        if found_ex5:
            self.cfg["expert"] = found_ex5
        else:
            self.cfg["expert"] = f"{self.active_ea}.ex5"

        save_config(self.cfg)

        # Synchronize EA binary to MT5 Experts directory
        try:
            from mt5_optimizer import sync_ea_to_mt5
            tdir = self.cfg.get("terminal_data_dir")
            tpath = self.cfg.get("terminal_path")
            if tdir:
                resolved_exp = sync_ea_to_mt5(self.cfg["expert"], tdir, tpath)
                if resolved_exp:
                    self.cfg["expert"] = resolved_exp
                    save_config(self.cfg)
        except Exception:
            pass

        if hasattr(self, "_mql5_badge"):
            self._mql5_badge.configure(text=self._get_mql5_status_text(self.active_ea))
        if hasattr(self, "_ea_info_val"):
            self._ea_info_val.configure(text=f"{self.active_ea}  –  {self.cfg.get('expert','')}")

    def _build(self):
        pad = dict(padx=32, pady=(24, 0))
        make_section_header(self, "⚙  Optimization Pipeline",
            "Select strategy, configure indicator filter switchboard and parameter ranges from MQL5"
        ).grid(row=0, column=0, sticky="ew", **pad)

        cfg = self.cfg

        # Strategy selector card
        strat_card = make_card(self)
        strat_card.grid(row=1, column=0, sticky="ew", padx=32, pady=(16, 0))
        strat_card.columnconfigure(1, weight=1)

        make_label(strat_card, "Strategy To Optimize:", font=FB, color=C["text"]).grid(row=0, column=0, padx=16, pady=12, sticky="w")

        available_eas = self._get_researched_eas()
        if self.active_ea not in available_eas:
            available_eas.insert(0, self.active_ea)

        self._ea_var = ctk.StringVar(value=self.active_ea)
        self._ea_combo = ctk.CTkComboBox(
            strat_card,
            values=available_eas,
            variable=self._ea_var,
            width=200,
            command=self._on_ea_selected
        )
        self._ea_combo.grid(row=0, column=1, padx=8, pady=12, sticky="w")

        def _refresh_eas():
            eas = self._get_researched_eas()
            self._ea_combo.configure(values=eas)
            self._mql5_badge.configure(text=self._get_mql5_status_text(self.active_ea))

        make_btn(strat_card, "🔄 Scan Strategies", _refresh_eas, color=C["hover"], width=130).grid(row=0, column=2, padx=8, pady=12, sticky="w")

        self._mql5_badge = make_label(strat_card, self._get_mql5_status_text(self.active_ea), font=FSM, color=C["success"])
        self._mql5_badge.grid(row=0, column=3, padx=16, pady=12, sticky="e")

        # Config overview cards
        info = make_card(self)
        info.grid(row=2, column=0, sticky="ew", padx=32, pady=(16, 0))
        info.columnconfigure((0,1,2,3), weight=1)

        f_ea = ctk.CTkFrame(info, fg_color="transparent")
        f_ea.grid(row=0, column=0, padx=16, pady=14, sticky="nsew")
        make_label(f_ea, "EA / Expert", font=FSM, color=C["sub"]).pack(anchor="w")
        self._ea_info_val = make_label(f_ea, cfg.get("active_ea","?") + "  –  " + cfg.get("expert",""), font=FH3, color=C["text"])
        self._ea_info_val.pack(anchor="w")

        info_data = [
            ("Symbol",         cfg.get("symbol","") + "  " + cfg.get("period","")),
            ("Date Range",     cfg.get("train_from","") + " → " + cfg.get("holdout_to","")),
            ("Deposit",        f"${float(cfg.get('deposit',2500)):,.0f}  {cfg.get('currency','USD')}"),
        ]
        for i, (lbl, val) in enumerate(info_data, start=1):
            f = ctk.CTkFrame(info, fg_color="transparent")
            f.grid(row=0, column=i, padx=16, pady=14, sticky="nsew")
            make_label(f, lbl, font=FSM, color=C["sub"]).pack(anchor="w")
            make_label(f, val, font=FH3, color=C["text"]).pack(anchor="w")

        # Phase progress indicators
        prog_card = make_card(self)
        prog_card.grid(row=3, column=0, sticky="ew", padx=32, pady=(16, 0))
        prog_card.columnconfigure((0,1,2,3), weight=1)
        self._phase_labels = {}
        for i, (phase, icon) in enumerate([
            ("Train\nOptimize", "🔵"),
            ("Val / Holdout",   "🔵"),
            ("Monte Carlo",     "🔵"),
            ("Passed →",        "🔵"),
        ]):
            f = ctk.CTkFrame(prog_card, fg_color="transparent")
            f.grid(row=0, column=i, padx=8, pady=12, sticky="nsew")
            ic  = make_label(f, icon, font=ctk.CTkFont("Segoe UI",22))
            ic.pack()
            lbl = make_label(f, phase, font=FSM, color=C["sub"])
            lbl.pack()
            self._phase_labels[i] = ic

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=32, pady=(20, 0))
        make_btn(btn_row, "▶  Run Full Pipeline", self._run, width=190).pack(side="left")
        make_btn(btn_row, "🔧  Parameters & Ranges", self._open_param_dialog,
                 color=C["accent"], hover=C["hover"], width=190).pack(side="left", padx=(10, 0))
        make_btn(btn_row, "🎯  Qualification Gates", self._open_criteria_dialog,
                 color=C["accent"], hover=C["hover"], width=180).pack(side="left", padx=(10, 0))
        make_btn(btn_row, "⚙  Settings",
                 lambda: self.app.show_panel("settings"),
                 color=C["card"], hover=C["hover"], width=130).pack(side="left", padx=(10, 0))
        make_btn(btn_row, "📂 Runs Folder",
                 lambda: os.startfile(self.cfg.get("work_dir", str(SCRIPT_DIR))),
                 color=C["card"], hover=C["hover"], width=140).pack(side="left", padx=(10, 0))

        # Log
        log_card = make_card(self)
        log_card.grid(row=5, column=0, sticky="nsew", padx=32, pady=(20, 28))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)
        make_label(log_card, "Live Pipeline Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12,4))
        self._log = make_log(log_card, height=300)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _run(self):
        self.cfg["active_ea"] = self.active_ea
        self.cfg["quant_name"] = self.active_ea
        save_config(self.cfg)
        self.log_clear(self._log)
        env_extra = {
            "AF_ACTIVE_EA": self.active_ea,
            "AF_EXPERT": self.cfg.get("expert", ""),
        }
        self.run_script("run_optimization.py", self._log, env_extra=env_extra)

    def _open_param_dialog(self):
        ea = getattr(self, "active_ea", self.cfg.get("active_ea", "TRB")).upper()
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Optimization Parameters & Ranges — {ea}")
        dlg.geometry("820x680")
        dlg.configure(fg_color=C["bg"])
        dlg.grab_set()

        make_section_header(dlg, f"🔧 {ea} Parameters & Indicator Ranges",
            f"Configured directly from {ea}'s MQL5 code in researched_strategies/{ea}/"
        ).pack(fill="x", padx=24, pady=(20, 10))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color=C["panel"], corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=24, pady=10)
        scroll.columnconfigure(1, weight=1)

        opt_params = self.cfg.get("optimization_params", {}).get(ea, self.cfg.get("optimization_params", {}))
        fixed_dict = dict(opt_params.get("fixed_params", {}))
        ranges_dict = dict(opt_params.get("opt_ranges", {}))
        toggles_dict = dict(opt_params.get("indicator_toggles", {}))

        # Parse from MQL5 file in researched_strategies/<EA>/
        parsed_config = None
        try:
            import mql5_parser
            parsed_config = mql5_parser.get_strategy_mql5_config(ea)
        except Exception:
            pass

        if parsed_config and parsed_config.get("indicators"):
            default_indicators = []
            for ind in parsed_config["indicators"]:
                def_toggle = 1 if ind.get("enabled", True) else 0
                default_indicators.append((
                    ind["toggleParam"],
                    ind["name"],
                    toggles_dict.get(ind["toggleParam"], def_toggle)
                ))
        elif ea == "ORB":
            default_indicators = [
                ("InpUseEmaFilter", "EMA Filter", toggles_dict.get("InpUseEmaFilter", 1)),
                ("InpUseRsiFilter", "RSI Filter", toggles_dict.get("InpUseRsiFilter", 0)),
                ("InpUseAtrFilter", "ATR Filter", toggles_dict.get("InpUseAtrFilter", 0)),
                ("InpUseAdxFilter", "ADX Filter", toggles_dict.get("InpUseAdxFilter", 0)),
                ("InpUseMacdFilter", "MACD Filter", toggles_dict.get("InpUseMacdFilter", 1)),
                ("InpUseHtfFilter", "HTF Filter", toggles_dict.get("InpUseHtfFilter", 0)),
            ]
        else:
            default_indicators = [
                ("UseTrendFilter", "EMA Trend Filter", toggles_dict.get("UseTrendFilter", 1)),
                ("UseAdxFilter", "ADX Volatility Filter", toggles_dict.get("UseAdxFilter", 1)),
                ("UseAtrFilter", "ATR Range Filter", toggles_dict.get("UseAtrFilter", 1)),
                ("UseAtrTrailingStop", "ATR Trailing Stop", toggles_dict.get("UseAtrTrailingStop", 0)),
                ("UseNewsFilter", "News Event Filter", toggles_dict.get("UseNewsFilter", 0)),
            ]

        if parsed_config and parsed_config.get("params"):
            default_params = []
            for p in parsed_config["params"]:
                rng = p.get("range", {})
                rng_tuple = (rng.get("start", 0), rng.get("step", 1), rng.get("stop", 10))
                default_params.append((
                    p["name"],
                    p.get("mode", "fixed"),
                    p.get("fixedValue", 0),
                    rng_tuple
                ))
        elif ea == "ORB":
            default_params = [
                ("InpTPRatio", "optimize", 1.5, (1.0, 0.25, 3.0)),
                ("InpSLBufferPips", "optimize", 1, (0, 1, 10)),
                ("InpMaxRangePips", "optimize", 50, (30, 10, 150)),
                ("InpFixedLotSize", "fixed", 1.0, (0.1, 0.1, 2.0)),
                ("InpRiskPercent", "optimize", 1.0, (0.25, 0.25, 2.0)),
                ("InpRangeStartHour", "optimize", 8, (6, 1, 10)),
                ("InpRangeEndHour", "optimize", 9, (9, 1, 12)),
                ("InpEntryCutoffHour", "optimize", 15, (12, 1, 20)),
                ("InpMacdFast", "optimize", 12, (6, 1, 16)),
                ("InpMacdSlow", "optimize", 26, (18, 2, 34)),
                ("InpMacdSignal", "optimize", 9, (5, 1, 13)),
            ]
        else:
            default_params = [
                ("LotSize", "fixed", 0.2, (0.1, 0.05, 0.5)),
                ("PipsOffset", "fixed", 13, (8, 1, 20)),
                ("TPMultiplier", "fixed", 3.0, (1.5, 0.5, 4.5)),
                ("MinRangePips", "fixed", 25, (15, 5, 50)),
                ("MaxRangePips", "fixed", 180, (100, 20, 240)),
                ("StartHourGMT", "fixed", 0, (0, 1, 3)),
                ("EndHourGMT", "fixed", 7, (5, 1, 9)),
                ("CancelHourGMT", "fixed", 10, (8, 1, 14)),
                ("CloseHourGMT", "fixed", 13, (11, 1, 17)),
                ("RiskPercent", "fixed", 1.0, (0.25, 0.25, 2.0)),
                ("EMAPeriod", "fixed", 200, (50, 25, 300)),
                ("AdxPeriod", "optimize", 14, (7, 1, 21)),
                ("AdxMin", "optimize", 20.0, (15.0, 2.5, 40.0)),
                ("AtrPeriod", "optimize", 14, (7, 1, 21)),
                ("AtrMinPips", "optimize", 0.0, (0.0, 2.0, 30.0)),
            ]

        # Indicator Toggles UI
        make_label(scroll, "📊 Indicator Filters", font=FH3, color=C["accent"]).pack(anchor="w", padx=12, pady=(8, 4))
        ind_frame = ctk.CTkFrame(scroll, fg_color=C["card"], corner_radius=8)
        ind_frame.pack(fill="x", padx=12, pady=(0, 14))

        ind_vars = {}
        for row_idx, (t_param, t_label, default_val) in enumerate(default_indicators):
            init_val = bool(toggles_dict.get(t_param, default_val))
            var = ctk.BooleanVar(value=init_val)
            ind_vars[t_param] = var
            cb = ctk.CTkCheckBox(ind_frame, text=f"{t_label} ({t_param})", variable=var,
                                 font=FB, fg_color=C["accent"], hover_color=C["hover"])
            cb.grid(row=row_idx // 2, column=row_idx % 2, sticky="w", padx=16, pady=8)

        # Parameters Table UI
        make_label(scroll, "⚙ Core & Indicator Parameters (Fixed vs Optimize)", font=FH3, color=C["accent"]).pack(anchor="w", padx=12, pady=(8, 4))
        params_container = ctk.CTkFrame(scroll, fg_color="transparent")
        params_container.pack(fill="x", padx=12, pady=4)

        param_rows = {}
        for p_name, def_mode, def_fixed, def_range in default_params:
            # Current value from config if exists
            cur_is_opt = p_name in ranges_dict or (def_mode == "optimize" and p_name not in fixed_dict)
            cur_fixed = fixed_dict.get(p_name, def_fixed)
            cur_rng = ranges_dict.get(p_name, def_range)

            rf = ctk.CTkFrame(params_container, fg_color=C["card"], corner_radius=6)
            rf.pack(fill="x", pady=4)

            # Param Name
            make_label(rf, p_name, font=FB, color=C["text"], width=180, anchor="w").pack(side="left", padx=12, pady=8)

            # Mode switch (Fixed vs Optimize)
            mode_var = ctk.StringVar(value="Optimize" if cur_is_opt else "Fixed")
            seg = ctk.CTkSegmentedButton(rf, values=["Fixed", "Optimize"], variable=mode_var, width=150, font=FSM)
            seg.pack(side="left", padx=8)

            # Input entries
            inp_frame = ctk.CTkFrame(rf, fg_color="transparent")
            inp_frame.pack(side="left", fill="x", expand=True, padx=8)

            # Fixed entry
            e_fixed = make_entry(inp_frame, width=90)
            e_fixed.insert(0, str(cur_fixed))

            # Range entries (start, step, stop)
            range_frame = ctk.CTkFrame(inp_frame, fg_color="transparent")
            make_label(range_frame, "Start:", font=FSM, color=C["sub"]).pack(side="left")
            e_start = make_entry(range_frame, width=60); e_start.insert(0, str(cur_rng[0]))
            e_start.pack(side="left", padx=4)

            make_label(range_frame, "Step:", font=FSM, color=C["sub"]).pack(side="left", padx=(6,0))
            e_step = make_entry(range_frame, width=60); e_step.insert(0, str(cur_rng[1]))
            e_step.pack(side="left", padx=4)

            make_label(range_frame, "Stop:", font=FSM, color=C["sub"]).pack(side="left", padx=(6,0))
            e_stop = make_entry(range_frame, width=60); e_stop.insert(0, str(cur_rng[2]))
            e_stop.pack(side="left", padx=4)

            def _update_view(mode_val, ef=e_fixed, rf_box=range_frame):
                if mode_val == "Fixed":
                    rf_box.pack_forget()
                    ef.pack(side="left", padx=4)
                else:
                    ef.pack_forget()
                    rf_box.pack(side="left")

            mode_var.trace_add("write", lambda *args, mv=mode_var, ef=e_fixed, rf_box=range_frame: _update_view(mv.get(), ef, rf_box))
            _update_view(mode_var.get(), e_fixed, range_frame)

            param_rows[p_name] = {
                "mode": mode_var,
                "fixed": e_fixed,
                "start": e_start,
                "step": e_step,
                "stop": e_stop
            }

        # Footer Actions
        footer = ctk.CTkFrame(dlg, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=16)

        status_lbl = make_label(footer, "", font=FB, color=C["success"])
        status_lbl.pack(side="left", padx=8)

        def _save_params():
            new_fixed = {}
            new_ranges = {}
            new_toggles = {k: 1 if v.get() else 0 for k, v in ind_vars.items()}

            for p_name, widgets in param_rows.items():
                m = widgets["mode"].get()
                if m == "Fixed":
                    try:
                        v = widgets["fixed"].get().strip()
                        new_fixed[p_name] = float(v) if "." in v else int(v)
                    except ValueError:
                        new_fixed[p_name] = widgets["fixed"].get().strip()
                else:
                    try:
                        st = float(widgets["start"].get().strip())
                        sp = float(widgets["step"].get().strip())
                        so = float(widgets["stop"].get().strip())
                        if st.is_integer() and sp.is_integer() and so.is_integer():
                            new_ranges[p_name] = [int(st), int(sp), int(so)]
                        else:
                            new_ranges[p_name] = [st, sp, so]
                    except ValueError:
                        pass

            if "optimization_params" not in self.app.config:
                self.app.config["optimization_params"] = {}

            ea_data = {
                "active_ea": ea,
                "indicator_toggles": new_toggles,
                "fixed_params": new_fixed,
                "opt_ranges": new_ranges,
            }
            self.app.config["optimization_params"][ea] = ea_data
            self.app.config["optimization_params"]["active_ea"] = ea
            self.app.config["optimization_params"]["indicator_toggles"] = new_toggles
            self.app.config["optimization_params"]["fixed_params"] = new_fixed
            self.app.config["optimization_params"]["opt_ranges"] = new_ranges

            if save_config(self.app.config):
                status_lbl.configure(text="✔  Parameters saved to config.json!", text_color=C["success"])
            else:
                status_lbl.configure(text="✘  Save failed", text_color=C["danger"])

        make_btn(footer, "💾 Save & Apply", _save_params, width=160).pack(side="right", padx=(8, 0))
        make_btn(footer, "Close", dlg.destroy, color=C["card"], hover=C["hover"], width=100).pack(side="right")

    def _open_criteria_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Candidate Qualification Gates (Pass/Fail Thresholds)")
        dlg.geometry("900x720")
        dlg.configure(fg_color=C["bg"])
        dlg.grab_set()

        make_section_header(dlg, "🎯 Candidate Qualification Gates",
            "Adjust candidate survival thresholds for Train (in-sample optimization), Validation (OOS 1), and Holdout (OOS 2)"
        ).pack(fill="x", padx=24, pady=(20, 10))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color=C["panel"], corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=24, pady=10)

        raw_cfg = self.app.config.get("qualification_criteria", {})
        default_train = {
            "min_profit_gain_pct": 30.0,
            "max_drawdown_pct": 20.0,
            "min_avg_trades_month": 1.0,
            "min_sharpe_ratio": 0.50,
            "min_ret_dd_ratio": 1.30,
            "min_profit_factor": 1.10,
            "min_net_profit": 0.0,
            "min_total_trades": 0,
            "min_win_rate_pct": 0.0,
        }
        default_oos = {
            "min_profit_gain_pct": 15.0,
            "max_drawdown_pct": 20.0,
            "min_avg_trades_month": 1.0,
            "min_sharpe_ratio": 0.50,
            "min_ret_dd_ratio": 1.00,
            "min_profit_factor": 1.00,
            "min_net_profit": 0.0,
            "min_total_trades": 0,
            "min_win_rate_pct": 0.0,
        }

        train_cfg = dict(default_train)
        train_cfg.update(raw_cfg.get("train", {}))
        val_cfg = dict(default_oos)
        val_cfg.update(raw_cfg.get("val", {}))
        holdout_cfg = dict(default_oos)
        holdout_cfg.update(raw_cfg.get("holdout", {}))

        metrics = [
            ("min_profit_gain_pct", "Net Profit Gain %", "%", "Min % return over starting capital"),
            ("max_drawdown_pct", "Max Drawdown %", "%", "Maximum allowable drawdown % (lower is stricter)"),
            ("min_profit_factor", "Profit Factor (PF)", "ratio", "Gross wins / gross losses (1.0 = break-even)"),
            ("min_sharpe_ratio", "Sharpe Ratio", "ratio", "Risk-adjusted return vs volatility"),
            ("min_ret_dd_ratio", "Return / DD Ratio", "ratio", "Recovery factor: Net profit / Max drawdown"),
            ("min_avg_trades_month", "Avg Trades / Month", "tr/mo", "Minimum monthly trade frequency density"),
            ("min_net_profit", "Net Profit Floor", "$", "Dollar threshold (0 = positive balance)"),
            ("min_total_trades", "Min Total Trades", "trades", "Sample size floor (0 = disabled)"),
            ("min_win_rate_pct", "Min Win Rate %", "%", "Win percentage threshold (0 = disabled)"),
        ]

        preset_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        preset_frame.pack(fill="x", padx=16, pady=(10, 16))
        make_label(preset_frame, "⚡ Quick Presets:", font=FB, color=C["sub"]).pack(side="left", padx=(0, 8))

        entries = {"train": {}, "val": {}, "holdout": {}}

        def _apply_preset(t_gain, t_dd, t_pf, t_sharpe, t_retdd, t_tpm, v_gain, v_dd, v_pf, v_sharpe, v_retdd, v_tpm):
            p_map = {
                "train": {"min_profit_gain_pct": t_gain, "max_drawdown_pct": t_dd, "min_profit_factor": t_pf, "min_sharpe_ratio": t_sharpe, "min_ret_dd_ratio": t_retdd, "min_avg_trades_month": t_tpm},
                "val": {"min_profit_gain_pct": v_gain, "max_drawdown_pct": v_dd, "min_profit_factor": v_pf, "min_sharpe_ratio": v_sharpe, "min_ret_dd_ratio": v_retdd, "min_avg_trades_month": v_tpm},
                "holdout": {"min_profit_gain_pct": v_gain, "max_drawdown_pct": v_dd, "min_profit_factor": v_pf, "min_sharpe_ratio": v_sharpe, "min_ret_dd_ratio": v_retdd, "min_avg_trades_month": v_tpm},
            }
            for phase, f_dict in p_map.items():
                for k, val in f_dict.items():
                    if k in entries[phase]:
                        entries[phase][k].delete(0, "end")
                        entries[phase][k].insert(0, str(val))

        make_btn(preset_frame, "Balanced", lambda: _apply_preset(30.0, 20.0, 1.10, 0.50, 1.30, 1.0, 15.0, 20.0, 1.00, 0.50, 1.00, 1.0),
                 color=C["card"], hover=C["hover"], width=90).pack(side="left", padx=4)
        make_btn(preset_frame, "Prop Firm (8% DD)", lambda: _apply_preset(20.0, 8.0, 1.35, 0.90, 2.50, 2.0, 10.0, 8.0, 1.20, 0.75, 1.50, 1.5),
                 color=C["card"], hover=C["hover"], width=130).pack(side="left", padx=4)
        make_btn(preset_frame, "High Frequency", lambda: _apply_preset(25.0, 15.0, 1.15, 0.60, 1.50, 4.0, 12.0, 15.0, 1.05, 0.50, 1.10, 3.5),
                 color=C["card"], hover=C["hover"], width=120).pack(side="left", padx=4)

        def _copy_train_to_oos():
            for k in entries["train"]:
                val_str = entries["train"][k].get().strip()
                try:
                    f_val = float(val_str)
                    if k == "min_profit_gain_pct":
                        decayed = round(f_val * 0.5, 1)
                    elif k in ("min_sharpe_ratio", "min_ret_dd_ratio", "min_profit_factor"):
                        decayed = round(max(1.0 if k == "min_profit_factor" else 0.5, f_val * 0.8), 2)
                    elif k == "min_avg_trades_month":
                        decayed = round(f_val * 0.8, 1)
                    else:
                        decayed = f_val
                    decay_str = str(int(decayed) if decayed.is_integer() else decayed)
                except ValueError:
                    decay_str = val_str

                for oos_phase in ("val", "holdout"):
                    entries[oos_phase][k].delete(0, "end")
                    entries[oos_phase][k].insert(0, decay_str)

        make_btn(preset_frame, "📋 Copy Train to OOS (50% Decay)", _copy_train_to_oos,
                 color=C["accent"], hover=C["hover"], width=190).pack(side="left", padx=(12, 4))

        grid_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        grid_frame.pack(fill="x", padx=16, pady=8)
        grid_frame.columnconfigure(0, weight=2)
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(2, weight=1)
        grid_frame.columnconfigure(3, weight=1)

        make_label(grid_frame, "Metric Name & Purpose", font=FB, color=C["sub"]).grid(row=0, column=0, sticky="w", pady=4)
        make_label(grid_frame, "🏋️ Train (In-Sample)", font=FB, color=C["accent"]).grid(row=0, column=1, pady=4)
        make_label(grid_frame, "🔬 Validation (OOS 1)", font=FB, color=C["success"]).grid(row=0, column=2, pady=4)
        make_label(grid_frame, "🛡️ Holdout (OOS 2)", font=FB, color=C["sub"]).grid(row=0, column=3, pady=4)

        for row_idx, (m_key, m_label, m_unit, m_desc) in enumerate(metrics, start=1):
            rf = ctk.CTkFrame(grid_frame, fg_color="transparent")
            rf.grid(row=row_idx, column=0, sticky="w", pady=6)
            make_label(rf, f"{m_label} ({m_unit})", font=FB).pack(anchor="w")
            make_label(rf, m_desc, font=FSM, color=C["sub"]).pack(anchor="w")

            e_train = ctk.CTkEntry(grid_frame, width=90, justify="center")
            e_train.insert(0, str(train_cfg.get(m_key, default_train.get(m_key, 0))))
            e_train.grid(row=row_idx, column=1, padx=6, pady=6)
            entries["train"][m_key] = e_train

            e_val = ctk.CTkEntry(grid_frame, width=90, justify="center")
            e_val.insert(0, str(val_cfg.get(m_key, default_oos.get(m_key, 0))))
            e_val.grid(row=row_idx, column=2, padx=6, pady=6)
            entries["val"][m_key] = e_val

            e_holdout = ctk.CTkEntry(grid_frame, width=90, justify="center")
            e_holdout.insert(0, str(holdout_cfg.get(m_key, default_oos.get(m_key, 0))))
            e_holdout.grid(row=row_idx, column=3, padx=6, pady=6)
            entries["holdout"][m_key] = e_holdout

        footer = ctk.CTkFrame(dlg, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=16)

        status_lbl = make_label(footer, "", font=FB, color=C["success"])
        status_lbl.pack(side="left", padx=8)

        def _save_criteria():
            new_criteria = {"train": {}, "val": {}, "holdout": {}}
            for phase in ("train", "val", "holdout"):
                for m_key in entries[phase]:
                    val_str = entries[phase][m_key].get().strip()
                    try:
                        v = float(val_str)
                        new_criteria[phase][m_key] = int(v) if v.is_integer() else v
                    except ValueError:
                        new_criteria[phase][m_key] = 0.0

            self.app.config["qualification_criteria"] = new_criteria
            if save_config(self.app.config):
                status_lbl.configure(text="✔  Qualification Gates saved to config.json!", text_color=C["success"])
            else:
                status_lbl.configure(text="✘  Save failed", text_color=C["danger"])

        make_btn(footer, "💾 Save & Apply Gates", _save_criteria, width=180).pack(side="right", padx=(8, 0))
        make_btn(footer, "Close", dlg.destroy, color=C["card"], hover=C["hover"], width=100).pack(side="right")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Monte Carlo Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MonteCarloPanel(BasePanel):
    """Monte Carlo Block-Bootstrap Risk Simulation & Prop Firm Certification Panel."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._all_cands_info = []
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(24, 0))
        make_section_header(
            self, "🎲  Monte Carlo Risk Engine",
            "Block-bootstrap Monte Carlo simulations & Prop Firm Certification (Phase 1 & Phase 2)"
        ).grid(row=0, column=0, sticky="ew", **pad)

        cfg = self.cfg

        # ── 3-Column Parameter Configuration Cards ───────────────────────────
        grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid_frame.grid(row=1, column=0, sticky="ew", padx=32, pady=(16, 0))
        grid_frame.columnconfigure((0, 1, 2), weight=1)

        # ── Card 1: Target Scope & Candidate ─────────────────────────────────
        c1 = make_card(grid_frame)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        c1.columnconfigure(0, weight=1)

        c1_hdr = ctk.CTkFrame(c1, fg_color="transparent")
        c1_hdr.pack(fill="x", padx=16, pady=(12, 6))
        make_label(c1_hdr, "🎯 Candidate & Scope", font=FH3, color=C["accent"]).pack(side="left")

        # Run directory selector
        make_label(c1, "Scope / Run Folder", font=FSM, color=C["sub"]).pack(anchor="w", padx=16, pady=(4, 2))
        run_dirs = ["(Auto-detect across workspace)"] + get_run_dirs(cfg.get("work_dir", ""))
        self._run_var = ctk.StringVar(value=run_dirs[0])
        self._run_cb = ctk.CTkComboBox(c1, values=run_dirs, variable=self._run_var,
                                       height=32, font=FB, fg_color=C["inp"],
                                       border_color=C["border"], button_color=C["accent"],
                                       command=lambda r: self._on_run_changed(r))
        self._run_cb.pack(fill="x", padx=16, pady=(0, 6))

        # Candidate selector with refresh
        cand_lbl_frame = ctk.CTkFrame(c1, fg_color="transparent")
        cand_lbl_frame.pack(fill="x", padx=16, pady=(2, 2))
        make_label(cand_lbl_frame, "Candidate", font=FSM, color=C["sub"]).pack(side="left")
        ctk.CTkButton(cand_lbl_frame, text="⟳ Refresh", width=65, height=20, font=FSM,
                      fg_color=C["hover"], hover_color="#2f3d5c",
                      command=self._refresh_candidates_list).pack(side="right")

        self._cand_var = ctk.StringVar()
        self._cand_cb = ctk.CTkComboBox(c1, values=["(scanning...)"], variable=self._cand_var,
                                        height=32, font=FB, fg_color=C["inp"],
                                        border_color=C["border"], button_color=C["accent"],
                                        command=lambda c: self._on_cand_changed(c))
        self._cand_cb.pack(fill="x", padx=16, pady=(0, 6))

        # Custom Candidate Override
        make_label(c1, "Or Custom Candidate ID", font=FSM, color=C["sub"]).pack(anchor="w", padx=16, pady=(2, 2))
        self._custom_cand = make_entry(c1, placeholder="e.g. cand_014", height=30)
        self._custom_cand.pack(fill="x", padx=16, pady=(0, 8))
        self._custom_cand.bind("<KeyRelease>", lambda e: self._on_custom_cand_changed())

        # Candidate Info Mini-Card
        self._cand_info_frame = ctk.CTkFrame(c1, fg_color="#141b2d", corner_radius=8,
                                             border_width=1, border_color=C["border"])
        self._cand_info_frame.pack(fill="x", padx=16, pady=(2, 14))

        self._cand_status_lbl = make_label(self._cand_info_frame, "Status: Ready for Monte Carlo",
                                           font=FSM, color=C["sub"])
        self._cand_status_lbl.pack(anchor="w", padx=10, pady=(6, 2))

        self._cand_dir_lbl = make_label(self._cand_info_frame, "Path: Auto-scan workspace",
                                        font=FSM, color="#64748b")
        self._cand_dir_lbl.pack(anchor="w", padx=10, pady=(0, 2))

        self._cand_trades_lbl = make_label(self._cand_info_frame, "Trades: Checking...",
                                           font=FSM, color="#64748b")
        self._cand_trades_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # ── Card 2: Simulation Horizons ──────────────────────────────────────
        c2 = make_card(grid_frame)
        c2.grid(row=0, column=1, sticky="nsew", padx=8, pady=0)
        c2.columnconfigure(0, weight=1)

        c2_hdr = ctk.CTkFrame(c2, fg_color="transparent")
        c2_hdr.pack(fill="x", padx=16, pady=(12, 6))
        make_label(c2_hdr, "⚡ Simulation Horizons", font=FH3, color=C["blue"]).pack(side="left")
        make_label(c2_hdr, "Block-Bootstrap", font=FSM, color=C["blue"]).pack(side="right")

        # Iterations / Sims count
        sims_f = ctk.CTkFrame(c2, fg_color="transparent")
        sims_f.pack(fill="x", padx=16, pady=(4, 2))
        make_label(sims_f, "Iterations (Runs):", font=FSM, color=C["sub"]).pack(side="left")
        self._sims_entry = make_entry(sims_f, width=100, height=28)
        self._sims_entry.insert(0, cfg.get("mc_simulations", "5000"))
        self._sims_entry.pack(side="right")

        # Quick preset buttons for simulations
        presets_f = ctk.CTkFrame(c2, fg_color="transparent")
        presets_f.pack(fill="x", padx=16, pady=(0, 8))
        for num, label in [(1000, "1k"), (2500, "2.5k"), (5000, "5k"), (10000, "10k")]:
            ctk.CTkButton(
                presets_f, text=label, width=42, height=22, font=FSM,
                fg_color="#141b2d", hover_color=C["hover"],
                border_width=1, border_color=C["border"],
                command=lambda n=num: self._set_sims(n)
            ).pack(side="left", expand=True, padx=2)

        # Deposit / Capital
        dep_f = ctk.CTkFrame(c2, fg_color="transparent")
        dep_f.pack(fill="x", padx=16, pady=(0, 8))
        make_label(dep_f, "Deposit / Capital ($):", font=FSM, color=C["sub"]).pack(side="left")
        self._dep_entry = make_entry(dep_f, width=100, height=28)
        self._dep_entry.insert(0, cfg.get("deposit", "2500"))
        self._dep_entry.pack(side="right")
        self._dep_entry.bind("<KeyRelease>", lambda e: self._update_calc_preview())

        # Block size
        block_f = ctk.CTkFrame(c2, fg_color="transparent")
        block_f.pack(fill="x", padx=16, pady=(0, 4))
        make_label(block_f, "Resample Block (Days):", font=FSM, color=C["sub"]).pack(side="left")
        self._block_entry = make_entry(block_f, width=100, height=28)
        self._block_entry.insert(0, cfg.get("mc_block_size", "10"))
        self._block_entry.pack(side="right")
        make_label(c2, "Preserves volatility clusters & streaks", font=ctk.CTkFont("Segoe UI", 9),
                   color="#64748b").pack(anchor="w", padx=16, pady=(0, 8))

        # Max Trading Days
        days_f = ctk.CTkFrame(c2, fg_color="transparent")
        days_f.pack(fill="x", padx=16, pady=(0, 6))
        make_label(days_f, "Max Trading Days:", font=FSM, color=C["sub"]).pack(side="left")
        self._maxdays_entry = make_entry(days_f, width=100, height=28)
        self._maxdays_entry.insert(0, cfg.get("mc_max_days", "250"))
        self._maxdays_entry.pack(side="right")

        # Unlimited horizon toggle switch
        self._no_max_days_var = ctk.BooleanVar(value=cfg.get("mc_no_max_days", "false").lower() == "true")
        self._no_max_switch = ctk.CTkSwitch(
            c2, text="Unlimited Trading Days (No Cap)",
            variable=self._no_max_days_var,
            font=FSM, text_color=C["sub"],
            progress_color=C["accent"], button_color="#ffffff",
            command=self._on_no_max_toggle
        )
        self._no_max_switch.pack(anchor="w", padx=16, pady=(4, 14))

        # ── Card 3: Prop Firm Gates ──────────────────────────────────────────
        c3 = make_card(grid_frame)
        c3.grid(row=0, column=2, sticky="nsew", padx=(8, 0), pady=0)
        c3.columnconfigure(0, weight=1)

        c3_hdr = ctk.CTkFrame(c3, fg_color="transparent")
        c3_hdr.pack(fill="x", padx=16, pady=(12, 6))
        make_label(c3_hdr, "🛡 Prop Firm Gate Limits", font=FH3, color=C["success"]).pack(side="left")
        make_label(c3_hdr, "Two-Phase", font=FSM, color=C["success"]).pack(side="right")

        # Phase 1 Target %
        p1_f = ctk.CTkFrame(c3, fg_color="transparent")
        p1_f.pack(fill="x", padx=16, pady=(4, 2))
        make_label(p1_f, "Phase 1 Target (%):", font=FSM, color=C["sub"]).pack(side="left")
        self._p1_entry = make_entry(p1_f, width=80, height=28)
        self._p1_entry.insert(0, cfg.get("mc_phase1_target", "8.0"))
        self._p1_entry.pack(side="right")
        self._p1_entry.bind("<KeyRelease>", lambda e: self._update_calc_preview())

        self._p1_dollar_lbl = make_label(c3, "+$200.00 profit required", font=ctk.CTkFont("Segoe UI", 9),
                                         color=C["success"])
        self._p1_dollar_lbl.pack(anchor="e", padx=16, pady=(0, 6))

        # Phase 2 Target %
        p2_f = ctk.CTkFrame(c3, fg_color="transparent")
        p2_f.pack(fill="x", padx=16, pady=(0, 2))
        make_label(p2_f, "Phase 2 Target (%):", font=FSM, color=C["sub"]).pack(side="left")
        self._p2_entry = make_entry(p2_f, width=80, height=28)
        self._p2_entry.insert(0, cfg.get("mc_phase2_target", "5.0"))
        self._p2_entry.pack(side="right")
        self._p2_entry.bind("<KeyRelease>", lambda e: self._update_calc_preview())

        self._p2_dollar_lbl = make_label(c3, "+$125.00 profit required", font=ctk.CTkFont("Segoe UI", 9),
                                         color=C["blue"])
        self._p2_dollar_lbl.pack(anchor="e", padx=16, pady=(0, 6))

        # Max Static DD %
        maxdd_f = ctk.CTkFrame(c3, fg_color="transparent")
        maxdd_f.pack(fill="x", padx=16, pady=(0, 2))
        make_label(maxdd_f, "Max Static DD (%):", font=FSM, color=C["sub"]).pack(side="left")
        self._maxdd_entry = make_entry(maxdd_f, width=80, height=28)
        self._maxdd_entry.insert(0, cfg.get("mc_max_dd", "10.0"))
        self._maxdd_entry.pack(side="right")
        self._maxdd_entry.bind("<KeyRelease>", lambda e: self._update_calc_preview())

        self._maxdd_dollar_lbl = make_label(c3, "-$250.00 drawdown ceiling", font=ctk.CTkFont("Segoe UI", 9),
                                            color=C["danger"])
        self._maxdd_dollar_lbl.pack(anchor="e", padx=16, pady=(0, 6))

        # Daily DD Limit %
        dailydd_f = ctk.CTkFrame(c3, fg_color="transparent")
        dailydd_f.pack(fill="x", padx=16, pady=(0, 2))
        make_label(dailydd_f, "Daily DD Limit (%):", font=FSM, color=C["sub"]).pack(side="left")
        self._dailydd_entry = make_entry(dailydd_f, width=80, height=28)
        self._dailydd_entry.insert(0, cfg.get("mc_daily_dd", "5.0"))
        self._dailydd_entry.pack(side="right")
        self._dailydd_entry.bind("<KeyRelease>", lambda e: self._update_calc_preview())

        self._dailydd_dollar_lbl = make_label(c3, "-$125.00 daily loss ceiling", font=ctk.CTkFont("Segoe UI", 9),
                                              color=C["danger"])
        self._dailydd_dollar_lbl.pack(anchor="e", padx=16, pady=(0, 10))

        # Initial preview calculation
        self._update_calc_preview()

        # ── Action Buttons Row ───────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=32, pady=(16, 0))

        make_btn(btn_row, "▶  Run Candidate Monte Carlo", self._run_candidate_mc,
                 width=220).pack(side="left")

        make_btn(btn_row, "🎲 Run Portfolio MC", self._run_portfolio_mc,
                 color=C["blue"], hover="#2563eb", width=180).pack(side="left", padx=(10, 0))

        make_btn(btn_row, "📄 Open Word Report", self._open_word_report,
                 color=C["card"], hover=C["hover"], width=170).pack(side="left", padx=(10, 0))

        make_btn(btn_row, "📂 Open Folder", self._open_cand_folder,
                 color=C["card"], hover=C["hover"], width=130).pack(side="left", padx=(10, 0))

        make_btn(btn_row, "💾 Save Defaults", self._save_settings,
                 color=C["card"], hover=C["hover"], width=130).pack(side="left", padx=(10, 0))

        make_btn(btn_row, "🗑 Clear Output", lambda: self.log_clear(self._log),
                 color=C["card"], hover=C["hover"], width=120).pack(side="left", padx=(10, 0))

        # ── Certification & Phase Metrics Dashboard Card ─────────────────────
        self._results_card = make_card(self)
        self._results_card.grid(row=3, column=0, sticky="ew", padx=32, pady=(16, 0))
        self._results_card.columnconfigure(0, weight=1)

        # Big Certification Status Banner
        self._cert_banner = ctk.CTkFrame(self._results_card, fg_color="#141b2d", corner_radius=8,
                                         border_width=1, border_color=C["border"])
        self._cert_banner.pack(fill="x", padx=16, pady=(14, 10))

        self._cert_title = make_label(
            self._cert_banner,
            "⚪ READY  —  Select a candidate and run Monte Carlo simulation",
            font=FH2, color=C["sub"]
        )
        self._cert_title.pack(anchor="center", pady=10)

        # Overview Stats Row
        self._stats_row = ctk.CTkFrame(self._results_card, fg_color="transparent")
        self._stats_row.pack(fill="x", padx=16, pady=(0, 10))
        self._stats_row.columnconfigure((0, 1, 2, 3), weight=1)

        self._stat_combined_pass = self._make_stat_box(self._stats_row, 0, "Combined Pass Rate", "— %", C["accent"])
        self._stat_worst_dd      = self._make_stat_box(self._stats_row, 1, "Worst Max DD Breach", "— %", C["danger"])
        self._stat_horizon       = self._make_stat_box(self._stats_row, 2, "Simulation Horizon", "250 Days", C["text"])
        self._stat_pnl_count     = self._make_stat_box(self._stats_row, 3, "Historical P&L Days", "—", C["sub"])

        # Phase 1 and Phase 2 Comparison Split
        phases_frame = ctk.CTkFrame(self._results_card, fg_color="transparent")
        phases_frame.pack(fill="x", padx=16, pady=(0, 14))
        phases_frame.columnconfigure((0, 1), weight=1)

        # Phase 1 Sub-card
        p1_box = ctk.CTkFrame(phases_frame, fg_color="#141b2d", corner_radius=8,
                              border_width=1, border_color=C["border"])
        p1_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
        p1_box.columnconfigure(0, weight=1)

        p1_title_f = ctk.CTkFrame(p1_box, fg_color="transparent")
        p1_title_f.pack(fill="x", padx=12, pady=(10, 6))
        make_label(p1_title_f, "Phase 1: Challenge Target", font=FH3, color=C["success"]).pack(side="left")
        self._p1_badge_lbl = make_label(p1_title_f, "Target: 8.0%", font=FSM, color=C["sub"])
        self._p1_badge_lbl.pack(side="right")

        self._p1_metrics_lbl = make_label(
            p1_box,
            "Pass Rate:             —%\n"
            "Passes / Runs:         — / —\n"
            "Max DD Breach:         —%\n"
            "Daily DD Breach:       —%\n"
            "Time Expired (>250d):  —%\n"
            "Median Days to Pass:   —\n"
            "Median Max DD:         —%",
            font=FMO, color=C["text"], justify="left"
        )
        self._p1_metrics_lbl.pack(anchor="w", padx=12, pady=(0, 10))

        # Phase 2 Sub-card
        p2_box = ctk.CTkFrame(phases_frame, fg_color="#141b2d", corner_radius=8,
                              border_width=1, border_color=C["border"])
        p2_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)
        p2_box.columnconfigure(0, weight=1)

        p2_title_f = ctk.CTkFrame(p2_box, fg_color="transparent")
        p2_title_f.pack(fill="x", padx=12, pady=(10, 6))
        make_label(p2_title_f, "Phase 2: Verification Target", font=FH3, color=C["blue"]).pack(side="left")
        self._p2_badge_lbl = make_label(p2_title_f, "Target: 5.0%", font=FSM, color=C["sub"])
        self._p2_badge_lbl.pack(side="right")

        self._p2_metrics_lbl = make_label(
            p2_box,
            "Pass Rate:             —%\n"
            "Passes / Runs:         — / —\n"
            "Max DD Breach:         —%\n"
            "Daily DD Breach:       —%\n"
            "Time Expired (>250d):  —%\n"
            "Median Days to Pass:   —\n"
            "Median Max DD:         —%",
            font=FMO, color=C["text"], justify="left"
        )
        self._p2_metrics_lbl.pack(anchor="w", padx=12, pady=(0, 10))

        # ── Output Log ───────────────────────────────────────────────────────
        log_card = make_card(self)
        log_card.grid(row=4, column=0, sticky="nsew", padx=32, pady=(16, 24))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        log_hdr = ctk.CTkFrame(log_card, fg_color="transparent")
        log_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 4))
        make_label(log_hdr, "Live Monte Carlo Simulation Output", font=FH3, color=C["sub"]).pack(side="left")

        self._log = make_log(log_card, height=220)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 14))

        # Populate initial list of candidates
        self._refresh_candidates_list()

    def _make_stat_box(self, parent, col, title, value, color):
        f = ctk.CTkFrame(parent, fg_color="#141b2d", corner_radius=8,
                         border_width=1, border_color=C["border"])
        f.grid(row=0, column=col, sticky="nsew", padx=4, pady=0)
        make_label(f, title, font=ctk.CTkFont("Segoe UI", 10), color=C["sub"]).pack(anchor="w", padx=10, pady=(6, 0))
        val_lbl = make_label(f, value, font=ctk.CTkFont("Segoe UI", 14, "bold"), color=color)
        val_lbl.pack(anchor="w", padx=10, pady=(2, 6))
        return val_lbl

    def _set_sims(self, n: int):
        self._sims_entry.delete(0, "end")
        self._sims_entry.insert(0, str(n))

    def _update_calc_preview(self):
        try:
            dep = float(self._dep_entry.get().strip())
        except Exception:
            dep = 2500.0

        try:
            p1 = float(self._p1_entry.get().strip())
            self._p1_dollar_lbl.configure(text=f"+${(dep * p1 / 100.0):,.2f} profit required")
        except Exception:
            pass

        try:
            p2 = float(self._p2_entry.get().strip())
            self._p2_dollar_lbl.configure(text=f"+${(dep * p2 / 100.0):,.2f} profit required")
        except Exception:
            pass

        try:
            maxdd = float(self._maxdd_entry.get().strip())
            self._maxdd_dollar_lbl.configure(text=f"-${(dep * maxdd / 100.0):,.2f} drawdown ceiling")
        except Exception:
            pass

        try:
            dailydd = float(self._dailydd_entry.get().strip())
            self._dailydd_dollar_lbl.configure(text=f"-${(dep * dailydd / 100.0):,.2f} daily loss ceiling")
        except Exception:
            pass

    def _on_no_max_toggle(self):
        is_unlimited = self._no_max_days_var.get()
        if is_unlimited:
            self._maxdays_entry.configure(state="disabled")
            self._stat_horizon.configure(text="Unlimited")
        else:
            self._maxdays_entry.configure(state="normal")
            self._stat_horizon.configure(text=f"{self._maxdays_entry.get().strip()} Days")

    def _get_target_candidate(self) -> str:
        custom = self._custom_cand.get().strip() if hasattr(self, "_custom_cand") else ""
        if custom:
            return custom
        cb_val = self._cand_var.get().strip() if hasattr(self, "_cand_var") else ""
        if not cb_val or cb_val in ("(none found)", "(scanning...)", "(none)"):
            return ""
        parts = cb_val.split()
        return parts[0] if parts else ""

    def _refresh_candidates_list(self):
        cfg = self.cfg
        run_choice = self._run_var.get().strip() if hasattr(self, "_run_var") else ""
        self._all_cands_info = get_all_candidates_summary(cfg.get("work_dir", ""), run_choice)

        formatted_choices = []
        for c in self._all_cands_info:
            cid = c["id"]
            if c.get("is_certified") is True:
                pr = c.get("pass_rate")
                tag = f" [CERTIFIED {pr:.1f}%]" if pr is not None else " [CERTIFIED]"
            elif c.get("is_certified") is False:
                tag = " [NOT CERTIFIED]"
            elif c.get("has_trades"):
                tag = " [Ready]"
            else:
                tag = ""
            formatted_choices.append(f"{cid}{tag}")

        self._cand_cb.configure(values=formatted_choices or ["(none found)"])
        if formatted_choices:
            curr = self._cand_var.get().strip() if hasattr(self, "_cand_var") else ""
            curr_parts = curr.split() if curr else []
            curr_id = curr_parts[0] if curr_parts else ""
            match = next((ch for ch in formatted_choices if (ch.split()[0] if ch.split() else "") == curr_id), None) if curr_id else None
            if match:
                self._cand_var.set(match)
            else:
                self._cand_var.set(formatted_choices[0])
        else:
            self._cand_var.set("(none found)")

        self._update_cand_details()
        self._load_active_result()

    def _on_run_changed(self, run_val):
        self._refresh_candidates_list()

    def _on_cand_changed(self, cand_val):
        self._update_cand_details()
        self._load_active_result()

    def _on_custom_cand_changed(self):
        self._update_cand_details()
        self._load_active_result()

    def _update_cand_details(self):
        target = self._get_target_candidate()
        if not target:
            self._cand_status_lbl.configure(text="Status: No candidate selected", text_color=C["sub"])
            self._cand_dir_lbl.configure(text="Path: —", text_color="#64748b")
            self._cand_trades_lbl.configure(text="Trades: —", text_color="#64748b")
            return

        cand_info = next((c for c in self._all_cands_info if c["id"] == target), None)
        target_path = find_candidate_path(self.cfg.get("work_dir", ""), target, self._run_var.get().strip())

        if cand_info and cand_info.get("is_certified") is True:
            self._cand_status_lbl.configure(text="Status: ✔ CERTIFIED", text_color=C["success"])
        elif cand_info and cand_info.get("is_certified") is False:
            self._cand_status_lbl.configure(text="Status: ✘ NOT CERTIFIED", text_color=C["danger"])
        else:
            self._cand_status_lbl.configure(text="Status: Ready for Monte Carlo", text_color=C["sub"])

        if target_path and target_path.exists():
            rel = str(target_path)
            if len(rel) > 42:
                rel = "..." + rel[-39:]
            self._cand_dir_lbl.configure(text=f"Path: {rel}", text_color="#94a3b8")
            has_trades = cand_info.get("has_trades") if cand_info else (target_path / "trades.csv").exists()
            self._cand_trades_lbl.configure(
                text="Trades: ✓ trades.csv detected" if has_trades else "Trades: ~ Report calibration available",
                text_color=C["success"] if has_trades else C["accent"]
            )
        else:
            self._cand_dir_lbl.configure(text="Path: Auto-scan workspace", text_color="#64748b")
            self._cand_trades_lbl.configure(text="Trades: Searching upon launch...", text_color="#64748b")

    def _load_active_result(self):
        target = self._get_target_candidate()
        if not target:
            self._reset_results_display()
            return

        target_path = find_candidate_path(self.cfg.get("work_dir", ""), target, self._run_var.get().strip())
        res_file = None
        if target_path and (target_path / "monte_carlo_results.json").exists():
            res_file = target_path / "monte_carlo_results.json"
        elif (SCRIPT_DIR / "last_mc_candidate_result.json").exists():
            try:
                with open(SCRIPT_DIR / "last_mc_candidate_result.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("candidate") == target:
                        res_file = SCRIPT_DIR / "last_mc_candidate_result.json"
            except Exception:
                pass

        if not res_file or not res_file.exists():
            self._reset_results_display()
            return

        try:
            with open(res_file, "r", encoding="utf-8") as f:
                d = json.load(f)

            is_cert = d.get("is_certified", False)
            comb_pass = d.get("combined_pass_rate", 0.0)
            worst_dd  = d.get("worst_breach_max_dd", 0.0)
            p1 = d.get("phase1", {})
            p2 = d.get("phase2", {})

            if is_cert:
                self._cert_banner.configure(fg_color="#064e3b", border_color="#10b981")
                self._cert_title.configure(
                    text=f"✔ CERTIFIED  —  Meets all Prop Firm Monte Carlo survival gates! ({comb_pass:.1f}%)",
                    text_color="#34d399"
                )
            else:
                self._cert_banner.configure(fg_color="#450a0a", border_color="#ef4444")
                self._cert_title.configure(
                    text=f"✘ NOT CERTIFIED  —  Did not satisfy survival threshold ({comb_pass:.1f}% pass, {worst_dd:.1f}% DD breach)",
                    text_color="#f87171"
                )

            self._stat_combined_pass.configure(
                text=f"{comb_pass:.1f}%",
                text_color=C["success"] if comb_pass >= 80 else (C["accent"] if comb_pass >= 60 else C["danger"])
            )
            self._stat_worst_dd.configure(
                text=f"{worst_dd:.1f}%",
                text_color=C["danger"] if worst_dd > 10 else C["success"]
            )

            no_max = d.get("no_max_days", False)
            max_d = d.get("max_days")
            horizon_text = "Unlimited" if no_max else (f"{max_d} Days" if max_d else "250 Days")
            self._stat_horizon.configure(text=horizon_text)
            self._stat_pnl_count.configure(text=f"{d.get('historical_pnl_count', '—')} days")

            # Phase 1 text
            p1_tgt = p1.get("target_pct", 8.0)
            self._p1_badge_lbl.configure(text=f"Target: {p1_tgt:.1f}%")
            self._p1_metrics_lbl.configure(
                text=(
                    f"Pass Rate:             {p1.get('pass_rate', 0.0):.1f}%\n"
                    f"Passes / Runs:         {p1.get('pass_count', 0):,} / {d.get('simulations', 5000):,}\n"
                    f"Max DD Breach:         {p1.get('breach_max_rate', 0.0):.1f}%\n"
                    f"Daily DD Breach:       {p1.get('breach_daily_rate', 0.0):.1f}%\n"
                    f"Time Expired (>250d):  {p1.get('incomplete_rate', 0.0):.1f}%\n"
                    f"Median Days to Pass:   {p1.get('median_days', 0):.0f}d  (P10: {p1.get('p10_days', 0):.0f}d / P90: {p1.get('p90_days', 0):.0f}d)\n"
                    f"Median Max DD:         {p1.get('median_max_dd', 0.0):.2f}%  (P90: {p1.get('p90_max_dd', 0.0):.2f}% / P99: {p1.get('p99_max_dd', 0.0):.2f}%)"
                )
            )

            # Phase 2 text
            p2_tgt = p2.get("target_pct", 5.0)
            self._p2_badge_lbl.configure(text=f"Target: {p2_tgt:.1f}%")
            self._p2_metrics_lbl.configure(
                text=(
                    f"Pass Rate:             {p2.get('pass_rate', 0.0):.1f}%\n"
                    f"Passes / Runs:         {p2.get('pass_count', 0):,} / {d.get('simulations', 5000):,}\n"
                    f"Max DD Breach:         {p2.get('breach_max_rate', 0.0):.1f}%\n"
                    f"Daily DD Breach:       {p2.get('breach_daily_rate', 0.0):.1f}%\n"
                    f"Time Expired (>250d):  {p2.get('incomplete_rate', 0.0):.1f}%\n"
                    f"Median Days to Pass:   {p2.get('median_days', 0):.0f}d  (P10: {p2.get('p10_days', 0):.0f}d / P90: {p2.get('p90_days', 0):.0f}d)\n"
                    f"Median Max DD:         {p2.get('median_max_dd', 0.0):.2f}%  (P90: {p2.get('p90_max_dd', 0.0):.2f}% / P99: {p2.get('p99_max_dd', 0.0):.2f}%)"
                )
            )

        except Exception as e:
            print(f"Error loading MC result: {e}")
            self._reset_results_display()

    def _reset_results_display(self):
        self._cert_banner.configure(fg_color="#141b2d", border_color=C["border"])
        self._cert_title.configure(
            text="⚪ READY  —  Select a candidate and run Monte Carlo simulation",
            text_color=C["sub"]
        )
        self._stat_combined_pass.configure(text="— %", text_color=C["accent"])
        self._stat_worst_dd.configure(text="— %", text_color=C["danger"])
        self._stat_horizon.configure(text="250 Days" if not self._no_max_days_var.get() else "Unlimited")
        self._stat_pnl_count.configure(text="—")
        self._p1_metrics_lbl.configure(
            text="Pass Rate:             —%\nPasses / Runs:         — / —\nMax DD Breach:         —%\nDaily DD Breach:       —%\nTime Expired (>250d):  —%\nMedian Days to Pass:   —\nMedian Max DD:         —%"
        )
        self._p2_metrics_lbl.configure(
            text="Pass Rate:             —%\nPasses / Runs:         — / —\nMax DD Breach:         —%\nDaily DD Breach:       —%\nTime Expired (>250d):  —%\nMedian Days to Pass:   —\nMedian Max DD:         —%"
        )

    def _run_candidate_mc(self):
        cand = self._get_target_candidate()
        if not cand:
            messagebox.showwarning("Missing", "Please select or enter a candidate name.")
            return

        run_dir = self._run_var.get().strip()
        if run_dir in ("(Auto-detect across workspace)", "latest", ""):
            run_dir = ""

        try:
            sims = int(self._sims_entry.get().strip())
        except ValueError:
            sims = 5000
        try:
            deposit = float(self._dep_entry.get().strip())
        except ValueError:
            deposit = 2500.0
        try:
            block = int(self._block_entry.get().strip())
        except ValueError:
            block = 10
        try:
            p1 = float(self._p1_entry.get().strip())
        except ValueError:
            p1 = 8.0
        try:
            p2 = float(self._p2_entry.get().strip())
        except ValueError:
            p2 = 5.0
        try:
            max_dd = float(self._maxdd_entry.get().strip())
        except ValueError:
            max_dd = 10.0
        try:
            daily_dd = float(self._dailydd_entry.get().strip())
        except ValueError:
            daily_dd = 5.0
        try:
            max_days = int(self._maxdays_entry.get().strip())
        except ValueError:
            max_days = 250

        no_max = bool(self._no_max_days_var.get())

        args = [cand, "--sims", str(sims), "--p1", str(p1), "--p2", str(p2),
                "--max-dd", str(max_dd), "--daily-dd", str(daily_dd),
                "--block-size", str(block), "--deposit", str(deposit)]

        if run_dir:
            args.extend(["--run-dir", run_dir])
        if no_max:
            args.append("--no-max-days")
        else:
            args.extend(["--max-days", str(max_days)])

        self.log_clear(self._log)
        self.log_append(self._log, f"▶ Launching Candidate Monte Carlo: {cand}  (sims={sims}, block={block}d, p1={p1}%, p2={p2}%)\n")
        self.run_script("run_can_monte_carlo.py", self._log, args=args, on_done=self._on_sim_done)

    def _on_sim_done(self):
        self._refresh_candidates_list()
        self._load_active_result()

    def _run_portfolio_mc(self):
        portfolios = get_portfolios(self.cfg.get("work_dir", ""), self.cfg.get("quant_name", "TRB"))
        if not portfolios:
            messagebox.showinfo("Portfolio", "No built portfolio found under optimization_runs.\nBuild a portfolio first in the Portfolio tab.")
            return
        port = portfolios[0]
        port_path = find_portfolio_path(self.cfg.get("work_dir", ""), self.cfg.get("quant_name", "TRB"), port)
        patches = {
            "PORTFOLIO_NAME": port,
            "QUANT_NAME": self.cfg.get("quant_name", "TRB"),
        }
        if port_path and port_path.exists():
            patches["PORTFOLIO_DIR"] = str(port_path)
        patch_script(SCRIPT_DIR / "run_portfolio_montecarlo.py", patches)
        self.log_clear(self._log)
        self.log_append(self._log, f"▶ Launching Portfolio Monte Carlo on {port}...\n")
        self.run_script("run_portfolio_montecarlo.py", self._log)

    def _open_word_report(self):
        target = self._get_target_candidate()
        target_path = find_candidate_path(self.cfg.get("work_dir", ""), target, self._run_var.get().strip()) if target else None

        doc_found = None
        if target_path and target_path.exists():
            docs = list(target_path.glob("*.docx"))
            if docs:
                doc_found = docs[0]

        if not doc_found and target_path:
            j = target_path / "monte_carlo_results.json"
            if j.exists():
                try:
                    with open(j, "r", encoding="utf-8") as jf:
                        jd = json.load(jf)
                        dp = jd.get("doc_path")
                        if dp and Path(dp).exists():
                            doc_found = Path(dp)
                except Exception:
                    pass

        if not doc_found:
            root_mc = SCRIPT_DIR / "last_mc_candidate_result.json"
            if root_mc.exists():
                try:
                    with open(root_mc, "r", encoding="utf-8") as jf:
                        jd = json.load(jf)
                        dp = jd.get("doc_path")
                        if dp and Path(dp).exists():
                            doc_found = Path(dp)
                except Exception:
                    pass

        if doc_found and doc_found.exists():
            open_in_file_manager(doc_found)
        else:
            messagebox.showinfo("Report Not Found", "No Word report (.docx) found for this candidate.\nRun a Monte Carlo simulation first.")

    def _open_cand_folder(self):
        target = self._get_target_candidate()
        target_path = find_candidate_path(self.cfg.get("work_dir", ""), target, self._run_var.get().strip()) if target else None
        if target_path and target_path.exists():
            open_in_file_manager(target_path)
        else:
            wdir = _resolve_work_dir(self.cfg.get("work_dir", ""))
            open_in_file_manager(wdir)

    def _save_settings(self):
        cfg = self.cfg
        try:
            cfg["mc_simulations"]   = self._sims_entry.get().strip()
            cfg["deposit"]          = self._dep_entry.get().strip()
            cfg["mc_block_size"]    = self._block_entry.get().strip()
            cfg["mc_max_days"]      = self._maxdays_entry.get().strip()
            cfg["mc_no_max_days"]   = "true" if self._no_max_days_var.get() else "false"
            cfg["mc_phase1_target"] = self._p1_entry.get().strip()
            cfg["mc_phase2_target"] = self._p2_entry.get().strip()
            cfg["mc_max_dd"]        = self._maxdd_entry.get().strip()
            cfg["mc_daily_dd"]      = self._dailydd_entry.get().strip()
            save_config(cfg)
            messagebox.showinfo("Saved", "Monte Carlo settings saved to config.json.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def refresh(self):
        self._refresh_candidates_list()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Walk Forward Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WalkForwardPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))
        make_section_header(self, "📈  Walk Forward Stability Testing",
            "Test a candidate across rolling time windows — run one at a time"
        ).grid(row=0, column=0, sticky="ew", **pad)

        # Selector card
        sel = make_card(self)
        sel.grid(row=1, column=0, sticky="ew", padx=32, pady=(24, 0))

        cfg = self.cfg

        # Run dir
        r1 = ctk.CTkFrame(sel, fg_color="transparent")
        r1.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        make_label(r1, "Run Directory", font=FB, color=C["sub"], width=150, anchor="e").pack(side="left", padx=(0,12))
        run_dirs = ["latest"] + get_run_dirs(cfg.get("work_dir",""))
        self._run_var = ctk.StringVar(value=run_dirs[1] if len(run_dirs)>1 else "latest")
        self._run_cb  = ctk.CTkComboBox(sel, values=run_dirs, variable=self._run_var,
                                         width=320, font=FB, fg_color=C["inp"],
                                         border_color=C["border"], button_color=C["accent"],
                                         command=self._refresh_cands)
        self._run_cb.grid(row=0, column=0, padx=20, pady=(16,6), sticky="w", columnspan=2)

        # Candidate
        r2 = ctk.CTkFrame(sel, fg_color="transparent")
        r2.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        make_label(r2, "Candidate", font=FB, color=C["sub"], width=150, anchor="e").pack(side="left", padx=(0,12))
        self._cand_var = ctk.StringVar()
        self._cand_cb  = ctk.CTkComboBox(sel, values=[], variable=self._cand_var,
                                          width=320, font=FB, fg_color=C["inp"],
                                          border_color=C["border"], button_color=C["accent"])
        self._cand_cb.grid(row=1, column=0, padx=20, pady=6, sticky="w")
        self._refresh_cands(self._run_var.get())

        # WF params
        r3 = ctk.CTkFrame(sel, fg_color="transparent")
        r3.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        make_label(r3, "Window / Step (months)", font=FB, color=C["sub"], width=180, anchor="e").pack(side="left", padx=(0,12))
        self._wf_window = make_entry(r3, width=80)
        self._wf_window.insert(0, cfg.get("wf_window_months","12"))
        self._wf_window.pack(side="left")
        make_label(r3, "/", color=C["sub"]).pack(side="left", padx=6)
        self._wf_step   = make_entry(r3, width=80)
        self._wf_step.insert(0, cfg.get("wf_step_months","6"))
        self._wf_step.pack(side="left")

        # Buttons
        btn_row = ctk.CTkFrame(sel, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(16, 16))
        make_btn(btn_row, "▶  Run WF Testing", self._run, width=200).pack(side="left")
        make_btn(btn_row, "📂 Open Candidate Folder",
                 self._open_cand, color=C["card"], hover=C["hover"], width=190).pack(side="left", padx=(12,0))
        make_btn(btn_row, "⟳ Refresh Lists",
                 lambda: self._refresh_cands(self._run_var.get()),
                 color=C["card"], hover=C["hover"], width=140).pack(side="left", padx=(12,0))

        # Log
        log_card = make_card(self)
        log_card.grid(row=2, column=0, sticky="nsew", padx=32, pady=(20, 28))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        make_label(log_card, "WF Testing Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12,4))
        self._log = make_log(log_card, height=280)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0,16))

    def _refresh_cands(self, run_dir_val):
        cfg    = self.cfg
        wdir   = cfg.get("work_dir","")
        cands  = get_candidates(wdir, run_dir_val) if run_dir_val != "latest" else []
        if not cands and run_dir_val == "latest":
            runs = get_run_dirs(wdir)
            if runs:
                cands = get_candidates(wdir, runs[0])
        self._cand_cb.configure(values=cands or ["(none found)"])
        if cands:
            self._cand_var.set(cands[0])

    def _get_target_dir(self):
        cfg    = self.cfg
        wdir   = cfg.get("work_dir","")
        run    = self._run_var.get()
        cand   = self._cand_var.get()
        if not run or not cand:
            return None
        run_path = find_run_path(wdir, run)
        if not run_path:
            return None
        # Try passed_candidates first
        pc = run_path / "passed_candidates" / cand
        if pc.exists():
            return pc
        return run_path / cand

    def _run(self):
        run  = self._run_var.get()
        cand = self._cand_var.get()
        if not run or not cand or cand == "(none found)":
            messagebox.showwarning("Missing", "Select a run and candidate.")
            return
        # Patch run_wf_pipeline.py with target values
        script = SCRIPT_DIR / "run_wf_pipeline.py"
        patch_script(script, {
            "TARGET_RUN_DIR":  run,
            "TARGET_CANDIDATE": cand,
        })
        self.log_clear(self._log)
        self.log_append(self._log, f"  Candidate: {cand}  |  Run: {run}\n")
        self.run_script("run_wf_pipeline.py", self._log)

    def _open_cand(self):
        d = self._get_target_dir()
        if d and d.exists():
            os.startfile(str(d))
        else:
            messagebox.showinfo("Not found", "Candidate folder not found.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Full Backtest Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FullBacktestPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))
        make_section_header(self, "📋  Full Backtest",
            "Run a full-period backtest with advanced charts & Word report for a candidate"
        ).grid(row=0, column=0, sticky="ew", **pad)

        cfg = self.cfg
        sel = make_card(self)
        sel.grid(row=1, column=0, sticky="ew", padx=32, pady=(24, 0))

        # Run dir
        run_dirs = get_run_dirs(cfg.get("work_dir",""))
        self._run_var = ctk.StringVar(value=run_dirs[0] if run_dirs else "")
        make_label(sel, "Run Directory", font=FB, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=(20,8), pady=(16,6))
        self._run_cb = ctk.CTkComboBox(sel, values=run_dirs or ["(none)"], variable=self._run_var,
                                        width=340, font=FB, fg_color=C["inp"],
                                        border_color=C["border"], button_color=C["accent"],
                                        command=self._refresh_cands)
        self._run_cb.grid(row=0, column=1, padx=(0,20), pady=(16,6), sticky="w")

        # Candidate
        make_label(sel, "Candidate", font=FB, color=C["sub"]).grid(
            row=1, column=0, sticky="w", padx=(20,8), pady=6)
        self._cand_var = ctk.StringVar()
        self._cand_cb  = ctk.CTkComboBox(sel, values=[], variable=self._cand_var,
                                          width=340, font=FB, fg_color=C["inp"],
                                          border_color=C["border"], button_color=C["accent"])
        self._cand_cb.grid(row=1, column=1, padx=(0,20), pady=6, sticky="w")
        self._refresh_cands(self._run_var.get())

        # Market / Symbol
        MARKETS = ["USDJPY", "EURJPY", "EURUSD", "GBPUSD", "XAUUSD"]
        default_sym = cfg.get("symbol", "USDJPY").upper()
        if default_sym not in MARKETS:
            default_sym = "USDJPY"
        self._market_var = ctk.StringVar(value=default_sym)
        make_label(sel, "Market / Symbol", font=FB, color=C["sub"]).grid(
            row=2, column=0, sticky="w", padx=(20,8), pady=6)
        self._market_cb = ctk.CTkComboBox(sel, values=MARKETS, variable=self._market_var,
                                          width=340, font=FB, fg_color=C["inp"],
                                          border_color=C["border"], button_color=C["accent"])
        self._market_cb.grid(row=2, column=1, padx=(0,20), pady=6, sticky="w")

        # Overrides
        ovr = ctk.CTkFrame(sel, fg_color="transparent")
        ovr.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(6, 6))
        make_label(ovr, "From Date", font=FB, color=C["sub"]).pack(side="left", padx=(0,8))
        self._from_var = make_entry(ovr, width=100)
        self._from_var.insert(0, cfg.get("train_from", ""))
        self._from_var.pack(side="left", padx=(0,16))
        
        make_label(ovr, "To Date", font=FB, color=C["sub"]).pack(side="left", padx=(0,8))
        self._to_var = make_entry(ovr, width=100)
        self._to_var.insert(0, cfg.get("holdout_to", ""))
        self._to_var.pack(side="left", padx=(0,16))
        
        make_label(ovr, "Deposit", font=FB, color=C["sub"]).pack(side="left", padx=(0,8))
        self._dep_var = make_entry(ovr, width=70)
        self._dep_var.insert(0, cfg.get("deposit", "2500"))
        self._dep_var.pack(side="left", padx=(0,16))

        make_label(ovr, "Lot Size", font=FB, color=C["sub"]).pack(side="left", padx=(0,8))
        self._lot_var = make_entry(ovr, width=60)
        self._lot_var.insert(0, cfg.get("lot_size", ""))
        self._lot_var.pack(side="left", padx=(0,16))

        make_label(ovr, "Risk %", font=FB, color=C["sub"]).pack(side="left", padx=(0,8))
        self._risk_var = make_entry(ovr, width=60)
        self._risk_var.insert(0, cfg.get("risk_pct", ""))
        self._risk_var.pack(side="left")

        # Buttons
        btn_row = ctk.CTkFrame(sel, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=2, sticky="ew", padx=20, pady=(16,16))
        make_btn(btn_row, "▶  Run Full Backtest", self._run, width=200).pack(side="left")
        make_btn(btn_row, "📂 Open Output",
                 self._open_out, color=C["card"], hover=C["hover"], width=150).pack(side="left", padx=(12,0))
        make_btn(btn_row, "⟳ Refresh",
                 lambda: self._refresh_cands(self._run_var.get()),
                 color=C["card"], hover=C["hover"], width=110).pack(side="left", padx=(12,0))

        # Log
        log_card = make_card(self)
        log_card.grid(row=2, column=0, sticky="nsew", padx=32, pady=(20, 28))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        make_label(log_card, "Full Backtest Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12,4))
        self._log = make_log(log_card, height=280)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0,16))

    def _refresh_cands(self, run_dir_val):
        cfg   = self.cfg
        cands = get_candidates(cfg.get("work_dir",""), run_dir_val)
        self._cand_cb.configure(values=cands or ["(none found)"])
        if cands:
            self._cand_var.set(cands[0])

    def _run(self):
        run    = self._run_var.get()
        cand   = self._cand_var.get()
        market = self._market_var.get().strip() or "USDJPY"
        if not run or not cand or cand == "(none found)":
            messagebox.showwarning("Missing", "Select a run and candidate.")
            return
        patch_script(SCRIPT_DIR / "run_full_backtest.py", {
            "TARGET_RUN_DIR": run,
            "TARGET_CANDIDATE": cand,
            "TARGET_SYMBOL": market,
        })
        env_extra = {
            "AF_SYMBOL":   market,
            "AF_BT_START": self._from_var.get().strip() or self.cfg.get("train_from", ""),
            "AF_BT_END":   self._to_var.get().strip() or self.cfg.get("holdout_to", ""),
            "AF_DEPOSIT":  self._dep_var.get().strip() or self.cfg.get("deposit", "2500"),
            "AF_LOT_SIZE": self._lot_var.get().strip(),
            "AF_RISK_PCT": self._risk_var.get().strip(),
        }
        self.log_clear(self._log)
        self.run_script("run_full_backtest.py", self._log, env_extra=env_extra)

    def _open_out(self):
        cfg  = self.cfg
        run  = self._run_var.get()
        cand = self._cand_var.get()
        if run and cand:
            run_path = find_run_path(cfg.get("work_dir",""), run)
            if run_path:
                d = run_path / "passed_candidates" / cand / "full_backtest"
                if not d.exists():
                    d = run_path / cand / "full_backtest_report"
                if not d.exists():
                    d = run_path / cand
                if d.exists():
                    os.startfile(str(d))
                    return
        messagebox.showinfo("Not found", "Output folder not found.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Portfolio Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PortfolioPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._candidate_rows = []
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))
        make_section_header(self, "📦  Portfolio Builder",
            "Merge multiple candidates into a quant portfolio, then run Monte Carlo"
        ).grid(row=0, column=0, sticky="ew", **pad)

        cfg = self.cfg

        # Portfolio meta
        meta = make_card(self)
        meta.grid(row=1, column=0, sticky="ew", padx=32, pady=(20, 0))
        r0 = ctk.CTkFrame(meta, fg_color="transparent")
        r0.grid(row=0, column=0, sticky="ew", padx=20, pady=(14,4))
        make_label(r0, "Portfolio Name", font=FB, color=C["sub"], width=160, anchor="e").pack(side="left", padx=(0,12))
        self._port_name = make_entry(r0, width=320)
        self._port_name.insert(0, f"{cfg.get('quant_name','TRB')}_Quant_Portfolio_001")
        self._port_name.pack(side="left")

        # Output Storage Folder
        r_out = ctk.CTkFrame(meta, fg_color="transparent")
        r_out.grid(row=1, column=0, sticky="ew", padx=20, pady=(4,6))
        make_label(r_out, "Output Folder", font=FB, color=C["sub"], width=160, anchor="e").pack(side="left", padx=(0,12))
        self._out_dir_var = ctk.StringVar(value="Multi_Market_Quant_Portfolio")
        self._out_dir_cb = ctk.CTkComboBox(r_out, 
                                           values=["Multi_Market_Quant_Portfolio", "Quant_Portfolios", "MultiMarket portfolio"],
                                           variable=self._out_dir_var, width=320, font=FB,
                                           fg_color=C["inp"], border_color=C["border"], button_color=C["accent"])
        self._out_dir_cb.pack(side="left")

        make_label(meta, "Candidates   (run_dir | candidate | weight)",
                   font=FH3, color=C["accent"]).grid(row=2, column=0, sticky="w", padx=20, pady=(12,4))

        # Scrollable candidate list
        self._cand_scroll = ctk.CTkScrollableFrame(meta, height=200, fg_color=C["inp"],
                                                    corner_radius=8)
        self._cand_scroll.grid(row=3, column=0, sticky="ew", padx=16, pady=(0,8))
        self._cand_scroll.columnconfigure((0,1,2), weight=1)
        self._add_candidate_row()  # Start with one empty row

        btn_add = make_btn(meta, "+ Add Candidate", self._add_candidate_row,
                           color=C["card"], hover=C["hover"], width=160)
        btn_add.grid(row=4, column=0, sticky="w", padx=20, pady=(0,14))

        # Action buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=32, pady=(16, 0))
        make_btn(btn_row, "🏗  Build Portfolio", self._build_portfolio, width=200).pack(side="left")
        make_btn(btn_row, "🎲 Run Portfolio MC",
                 self._run_mc, color=C["blue"], hover="#2563eb", width=190).pack(side="left", padx=(12,0))
        make_btn(btn_row, "📂 Open Portfolio Folder",
                 self._open_portfolio, color=C["card"], hover=C["hover"], width=190).pack(side="left", padx=(12,0))

        # MC portfolio selector
        mc_row = ctk.CTkFrame(self, fg_color="transparent")
        mc_row.grid(row=3, column=0, sticky="ew", padx=32, pady=(12, 0))
        make_label(mc_row, "Run MC on Portfolio:", font=FB, color=C["sub"]).pack(side="left", padx=(0,12))
        portfolios = get_portfolios(cfg.get("work_dir",""), cfg.get("quant_name","TRB"))
        self._mc_port_var = ctk.StringVar(value=portfolios[0] if portfolios else "")
        self._mc_port_cb  = ctk.CTkComboBox(mc_row, values=portfolios or ["(none)"],
                                             variable=self._mc_port_var, width=320,
                                             font=FB, fg_color=C["inp"], border_color=C["border"],
                                             button_color=C["accent"],
                                             command=self._on_port_selected)
        self._mc_port_cb.pack(side="left")
        make_btn(mc_row, "⟳", lambda: self._refresh_portfolios(),
                 color=C["card"], hover=C["hover"], width=40).pack(side="left", padx=(8,0))
        self._port_info_lbl = make_label(mc_row, "", font=FSM, color=C["accent"])
        self._port_info_lbl.pack(side="left", padx=(16, 0))
        self._update_port_info()

        # Log
        log_card = make_card(self)
        log_card.grid(row=4, column=0, sticky="nsew", padx=32, pady=(20, 28))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        make_label(log_card, "Portfolio Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12,4))
        self._log = make_log(log_card, height=240)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0,16))

    def _add_candidate_row(self):
        n   = len(self._candidate_rows)
        cfg = self.cfg
        runs  = get_run_dirs(cfg.get("work_dir",""))
        row_f = ctk.CTkFrame(self._cand_scroll, fg_color="transparent")
        row_f.grid(row=n, column=0, sticky="ew", padx=4, pady=4)

        run_e  = make_entry(row_f, "run_20260909_101955", width=210)
        run_e.pack(side="left", padx=(0,6))
        cand_e = make_entry(row_f, "cand_001", width=110)
        cand_e.pack(side="left", padx=(0,6))
        wgt_e  = make_entry(row_f, "1.0", width=60)
        wgt_e.pack(side="left", padx=(0,6))
        del_btn = ctk.CTkButton(row_f, text="✕", width=32, height=28,
                                fg_color="#2d2d2d", hover_color=C["danger"],
                                font=FB, corner_radius=6,
                                command=lambda rf=row_f, recs=(run_e, cand_e, wgt_e): self._del_row(rf, recs))
        del_btn.pack(side="left")
        self._candidate_rows.append((row_f, run_e, cand_e, wgt_e))

    def _del_row(self, row_frame, record):
        row_frame.destroy()
        self._candidate_rows = [(rf, r, c, w) for rf, r, c, w in self._candidate_rows
                                if rf != row_frame]

    def _get_candidates_list(self):
        cands = []
        for _, run_e, cand_e, wgt_e in self._candidate_rows:
            r = run_e.get().strip()
            c = cand_e.get().strip()
            w = wgt_e.get().strip() or "1.0"
            if r and c:
                item = {"run_dir": r, "candidate": c, "weight": float(w)}
                combined_str = f"{r} {c}".lower()
                for mkt in ("eurjpy", "usdjpy", "gbpjpy", "audusd", "eurusd", "xauusd", "btcusd"):
                    if mkt in combined_str:
                        item["market"] = mkt.upper()
                        break
                cands.append(item)
        return cands

    def _build_portfolio(self):
        cands     = self._get_candidates_list()
        port_name = self._port_name.get().strip()
        out_dir   = self._out_dir_var.get().strip() or "Multi_Market_Quant_Portfolio"
        if not cands:
            messagebox.showwarning("Empty", "Add at least one candidate.")
            return
        if not port_name:
            messagebox.showwarning("Missing", "Enter a portfolio name.")
            return

        # Sanitize portfolio name to prevent nested subdirectories like TRB_USDJPY/ or TRB_EURJPY/
        port_name = re.sub(r"[/\\:]+", "_", port_name).strip("_")

        is_multi_market = (
            "multimarket" in port_name.lower()
            or len(set(c.get("market") for c in cands if c.get("market"))) > 1
            or any("usdjpy" in f"{c.get('run_dir', '')}{c.get('candidate', '')}".lower() for c in cands) and any("eurjpy" in f"{c.get('run_dir', '')}{c.get('candidate', '')}".lower() for c in cands)
        )

        # Patch build_quant_portfolio.py
        cfg        = self.cfg
        cands_repr = json.dumps(cands, indent=4)
        script     = SCRIPT_DIR / "build_quant_portfolio.py"
        patches = {
            "PORTFOLIO_NAME":    port_name,
            "QUANT_NAME":        cfg.get("quant_name","TRB"),
            "PORTFOLIO_TYPE":    "MultiMarket" if is_multi_market else "SingleMarket",
            "TARGET_OUTPUT_DIR": out_dir,
        }
        patch_script(script, patches)
        # Also patch the CANDIDATES list (special multi-line replacement)
        try:
            text = script.read_text(encoding="utf-8")
            text = re.sub(
                r"CANDIDATES\s*=\s*\[.*?\]",
                f"CANDIDATES = {cands_repr}",
                text, flags=re.DOTALL
            )
            script.write_text(text, encoding="utf-8")
        except Exception as e:
            self.log_append(self._log, f"[WARN] Could not patch CANDIDATES list: {e}\n")

        self.log_clear(self._log)
        self.run_script("build_quant_portfolio.py", self._log,
                        env_extra={"AF_PORTFOLIO_OUTPUT_DIR": out_dir},
                        on_done=self._refresh_portfolios)

    def _refresh_portfolios(self):
        cfg        = self.cfg
        portfolios = get_portfolios(cfg.get("work_dir",""), cfg.get("quant_name","TRB"))
        self._mc_port_cb.configure(values=portfolios or ["(none)"])
        if portfolios:
            if not self._mc_port_var.get() or self._mc_port_var.get() not in portfolios:
                self._mc_port_var.set(portfolios[0])
        else:
            self._mc_port_var.set("(none)")
        self._update_port_info()

    def _on_port_selected(self, choice=None):
        self._update_port_info()

    def _update_port_info(self):
        if not hasattr(self, "_port_info_lbl"):
            return
        port = self._mc_port_var.get()
        if not port or port == "(none)":
            self._port_info_lbl.configure(text="No built portfolios detected.", text_color=C["sub"])
            return
        cfg = self.cfg
        p_path = find_portfolio_path(cfg.get("work_dir", ""), cfg.get("quant_name", "TRB"), port)
        if not p_path or not p_path.exists():
            self._port_info_lbl.configure(text="📍 Path not resolved", text_color=C["danger"])
            return
        info_items = [f"📍 {p_path.name}"]
        mf = p_path / "portfolio_manifest.json"
        if mf.exists():
            try:
                with open(mf, "r") as mff:
                    mdata = json.load(mff)
                    info_items.append(f"{len(mdata.get('candidates', []))} candidates")
            except Exception:
                pass
        if (p_path / "combined_trades.csv").exists():
            info_items.append("Trades: ✓")
        docx = list(p_path.glob("*_Report.docx"))
        if docx:
            info_items.append("Report: ✓")
        self._port_info_lbl.configure(text="  |  ".join(info_items), text_color=C["accent"])

    def _run_mc(self):
        port = self._mc_port_var.get()
        if not port or port == "(none)":
            messagebox.showwarning("Missing", "No portfolio selected.")
            return
        cfg = self.cfg
        port_path = find_portfolio_path(cfg.get("work_dir", ""), cfg.get("quant_name", "TRB"), port)
        patches = {
            "PORTFOLIO_NAME": port,
            "QUANT_NAME":     cfg.get("quant_name", "TRB"),
        }
        if port_path and port_path.exists():
            patches["PORTFOLIO_DIR"] = str(port_path)
        patch_script(SCRIPT_DIR / "run_portfolio_montecarlo.py", patches)
        self.log_clear(self._log)
        self.run_script("run_portfolio_montecarlo.py", self._log)

    def _open_portfolio(self):
        cfg  = self.cfg
        port = self._mc_port_var.get()
        if port and port != "(none)":
            p = find_portfolio_path(cfg.get("work_dir", ""), cfg.get("quant_name", "TRB"), port)
            if p and p.exists():
                if sys.platform == "win32":
                    os.startfile(str(p))
                else:
                    cmd = ["xdg-open", str(p)] if shutil.which("xdg-open") else ["open", str(p)]
                    subprocess.Popen(cmd)
                return
        wdir = _resolve_work_dir(cfg.get("work_dir", ""))
        if sys.platform == "win32":
            os.startfile(str(wdir))
        else:
            cmd = ["xdg-open", str(wdir)] if shutil.which("xdg-open") else ["open", str(wdir)]
            subprocess.Popen(cmd)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Strategies Browser Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StrategiesPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))
        make_section_header(self, "🗂  Strategies Browser",
            "Browse researched strategies and optimized strategy outputs"
        ).grid(row=0, column=0, sticky="ew", **pad)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=32, pady=(20, 28))
        content.columnconfigure((0,1), weight=1)
        content.rowconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # Researched strategies
        left = make_card(content)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0,10), pady=0)
        left.rowconfigure(1, weight=1)
        make_label(left, "🔬 Researched Strategies", font=FH2, color=C["accent"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14,8))
        self._res_box = make_log(left, height=400)
        self._res_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0,8))
        make_btn(left, "📂 Open Folder",
                 lambda: os.startfile(self.cfg.get("research_dir",
                     str(SCRIPT_DIR/"researched_strategies"))),
                 color=C["card"], hover=C["hover"], width=140).grid(
            row=2, column=0, pady=(0,14))

        # Optimized strategies
        right = make_card(content)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10,0), pady=0)
        right.rowconfigure(1, weight=1)
        make_label(right, "📦 Strategies Library", font=FH2, color=C["accent"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14,8))
        self._strat_box = make_log(right, height=400)
        self._strat_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0,8))
        make_btn(right, "📂 Open Folder",
                 lambda: os.startfile(self.cfg.get("strategies_dir",
                     str(SCRIPT_DIR/"strategies"))),
                 color=C["card"], hover=C["hover"], width=140).grid(
            row=2, column=0, pady=(0,14))

        make_btn(content, "⟳ Refresh", self.refresh,
                 color=C["card"], hover=C["hover"], width=130).grid(
            row=2, column=0, columnspan=2, pady=(12,0), sticky="w")
        self.refresh()

    def _list_dir(self, path: str, widget: ctk.CTkTextbox):
        p = Path(path)
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if not p.exists():
            widget.insert("end", f"  (folder not found)\n  {path}\n")
        else:
            items = sorted(p.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
            if not items:
                widget.insert("end", "  (empty)\n")
            for item in items:
                ts = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d")
                if item.is_dir():
                    # Count files inside
                    fc = len(list(item.iterdir()))
                    widget.insert("end", f"  📁  {item.name:<40}  {fc} items   {ts}\n")
                else:
                    widget.insert("end", f"  📄  {item.name:<40}  {ts}\n")
        widget.configure(state="disabled")

    def refresh(self):
        cfg = self.cfg
        self._list_dir(cfg.get("research_dir",  str(SCRIPT_DIR/"researched_strategies")), self._res_box)
        self._list_dir(cfg.get("strategies_dir", str(SCRIPT_DIR/"strategies")),            self._strat_box)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Settings Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SettingsPanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._entries = {}
        self._build()

    def _field(self, parent, label, cfg_key, row, wide=False, secret=False):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        make_label(f, label, font=FB, color=C["sub"], width=210, anchor="e").pack(side="left", padx=(0,12))
        w = 460 if wide else 320
        e = make_entry(f, width=w, show="•" if secret else None)
        e.insert(0, str(self.cfg.get(cfg_key, "")))
        e.pack(side="left")
        self._entries[cfg_key] = e
        return e

    def _browse_field(self, parent, label, cfg_key, row, is_dir=False):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        make_label(f, label, font=FB, color=C["sub"], width=210, anchor="e").pack(side="left", padx=(0,12))
        e = make_entry(f, width=340)
        e.insert(0, str(self.cfg.get(cfg_key, "")))
        e.pack(side="left")
        self._entries[cfg_key] = e
        def _browse():
            if is_dir:
                p = filedialog.askdirectory(title=f"Select {label}")
            else:
                p = filedialog.askopenfilename(title=f"Select {label}",
                                               filetypes=[("Executables","*.exe"),("All","*.*")])
            if p:
                e.delete(0,"end"); e.insert(0,p)
        make_btn(f, "Browse", _browse, color=C["card"], hover=C["hover"], width=80).pack(side="left", padx=(8,0))

    def _build(self):
        make_section_header(self, "🔧  Settings",
            "Configure AlphaForge — changes are saved to config.json and can be applied to scripts"
        ).grid(row=0, column=0, sticky="ew", padx=32, pady=(28,0))

        scroll = ctk.CTkScrollableFrame(self, fg_color=C["panel"], corner_radius=0)
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        scroll.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        def section(title, subtitle=""):
            card = make_card(scroll)
            card.grid(sticky="ew", padx=32, pady=(16,0))
            card.columnconfigure(0, weight=1)
            lbl = ctk.CTkFrame(card, fg_color="transparent")
            lbl.grid(row=0, column=0, sticky="ew", padx=16, pady=(14,4))
            make_label(lbl, title,    font=FH2, color=C["accent"]).pack(anchor="w")
            if subtitle:
                make_label(lbl, subtitle, font=FSM, color=C["sub"]).pack(anchor="w")
            return card

        # MT5 Terminal
        c1 = section("MT5 Terminal", "Paths and connection credentials")
        self._browse_field(c1, "Terminal Path (.exe)",     "terminal_path",     1, is_dir=False)
        self._browse_field(c1, "Terminal Data Dir",        "terminal_data_dir", 2, is_dir=True)
        self._field(c1,        "Login",                    "login",             3)
        self._field(c1,        "Password",                 "password",          4, secret=True)
        self._field(c1,        "Server",                   "server",            5)
        ctk.CTkFrame(c1, height=14, fg_color="transparent").grid(row=6, column=0)

        # EA & Symbol
        c2 = section("EA & Symbol")
        self._field(c2, "Active EA Name",        "active_ea",    1)
        self._field(c2, "Expert Filename (.ex5)","expert",       2, wide=True)
        self._field(c2, "Symbol",                "symbol",       3, wide=True)
        self._field(c2, "Symbol Key",            "symbol_key",   4)
        self._field(c2, "Period",                "period",       5)
        self._field(c2, "Pip Size",              "pip_size",     6)
        ctk.CTkFrame(c2, height=14, fg_color="transparent").grid(row=7, column=0)

        # Date Ranges
        c3 = section("Date Ranges")
        self._field(c3, "Train From",   "train_from",   1)
        self._field(c3, "Train To",     "train_to",     2)
        self._field(c3, "Val From",     "val_from",     3)
        self._field(c3, "Val To",       "val_to",       4)
        self._field(c3, "Holdout From", "holdout_from", 5)
        self._field(c3, "Holdout To",   "holdout_to",   6)
        ctk.CTkFrame(c3, height=14, fg_color="transparent").grid(row=7, column=0)

        # Account
        c4 = section("Account & Pipeline")
        self._field(c4, "Deposit",             "deposit",              1)
        self._field(c4, "Currency",            "currency",             2)
        self._field(c4, "Leverage",            "leverage",             3)
        self._field(c4, "Top N Train Passes",  "top_n_train",          4)
        self._field(c4, "Optimization Timeout (s)", "opt_timeout",     5)
        self._field(c4, "Single Test Timeout (s)",  "single_test_timeout", 6)
        ctk.CTkFrame(c4, height=14, fg_color="transparent").grid(row=7, column=0)

        # Walk Forward & MC
        c5 = section("Walk Forward & Monte Carlo")
        self._field(c5, "WF Window Months",  "wf_window_months",  1)
        self._field(c5, "WF Step Months",    "wf_step_months",    2)
        self._field(c5, "MC Simulations",    "mc_simulations",    3)
        self._field(c5, "MC Max DD %",       "mc_max_dd",         4)
        self._field(c5, "MC Daily DD %",     "mc_daily_dd",       5)
        self._field(c5, "MC Phase 1 Target %","mc_phase1_target", 6)
        self._field(c5, "MC Phase 2 Target %","mc_phase2_target", 7)
        ctk.CTkFrame(c5, height=14, fg_color="transparent").grid(row=8, column=0)

        # Folders
        c6 = section("Folder Paths")
        self._browse_field(c6, "Work Dir (optimization_runs)", "work_dir",      1, is_dir=True)
        self._browse_field(c6, "Research Dir",                 "research_dir",  2, is_dir=True)
        self._browse_field(c6, "Strategies Dir",               "strategies_dir",3, is_dir=True)
        self._field(c6,        "Quant Portfolio Name Prefix",  "quant_name",    4)
        ctk.CTkFrame(c6, height=14, fg_color="transparent").grid(row=5, column=0)

        # UI & Display Scaling
        c_ui = section("Display & Zoom", "Scale interface up or down to fit your screen resolution")
        ui_f = ctk.CTkFrame(c_ui, fg_color="transparent")
        ui_f.grid(row=1, column=0, padx=16, pady=12, sticky="ew")
        make_label(ui_f, "Interface Zoom Scale:", font=FB, color=C["sub"]).pack(side="left")
        self._zoom_status_lbl = make_label(
            ui_f,
            f"  {int(round(float(self.cfg.get('ui_zoom', 1.0)) * 100))}%  ",
            font=FH2,
            color=C["accent"]
        )
        self._zoom_status_lbl.pack(side="left", padx=8)

        def _do_zoom_out():
            self.app.zoom_out()
            self._zoom_status_lbl.configure(text=f"  {int(round(self.app._current_zoom * 100))}%  ")

        def _do_zoom_reset():
            self.app.zoom_reset()
            self._zoom_status_lbl.configure(text="  100%  ")

        def _do_zoom_in():
            self.app.zoom_in()
            self._zoom_status_lbl.configure(text=f"  {int(round(self.app._current_zoom * 100))}%  ")

        make_btn(ui_f, "− Zoom Out", _do_zoom_out, color=C["card"], hover=C["hover"], width=110).pack(side="left", padx=4)
        make_btn(ui_f, "100% Reset", _do_zoom_reset, color=C["card"], hover=C["hover"], width=100).pack(side="left", padx=4)
        make_btn(ui_f, "+ Zoom In", _do_zoom_in, color=C["card"], hover=C["hover"], width=100).pack(side="left", padx=4)

        make_label(ui_f, "  (Tip: Ctrl + Mouse Wheel, or Ctrl +/- to zoom anytime)", font=FSM, color=C["sub"]).pack(side="left", padx=12)
        ctk.CTkFrame(c_ui, height=14, fg_color="transparent").grid(row=2, column=0)

        # Action buttons
        btn_card = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_card.grid(sticky="ew", padx=32, pady=(20, 28))
        make_btn(btn_card, "💾 Save Config",       self._save,          width=170).pack(side="left")
        make_btn(btn_card, "🔁 Apply to Scripts", self._apply_scripts,
                 color=C["blue"], hover="#2563eb",  width=180).pack(side="left", padx=(12,0))
        make_btn(btn_card, "↩ Reset Defaults",    self._reset_defaults,
                 color=C["card"], hover=C["hover"], width=160).pack(side="left", padx=(12,0))
        self._status_lbl = make_label(btn_card, "", color=C["success"])
        self._status_lbl.pack(side="left", padx=(16,0))

    def _collect(self) -> dict:
        return {k: e.get().strip() for k, e in self._entries.items()}

    def _save(self):
        vals = self._collect()
        self.app.config.update(vals)
        self.app.update_topbar_meta()
        ok   = save_config(self.app.config)
        self._status_lbl.configure(text="✔  Saved." if ok else "✘  Save failed.",
                                   text_color=C["success"] if ok else C["danger"])
        self.after(3000, lambda: self._status_lbl.configure(text=""))

    def _apply_scripts(self):
        vals = self._collect()
        self.app.config.update(vals)
        self.app.update_topbar_meta()
        save_config(self.app.config)

        SCRIPT_PATCHES = {
            "run_optimization.py": {
                "TERMINAL_PATH":      vals.get("terminal_path",""),
                "TERMINAL_DATA_DIR":  vals.get("terminal_data_dir",""),
                "LOGIN":              vals.get("login",""),
                "PASSWORD":           vals.get("password",""),
                "SERVER":             vals.get("server",""),
                "ACTIVE_EA":          vals.get("active_ea",""),
                "EXPERT":             vals.get("expert",""),
                "SYMBOL":             vals.get("symbol",""),
                "SYMBOL_KEY":         vals.get("symbol_key",""),
                "PERIOD":             vals.get("period",""),
                "DEPOSIT":            vals.get("deposit",""),
                "CURRENCY":           vals.get("currency",""),
                "LEVERAGE":           vals.get("leverage",""),
                "TRAIN_FROM":         vals.get("train_from",""),
                "TRAIN_TO":           vals.get("train_to",""),
                "VAL_FROM":           vals.get("val_from",""),
                "VAL_TO":             vals.get("val_to",""),
                "HOLDOUT_FROM":       vals.get("holdout_from",""),
                "HOLDOUT_TO":         vals.get("holdout_to",""),
                "TOP_N_TRAIN":        vals.get("top_n_train",""),
                "OPT_TIMEOUT":        vals.get("opt_timeout",""),
                "SINGLE_TEST_TIMEOUT":vals.get("single_test_timeout",""),
                "WF_WINDOW_MONTHS":   vals.get("wf_window_months",""),
                "WF_STEP_MONTHS":     vals.get("wf_step_months",""),
            },
        }
        errors = []
        for script_name, patches in SCRIPT_PATCHES.items():
            sp = SCRIPT_DIR / script_name
            if sp.exists():
                ok = patch_script(sp, patches)
                if not ok:
                    errors.append(script_name)

        if errors:
            self._status_lbl.configure(text=f"✘ Errors: {errors}", text_color=C["danger"])
        else:
            self._status_lbl.configure(text="✔ Applied to scripts.", text_color=C["success"])
        self.after(4000, lambda: self._status_lbl.configure(text=""))

    def _reset_defaults(self):
        if messagebox.askyesno("Reset", "Reset all settings to defaults?"):
            for k, e in self._entries.items():
                e.delete(0, "end")
                e.insert(0, str(DEFAULT_CONFIG.get(k, "")))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Application
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AlphaForgeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Initialize fonts after root window is created
        global FH1, FH2, FH3, FB, FMO, FSM
        FH1  = ctk.CTkFont("Segoe UI", 22, "bold")
        FH2  = ctk.CTkFont("Segoe UI", 15, "bold")
        FH3  = ctk.CTkFont("Segoe UI", 12, "bold")
        FB   = ctk.CTkFont("Segoe UI", 12)
        FMO  = ctk.CTkFont("Consolas", 11)
        FSM  = ctk.CTkFont("Segoe UI", 10)

        self.config = load_config()
        try:
            self._current_zoom = float(self.config.get("ui_zoom", 1.0))
        except (ValueError, TypeError):
            self._current_zoom = 1.0

        if self._current_zoom != 1.0:
            try:
                ctk.set_widget_scaling(self._current_zoom)
            except Exception:
                pass

        self.title("AlphaForge  —  MT5 Quant Optimizer & Portfolio Builder")
        self.geometry("1420x860")
        self.minsize(1100, 700)
        self.configure(fg_color=C["bg"])

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()
        self._nav_buttons  = {}
        self._active_panel = None
        self._build_nav_buttons()
        self._setup_events()
        self.show_panel("dashboard")

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=230, fg_color=C["sidebar"], corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)

        # Brand header matching cloud app
        logo_f = ctk.CTkFrame(sb, fg_color="transparent")
        logo_f.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 12))

        brand_row = ctk.CTkFrame(logo_f, fg_color="transparent")
        brand_row.pack(anchor="w")

        ctk.CTkLabel(brand_row, text="⚡", font=ctk.CTkFont("Segoe UI", 22),
                     text_color=C["accent"]).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(brand_row, text="AlphaForge",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(side="left")

        ctk.CTkLabel(logo_f, text="MT5 Quant Platform",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["sub"]).pack(anchor="w", padx=(30, 0), pady=(0, 6))

        # Version Pill Badge matching web app
        ver_badge = ctk.CTkFrame(logo_f, fg_color=C["card"], corner_radius=4)
        ver_badge.pack(anchor="w", padx=(30, 0))
        ctk.CTkLabel(ver_badge, text="v1.0 | MT5 Desktop",
                     font=ctk.CTkFont("Consolas", 10),
                     text_color=C["sub"]).pack(padx=8, pady=2)

        sep = ctk.CTkFrame(sb, height=1, fg_color=C["border"])
        sep.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 8))

        # Nav buttons placeholder frame
        self._nav_frame = ctk.CTkFrame(sb, fg_color="transparent")
        self._nav_frame.grid(row=2, column=0, sticky="nsew", pady=(2, 0))
        self._nav_frame.columnconfigure(0, weight=1)
        sb.rowconfigure(2, weight=1)

        # Bottom Local MT5 & Sync Card
        bot_card = ctk.CTkFrame(sb, fg_color="#0b101d", corner_radius=8,
                                border_width=1, border_color=C["border"])
        bot_card.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 14))

        bot_inner = ctk.CTkFrame(bot_card, fg_color="transparent")
        bot_inner.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(bot_inner, text="💻 Local MT5 Ready",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(bot_inner, text="Run: python app.py",
                     font=ctk.CTkFont("Consolas", 10),
                     text_color=C["sub"]).pack(anchor="w", pady=(2, 0))

    def _build_content(self):
        # Main Right Container
        self._main_container = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self._main_container.grid(row=0, column=1, sticky="nsew")
        self._main_container.columnconfigure(0, weight=1)
        self._main_container.rowconfigure(1, weight=1)

        # ── Top Bar matching cloud web app ──────────────────────────────────
        self._topbar = ctk.CTkFrame(self._main_container, height=48, fg_color=C["sidebar"], corner_radius=0)
        self._topbar.grid(row=0, column=0, sticky="ew")
        self._topbar.grid_propagate(False)
        self._topbar.columnconfigure(0, weight=1)

        # Left meta pills: Active EA | Symbol | Period
        tb_left = ctk.CTkFrame(self._topbar, fg_color="transparent")
        tb_left.pack(side="left", padx=20, fill="y")

        cfg = self.config
        ctk.CTkLabel(tb_left, text="Active EA:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["sub"]).pack(side="left")
        self._top_ea_val = ctk.CTkLabel(tb_left, text=f" {cfg.get('active_ea', 'TRB')} ",
                                       font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=C["accent"])
        self._top_ea_val.pack(side="left")

        ctk.CTkLabel(tb_left, text="  |   Symbol:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["sub"]).pack(side="left")
        self._top_sym_val = ctk.CTkLabel(tb_left, text=f" {cfg.get('symbol', 'USDJPY Dukascopy')} ",
                                        font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=C["text"])
        self._top_sym_val.pack(side="left")

        ctk.CTkLabel(tb_left, text="  |   Period:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["sub"]).pack(side="left")
        self._top_per_val = ctk.CTkLabel(tb_left, text=f" {cfg.get('period', 'M15')} ",
                                        font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=C["text"])
        self._top_per_val.pack(side="left")

        # Right toolbar: Quick Scroll, Zoom Controls, Engine Status
        tb_right = ctk.CTkFrame(self._topbar, fg_color="transparent")
        tb_right.pack(side="right", padx=16, fill="y")

        # Quick Scroll cluster (sideways, down and up)
        scroll_grp = ctk.CTkFrame(tb_right, fg_color="#0e1526", corner_radius=6, border_width=1, border_color="#232f48")
        scroll_grp.pack(side="left", padx=(0, 10), pady=8)

        ctk.CTkLabel(scroll_grp, text="⇳ Scroll:", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["sub"]).pack(side="left", padx=(6, 2))

        ctk.CTkButton(scroll_grp, text="▲ Top", width=44, height=24, font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      fg_color="transparent", hover_color=C["hover"], text_color=C["text"],
                      command=lambda: self._scroll_container.scroll_to_top()).pack(side="left", padx=1)
        ctk.CTkButton(scroll_grp, text="▼ Bottom", width=58, height=24, font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      fg_color="transparent", hover_color=C["hover"], text_color=C["text"],
                      command=lambda: self._scroll_container.scroll_to_bottom()).pack(side="left", padx=1)
        ctk.CTkButton(scroll_grp, text="◄ Left", width=46, height=24, font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      fg_color="transparent", hover_color=C["hover"], text_color=C["text"],
                      command=lambda: self._scroll_container.scroll_to_left()).pack(side="left", padx=1)
        ctk.CTkButton(scroll_grp, text="► Right", width=50, height=24, font=ctk.CTkFont("Segoe UI", 10, "bold"),
                      fg_color="transparent", hover_color=C["hover"], text_color=C["text"],
                      command=lambda: self._scroll_container.scroll_to_right()).pack(side="left", padx=(1, 4))

        # Zoom cluster (Zoom In, Out, Reset, Presets)
        zoom_grp = ctk.CTkFrame(tb_right, fg_color="#0e1526", corner_radius=6, border_width=1, border_color="#232f48")
        zoom_grp.pack(side="left", padx=(0, 12), pady=8)

        ctk.CTkLabel(zoom_grp, text="🔍 Zoom", font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["sub"]).pack(side="left", padx=(6, 2))

        ctk.CTkButton(zoom_grp, text="−", width=24, height=24, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=C["card"], hover_color=C["hover"], text_color=C["text"], corner_radius=4,
                      command=self.zoom_out).pack(side="left", padx=2)

        self._zoom_val_btn = ctk.CTkButton(
            zoom_grp, text=f"{int(round(self._current_zoom * 100))}%", width=48, height=24,
            font=ctk.CTkFont("Segoe UI", 10, "bold"), fg_color="transparent", hover_color=C["hover"],
            text_color=C["accent"], corner_radius=4,
            command=self.zoom_reset
        )
        self._zoom_val_btn.pack(side="left", padx=1)

        ctk.CTkButton(zoom_grp, text="+", width=24, height=24, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=C["card"], hover_color=C["hover"], text_color=C["text"], corner_radius=4,
                      command=self.zoom_in).pack(side="left", padx=2)

        self._zoom_presets = ["60%", "70%", "75%", "80%", "85%", "90%", "100%", "110%", "125%", "150%"]
        self._zoom_combo = ctk.CTkComboBox(
            zoom_grp, values=self._zoom_presets, width=72, height=24,
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            command=self._on_zoom_preset
        )
        self._zoom_combo.set(f"{int(round(self._current_zoom * 100))}%")
        self._zoom_combo.pack(side="left", padx=(2, 6))

        # Status badge
        self._status_badge = ctk.CTkLabel(
            tb_right,
            text="● Engine Ready",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=C["success"],
        )
        self._status_badge.pack(side="left", padx=(0, 8))

        # Bottom subtle separator line under topbar
        tb_sep = ctk.CTkFrame(self._topbar, height=1, fg_color=C["border"])
        tb_sep.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")

        # Main dynamic 2-way scrollable container (handles both vertical and horizontal scrolling)
        self._scroll_container = DualScrollableContainer(self._main_container, fg_color=C["panel"])
        self._scroll_container.grid(row=1, column=0, sticky="nsew")
        self._content = self._scroll_container.viewport
        self._panels: dict[str, BasePanel] = {}

    def set_process_status(self, script_name: str | None):
        if hasattr(self, "_status_badge"):
            if script_name:
                self._status_badge.configure(
                    text=f"⚡ Running: {script_name}",
                    text_color=C["accent"]
                )
            else:
                self._status_badge.configure(
                    text="● Engine Ready",
                    text_color=C["success"]
                )

    def update_topbar_meta(self):
        cfg = self.config
        if hasattr(self, "_top_ea_val"):
            self._top_ea_val.configure(text=f" {cfg.get('active_ea', 'TRB')} ")
        if hasattr(self, "_top_sym_val"):
            self._top_sym_val.configure(text=f" {cfg.get('symbol', 'USDJPY Dukascopy')} ")
        if hasattr(self, "_top_per_val"):
            self._top_per_val.configure(text=f" {cfg.get('period', 'M15')} ")

    def _build_nav_buttons(self):
        PANEL_CLASSES = {
            "dashboard":   DashboardPanel,
            "research":    ResearchPanel,
            "optimize":    OptimizePanel,
            "montecarlo":  MonteCarloPanel,
            "walkforward": WalkForwardPanel,
            "fullbacktest":FullBacktestPanel,
            "portfolio":   PortfolioPanel,
            "strategies":  StrategiesPanel,
            "settings":    SettingsPanel,
        }
        for i, (icon, label, key) in enumerate(NAV_ITEMS):
            btn = ctk.CTkButton(
                self._nav_frame,
                text=f"  {icon}  {label}",
                anchor="w",
                height=42,
                fg_color="transparent",
                hover_color=C["hover"],
                text_color=C["sub"],
                font=ctk.CTkFont("Segoe UI", 13),
                corner_radius=8,
                border_width=0,
                command=lambda k=key: self.show_panel(k),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=10, pady=2)
            self._nav_buttons[key] = btn

            # Lazy-create panel
            cls = PANEL_CLASSES.get(key)
            if cls:
                panel = cls(self._content, self)
                panel.grid(row=0, column=0, sticky="nsew")
                panel.grid_remove()
                self._panels[key] = panel

    # ── Panel switching ───────────────────────────────────────────────────────

    def show_panel(self, key: str):
        if self._active_panel and self._active_panel in self._panels:
            self._panels[self._active_panel].grid_remove()
            if self._active_panel in self._nav_buttons:
                self._nav_buttons[self._active_panel].configure(
                    fg_color="transparent",
                    text_color=C["sub"],
                    border_width=0
                )

        panel = self._panels.get(key)
        if panel:
            panel.grid(row=0, column=0, sticky="nsew")
            # Refresh dynamic panels
            if key in ("dashboard", "strategies", "montecarlo") and hasattr(panel, "refresh"):
                panel.refresh()
            self._scroll_container.update_scroll()
            self._scroll_container.scroll_to_top_left()

        if key in self._nav_buttons:
            self._nav_buttons[key].configure(
                fg_color=C["nav_act"],
                text_color=C["accent"],
                border_width=1,
                border_color="#314264"
            )
        self._active_panel = key

    # ── Zoom controls ─────────────────────────────────────────────────────────

    def set_zoom(self, zoom_factor: float, save: bool = True):
        zoom_factor = max(0.5, min(1.8, round(zoom_factor, 2)))
        self._current_zoom = zoom_factor
        try:
            ctk.set_widget_scaling(zoom_factor)
        except Exception as e:
            print(f"Widget scaling notice: {e}")

        pct = int(round(zoom_factor * 100))
        if hasattr(self, "_zoom_val_btn"):
            self._zoom_val_btn.configure(text=f"{pct}%")
        if hasattr(self, "_zoom_combo"):
            self._zoom_combo.set(f"{pct}%")

        if hasattr(self, "_scroll_container"):
            self.after(60, self._scroll_container.update_scroll)

        if save:
            self.config["ui_zoom"] = str(zoom_factor)
            save_config(self.config)

    def zoom_in(self):
        new_zoom = round(self._current_zoom + 0.10, 2)
        if new_zoom > 1.8:
            new_zoom = 1.8
        self.set_zoom(new_zoom)

    def zoom_out(self):
        new_zoom = round(self._current_zoom - 0.10, 2)
        if new_zoom < 0.5:
            new_zoom = 0.5
        self.set_zoom(new_zoom)

    def zoom_reset(self):
        self.set_zoom(1.0)

    def _on_zoom_preset(self, val_str: str):
        try:
            val = int(val_str.replace("%", "").strip()) / 100.0
            self.set_zoom(val)
        except Exception:
            pass

    # ── Keyboard & Mouse event handling ──────────────────────────────────────

    def _setup_events(self):
        # Keyboard shortcuts for zoom
        for key in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind_all(key, lambda e: self.zoom_in())
        for key in ("<Control-minus>", "<Control-underscore>", "<Control-KP_Subtract>"):
            self.bind_all(key, lambda e: self.zoom_out())
        for key in ("<Control-0>", "<Control-KP_0>"):
            self.bind_all(key, lambda e: self.zoom_reset())

        # Keyboard shortcuts for scrolling
        self.bind_all("<Prior>", lambda e: self._scroll_container.scroll_up(8))
        self.bind_all("<Next>", lambda e: self._scroll_container.scroll_down(8))
        self.bind_all("<Home>", lambda e: self._scroll_container.scroll_to_top())
        self.bind_all("<End>", lambda e: self._scroll_container.scroll_to_bottom())
        self.bind_all("<Alt-Left>", lambda e: self._scroll_container.scroll_left(8))
        self.bind_all("<Alt-Right>", lambda e: self._scroll_container.scroll_right(8))

        # Mouse wheel bindings (Windows, macOS)
        self.bind_all("<MouseWheel>", self._handle_mousewheel, add="+")
        self.bind_all("<Shift-MouseWheel>", self._handle_shift_mousewheel, add="+")

        # Linux X11 bindings
        self.bind_all("<Button-4>", self._handle_button4, add="+")
        self.bind_all("<Button-5>", self._handle_button5, add="+")
        self.bind_all("<Shift-Button-4>", lambda e: self._scroll_container.scroll_left(4), add="+")
        self.bind_all("<Shift-Button-5>", lambda e: self._scroll_container.scroll_right(4), add="+")
        self.bind_all("<Control-Button-4>", lambda e: self.zoom_in(), add="+")
        self.bind_all("<Control-Button-5>", lambda e: self.zoom_out(), add="+")

    def _handle_mousewheel(self, event):
        # 1. Ctrl + Wheel -> Zoom In/Out
        if event.state & 0x0004 or event.state & 4:
            if event.delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            return "break"

        # 2. Shift + Wheel -> Sideways scroll
        if event.state & 0x0001 or event.state & 1:
            if event.delta > 0:
                self._scroll_container.scroll_left(4)
            else:
                self._scroll_container.scroll_right(4)
            return "break"

        # 3. Normal Wheel -> Down and Up scroll
        try:
            w = event.widget
            if w and w.winfo_class() == "Text":
                return
        except Exception:
            pass

        if event.delta > 0:
            self._scroll_container.scroll_up(3)
        else:
            self._scroll_container.scroll_down(3)

    def _handle_shift_mousewheel(self, event):
        if event.delta > 0:
            self._scroll_container.scroll_left(4)
        else:
            self._scroll_container.scroll_right(4)
        return "break"

    def _handle_button4(self, event):
        if event.state & 0x0004 or event.state & 4:
            self.zoom_in()
            return "break"
        if event.state & 0x0001 or event.state & 1:
            self._scroll_container.scroll_left(4)
            return "break"
        self._scroll_container.scroll_up(3)

    def _handle_button5(self, event):
        if event.state & 0x0004 or event.state & 4:
            self.zoom_out()
            return "break"
        if event.state & 0x0001 or event.state & 1:
            self._scroll_container.scroll_right(4)
            return "break"
        self._scroll_container.scroll_down(3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    app = AlphaForgeApp()
    app.mainloop()
