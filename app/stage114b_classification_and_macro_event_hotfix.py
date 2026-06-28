#!/usr/bin/env python3
"""
Stage114B_CLASSIFICATION_AND_MACRO_EVENT_HOTFIX

Hotfix for Stage114 official/fundamental event normalizer.

Purpose:
- Fix source classification after Stage113 copies files with hash prefixes like
  `148364a82be6__DFII10.csv`.
- Recognize all downloaded official-data families found in the current inbox:
  FRED macro CSV, FRED release JSON, COT zip variants, DXY/Stooq, BLS, BEA,
  Census, FOMC, Treasury, WGC ETF, WGC central-bank gold, SPDR GLD, AMarkets.
- Produce corrected manifests and feature-ready macro/event shells without any
  order/MT5/EA/broker action.

This is infrastructure-only. No trading signal, no paper order, no live order.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage114B_CLASSIFICATION_AND_MACRO_EVENT_HOTFIX"
STATUS = "STAGE114B_COMPLETE_CLASSIFICATION_HOTFIX_READY_NO_PROMOTION"
DECISION = "STAGE114B_CORRECTED_MACRO_EVENT_MANIFEST_READY_NO_ORDER"
CLASSIFICATION = "INFRASTRUCTURE_ONLY_NO_ORDER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE114B",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_INBOX_REL = "xauusd_fundamental_event_inbox"
NORMALIZED_REL = "data/fundamental_event_inbox/normalized"
REPORT_REL = "reports/stage114b_classification_and_macro_event_hotfix"
RAW_REL = "data/fundamental_event_inbox/raw"
EXTERNAL_FRONTIERS_REL = "data/external_frontiers"

HASH_PREFIX_RE = re.compile(r"^[0-9a-fA-F]{8,16}__(.+)$")

FRED_SERIES_NAMES: Dict[str, str] = {
    "DFII10": "10-Year Treasury Inflation-Indexed Security, constant maturity",
    "VIXCLS": "CBOE Volatility Index: VIX",
    "DTWEXBGS": "Nominal Broad U.S. Dollar Index",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "DGS2": "2-Year Treasury Constant Maturity Rate",
    "T10YIE": "10-Year Breakeven Inflation Rate",
    "T5YIE": "5-Year Breakeven Inflation Rate",
    "DFF": "Effective Federal Funds Rate",
    "WALCL": "Federal Reserve Total Assets",
    "BAMLH0A0HYM2": "ICE BofA US High Yield Index Option-Adjusted Spread",
}

BLS_SERIES_NAMES: Dict[str, str] = {
    "CUSR0000SA0": "CPI-U All Items, seasonally adjusted",
    "CUSR0000SA0L1E": "CPI-U All Items Less Food and Energy, seasonally adjusted",
    "CES0000000001": "Total nonfarm payroll employment",
    "LNS14000000": "Unemployment rate",
    "LNS11300000": "Labor force participation rate",
}

IGNORE_NAMES = {
    ".ds_store",
    "data.txt",
}
IGNORE_SUFFIXES = {".pyc"}
SKIP_DIR_NAMES = {"__MACOSX", ".git", "__pycache__"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def canonical_filename(name: str) -> str:
    """Remove Stage113 hash prefix if present."""
    m = HASH_PREFIX_RE.match(name)
    return m.group(1) if m else name


def canonical_stem(name: str) -> str:
    return Path(canonical_filename(name)).stem


def sha256_file(path: Path, limit_mb: Optional[int] = 32) -> str:
    h = hashlib.sha256()
    limit = None if limit_mb is None else limit_mb * 1024 * 1024
    read = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            if limit is not None and read + len(chunk) > limit:
                chunk = chunk[: max(0, limit - read)]
            h.update(chunk)
            read += len(chunk)
            if limit is not None and read >= limit:
                break
    return h.hexdigest()


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in {".", "NA", "N/A", "nan", "NaN", "null", "None", "-"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
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


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    last_err: Optional[Exception] = None
    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
                except Exception:
                    dialect = csv.excel
                return list(csv.DictReader(f, dialect=dialect))
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"could not read csv {path}: {last_err}")


def read_manifest_paths(manifest_path: Optional[Path]) -> List[Path]:
    out: List[Path] = []
    if not manifest_path or not manifest_path.exists():
        return out
    try:
        rows = read_csv_dicts(manifest_path)
    except Exception:
        return out
    possible_cols = [
        "path", "file_path", "project_path", "dest_path", "destination_path",
        "source_path", "absolute_path", "local_path", "copied_path",
    ]
    for row in rows:
        for col in possible_cols:
            value = row.get(col)
            if value:
                p = Path(value).expanduser()
                if p.exists() and p.is_file():
                    out.append(p)
                break
    return out


def classify_path(path: Path) -> Tuple[str, str, str, str]:
    """Return source_family, canonical_bucket, parser_hint, normalized_filename."""
    fname = canonical_filename(path.name)
    lname = fname.lower()
    stem = Path(fname).stem
    lstem = stem.lower()
    suffix = Path(fname).suffix.lower()
    rel = str(path).lower()

    if lname in IGNORE_NAMES or suffix in IGNORE_SUFFIXES:
        return "ignored", "ignored", "ignored", fname

    # Technical data should be recognized but ignored by fundamental/event feature logic.
    if re.match(r"^amarkets_xauusd_(1m|5m|15m|30m|1h|h1|m1|m5|m15|m30)\.csv$", lname):
        return "technical_amarkets", "technical/amarkets", "amarkets_bars_reference_only", fname

    # FRED macro series, with or without hash prefix.
    if suffix == ".csv" and stem.upper() in FRED_SERIES_NAMES:
        return "fred_macro", "fred_macro", "fred_series_csv", fname

    if suffix == ".json" and ("fred_releases" in lname or "release_dates" in lname or "releases_dates" in lname):
        return "fred_release_calendar", "events/fred", "fred_release_dates_json", fname

    # DXY / dollar reference.
    if suffix == ".csv" and (
        "stooq" in lname or lname in {"us dollar index historical data.csv", "dxy.csv", "dx_f.csv", "dx.f.csv"} or "/dxy" in rel
    ):
        return "dxy_reference", "macro_misc/dxy", "dxy_csv", fname

    # COT variants. Keep all downloaded families out of unknown.
    if suffix == ".zip" and re.match(r"^(fut_disagg_txt|fut_disagg_xls|com_disagg_txt|com_disagg_xls)_\d{4}\.zip$", lname):
        return "cot_cftc", "cot/cftc", "cot_zip", fname
    if suffix == ".csv" and "cot_positioning_normalized" in lname:
        return "cot_cftc", "cot/cftc", "cot_normalized_existing", fname

    # Official agency data.
    if "bls" in rel or lname.startswith("bls_"):
        return "bls", "events/bls", "bls_json" if suffix == ".json" else "bls_other", fname
    if "bea" in rel or lname.startswith("bea_"):
        return "bea", "events/bea", "json_shell" if suffix == ".json" else "generic_event_data", fname
    if "census" in rel or lname.startswith("census_"):
        return "census", "events/census", "json_shell" if suffix == ".json" else "generic_event_data", fname
    if "fomc" in rel or "fomc" in lname:
        return "fomc", "events/fomc", "fomc_html_or_csv", fname
    if "treasury" in rel or "auction" in lname:
        return "treasury", "events/treasury", "treasury_csv" if suffix == ".csv" else "generic_event_data", fname

    # Gold flow / reserves.
    if suffix in {".xlsx", ".xls", ".csv"} and ("etf" in lname or "gold_etf" in rel):
        return "wgc_gold_etf", "gold_etf/wgc", "wgc_etf_xlsx_or_csv", fname
    if suffix == ".pdf" and "etf" in lname:
        return "reference_doc", "gold_etf/wgc", "reference_pdf", fname
    if suffix in {".xlsx", ".xls", ".csv"} and (
        "world_official_gold_holdings" in lname or "changes_latest" in lname or "quarterly_gold" in lname or "central_bank_gold" in rel
    ):
        return "wgc_central_bank_gold", "central_bank_gold", "wgc_cb_xlsx_or_csv", fname
    if suffix in {".xlsx", ".xls", ".csv"} and ("gld" in rel or "spdr" in rel or "spdr" in lname):
        return "spdr_gld", "gld/spdr", "spdr_gld_xlsx_or_csv", fname

    if suffix in {".md", ".pdf", ".txt"}:
        return "reference_doc", "docs_or_reference", "reference_doc", fname

    return "unknown", "unknown", "unknown", fname


def scan_files(root: Path, inbox: Path, manifest_path: Optional[Path]) -> List[Dict[str, Any]]:
    scan_roots = [
        inbox,
        root / RAW_REL,
        root / EXTERNAL_FRONTIERS_REL,
    ]
    manifest_paths = read_manifest_paths(manifest_path)
    rows_by_key: Dict[str, Dict[str, Any]] = {}

    def add_path(path: Path, discovered_from: str) -> None:
        if not path.exists() or not path.is_file():
            return
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            return
        if path.name.startswith("."):
            return
        try:
            digest = sha256_file(path, limit_mb=32)
        except Exception as exc:
            digest = f"unreadable:{exc}"
        family, bucket, hint, logical_name = classify_path(path)
        key = f"{digest}|{logical_name}|{path.stat().st_size}"
        existing = rows_by_key.get(key)
        # Prefer manual inbox path over copied raw hash path when duplicate content exists.
        prefer_new = existing is None or ("/Downloads/" in str(path) and "/Downloads/" not in str(existing.get("path", "")))
        if prefer_new:
            rows_by_key[key] = {
                "path": str(path),
                "filename": path.name,
                "logical_filename": logical_name,
                "size_bytes": path.stat().st_size,
                "sha256_partial_or_full": digest,
                "source_family": family,
                "canonical_bucket": bucket,
                "parser_hint": hint,
                "discovered_from": discovered_from,
                "hash_prefix_removed": "YES" if path.name != logical_name else "NO",
            }

    for base in scan_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            add_path(path, str(base))
    for path in manifest_paths:
        add_path(path, str(manifest_path))

    return sorted(rows_by_key.values(), key=lambda r: (r["source_family"], r["logical_filename"], r["path"]))


def normalize_fred(files: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        series_id = Path(canonical_filename(path.name)).stem.upper()
        try:
            rows = read_csv_dicts(path)
            for row in rows:
                # FRED CSV is usually DATE,<SERIES_ID>.
                date_value = row.get("DATE") or row.get("date") or row.get("observation_date") or ""
                value_raw = row.get(series_id)
                if value_raw is None:
                    # Use the first non-date column.
                    for k, v in row.items():
                        if k and k.lower() not in {"date", "observation_date"}:
                            value_raw = v
                            break
                out.append({
                    "date": date_value,
                    "series_id": series_id,
                    "series_name": FRED_SERIES_NAMES.get(series_id, ""),
                    "value": safe_float(value_raw),
                    "raw_value": "" if value_raw is None else value_raw,
                    "source_file": str(path),
                    "source_family": "fred_macro",
                })
        except Exception as exc:
            out.append({"date": "", "series_id": series_id, "series_name": FRED_SERIES_NAMES.get(series_id, ""), "value": "", "raw_value": "", "source_file": str(path), "source_family": "fred_macro", "error": str(exc)})
    return out


def normalize_fred_release_dates(files: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            candidates = []
            if isinstance(data, dict):
                for key in ["release_dates", "releases", "dates"]:
                    if isinstance(data.get(key), list):
                        candidates = data[key]
                        break
            if isinstance(candidates, list):
                for item in candidates:
                    if not isinstance(item, dict):
                        continue
                    out.append({
                        "date": item.get("date") or item.get("release_date") or "",
                        "release_id": item.get("release_id") or item.get("id") or "",
                        "release_name": item.get("release_name") or item.get("name") or "",
                        "source_file": str(path),
                        "source_family": "fred_release_calendar",
                        "raw_row_json": json.dumps(item, ensure_ascii=False),
                    })
            else:
                out.append({"date": "", "release_id": "", "release_name": "", "source_file": str(path), "source_family": "fred_release_calendar", "raw_row_json": json.dumps(data, ensure_ascii=False)[:5000], "warning": "no_release_dates_list_found"})
        except Exception as exc:
            out.append({"date": "", "release_id": "", "release_name": "", "source_file": str(path), "source_family": "fred_release_calendar", "raw_row_json": "", "error": str(exc)})
    return out


def normalize_dxy(files: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            rows = read_csv_dicts(path)
            for row in rows:
                lower = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
                date_value = lower.get("date") or lower.get("time") or lower.get("datetime") or ""
                close_raw = lower.get("close") or lower.get("price") or lower.get("last")
                out.append({
                    "date": date_value,
                    "open": safe_float(lower.get("open")),
                    "high": safe_float(lower.get("high")),
                    "low": safe_float(lower.get("low")),
                    "close": safe_float(close_raw),
                    "volume": safe_float(lower.get("volume") or lower.get("vol.")),
                    "source_file": str(path),
                    "source_family": "dxy_reference",
                })
        except Exception as exc:
            out.append({"date": "", "open": "", "high": "", "low": "", "close": "", "volume": "", "source_file": str(path), "source_family": "dxy_reference", "error": str(exc)})
    return out


def period_to_date(year: str, period: str) -> str:
    if period and re.fullmatch(r"M\d{2}", period):
        return f"{year}-{int(period[1:]):02d}-01"
    if period and re.fullmatch(r"Q\d", period):
        q = int(period[1:])
        m = {1: 1, 2: 4, 3: 7, 4: 10}.get(q, 1)
        return f"{year}-{m:02d}-01"
    return f"{year}-01-01" if year else ""


def normalize_bls_json(files: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            series_list = data.get("Results", {}).get("series", []) if isinstance(data, dict) else []
            for series in series_list:
                sid = series.get("seriesID") or series.get("seriesId") or ""
                for item in series.get("data", []):
                    year = str(item.get("year", ""))
                    period = str(item.get("period", ""))
                    out.append({
                        "date": period_to_date(year, period),
                        "series_id": sid,
                        "series_name": BLS_SERIES_NAMES.get(sid, ""),
                        "year": year,
                        "period": period,
                        "period_name": item.get("periodName", ""),
                        "value": safe_float(item.get("value")),
                        "raw_value": item.get("value", ""),
                        "source_file": str(path),
                        "source_family": "bls",
                    })
        except Exception as exc:
            out.append({"date": "", "series_id": "", "series_name": "", "year": "", "period": "", "period_name": "", "value": "", "raw_value": "", "source_file": str(path), "source_family": "bls", "error": str(exc)})
    return out


def normalize_json_shell(files: Sequence[Path], family: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    items = data["data"]
                elif isinstance(data.get("Results"), dict):
                    items = [data.get("Results")]
                elif isinstance(data.get("BEAAPI"), dict):
                    items = [data.get("BEAAPI")]
                else:
                    items = [data]
            elif isinstance(data, list):
                items = data
            else:
                items = [{"value": data}]
            for i, item in enumerate(items[:200000]):
                if not isinstance(item, dict):
                    item = {"value": item}
                date_candidate = ""
                for k, v in item.items():
                    lk = str(k).lower()
                    if "date" in lk or lk in {"time", "year", "period", "record_date"}:
                        date_candidate = str(v)
                        break
                out.append({
                    "date": date_candidate,
                    "source_family": family,
                    "source_file": str(path),
                    "row_index": i,
                    "raw_row_json": json.dumps(item, ensure_ascii=False, default=str),
                })
        except Exception as exc:
            out.append({"date": "", "source_family": family, "source_file": str(path), "row_index": "", "raw_row_json": "", "error": str(exc)})
    return out


def normalize_generic_csv(files: Sequence[Path], family: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            rows = read_csv_dicts(path)
            for i, row in enumerate(rows):
                compact = {str(k).strip(): v for k, v in row.items() if k is not None}
                date_candidate = ""
                for k, v in compact.items():
                    lk = k.lower()
                    if "date" in lk or lk in {"record_date", "auction_date", "issue_date", "maturity_date", "year", "period"}:
                        date_candidate = str(v)
                        break
                out.append({
                    "date": date_candidate,
                    "source_family": family,
                    "source_file": str(path),
                    "row_index": i,
                    "raw_row_json": json.dumps(compact, ensure_ascii=False, default=str),
                })
        except Exception as exc:
            out.append({"date": "", "source_family": family, "source_file": str(path), "row_index": "", "raw_row_json": "", "error": str(exc)})
    return out


def normalize_fomc(files: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    date_re = re.compile(r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:-\d{1,2})?,\s+\d{4}", re.I)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:3_000_000]
            matches = sorted(set(m.group(0) for m in date_re.finditer(text)))
            if matches:
                for m in matches:
                    out.append({"event_date_text": m, "source_family": "fomc", "source_file": str(path), "event_type": "fomc_calendar_text_match"})
            else:
                out.append({"event_date_text": "", "source_family": "fomc", "source_file": str(path), "event_type": "fomc_source_snapshot_no_date_parse"})
        except Exception as exc:
            out.append({"event_date_text": "", "source_family": "fomc", "source_file": str(path), "event_type": "error", "error": str(exc)})
    return out


def normalize_cot_zip(files: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        fname = canonical_filename(path.name)
        m = re.match(r"^(fut_disagg_txt|fut_disagg_xls|com_disagg_txt|com_disagg_xls)_(\d{4})\.zip$", fname.lower())
        cot_family = m.group(1) if m else "unknown_cot_zip"
        year = m.group(2) if m else ""
        try:
            with zipfile.ZipFile(path) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                out.append({
                    "source_family": "cot_cftc",
                    "cot_file_family": cot_family,
                    "year": year,
                    "logical_filename": fname,
                    "source_file": str(path),
                    "zip_member_count": len(names),
                    "zip_members": ";".join(names[:30]),
                    "note": "Registered for Stage115 dedicated COT feature parser.",
                })
        except Exception as exc:
            out.append({"source_family": "cot_cftc", "cot_file_family": cot_family, "year": year, "logical_filename": fname, "source_file": str(path), "zip_member_count": "", "zip_members": "", "note": "", "error": str(exc)})
    return out


def read_xlsx_rows(files: Sequence[Path], family: str, max_rows_per_file: int = 50000) -> List[Dict[str, Any]]:
    try:
        import openpyxl  # type: ignore
    except Exception as exc:
        return [{"source_family": family, "source_file": "", "sheet": "", "row_index": "", "raw_row_json": "", "error": f"openpyxl_not_available: {exc}"}]
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            per_file = 0
            for ws in wb.worksheets:
                headers: Optional[List[str]] = None
                for idx, values in enumerate(ws.iter_rows(values_only=True)):
                    vals = list(values)
                    non_empty = [v for v in vals if v not in (None, "")]
                    if len(non_empty) < 2:
                        continue
                    if headers is None:
                        headers = [str(v).strip() if v is not None else f"col_{i}" for i, v in enumerate(vals)]
                        continue
                    row = {headers[i] if i < len(headers) else f"col_{i}": vals[i] for i in range(len(vals))}
                    out.append({
                        "source_family": family,
                        "source_file": str(path),
                        "sheet": ws.title,
                        "row_index": idx,
                        "raw_row_json": json.dumps(row, ensure_ascii=False, default=str),
                    })
                    per_file += 1
                    if per_file >= max_rows_per_file:
                        break
                if per_file >= max_rows_per_file:
                    break
            wb.close()
        except Exception as exc:
            out.append({"source_family": family, "source_file": str(path), "sheet": "", "row_index": "", "raw_row_json": "", "error": str(exc)})
    return out


def rebuild_readme(inbox: Path) -> Path:
    ensure_dir(inbox)
    path = inbox / "README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md"
    text = """# XAUUSD Fundamental/Event Inbox Guide

Generated by Stage114B.

## Current operating rule

You may put downloaded files directly in the root of this inbox or in subfolders. The normalizer removes Stage113 hash prefixes and classifies files by logical filename.

## Run unifier

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage113_fundamental_event_inbox_unifier.py \
  --root /Users/vahid/Desktop/xauusd-trader
```

## Run corrected normalizer

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage114b_classification_and_macro_event_hotfix.py \
  --root /Users/vahid/Desktop/xauusd-trader \
  --manifest data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv
```

## BLS without API key

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/events/bls
curl -L --retry 3 --retry-delay 3 \
  -H 'Content-Type: application/json' \
  -X POST \
  -d '{"seriesid":["CUSR0000SA0","CUSR0000SA0L1E","CES0000000001","LNS14000000","LNS11300000"],"startyear":"2017","endyear":"2026"}' \
  'https://api.bls.gov/publicAPI/v2/timeseries/data/' \
  -o ~/Downloads/xauusd_fundamental_event_inbox/events/bls/bls_core_macro_2017_2026.json
```

## FRED macro no-key CSVs

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/fred_macro
cd ~/Downloads/xauusd_fundamental_event_inbox/fred_macro
for s in DFII10 VIXCLS DTWEXBGS DGS10 DGS2 T10YIE T5YIE DFF WALCL BAMLH0A0HYM2; do
  curl -L --retry 3 --retry-delay 3 \
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=${s}" \
    -o "${s}.csv"
done
```

## CFTC COT

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/cot/cftc
cd ~/Downloads/xauusd_fundamental_event_inbox/cot/cftc
for y in $(seq 2009 2026); do
  curl -L --retry 3 --retry-delay 3 \
    -o "fut_disagg_txt_${y}.zip" \
    "https://www.cftc.gov/files/dea/history/fut_disagg_txt_${y}.zip"
done
```

## DXY reference

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/macro_misc/dxy
curl -L --retry 3 --retry-delay 3 \
  "https://stooq.com/q/d/l/?s=dx.f&i=d" \
  -o ~/Downloads/xauusd_fundamental_event_inbox/macro_misc/dxy/stooq_dx_f_dxy_daily.csv
```

## Treasury auctions

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/events/treasury
curl -g -L --retry 3 --retry-delay 3 \
  "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/upcoming_auctions?format=csv&page[size]=1000" \
  -o ~/Downloads/xauusd_fundamental_event_inbox/events/treasury/treasury_upcoming_auctions.csv
```

## Notes

AMarkets files are accepted as reference-only technical files in this inbox, but they are not fundamental/event features. WGC and COT are registered here; Stage115 should build feature-grade COT/WGC parsers.
"""
    path.write_text(text, encoding="utf-8")
    return path


def path_rows(rows: List[Dict[str, Any]], family: str, hints: Optional[set[str]] = None) -> List[Path]:
    result: List[Path] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("source_family") != family:
            continue
        if hints and row.get("parser_hint") not in hints:
            continue
        p = Path(str(row["path"]))
        # Prefer one logical file per digest/name; scan already dedupes but keep safe.
        key = str(p)
        if key not in seen:
            result.append(p)
            seen.add(key)
    return result


def run(root: Path, manifest_path: Optional[Path], out_dir: Optional[Path]) -> Dict[str, Any]:
    downloads = Path.home() / "Downloads"
    inbox = downloads / DEFAULT_INBOX_REL
    normalized_dir = root / NORMALIZED_REL
    report_dir = out_dir or (root / REPORT_REL)
    ensure_dir(normalized_dir)
    ensure_dir(report_dir)

    rows = scan_files(root=root, inbox=inbox, manifest_path=manifest_path)

    # Write corrected classification manifest before normalization.
    classification_csv = report_dir / "stage114b_corrected_file_classification.csv"
    write_csv(classification_csv, rows)

    families: Dict[str, int] = {}
    for row in rows:
        families[row["source_family"]] = families.get(row["source_family"], 0) + 1

    # Normalize by family.
    fred_rows = normalize_fred(path_rows(rows, "fred_macro", {"fred_series_csv"}))
    fred_release_rows = normalize_fred_release_dates(path_rows(rows, "fred_release_calendar", {"fred_release_dates_json"}))
    dxy_rows = normalize_dxy(path_rows(rows, "dxy_reference", {"dxy_csv"}))
    bls_rows = normalize_bls_json(path_rows(rows, "bls", {"bls_json"}))
    bea_rows = normalize_json_shell(path_rows(rows, "bea"), "bea")
    census_rows = normalize_json_shell(path_rows(rows, "census"), "census")
    treasury_rows = normalize_generic_csv(path_rows(rows, "treasury", {"treasury_csv"}), "treasury")
    fomc_rows = normalize_fomc(path_rows(rows, "fomc"))
    cot_rows = normalize_cot_zip(path_rows(rows, "cot_cftc", {"cot_zip"}))
    wgc_etf_rows = read_xlsx_rows([p for p in path_rows(rows, "wgc_gold_etf") if p.suffix.lower() in {".xlsx", ".xls"}], "wgc_gold_etf")
    wgc_cb_rows = read_xlsx_rows([p for p in path_rows(rows, "wgc_central_bank_gold") if p.suffix.lower() in {".xlsx", ".xls"}], "wgc_central_bank_gold")
    spdr_rows = read_xlsx_rows([p for p in path_rows(rows, "spdr_gld") if p.suffix.lower() in {".xlsx", ".xls"}], "spdr_gld")

    outputs = [
        ("fred_macro", normalized_dir / "fred_macro_normalized.csv", fred_rows),
        ("fred_release_calendar", normalized_dir / "fred_release_calendar_normalized.csv", fred_release_rows),
        ("dxy_reference", normalized_dir / "dxy_reference_normalized.csv", dxy_rows),
        ("bls", normalized_dir / "bls_macro_normalized.csv", bls_rows),
        ("bea", normalized_dir / "bea_macro_shell_normalized.csv", bea_rows),
        ("census", normalized_dir / "census_macro_shell_normalized.csv", census_rows),
        ("treasury", normalized_dir / "treasury_auctions_normalized.csv", treasury_rows),
        ("fomc", normalized_dir / "fomc_calendar_extracted.csv", fomc_rows),
        ("cot_cftc", normalized_dir / "cot_cftc_zip_registry.csv", cot_rows),
        ("wgc_gold_etf", normalized_dir / "wgc_gold_etf_xlsx_rows.csv", wgc_etf_rows),
        ("wgc_central_bank_gold", normalized_dir / "wgc_central_bank_gold_xlsx_rows.csv", wgc_cb_rows),
        ("spdr_gld", normalized_dir / "spdr_gld_xlsx_rows.csv", spdr_rows),
    ]

    output_rows: List[Dict[str, Any]] = []
    for family, path, data_rows in outputs:
        if data_rows:
            write_csv(path, data_rows)
        else:
            write_csv(path, [])
        output_rows.append({
            "source_family": family,
            "output_path": str(path),
            "row_count": len(data_rows),
        })
    outputs_csv = report_dir / "stage114b_normalized_outputs.csv"
    write_csv(outputs_csv, output_rows)

    unknown_rows = [r for r in rows if r.get("source_family") == "unknown"]
    unknown_csv = report_dir / "stage114b_remaining_unknown_files.csv"
    write_csv(unknown_csv, unknown_rows)

    readme_path = rebuild_readme(inbox)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS,
        "decision": DECISION,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "manual_inbox_dir": str(inbox),
        "manifest_path": str(manifest_path) if manifest_path else "",
        "input_files_discovered": len(rows),
        "source_family_counts": families,
        "remaining_unknown_count": len(unknown_rows),
        "corrected_classification_csv": str(classification_csv),
        "remaining_unknown_csv": str(unknown_csv),
        "normalized_outputs_csv": str(outputs_csv),
        "normalized_outputs": output_rows,
        "readme_rebuilt": str(readme_path),
        "notes": [
            "Hash-prefixed Stage113 filenames are classified by logical filename.",
            "AMarkets files are recognized as technical reference-only, not fundamental features.",
            "COT zip files are registered; Stage115 should build feature-grade COT parser.",
            "WGC XLSX files are raw-row extracted; Stage115 should build feature-grade WGC parser.",
        ],
        "next": [
            "Inspect remaining_unknown_count. It should be near zero or only reference docs.",
            "If FRED/DXY rows are now non-trivial, continue to Stage115 COT/WGC feature parser.",
            "No order, no MT5, no EA change from this stage.",
        ],
    }
    summary_json = report_dir / "stage114b_classification_and_macro_event_hotfix_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report_md = report_dir / "stage114b_classification_and_macro_event_hotfix_report.md"
    report_md.write_text(
        "# Stage114B Classification and Macro/Event Hotfix\n\n"
        f"- status: `{STATUS}`\n"
        f"- decision: `{DECISION}`\n"
        f"- input_files_discovered: `{len(rows)}`\n"
        f"- remaining_unknown_count: `{len(unknown_rows)}`\n\n"
        "## Source family counts\n\n"
        + "\n".join(f"- `{k}`: {v}" for k, v in sorted(families.items()))
        + "\n\n## Outputs\n\n"
        + "\n".join(f"- `{r['source_family']}`: {r['row_count']} rows -> `{r['output_path']}`" for r in output_rows)
        + "\n\n## Interpretation\n\n"
        "This stage fixes classification and macro/event shell normalization only. It does not promote any trading candidate.\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=STAGE)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--manifest", default="data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv")
    parser.add_argument("--out", default=None, help="Report output directory")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    manifest = (root / args.manifest).resolve() if args.manifest else None
    out_dir = Path(args.out).expanduser().resolve() if args.out else None
    run(root=root, manifest_path=manifest, out_dir=out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
