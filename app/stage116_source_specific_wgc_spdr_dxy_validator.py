#!/usr/bin/env python3
"""Stage116 source-specific WGC/SPDR/DXY validator for XAUUSD project.

Purpose:
- Validate / repair direct DXY source and build a final dollar-pressure series.
- Convert WGC ETF, WGC central-bank, SPDR GLD xlsx files into validated long-form
  feature candidates with sheet/metric/date provenance.
- Keep all trading/order surfaces blocked. This script is data-only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import openpyxl  # type: ignore
except Exception:  # pragma: no cover
    openpyxl = None

STAGE = "Stage116_SOURCE_SPECIFIC_WGC_SPDR_DXY_VALIDATOR"
STATUS = "STAGE116_COMPLETE_SOURCE_VALIDATION_READY_NO_PROMOTION"
DECISION = "STAGE116_SOURCE_SPECIFIC_VALIDATION_READY_NO_ORDER"
CLASSIFICATION = "SOURCE_VALIDATOR_ONLY_NO_ORDER"
HARD_BLOCKS = [
    "NO_AUTOMATED_ORDER",
    "NO_PAPER_ORDER",
    "NO_BROKER_CONNECTION",
    "NO_MT5_OR_EA_CHANGE_FROM_STAGE116",
    "NO_EA_CHANGE",
    "NO_PAPER_LIVE",
    "NO_LIVE",
]


def set_csv_limit() -> None:
    max_size = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_size)
            return
        except OverflowError:
            max_size = int(max_size / 10)


set_csv_limit()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    ensure_dir(path.parent)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def read_csv_dicts(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with path.open("r", newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except Exception:
            continue
    return []


def safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if math.isfinite(float(x)):
            return float(x)
        return None
    s = str(x).strip().replace(",", "")
    if not s or s in {".", "-", "--", "N/A", "NA", "null", "None"}:
        return None
    s = s.replace("%", "")
    try:
        v = float(s)
    except Exception:
        return None
    if math.isfinite(v):
        return v
    return None


def parse_date(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, dt.datetime):
        return x.date().isoformat()
    if isinstance(x, dt.date):
        return x.isoformat()
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    # normalize unicode left-to-right oddities without overreaching
    s = s.replace("\u200e", "").replace("\u200f", "")
    fmts = [
        "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y",
        "%d-%b-%Y", "%Y.%m.%d", "%m-%d-%Y", "%d-%m-%Y",
    ]
    for fmt in fmts:
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    # Month-year only -> month start
    for fmt in ("%b %Y", "%B %Y", "%Y-%m", "%Y/%m"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    # Excel serial date fallback
    fv = safe_float(s)
    if fv is not None and 20000 < fv < 60000:
        try:
            return (dt.date(1899, 12, 30) + dt.timedelta(days=int(fv))).isoformat()
        except Exception:
            return None
    return None


def normalize_metric_name(s: Any) -> str:
    t = str(s or "metric").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t or "metric"


def looks_like_html(path: Path) -> bool:
    try:
        head = path.read_bytes()[:512].lower()
    except Exception:
        return False
    return b"<html" in head or b"<!doctype html" in head or b"access denied" in head or b"forbidden" in head


@dataclass
class DxyResult:
    rows: List[Dict[str, Any]]
    source_path: str
    source_mode: str
    valid_close_rows: int
    valid: bool
    note: str


def find_dxy_candidates(root: Path, inbox: Path) -> List[Path]:
    pats = [
        inbox / "macro_misc" / "dxy" / "stooq_dx_f_dxy_daily.csv",
        inbox / "macro_misc" / "dxy" / "US Dollar Index Historical Data.csv",
        root / "data" / "fundamental_event_inbox" / "normalized" / "dxy_reference_normalized.csv",
    ]
    # add any dxy-ish csv under inbox
    for p in list((inbox / "macro_misc" / "dxy").glob("*.csv")) if (inbox / "macro_misc" / "dxy").exists() else []:
        if p not in pats:
            pats.append(p)
    return [p for p in pats if p.exists()]


def parse_direct_dxy(path: Path) -> DxyResult:
    if not path.exists():
        return DxyResult([], str(path), "MISSING", 0, False, "missing")
    if looks_like_html(path):
        return DxyResult([], str(path), "HTML_OR_BLOCKED", 0, False, "file looks like html/blocked output")
    rows = read_csv_dicts(path)
    out: List[Dict[str, Any]] = []
    if not rows:
        return DxyResult([], str(path), "EMPTY_OR_UNREADABLE", 0, False, "csv unreadable or empty")
    headers = list(rows[0].keys())
    lower = {h.lower().strip(): h for h in headers}
    date_col = None
    for k in ("date", "time", "datetime", "timestamp"):
        if k in lower:
            date_col = lower[k]
            break
    if date_col is None:
        for h in headers:
            if "date" in h.lower():
                date_col = h
                break
    price_cols = []
    for k in ("close", "price", "last", "value", "dxy", "us dollar index", "dxy_reference"):
        if k in lower:
            price_cols.append(lower[k])
    if not price_cols:
        for h in headers:
            lh = h.lower()
            if any(tok in lh for tok in ("close", "price", "value")):
                price_cols.append(h)
    if date_col is None or not price_cols:
        return DxyResult([], str(path), "DIRECT_DXY_SCHEMA_UNRECOGNIZED", 0, False, f"headers={headers[:20]}")
    for r in rows:
        d = parse_date(r.get(date_col))
        v = None
        used_col = ""
        for c in price_cols:
            v = safe_float(r.get(c))
            if v is not None:
                used_col = c
                break
        if d and v is not None:
            out.append({"date": d, "direct_dxy_close": v, "direct_dxy_metric": used_col, "source_path": str(path)})
    # dedupe by date
    by_date: Dict[str, Dict[str, Any]] = {}
    for row in out:
        by_date[row["date"]] = row
    out = [by_date[k] for k in sorted(by_date)]
    valid = len(out) >= 50
    mode = "DIRECT_DXY_VALID" if valid else "DIRECT_DXY_INVALID_OR_TOO_SHORT"
    return DxyResult(out, str(path), mode, len(out), valid, "")


def load_fallback_dtwexbgs(root: Path) -> List[Dict[str, Any]]:
    candidates = [
        root / "data" / "fundamental_event_inbox" / "features" / "stage115_fred_macro_daily_wide.csv",
        root / "data" / "fundamental_event_inbox" / "features" / "stage115_daily_macro_feature_panel.csv",
        root / "data" / "fundamental_event_inbox" / "normalized" / "fred_macro_normalized.csv",
    ]
    for p in candidates:
        rows = read_csv_dicts(p)
        if not rows:
            continue
        headers = list(rows[0].keys())
        lower = {h.lower(): h for h in headers}
        date_col = lower.get("date") or lower.get("utc_date") or lower.get("time")
        val_col = None
        for name in ("DTWEXBGS", "dtwexbgs", "dollar_pressure_index", "value"):
            if name in headers:
                val_col = name
                break
            if name.lower() in lower:
                val_col = lower[name.lower()]
                break
        # normalized long form likely series_id,value,date
        series_col = lower.get("series_id") or lower.get("series") or lower.get("metric")
        out: List[Dict[str, Any]] = []
        for r in rows:
            if series_col and str(r.get(series_col, "")).upper() != "DTWEXBGS":
                continue
            d = parse_date(r.get(date_col)) if date_col else None
            v = safe_float(r.get(val_col)) if val_col else None
            if d and v is not None:
                out.append({"date": d, "dollar_pressure_index": v, "source": "DTWEXBGS_FRED_FALLBACK", "source_path": str(p)})
        if len(out) >= 50:
            by_date = {r["date"]: r for r in out}
            return [by_date[k] for k in sorted(by_date)]
    return []


def build_dollar_pressure(root: Path, inbox: Path, feature_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    candidates = find_dxy_candidates(root, inbox)
    dxy_results = [parse_direct_dxy(p) for p in candidates]
    direct = next((r for r in dxy_results if r.valid), None)
    if direct:
        rows = [{"date": r["date"], "dollar_pressure_index": r["direct_dxy_close"], "source": "DIRECT_DXY", "source_path": r["source_path"]} for r in direct.rows]
        meta = {
            "direct_dxy_valid": True,
            "dxy_source_mode": direct.source_mode,
            "dxy_source_path": direct.source_path,
            "dxy_valid_close_rows": direct.valid_close_rows,
            "dxy_fallback_active": False,
            "dxy_candidates_checked": [r.source_path for r in dxy_results],
        }
    else:
        rows = load_fallback_dtwexbgs(root)
        best = dxy_results[0] if dxy_results else DxyResult([], "", "NO_DIRECT_DXY_FILE", 0, False, "")
        meta = {
            "direct_dxy_valid": False,
            "dxy_source_mode": best.source_mode,
            "dxy_source_path": best.source_path,
            "dxy_valid_close_rows": best.valid_close_rows,
            "dxy_fallback_active": True,
            "dxy_fallback_rows": len(rows),
            "dxy_candidates_checked": [r.source_path for r in dxy_results],
        }
    write_csv(feature_dir / "stage116_validated_dollar_pressure.csv", rows,
              ["date", "dollar_pressure_index", "source", "source_path"])
    dxy_diag_rows = [{"source_path": r.source_path, "source_mode": r.source_mode, "valid_close_rows": r.valid_close_rows, "valid": r.valid, "note": r.note} for r in dxy_results]
    write_csv(feature_dir / "stage116_dxy_source_diagnostics.csv", dxy_diag_rows,
              ["source_path", "source_mode", "valid_close_rows", "valid", "note"])
    return rows, meta


def find_xlsx_files(inbox: Path, family: str) -> List[Path]:
    if family == "wgc_etf":
        dirs = [inbox / "gold_etf" / "wgc"]
        tokens = ["ETF", "Flows"]
    elif family == "central_bank":
        dirs = [inbox / "central_bank_gold"]
        tokens = ["gold", "holdings", "changes", "quarterly", "reserves"]
    elif family == "spdr":
        dirs = [inbox / "gld" / "spdr"]
        tokens = ["spdr", "gld", "historical", "archive"]
    else:
        return []
    out: List[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        for p in d.glob("*.xlsx"):
            name = p.name.lower()
            if family == "wgc_etf" and ("methodology" in name):
                continue
            if family == "wgc_etf" and ("etf" in name or "flow" in name):
                out.append(p)
            elif family == "central_bank" and any(t in name for t in ("official", "changes", "quarterly", "reserves", "holdings")):
                out.append(p)
            elif family == "spdr" and ("spdr" in name or "gld" in name or "archive" in name):
                out.append(p)
    return sorted(set(out))


def cell_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def infer_header_and_cols(rows: List[Tuple[Any, ...]]) -> Tuple[int, List[int], List[int], List[str]]:
    max_cols = max((len(r) for r in rows), default=0)
    best = (0, [], [], [])
    best_score = -1
    search_rows = min(len(rows), 40)
    for hidx in range(search_rows):
        header = list(rows[hidx]) + [None] * max(0, max_cols - len(rows[hidx]))
        headers = [cell_text(x) for x in header]
        sample = rows[hidx + 1: hidx + 80]
        date_cols: List[int] = []
        numeric_cols: List[int] = []
        for c in range(max_cols):
            vals = [r[c] if c < len(r) else None for r in sample]
            date_hits = sum(1 for v in vals if parse_date(v))
            num_hits = sum(1 for v in vals if safe_float(v) is not None)
            htxt = headers[c].lower() if c < len(headers) else ""
            if date_hits >= max(2, len(sample)//12) or any(tok in htxt for tok in ("date", "month", "period")):
                date_cols.append(c)
            if num_hits >= max(3, len(sample)//8):
                numeric_cols.append(c)
        text_headers = sum(1 for h in headers if h and len(h) <= 80)
        score = len(date_cols) * 5 + len(numeric_cols) * 2 + text_headers
        if score > best_score and numeric_cols:
            best_score = score
            best = (hidx, date_cols, numeric_cols, headers)
    return best


def extract_xlsx_long(path: Path, source_family: str, max_rows_per_sheet: int = 50000) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if openpyxl is None:
        return [], {"file": str(path), "status": "OPENPYXL_NOT_AVAILABLE"}
    if not path.exists() or looks_like_html(path):
        return [], {"file": str(path), "status": "MISSING_OR_HTML"}
    rows_out: List[Dict[str, Any]] = []
    sheet_profiles: List[Dict[str, Any]] = []
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        return [], {"file": str(path), "status": "XLSX_OPEN_ERROR", "error": str(e)}
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            rows.append(tuple(row))
            if i >= max_rows_per_sheet:
                break
        hidx, date_cols, numeric_cols, headers = infer_header_and_cols(rows)
        emitted = 0
        # Mode A: one date column + many metrics
        if date_cols:
            date_col = date_cols[0]
            for ridx in range(hidx + 1, len(rows)):
                row = rows[ridx]
                d = parse_date(row[date_col] if date_col < len(row) else None)
                if not d:
                    continue
                for c in numeric_cols:
                    if c == date_col:
                        continue
                    v = safe_float(row[c] if c < len(row) else None)
                    if v is None:
                        continue
                    metric = headers[c] if c < len(headers) and headers[c] else f"col_{c+1}"
                    rows_out.append({
                        "source_family": source_family,
                        "workbook": path.name,
                        "sheet": ws.title,
                        "date": d,
                        "metric": normalize_metric_name(metric),
                        "metric_raw": metric,
                        "value": v,
                        "entity": "",
                        "row_index": ridx + 1,
                        "column_index": c + 1,
                    })
                    emitted += 1
        # Mode B: date-like headers across columns, entity in first text column
        date_header_cols = [i for i, h in enumerate(headers) if parse_date(h)]
        if len(date_header_cols) >= 2:
            entity_col = 0
            for ridx in range(hidx + 1, len(rows)):
                row = rows[ridx]
                entity = cell_text(row[entity_col] if entity_col < len(row) else "")[:120]
                for c in date_header_cols:
                    v = safe_float(row[c] if c < len(row) else None)
                    d = parse_date(headers[c])
                    if d and v is not None:
                        rows_out.append({
                            "source_family": source_family,
                            "workbook": path.name,
                            "sheet": ws.title,
                            "date": d,
                            "metric": "date_column_value",
                            "metric_raw": headers[c],
                            "value": v,
                            "entity": entity,
                            "row_index": ridx + 1,
                            "column_index": c + 1,
                        })
                        emitted += 1
        sheet_profiles.append({
            "source_family": source_family,
            "workbook": path.name,
            "sheet": ws.title,
            "rows_scanned": len(rows),
            "header_row": hidx + 1,
            "date_cols": len(date_cols),
            "numeric_cols": len(numeric_cols),
            "emitted_rows": emitted,
        })
    return rows_out, {"file": str(path), "status": "OK", "sheets": sheet_profiles}


def validate_family(inbox: Path, feature_dir: Path, family: str, out_name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    files = find_xlsx_files(inbox, family)
    all_rows: List[Dict[str, Any]] = []
    profiles: List[Dict[str, Any]] = []
    file_meta: List[Dict[str, Any]] = []
    for p in files:
        rows, meta = extract_xlsx_long(p, family)
        all_rows.extend(rows)
        file_meta.append({k: v for k, v in meta.items() if k != "sheets"})
        profiles.extend(meta.get("sheets", []))
    # dedupe exact rows
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for r in all_rows:
        key = tuple(str(r.get(k, "")) for k in ("source_family", "workbook", "sheet", "date", "metric", "entity", "value"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    write_csv(feature_dir / out_name, deduped, [
        "source_family", "workbook", "sheet", "date", "metric", "metric_raw", "value", "entity", "row_index", "column_index"
    ])
    meta = {
        "files_seen": len(files),
        "rows_extracted": len(deduped),
        "feature_status": "VALIDATED_CANDIDATE" if len(deduped) > 0 else "NO_ROWS_EXTRACTED",
        "files": [str(p) for p in files],
    }
    return deduped, meta, profiles + file_meta


def run(root: Path, inbox: Optional[Path] = None) -> Dict[str, Any]:
    inbox = inbox or Path.home() / "Downloads" / "xauusd_fundamental_event_inbox"
    feature_dir = root / "data" / "fundamental_event_inbox" / "features"
    report_dir = root / "reports" / "stage116_source_specific_wgc_spdr_dxy_validator"
    ensure_dir(feature_dir)
    ensure_dir(report_dir)

    dollar_rows, dxy_meta = build_dollar_pressure(root, inbox, feature_dir)
    etf_rows, etf_meta, etf_profiles = validate_family(inbox, feature_dir, "wgc_etf", "stage116_validated_wgc_gold_etf_long.csv")
    cb_rows, cb_meta, cb_profiles = validate_family(inbox, feature_dir, "central_bank", "stage116_validated_wgc_central_bank_gold_long.csv")
    spdr_rows, spdr_meta, spdr_profiles = validate_family(inbox, feature_dir, "spdr", "stage116_validated_spdr_gld_long.csv")

    all_profiles = etf_profiles + cb_profiles + spdr_profiles
    write_csv(report_dir / "stage116_xlsx_sheet_profiles.csv", all_profiles)

    blockers = []
    if len(dollar_rows) < 100:
        blockers.append("NO_VALID_DOLLAR_PRESSURE_SERIES")
    # WGC/SPDR are useful but not hard-blocking for macro+COT discovery; status is explicit.
    source_validation_ready = len(dollar_rows) >= 100 and (len(etf_rows) > 0 or len(spdr_rows) > 0)

    summary = {
        "stage": STAGE,
        "generated_utc": utc_now(),
        "status": STATUS,
        "decision": DECISION,
        "classification": CLASSIFICATION,
        "hard_blocks": HARD_BLOCKS,
        "root": str(root),
        "inbox": str(inbox),
        "feature_dir": str(feature_dir),
        **dxy_meta,
        "validated_dollar_pressure_rows": len(dollar_rows),
        "wgc_gold_etf_rows": len(etf_rows),
        "wgc_gold_etf_files_seen": etf_meta["files_seen"],
        "wgc_gold_etf_status": etf_meta["feature_status"],
        "wgc_central_bank_rows": len(cb_rows),
        "wgc_central_bank_files_seen": cb_meta["files_seen"],
        "wgc_central_bank_status": cb_meta["feature_status"],
        "spdr_gld_rows": len(spdr_rows),
        "spdr_gld_files_seen": spdr_meta["files_seen"],
        "spdr_gld_status": spdr_meta["feature_status"],
        "source_validation_ready_for_discovery": source_validation_ready,
        "soft_blockers": blockers,
        "validated_dollar_pressure": str(feature_dir / "stage116_validated_dollar_pressure.csv"),
        "dxy_source_diagnostics": str(feature_dir / "stage116_dxy_source_diagnostics.csv"),
        "validated_wgc_gold_etf_long": str(feature_dir / "stage116_validated_wgc_gold_etf_long.csv"),
        "validated_wgc_central_bank_gold_long": str(feature_dir / "stage116_validated_wgc_central_bank_gold_long.csv"),
        "validated_spdr_gld_long": str(feature_dir / "stage116_validated_spdr_gld_long.csv"),
        "sheet_profiles": str(report_dir / "stage116_xlsx_sheet_profiles.csv"),
        "summary_json": str(report_dir / "stage116_source_specific_wgc_spdr_dxy_validator_summary.json"),
        "report_md": str(report_dir / "stage116_source_specific_wgc_spdr_dxy_validator_report.md"),
        "next": [
            "If source_validation_ready_for_discovery is true, proceed to segmented discovery using Stage115 macro/COT plus Stage116 validated dollar-pressure and validated WGC/SPDR candidates.",
            "If direct DXY is invalid, keep DTWEXBGS fallback and do not block discovery.",
            "Treat central-bank rows as context if generic extraction remains sparse; build a stricter country/month parser only if central-bank features are shortlisted.",
        ],
    }
    with (report_dir / "stage116_source_specific_wgc_spdr_dxy_validator_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    report = [
        f"# {STAGE}", "", f"Generated UTC: {summary['generated_utc']}", "",
        f"Status: `{STATUS}`", f"Decision: `{DECISION}`", "",
        "## Interpretation", "",
        "Stage116 validates source-specific WGC/SPDR/DXY paths and remains data-only. It does not touch MT5, EA, broker, paper-order, or live-order surfaces.", "",
        "## Key flags", "",
        f"- Direct DXY valid: `{summary['direct_dxy_valid']}`",
        f"- DXY source mode: `{summary['dxy_source_mode']}`",
        f"- DXY fallback active: `{summary['dxy_fallback_active']}`",
        f"- Validated dollar-pressure rows: `{summary['validated_dollar_pressure_rows']}`",
        f"- WGC ETF rows: `{summary['wgc_gold_etf_rows']}`",
        f"- WGC central-bank rows: `{summary['wgc_central_bank_rows']}`",
        f"- SPDR GLD rows: `{summary['spdr_gld_rows']}`",
        f"- Source validation ready for discovery: `{summary['source_validation_ready_for_discovery']}`",
    ]
    (report_dir / "stage116_source_specific_wgc_spdr_dxy_validator_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=STAGE)
    ap.add_argument("--root", default="/Users/vahid/Desktop/xauusd-trader")
    ap.add_argument("--inbox", default=str(Path.home() / "Downloads" / "xauusd_fundamental_event_inbox"))
    args = ap.parse_args(argv)
    summary = run(Path(args.root), Path(args.inbox))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
