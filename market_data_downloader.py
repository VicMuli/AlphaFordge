#!/usr/bin/env python3
"""
market_data_downloader.py
HistData M1 & Tick Data Downloader and Organizer for AlphaForge.

Downloads M1 (1-minute bars) and Tick quotes directly from HistData.com,
extracts and organizes data into:
    market_data/
      └── <PAIR>/
            ├── M1/
            │     └── DAT_ASCII_<PAIR>_M1_<YEAR>.csv
            ├── TICK/
            │     └── DAT_ASCII_<PAIR>_T_<YEAR><MONTH>.csv
            └── manifest.json
"""

import os
import sys
import re
import json
import time
import zipfile
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# Root directory for AlphaForge market data
SCRIPT_DIR = Path(__file__).parent.resolve()
MARKET_DATA_DIR = SCRIPT_DIR / "market_data"

HISTDATA_BASE_URL = "https://www.histdata.com"
HISTDATA_GET_URL = "https://www.histdata.com/get.php"

# Standard popular pairs supported on HistData
POPULAR_PAIRS = [
    "AUDJPY", "AUDUSD", "CHFJPY", "EURCAD", "EURCHF", "EURGBP", 
    "EURJPY", "EURUSD", "GBPAUD", "GBPJPY", "GBPUSD", "NZDUSD", 
    "USDCAD", "USDCHF", "USDJPY", "XAUUSD"
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def get_token_from_page(page_url: str, max_retries: int = 3) -> str | None:
    """Fetches HistData page and parses the hidden 'tk' security token."""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": HISTDATA_BASE_URL,
    }
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(page_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    continue
                html = resp.read().decode("utf-8", errors="ignore")
                m = re.search(r'id=[\"\']tk[\"\']\s+value=[\"\']([^\"\']+)[\"\']', html)
                if not m:
                    m = re.search(r'value=[\"\']([^\"\']+)[\"\']\s+id=[\"\']tk[\"\']', html)
                if m:
                    return m.group(1).strip()
        except Exception as e:
            if attempt == max_retries:
                print(f"[WARN] Failed fetching token from {page_url} (Attempt {attempt}): {e}")
            time.sleep(1.0)
    return None


def download_histdata_file(
    pair: str,
    timeframe: str,  # 'M1' or 'T'
    year: int,
    month: int | None = None,
    platform: str = "ASCII",
    dest_dir: Path | None = None,
    extract: bool = True
) -> Path | None:
    """
    Downloads a single file from HistData.
    - M1 can be yearly (month=None) or monthly.
    - Tick is strictly monthly.
    """
    pair_lower = pair.lower()
    pair_upper = pair.upper()

    # 1. Build Referer URL
    if timeframe.upper() == "M1":
        tf_path = "1-minute-bar-quotes"
        tf_code = "M1"
        if month is None:
            referer_url = f"{HISTDATA_BASE_URL}/download-free-forex-historical-data/?/{platform.lower()}/{tf_path}/{pair_lower}/{year}"
            date_param = str(year)
            datemonth_param = str(year)
        else:
            referer_url = f"{HISTDATA_BASE_URL}/download-free-forex-historical-data/?/{platform.lower()}/{tf_path}/{pair_lower}/{year}/{month}"
            date_param = str(year)
            datemonth_param = f"{year}{str(month).zfill(2)}"
    else:  # TICK
        tf_path = "tick-data-quotes"
        tf_code = "T"
        month_val = month if month is not None else 1
        referer_url = f"{HISTDATA_BASE_URL}/download-free-forex-historical-data/?/{platform.lower()}/{tf_path}/{pair_lower}/{year}/{month_val}"
        date_param = str(year)
        datemonth_param = f"{year}{str(month_val).zfill(2)}"

    print(f"[PAGE] Requesting token for {pair_upper} {tf_code} {datemonth_param}...")
    token = get_token_from_page(referer_url)
    if not token:
        print(f"[ERROR] Could not extract download token for {pair_upper} {datemonth_param}. The data might not exist on HistData.")
        return None

    # 2. POST to get.php
    post_payload = {
        "tk": token,
        "date": date_param,
        "datemonth": datemonth_param,
        "platform": platform,
        "timeframe": tf_code,
        "fxpair": pair_lower
    }
    encoded_data = urllib.parse.urlencode(post_payload).encode("utf-8")
    post_headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer_url,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    if dest_dir is None:
        subfolder = "M1" if tf_code == "M1" else "TICK"
        dest_dir = MARKET_DATA_DIR / pair_upper / subfolder

    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_filename = f"DAT_{platform}_{pair_upper}_{tf_code}_{datemonth_param}.zip"
    zip_path = dest_dir / zip_filename

    try:
        print(f"[DOWNLOAD] Streaming {zip_filename} from HistData...")
        req = urllib.request.Request(HISTDATA_GET_URL, data=encoded_data, headers=post_headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            content = resp.read()
            if not content or len(content) < 200 or not content.startswith(b"PK"):
                print(f"[ERROR] Invalid ZIP payload received ({len(content)} bytes). Response preview: {content[:100]}")
                return None
            
            with open(zip_path, "wb") as f:
                f.write(content)
        
        file_size_mb = len(content) / (1024 * 1024)
        print(f"[SUCCESS] Downloaded {zip_filename} ({file_size_mb:.2f} MB)")

        # 3. Extract if requested
        if extract:
            extracted_files = []
            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    z.extract(member, dest_dir)
                    extracted_path = dest_dir / member
                    extracted_files.append(extracted_path)
            
            # Remove zip archive to conserve space
            try:
                zip_path.unlink()
            except Exception:
                pass

            if extracted_files:
                final_csv = extracted_files[0]
                csv_size_mb = final_csv.stat().st_size / (1024 * 1024)
                print(f"[UNPACKED] Extracted: {final_csv.name} ({csv_size_mb:.2f} MB)")
                return final_csv
        return zip_path

    except Exception as e:
        print(f"[ERROR] Failed downloading {zip_filename}: {e}")
        return None


def download_pair_dataset(
    pair: str,
    data_type: str = "both",  # "m1", "tick", "both"
    years: list[int] | None = None,
    months: list[int] | None = None,
    platform: str = "ASCII",
    extract: bool = True
) -> dict:
    """
    Downloads and organizes M1 and/or Tick dataset for a pair.
    Saves metadata to market_data/<PAIR>/manifest.json.
    """
    pair = pair.upper().strip()
    current_year = datetime.now().year
    if not years:
        # Default to last 3 complete years
        years = [current_year - 3, current_year - 2, current_year - 1]

    pair_root = MARKET_DATA_DIR / pair
    m1_dir = pair_root / "M1"
    tick_dir = pair_root / "TICK"
    m1_dir.mkdir(parents=True, exist_ok=True)
    tick_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "pair": pair,
        "m1_files": [],
        "tick_files": [],
        "errors": []
    }

    # 1. Download M1 data (annual files where available)
    if data_type in ("m1", "both"):
        print(f"\n==========================================")
        print(f"📥 Starting M1 Data Download for {pair} (Years: {years})")
        print(f"==========================================")
        for y in years:
            try:
                # Annual M1 file
                res = download_histdata_file(
                    pair=pair,
                    timeframe="M1",
                    year=y,
                    month=None,
                    platform=platform,
                    dest_dir=m1_dir,
                    extract=extract
                )
                if res and res.exists():
                    results["m1_files"].append(str(res.relative_to(SCRIPT_DIR)))
                else:
                    results["errors"].append(f"M1 {y} failed or unavailable")
            except Exception as e:
                results["errors"].append(f"M1 {y} exception: {e}")
            # Respect rate limit
            time.sleep(1.0)

    # 2. Download Tick data (monthly files)
    if data_type in ("tick", "both"):
        print(f"\n==========================================")
        print(f"📥 Starting Tick Data Download for {pair} (Years: {years})")
        print(f"==========================================")
        target_months = months if months else list(range(1, 13))
        for y in years:
            for m in target_months:
                try:
                    res = download_histdata_file(
                        pair=pair,
                        timeframe="T",
                        year=y,
                        month=m,
                        platform=platform,
                        dest_dir=tick_dir,
                        extract=extract
                    )
                    if res and res.exists():
                        results["tick_files"].append(str(res.relative_to(SCRIPT_DIR)))
                    else:
                        results["errors"].append(f"Tick {y}-{m:02d} failed or unavailable")
                except Exception as e:
                    results["errors"].append(f"Tick {y}-{m:02d} exception: {e}")
                # Respect rate limit
                time.sleep(1.2)

    # Update manifest
    manifest_data = update_pair_manifest(pair)
    results["manifest"] = manifest_data
    return results


def update_pair_manifest(pair: str) -> dict:
    """Scans market_data/<PAIR> and writes an updated manifest.json."""
    pair_dir = MARKET_DATA_DIR / pair.upper()
    if not pair_dir.exists():
        return {}

    m1_dir = pair_dir / "M1"
    tick_dir = pair_dir / "TICK"

    m1_files = []
    m1_bytes = 0
    if m1_dir.exists():
        for p in m1_dir.iterdir():
            if p.is_file() and not p.name.startswith("."):
                size = p.stat().st_size
                m1_bytes += size
                m1_files.append({
                    "name": p.name,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "ext": p.suffix.lower()
                })

    tick_files = []
    tick_bytes = 0
    if tick_dir.exists():
        for p in tick_dir.iterdir():
            if p.is_file() and not p.name.startswith("."):
                size = p.stat().st_size
                tick_bytes += size
                tick_files.append({
                    "name": p.name,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "ext": p.suffix.lower()
                })

    manifest = {
        "pair": pair.upper(),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "m1_count": len(m1_files),
        "m1_total_mb": round(m1_bytes / (1024 * 1024), 2),
        "tick_count": len(tick_files),
        "tick_total_mb": round(tick_bytes / (1024 * 1024), 2),
        "total_mb": round((m1_bytes + tick_bytes) / (1024 * 1024), 2),
        "m1_files": sorted(m1_files, key=lambda x: x["name"]),
        "tick_files": sorted(tick_files, key=lambda x: x["name"]),
    }

    manifest_path = pair_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def get_market_data_catalog() -> dict:
    """Scans all pair subdirectories inside market_data/."""
    MARKET_DATA_DIR.mkdir(parents=True, exist_ok=True)
    pairs_data = []
    total_bytes = 0
    total_m1 = 0
    total_ticks = 0

    for item in sorted(MARKET_DATA_DIR.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            manifest_path = item / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = update_pair_manifest(item.name)
            else:
                data = update_pair_manifest(item.name)
            
            pairs_data.append(data)
            total_bytes += int(data.get("total_mb", 0) * 1024 * 1024)
            total_m1 += data.get("m1_count", 0)
            total_ticks += data.get("tick_count", 0)

    return {
        "market_data_dir": str(MARKET_DATA_DIR),
        "total_pairs": len(pairs_data),
        "total_m1_files": total_m1,
        "total_tick_files": total_ticks,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "popular_pairs": POPULAR_PAIRS,
        "pairs": pairs_data
    }


def parse_year_range(arg_str: str) -> list[int]:
    """Parses '2021,2022,2023' or '2020-2024' into a sorted list of ints."""
    years = set()
    parts = [p.strip() for p in arg_str.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            s_parts = p.split("-")
            if len(s_parts) == 2 and s_parts[0].isdigit() and s_parts[1].isdigit():
                start_y, end_y = int(s_parts[0]), int(s_parts[1])
                for y in range(min(start_y, end_y), max(start_y, end_y) + 1):
                    years.add(y)
        elif p.isdigit():
            years.add(int(p))
    return sorted(list(years))


def parse_month_list(arg_str: str | None) -> list[int]:
    """Parses '1,2,3,4' or '1-6' into list of month ints."""
    if not arg_str:
        return list(range(1, 13))
    months = set()
    parts = [p.strip() for p in arg_str.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            s_parts = p.split("-")
            if len(s_parts) == 2 and s_parts[0].isdigit() and s_parts[1].isdigit():
                start_m, end_m = int(s_parts[0]), int(s_parts[1])
                for m in range(min(start_m, end_m), max(start_m, end_m) + 1):
                    if 1 <= m <= 12:
                        months.add(m)
        elif p.isdigit():
            val = int(p)
            if 1 <= val <= 12:
                months.add(val)
    return sorted(list(months))


def main():
    parser = argparse.ArgumentParser(description="HistData M1 & Tick Data Downloader for AlphaForge")
    parser.add_argument("--pair", type=str, help="Currency pair (e.g., AUDJPY, EURUSD, USDJPY)")
    parser.add_argument("--type", type=str, choices=["m1", "tick", "both"], default="both", help="Data type to download")
    parser.add_argument("--years", type=str, default="2022-2024", help="Years to download, e.g. 2021,2022 or 2020-2024")
    parser.add_argument("--months", type=str, default=None, help="Months for tick data, e.g. 1-12 or 1,2,3 (default all)")
    parser.add_argument("--platform", type=str, default="ASCII", choices=["ASCII", "MT"], help="Platform format (ASCII or MT)")
    parser.add_argument("--no-extract", action="store_true", help="Keep zip files instead of extracting CSVs")
    parser.add_argument("--catalog", action="store_true", help="Output catalog JSON of downloaded pairs")

    args = parser.parse_args()

    if args.catalog:
        catalog = get_market_data_catalog()
        print(json.dumps(catalog, indent=2))
        return

    if not args.pair:
        parser.print_help()
        print("\n[ERROR] --pair is required. (e.g. --pair AUDJPY --type both --years 2023)")
        sys.exit(1)

    years_list = parse_year_range(args.years)
    months_list = parse_month_list(args.months)
    extract = not args.no_extract

    pairs_to_run = [p.strip().upper() for p in args.pair.split(",") if p.strip()]

    print(f"🚀 AlphaForge Market Data Engine Initiated")
    print(f"Pairs: {', '.join(pairs_to_run)}")
    print(f"Type: {args.type.upper()} | Years: {years_list} | Format: {args.platform}")
    print(f"Target Directory: {MARKET_DATA_DIR}")

    for p in pairs_to_run:
        download_pair_dataset(
            pair=p,
            data_type=args.type,
            years=years_list,
            months=months_list,
            platform=args.platform,
            extract=extract
        )

    print("\n✅ Market Data Download & Organization Complete!")
    print(f"Folders updated in: {MARKET_DATA_DIR}")


if __name__ == "__main__":
    main()
