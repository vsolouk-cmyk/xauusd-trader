#!/usr/bin/env python3
"""
Stage114_OFFICIAL_EVENT_AND_FUNDAMENTAL_NORMALIZER

Infrastructure-only normalizer for XAUUSD fundamental/event inbox files.
- No order, no MT5, no EA, no broker connection.
- Scans a flat manual inbox and nested buckets.
- Reads Stage113 manifest if present, but does not depend on its exact schema.
- Produces normalized CSVs under data/fundamental_event_inbox/normalized/.
- Rebuilds README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md inside the manual inbox with download commands.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage114_OFFICIAL_EVENT_AND_FUNDAMENTAL_NORMALIZER"
STATUS = "STAGE114_COMPLETE_NORMALIZER_READY_NO_PROMOTION"
DECISION = "STAGE114_NORMALIZED_FUNDAMENTAL_EVENT_DATA_READY_NO_ORDER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE114",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]

DEFAULT_INBOX_REL = "xauusd_fundamental_event_inbox"
NORMALIZED_REL = "data/fundamental_event_inbox/normalized"
REPORT_REL = "reports/stage114_official_event_and_fundamental_normalizer"

FRED_SERIES_NAMES = {
    "DFII10": "10-Year Treasury Inflation-Indexed Security, constant maturity",
    "VIXCLS": "CBOE Volatility Index: VIX",
    "DTWEXBGS": "Nominal Broad U.S. Dollar Index",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "DGS2": "2-Year Treasury Constant Maturity Rate",
    "T10YIE": "10-Year Breakeven Inflation Rate",
    "DFF": "Effective Federal Funds Rate",
    "WALCL": "Federal Reserve Total Assets",
}

BLS_SERIES_NAMES = {
    "CUSR0000SA0": "CPI-U All Items, seasonally adjusted",
    "CUSR0000SA0L1E": "CPI-U All Items Less Food and Energy, seasonally adjusted",
    "CES0000000001": "Total nonfarm payroll employment",
    "LNS14000000": "Unemployment rate",
    "LNS11300000": "Labor force participation rate",
}

SKIP_DIR_NAMES = {"_processed", "_rejected", ".DS_Store", "__MACOSX"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, limit_mb: Optional[int] = None) -> str:
    h = hashlib.sha256()
    max_bytes = None if limit_mb is None else limit_mb * 1024 * 1024
    read_bytes = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            if max_bytes is not None and read_bytes + len(chunk) > max_bytes:
                chunk = chunk[: max(0, max_bytes - read_bytes)]
            h.update(chunk)
            read_bytes += len(chunk)
            if max_bytes is not None and read_bytes >= max_bytes:
                break
    return h.hexdigest()


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in {".", "NA", "N/A", "nan", "NaN", "null", "None"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as f:
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
                sample = f.read(4096)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
                return list(csv.DictReader(f, dialect=dialect))
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"could not read csv {path}: {last_err}")


def infer_source(path: Path) -> Tuple[str, str, str]:
    """Return source_family, canonical_bucket, parser_hint."""
    name = path.name.lower()
    rel = str(path).lower()
    suffix = path.suffix.lower()

    if name.startswith("amarkets_xauusd_") and suffix == ".csv":
        return "technical_amarkets", "technical/amarkets", "amarkets_bars"
    if re.match(r"^(dfii10|vixcls|dtwexbgs|dgs10|dgs2|t10yie|dff|walcl)\.csv$", name):
        return "fred_macro", "fred_macro", "fred_series"
    if "stooq" in name or name in {"us dollar index historical data.csv", "dxy.csv"} or "dxy" in rel:
        if suffix == ".csv":
            return "dxy_reference", "macro_misc/dxy", "dxy_csv"
    if "bls" in rel and suffix in {".json", ".xlsx", ".csv"}:
        return "bls", "events/bls", "bls_json" if suffix == ".json" else "bls_other"
    if "bea" in rel and suffix in {".json", ".csv", ".xlsx"}:
        return "bea", "events/bea", "generic_event_data"
    if "census" in rel and suffix in {".json", ".csv", ".xlsx"}:
        return "census", "events/census", "generic_event_data"
    if "fomc" in rel or "fomc" in name:
        return "fomc", "events/fomc", "fomc_html_or_csv"
    if "treasury" in rel or "auction" in name:
        return "treasury", "events/treasury", "treasury_csv" if suffix == ".csv" else "generic_event_data"
    if name.startswith("fut_disagg_txt_") and suffix == ".zip":
        return "cot_cftc", "cot/cftc", "cot_zip"
    if "cot_positioning_normalized" in name and suffix == ".csv":
        return "cot_cftc", "cot/cftc", "cot_normalized_existing"
    if "etf" in name and suffix in {".xlsx", ".xls", ".csv"}:
        return "wgc_gold_etf", "gold_etf/wgc", "wgc_etf_xlsx"
    if "etf" in name and suffix == ".pdf":
        return "wgc_gold_etf_methodology", "gold_etf/wgc", "reference_pdf"
    if "world_official_gold_holdings" in name or "changes_latest" in name or "quarterly_gold" in name:
        return "wgc_central_bank_gold", "central_bank_gold", "wgc_cb_xlsx"
    if "gld" in rel or "spdr" in rel:
        return "spdr_gld", "gld/spdr", "spdr_gld"
    if suffix == ".pdf":
        return "reference_doc", "docs_or_reference", "reference_pdf"
    return "unknown", "unknown", "unknown"


def scan_files(root: Path, inbox: Path, manifest_path: Optional[Path]) -> List[Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}

    roots_to_scan = [inbox, root / "data" / "fundamental_event_inbox" / "raw", root / "data" / "external_frontiers"]
    for base in roots_to_scan:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.name.startswith(".") or path.name == "data.txt":
                continue
            try:
                digest = sha256_file(path, limit_mb=32)
            except Exception:
                digest = f"unreadable:{path}"
            source_family, bucket, hint = infer_source(path)
            key = digest + "|" + path.name
            candidates[key] = {
                "path": str(path),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256_partial_or_full": digest,
                "source_family": source_family,
                "canonical_bucket": bucket,
                "parser_hint": hint,
                "discovered_from": str(base),
            }

    if manifest_path and manifest_path.exists():
        try:
            for row in read_csv_dicts(manifest_path):
                path_value = None
                for k in ["path", "file_path", "project_path", "dest_path", "source_path", "absolute_path"]:
                    if row.get(k):
                        path_value = row[k]
                        break
                if path_value:
                    path = Path(path_value).expanduser()
                    if path.exists() and path.is_file():
                        digest = sha256_file(path, limit_mb=32)
                        source_family, bucket, hint = infer_source(path)
                        key = digest + "|" + path.name
                        candidates.setdefault(key, {
                            "path": str(path),
                            "filename": path.name,
                            "size_bytes": path.stat().st_size,
                            "sha256_partial_or_full": digest,
                            "source_family": source_family,
                            "canonical_bucket": bucket,
                            "parser_hint": hint,
                            "discovered_from": str(manifest_path),
                        })
        except Exception as exc:
            candidates[f"manifest_error|{manifest_path}"] = {
                "path": str(manifest_path),
                "filename": manifest_path.name,
                "size_bytes": manifest_path.stat().st_size if manifest_path.exists() else 0,
                "sha256_partial_or_full": "",
                "source_family": "manifest_error",
                "canonical_bucket": "manifest",
                "parser_hint": "manifest_error",
                "discovered_from": str(manifest_path),
                "error": str(exc),
            }

    return sorted(candidates.values(), key=lambda r: (r.get("source_family", ""), r.get("filename", "")))


def normalize_fred(files: List[Path]) -> List[Dict[str, Any]]:
    rows_out: List[Dict[str, Any]] = []
    for path in files:
        series_id = path.stem.upper()
        try:
            rows = read_csv_dicts(path)
            for row in rows:
                # FRED CSV usually: DATE, SERIES_ID
                date_val = row.get("DATE") or row.get("date") or row.get("Date")
                value = row.get(series_id) or row.get("VALUE") or row.get("value")
                if not date_val:
                    continue
                rows_out.append({
                    "date": date_val,
                    "series_id": series_id,
                    "series_name": FRED_SERIES_NAMES.get(series_id, ""),
                    "value": safe_float(value),
                    "raw_value": "" if value is None else str(value),
                    "source_file": str(path),
                    "source_family": "fred_macro",
                })
        except Exception as exc:
            rows_out.append({"date": "", "series_id": series_id, "series_name": "", "value": "", "raw_value": "", "source_file": str(path), "source_family": "fred_macro", "error": str(exc)})
    return rows_out


def normalize_dxy(files: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            for row in read_csv_dicts(path):
                lower = {k.lower().strip(): v for k, v in row.items() if k is not None}
                date_val = lower.get("date") or lower.get("data") or lower.get("time")
                close = lower.get("close") or lower.get("price") or lower.get("last")
                out.append({
                    "date": date_val or "",
                    "open": safe_float(lower.get("open")),
                    "high": safe_float(lower.get("high")),
                    "low": safe_float(lower.get("low")),
                    "close": safe_float(close),
                    "volume": safe_float(lower.get("volume")) if lower.get("volume") else "",
                    "source_file": str(path),
                    "source_family": "dxy_reference",
                })
        except Exception as exc:
            out.append({"date": "", "open": "", "high": "", "low": "", "close": "", "volume": "", "source_file": str(path), "source_family": "dxy_reference", "error": str(exc)})
    return out


def period_to_date(year: str, period: str) -> str:
    if period and re.fullmatch(r"M\d{2}", period):
        return f"{year}-{int(period[1:]):02d}-01"
    if period and period.startswith("Q") and period[1:].isdigit():
        q = int(period[1:])
        m = {1: 1, 2: 4, 3: 7, 4: 10}.get(q, 1)
        return f"{year}-{m:02d}-01"
    return f"{year}-01-01"


def normalize_bls_json(files: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            series_list = data.get("Results", {}).get("series", [])
            for s in series_list:
                sid = s.get("seriesID") or s.get("seriesId") or ""
                for item in s.get("data", []):
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


def normalize_generic_csv(files: List[Path], family: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            rows = read_csv_dicts(path)
            for i, row in enumerate(rows):
                compact = {str(k).strip(): v for k, v in row.items() if k is not None}
                # Keep a small normalized shell while preserving source path and raw json row.
                date_candidate = ""
                for k, v in compact.items():
                    lk = k.lower()
                    if "date" in lk or lk in {"record_date", "auction_date", "issue_date", "maturity_date"}:
                        date_candidate = str(v)
                        break
                out.append({
                    "date": date_candidate,
                    "source_family": family,
                    "source_file": str(path),
                    "row_index": i,
                    "raw_row_json": json.dumps(compact, ensure_ascii=False),
                })
        except Exception as exc:
            out.append({"date": "", "source_family": family, "source_file": str(path), "row_index": "", "raw_row_json": "", "error": str(exc)})
    return out


def normalize_fomc(files: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    date_re = re.compile(r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:-\d{1,2})?,\s+\d{4}", re.I)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:2_000_000]
            matches = sorted(set(m.group(0) for m in date_re.finditer(text)))
            if matches:
                for m in matches:
                    out.append({"event_date_text": m, "source_family": "fomc", "source_file": str(path), "event_type": "fomc_calendar_text_match"})
            else:
                out.append({"event_date_text": "", "source_family": "fomc", "source_file": str(path), "event_type": "fomc_source_snapshot_no_date_parse"})
        except Exception as exc:
            out.append({"event_date_text": "", "source_family": "fomc", "source_file": str(path), "event_type": "error", "error": str(exc)})
    return out


def try_read_xlsx_basic(path: Path, source_family: str) -> List[Dict[str, Any]]:
    try:
        import openpyxl  # type: ignore
    except Exception as exc:
        return [{"source_family": source_family, "source_file": str(path), "sheet": "", "row_index": "", "raw_row_json": "", "error": f"openpyxl_not_available: {exc}"}]
    out: List[Dict[str, Any]] = []
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets[:10]:
            rows_iter = ws.iter_rows(values_only=True)
            headers = None
            for idx, values in enumerate(rows_iter):
                vals = list(values)
                non_empty = [v for v in vals if v not in (None, "")]
                if len(non_empty) < 2:
                    continue
                if headers is None:
                    headers = [str(v).strip() if v is not None else f"col_{i}" for i, v in enumerate(vals)]
                    continue
                row = {headers[i] if i < len(headers) else f"col_{i}": vals[i] for i in range(len(vals))}
                out.append({
                    "source_family": source_family,
                    "source_file": str(path),
                    "sheet": ws.title,
                    "row_index": idx,
                    "raw_row_json": json.dumps({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}, ensure_ascii=False, default=str),
                })
                if len(out) >= 20000:
                    break
            if len(out) >= 20000:
                break
        wb.close()
    except Exception as exc:
        out.append({"source_family": source_family, "source_file": str(path), "sheet": "", "row_index": "", "raw_row_json": "", "error": str(exc)})
    return out


def normalize_cot_zip(files: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            with zipfile.ZipFile(path) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                out.append({
                    "source_family": "cot_cftc",
                    "source_file": str(path),
                    "zip_member_count": len(names),
                    "zip_members": ";".join(names[:20]),
                    "note": "Stage114 registered COT zip. Full COT parsing should use existing stage95 or Stage115 dedicated COT parser.",
                })
        except Exception as exc:
            out.append({"source_family": "cot_cftc", "source_file": str(path), "zip_member_count": "", "zip_members": "", "note": "", "error": str(exc)})
    return out


def rebuild_readme(inbox: Path) -> Path:
    ensure_dir(inbox)
    readme = inbox / "README_XAUUSD_FUNDAMENTAL_EVENT_INBOX.md"
    text = f"""# XAUUSD Fundamental/Event Inbox Download and Normalize Guide

Generated by `Stage114_OFFICIAL_EVENT_AND_FUNDAMENTAL_NORMALIZER`.

## Operating rule

Put all manually downloaded files in this inbox. Flat root files are accepted. Subfolders are optional. The normalizer scans both root and nested folders.

## Main commands

Run Stage113 after downloads:

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage113_fundamental_event_inbox_unifier.py \\
  --root /Users/vahid/Desktop/xauusd-trader
```

Run Stage114 normalizer:

```bash
cd /Users/vahid/Desktop/xauusd-trader
python3 app/stage114_official_event_and_fundamental_normalizer.py \\
  --root /Users/vahid/Desktop/xauusd-trader \\
  --manifest data/fundamental_event_inbox/manifests/stage113_fundamental_event_file_manifest.csv
```

## BLS without API key

BLS basic v2 POST works without a registration key over shorter windows.

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/events/bls
curl -L --retry 3 --retry-delay 3 \\
  -H 'Content-Type: application/json' \\
  -X POST \\
  -d '{{"seriesid":["CUSR0000SA0","CUSR0000SA0L1E","CES0000000001","LNS14000000","LNS11300000"],"startyear":"2017","endyear":"2026"}}' \\
  'https://api.bls.gov/publicAPI/v2/timeseries/data/' \\
  -o ~/Downloads/xauusd_fundamental_event_inbox/events/bls/bls_core_macro_2017_2026.json
```

## CFTC COT

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/cot/cftc
cd ~/Downloads/xauusd_fundamental_event_inbox/cot/cftc
for y in $(seq 2009 2026); do
  curl -L --retry 3 --retry-delay 3 \\
    -o "fut_disagg_txt_${{y}}.zip" \\
    "https://www.cftc.gov/files/dea/history/fut_disagg_txt_${{y}}.zip"
done
```

## Treasury auctions

Use `-g` because the URL contains `page[size]`.

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/events/treasury
curl -g -L --retry 3 --retry-delay 3 \\
  "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/upcoming_auctions?format=csv&page[size]=1000" \\
  -o ~/Downloads/xauusd_fundamental_event_inbox/events/treasury/treasury_upcoming_auctions.csv
```

## FRED macro CSVs without API key

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/fred_macro
cd ~/Downloads/xauusd_fundamental_event_inbox/fred_macro
for s in DFII10 VIXCLS DTWEXBGS DGS10 DGS2 T10YIE DFF WALCL; do
  curl -L --retry 3 --retry-delay 3 \\
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=${{s}}" \\
    -o "${{s}}.csv"
done
```

## FRED release calendar with API key

```bash
FRED_API_KEY="PUT_YOUR_FRED_API_KEY_HERE"
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/events/fred
curl -L --retry 3 --retry-delay 3 \\
  "https://api.stlouisfed.org/fred/releases/dates?api_key=${{FRED_API_KEY}}&file_type=json&include_release_dates_with_no_data=true&realtime_start=2009-01-01&realtime_end=2026-12-31" \\
  -o ~/Downloads/xauusd_fundamental_event_inbox/events/fred/fred_release_dates_2009_2026.json
```

## DXY reference

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/macro_misc/dxy
curl -L --retry 3 --retry-delay 3 \\
  "https://stooq.com/q/d/l/?s=dx.f&i=d" \\
  -o ~/Downloads/xauusd_fundamental_event_inbox/macro_misc/dxy/stooq_dx_f_dxy_daily.csv
```

## WGC ETF and central bank gold

Command-line direct downloads may fail with HTML/403. Always check the file type after download.

```bash
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/gold_etf/wgc
mkdir -p ~/Downloads/xauusd_fundamental_event_inbox/central_bank_gold

curl -L --retry 3 --retry-delay 3 \\
  -A "Mozilla/5.0" \\
  -e "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows" \\
  "https://www.gold.org/download/file/20888/ETF_Flows_2026-06-02_1536.xlsx" \\
  -o ~/Downloads/xauusd_fundamental_event_inbox/gold_etf/wgc/ETF_Flows_2026-06-02_1536.xlsx

curl -L --retry 3 --retry-delay 3 \\
  -A "Mozilla/5.0" \\
  -e "https://www.gold.org/goldhub/data/gold-reserves-by-country" \\
  "https://www.gold.org/download/file/7739/World_official_gold_holdings_as_of_Jun2026_IFS.xlsx" \\
  -o ~/Downloads/xauusd_fundamental_event_inbox/central_bank_gold/World_official_gold_holdings_as_of_Jun2026_IFS.xlsx

file ~/Downloads/xauusd_fundamental_event_inbox/gold_etf/wgc/ETF_Flows_2026-06-02_1536.xlsx
file ~/Downloads/xauusd_fundamental_event_inbox/central_bank_gold/World_official_gold_holdings_as_of_Jun2026_IFS.xlsx
```

If the output is `HTML document`, download manually from:

- https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows
- https://www.gold.org/goldhub/data/gold-reserves-by-country

## Git storage rule

Raw and normalized inbox data should remain gitignored. Commit code/config/docs/tests, not large data.
"""
    readme.write_text(text, encoding="utf-8")
    return readme


def run(args: argparse.Namespace) -> Dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    downloads_dir = Path(args.downloads_dir).expanduser().resolve() if args.downloads_dir else Path.home() / "Downloads"
    inbox = Path(args.inbox).expanduser().resolve() if args.inbox else downloads_dir / DEFAULT_INBOX_REL
    normalized_dir = (root / args.normalized_dir).resolve() if args.normalized_dir else root / NORMALIZED_REL
    report_dir = (root / args.out).resolve() if args.out else root / REPORT_REL
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else root / "data" / "fundamental_event_inbox" / "manifests" / "stage113_fundamental_event_file_manifest.csv"

    ensure_dir(normalized_dir)
    ensure_dir(report_dir)

    discovered = scan_files(root, inbox, manifest_path)
    write_csv(report_dir / "stage114_discovered_input_files.csv", discovered)

    paths_by_hint: Dict[str, List[Path]] = {}
    for row in discovered:
        hint = row.get("parser_hint", "unknown")
        p = Path(str(row.get("path", "")))
        if p.exists() and p.is_file():
            paths_by_hint.setdefault(str(hint), []).append(p)

    outputs: List[Dict[str, Any]] = []

    fred_rows = normalize_fred(paths_by_hint.get("fred_series", []))
    if fred_rows:
        out = normalized_dir / "fred_macro_normalized.csv"
        write_csv(out, fred_rows)
        outputs.append({"dataset": "fred_macro", "path": str(out), "rows": len(fred_rows)})

    dxy_rows = normalize_dxy(paths_by_hint.get("dxy_csv", []))
    if dxy_rows:
        out = normalized_dir / "dxy_reference_normalized.csv"
        write_csv(out, dxy_rows)
        outputs.append({"dataset": "dxy_reference", "path": str(out), "rows": len(dxy_rows)})

    bls_rows = normalize_bls_json(paths_by_hint.get("bls_json", []))
    if bls_rows:
        out = normalized_dir / "bls_macro_normalized.csv"
        write_csv(out, bls_rows)
        outputs.append({"dataset": "bls_macro", "path": str(out), "rows": len(bls_rows)})

    treasury_rows = normalize_generic_csv(paths_by_hint.get("treasury_csv", []), "treasury")
    if treasury_rows:
        out = normalized_dir / "treasury_auctions_normalized.csv"
        write_csv(out, treasury_rows)
        outputs.append({"dataset": "treasury_auctions", "path": str(out), "rows": len(treasury_rows)})

    fomc_rows = normalize_fomc(paths_by_hint.get("fomc_html_or_csv", []))
    if fomc_rows:
        out = normalized_dir / "fomc_calendar_extracted.csv"
        write_csv(out, fomc_rows)
        outputs.append({"dataset": "fomc_calendar", "path": str(out), "rows": len(fomc_rows)})

    cot_rows = normalize_cot_zip(paths_by_hint.get("cot_zip", []))
    if cot_rows:
        out = normalized_dir / "cot_cftc_zip_registry.csv"
        write_csv(out, cot_rows)
        outputs.append({"dataset": "cot_cftc_zip_registry", "path": str(out), "rows": len(cot_rows)})

    xlsx_rows: List[Dict[str, Any]] = []
    for p in paths_by_hint.get("wgc_etf_xlsx", []):
        xlsx_rows.extend(try_read_xlsx_basic(p, "wgc_gold_etf"))
    if xlsx_rows:
        out = normalized_dir / "wgc_gold_etf_xlsx_rows.csv"
        write_csv(out, xlsx_rows)
        outputs.append({"dataset": "wgc_gold_etf_raw_rows", "path": str(out), "rows": len(xlsx_rows)})

    cb_rows: List[Dict[str, Any]] = []
    for p in paths_by_hint.get("wgc_cb_xlsx", []):
        cb_rows.extend(try_read_xlsx_basic(p, "wgc_central_bank_gold"))
    if cb_rows:
        out = normalized_dir / "wgc_central_bank_gold_xlsx_rows.csv"
        write_csv(out, cb_rows)
        outputs.append({"dataset": "wgc_central_bank_gold_raw_rows", "path": str(out), "rows": len(cb_rows)})

    write_csv(report_dir / "stage114_normalized_outputs.csv", outputs)
    readme_path = rebuild_readme(inbox)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS,
        "decision": DECISION,
        "classification": "INFRASTRUCTURE_NORMALIZER_ONLY_NO_ORDER",
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "manual_inbox_dir": str(inbox),
        "manifest_path": str(manifest_path),
        "normalized_dir": str(normalized_dir),
        "report_dir": str(report_dir),
        "input_files_discovered": len([r for r in discovered if r.get("source_family") != "manifest_error"]),
        "unknown_files": len([r for r in discovered if r.get("source_family") == "unknown"]),
        "normalized_outputs": outputs,
        "readme_rebuilt": str(readme_path),
        "next": [
            "Review stage114_discovered_input_files.csv for unknown or misclassified files.",
            "Review normalized CSV outputs under data/fundamental_event_inbox/normalized/.",
            "Use a dedicated Stage115 parser for COT/WGC feature-grade transformations if raw rows are present.",
        ],
    }
    (report_dir / "stage114_official_event_and_fundamental_normalizer_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [
        f"# {STAGE}",
        "",
        f"- status: `{STATUS}`",
        f"- decision: `{DECISION}`",
        "- order/broker/MT5/EA: blocked",
        "",
        f"Input files discovered: {summary['input_files_discovered']}",
        f"Unknown files: {summary['unknown_files']}",
        "",
        "## Normalized outputs",
        "",
    ]
    for o in outputs:
        md.append(f"- `{o['dataset']}` rows={o['rows']} path=`{o['path']}`")
    if not outputs:
        md.append("- No normalized output generated. Add/download source files and rerun Stage113 then Stage114.")
    (report_dir / "stage114_official_event_and_fundamental_normalizer_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"stage": STAGE, "status": STATUS, "decision": DECISION, "input_files_discovered": summary["input_files_discovered"], "normalized_output_count": len(outputs), "summary": str(report_dir / "stage114_official_event_and_fundamental_normalizer_summary.json")}, ensure_ascii=False))
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=STAGE)
    p.add_argument("--root", default=".")
    p.add_argument("--downloads-dir", default=None)
    p.add_argument("--inbox", default=None)
    p.add_argument("--manifest", default=None)
    p.add_argument("--normalized-dir", default=None, help="Relative to root unless absolute-like Path is supplied by caller")
    p.add_argument("--out", default=None, help="Relative to root report directory")
    return p


def main() -> int:
    args = build_parser().parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
