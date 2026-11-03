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

# Standard Built-in MT5 Enums and Dropdown Options
BUILTIN_ENUMS: Dict[str, List[Dict[str, Any]]] = {
    "bool": [
        {"value": True, "label": "true (Enabled / Yes)"},
        {"value": False, "label": "false (Disabled / No)"}
    ],
    "boolean": [
        {"value": True, "label": "true (Enabled / Yes)"},
        {"value": False, "label": "false (Disabled / No)"}
    ],
    "enum_timeframes": [
        {"value": "PERIOD_CURRENT", "label": "PERIOD_CURRENT (Current Timeframe)"},
        {"value": "PERIOD_M1", "label": "PERIOD_M1 (1 Minute)"},
        {"value": "PERIOD_M5", "label": "PERIOD_M5 (5 Minutes)"},
        {"value": "PERIOD_M15", "label": "PERIOD_M15 (15 Minutes)"},
        {"value": "PERIOD_M30", "label": "PERIOD_M30 (30 Minutes)"},
        {"value": "PERIOD_H1", "label": "PERIOD_H1 (1 Hour)"},
        {"value": "PERIOD_H4", "label": "PERIOD_H4 (4 Hours)"},
        {"value": "PERIOD_D1", "label": "PERIOD_D1 (Daily)"},
        {"value": "PERIOD_W1", "label": "PERIOD_W1 (Weekly)"},
        {"value": "PERIOD_MN1", "label": "PERIOD_MN1 (Monthly)"}
    ],
    "enum_tp_mode": [
        {"value": "TP_OPPOSITE_RANGE", "label": "Opposite Range Target (TP_OPPOSITE_RANGE)"},
        {"value": "TP_FIXED_RR", "label": "Fixed Risk:Reward Ratio (TP_FIXED_RR)"},
        {"value": "TP_ATR_MULT", "label": "ATR Volatility Multiple (TP_ATR_MULT)"},
        {"value": "TP_FIXED_PIPS", "label": "Fixed Pips Target (TP_FIXED_PIPS)"}
    ],
    "enum_sl_mode": [
        {"value": "SL_RANGE_OPPOSITE", "label": "Opposite Range Boundary (SL_RANGE_OPPOSITE)"},
        {"value": "SL_FIXED_PIPS", "label": "Fixed Pips Stop Loss (SL_FIXED_PIPS)"},
        {"value": "SL_ATR_MULT", "label": "ATR Volatility Stop (SL_ATR_MULT)"}
    ],
    "enum_applied_price": [
        {"value": "PRICE_CLOSE", "label": "Close Price (PRICE_CLOSE)"},
        {"value": "PRICE_OPEN", "label": "Open Price (PRICE_OPEN)"},
        {"value": "PRICE_HIGH", "label": "High Price (PRICE_HIGH)"},
        {"value": "PRICE_LOW", "label": "Low Price (PRICE_LOW)"},
        {"value": "PRICE_MEDIAN", "label": "Median Price HL/2 (PRICE_MEDIAN)"},
        {"value": "PRICE_TYPICAL", "label": "Typical Price HLC/3 (PRICE_TYPICAL)"},
        {"value": "PRICE_WEIGHTED", "label": "Weighted Price HLCC/4 (PRICE_WEIGHTED)"}
    ],
    "enum_ma_method": [
        {"value": "MODE_SMA", "label": "Simple MA (MODE_SMA)"},
        {"value": "MODE_EMA", "label": "Exponential MA (MODE_EMA)"},
        {"value": "MODE_SMMA", "label": "Smoothed MA (MODE_SMMA)"},
        {"value": "MODE_LWMA", "label": "Linear Weighted MA (MODE_LWMA)"}
    ],
    "enum_order_type": [
        {"value": "ORDER_TYPE_BUY_STOP", "label": "Pending Breakout (Stop Orders)"},
        {"value": "ORDER_TYPE_BUY_LIMIT", "label": "Retest Pullback (Limit Orders)"},
        {"value": "ORDER_TYPE_BUY", "label": "Market Execution"}
    ],
    "enum_entry_type": [
        {"value": "ORDER_TYPE_BUY_STOP", "label": "Pending Breakout (Stop Orders)"},
        {"value": "ORDER_TYPE_BUY_LIMIT", "label": "Retest Pullback (Limit Orders)"},
        {"value": "ORDER_TYPE_BUY", "label": "Market Execution"}
    ]
}

# Alias mapping for built-in enums
BUILTIN_ENUM_ALIASES = {
    "timeframe": "enum_timeframes",
    "period": "enum_timeframes",
    "tp_mode": "enum_tp_mode",
    "takeprofitmode": "enum_tp_mode",
    "enum_takeprofit_mode": "enum_tp_mode",
    "sl_mode": "enum_sl_mode",
    "stoplossmode": "enum_sl_mode",
    "enum_stoploss_mode": "enum_sl_mode",
    "applied_price": "enum_applied_price",
    "ma_method": "enum_ma_method",
    "entry_type": "enum_entry_type",
}

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
            "TakeProfitMode": "TP_OPPOSITE_RANGE",
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


def parse_mql5_enums(content: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract custom enum declarations from MQL5 source code:
    enum ENUM_TP_MODE
    {
       TP_OPPOSITE_RANGE, // Opposite Range
       TP_FIXED_RR,        // Fixed Risk:Reward
       TP_ATR_MULT         // ATR Multiplier
    };
    """
    enums: Dict[str, List[Dict[str, Any]]] = {}
    enum_pattern = re.compile(r'\benum\s+([\w_]+)\s*\{([^}]+)\}', re.MULTILINE | re.DOTALL)
    for match in enum_pattern.finditer(content):
        enum_name = match.group(1).strip()
        body = match.group(2)
        items = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue
            comment = ""
            if "//" in line:
                parts = line.split("//", 1)
                line = parts[0].strip()
                comment = parts[1].strip()
            line = line.rstrip(',;').strip()
            if not line:
                continue
            if "=" in line:
                val_name = line.split("=")[0].strip()
            else:
                val_name = line.strip()

            if val_name:
                label = f"{comment} ({val_name})" if comment else val_name
                items.append({
                    "value": val_name,
                    "label": label
                })
        if items:
            enums[enum_name] = items
            enums[enum_name.lower()] = items
            # Also register with or without ENUM_ prefix
            if enum_name.lower().startswith("enum_"):
                short_name = enum_name.lower().replace("enum_", "")
                enums[short_name] = items

    return enums


def resolve_dropdown_options(var_name: str, var_type: str, raw_val: Any, file_enums: Dict[str, List[Dict[str, Any]]]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Determines if a parameter is an enum/dropdown in MT5 and resolves its option list.
    """
    t_low = var_type.lower().strip()
    n_low = var_name.lower().strip()
    val_str = str(raw_val).strip()

    # 1. Boolean types
    if t_low in ("bool", "boolean") or isinstance(raw_val, bool):
        return True, BUILTIN_ENUMS["bool"]

    # 2. Match in file-parsed custom enums
    if var_type in file_enums:
        return True, file_enums[var_type]
    if t_low in file_enums:
        return True, file_enums[t_low]
    if t_low.startswith("enum_"):
        stripped = t_low.replace("enum_", "")
        if stripped in file_enums:
            return True, file_enums[stripped]

    # 3. Match in built-in enums directly or via alias
    if t_low in BUILTIN_ENUMS:
        return True, BUILTIN_ENUMS[t_low]
    if t_low in BUILTIN_ENUM_ALIASES:
        return True, BUILTIN_ENUMS[BUILTIN_ENUM_ALIASES[t_low]]

    # 4. Value-based detection (e.g. if default value is TP_OPPOSITE_RANGE or PERIOD_M15)
    for enum_key, opts in BUILTIN_ENUMS.items():
        if any(str(opt["value"]).lower() == val_str.lower() for opt in opts):
            return True, opts

    for enum_key, opts in file_enums.items():
        if any(str(opt["value"]).lower() == val_str.lower() for opt in opts):
            return True, opts

    # 5. Name-based heuristic (e.g. timeframe, takeprofitmode, tp_mode)
    if "timeframe" in n_low or "period" in n_low and val_str.startswith("PERIOD_"):
        return True, BUILTIN_ENUMS["enum_timeframes"]
    if ("tp_mode" in n_low or "takeprofitmode" in n_low or "tpmode" in n_low):
        return True, BUILTIN_ENUMS["enum_tp_mode"]
    if ("sl_mode" in n_low or "stoplossmode" in n_low or "slmode" in n_low):
        return True, BUILTIN_ENUMS["enum_sl_mode"]

    # 6. Integer boolean toggles (Use*, Enable*, Show*, Avoid*)
    is_bool_toggle_name = any(n_low.startswith(pfx) for pfx in ["use", "enable", "show", "avoid", "inpuse", "inpavoid", "inpshow"])
    if is_bool_toggle_name and (val_str in ("0", "1", "true", "false", "True", "False") or raw_val in (0, 1)):
        return True, [
            {"value": 1, "label": "1 (Enabled / True)"},
            {"value": 0, "label": "0 (Disabled / False)"}
        ]

    return False, []


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

    # Extract all enum definitions in this file
    file_enums = parse_mql5_enums(content)

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
        v_type = inp["type"]
        v_val = inp["value"]

        # If it was already treated as an indicator toggle switch, we don't duplicate it in params
        if any(ind["toggleParam"] == v_name for ind in indicators):
            continue

        label = inp["comment"] or re.sub(r'([A-Z])', r' \1', v_name).strip()
        category = _categorize_param(v_name, inp["group"])

        # Check if parameter has a dropdown/enum in MT5
        is_dropdown, drop_options = resolve_dropdown_options(v_name, v_type, v_val, file_enums)

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
            is_numeric = v_type.lower() in ("int", "float", "double", "short", "long", "uint", "ushort", "ulong")
            has_valid_range = rng_tuple[2] > rng_tuple[0] and rng_tuple[1] > 0
            
            # Prioritize strategy tunables: period, mult, ratio, buffer, tp, sl, threshold, range
            is_tunable_keyword = any(kw in low_name for kw in [
                "period", "mult", "ratio", "buffer", "offset", "tp", "sl", 
                "threshold", "range", "level", "step", "fast", "slow", "signal",
                "filter", "min", "max", "pips"
            ])
            is_opt = not is_dropdown and is_numeric and not is_ignored and has_valid_range and (is_tunable_keyword or len([p for p in params if p.get("mode") == "optimize"]) < 4)

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
            "description": inp["comment"] or f"Parameter {v_name}",
            "isDropdown": is_dropdown,
            "options": drop_options,
            "optionValues": [opt["value"] for opt in drop_options] if drop_options else []
        })

    return {
        "ea_name": ea_name,
        "mq5_file": str(mq5_path.relative_to(SCRIPT_DIR) if mq5_path.is_relative_to(SCRIPT_DIR) else mq5_path),
        "indicators": indicators,
        "params": params,
        "raw_count": len(raw_inputs)
    }


def _parse_set_file_to_config(set_path: Path, ea_name: str) -> Dict[str, Any]:
    """Fallback parser when only a .set file is available."""
    try:
        content = ""
        for enc in ("utf-16", "utf-16-le", "utf-8", "cp1252"):
            try:
                content = set_path.read_text(encoding=enc)
                break
            except Exception:
                continue
        params = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#") or "=" not in line:
                continue
            parts = line.split("=", 1)
            p_name = parts[0].strip()
            p_body = parts[1].strip()
            is_opt = "||Y" in p_body or "||y" in p_body
            if "||" in p_body:
                chunks = p_body.split("||")
                cur_val = _clean_val(chunks[0])
                st = _clean_val(chunks[1]) if len(chunks) > 1 else cur_val
                sp = _clean_val(chunks[2]) if len(chunks) > 2 else 1
                so = _clean_val(chunks[3]) if len(chunks) > 3 else cur_val
                rng = (st, sp, so)
            else:
                cur_val = _clean_val(p_body)
                rng = _generate_range_for_val(cur_val)

            val_type = type(cur_val).__name__
            is_dropdown, drop_options = resolve_dropdown_options(p_name, val_type, cur_val, {})

            params.append({
                "name": p_name,
                "label": re.sub(r'([A-Z])', r' \1', p_name).strip(),
                "type": val_type,
                "category": _categorize_param(p_name, ""),
                "mode": "optimize" if is_opt else "fixed",
                "fixedValue": cur_val,
                "range": {"start": rng[0], "step": rng[1], "stop": rng[2]},
                "description": f"Parameter {p_name}",
                "isDropdown": is_dropdown,
                "options": drop_options,
                "optionValues": [opt["value"] for opt in drop_options] if drop_options else []
            })
        return {
            "ea_name": ea_name,
            "mq5_file": None,
            "indicators": [],
            "params": params,
            "raw_count": len(params)
        }
    except Exception as e:
        print(f"  [WARN] Failed parsing .set file: {e}")
        return {"ea_name": ea_name, "mq5_file": None, "indicators": [], "params": [], "raw_count": 0}


def get_strategy_mql5_config(ea_name: str, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Finds the MQL5 file for `ea_name` inside `researched_strategies/` or `strategies/`
    and parses its inputs into switchboard + parameter config.
    Supports flexible matching (e.g. 'LRB' matches 'LRB V1.0').
    """
    clean_ea = re.sub(r'\.(ex5|mq5)$', '', ea_name, flags=re.IGNORECASE).strip().lower()

    search_dirs = [
        SCRIPT_DIR / "researched_strategies",
        SCRIPT_DIR / "strategies",
        SCRIPT_DIR,
    ]
    if base_dir:
        search_dirs.insert(0, Path(base_dir))

    matched_folder = None
    direct_mq5 = None
    direct_set = None

    for sdir in search_dirs:
        if not sdir.exists():
            continue
        # 1. Direct file search
        for f in sdir.glob("*.mq5"):
            f_stem = f.stem.lower()
            if f_stem == clean_ea or f_stem.startswith(clean_ea) or clean_ea.startswith(f_stem):
                direct_mq5 = f
                break
        if direct_mq5:
            break

        # 2. Folder search
        for d in sdir.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            d_low = d.name.lower()
            if d_low == clean_ea or d_low.startswith(clean_ea) or clean_ea.startswith(d_low) or clean_ea in d_low:
                matched_folder = d
                break
        if matched_folder:
            break

    # Search for .mq5 file in matched folder
    primary_mq5 = direct_mq5
    if not primary_mq5 and matched_folder:
        mq5_files = list(matched_folder.glob("*.mq5")) or list(matched_folder.rglob("*.mq5"))
        if mq5_files:
            primary_mq5 = mq5_files[0]
        else:
            set_files = list(matched_folder.glob("*.set")) or list(matched_folder.rglob("*.set"))
            if set_files:
                direct_set = set_files[0]

    if primary_mq5:
        return parse_mql5_file(primary_mq5, ea_name=ea_name)

    if direct_set:
        return _parse_set_file_to_config(direct_set, ea_name=ea_name)

    # 3. HTML report fallback (e.g. HA V1.0_default.htm contains EA Inputs)
    if matched_folder:
        htm_files = list(matched_folder.glob("*.htm*"))
        if htm_files:
            try:
                import report_analysis as ra
                parsed_rep = ra.parse_report(htm_files[0])
                ea_inputs = parsed_rep.get("ea_inputs", {})
                if ea_inputs:
                    params = []
                    for p_name, p_val_str in ea_inputs.items():
                        cur_val = _clean_val(p_val_str)
                        rng = _generate_range_for_val(cur_val)
                        is_numeric = isinstance(cur_val, (int, float)) and not isinstance(cur_val, bool)
                        low_name = p_name.lower()
                        is_ignored = any(ign in low_name for ign in ["magic", "slip", "depth", "comment"])
                        is_opt = is_numeric and not is_ignored
                        params.append({
                            "name": p_name,
                            "label": re.sub(r'([A-Z])', r' \1', p_name).strip(),
                            "type": type(cur_val).__name__,
                            "category": _categorize_param(p_name, ""),
                            "mode": "optimize" if is_opt else "fixed",
                            "fixedValue": cur_val,
                            "range": {"start": rng[0], "step": rng[1], "stop": rng[2]},
                            "description": f"Parameter {p_name}"
                        })
                    return {
                        "ea_name": ea_name,
                        "mq5_file": None,
                        "indicators": [],
                        "params": params,
                        "raw_count": len(params)
                    }
            except Exception as ex:
                print(f"  [INFO] HTML report input parse fallback: {ex}")

    # Check KNOWN_PRESETS for fallback
    ea_upper = ea_name.upper().split()[0]
    if ea_upper in KNOWN_PRESETS:
        preset = KNOWN_PRESETS[ea_upper]
        params = []
        for name, rng in preset.get("ranges", {}).items():
            params.append({
                "name": name,
                "label": name,
                "type": "double" if isinstance(rng[0], float) else "int",
                "category": _categorize_param(name, ""),
                "mode": "optimize" if name in preset.get("optimize_by_default", []) else "fixed",
                "fixedValue": preset.get("fixed_defaults", {}).get(name, rng[0]),
                "range": {"start": rng[0], "step": rng[1], "stop": rng[2]},
                "description": f"Preset parameter {name}"
            })
        return {
            "ea_name": ea_name,
            "mq5_file": None,
            "indicators": [],
            "params": params,
            "raw_count": len(params)
        }

    return {
        "ea_name": ea_name,
        "mq5_file": None,
        "indicators": [],
        "params": [],
        "error": f"No .mq5 or .set file found for strategy '{ea_name}' in workspace"
    }


if __name__ == "__main__":
    import sys
    ea = sys.argv[1] if len(sys.argv) > 1 else "TRB"
    res = get_strategy_mql5_config(ea)
    print(json.dumps(res, indent=2))
