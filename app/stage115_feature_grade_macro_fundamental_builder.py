#!/usr/bin/env python3
"""
Stage115_FEATURE_GRADE_MACRO_FUNDAMENTAL_BUILDER

Build feature-grade macro/fundamental/event inputs from Stage114B normalized outputs.

This stage is infrastructure / research-data preparation only:
- no broker connection
- no MT5 / EA change
- no signal promotion
- no paper/live order

Main outputs:
- daily macro feature panel from FRED + DXY fallback logic
- COT gold weekly positioning features parsed from CFTC zip text files
- event calendar feature shells from FRED/FOMC/Treasury/BLS/BEA/Census
- WGC/SPDR flow/reserve feature candidate extracts
- feature inventory and quality flags for the next discovery stage
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import statistics
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

STAGE = "Stage115_FEATURE_GRADE_MACRO_FUNDAMENTAL_BUILDER"
STATUS = "STAGE115_COMPLETE_FEATURE_GRADE_DATASET_READY_NO_PROMOTION"
DECISION = "STAGE115_FEATURE_GRADE_MACRO_FUNDAMENTAL_DATA_READY_NO_ORDER"
CLASSIFICATION = "FEATURE_DATA_BUILDER_ONLY_NO_ORDER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE115",
    "NO_EA_CHANGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

NORMALIZED_REL = "data/fundamental_event_inbox/normalized"
FEATURE_REL = "data/fundamental_event_inbox/features"
REPORT_REL = "reports/stage115_feature_grade_macro_fundamental_builder"
CLASSIFICATION_REL = "reports/stage114b_classification_and_macro_event_hotfix/stage114b_corrected_file_classification.csv"

FRED_DESCRIPTIONS = {
    "DFII10": "10Y real yield / TIPS constant maturity",
    "DGS10": "10Y nominal Treasury yield",
    "DGS2": "2Y nominal Treasury yield",
    "T10YIE": "10Y breakeven inflation",
    "T5YIE": "5Y breakeven inflation",
    "DFF": "effective federal funds rate",
    "WALCL": "Fed total assets",
    "VIXCLS": "VIX close",
    "DTWEXBGS": "nominal broad U.S. dollar index",
    "BAMLH0A0HYM2": "HY OAS credit spread",
}

BLS_DESCRIPTIONS = {
    "CUSR0000SA0": "CPI-U all items SA",
    "CUSR0000SA0L1E": "Core CPI-U SA",
    "CES0000000001": "Total nonfarm payroll employment",
    "LNS14000000": "Unemployment rate",
    "LNS11300000": "Labor force participation rate",
}


def configure_csv_field_size_limit() -> int:
    """Raise Python csv field-size limit for shell-normalized JSON payload columns.

    Stage114B shell outputs can contain full BEA/Census JSON payloads in a single
    CSV field. The csv module default limit is commonly 131072 bytes, which is
    too small for those rows. Use the largest platform-supported limit and fall
    back safely if C long overflows.
    """
    limit = sys.maxsize
    while limit > 131072:
        try:
            csv.field_size_limit(limit)
            return int(limit)
        except OverflowError:
            limit = int(limit / 10)
    csv.field_size_limit(131072)
    return 131072


CSV_FIELD_SIZE_LIMIT = configure_csv_field_size_limit()

# Column aliases for flexible CFTC disaggregated file parsing.
COT_ALIASES = {
    "market": ["market_and_exchange_names", "market_and_exchange_name", "market_and_exchange"],
    "date": ["report_date_as_yyyy_mm_dd", "report_date_as_yyyy-mm-dd", "report_date", "as_of_date_in_form_yyyy_mm_dd"],
    "open_interest": ["open_interest_all", "open_interest"],
    "mm_long": ["m_money_positions_long_all", "managed_money_positions_long_all", "money_manager_positions_long_all"],
    "mm_short": ["m_money_positions_short_all", "managed_money_positions_short_all", "money_manager_positions_short_all"],
    "mm_spread": ["m_money_positions_spread_all", "managed_money_positions_spread_all", "money_manager_positions_spread_all"],
    "prod_long": ["prod_merc_positions_long_all", "producer_merchant_processor_user_positions_long_all"],
    "prod_short": ["prod_merc_positions_short_all", "producer_merchant_processor_user_positions_short_all"],
    "swap_long": ["swap_positions_long_all", "swap_dealer_positions_long_all"],
    "swap_short": ["swap_positions_short_all", "swap_dealer_positions_short_all"],
    "other_long": ["other_rept_positions_long_all", "other_reportables_positions_long_all"],
    "other_short": ["other_rept_positions_short_all", "other_reportables_positions_short_all"],
    "nonrep_long": ["nonrept_positions_long_all", "nonreportable_positions_long_all"],
    "nonrep_short": ["nonrept_positions_short_all", "nonreportable_positions_short_all"],
}

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in {".", "NA", "N/A", "nan", "NaN", "null", "None", "-", "--"}:
        return None
    try:
        x = float(s)
        if math.isfinite(x):
            return x
        return None
    except Exception:
        return None


def parse_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    # ISO-like date first.
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            return None
    # Compact yyyymmdd.
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            return None
    # Excel serial as number.
    x = safe_float(s)
    if x is not None and 20000 <= x <= 70000:
        try:
            # Excel Windows epoch; openpyxl does this too, but avoid dependency here.
            base = dt.date(1899, 12, 30)
            return (base + dt.timedelta(days=int(x))).isoformat()
        except Exception:
            pass
    # Month name date, including ranges like June 17-18, 2025 -> take first day.
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:[-–]\d{1,2})?,\s*(\d{4})", s)
    if m:
        mon = MONTHS.get(m.group(1).lower().replace(".", ""))
        if mon:
            try:
                return dt.date(int(m.group(3)), mon, int(m.group(2))).isoformat()
            except Exception:
                return None
    # Year-month only.
    m = re.match(r"^(\d{4})[-/](\d{1,2})$", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), 1).isoformat()
        except Exception:
            return None
    return None


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    last_err: Optional[Exception] = None
    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                sample = f.read(8192)
                if not sample:
                    return []
                f.seek(0)
                # Most project-generated files are comma-delimited. Avoid csv.Sniffer here
                # because one-column empty-header files can trigger bad delimiter choices.
                return list(csv.DictReader(f))
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"could not read CSV {path}: {last_err}")

def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        fieldnames = keys or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def write_json(path: Path, data: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def norm_col(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")


def find_col(columns: Sequence[str], aliases: Sequence[str]) -> Optional[str]:
    normalized = {norm_col(c): c for c in columns}
    for alias in aliases:
        n = norm_col(alias)
        if n in normalized:
            return normalized[n]
    for c in columns:
        nc = norm_col(c)
        for alias in aliases:
            if norm_col(alias) in nc:
                return c
    return None


def rolling_z(values: Sequence[Optional[float]], window: int = 52, min_periods: int = 20) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    history: List[float] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        sample = history[-window:]
        if len(sample) >= min_periods:
            try:
                mu = statistics.mean(sample)
                sd = statistics.pstdev(sample)
                out.append((v - mu) / sd if sd and math.isfinite(sd) else None)
            except Exception:
                out.append(None)
        else:
            out.append(None)
        history.append(v)
    return out


def lag_diff(values: Sequence[Optional[float]], lag: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i, v in enumerate(values):
        if i < lag or v is None or values[i - lag] is None:
            out.append(None)
        else:
            out.append(v - values[i - lag])  # type: ignore[operator]
    return out


def lag_pct(values: Sequence[Optional[float]], lag: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i, v in enumerate(values):
        base = values[i - lag] if i >= lag else None
        if i < lag or v is None or base is None or base == 0:
            out.append(None)
        else:
            out.append((v / base) - 1.0)  # type: ignore[operator]
    return out


def parse_fred_macro(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Optional[float]]]]:
    if not path.exists():
        return [], {}
    rows = read_csv_dicts(path)
    long_rows: List[Dict[str, Any]] = []
    panel: Dict[str, Dict[str, Optional[float]]] = defaultdict(dict)
    for row in rows:
        date = parse_date(row.get("date") or row.get("DATE") or row.get("observation_date"))
        sid = str(row.get("series_id") or row.get("series") or "").strip().upper()
        value = safe_float(row.get("value"))
        if not sid:
            # tolerate wide FRED file accidentally routed here
            for k, v in row.items():
                if norm_col(k) not in {"date", "observation_date"}:
                    sid = str(k).strip().upper()
                    value = safe_float(v)
                    break
        if not date or not sid or value is None:
            continue
        long_rows.append({"date": date, "series_id": sid, "value": value, "series_name": row.get("series_name") or FRED_DESCRIPTIONS.get(sid, "")})
        panel[date][sid] = value
    return long_rows, panel


def load_dxy_reference(path: Path) -> Tuple[Dict[str, Dict[str, Optional[float]]], Dict[str, Any]]:
    meta: Dict[str, Any] = {"dxy_rows": 0, "dxy_valid_close_rows": 0, "dxy_source_mode": "NO_DXY_FILE"}
    out: Dict[str, Dict[str, Optional[float]]] = defaultdict(dict)
    if not path.exists():
        return out, meta
    try:
        rows = read_csv_dicts(path)
    except Exception as exc:
        meta["dxy_source_mode"] = "DXY_READ_ERROR"
        meta["dxy_error"] = str(exc)
        return out, meta
    for row in rows:
        date = parse_date(row.get("date") or row.get("Date") or row.get("time") or row.get("datetime"))
        close = safe_float(row.get("close") or row.get("Close") or row.get("price") or row.get("last"))
        if not date:
            continue
        meta["dxy_rows"] += 1
        if close is not None:
            meta["dxy_valid_close_rows"] += 1
            out[date]["dxy_close"] = close
    meta["dxy_source_mode"] = "DIRECT_DXY_VALID" if meta["dxy_valid_close_rows"] >= 50 else "DIRECT_DXY_INVALID_OR_TOO_SHORT"
    return out, meta


def build_daily_macro_panel(normalized_dir: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    fred_rows, fred_panel = parse_fred_macro(normalized_dir / "fred_macro_normalized.csv")
    dxy_panel, dxy_meta = load_dxy_reference(normalized_dir / "dxy_reference_normalized.csv")

    all_dates = sorted(set(fred_panel.keys()) | set(dxy_panel.keys()))
    rows: List[Dict[str, Any]] = []
    if not all_dates:
        return [], {"warning": "no_fred_or_dxy_dates"}

    # Carry no forward fill here: keep observation-date values exact. Discovery stages can decide lag/ffill policy.
    for d in all_dates:
        f = fred_panel.get(d, {})
        dx = dxy_panel.get(d, {})
        direct_dxy_valid = dxy_meta.get("dxy_source_mode") == "DIRECT_DXY_VALID"
        dollar_index = dx.get("dxy_close") if direct_dxy_valid else f.get("DTWEXBGS")
        row: Dict[str, Any] = {
            "date": d,
            "real_yield_10y": f.get("DFII10"),
            "nominal_yield_10y": f.get("DGS10"),
            "nominal_yield_2y": f.get("DGS2"),
            "curve_10y_2y": (f.get("DGS10") - f.get("DGS2")) if f.get("DGS10") is not None and f.get("DGS2") is not None else None,
            "breakeven_10y": f.get("T10YIE"),
            "breakeven_5y": f.get("T5YIE"),
            "fed_funds_effective": f.get("DFF"),
            "fed_balance_sheet_walcl": f.get("WALCL"),
            "vix": f.get("VIXCLS"),
            "hy_oas": f.get("BAMLH0A0HYM2"),
            "broad_dollar_dtwexbgs": f.get("DTWEXBGS"),
            "dxy_close_direct": dx.get("dxy_close"),
            "dollar_pressure_index": dollar_index,
            "dollar_pressure_source": "DIRECT_DXY" if direct_dxy_valid and dollar_index is not None else "FRED_DTWEXBGS_FALLBACK" if dollar_index is not None else "MISSING",
            "lag_safety_status": "OBSERVATION_DATE_PANEL_NOT_RELEASE_LAGGED",
        }
        rows.append(row)

    # Derived lag features.
    lag_cols = [
        "real_yield_10y", "nominal_yield_10y", "nominal_yield_2y", "curve_10y_2y",
        "breakeven_10y", "fed_funds_effective", "fed_balance_sheet_walcl", "vix", "hy_oas", "dollar_pressure_index",
    ]
    for col in lag_cols:
        vals = [safe_float(r.get(col)) for r in rows]
        for lag in [1, 5, 20, 60, 120]:
            diffs = lag_diff(vals, lag)
            pcts = lag_pct(vals, lag)
            for i, r in enumerate(rows):
                r[f"{col}_chg_{lag}d"] = diffs[i]
                if col in {"fed_balance_sheet_walcl", "vix", "dollar_pressure_index"}:
                    r[f"{col}_pct_{lag}d"] = pcts[i]
        zvals = rolling_z(vals, window=252, min_periods=60)
        for i, r in enumerate(rows):
            r[f"{col}_z252"] = zvals[i]

    output = feature_dir / "stage115_daily_macro_feature_panel.csv"
    write_csv(output, rows)
    fred_wide = feature_dir / "stage115_fred_macro_daily_wide.csv"
    write_csv(fred_wide, [{"date": d, **fred_panel.get(d, {})} for d in all_dates])
    meta = {
        "daily_macro_rows": len(rows),
        "fred_long_rows": len(fred_rows),
        **dxy_meta,
        "dxy_fallback_active": dxy_meta.get("dxy_source_mode") != "DIRECT_DXY_VALID",
        "daily_macro_feature_panel": str(output),
        "fred_macro_daily_wide": str(fred_wide),
    }
    return rows, meta


def find_existing_path(value: Any) -> Optional[Path]:
    if not value:
        return None
    p = Path(str(value))
    return p if p.exists() and p.is_file() else None


def paths_from_classification(classification_csv: Path, family: str, parser_hint_filter: Optional[str] = None) -> List[Path]:
    if not classification_csv.exists():
        return []
    out: List[Path] = []
    try:
        rows = read_csv_dicts(classification_csv)
    except Exception:
        return []
    for row in rows:
        if row.get("source_family") != family:
            continue
        if parser_hint_filter and row.get("parser_hint") != parser_hint_filter:
            continue
        p = find_existing_path(row.get("path"))
        if p:
            out.append(p)
    # de-dupe by logical filename + size, prefer Downloads path over copied raw path if duplicates remain.
    best: Dict[Tuple[str, str], Path] = {}
    for p in out:
        logical = row_logical_name_from_path(p)
        key = (logical, str(p.stat().st_size))
        current = best.get(key)
        if current is None or ("/Downloads/" in str(p) and "/Downloads/" not in str(current)):
            best[key] = p
    return sorted(best.values(), key=lambda x: x.name)


def row_logical_name_from_path(p: Path) -> str:
    m = re.match(r"^[0-9a-fA-F]{8,16}__(.+)$", p.name)
    return m.group(1) if m else p.name


def parse_cot_csv_member(zf: zipfile.ZipFile, member: str) -> List[Dict[str, str]]:
    raw = zf.read(member)
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = raw.decode(enc)
            sample = text[:8192]
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            return list(csv.DictReader(text.splitlines(), dialect=dialect))
        except Exception:
            continue
    return []


def parse_cot_gold_features(classification_csv: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    zips = paths_from_classification(classification_csv, "cot_cftc", "cot_zip")
    # Prefer futures text disaggregated. Avoid parsing XLS zip families unless no text exists.
    fut_txt = [p for p in zips if row_logical_name_from_path(p).lower().startswith("fut_disagg_txt_")]
    com_txt = [p for p in zips if row_logical_name_from_path(p).lower().startswith("com_disagg_txt_")]
    parse_targets = fut_txt if fut_txt else com_txt
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for path in parse_targets:
        family = row_logical_name_from_path(path).lower().split("_")[0:3]
        family_name = "_".join(family)
        try:
            with zipfile.ZipFile(path) as zf:
                members = [m for m in zf.namelist() if not m.endswith("/") and m.lower().endswith((".txt", ".csv"))]
                for member in members:
                    dict_rows = parse_cot_csv_member(zf, member)
                    if not dict_rows:
                        continue
                    cols = list(dict_rows[0].keys())
                    colmap = {k: find_col(cols, aliases) for k, aliases in COT_ALIASES.items()}
                    if not colmap.get("market") or not colmap.get("date"):
                        continue
                    for r in dict_rows:
                        market = str(r.get(colmap["market"] or "", ""))
                        if "GOLD" not in market.upper():
                            continue
                        date = parse_date(r.get(colmap["date"] or ""))
                        if not date:
                            continue
                        oi = safe_float(r.get(colmap.get("open_interest") or ""))
                        mm_long = safe_float(r.get(colmap.get("mm_long") or ""))
                        mm_short = safe_float(r.get(colmap.get("mm_short") or ""))
                        mm_spread = safe_float(r.get(colmap.get("mm_spread") or ""))
                        prod_long = safe_float(r.get(colmap.get("prod_long") or ""))
                        prod_short = safe_float(r.get(colmap.get("prod_short") or ""))
                        swap_long = safe_float(r.get(colmap.get("swap_long") or ""))
                        swap_short = safe_float(r.get(colmap.get("swap_short") or ""))
                        other_long = safe_float(r.get(colmap.get("other_long") or ""))
                        other_short = safe_float(r.get(colmap.get("other_short") or ""))
                        nonrep_long = safe_float(r.get(colmap.get("nonrep_long") or ""))
                        nonrep_short = safe_float(r.get(colmap.get("nonrep_short") or ""))
                        mm_net = (mm_long - mm_short) if mm_long is not None and mm_short is not None else None
                        prod_net = (prod_long - prod_short) if prod_long is not None and prod_short is not None else None
                        swap_net = (swap_long - swap_short) if swap_long is not None and swap_short is not None else None
                        rows.append({
                            "report_date": date,
                            "market_name": market,
                            "open_interest_all": oi,
                            "mm_long_all": mm_long,
                            "mm_short_all": mm_short,
                            "mm_spread_all": mm_spread,
                            "mm_net_all": mm_net,
                            "mm_net_pct_oi": (mm_net / oi) if mm_net is not None and oi else None,
                            "prod_long_all": prod_long,
                            "prod_short_all": prod_short,
                            "prod_net_all": prod_net,
                            "prod_net_pct_oi": (prod_net / oi) if prod_net is not None and oi else None,
                            "swap_long_all": swap_long,
                            "swap_short_all": swap_short,
                            "swap_net_all": swap_net,
                            "other_long_all": other_long,
                            "other_short_all": other_short,
                            "other_net_all": (other_long - other_short) if other_long is not None and other_short is not None else None,
                            "nonrep_long_all": nonrep_long,
                            "nonrep_short_all": nonrep_short,
                            "nonrep_net_all": (nonrep_long - nonrep_short) if nonrep_long is not None and nonrep_short is not None else None,
                            "cot_source_family": family_name,
                            "source_zip": str(path),
                            "source_member": member,
                        })
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    # Deduplicate and pick one primary gold row per date. Prefer COMEX/GOLD rows with highest OI.
    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_date[str(r.get("report_date"))].append(r)
    selected: List[Dict[str, Any]] = []
    for date, candidates in sorted(by_date.items()):
        def score(r: Dict[str, Any]) -> Tuple[int, float]:
            name = str(r.get("market_name", "")).upper()
            comex = 1 if ("COMEX" in name or "COMMODITY EXCHANGE" in name) else 0
            oi = safe_float(r.get("open_interest_all")) or -1.0
            return (comex, oi)
        best = sorted(candidates, key=score, reverse=True)[0]
        selected.append(best)

    # Rolling features.
    selected.sort(key=lambda r: str(r.get("report_date")))
    mm_pct = [safe_float(r.get("mm_net_pct_oi")) for r in selected]
    prod_pct = [safe_float(r.get("prod_net_pct_oi")) for r in selected]
    mm_net = [safe_float(r.get("mm_net_all")) for r in selected]
    mm_z = rolling_z(mm_pct, window=156, min_periods=52)
    prod_z = rolling_z(prod_pct, window=156, min_periods=52)
    mm_net_z = rolling_z(mm_net, window=156, min_periods=52)
    mm_decrowd_4w = lag_diff(mm_pct, 4)
    mm_decrowd_12w = lag_diff(mm_pct, 12)
    for i, r in enumerate(selected):
        r["mm_net_pct_oi_z156w"] = mm_z[i]
        r["prod_net_pct_oi_z156w"] = prod_z[i]
        r["mm_net_all_z156w"] = mm_net_z[i]
        r["mm_net_pct_oi_change_4w"] = mm_decrowd_4w[i]
        r["mm_net_pct_oi_change_12w"] = mm_decrowd_12w[i]
        z = safe_float(r.get("mm_net_pct_oi_z156w"))
        if z is None:
            state = "COT_STATE_INSUFFICIENT_HISTORY"
        elif z >= 1.5:
            state = "LONG_CROWDED"
        elif z <= -1.5:
            state = "SHORT_CROWDED"
        else:
            state = "COT_NEUTRAL"
        r["cot_positioning_state"] = state

    output = feature_dir / "stage115_cot_gold_weekly_features.csv"
    write_csv(output, selected)
    meta = {
        "cot_zip_files_seen": len(zips),
        "cot_zip_files_parsed": len(parse_targets),
        "cot_source_mode": "fut_disagg_txt" if fut_txt else "com_disagg_txt_fallback" if com_txt else "NO_TEXT_COT_ZIPS",
        "cot_gold_raw_rows": len(rows),
        "cot_gold_weekly_feature_rows": len(selected),
        "cot_parse_errors": errors[:20],
        "cot_gold_weekly_features": str(output),
    }
    return selected, meta


def parse_fred_release_calendar(path: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if path.exists():
        for row in read_csv_dicts(path):
            date = parse_date(row.get("date") or row.get("release_date"))
            if not date:
                continue
            name = str(row.get("release_name") or row.get("name") or "")
            out.append({
                "event_date": date,
                "event_family": "fred_release_calendar",
                "event_name": name,
                "release_id": row.get("release_id") or row.get("id") or "",
                "is_fed_release": "fed" in name.lower() or "fomc" in name.lower(),
                "is_labor_release": any(x in name.lower() for x in ["employment", "labor", "payroll", "jobs", "unemployment"]),
                "is_inflation_release": any(x in name.lower() for x in ["price", "cpi", "ppi", "inflation", "pce"]),
                "source": "FRED",
            })
    output = feature_dir / "stage115_fred_release_event_features.csv"
    write_csv(output, out)
    return out, {"fred_release_event_rows": len(out), "fred_release_event_features": str(output)}


def parse_fomc_calendar(path: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if path.exists():
        for row in read_csv_dicts(path):
            date = parse_date(row.get("date") or row.get("event_date_text") or row.get("event_date"))
            if not date:
                continue
            out.append({
                "event_date": date,
                "event_family": "fomc",
                "event_name": "FOMC meeting/calendar item",
                "is_fed_release": True,
                "source": row.get("source_file") or "FOMC",
            })
    output = feature_dir / "stage115_fomc_event_features.csv"
    write_csv(output, out)
    return out, {"fomc_event_rows": len(out), "fomc_event_features": str(output)}


def parse_treasury_auctions(path: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if path.exists():
        for row in read_csv_dicts(path):
            raw = row.get("raw_row_json")
            payload: Dict[str, Any] = {}
            if raw:
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {}
            date = parse_date(row.get("date") or payload.get("auction_date") or payload.get("auctionDate") or payload.get("issue_date") or payload.get("record_date"))
            if not date:
                continue
            security = payload.get("security_type") or payload.get("security_desc") or payload.get("security_term") or payload.get("Security Type") or ""
            out.append({
                "event_date": date,
                "event_family": "treasury_auction",
                "event_name": str(security) or "Treasury auction",
                "security_type": security,
                "offering_amount": safe_float(payload.get("offering_amt") or payload.get("offering_amount") or payload.get("Offering Amount")),
                "source": row.get("source_file") or "Treasury FiscalData",
            })
    output = feature_dir / "stage115_treasury_auction_event_features.csv"
    write_csv(output, out)
    return out, {"treasury_auction_event_rows": len(out), "treasury_auction_event_features": str(output)}


def parse_bls_features(path: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if path.exists():
        for row in read_csv_dicts(path):
            date = parse_date(row.get("date"))
            sid = str(row.get("series_id") or "").strip()
            value = safe_float(row.get("value"))
            if not date or not sid or value is None:
                continue
            rows.append({
                "date": date,
                "series_id": sid,
                "series_name": row.get("series_name") or BLS_DESCRIPTIONS.get(sid, ""),
                "value": value,
                "feature_name": f"bls_{sid}",
                "lag_safety_status": "OBSERVATION_PERIOD_NOT_RELEASE_LAGGED",
            })
    output = feature_dir / "stage115_bls_macro_feature_long.csv"
    write_csv(output, rows)
    return rows, {"bls_feature_rows": len(rows), "bls_macro_feature_long": str(output)}


def parse_shell_to_event_counts(path: Path, family: str, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if path.exists():
        for row in read_csv_dicts(path):
            date = parse_date(row.get("date"))
            rows.append({
                "event_date": date or "",
                "event_family": family,
                "event_name": row.get("source_file") or family,
                "source": row.get("source_file") or "",
                "quality_flag": "DATE_PARSED" if date else "DATE_NOT_PARSED_SHELL_ONLY",
            })
    output = feature_dir / f"stage115_{family}_event_shell_features.csv"
    write_csv(output, rows)
    return rows, {f"{family}_event_shell_rows": len(rows), f"{family}_event_shell_features": str(output)}


def parse_raw_json_row(row: Dict[str, str]) -> Dict[str, Any]:
    raw = row.get("raw_row_json") or ""
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"value": val}
    except Exception:
        return {}


def find_first_date_in_payload(payload: Dict[str, Any]) -> Optional[str]:
    for k, v in payload.items():
        if "date" in str(k).lower() or "time" in str(k).lower() or "month" in str(k).lower() or "year" in str(k).lower():
            d = parse_date(v)
            if d:
                return d
    for v in payload.values():
        d = parse_date(v)
        if d:
            return d
    return None


def numeric_payload_features(payload: Dict[str, Any], max_features: int = 12) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    count = 0
    for k, v in payload.items():
        x = safe_float(v)
        if x is None:
            continue
        key = re.sub(r"[^a-zA-Z0-9]+", "_", str(k).strip()).strip("_").lower()[:80] or f"numeric_{count}"
        out[key] = x
        count += 1
        if count >= max_features:
            break
    return out


def parse_xlsx_raw_rows(path: Path, family: str, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if path.exists():
        for row in read_csv_dicts(path):
            payload = parse_raw_json_row(row)
            date = find_first_date_in_payload(payload)
            numerics = numeric_payload_features(payload)
            if not date and not numerics:
                continue
            rows.append({
                "date": date or "",
                "source_family": family,
                "source_file": row.get("source_file") or "",
                "sheet": row.get("sheet") or "",
                "row_index": row.get("row_index") or "",
                "quality_flag": "FEATURE_CANDIDATE" if date or len(numerics) >= 2 else "LOW_CONFIDENCE_RAW_ROW",
                **numerics,
            })
    output = feature_dir / f"stage115_{family}_feature_candidates.csv"
    write_csv(output, rows)
    return rows, {f"{family}_feature_candidate_rows": len(rows), f"{family}_feature_candidates": str(output)}


OFFICIAL_EVENT_TIME_POLICY_VERSION = "USD_CORE_RELEASE_TIME_POLICY_V1"
ET = ZoneInfo("America/New_York")


def canonical_et_timestamp(date_iso: str, hour: int, minute: int) -> Optional[str]:
    parsed = parse_date(date_iso)
    if not parsed:
        return None
    try:
        d = dt.date.fromisoformat(parsed)
        local = dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)
        return local.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def classify_official_release_name(name: str) -> Optional[Dict[str, Any]]:
    cleaned = re.sub(r"\s+", " ", str(name or "")).strip()
    lower = cleaned.lower()
    if lower.startswith("employment situation"):
        return {"source": "BLS", "category": "BLS_EMPLOYMENT_SITUATION", "hour": 8, "minute": 30}
    if lower.startswith("consumer price index"):
        return {"source": "BLS", "category": "BLS_CPI", "hour": 8, "minute": 30}
    if lower.startswith("producer price index"):
        return {"source": "BLS", "category": "BLS_PPI", "hour": 8, "minute": 30}
    if lower.startswith("job openings and labor turnover") or lower.startswith("job openings and labor turnover survey"):
        return {"source": "BLS", "category": "BLS_JOLTS", "hour": 10, "minute": 0}
    if lower.startswith("employment cost index"):
        return {"source": "BLS", "category": "BLS_ECI", "hour": 8, "minute": 30}
    if lower.startswith("personal income and outlays"):
        return {"source": "BEA", "category": "BEA_PERSONAL_INCOME_OUTLAYS", "hour": 8, "minute": 30}
    if lower.startswith("gross domestic product"):
        excluded = (
            " by state", " by industry", " by county", " by metropolitan",
            " puerto rico", " guam", " american samoa", " territories",
        )
        if any(token in lower for token in excluded):
            return None
        return {"source": "BEA", "category": "BEA_GDP", "hour": 8, "minute": 30}
    return None


def build_official_core_event_timestamps(normalized_dir: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build timestamped BLS/BEA/FOMC events from the existing normalized pipeline.

    Dates come from the official FRED release-dates API or locally downloaded Fed
    calendar pages. Times are deterministic source-family policies in US Eastern
    time and are explicitly labeled as policy-derived, not scraped exact timestamps.
    """
    rows: List[Dict[str, Any]] = []
    fred_path = normalized_dir / "fred_release_calendar_normalized.csv"
    if fred_path.exists():
        for row in read_csv_dicts(fred_path):
            date = parse_date(row.get("date") or row.get("release_date"))
            name = str(row.get("release_name") or row.get("name") or "").strip()
            policy = classify_official_release_name(name)
            if not date or not policy:
                continue
            event_time = canonical_et_timestamp(date, int(policy["hour"]), int(policy["minute"]))
            if not event_time:
                continue
            source_file = str(row.get("source_file") or fred_path)
            is_core_release_endpoint = "fred_core_release_dates" in source_file
            rows.append({
                "event_time_utc": event_time,
                "source": policy["source"],
                "category": policy["category"],
                "title": name,
                "source_url": (
                    "https://api.stlouisfed.org/fred/release/dates"
                    if is_core_release_endpoint
                    else "https://api.stlouisfed.org/fred/releases/dates"
                ),
                "source_file": source_file,
                "date_source": (
                    "FRED_CORE_RELEASE_DATES_API"
                    if is_core_release_endpoint
                    else "FRED_RELEASE_DATES_API"
                ),
                "time_source": OFFICIAL_EVENT_TIME_POLICY_VERSION,
                "blackout_before_minutes": 60.0,
                "blackout_after_minutes": 60.0,
                "release_id": row.get("release_id") or "",
            })

    fomc_path = normalized_dir / "fomc_calendar_extracted.csv"
    if fomc_path.exists():
        for row in read_csv_dicts(fomc_path):
            if str(row.get("has_statement") or "").strip().lower() not in {"1", "true", "yes"}:
                continue
            date = parse_date(row.get("event_date") or row.get("event_date_text"))
            if not date:
                continue
            statement_time = canonical_et_timestamp(date, 14, 0)
            if statement_time:
                rows.append({
                    "event_time_utc": statement_time,
                    "source": "FED",
                    "category": "FOMC_STATEMENT",
                    "title": f"FOMC Statement — {date}",
                    "source_url": "https://www.federalreserve.gov/monetarypolicy/fomc.htm",
                    "source_file": row.get("source_file") or str(fomc_path),
                    "date_source": "FED_LOCAL_CALENDAR_PAGE",
                    "time_source": OFFICIAL_EVENT_TIME_POLICY_VERSION,
                    "blackout_before_minutes": 60.0,
                    "blackout_after_minutes": 60.0,
                    "release_id": "",
                })
            if str(row.get("has_press_conference") or "").strip().lower() in {"1", "true", "yes"}:
                press_time = canonical_et_timestamp(date, 14, 30)
                if press_time:
                    rows.append({
                        "event_time_utc": press_time,
                        "source": "FED",
                        "category": "FOMC_PRESS_CONFERENCE",
                        "title": f"FOMC Press Conference — {date}",
                        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomc.htm",
                        "source_file": row.get("source_file") or str(fomc_path),
                        "date_source": "FED_LOCAL_CALENDAR_PAGE",
                        "time_source": OFFICIAL_EVENT_TIME_POLICY_VERSION,
                        "blackout_before_minutes": 60.0,
                        "blackout_after_minutes": 60.0,
                        "release_id": "",
                    })

    unique: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in rows:
        unique[(str(row["event_time_utc"]), str(row["source"]), str(row["category"]))] = row
    rows = [unique[key] for key in sorted(unique)]
    output = feature_dir / "stage115_official_core_event_timestamps.csv"
    write_csv(output, rows)
    policy_path = feature_dir / "stage115_official_core_event_timestamp_policy.json"
    write_json(policy_path, {
        "policy_version": OFFICIAL_EVENT_TIME_POLICY_VERSION,
        "date_sources": ["FRED_CORE_RELEASE_DATES_API", "FRED_RELEASE_DATES_API", "FED_LOCAL_CALENDAR_PAGE"],
        "timezone": "America/New_York",
        "times": {
            "BLS_EMPLOYMENT_SITUATION": "08:30 ET",
            "BLS_CPI": "08:30 ET",
            "BLS_PPI": "08:30 ET",
            "BLS_JOLTS": "10:00 ET",
            "BLS_ECI": "08:30 ET",
            "BEA_GDP": "08:30 ET",
            "BEA_PERSONAL_INCOME_OUTLAYS": "08:30 ET",
            "FOMC_STATEMENT": "14:00 ET",
            "FOMC_PRESS_CONFERENCE": "14:30 ET",
        },
        "scope": "scheduled_blackout_only_not_event_surprise",
    })
    return rows, {
        "official_core_event_timestamp_rows": len(rows),
        "official_core_event_timestamps": str(output),
        "official_core_event_timestamp_policy": str(policy_path),
        "official_core_event_counts_by_source": dict(
            sorted((source, sum(1 for row in rows if row["source"] == source)) for source in {row["source"] for row in rows})
        ),
    }


def build_unified_event_calendar(feature_dir: Path, event_groups: Sequence[Sequence[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for group in event_groups:
        flat.extend(group)
    by_date: Dict[str, Dict[str, Any]] = {}
    for r in flat:
        d = str(r.get("event_date") or r.get("date") or "")
        if not d:
            continue
        bucket = by_date.setdefault(d, {"date": d, "event_count_total": 0})
        bucket["event_count_total"] = int(bucket.get("event_count_total", 0)) + 1
        family = str(r.get("event_family") or "unknown")
        key = f"event_count_{family}"
        bucket[key] = int(bucket.get(key, 0)) + 1
        if r.get("is_fed_release") in {True, "True", "true", "1"}:
            bucket["has_fed_release"] = 1
        if r.get("is_labor_release") in {True, "True", "true", "1"}:
            bucket["has_labor_release"] = 1
        if r.get("is_inflation_release") in {True, "True", "true", "1"}:
            bucket["has_inflation_release"] = 1
    rows = [by_date[d] for d in sorted(by_date)]
    output = feature_dir / "stage115_unified_event_calendar_features.csv"
    write_csv(output, rows)
    return rows, {"unified_event_calendar_rows": len(rows), "unified_event_calendar_features": str(output)}


def build_feature_inventory(feature_dir: Path, outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, val in sorted(outputs.items()):
        if isinstance(val, str) and val.endswith(".csv"):
            p = Path(val)
            row_count = ""
            col_count = ""
            columns = ""
            if p.exists():
                try:
                    rr = read_csv_dicts(p)
                    row_count = len(rr)
                    if rr:
                        col_count = len(rr[0].keys())
                        columns = ";".join(list(rr[0].keys())[:80])
                except Exception as exc:
                    columns = f"read_error:{exc}"
            rows.append({"artifact_key": key, "path": val, "row_count": row_count, "column_count": col_count, "columns_preview": columns})
    output = feature_dir / "stage115_feature_inventory.csv"
    write_csv(output, rows)
    return rows


def write_report(path: Path, summary: Dict[str, Any]) -> None:
    lines = [
        f"# {STAGE}",
        "",
        f"Generated UTC: {summary.get('generated_utc')}",
        "",
        f"Status: `{summary.get('status')}`",
        "",
        f"Decision: `{summary.get('decision')}`",
        "",
        "## Interpretation",
        "",
        "Stage115 turns Stage114B intake outputs into feature-grade or feature-candidate datasets. It does not promote any candidate, touch MT5, modify the EA, or allow orders.",
        "",
        "## Key quality flags",
        "",
        f"- DXY source mode: `{summary.get('dxy_source_mode')}`",
        f"- DXY fallback active: `{summary.get('dxy_fallback_active')}`",
        f"- COT source mode: `{summary.get('cot_source_mode')}`",
        f"- COT weekly feature rows: `{summary.get('cot_gold_weekly_feature_rows')}`",
        f"- Daily macro panel rows: `{summary.get('daily_macro_rows')}`",
        "",
        "## Next use",
        "",
        "Use `stage115_daily_macro_feature_panel.csv` and `stage115_cot_gold_weekly_features.csv` as first-class inputs for the next segmented discovery/audit stage. Treat WGC/SPDR candidate extracts as candidate features until Stage116 performs source-specific validation.",
    ]
    ensure_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(root: Path, normalized_dir: Optional[Path] = None, classification_csv: Optional[Path] = None) -> Dict[str, Any]:
    normalized_dir = normalized_dir or (root / NORMALIZED_REL)
    classification_csv = classification_csv or (root / CLASSIFICATION_REL)
    feature_dir = root / FEATURE_REL
    report_dir = root / REPORT_REL
    ensure_dir(feature_dir)
    ensure_dir(report_dir)

    daily_rows, daily_meta = build_daily_macro_panel(normalized_dir, feature_dir)
    cot_rows, cot_meta = parse_cot_gold_features(classification_csv, feature_dir)
    fred_events, fred_event_meta = parse_fred_release_calendar(normalized_dir / "fred_release_calendar_normalized.csv", feature_dir)
    fomc_events, fomc_meta = parse_fomc_calendar(normalized_dir / "fomc_calendar_extracted.csv", feature_dir)
    treasury_events, treasury_meta = parse_treasury_auctions(normalized_dir / "treasury_auctions_normalized.csv", feature_dir)
    bls_rows, bls_meta = parse_bls_features(normalized_dir / "bls_macro_normalized.csv", feature_dir)
    bea_events, bea_meta = parse_shell_to_event_counts(normalized_dir / "bea_macro_shell_normalized.csv", "bea", feature_dir)
    census_events, census_meta = parse_shell_to_event_counts(normalized_dir / "census_macro_shell_normalized.csv", "census", feature_dir)
    wgc_etf_rows, wgc_etf_meta = parse_xlsx_raw_rows(normalized_dir / "wgc_gold_etf_xlsx_rows.csv", "wgc_gold_etf", feature_dir)
    wgc_cb_rows, wgc_cb_meta = parse_xlsx_raw_rows(normalized_dir / "wgc_central_bank_gold_xlsx_rows.csv", "wgc_central_bank_gold", feature_dir)
    spdr_rows, spdr_meta = parse_xlsx_raw_rows(normalized_dir / "spdr_gld_xlsx_rows.csv", "spdr_gld", feature_dir)
    official_core_events, official_core_meta = build_official_core_event_timestamps(normalized_dir, feature_dir)
    unified_events, unified_event_meta = build_unified_event_calendar(feature_dir, [fred_events, fomc_events, treasury_events, bea_events, census_events])

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS,
        "decision": DECISION,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "normalized_dir": str(normalized_dir),
        "classification_csv": str(classification_csv),
        "feature_dir": str(feature_dir),
        **daily_meta,
        **cot_meta,
        **fred_event_meta,
        **fomc_meta,
        **treasury_meta,
        **bls_meta,
        **bea_meta,
        **census_meta,
        **wgc_etf_meta,
        **wgc_cb_meta,
        **spdr_meta,
        **official_core_meta,
        **unified_event_meta,
        "wgc_spdr_feature_status": "FEATURE_CANDIDATE_NEEDS_SOURCE_SPECIFIC_VALIDATION",
        "bls_bea_census_lag_status": "OBSERVATION_OR_SHELL_DATES_NOT_FULLY_RELEASE_LAG_SAFE",
        "official_core_event_timestamp_status": "DATE_SOURCE_OFFICIAL_TIME_SOURCE_EXPLICIT_POLICY",
        "next": [
            "Review DXY source output; if Stooq is invalid, keep DTWEXBGS fallback and replace DXY downloader later.",
            "Use COT weekly features plus daily macro panel for segmented discovery.",
            "Run a Stage116 source-specific WGC/SPDR validator before treating gold ETF/central-bank rows as hard features.",
        ],
    }
    inventory_rows = build_feature_inventory(feature_dir, summary)
    inventory_path = feature_dir / "stage115_feature_inventory.csv"
    summary["feature_inventory"] = str(inventory_path)
    summary["feature_inventory_rows"] = len(inventory_rows)

    summary_path = report_dir / "stage115_feature_grade_macro_fundamental_builder_summary.json"
    report_path = report_dir / "stage115_feature_grade_macro_fundamental_builder_report.md"
    write_json(summary_path, summary)
    write_report(report_path, summary)
    summary["summary_json"] = str(summary_path)
    summary["report_md"] = str(report_path)
    # Rewrite after adding self paths.
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default=".", help="Project root")
    ap.add_argument("--normalized-dir", default=None, help="Override Stage114B normalized output directory")
    ap.add_argument("--classification", default=None, help="Override Stage114B corrected classification CSV")
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    normalized_dir = Path(args.normalized_dir).expanduser().resolve() if args.normalized_dir else None
    classification = Path(args.classification).expanduser().resolve() if args.classification else None
    run(root=root, normalized_dir=normalized_dir, classification_csv=classification)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
