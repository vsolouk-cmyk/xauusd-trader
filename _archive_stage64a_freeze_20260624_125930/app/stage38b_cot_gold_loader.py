#!/usr/bin/env python3
"""
Stage38B COT Gold Loader

Purpose:
  Load the Stage38B CFTC COT gold artifact into the local SQLite research store.

Scope guard:
  - Read-only research data ingestion.
  - No Stage39.
  - No EA.
  - No paper/live orders.
  - No trading-signal generation.

Expected inputs:
  1) GitHub Actions artifact zip, e.g.
       stage38b-cot-gold-cftc-1.zip
     containing:
       normalized/cot_gold_weekly.csv
       metadata/stage38b_cot_gold_download_metadata.json
  OR
  2) Direct CSV path:
       data/cot/cftc/normalized/cot_gold_weekly.csv

Default DB:
  data/local/xauusd_local_store.sqlite

Tables created/replaced:
  cot_gold_weekly
  cot_gold_features
  cot_gold_ingest_audit
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

STAGE = "Stage38B"
REPORT_TYPE_EXPECTED = "DISAGGREGATED_FUTURES_ONLY"
MARKET_NAME_EXPECTED = "GOLD - COMMODITY EXCHANGE INC."
CONTRACT_CODE_EXPECTED = "088691"
COMMODITY_CODE_ACCEPTED = {"088", "000088"}
CSV_IN_ZIP = "normalized/cot_gold_weekly.csv"
METADATA_IN_ZIP = "metadata/stage38b_cot_gold_download_metadata.json"
DEFAULT_DB_PATH = "data/local/xauusd_local_store.sqlite"
DEFAULT_REPORTS_DIR = "data/reports/stage38b_cot_audit"

INTEGER_COLUMNS = [
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
    "traders_total_all",
]

REAL_COLUMNS = [
    "pct_oi_m_money_long_all",
    "pct_oi_m_money_short_all",
    "pct_oi_prod_merc_long_all",
    "pct_oi_prod_merc_short_all",
    "pct_oi_swap_long_all",
    "pct_oi_swap_short_all",
]

TEXT_COLUMNS = [
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
]

WEEKLY_TABLE_COLUMNS = [
    "as_of_date",
    "available_from_utc",
    "report_type",
    "source_name",
    "source_url",
    "market_and_exchange_names",
    "cftc_contract_market_code",
    "cftc_market_code",
    "cftc_commodity_code",
    *INTEGER_COLUMNS,
    *REAL_COLUMNS,
    "contract_units",
    "raw_record_json",
    "ingest_utc",
]

FEATURE_TABLE_COLUMNS = [
    "as_of_date",
    "available_from_utc",
    "open_interest_all",
    "open_interest_change_1w",
    "open_interest_zscore_156w",
    "open_interest_pct_rank_156w",
    "m_money_long_all",
    "m_money_short_all",
    "m_money_spread_all",
    "m_money_net_all",
    "m_money_net_pct_oi",
    "m_money_net_change_1w",
    "m_money_net_change_4w",
    "m_money_net_change_13w",
    "m_money_net_change_26w",
    "m_money_net_zscore_156w",
    "m_money_net_pct_rank_156w",
    "m_money_gross_all",
    "m_money_long_short_ratio",
    "prod_merc_long_all",
    "prod_merc_short_all",
    "prod_merc_net_all",
    "prod_merc_net_pct_oi",
    "prod_merc_net_change_1w",
    "prod_merc_net_change_4w",
    "swap_long_all",
    "swap_short_all",
    "swap_spread_all",
    "swap_net_all",
    "swap_net_pct_oi",
    "other_rept_long_all",
    "other_rept_short_all",
    "other_rept_spread_all",
    "other_rept_net_all",
    "other_rept_net_pct_oi",
    "nonrept_long_all",
    "nonrept_short_all",
    "nonrept_net_all",
    "nonrept_net_pct_oi",
    "crowding_mm_long_minus_pm_short_pct_oi",
    "commercial_hedging_pressure_pct_oi",
    "lookback_rows_156w",
    "ingest_utc",
]


@dataclass
class InputPayload:
    csv_rows: List[Dict[str, str]]
    metadata: Dict[str, Any]
    input_kind: str
    input_path: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Stage38B CFTC COT gold data into SQLite.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to GitHub artifact zip or normalized cot_gold_weekly.csv.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB path. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--reports-dir",
        default=DEFAULT_REPORTS_DIR,
        help=f"Audit reports directory. Default: {DEFAULT_REPORTS_DIR}",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        default=True,
        help="Replace Stage38B COT tables before loading. Default: true.",
    )
    parser.add_argument(
        "--no-replace",
        action="store_false",
        dest="replace",
        help="Do not drop existing Stage38B COT tables before loading.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero if audit warnings are produced.",
    )
    return parser.parse_args(argv)


def read_payload(input_path: str) -> InputPayload:
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = p.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(p) as z:
            names = set(z.namelist())
            if CSV_IN_ZIP not in names:
                raise FileNotFoundError(f"Artifact zip is missing {CSV_IN_ZIP}")
            csv_text = z.read(CSV_IN_ZIP).decode("utf-8-sig")
            metadata: Dict[str, Any] = {}
            if METADATA_IN_ZIP in names:
                metadata = json.loads(z.read(METADATA_IN_ZIP).decode("utf-8"))
            rows = list(csv.DictReader(io.StringIO(csv_text)))
            return InputPayload(rows, metadata, "zip", str(p))

    if suffix == ".csv":
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        return InputPayload(rows, {}, "csv", str(p))

    raise ValueError(f"Unsupported input type: {input_path}. Use .zip or .csv")


def to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date_yyyy_mm_dd(value: Any) -> date:
    s = str(value).strip()
    if not s:
        raise ValueError("Empty date")
    if "T" in s:
        s = s.split("T", 1)[0]
    return date.fromisoformat(s)


def compute_available_from_utc(as_of: date) -> str:
    """COT reports are normally released Friday 15:30 America/New_York after Tuesday as-of date."""
    days_until_friday = (4 - as_of.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    release_day = as_of + timedelta(days=days_until_friday)
    if ZoneInfo is None:
        # Conservative fallback: 21:30 UTC covers 15:30 ET in both EST and EDT with extra delay in EDT.
        dt_utc = datetime.combine(release_day, time(21, 30), tzinfo=timezone.utc)
    else:
        dt_local = datetime.combine(release_day, time(15, 30), tzinfo=ZoneInfo("America/New_York"))
        dt_utc = dt_local.astimezone(timezone.utc)
    return dt_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def rolling_zscore(values: List[Optional[float]], idx: int, lookback: int) -> Optional[float]:
    current = values[idx]
    if current is None:
        return None
    start = max(0, idx - lookback + 1)
    window = [v for v in values[start : idx + 1] if v is not None]
    if len(window) < 20:
        return None
    mean = sum(window) / len(window)
    var = sum((v - mean) ** 2 for v in window) / len(window)
    sd = math.sqrt(var)
    if sd == 0:
        return None
    return (current - mean) / sd


def rolling_pct_rank(values: List[Optional[float]], idx: int, lookback: int) -> Optional[float]:
    current = values[idx]
    if current is None:
        return None
    start = max(0, idx - lookback + 1)
    window = [v for v in values[start : idx + 1] if v is not None]
    if len(window) < 20:
        return None
    less_or_equal = sum(1 for v in window if v <= current)
    return less_or_equal / len(window)


def lag_change(values: List[Optional[float]], idx: int, lag: int) -> Optional[float]:
    current = values[idx]
    if current is None or idx - lag < 0:
        return None
    prior = values[idx - lag]
    if prior is None:
        return None
    return current - prior


def validate_and_normalize_rows(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    warnings: List[str] = []
    notes: List[str] = []
    if not rows:
        raise ValueError("Input CSV contains no rows")

    required = set(TEXT_COLUMNS + [c for c in INTEGER_COLUMNS if c not in {"change_prod_merc_long_all", "change_prod_merc_short_all"}] + REAL_COLUMNS)
    missing = sorted(required - set(rows[0].keys()))
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {missing}")

    normalized: List[Dict[str, Any]] = []
    seen_dates = set()
    ingest_utc = utc_now_iso()

    for raw in rows:
        as_of = parse_date_yyyy_mm_dd(raw.get("as_of_date"))
        as_of_str = as_of.isoformat()
        if as_of_str in seen_dates:
            warnings.append(f"duplicate_as_of_date:{as_of_str}")
        seen_dates.add(as_of_str)

        rec: Dict[str, Any] = {"as_of_date": as_of_str, "available_from_utc": compute_available_from_utc(as_of)}
        for col in TEXT_COLUMNS:
            if col == "as_of_date":
                continue
            rec[col] = (raw.get(col) or "").strip()
        for col in INTEGER_COLUMNS:
            rec[col] = to_int(raw.get(col))
        for col in REAL_COLUMNS:
            rec[col] = to_float(raw.get(col))
        rec["ingest_utc"] = ingest_utc
        normalized.append(rec)

    normalized.sort(key=lambda r: r["as_of_date"])

    market_names = {r.get("market_and_exchange_names") for r in normalized}
    contract_codes = {r.get("cftc_contract_market_code") for r in normalized}
    report_types = {r.get("report_type") for r in normalized}
    commodity_codes = {str(r.get("cftc_commodity_code", "")).lstrip("0") for r in normalized}

    if market_names != {MARKET_NAME_EXPECTED}:
        warnings.append(f"unexpected_market_names:{sorted(market_names)}")
    if contract_codes != {CONTRACT_CODE_EXPECTED}:
        warnings.append(f"unexpected_contract_codes:{sorted(contract_codes)}")
    if report_types != {REPORT_TYPE_EXPECTED}:
        warnings.append(f"unexpected_report_types:{sorted(report_types)}")
    if not commodity_codes.issubset({"88"}):
        warnings.append(f"unexpected_commodity_codes:{sorted(commodity_codes)}")

    shifted_gap_count = 0
    for i in range(1, len(normalized)):
        d0 = parse_date_yyyy_mm_dd(normalized[i - 1]["as_of_date"])
        d1 = parse_date_yyyy_mm_dd(normalized[i]["as_of_date"])
        gap_days = (d1 - d0).days
        if gap_days in {6, 8}:
            shifted_gap_count += 1
        elif gap_days not in {7, 14, 21, 28, 35, 42, 49, 56, 63}:
            warnings.append(f"unusual_date_gap:{normalized[i - 1]['as_of_date']}->{normalized[i]['as_of_date']}:{gap_days}d")
    if shifted_gap_count:
        notes.append(f"holiday_or_special_report_date_shifts_6_or_8_day_gaps:{shifted_gap_count}")

    for col in ["open_interest_all", "m_money_long_all", "m_money_short_all", "prod_merc_long_all", "prod_merc_short_all"]:
        null_count = sum(1 for r in normalized if r.get(col) is None)
        if null_count:
            warnings.append(f"null_required_numeric:{col}:{null_count}")

    # Recompute missing producer/merchant changes from positions.
    pm_long_values = [r.get("prod_merc_long_all") for r in normalized]
    pm_short_values = [r.get("prod_merc_short_all") for r in normalized]
    filled_pm_long = 0
    filled_pm_short = 0
    for i, rec in enumerate(normalized):
        if rec.get("change_prod_merc_long_all") is None:
            rec["change_prod_merc_long_all"] = int(lag_change(pm_long_values, i, 1)) if lag_change(pm_long_values, i, 1) is not None else None
            if rec.get("change_prod_merc_long_all") is not None:
                filled_pm_long += 1
        if rec.get("change_prod_merc_short_all") is None:
            rec["change_prod_merc_short_all"] = int(lag_change(pm_short_values, i, 1)) if lag_change(pm_short_values, i, 1) is not None else None
            if rec.get("change_prod_merc_short_all") is not None:
                filled_pm_short += 1
    if filled_pm_long or filled_pm_short:
        notes.append(f"recomputed_missing_prod_merc_changes:long={filled_pm_long},short={filled_pm_short}")

    return normalized, warnings, notes


def build_features(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ingest_utc = utc_now_iso()
    oi_values = [float(r["open_interest_all"]) if r.get("open_interest_all") is not None else None for r in rows]
    mm_net_values: List[Optional[float]] = []
    pm_net_values: List[Optional[float]] = []

    for r in rows:
        mm_long = r.get("m_money_long_all")
        mm_short = r.get("m_money_short_all")
        pm_long = r.get("prod_merc_long_all")
        pm_short = r.get("prod_merc_short_all")
        mm_net_values.append(float(mm_long - mm_short) if mm_long is not None and mm_short is not None else None)
        pm_net_values.append(float(pm_long - pm_short) if pm_long is not None and pm_short is not None else None)

    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        oi = r.get("open_interest_all")
        mm_long = r.get("m_money_long_all")
        mm_short = r.get("m_money_short_all")
        mm_spread = r.get("m_money_spread_all")
        pm_long = r.get("prod_merc_long_all")
        pm_short = r.get("prod_merc_short_all")
        swap_long = r.get("swap_long_all")
        swap_short = r.get("swap_short_all")
        swap_spread = r.get("swap_spread_all")
        other_long = r.get("other_rept_long_all")
        other_short = r.get("other_rept_short_all")
        other_spread = r.get("other_rept_spread_all")
        nonrept_long = r.get("nonrept_long_all")
        nonrept_short = r.get("nonrept_short_all")

        mm_net = mm_net_values[i]
        pm_net = pm_net_values[i]
        swap_net = float(swap_long - swap_short) if swap_long is not None and swap_short is not None else None
        other_net = float(other_long - other_short) if other_long is not None and other_short is not None else None
        nonrept_net = float(nonrept_long - nonrept_short) if nonrept_long is not None and nonrept_short is not None else None

        pct_mm_long = r.get("pct_oi_m_money_long_all")
        pct_mm_short = r.get("pct_oi_m_money_short_all")
        pct_pm_long = r.get("pct_oi_prod_merc_long_all")
        pct_pm_short = r.get("pct_oi_prod_merc_short_all")
        pct_swap_long = r.get("pct_oi_swap_long_all")
        pct_swap_short = r.get("pct_oi_swap_short_all")

        lookback_start = max(0, i - 156 + 1)
        lookback_rows = i - lookback_start + 1

        rec: Dict[str, Any] = {
            "as_of_date": r["as_of_date"],
            "available_from_utc": r["available_from_utc"],
            "open_interest_all": oi,
            "open_interest_change_1w": lag_change(oi_values, i, 1),
            "open_interest_zscore_156w": rolling_zscore(oi_values, i, 156),
            "open_interest_pct_rank_156w": rolling_pct_rank(oi_values, i, 156),
            "m_money_long_all": mm_long,
            "m_money_short_all": mm_short,
            "m_money_spread_all": mm_spread,
            "m_money_net_all": mm_net,
            "m_money_net_pct_oi": safe_div(mm_net, float(oi) if oi is not None else None),
            "m_money_net_change_1w": lag_change(mm_net_values, i, 1),
            "m_money_net_change_4w": lag_change(mm_net_values, i, 4),
            "m_money_net_change_13w": lag_change(mm_net_values, i, 13),
            "m_money_net_change_26w": lag_change(mm_net_values, i, 26),
            "m_money_net_zscore_156w": rolling_zscore(mm_net_values, i, 156),
            "m_money_net_pct_rank_156w": rolling_pct_rank(mm_net_values, i, 156),
            "m_money_gross_all": (mm_long + mm_short) if mm_long is not None and mm_short is not None else None,
            "m_money_long_short_ratio": safe_div(float(mm_long) if mm_long is not None else None, float(mm_short) if mm_short is not None else None),
            "prod_merc_long_all": pm_long,
            "prod_merc_short_all": pm_short,
            "prod_merc_net_all": pm_net,
            "prod_merc_net_pct_oi": safe_div(pm_net, float(oi) if oi is not None else None),
            "prod_merc_net_change_1w": lag_change(pm_net_values, i, 1),
            "prod_merc_net_change_4w": lag_change(pm_net_values, i, 4),
            "swap_long_all": swap_long,
            "swap_short_all": swap_short,
            "swap_spread_all": swap_spread,
            "swap_net_all": swap_net,
            "swap_net_pct_oi": safe_div(swap_net, float(oi) if oi is not None else None),
            "other_rept_long_all": other_long,
            "other_rept_short_all": other_short,
            "other_rept_spread_all": other_spread,
            "other_rept_net_all": other_net,
            "other_rept_net_pct_oi": safe_div(other_net, float(oi) if oi is not None else None),
            "nonrept_long_all": nonrept_long,
            "nonrept_short_all": nonrept_short,
            "nonrept_net_all": nonrept_net,
            "nonrept_net_pct_oi": safe_div(nonrept_net, float(oi) if oi is not None else None),
            "crowding_mm_long_minus_pm_short_pct_oi": (pct_mm_long - pct_pm_short) if pct_mm_long is not None and pct_pm_short is not None else None,
            "commercial_hedging_pressure_pct_oi": (pct_pm_short - pct_pm_long) if pct_pm_short is not None and pct_pm_long is not None else None,
            "lookback_rows_156w": lookback_rows,
            "ingest_utc": ingest_utc,
        }
        out.append(rec)
    return out


def create_tables(conn: sqlite3.Connection, replace: bool) -> None:
    cur = conn.cursor()
    if replace:
        cur.execute("DROP TABLE IF EXISTS cot_gold_features")
        cur.execute("DROP TABLE IF EXISTS cot_gold_weekly")
        cur.execute("DROP TABLE IF EXISTS cot_gold_ingest_audit")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cot_gold_weekly (
            as_of_date TEXT PRIMARY KEY,
            available_from_utc TEXT NOT NULL,
            report_type TEXT NOT NULL,
            source_name TEXT,
            source_url TEXT,
            market_and_exchange_names TEXT NOT NULL,
            cftc_contract_market_code TEXT NOT NULL,
            cftc_market_code TEXT,
            cftc_commodity_code TEXT,
            open_interest_all INTEGER,
            prod_merc_long_all INTEGER,
            prod_merc_short_all INTEGER,
            swap_long_all INTEGER,
            swap_short_all INTEGER,
            swap_spread_all INTEGER,
            m_money_long_all INTEGER,
            m_money_short_all INTEGER,
            m_money_spread_all INTEGER,
            other_rept_long_all INTEGER,
            other_rept_short_all INTEGER,
            other_rept_spread_all INTEGER,
            tot_rept_long_all INTEGER,
            tot_rept_short_all INTEGER,
            nonrept_long_all INTEGER,
            nonrept_short_all INTEGER,
            change_open_interest_all INTEGER,
            change_m_money_long_all INTEGER,
            change_m_money_short_all INTEGER,
            change_prod_merc_long_all INTEGER,
            change_prod_merc_short_all INTEGER,
            traders_total_all INTEGER,
            pct_oi_m_money_long_all REAL,
            pct_oi_m_money_short_all REAL,
            pct_oi_prod_merc_long_all REAL,
            pct_oi_prod_merc_short_all REAL,
            pct_oi_swap_long_all REAL,
            pct_oi_swap_short_all REAL,
            contract_units TEXT,
            raw_record_json TEXT,
            ingest_utc TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cot_gold_features (
            as_of_date TEXT PRIMARY KEY,
            available_from_utc TEXT NOT NULL,
            open_interest_all INTEGER,
            open_interest_change_1w REAL,
            open_interest_zscore_156w REAL,
            open_interest_pct_rank_156w REAL,
            m_money_long_all INTEGER,
            m_money_short_all INTEGER,
            m_money_spread_all INTEGER,
            m_money_net_all REAL,
            m_money_net_pct_oi REAL,
            m_money_net_change_1w REAL,
            m_money_net_change_4w REAL,
            m_money_net_change_13w REAL,
            m_money_net_change_26w REAL,
            m_money_net_zscore_156w REAL,
            m_money_net_pct_rank_156w REAL,
            m_money_gross_all INTEGER,
            m_money_long_short_ratio REAL,
            prod_merc_long_all INTEGER,
            prod_merc_short_all INTEGER,
            prod_merc_net_all REAL,
            prod_merc_net_pct_oi REAL,
            prod_merc_net_change_1w REAL,
            prod_merc_net_change_4w REAL,
            swap_long_all INTEGER,
            swap_short_all INTEGER,
            swap_spread_all INTEGER,
            swap_net_all REAL,
            swap_net_pct_oi REAL,
            other_rept_long_all INTEGER,
            other_rept_short_all INTEGER,
            other_rept_spread_all INTEGER,
            other_rept_net_all REAL,
            other_rept_net_pct_oi REAL,
            nonrept_long_all INTEGER,
            nonrept_short_all INTEGER,
            nonrept_net_all REAL,
            nonrept_net_pct_oi REAL,
            crowding_mm_long_minus_pm_short_pct_oi REAL,
            commercial_hedging_pressure_pct_oi REAL,
            lookback_rows_156w INTEGER,
            ingest_utc TEXT NOT NULL,
            FOREIGN KEY(as_of_date) REFERENCES cot_gold_weekly(as_of_date)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cot_gold_ingest_audit (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            input_kind TEXT NOT NULL,
            input_path TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            feature_row_count INTEGER NOT NULL,
            min_as_of_date TEXT,
            max_as_of_date TEXT,
            min_available_from_utc TEXT,
            max_available_from_utc TEXT,
            warning_count INTEGER NOT NULL,
            warnings_json TEXT NOT NULL,
            note_count INTEGER NOT NULL,
            notes_json TEXT NOT NULL,
            metadata_json TEXT,
            generated_at_utc TEXT NOT NULL,
            scope_guard_json TEXT NOT NULL
        )
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_cot_gold_weekly_available_from ON cot_gold_weekly(available_from_utc)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cot_gold_features_available_from ON cot_gold_features(available_from_utc)")
    conn.commit()


def insert_rows(conn: sqlite3.Connection, table: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
    placeholders = ",".join(["?"] * len(columns))
    col_sql = ",".join(columns)
    sql = f"INSERT OR REPLACE INTO {table} ({col_sql}) VALUES ({placeholders})"
    values = [[r.get(c) for c in columns] for r in rows]
    conn.executemany(sql, values)


def write_audit(
    conn: sqlite3.Connection,
    reports_dir: str,
    payload: InputPayload,
    rows: List[Dict[str, Any]],
    features: List[Dict[str, Any]],
    warnings: List[str],
    notes: List[str],
) -> Dict[str, Any]:
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    scope_guard = {
        "stage39": "NO_GO",
        "ea": "NO_GO",
        "paper_live": "NO_GO",
        "live_order": "NO_GO",
        "trading_signal_generation": "OUT_OF_SCOPE",
    }
    audit = {
        "stage": STAGE,
        "status": "LOADED_WITH_WARNINGS" if warnings else "LOADED",
        "input_kind": payload.input_kind,
        "input_path": payload.input_path,
        "row_count": len(rows),
        "feature_row_count": len(features),
        "min_as_of_date": rows[0]["as_of_date"] if rows else None,
        "max_as_of_date": rows[-1]["as_of_date"] if rows else None,
        "min_available_from_utc": rows[0]["available_from_utc"] if rows else None,
        "max_available_from_utc": rows[-1]["available_from_utc"] if rows else None,
        "warning_count": len(warnings),
        "warnings": warnings,
        "note_count": len(notes),
        "notes": notes,
        "metadata": payload.metadata,
        "generated_at_utc": utc_now_iso(),
        "scope_guard": scope_guard,
        "tables": ["cot_gold_weekly", "cot_gold_features", "cot_gold_ingest_audit"],
        "next_step": "Join cot_gold_features to H1 bars by timestamp >= available_from_utc for Stage38B/T3 read-only feature audit.",
    }

    audit_json_path = Path(reports_dir) / "stage38b_cot_gold_loader_audit.json"
    audit_md_path = Path(reports_dir) / "stage38b_cot_gold_loader_audit.md"
    audit_json_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# Stage38B COT Gold Loader Audit",
        "",
        f"Generated UTC: `{audit['generated_at_utc']}`",
        "",
        "## Scope Guard",
        "",
        "```text",
        "Stage39 = NO_GO",
        "EA = NO_GO",
        "paper_live = NO_GO",
        "live_order = NO_GO",
        "trading_signal_generation = OUT_OF_SCOPE",
        "```",
        "",
        "## Load Summary",
        "",
        f"- input_kind: `{audit['input_kind']}`",
        f"- input_path: `{audit['input_path']}`",
        f"- weekly rows: `{audit['row_count']}`",
        f"- feature rows: `{audit['feature_row_count']}`",
        f"- min_as_of_date: `{audit['min_as_of_date']}`",
        f"- max_as_of_date: `{audit['max_as_of_date']}`",
        f"- min_available_from_utc: `{audit['min_available_from_utc']}`",
        f"- max_available_from_utc: `{audit['max_available_from_utc']}`",
        "",
        "## Tables",
        "",
        "```text",
        "cot_gold_weekly",
        "cot_gold_features",
        "cot_gold_ingest_audit",
        "```",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        md_lines.extend([f"- `{w}`" for w in warnings])
    else:
        md_lines.append("No warnings.")
    md_lines.extend([
        "",
        "## Notes",
        "",
    ])
    if notes:
        md_lines.extend([f"- `{n}`" for n in notes])
    else:
        md_lines.append("No notes.")
    md_lines.extend([
        "",
        "## Next Step",
        "",
        "Use `cot_gold_features.available_from_utc` for anti-lookahead joins to H1 bars.",
        "Do not join on `as_of_date` directly for trading/research features.",
    ])
    audit_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    conn.execute("DELETE FROM cot_gold_ingest_audit WHERE id = 1")
    conn.execute(
        """
        INSERT INTO cot_gold_ingest_audit (
            id, stage, status, input_kind, input_path, row_count, feature_row_count,
            min_as_of_date, max_as_of_date, min_available_from_utc, max_available_from_utc,
            warning_count, warnings_json, note_count, notes_json, metadata_json, generated_at_utc, scope_guard_json
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit["stage"],
            audit["status"],
            audit["input_kind"],
            audit["input_path"],
            audit["row_count"],
            audit["feature_row_count"],
            audit["min_as_of_date"],
            audit["max_as_of_date"],
            audit["min_available_from_utc"],
            audit["max_available_from_utc"],
            audit["warning_count"],
            json.dumps(warnings, ensure_ascii=False),
            len(notes),
            json.dumps(notes, ensure_ascii=False),
            json.dumps(payload.metadata, ensure_ascii=False),
            audit["generated_at_utc"],
            json.dumps(scope_guard, ensure_ascii=False),
        ),
    )
    conn.commit()
    return audit


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    payload = read_payload(args.input)
    rows, warnings, notes = validate_and_normalize_rows(payload.csv_rows)
    features = build_features(rows)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        create_tables(conn, args.replace)
        insert_rows(conn, "cot_gold_weekly", WEEKLY_TABLE_COLUMNS, rows)
        insert_rows(conn, "cot_gold_features", FEATURE_TABLE_COLUMNS, features)
        audit = write_audit(conn, args.reports_dir, payload, rows, features, warnings, notes)

    print(json.dumps({
        "stage": STAGE,
        "status": audit["status"],
        "db": str(db_path),
        "row_count": audit["row_count"],
        "feature_row_count": audit["feature_row_count"],
        "min_as_of_date": audit["min_as_of_date"],
        "max_as_of_date": audit["max_as_of_date"],
        "warning_count": audit["warning_count"],
        "note_count": audit["note_count"],
        "reports_dir": args.reports_dir,
        "scope_guard": audit["scope_guard"],
    }, indent=2, ensure_ascii=False))

    if args.fail_on_warning and warnings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
