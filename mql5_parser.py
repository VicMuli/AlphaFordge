"""
MQL5 Source Code Input Parser & Strategy Configuration Extractor
AlphaFordge Optimization Engine

Scans researched_strategies/<EA>/ for MQL5 (.mq5) files, extracts all input
declarations (input / sinput), and builds:
1. Indicator Filter Switchboard (boolean indicator filters and switches)
2. Strategy Parameter Configuration (core, risk, session, and indicator parameters
   with default values, fixed/optimize modes, and search ranges)
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent

# Known curated parameter defaults and optimization ranges for standard AlphaFordge strategies
KNOWN_PRESETS = {
    "TRB": {
        "ranges": {
            "LotSize": (0.1, 0.05, 0.5),
            "PipsOffset": (8, 1, 20),
            "TPMultiplier": (1.5, 0.5, 4.5),
            "MinRangePips": (15, 5, 50),
            "MaxRangePips": (100, 20, 240),
            "StartHourGMT": (0, 1, 3),
            "EndHourGMT": (5, 1, 9),
            "CancelHourGMT": (8, 1, 14),
            "CloseHourGMT": (11, 1, 17),
            "RiskPercent": (0.25, 0.25, 2.0),
            "EMAPeriod": (50, 25, 300),
            "AdxPeriod": (7, 1, 21),
            "AdxMin": (15.0, 2.5, 40.0),
            "AtrPeriod": (7, 1, 21),
            "AtrMinPips": (0.0, 2.0, 30.0),
            "AtrTrailPeriod": (7, 1, 21),
            "AtrTrailMultiplier": (1.0, 0.5, 4.0),
            "NewsBlockMinutesBefore": (15, 15, 60),
            "NewsBlockMinutesAfter": (15, 15, 60),
        },
        "fixed_defaults": {
            "LotSize": 0.2,
            "PipsOffset": 13,
            "TPMultiplier": 3.0,
            "MinRangePips": 25,
            "MaxRangePips": 180,
            "MagicNumber": 881024,
            "UseMonthlyDDLimit": 1,
            "MonthlyDDPercent": 3.0,
            "UseDailyLossLimit": 1,
            "DailyLossPercent": 4.0,
            "UseRiskBasedSizing": 0,
        },
        "optimize_by_default": ["AdxPeriod", "AdxMin", "AtrPeriod", "AtrMinPips"]
    },
    "ORB": {
        "ranges": {
            "InpFixedLotSize": (0.1, 0.1, 2.0),
            "InpRiskPercent": (0.25, 0.25, 2.0),
            "InpTPRatio": (1.0, 0.25, 3.0),
            "InpSLBufferPips": (0, 1, 10),
            "InpMaxRangePips": (30, 10, 150),
            "InpRangeStartHour": (6, 1, 10),
            "InpRangeEndHour": (9, 1, 12),
            "InpEntryCutoffHour": (12, 1, 20),
            "InpRetestTolerancePips": (0.5, 0.5, 5.0),
            "InpRetestMaxBars": (5, 5, 30),
            "InpEmaPeriod": (50, 25, 300),
            "InpRsiPeriod": (7, 1, 21),
            "InpRsiUpper": (60.0, 2.5, 85.0),
            "InpRsiLower": (15.0, 2.5, 40.0),
            "InpAtrPeriod": (7, 1, 21),
            "InpAtrMin": (0.0, 0.5, 5.0),
            "InpAdxPeriod": (7, 1, 21),
            "InpAdxMin": (15.0, 2.5, 40.0),
            "InpMacdFast": (6, 1, 16),
            "InpMacdSlow": (18, 2, 34),
            "InpMacdSignal": (5, 1, 13),
            "InpHtfEmaPeriod": (20, 10, 100),
        },
        "fixed_defaults": {
            "InpFixedLotSize": 1.0,
            "InpMagicNumber": 10101,
            "InpPipSize": 0.0001,
        },
        "optimize_by_default": ["InpTPRatio", "InpSLBufferPips", "InpMacdFast", "InpMacdSlow", "InpMacdSignal"]
    }
}


def _clean_val(val_str: str) -> Any:
    """Parse raw string into bool, int, float, or str."""
    if not val_str:
        return ""
    v = val_str.strip()
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v.strip(' "')


def _generate_range_for_val(val: Any) -> Tuple[float, float, float]:
    """Intelligently generate a start, step, stop search range around a default value."""
    if isinstance(val, bool):
        return (0, 1, 1)
    if isinstance(val, int):
        if val <= 0:
            return (0, 1, 10)
        if val <= 5:
            return (1, 1, max(5, val * 3))
        if val <= 30:
            start = max(1, int(val * 0.5))
            step = 1 if val < 15 else 2
            stop = int(val * 1.8)
            return (start, step, stop)
        if val <= 100:
            start = max(10, int(val * 0.5))
            step = 5
            stop = int(val * 1.5)
            return (start, step, stop)
        start = max(20, int(val * 0.5))
        step = 25
        stop = int(val * 1.5)
        return (start, step, stop)
    if isinstance(val, float):
        if val <= 0.0:
            return (0.0, 0.5, 5.0)
        if val <= 1.0:
            return (round(val * 0.5, 2), 0.1, round(val * 2.0, 2))
        start = round(val * 0.5, 2)
        step = round(max(0.1, val * 0.1), 2)
        stop = round(val * 2.0, 2)
        return (start, step, stop)
    return (0, 1, 10)


def _categorize_param(name: str, group_title: str) -> str:
    """Classify parameter into core, timing, risk, indicator, or custom."""
    n = name.lower()
    g = group_title.lower() if group_title else ""
    if "risk" in g or "drawdown" in g or "loss" in n or "risk" in n or "dd" in n:
        return "risk"
    if "timing" in g or "session" in g or "hour" in n or "time" in n or "minute" in n:
        return "timing"
    if "indicator" in g or "filter" in g or "ema" in n or "adx" in n or "atr" in n or "rsi" in n or "macd" in n:
        return "indicator"
    if "lot" in n or "tp" in n or "sl" in n or "offset" in n or "range" in n or "magic" in n or "retest" in n:
        return "core"
    return "core"


def parse_mql5_file(mq5_path: Path, ea_name: str = "") -> Dict[str, Any]:
    """
    Parse an MQL5 (.mq5) file and extract its inputs, indicator filter switchboard,
    and parameter configuration.
    """
    if not mq5_path.exists():
        return {
            "ea_name": ea_name,
            "mq5_file": str(mq5_path),
            "indicators": [],
            "params": [],
            "error": f"File {mq5_path} does not exist"
        }

    try:
        content = mq5_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "ea_name": ea_name,
            "mq5_file": str(mq5_path),
            "indicators": [],
            "params": [],
            "error": str(e)
        }

    # Match input group "..."
    # Match input / sinput declarations:
    # e.g.: input double LotSize = 0.2; // Fixed Lot Size
    # e.g.: input bool UseTrendFilter = true; // EMA Trend Filter
    lines = content.splitlines()

    current_group = ""
    raw_inputs = []

    # Regex for input declaration
    input_regex = re.compile(
        r'^\s*(?:input|sinput)\s+([\w_:]+)\s+([\w_]+)\s*(?:=\s*([^;]+))?;(?:\s*//\s*(.*))?',
        re.IGNORECASE
    )
    group_regex = re.compile(
        r'^\s*input\s+group\s+"([^"]+)"',
        re.IGNORECASE
    )

    for line in lines:
        g_match = group_regex.match(line)
        if g_match:
            current_group = g_match.group(1).strip()
            continue

        m = input_regex.match(line)
        if m:
            var_type = m.group(1).strip()
            var_name = m.group(2).strip()
            raw_val = m.group(3).strip() if m.group(3) else ""
            comment = m.group(4).strip() if m.group(4) else ""

            parsed_val = _clean_val(raw_val)
            raw_inputs.append({
                "type": var_type,
                "name": var_name,
                "value": parsed_val,
                "comment": comment,
                "group": current_group
            })

    # Separate into Indicator Filter Switchboard and Strategy Parameters
    indicators = []
    params = []

    ea_key = ea_name.upper() if ea_name else "CUSTOM"
    presets = KNOWN_PRESETS.get(ea_key, {})
    preset_ranges = presets.get("ranges", {})
    preset_fixed = presets.get("fixed_defaults", {})
    preset_opt = presets.get("optimize_by_default", [])

    # Identify Boolean Filters / Switchboard
    for inp in raw_inputs:
        v_name = inp["name"]
        v_type = inp["type"].lower()
        is_bool = v_type == "bool" or isinstance(inp["value"], bool)

        # Indicator / Filter switch detection
        is_filter_switch = is_bool and any(
            kw in v_name.lower()
            for kw in ["use", "filter", "enable", "switch", "active"]
        )

        if is_filter_switch:
            # Clean display label
            label = inp["comment"] or re.sub(r'([A-Z])', r' \1', v_name).strip()
            # Deriving id
            clean_id = v_name.lower().replace("inp", "").replace("use", "").replace("filter", "").strip("_")
            if not clean_id:
                clean_id = v_name.lower()

            # Find linked parameters specifically related to this indicator
            linked_params = []
            filter_stem = clean_id.split('_')[0] if clean_id else ""

            # Common indicator acronyms / roots to match
            known_roots = {
                "trend": ["ema"],
                "ema": ["ema"],
                "adx": ["adx"],
                "atr": ["atr"],
                "atrtrailingstop": ["atrtrail", "trail"],
                "news": ["news"],
                "rsi": ["rsi"],
                "macd": ["macd"],
                "htf": ["htf"],
                "retest": ["retest"],
                "sizing": ["riskpercent"],
            }
            roots = known_roots.get(clean_id, [filter_stem] if len(filter_stem) >= 3 else [])

            for other in raw_inputs:
                o_name = other["name"]
                if o_name == v_name:
                    continue
                o_type = other["type"].lower()
                if o_type == "bool":
                    continue
                # Match root
                low_o = o_name.lower()
                matched = any(r in low_o for r in roots)
                if matched:
                    linked_params.append(o_name)

            indicators.append({
                "id": clean_id,
                "name": label,
                "toggleParam": v_name,
                "enabled": bool(inp["value"]),
                "optimize": False,
                "description": inp["comment"] or f"Toggles {label}",
                "paramNames": list(dict.fromkeys(linked_params))  # unique preserving order
            })

    # Strategy Parameters (All non-toggles or all tunable inputs)
    for inp in raw_inputs:
        v_name = inp["name"]
        v_type = inp["type"].lower()
        v_val = inp["value"]

        # If it was already treated as an indicator toggle switch, we don't duplicate it in params
        if any(ind["toggleParam"] == v_name for ind in indicators):
            continue

        label = inp["comment"] or re.sub(r'([A-Z])', r' \1', v_name).strip()
        category = _categorize_param(v_name, inp["group"])

        # Range determination
        if v_name in preset_ranges:
            rng_tuple = preset_ranges[v_name]
        else:
            rng_tuple = _generate_range_for_val(v_val)

        # Mode determination (Fixed vs Optimize)
        if preset_opt:
            is_opt = v_name in preset_opt
        else:
            # Smart auto-detection for non-preset EAs:
            # Mark the top numeric parameters (periods, multipliers, buffers, thresholds) as optimizable
            low_name = v_name.lower()
            is_ignored = any(ign in low_name for ign in ["magic", "slip", "comment", "color", "timer", "digits", "dev", "font"])
            is_numeric = v_type in ("int", "float", "double", "short", "long", "uint", "ushort", "ulong")
            has_valid_range = rng_tuple[2] > rng_tuple[0] and rng_tuple[1] > 0
            
            # Prioritize strategy tunables: period, mult, ratio, buffer, tp, sl, threshold, range
            is_tunable_keyword = any(kw in low_name for kw in [
                "period", "mult", "ratio", "buffer", "offset", "tp", "sl", 
                "threshold", "range", "level", "step", "fast", "slow", "signal",
                "filter", "min", "max", "pips"
            ])
            is_opt = is_numeric and not is_ignored and has_valid_range and (is_tunable_keyword or len([p for p in params if p.get("mode") == "optimize"]) < 4)

        params.append({
            "name": v_name,
            "label": label,
            "type": v_type,
            "category": category,
            "mode": "optimize" if is_opt else "fixed",
            "fixedValue": preset_fixed.get(v_name, v_val),
            "range": {
                "start": rng_tuple[0],
                "step": rng_tuple[1],
                "stop": rng_tuple[2]
            },
            "description": inp["comment"] or f"Parameter {v_name}"
        })

    return {
        "ea_name": ea_name,
        "mq5_file": str(mq5_path.relative_to(SCRIPT_DIR) if mq5_path.is_relative_to(SCRIPT_DIR) else mq5_path),
        "indicators": indicators,
        "params": params,
        "raw_count": len(raw_inputs)
    }


def get_strategy_mql5_config(ea_name: str, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Finds the MQL5 file for `ea_name` inside `researched_strategies/<ea_name>/`
    and parses its inputs into switchboard + parameter config.
    """
    if base_dir is None:
        base_dir = SCRIPT_DIR / "researched_strategies"

    ea_folder = base_dir / ea_name
    if not ea_folder.exists() or not ea_folder.is_dir():
        # Fallback: check if base_dir contains any folder matching ea_name case-insensitively
        found = None
        if base_dir.exists():
            for d in base_dir.iterdir():
                if d.is_dir() and d.name.lower() == ea_name.lower():
                    found = d
                    break
        if found:
            ea_folder = found
        else:
            ea_folder.mkdir(parents=True, exist_ok=True)

    # Search for .mq5 file in folder
    mq5_files = list(ea_folder.glob("*.mq5"))
    if not mq5_files:
        # Check subdirectories
        mq5_files = list(ea_folder.rglob("*.mq5"))

    if not mq5_files:
        # If no .mq5 in folder, check if a known preset exists or create baseline
        return {
            "ea_name": ea_name,
            "mq5_file": None,
            "indicators": [],
            "params": [],
            "error": f"No .mq5 file found in {ea_folder}"
        }

    # Use first matching .mq5
    primary_mq5 = mq5_files[0]
    return parse_mql5_file(primary_mq5, ea_name=ea_name)


if __name__ == "__main__":
    import sys
    ea = sys.argv[1] if len(sys.argv) > 1 else "TRB"
    res = get_strategy_mql5_config(ea)
    print(json.dumps(res, indent=2))
