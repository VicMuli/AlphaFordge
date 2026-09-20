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
    "work_dir":           str(SCRIPT_DIR / "optimization_runs"),
    "quant_name":         "TRB",
    "research_dir":       str(SCRIPT_DIR / "researched_strategies"),
    "strategies_dir":     str(SCRIPT_DIR / "strategies"),
}

NAV_ITEMS = [
    ("🏠", "Dashboard",    "dashboard"),
    ("🔬", "Research",     "research"),
    ("⚙",  "Optimize",    "optimize"),
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
    if name_lower in ("quant_portfolios", "portfolios") or name_lower.endswith("_quant_portfolios") or name_lower.endswith("_portfolios"):
        return False
    # Check for portfolio files
    if (d / "portfolio_manifest.json").exists() or (d / "combined_trades.csv").exists():
        return True
    if any(f.is_file() and (f.name.endswith("_Report.docx") or f.name.startswith("chart_")) for f in d.iterdir()):
        return True
    pname = d.parent.name.lower()
    if "quant_portfolios" in pname or pname == "quant_portfolios":
        return True
    if "portfolio_" in name_lower:
        return True
    return False


def get_portfolios(work_dir: str, quant_name: str = "") -> list:
    """Return sorted list of valid portfolio directory names found under work_dir."""
    base = _resolve_work_dir(work_dir)
    if not base.exists():
        return []

    found_dirs: list[Path] = []

    # 1. Direct standard location: base / Quant_Portfolios / {quant_name}_Quant_Portfolios
    if quant_name:
        direct = base / "Quant_Portfolios" / f"{quant_name}_Quant_Portfolios"
        if direct.exists() and direct.is_dir():
            for d in direct.iterdir():
                if is_valid_portfolio_dir(d):
                    found_dirs.append(d)

    # 2. Check 1-level subfolders (e.g. base / trb_usdjpy / Quant_Portfolios / ...)
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

    # 3. Search via rglob for any Quant_Portfolios or portfolio_manifest.json under base
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

    # Deduplicate by folder name
    unique_names = {d.name: d for d in found_dirs}
    return sorted(list(unique_names.keys()), reverse=True)


def find_portfolio_path(work_dir: str, quant_name: str, port_name: str) -> Path | None:
    """Find the exact directory Path for a given portfolio name."""
    if not port_name or port_name == "(none)":
        return None
    base = _resolve_work_dir(work_dir)
    if not base.exists():
        return None

    # 1. Direct standard location: base / Quant_Portfolios / {quant_name}_Quant_Portfolios / port_name
    if quant_name:
        cand = base / "Quant_Portfolios" / f"{quant_name}_Quant_Portfolios" / port_name
        if cand.exists() and is_valid_portfolio_dir(cand):
            return cand

    # 2. Check in subfolders (e.g. base / trb_usdjpy / Quant_Portfolios / ...)
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

    # 3. Search via rglob
    try:
        for found in base.rglob(port_name):
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
        if env_extra:
            env.update(env_extra)

        cmd = [sys.executable, str(script_path)] + (args or [])

        def _worker():
            self.log_append(log_widget,
                f"▶  {datetime.now().strftime('%H:%M:%S')}  {script_name}\n"
                f"   CWD: {SCRIPT_DIR}\n{'─'*60}\n")
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(SCRIPT_DIR), env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32" else 0,
                )
                for line in iter(proc.stdout.readline, ""):
                    self.log_append(log_widget, line)
                proc.wait()
                self.log_append(log_widget,
                    f"\n{'─'*60}\n✔  Finished  (code {proc.returncode})  "
                    f"{datetime.now().strftime('%H:%M:%S')}\n")
                if on_done:
                    log_widget.after(0, on_done)
            except Exception as exc:
                self.log_append(log_widget, f"\n[ERROR] {exc}\n")

        threading.Thread(target=_worker, daemon=True).start()


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
        self._build()

    def _set(self, entry, val):
        entry.delete(0, "end")
        entry.insert(0, str(val))

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))
        make_section_header(self, "🔬  Research Backtest",
            "Run a default (un-optimised) backtest for a newly researched strategy"
        ).grid(row=0, column=0, sticky="ew", **pad)

        # Form
        form = make_card(self)
        form.grid(row=1, column=0, sticky="ew", padx=32, pady=(24, 0))

        cfg = self.cfg
        fields = [
            ("Strategy Name",  "My_Strategy_v1",           "name"),
            ("Expert (.ex5)",  cfg.get("expert",""),        "expert"),
            ("Set File",       "my_strategy.set",           "set_file"),
            ("Symbol",         cfg.get("symbol",""),        "symbol"),
            ("Period",         cfg.get("period",""),        "period"),
            ("From Date",      cfg.get("train_from",""),    "from_date"),
            ("To Date",        cfg.get("holdout_to",""),    "to_date"),
            ("Deposit ($)",    cfg.get("deposit","2500"),   "deposit"),
        ]
        self._entries = {}
        for i, (label, default, key) in enumerate(fields):
            row_f = ctk.CTkFrame(form, fg_color="transparent")
            row_f.grid(row=i, column=0, sticky="ew", padx=20, pady=6)
            ctk.CTkLabel(row_f, text=label, font=FB, text_color=C["sub"],
                         width=150, anchor="e").pack(side="left", padx=(0,12))
            e = make_entry(row_f, placeholder=default, width=360)
            e.insert(0, default)
            e.pack(side="left")
            self._entries[key] = e
            if key == "set_file":
                make_btn(row_f, "Browse .set", lambda: self._browse_set(),
                         color=C["card"], hover=C["hover"], width=110).pack(side="left", padx=(8,0))

        # Buttons
        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=len(fields), column=0, sticky="ew", padx=20, pady=(16, 16))
        make_btn(btn_row, "▶  Run Research Backtest", self._run, width=230).pack(side="left")
        make_btn(btn_row, "📂 Open Output Folder",
                 self._open_output, color=C["card"], hover=C["hover"], width=180).pack(side="left", padx=(12,0))

        # Log
        log_card = make_card(self)
        log_card.grid(row=2, column=0, sticky="nsew", padx=32, pady=(20, 28))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        make_label(log_card, "Live Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self._log = make_log(log_card, height=260)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

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
        if not v["name"]:
            messagebox.showwarning("Missing", "Strategy Name is required.")
            return
        self.log_clear(self._log)
        env_extra = {
            "AF_STRATEGY_NAME": v["name"],
            "AF_SET_FILE":      v["set_file"],
            "AF_EXPERT":        v["expert"],
            "AF_SYMBOL":        v["symbol"],
            "AF_PERIOD":        v["period"],
            "AF_FROM_DATE":     v["from_date"],
            "AF_TO_DATE":       v["to_date"],
            "AF_DEPOSIT":       v["deposit"],
        }
        self.run_script("run_research_backtest.py", self._log, env_extra=env_extra)

    def _open_output(self):
        v        = self._get_vals()
        name     = v.get("name", "").strip() or "My_Strategy_v1"
        out_dir  = Path(self.cfg.get("research_dir",
                         str(SCRIPT_DIR / "researched_strategies"))) / name
        out_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(out_dir))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Optimization Panel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OptimizePanel(BasePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        pad = dict(padx=32, pady=(28, 0))
        make_section_header(self, "⚙  Optimization Pipeline",
            "Train → Validation → Holdout → Monte Carlo certification"
        ).grid(row=0, column=0, sticky="ew", **pad)

        cfg = self.cfg

        # Config overview cards
        info = make_card(self)
        info.grid(row=1, column=0, sticky="ew", padx=32, pady=(24, 0))
        info.columnconfigure((0,1,2,3), weight=1)

        info_data = [
            ("EA / Expert",    cfg.get("active_ea","?") + "  –  " + cfg.get("expert","")),
            ("Symbol",         cfg.get("symbol","") + "  " + cfg.get("period","")),
            ("Date Range",     cfg.get("train_from","") + " → " + cfg.get("holdout_to","")),
            ("Deposit",        f"${float(cfg.get('deposit',2500)):,.0f}  {cfg.get('currency','USD')}"),
        ]
        for i, (lbl, val) in enumerate(info_data):
            f = ctk.CTkFrame(info, fg_color="transparent")
            f.grid(row=0, column=i, padx=16, pady=14, sticky="nsew")
            make_label(f, lbl, font=FSM, color=C["sub"]).pack(anchor="w")
            make_label(f, val, font=FH3, color=C["text"]).pack(anchor="w")

        # Phase progress indicators
        prog_card = make_card(self)
        prog_card.grid(row=2, column=0, sticky="ew", padx=32, pady=(16, 0))
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
        btn_row.grid(row=3, column=0, sticky="ew", padx=32, pady=(20, 0))
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
        log_card.grid(row=4, column=0, sticky="nsew", padx=32, pady=(20, 28))
        log_card.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        make_label(log_card, "Live Pipeline Output", font=FH3, color=C["sub"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12,4))
        self._log = make_log(log_card, height=300)
        self._log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _run(self):
        self.log_clear(self._log)
        self.run_script("run_optimization.py", self._log)

    def _open_param_dialog(self):
        ea = self.cfg.get("active_ea", "TRB").upper()
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Optimization Parameters & Ranges — {ea}")
        dlg.geometry("780x640")
        dlg.configure(fg_color=C["bg"])
        dlg.grab_set()

        make_section_header(dlg, f"🔧 {ea} Parameters & Indicator Ranges",
            "Configure which parameters are fixed and the search ranges for optimization"
        ).pack(fill="x", padx=24, pady=(20, 10))

        scroll = ctk.CTkScrollableFrame(dlg, fg_color=C["panel"], corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=24, pady=10)
        scroll.columnconfigure(1, weight=1)

        opt_params = self.cfg.get("optimization_params", {}).get(ea, self.cfg.get("optimization_params", {}))
        fixed_dict = dict(opt_params.get("fixed_params", {}))
        ranges_dict = dict(opt_params.get("opt_ranges", {}))
        toggles_dict = dict(opt_params.get("indicator_toggles", {}))

        # Default fallback indicators & params if not yet in config
        if ea == "ORB":
            default_indicators = [
                ("InpUseEmaFilter", "EMA Filter", toggles_dict.get("InpUseEmaFilter", 1)),
                ("InpUseRsiFilter", "RSI Filter", toggles_dict.get("InpUseRsiFilter", 0)),
                ("InpUseAtrFilter", "ATR Filter", toggles_dict.get("InpUseAtrFilter", 0)),
                ("InpUseAdxFilter", "ADX Filter", toggles_dict.get("InpUseAdxFilter", 0)),
                ("InpUseMacdFilter", "MACD Filter", toggles_dict.get("InpUseMacdFilter", 1)),
                ("InpUseHtfFilter", "HTF Filter", toggles_dict.get("InpUseHtfFilter", 0)),
            ]
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
            default_indicators = [
                ("UseTrendFilter", "EMA Trend Filter", toggles_dict.get("UseTrendFilter", 1)),
                ("UseAdxFilter", "ADX Volatility Filter", toggles_dict.get("UseAdxFilter", 1)),
                ("UseAtrFilter", "ATR Range Filter", toggles_dict.get("UseAtrFilter", 1)),
                ("UseAtrTrailingStop", "ATR Trailing Stop", toggles_dict.get("UseAtrTrailingStop", 0)),
                ("UseNewsFilter", "News Event Filter", toggles_dict.get("UseNewsFilter", 0)),
            ]
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

        # Overrides
        ovr = ctk.CTkFrame(sel, fg_color="transparent")
        ovr.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(6, 6))
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
        btn_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(16,16))
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
        run  = self._run_var.get()
        cand = self._cand_var.get()
        if not run or not cand or cand == "(none found)":
            messagebox.showwarning("Missing", "Select a run and candidate.")
            return
        patch_script(SCRIPT_DIR / "run_full_backtest.py", {
            "TARGET_RUN_DIR": run,
            "TARGET_CANDIDATE": cand,
        })
        env_extra = {
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
        r0.grid(row=0, column=0, sticky="ew", padx=20, pady=(14,6))
        make_label(r0, "Portfolio Name", font=FB, color=C["sub"], width=160, anchor="e").pack(side="left", padx=(0,12))
        self._port_name = make_entry(r0, width=320)
        self._port_name.insert(0, f"{cfg.get('quant_name','TRB')}_Quant_Portfolio_001")
        self._port_name.pack(side="left")

        make_label(meta, "Candidates   (run_dir | candidate | weight)",
                   font=FH3, color=C["accent"]).grid(row=1, column=0, sticky="w", padx=20, pady=(12,4))

        # Scrollable candidate list
        self._cand_scroll = ctk.CTkScrollableFrame(meta, height=200, fg_color=C["inp"],
                                                    corner_radius=8)
        self._cand_scroll.grid(row=2, column=0, sticky="ew", padx=16, pady=(0,8))
        self._cand_scroll.columnconfigure((0,1,2), weight=1)
        self._add_candidate_row()  # Start with one empty row

        btn_add = make_btn(meta, "+ Add Candidate", self._add_candidate_row,
                           color=C["card"], hover=C["hover"], width=160)
        btn_add.grid(row=3, column=0, sticky="w", padx=20, pady=(0,14))

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
                cands.append({"run_dir": r, "candidate": c, "weight": float(w)})
        return cands

    def _build_portfolio(self):
        cands     = self._get_candidates_list()
        port_name = self._port_name.get().strip()
        if not cands:
            messagebox.showwarning("Empty", "Add at least one candidate.")
            return
        if not port_name:
            messagebox.showwarning("Missing", "Enter a portfolio name.")
            return
        # Patch build_quant_portfolio.py
        cfg        = self.cfg
        cands_repr = json.dumps(cands, indent=4)
        script     = SCRIPT_DIR / "build_quant_portfolio.py"
        patch_script(script, {
            "PORTFOLIO_NAME":    port_name,
            "QUANT_NAME":        cfg.get("quant_name","TRB"),
        })
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
        ok   = save_config(self.app.config)
        self._status_lbl.configure(text="✔  Saved." if ok else "✘  Save failed.",
                                   text_color=C["success"] if ok else C["danger"])
        self.after(3000, lambda: self._status_lbl.configure(text=""))

    def _apply_scripts(self):
        vals = self._collect()
        self.app.config.update(vals)
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
        self.show_panel("dashboard")

    # ── Sidebar ──────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=220, fg_color=C["sidebar"], corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)

        # Logo area
        logo_f = ctk.CTkFrame(sb, fg_color="transparent", height=110)
        logo_f.grid(row=0, column=0, sticky="ew")
        logo_f.grid_propagate(False)
        ctk.CTkLabel(logo_f, text="⚡", font=ctk.CTkFont("Segoe UI", 38)).pack(pady=(22, 0))
        ctk.CTkLabel(logo_f, text="AlphaForge",
                     font=ctk.CTkFont("Segoe UI", 16, "bold"),
                     text_color=C["accent"]).pack()
        ctk.CTkLabel(logo_f, text="MT5 Quant Platform",
                     font=ctk.CTkFont("Segoe UI", 9),
                     text_color=C["sub"]).pack()

        sep = ctk.CTkFrame(sb, height=1, fg_color=C["border"])
        sep.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 4))

        # Nav buttons placeholder frame
        self._nav_frame = ctk.CTkFrame(sb, fg_color="transparent")
        self._nav_frame.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        self._nav_frame.columnconfigure(0, weight=1)
        sb.rowconfigure(2, weight=1)

        # Bottom version
        ctk.CTkLabel(sb, text="v1.0  |  AlphaForge",
                     font=ctk.CTkFont("Segoe UI", 9),
                     text_color=C["sub"]).grid(row=3, column=0, pady=(0, 16))

    def _build_content(self):
        self._content = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=1)
        self._panels: dict[str, BasePanel] = {}

    def _build_nav_buttons(self):
        PANEL_CLASSES = {
            "dashboard":   DashboardPanel,
            "research":    ResearchPanel,
            "optimize":    OptimizePanel,
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
                height=46,
                fg_color="transparent",
                hover_color=C["hover"],
                text_color=C["sub"],
                font=ctk.CTkFont("Segoe UI", 13),
                corner_radius=8,
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
        if self._active_panel:
            self._panels[self._active_panel].grid_remove()
            self._nav_buttons[self._active_panel].configure(
                fg_color="transparent", text_color=C["sub"])

        panel = self._panels.get(key)
        if panel:
            panel.grid()
            # Refresh dynamic panels
            if key == "dashboard" and hasattr(panel, "refresh"):
                panel.refresh()
            if key == "strategies" and hasattr(panel, "refresh"):
                panel.refresh()

        self._nav_buttons[key].configure(
            fg_color=C["nav_act"],
            text_color=C["accent"])
        self._active_panel = key


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    app = AlphaForgeApp()
    app.mainloop()
