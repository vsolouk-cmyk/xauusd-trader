#!/usr/bin/env python3
"""
Stage47B2 Data Horizon Audit for XAUUSD Liquidity Sweep Reversal.

Purpose:
- Validate that the Stage47B scan is being run on enough M5 history.
- Merge bounded normalized CSV files for a selected timeframe.
- Stop safely if only a tiny source window is available.
- No promotion, no EA, no paper-live, no live trading.

This script intentionally does not tune the Stage47B trading rule.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
from collections import Counter, OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple


STAGE = "Stage47B2_DATA_HORIZON_AUDIT_BEFORE_RERUN"
PATCH = "Stage47B2_MULTIFILE_NORMALIZED_CSV_HORIZON_AUDIT"


TIMEFRAME_SECONDS = {
    "M1": 60,
    "1MIN": 60,
    "1M": 60,
    "M5": 300,
    "5MIN": 300,
    "5M": 300,
    "M15": 900,
    "15MIN": 900,
    "15M": 900,
    "H1": 3600,
    "1H": 3600,
    "60MIN": 3600,
}


def norm_name(name: str) -> str:
    return "".join(ch.lower() for ch in str(name).strip() if ch.isalnum() or ch == "_")


def canonical_timeframe(value: str) -> str:
    v = str(value or "").strip().upper().replace(" ", "")
    aliases = {
        "M1": "M1", "1M": "M1", "1MIN": "M1", "1MINUTE": "M1", "1MINUTES": "M1",
        "M5": "M5", "5M": "M5", "5MIN": "M5", "5MINUTE": "M5", "5MINUTES": "M5",
        "M15": "M15", "15M": "M15", "15MIN": "M15", "15MINUTE": "M15", "15MINUTES": "M15",
        "H1": "H1", "1H": "H1", "1HR": "H1", "1HOUR": "H1", "60MIN": "H1",
    }
    return aliases.get(v, v)


def timeframe_filename_tokens(tf: str) -> List[str]:
    tf = canonical_timeframe(tf)
    if tf == "M5":
        return ["_5min_", "-5min-", "_M5_", "-M5-", "_5m_", "-5m-"]
    if tf == "M1":
        return ["_1min_", "-1min-", "_M1_", "-M1-", "_1m_", "-1m-"]
    if tf == "M15":
        return ["_15min_", "-15min-", "_M15_", "-M15-", "_15m_", "-15m-"]
    if tf == "H1":
        return ["_1h_", "-1h-", "_H1_", "-H1-", "_60min_", "-60min-"]
    return [tf]


def parse_ts(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Python can parse "2026-06-02 12:25:00+00:00" and ISO strings.
    variants = [s, s.replace("Z", "+00:00"), s.replace(" ", "T").replace("Z", "+00:00")]
    for v in variants:
        try:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return None


def to_float(value) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "false", "true"}:
        return None
    try:
        x = float(s)
        if math.isfinite(x):
            return x
    except Exception:
        return None
    return None


FIELD_ALIASES = {
    "ts": [
        "time_utc", "timestamp_utc", "utc_timestamp", "datetime_utc", "date_utc",
        "timestamp", "datetime", "time", "date", "candle_time", "candle_timestamp_utc",
    ],
    "open": ["open", "o", "mid_o", "bid_o", "ask_o"],
    "high": ["high", "h", "mid_h", "bid_h", "ask_h"],
    "low": ["low", "l", "mid_l", "bid_l", "ask_l"],
    "close": ["close", "c", "mid_c", "bid_c", "ask_c"],
    "symbol": ["symbol", "instrument", "pair", "ticker"],
    "timeframe": ["timeframe", "interval", "tf", "granularity"],
    "session": ["session", "session_utc"],
    "provider": ["provider", "source_provider"],
    "source_file": ["source_file", "raw_file"],
}


def detect_mapping(fieldnames: List[str]) -> Dict[str, Optional[str]]:
    norm_to_original = {norm_name(f): f for f in fieldnames}
    mapping: Dict[str, Optional[str]] = {}
    for key, aliases in FIELD_ALIASES.items():
        found = None
        for a in aliases:
            if norm_name(a) in norm_to_original:
                found = norm_to_original[norm_name(a)]
                break
        mapping[key] = found
    return mapping


def symbol_ok(value: str) -> bool:
    if value is None or str(value).strip() == "":
        return True
    v = str(value).upper().replace("/", "").replace("_", "").replace("-", "")
    return "XAU" in v or "GOLD" in v


def discover_csv_files(root: Path, timeframe: str, csv_glob: Optional[str]) -> Tuple[List[str], Dict]:
    checked = []
    files: List[str] = []
    if csv_glob:
        pattern = str((root / csv_glob).resolve()) if not os.path.isabs(csv_glob) else csv_glob
        checked.append(pattern)
        files.extend(glob.glob(pattern))
    else:
        patterns = [
            root / "data" / "normalized" / "normalized_*XAU*.csv",
            root / "data" / "normalized" / "*XAU*.csv",
            root / "data" / "normalized" / "*.csv",
        ]
        for p in patterns:
            checked.append(str(p))
            files.extend(glob.glob(str(p)))
    # Bounded, no recursive scan outside data/normalized unless explicit glob asked.
    tokens = [t.lower() for t in timeframe_filename_tokens(timeframe)]
    scored = []
    for f in sorted(set(files)):
        name = Path(f).name.lower()
        score = 0
        if any(tok.lower() in name for tok in tokens):
            score += 100
        else:
            # Keep as fallback; row-level interval filter can still decide.
            score -= 100
        if "xau" in name or "gold" in name:
            score += 10
        try:
            mtime = os.path.getmtime(f)
        except OSError:
            mtime = 0
        scored.append({"score": score, "mtime": mtime, "path": f})
    scored.sort(key=lambda x: (x["score"], x["mtime"], x["path"]), reverse=True)
    selected = [x["path"] for x in scored if x["score"] >= 0]
    if not selected:
        selected = [x["path"] for x in scored]
    return selected, {"checked_patterns": checked, "candidate_scores": scored, "selected_files": selected}


def read_one_csv(path: str, timeframe: str) -> Tuple[List[Dict], Dict]:
    accepted = []
    meta = {
        "path": path,
        "raw_rows": 0,
        "accepted_rows": 0,
        "parse_fail_rows": 0,
        "symbol_filtered_rows": 0,
        "timeframe_filtered_rows": 0,
        "bad_ohlc_rows": 0,
        "fieldnames": [],
        "mapping": {},
        "first_bad_row_limited": None,
        "first_parse_exception": None,
    }
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            fieldnames = reader.fieldnames or []
            meta["fieldnames"] = fieldnames
            mapping = detect_mapping(fieldnames)
            meta["mapping"] = mapping
            required = ["ts", "open", "high", "low", "close"]
            if any(mapping.get(k) is None for k in required):
                meta["error"] = "MISSING_REQUIRED_COLUMNS"
                return [], meta
            requested_tf = canonical_timeframe(timeframe)
            for row in reader:
                meta["raw_rows"] += 1
                try:
                    if mapping.get("symbol") and not symbol_ok(row.get(mapping["symbol"])):
                        meta["symbol_filtered_rows"] += 1
                        continue
                    if mapping.get("timeframe"):
                        row_tf = canonical_timeframe(row.get(mapping["timeframe"]))
                        if row_tf and row_tf != requested_tf:
                            meta["timeframe_filtered_rows"] += 1
                            continue
                    ts = parse_ts(row.get(mapping["ts"]))
                    o = to_float(row.get(mapping["open"]))
                    h = to_float(row.get(mapping["high"]))
                    l = to_float(row.get(mapping["low"]))
                    c = to_float(row.get(mapping["close"]))
                    if ts is None or o is None or h is None or l is None or c is None:
                        meta["parse_fail_rows"] += 1
                        if meta["first_bad_row_limited"] is None:
                            meta["first_bad_row_limited"] = {k: row.get(k) for k in list(row.keys())[:12]}
                        continue
                    if h < max(o, c) or l > min(o, c) or h < l:
                        meta["bad_ohlc_rows"] += 1
                        continue
                    accepted.append({
                        "time_utc": ts.isoformat().replace("+00:00", "Z"),
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "symbol": row.get(mapping["symbol"], "XAU/USD") if mapping.get("symbol") else "XAU/USD",
                        "interval": requested_tf,
                        "session_utc": row.get(mapping["session"], "") if mapping.get("session") else "",
                        "provider": row.get(mapping["provider"], "") if mapping.get("provider") else "",
                        "source_file": row.get(mapping["source_file"], Path(path).name) if mapping.get("source_file") else Path(path).name,
                    })
                except Exception as e:
                    meta["parse_fail_rows"] += 1
                    if meta["first_parse_exception"] is None:
                        meta["first_parse_exception"] = repr(e)
                    if meta["first_bad_row_limited"] is None:
                        meta["first_bad_row_limited"] = {k: row.get(k) for k in list(row.keys())[:12]}
    except Exception as e:
        meta["error"] = repr(e)
        return [], meta
    meta["accepted_rows"] = len(accepted)
    return accepted, meta


def summarize_gaps(rows: List[Dict], timeframe: str) -> Dict:
    if len(rows) < 2:
        return {"gap_count_gt_1_5x": 0, "max_gap_minutes": None, "median_gap_minutes": None}
    tss = [parse_ts(r["time_utc"]) for r in rows]
    tss = [t for t in tss if t]
    diffs_min = [(b - a).total_seconds() / 60.0 for a, b in zip(tss[:-1], tss[1:])]
    exp = TIMEFRAME_SECONDS.get(canonical_timeframe(timeframe), 300) / 60.0
    return {
        "expected_gap_minutes": exp,
        "gap_count_gt_1_5x": sum(1 for d in diffs_min if d > 1.5 * exp),
        "gap_count_gt_3x": sum(1 for d in diffs_min if d > 3.0 * exp),
        "max_gap_minutes": max(diffs_min) if diffs_min else None,
        "median_gap_minutes": median(diffs_min) if diffs_min else None,
    }


def write_merged_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["time_utc", "open", "high", "low", "close", "symbol", "interval", "session_utc", "provider", "source_file"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repo root. Default: current directory.")
    ap.add_argument("--timeframe", default="M5")
    ap.add_argument("--csv-glob", default=None, help="Optional glob relative to root or absolute. Example: data/normalized/*5min*.csv")
    ap.add_argument("--out", default="reports/stage47b2")
    ap.add_argument("--merged-out", default=None, help="Optional merged CSV output path.")
    ap.add_argument("--min-rows", type=int, default=5000)
    ap.add_argument("--min-days", type=float, default=20.0)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    files, discovery_meta = discover_csv_files(root, args.timeframe, args.csv_glob)
    all_rows: List[Dict] = []
    file_metas: List[Dict] = []
    for f in files:
        rows, meta = read_one_csv(f, args.timeframe)
        file_metas.append(meta)
        all_rows.extend(rows)

    # Deduplicate by timestamp. Keep the last version from the latest selected file order.
    dedup: "OrderedDict[str, Dict]" = OrderedDict()
    for r in all_rows:
        dedup[r["time_utc"]] = r
    rows = list(dedup.values())
    rows.sort(key=lambda r: r["time_utc"])

    start = rows[0]["time_utc"] if rows else None
    end = rows[-1]["time_utc"] if rows else None
    coverage_days = None
    unique_calendar_days = 0
    if rows:
        t0 = parse_ts(start)
        t1 = parse_ts(end)
        if t0 and t1:
            coverage_days = (t1 - t0).total_seconds() / 86400.0
        unique_calendar_days = len(set((parse_ts(r["time_utc"]).date().isoformat() for r in rows if parse_ts(r["time_utc"]))))

    status = "DATA_HORIZON_READY_FOR_STAGE47B_RERUN_NO_PROMOTION"
    stop_reason = None
    if len(rows) < args.min_rows:
        status = "INSUFFICIENT_HISTORY_STOP_NO_PROMOTION"
        stop_reason = f"unique_rows_lt_min_rows_{args.min_rows}"
    elif coverage_days is not None and coverage_days < args.min_days:
        status = "INSUFFICIENT_HISTORY_STOP_NO_PROMOTION"
        stop_reason = f"coverage_days_lt_min_days_{args.min_days}"

    merged_path = None
    if args.merged_out:
        merged_path = Path(args.merged_out)
        if not merged_path.is_absolute():
            merged_path = root / merged_path
        write_merged_csv(merged_path, rows)

    summary = {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "timeframe": canonical_timeframe(args.timeframe),
        "root": str(root),
        "files_selected": len(files),
        "raw_rows_total": sum(m.get("raw_rows", 0) for m in file_metas),
        "accepted_rows_total_before_dedup": sum(m.get("accepted_rows", 0) for m in file_metas),
        "unique_rows_after_dedup": len(rows),
        "duplicates_removed": max(0, sum(m.get("accepted_rows", 0) for m in file_metas) - len(rows)),
        "start_utc": start,
        "end_utc": end,
        "coverage_days": coverage_days,
        "unique_calendar_days": unique_calendar_days,
        "min_rows_required": args.min_rows,
        "min_days_required": args.min_days,
        "stop_reason": stop_reason,
        "gap_summary": summarize_gaps(rows, args.timeframe),
        "merged_csv": str(merged_path) if merged_path else None,
        "discovery_meta": discovery_meta,
        "file_metas_limited": file_metas[:20],
    }
    summary_path = out_dir / "stage47b2_data_horizon_audit_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    report_path = out_dir / "stage47b2_data_horizon_audit_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Stage47B2 Data Horizon Audit\n\n")
        for k in [
            "status", "timeframe", "files_selected", "raw_rows_total",
            "accepted_rows_total_before_dedup", "unique_rows_after_dedup",
            "duplicates_removed", "start_utc", "end_utc", "coverage_days",
            "unique_calendar_days", "stop_reason", "merged_csv",
        ]:
            f.write(f"- {k}: `{summary.get(k)}`\n")
        f.write("\nNo promotion, EA, paper-live, or live action is allowed from this audit.\n")
        if status == "DATA_HORIZON_READY_FOR_STAGE47B_RERUN_NO_PROMOTION" and merged_path:
            f.write("\nSuggested rerun command:\n\n")
            f.write("```bash\n")
            rel = os.path.relpath(merged_path, root)
            f.write(f"python3 app/stage47b_liquidity_sweep_reversal_scan.py --csv {rel} --timeframe {canonical_timeframe(args.timeframe)} --out reports/stage47b\n")
            f.write("```\n")

    print(json.dumps({
        "stage": STAGE,
        "status": status,
        "unique_rows_after_dedup": len(rows),
        "coverage_days": coverage_days,
        "merged_csv": str(merged_path) if merged_path else None,
        "out": str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
