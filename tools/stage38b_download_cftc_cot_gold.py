#!/usr/bin/env python3
"""
Stage38B — CFTC COT Gold downloader

Purpose:
    Download and normalize free official CFTC Commitments of Traders data for
    GOLD - COMMODITY EXCHANGE INC. / CFTC contract market code 088691.

Scope:
    - Read-only data foundation only.
    - No Stage39, no EA, no paper-live, no live order, no trading signal.
    - Uses official CFTC Public Reporting Environment / Socrata endpoint.

Expected use:
    python3 tools/stage38b_download_cftc_cot_gold.py \
      --start-year 2009 \
      --out-dir data/cot/cftc

Outputs:
    data/cot/cftc/raw/disaggregated_futures_only/cot_gold_088691_raw.json
    data/cot/cftc/normalized/cot_gold_weekly.csv
    data/cot/cftc/metadata/stage38b_cot_gold_download_metadata.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DATASET_ID = "72hh-3qpy"
REPORT_TYPE = "DISAGGREGATED_FUTURES_ONLY"
SOURCE_NAME = "CFTC Public Reporting Environment / Socrata API"
BASE_URL = f"https://publicreporting.cftc.gov/resource/{DATASET_ID}.json"
GOLD_CFTC_CONTRACT_MARKET_CODE = "088691"
GOLD_MARKET_NAME = "GOLD - COMMODITY EXCHANGE INC."
DEFAULT_LIMIT = 50000
DEFAULT_RETRIES = 4
DEFAULT_SLEEP_SECONDS = 0.35
USER_AGENT = "xauusd-stage38b-cot-gold-downloader/1.0 (+read-only research; no trading)"

NORMALIZED_COLUMNS = [
    "as_of_date",
    "report_type",
    "source_name",
    "source_url",
    "market_and_exchange_names",
    "cftc_contract_market_code",
    "cftc_market_code",
    "cftc_commodity_code",
    "open_interest_all",
    "prod_merc_long_all",
    "prod_merc_short_all",
    "swap_long_all",
    "swap_short_all",
    "swap_spread_all",
    "m_money_long_all",
    "m_money_short_all",
    "m_money_spread_all",
    "other_rept_long_all",
    "other_rept_short_all",
    "other_rept_spread_all",
    "tot_rept_long_all",
    "tot_rept_short_all",
    "nonrept_long_all",
    "nonrept_short_all",
    "change_open_interest_all",
    "change_m_money_long_all",
    "change_m_money_short_all",
    "change_prod_merc_long_all",
    "change_prod_merc_short_all",
    "pct_oi_m_money_long_all",
    "pct_oi_m_money_short_all",
    "pct_oi_prod_merc_long_all",
    "pct_oi_prod_merc_short_all",
    "pct_oi_swap_long_all",
    "pct_oi_swap_short_all",
    "traders_total_all",
    "contract_units",
    "raw_record_json",
]

# Socrata field names are lower_snake_case. Historical compressed files use
# CFTC title-case names. The aliases below make the normalizer tolerant to
# both naming styles and to minor PRE schema variations.
ALIASES: Dict[str, Sequence[str]] = {
    "as_of_date": (
        "report_date_as_yyyy_mm_dd",
        "as_of_date_form_yyyy_mm_dd",
        "as_of_date_form_yyyy_mm_dd",
        "as_of_date_form_yyyy_mm_dd",
        "report_date_as_yyyy_mm_dd",
        "as_of_date_form_yyyy_mm_dd",
        "As_of_Date_Form_YYYY-MM-DD",
        "Report_Date_as_YYYY-MM-DD",
        "report_date",
    ),
    "market_and_exchange_names": (
        "market_and_exchange_names",
        "Market_and_Exchange_Names",
    ),
    "cftc_contract_market_code": (
        "cftc_contract_market_code",
        "cftc_contract_market_code_quotes",
        "CFTC_Contract_Market_Code",
        "CFTC_Contract_Market_Code_Quotes",
    ),
    "cftc_market_code": (
        "cftc_market_code",
        "cftc_market_code_quotes",
        "CFTC_Market_Code",
        "CFTC_Market_Code_Quotes",
    ),
    "cftc_commodity_code": (
        "cftc_commodity_code",
        "cftc_commodity_code_quotes",
        "CFTC_Commodity_Code",
        "CFTC_Commodity_Code_Quotes",
    ),
    "open_interest_all": (
        "open_interest_all",
        "Open_Interest_All",
    ),
    "prod_merc_long_all": (
        "prod_merc_positions_long_all",
        "prod_merc_positions_long",
        "Prod_Merc_Positions_Long_All",
    ),
    "prod_merc_short_all": (
        "prod_merc_positions_short_all",
        "prod_merc_positions_short",
        "Prod_Merc_Positions_Short_All",
    ),
    "swap_long_all": (
        "swap_positions_long_all",
        "swap_positions_long",
        "Swap_Positions_Long_All",
    ),
    "swap_short_all": (
        "swap_positions_short_all",
        "swap_positions_short",
        "swap__positions_short_all",
        "Swap__Positions_Short_All",
    ),
    "swap_spread_all": (
        "swap_positions_spread_all",
        "swap_positions_spread",
        "swap__positions_spread_all",
        "Swap__Positions_Spread_All",
    ),
    "m_money_long_all": (
        "m_money_positions_long_all",
        "m_money_positions_long",
        "M_Money_Positions_Long_All",
    ),
    "m_money_short_all": (
        "m_money_positions_short_all",
        "m_money_positions_short",
        "M_Money_Positions_Short_All",
    ),
    "m_money_spread_all": (
        "m_money_positions_spread_all",
        "m_money_positions_spread",
        "M_Money_Positions_Spread_All",
    ),
    "other_rept_long_all": (
        "other_rept_positions_long_all",
        "other_rept_positions_long",
        "Other_Rept_Positions_Long_All",
    ),
    "other_rept_short_all": (
        "other_rept_positions_short_all",
        "other_rept_positions_short",
        "Other_Rept_Positions_Short_All",
    ),
    "other_rept_spread_all": (
        "other_rept_positions_spread_all",
        "other_rept_positions_spread",
        "Other_Rept_Positions_Spread_All",
    ),
    "tot_rept_long_all": (
        "tot_rept_positions_long_all",
        "tot_rept_positions_long",
        "Tot_Rept_Positions_Long_All",
    ),
    "tot_rept_short_all": (
        "tot_rept_positions_short_all",
        "tot_rept_positions_short",
        "Tot_Rept_Positions_Short_All",
    ),
    "nonrept_long_all": (
        "nonrept_positions_long_all",
        "nonrept_positions_long",
        "NonRept_Positions_Long_All",
    ),
    "nonrept_short_all": (
        "nonrept_positions_short_all",
        "nonrept_positions_short",
        "NonRept_Positions_Short_All",
    ),
    "change_open_interest_all": (
        "change_in_open_interest_all",
        "change_open_interest_all",
        "Change_in_Open_Interest_All",
    ),
    "change_m_money_long_all": (
        "change_in_m_money_long_all",
        "change_m_money_long_all",
        "Change_in_M_Money_Long_All",
    ),
    "change_m_money_short_all": (
        "change_in_m_money_short_all",
        "change_m_money_short_all",
        "Change_in_M_Money_Short_All",
    ),
    "change_prod_merc_long_all": (
        "change_in_prod_merc_long_all",
        "change_prod_merc_long_all",
        "Change_in_Prod_Merc_Long_All",
    ),
    "change_prod_merc_short_all": (
        "change_in_prod_merc_short_all",
        "change_prod_merc_short_all",
        "Change_in_Prod_Merc_Short_All",
    ),
    "pct_oi_m_money_long_all": (
        "pct_of_oi_m_money_long_all",
        "pct_of_oi_m_money_long",
        "Pct_of_OI_M_Money_Long_All",
    ),
    "pct_oi_m_money_short_all": (
        "pct_of_oi_m_money_short_all",
        "pct_of_oi_m_money_short",
        "Pct_of_OI_M_Money_Short_All",
    ),
    "pct_oi_prod_merc_long_all": (
        "pct_of_oi_prod_merc_long_all",
        "pct_of_oi_prod_merc_long",
        "Pct_of_OI_Prod_Merc_Long_All",
    ),
    "pct_oi_prod_merc_short_all": (
        "pct_of_oi_prod_merc_short_all",
        "pct_of_oi_prod_merc_short",
        "Pct_of_OI_Prod_Merc_Short_All",
    ),
    "pct_oi_swap_long_all": (
        "pct_of_oi_swap_long_all",
        "pct_of_oi_swap_long",
        "Pct_of_OI_Swap_Long_All",
    ),
    "pct_oi_swap_short_all": (
        "pct_of_oi_swap_short_all",
        "pct_of_oi_swap_short",
        "Pct_of_OI_Swap_Short_All",
    ),
    "traders_total_all": (
        "traders_tot_all",
        "traders_total_all",
        "Traders_Tot_All",
    ),
    "contract_units": (
        "contract_units",
        "Contract_Units",
    ),
}

NUMERIC_COLUMNS = {
    col
    for col in NORMALIZED_COLUMNS
    if col
    not in {
        "as_of_date",
        "report_type",
        "source_name",
        "source_url",
        "market_and_exchange_names",
        "cftc_contract_market_code",
        "cftc_market_code",
        "cftc_commodity_code",
        "contract_units",
        "raw_record_json",
    }
}


@dataclass(frozen=True)
class Paths:
    out_dir: Path
    raw_dir: Path
    normalized_dir: Path
    metadata_dir: Path
    raw_json: Path
    normalized_csv: Path
    metadata_json: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download official CFTC Disaggregated Futures Only COT rows for COMEX Gold / code 088691."
    )
    parser.add_argument("--start-year", type=int, default=2009, help="First report year to request. Default: 2009")
    parser.add_argument("--end-year", type=int, default=None, help="Last report year to request. Default: current UTC year")
    parser.add_argument("--start-date", default=None, help="Explicit start date YYYY-MM-DD. Overrides --start-year lower bound.")
    parser.add_argument("--end-date", default=None, help="Explicit end date YYYY-MM-DD. Overrides --end-year upper bound.")
    parser.add_argument("--out-dir", default="data/cot/cftc", help="Output root directory. Default: data/cot/cftc")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Socrata page size. Default: 50000")
    parser.add_argument("--sleep-seconds", type=float, default=DEFAULT_SLEEP_SECONDS, help="Pause between pages. Default: 0.35")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per HTTP request. Default: 4")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds. Default: 60")
    parser.add_argument(
        "--contract-code",
        default=GOLD_CFTC_CONTRACT_MARKET_CODE,
        help="CFTC contract market code. Default locks to COMEX Gold 088691.",
    )
    parser.add_argument(
        "--allow-non-gold-code",
        action="store_true",
        help="Allow a contract code other than 088691. Intended only for manual diagnostics.",
    )
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit non-zero if no rows are downloaded.",
    )
    return parser.parse_args(argv)


def validate_date_string(value: str, name: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {name}: {value!r}; expected YYYY-MM-DD") from exc
    return value


def compute_date_bounds(args: argparse.Namespace) -> Tuple[str, str]:
    current_year = datetime.now(timezone.utc).year
    end_year = args.end_year or current_year
    if args.start_year < 2009:
        raise SystemExit("Disaggregated COT coverage starts in 2009; use --start-year 2009 or later.")
    if end_year < args.start_year:
        raise SystemExit("--end-year must be >= --start-year")

    start_date = args.start_date or f"{args.start_year:04d}-01-01"
    end_date = args.end_date or f"{end_year:04d}-12-31"
    start_date = validate_date_string(start_date, "--start-date")
    end_date = validate_date_string(end_date, "--end-date")
    if date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise SystemExit("End date must be >= start date")
    return start_date, end_date


def build_paths(out_dir_text: str) -> Paths:
    out_dir = Path(out_dir_text)
    raw_dir = out_dir / "raw" / "disaggregated_futures_only"
    normalized_dir = out_dir / "normalized"
    metadata_dir = out_dir / "metadata"
    return Paths(
        out_dir=out_dir,
        raw_dir=raw_dir,
        normalized_dir=normalized_dir,
        metadata_dir=metadata_dir,
        raw_json=raw_dir / f"cot_gold_{GOLD_CFTC_CONTRACT_MARKET_CODE}_raw.json",
        normalized_csv=normalized_dir / "cot_gold_weekly.csv",
        metadata_json=metadata_dir / "stage38b_cot_gold_download_metadata.json",
    )


def ensure_dirs(paths: Paths) -> None:
    paths.raw_dir.mkdir(parents=True, exist_ok=True)
    paths.normalized_dir.mkdir(parents=True, exist_ok=True)
    paths.metadata_dir.mkdir(parents=True, exist_ok=True)


def build_query_url(contract_code: str, start_date: str, end_date: str, limit: int, offset: int) -> str:
    # Socrata uses a Floating Timestamp for report_date_as_yyyy_mm_dd. The ISO
    # timestamp literals below keep the request date-bounded while contract_code
    # locks the query to GOLD / 088691.
    where = (
        f"cftc_contract_market_code='{contract_code}' "
        f"AND report_date_as_yyyy_mm_dd >= '{start_date}T00:00:00' "
        f"AND report_date_as_yyyy_mm_dd <= '{end_date}T23:59:59'"
    )
    params = {
        "$limit": str(limit),
        "$offset": str(offset),
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$where": where,
    }
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def http_get_json(url: str, timeout: int, retries: int) -> List[Dict[str, Any]]:
    last_error: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                payload = response.read().decode("utf-8")
            if status < 200 or status >= 300:
                raise RuntimeError(f"HTTP status {status}")
            data = json.loads(payload)
            if not isinstance(data, list):
                raise RuntimeError(f"Expected JSON list from Socrata, got {type(data).__name__}")
            return data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            sleep_for = min(2.0 * attempt, 8.0)
            print(f"WARN: request failed on attempt {attempt}/{retries}; retrying in {sleep_for:.1f}s: {exc}", file=sys.stderr)
            time.sleep(sleep_for)
    raise RuntimeError(f"Failed to fetch URL after {retries} attempts: {last_error}")


def fetch_all_rows(args: argparse.Namespace, start_date: str, end_date: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    all_rows: List[Dict[str, Any]] = []
    request_urls: List[str] = []
    offset = 0
    while True:
        url = build_query_url(args.contract_code, start_date, end_date, args.limit, offset)
        request_urls.append(url)
        print(f"Fetching CFTC COT page offset={offset} limit={args.limit}")
        page = http_get_json(url, timeout=args.timeout, retries=args.retries)
        all_rows.extend(page)
        print(f"  received_rows={len(page)} cumulative_rows={len(all_rows)}")
        if len(page) < args.limit:
            break
        offset += args.limit
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)
    return all_rows, request_urls


def lookup(record: Dict[str, Any], canonical_name: str) -> Any:
    for key in ALIASES.get(canonical_name, (canonical_name,)):
        if key in record:
            return record.get(key)
    return None


def normalize_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().strip('"').strip("'")
    # Socrata may return numeric-looking strings without leading zeros only in
    # unusual transforms. Preserve the six-character CFTC code if possible.
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    return text


def normalize_as_of_date(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return ""
    text = str(value).strip()
    # Socrata usually returns YYYY-MM-DDT00:00:00.000 or YYYY-MM-DDT00:00:00.
    if "T" in text:
        text = text.split("T", 1)[0]
    if "/" in text:
        # Historical CSV variants may be MM/DD/YYYY.
        try:
            return datetime.strptime(text, "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return text


def normalize_numeric(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    if text in {"", ".", "NA", "N/A", "nan", "NaN", "null", "None"}:
        return ""
    return text.replace(",", "")


def normalize_record(record: Dict[str, Any], source_url: str) -> Dict[str, str]:
    row: Dict[str, str] = {col: "" for col in NORMALIZED_COLUMNS}
    row["as_of_date"] = normalize_as_of_date(lookup(record, "as_of_date"))
    row["report_type"] = REPORT_TYPE
    row["source_name"] = SOURCE_NAME
    row["source_url"] = source_url
    row["market_and_exchange_names"] = str(lookup(record, "market_and_exchange_names") or "").strip()
    row["cftc_contract_market_code"] = normalize_code(lookup(record, "cftc_contract_market_code"))
    row["cftc_market_code"] = normalize_code(lookup(record, "cftc_market_code"))
    row["cftc_commodity_code"] = normalize_code(lookup(record, "cftc_commodity_code"))
    row["contract_units"] = str(lookup(record, "contract_units") or "").strip()

    for col in NUMERIC_COLUMNS:
        row[col] = normalize_numeric(lookup(record, col))

    row["raw_record_json"] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return row


def sort_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    return sorted(rows, key=lambda row: (row.get("as_of_date", ""), row.get("market_and_exchange_names", "")))


def validate_normalized_rows(rows: List[Dict[str, str]], contract_code: str) -> List[str]:
    warnings: List[str] = []
    if not rows:
        warnings.append("No normalized rows were produced.")
        return warnings

    bad_codes = sorted({row["cftc_contract_market_code"] for row in rows if row["cftc_contract_market_code"] != contract_code})
    if bad_codes:
        warnings.append(f"Unexpected CFTC contract codes present: {bad_codes}")

    non_gold_names = sorted(
        {
            row["market_and_exchange_names"]
            for row in rows
            if row["market_and_exchange_names"] and "GOLD" not in row["market_and_exchange_names"].upper()
        }
    )
    if non_gold_names:
        warnings.append(f"Rows with non-GOLD-looking market names present: {non_gold_names[:10]}")

    missing_dates = sum(1 for row in rows if not row["as_of_date"])
    if missing_dates:
        warnings.append(f"Rows missing as_of_date: {missing_dates}")

    missing_oi = sum(1 for row in rows if not row["open_interest_all"])
    if missing_oi:
        warnings.append(f"Rows missing open_interest_all: {missing_oi}")

    primary_keys = [(row["as_of_date"], row["report_type"], row["cftc_contract_market_code"]) for row in rows]
    duplicate_count = len(primary_keys) - len(set(primary_keys))
    if duplicate_count:
        warnings.append(f"Duplicate primary-key candidates detected: {duplicate_count}")

    return warnings


def write_raw_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, sort_keys=True)
        fh.write("\n")


def write_normalized_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_iso_dates_from_rows(rows: List[Dict[str, str]]) -> List[str]:
    dates = []
    for row in rows:
        value = row.get("as_of_date", "")
        if value:
            dates.append(value)
    return sorted(dates)


def summarize_null_counts(rows: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for col in NORMALIZED_COLUMNS:
        if col == "raw_record_json":
            continue
        counts[col] = sum(1 for row in rows if row.get(col, "") == "")
    return counts


def write_metadata(
    path: Path,
    args: argparse.Namespace,
    paths: Paths,
    start_date: str,
    end_date: str,
    request_urls: List[str],
    raw_rows: List[Dict[str, Any]],
    normalized_rows: List[Dict[str, str]],
    warnings: List[str],
) -> None:
    dates = parse_iso_dates_from_rows(normalized_rows)
    metadata = {
        "stage": "Stage38B",
        "artifact": "tools/stage38b_download_cftc_cot_gold.py",
        "status": "DOWNLOADED" if normalized_rows else "EMPTY",
        "generated_at_utc": utc_now_iso(),
        "source_name": SOURCE_NAME,
        "dataset_id": DATASET_ID,
        "base_url": BASE_URL,
        "request_url_first_page": request_urls[0] if request_urls else None,
        "request_page_count": len(request_urls),
        "contract_identity": {
            "market_name_expected": GOLD_MARKET_NAME,
            "cftc_contract_market_code": args.contract_code,
            "primary_gold_code_locked": args.contract_code == GOLD_CFTC_CONTRACT_MARKET_CODE,
        },
        "requested_date_range": {"start_date": start_date, "end_date": end_date},
        "row_count_raw": len(raw_rows),
        "row_count_normalized": len(normalized_rows),
        "min_as_of_date": dates[0] if dates else None,
        "max_as_of_date": dates[-1] if dates else None,
        "output_files": {
            "raw_json": str(paths.raw_json),
            "normalized_csv": str(paths.normalized_csv),
            "metadata_json": str(paths.metadata_json),
        },
        "null_counts": summarize_null_counts(normalized_rows),
        "warnings": warnings,
        "next_step": "Run app/stage38b_cot_gold_loader.py after it is created.",
        "scope_guard": {
            "stage39": "NO_GO",
            "ea": "NO_GO",
            "paper_live": "NO_GO",
            "live_order": "NO_GO",
            "trading_signal_generation": "OUT_OF_SCOPE",
        },
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.contract_code != GOLD_CFTC_CONTRACT_MARKET_CODE and not args.allow_non_gold_code:
        print(
            f"ERROR: Stage38B baseline is locked to GOLD code {GOLD_CFTC_CONTRACT_MARKET_CODE}. "
            "Use --allow-non-gold-code only for manual diagnostics.",
            file=sys.stderr,
        )
        return 2

    start_date, end_date = compute_date_bounds(args)
    paths = build_paths(args.out_dir)
    ensure_dirs(paths)

    print("Stage38B COT gold downloader")
    print(f"  source={SOURCE_NAME}")
    print(f"  dataset={DATASET_ID}")
    print(f"  contract_code={args.contract_code}")
    print(f"  date_range={start_date}..{end_date}")

    try:
        raw_rows, request_urls = fetch_all_rows(args, start_date, end_date)
    except Exception as exc:
        print(f"ERROR: CFTC download failed: {exc}", file=sys.stderr)
        return 1

    source_url = request_urls[0] if request_urls else BASE_URL
    normalized_rows = sort_rows(normalize_record(record, source_url) for record in raw_rows)
    warnings = validate_normalized_rows(normalized_rows, args.contract_code)

    write_raw_json(paths.raw_json, raw_rows)
    write_normalized_csv(paths.normalized_csv, normalized_rows)
    write_metadata(paths.metadata_json, args, paths, start_date, end_date, request_urls, raw_rows, normalized_rows, warnings)

    print("\nOutputs written:")
    print(f"  raw_json={paths.raw_json}")
    print(f"  normalized_csv={paths.normalized_csv}")
    print(f"  metadata_json={paths.metadata_json}")
    print(f"  raw_rows={len(raw_rows)} normalized_rows={len(normalized_rows)}")

    dates = parse_iso_dates_from_rows(normalized_rows)
    if dates:
        print(f"  as_of_date_range={dates[0]}..{dates[-1]}")

    if warnings:
        print("\nWARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
    elif normalized_rows:
        print("\nBasic download sanity: PASS")

    if args.fail_on_empty and not normalized_rows:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
