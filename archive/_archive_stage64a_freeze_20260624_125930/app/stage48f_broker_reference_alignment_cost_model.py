#!/usr/bin/env python3
"""Stage48F: Broker/reference alignment and spread cost model calibration.

Research-only utility for XAUUSD project.

Inputs:
  - Broker MT5/AMarkets M5 export with row-level spread, e.g.
    <DATE>\t<TIME>\t<OPEN>\t...\t<SPREAD>
  - Optional reference normalized M5 CSV, e.g. TwelveData normalized file.

Outputs:
  - summary JSON
  - markdown report
  - cost model JSON
  - session profile CSV
  - alignment sample CSV

No trading signals are generated.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage48F_BROKER_REFERENCE_ALIGNMENT_AND_COST_MODEL_CALIBRATION"
PATCH = "Stage48F_LOADERFIX1_SPREAD_COVERAGE_DENOMINATOR_AND_OFFSET_QUALITY"


@dataclass
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    spread_points: Optional[float] = None
    source: str = ""
    session: str = ""


def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_dt(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y.%m.%d",
    ]
    try:
        return utc(datetime.fromisoformat(s))
    except Exception:
        pass
    for fmt in fmts:
        try:
            return utc(datetime.strptime(s, fmt))
        except Exception:
            continue
    return None


def parse_date_time(date_value: str, time_value: str) -> Optional[datetime]:
    ds = str(date_value or "").strip()
    ts = str(time_value or "").strip()
    if not ds and not ts:
        return None
    return parse_dt((ds + " " + ts).strip())


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null", "false", "true", "-"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def normalize_header(h: str) -> str:
    return str(h or "").strip().strip("\ufeff").strip().strip("<>").strip().lower().replace(" ", "_")


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except Exception:
        class D(csv.excel):
            delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
        return D


def percentile(values: List[float], p: float) -> Optional[float]:
    xs = sorted([x for x in values if x is not None and not math.isnan(x)])
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)


def describe(values: List[float]) -> Dict[str, Any]:
    xs = [x for x in values if x is not None and not math.isnan(x)]
    if not xs:
        return {"count": 0}
    return {
        "count": len(xs),
        "mean": statistics.fmean(xs),
        "median": percentile(xs, 50),
        "p90": percentile(xs, 90),
        "p95": percentile(xs, 95),
        "p99": percentile(xs, 99),
        "min": min(xs),
        "max": max(xs),
    }


def session_utc(dt: datetime) -> str:
    h = utc(dt).hour
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 21:
        return "new_york"
    return "late_us"


def load_broker_csv(path: Path, timeframe: str, offset_hours: int = 0) -> Tuple[List[Candle], Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "raw_rows": 0,
        "accepted_rows": 0,
        "parse_fail_rows": 0,
        "bad_ohlc_rows": 0,
        "bad_timestamp_rows": 0,
        "numeric_spread_rows": 0,
        "delimiter": None,
        "fieldnames": [],
        "mapping": {},
        "time_offset_hours_applied": offset_hours,
    }
    dialect = sniff_dialect(path)
    meta["delimiter"] = getattr(dialect, "delimiter", None)
    candles: List[Candle] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, dialect=dialect)
        raw_fieldnames = reader.fieldnames or []
        meta["fieldnames"] = raw_fieldnames
        norm_to_raw = {normalize_header(h): h for h in raw_fieldnames}
        def col(*names: str) -> Optional[str]:
            for n in names:
                if n in norm_to_raw:
                    return norm_to_raw[n]
            return None
        c_date = col("date")
        c_time = col("time")
        c_ts = col("time_utc", "timestamp", "datetime", "utc_time", "bar_ts_utc", "time") if not (c_date and c_time) else None
        c_open = col("open")
        c_high = col("high")
        c_low = col("low")
        c_close = col("close")
        c_spread = col("spread", "spread_points", "spread_point", "spreadpts")
        c_tf = col("timeframe", "interval", "tf")
        meta["mapping"] = {"date": c_date, "time": c_time, "ts": c_ts, "open": c_open, "high": c_high, "low": c_low, "close": c_close, "spread": c_spread, "timeframe": c_tf}
        for row in reader:
            meta["raw_rows"] += 1
            if c_tf:
                tfv = str(row.get(c_tf, "")).strip().lower()
                if tfv and tfv not in {"m5", "5m", "5min", "5"}:
                    continue
            dt = parse_date_time(row.get(c_date, ""), row.get(c_time, "")) if c_date and c_time else parse_dt(row.get(c_ts, ""))
            if dt is None:
                meta["bad_timestamp_rows"] += 1
                continue
            dt = utc(dt - timedelta(hours=offset_hours))
            o = safe_float(row.get(c_open))
            h = safe_float(row.get(c_high))
            l = safe_float(row.get(c_low))
            c = safe_float(row.get(c_close))
            sp = safe_float(row.get(c_spread)) if c_spread else None
            if sp is not None:
                meta["numeric_spread_rows"] += 1
            if o is None or h is None or l is None or c is None or not (l <= min(o, c) <= max(o, c) <= h):
                meta["bad_ohlc_rows"] += 1
                continue
            candles.append(Candle(dt, o, h, l, c, sp, source="broker", session=session_utc(dt)))
    candles.sort(key=lambda x: x.ts)
    # dedupe by ts, keep latest parsed
    dedup: Dict[datetime, Candle] = {x.ts: x for x in candles}
    candles = [dedup[k] for k in sorted(dedup)]
    meta["accepted_rows"] = len(candles)
    meta["duplicates_removed"] = meta["raw_rows"] - len(candles) - meta["bad_timestamp_rows"] - meta["bad_ohlc_rows"]
    if candles:
        meta["start_utc"] = candles[0].ts.isoformat().replace("+00:00", "Z")
        meta["end_utc"] = candles[-1].ts.isoformat().replace("+00:00", "Z")
        meta["coverage_days"] = (candles[-1].ts - candles[0].ts).total_seconds() / 86400.0
    return candles, meta


def load_reference_csv(path: Path, timeframe: str) -> Tuple[List[Candle], Dict[str, Any]]:
    meta: Dict[str, Any] = {"path": str(path), "raw_rows": 0, "accepted_rows": 0, "bad_timestamp_rows": 0, "bad_ohlc_rows": 0, "fieldnames": [], "delimiter": None, "mapping": {}}
    dialect = sniff_dialect(path)
    meta["delimiter"] = getattr(dialect, "delimiter", None)
    candles: List[Candle] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, dialect=dialect)
        raw_fieldnames = reader.fieldnames or []
        meta["fieldnames"] = raw_fieldnames
        norm_to_raw = {normalize_header(h): h for h in raw_fieldnames}
        def col(*names: str) -> Optional[str]:
            for n in names:
                if n in norm_to_raw:
                    return norm_to_raw[n]
            return None
        c_ts = col("time_utc", "timestamp", "datetime", "utc_time", "bar_ts_utc", "time")
        c_open = col("open")
        c_high = col("high")
        c_low = col("low")
        c_close = col("close")
        c_tf = col("timeframe", "interval", "tf")
        c_session = col("session_utc", "session")
        meta["mapping"] = {"ts": c_ts, "open": c_open, "high": c_high, "low": c_low, "close": c_close, "timeframe": c_tf, "session": c_session}
        for row in reader:
            meta["raw_rows"] += 1
            if c_tf:
                tfv = str(row.get(c_tf, "")).strip().lower()
                if tfv and tfv not in {"m5", "5m", "5min", "5"}:
                    continue
            dt = parse_dt(row.get(c_ts, "")) if c_ts else None
            if dt is None:
                meta["bad_timestamp_rows"] += 1
                continue
            o = safe_float(row.get(c_open))
            h = safe_float(row.get(c_high))
            l = safe_float(row.get(c_low))
            c = safe_float(row.get(c_close))
            if o is None or h is None or l is None or c is None or not (l <= min(o, c) <= max(o, c) <= h):
                meta["bad_ohlc_rows"] += 1
                continue
            sess = str(row.get(c_session, "")).strip() if c_session else session_utc(dt)
            candles.append(Candle(utc(dt), o, h, l, c, None, source="reference", session=sess or session_utc(dt)))
    candles.sort(key=lambda x: x.ts)
    dedup = {x.ts: x for x in candles}
    candles = [dedup[k] for k in sorted(dedup)]
    meta["accepted_rows"] = len(candles)
    if candles:
        meta["start_utc"] = candles[0].ts.isoformat().replace("+00:00", "Z")
        meta["end_utc"] = candles[-1].ts.isoformat().replace("+00:00", "Z")
        meta["coverage_days"] = (candles[-1].ts - candles[0].ts).total_seconds() / 86400.0
    return candles, meta


def discover_reference(root: Path) -> Optional[Path]:
    patterns = [
        str(root / "data/normalized/normalized_twelvedata_XAU_USD_5min_backfill_*.csv"),
        str(root / "data/normalized/normalized_twelvedata_XAU_USD_5min_*.csv"),
        str(root / "data/normalized/*XAU*5min*.csv"),
    ]
    candidates: List[Path] = []
    for p in patterns:
        candidates += [Path(x) for x in glob.glob(p)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def choose_offset(broker_path: Path, ref_by_ts: Dict[datetime, Candle], timeframe: str, min_offset: int, max_offset: int) -> Tuple[int, Dict[str, Any]]:
    """Choose broker server-time offset using match count plus price-alignment quality.

    LoaderFix1 changes the offset rule from pure timestamp match count to a quality-aware
    score. Timestamp count alone can tie across adjacent offsets when the reference file
    has a continuous M5 grid; in that case the selected offset can be arbitrary.
    We first keep offsets with enough timestamp overlap, then prefer the offset with
    the lowest median absolute close basis against the reference feed.
    """
    scores: List[Dict[str, Any]] = []
    max_match = 0
    for off in range(min_offset, max_offset + 1):
        bc, _bm = load_broker_csv(broker_path, timeframe, offset_hours=off)
        basis_abs: List[float] = []
        matched = 0
        for c in bc:
            r = ref_by_ts.get(c.ts)
            if r is None:
                continue
            matched += 1
            if r.close:
                basis_abs.append(abs((c.close - r.close) / r.close * 10000.0))
        max_match = max(max_match, matched)
        scores.append({
            "offset_hours": off,
            "matched_timestamps": matched,
            "broker_rows": len(bc),
            "median_abs_basis_bps": percentile(basis_abs, 50),
            "p90_abs_basis_bps": percentile(basis_abs, 90),
            "basis_sample_count": len(basis_abs),
        })

    # Keep offsets that do not sacrifice too much overlap; then optimize quality.
    min_acceptable_match = max(1, int(max_match * 0.98)) if max_match else 1
    eligible = [x for x in scores if x.get("matched_timestamps", 0) >= min_acceptable_match and x.get("median_abs_basis_bps") is not None]
    if not eligible:
        eligible = [x for x in scores if x.get("median_abs_basis_bps") is not None] or scores

    def sort_key(x: Dict[str, Any]) -> Tuple[float, int, int]:
        mab = x.get("median_abs_basis_bps")
        if mab is None:
            mab = float("inf")
        return (float(mab), -int(x.get("matched_timestamps", 0)), abs(int(x.get("offset_hours", 0))))

    best = sorted(eligible, key=sort_key)[0] if eligible else {"offset_hours": 0, "matched_timestamps": 0}
    return int(best.get("offset_hours", 0)), {
        "offset_scores": scores,
        "selected_offset_hours": int(best.get("offset_hours", 0)),
        "selected_match_count": int(best.get("matched_timestamps", 0)),
        "selected_median_abs_basis_bps": best.get("median_abs_basis_bps"),
        "max_match_count": max_match,
        "min_acceptable_match_for_quality_selection": min_acceptable_match,
        "selection_rule": "eligible_offsets_within_98pct_of_max_match_then_min_median_abs_basis_bps",
    }


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker-csv", default="~/Downloads/amarkets_xauusd_5m.csv")
    ap.add_argument("--reference-csv", default="")
    ap.add_argument("--root", default=".")
    ap.add_argument("--timeframe", default="M5")
    ap.add_argument("--point-size", type=float, default=0.01, help="MT5 point size for XAUUSD spread_points conversion. Common AMarkets XAUUSD value is 0.01 if digits=2.")
    ap.add_argument("--slippage-buffer-bps", type=float, default=2.0)
    ap.add_argument("--auto-offset-search", action="store_true", default=True)
    ap.add_argument("--no-auto-offset-search", action="store_false", dest="auto_offset_search")
    ap.add_argument("--offset-min", type=int, default=-6)
    ap.add_argument("--offset-max", type=int, default=6)
    ap.add_argument("--min-aligned-rows", type=int, default=5000)
    ap.add_argument("--min-aligned-days", type=float, default=20.0)
    ap.add_argument("--out", default="reports/stage48f")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    broker_path = Path(args.broker_csv).expanduser()
    if not broker_path.exists():
        summary = {"stage": STAGE, "patch": PATCH, "status": "BROKER_CSV_NOT_FOUND_NO_PROMOTION", "broker_csv": str(broker_path), "promotion": "NO_GO", "EA": "NO_GO", "paper_live": "NO_GO", "live": "NO_GO"}
        (out / "stage48f_broker_reference_alignment_cost_model_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
        return 2

    reference_path = Path(args.reference_csv).expanduser() if args.reference_csv else discover_reference(root)
    reference_candles: List[Candle] = []
    reference_meta: Dict[str, Any] = {"path": str(reference_path) if reference_path else None, "found": bool(reference_path)}
    if reference_path and reference_path.exists():
        reference_candles, reference_meta = load_reference_csv(reference_path, args.timeframe)
        reference_meta["found"] = True
    ref_by_ts = {c.ts: c for c in reference_candles}

    offset_meta: Dict[str, Any] = {"auto_offset_search": args.auto_offset_search, "selected_offset_hours": 0, "selected_match_count": None}
    selected_offset = 0
    if args.auto_offset_search and ref_by_ts:
        selected_offset, offset_meta = choose_offset(broker_path, ref_by_ts, args.timeframe, args.offset_min, args.offset_max)
        offset_meta["auto_offset_search"] = True
    broker_candles, broker_meta = load_broker_csv(broker_path, args.timeframe, offset_hours=selected_offset)
    broker_by_ts = {c.ts: c for c in broker_candles}

    aligned_rows: List[Dict[str, Any]] = []
    spread_points_values: List[float] = []
    spread_price_values: List[float] = []
    spread_cost_bps_values: List[float] = []
    basis_bps_values: List[float] = []
    abs_basis_bps_values: List[float] = []
    by_session: Dict[str, Dict[str, List[float]]] = {}

    common_ts = sorted(set(broker_by_ts).intersection(ref_by_ts)) if ref_by_ts else sorted(broker_by_ts)
    for ts in common_ts:
        b = broker_by_ts[ts]
        r = ref_by_ts.get(ts)
        sp = b.spread_points
        spread_price = sp * args.point_size if sp is not None else None
        spread_cost_bps = (spread_price / b.close * 10000.0) if spread_price is not None and b.close else None
        if sp is not None:
            spread_points_values.append(sp)
        if spread_price is not None:
            spread_price_values.append(spread_price)
        if spread_cost_bps is not None:
            spread_cost_bps_values.append(spread_cost_bps)
        basis_bps = None
        abs_basis_bps = None
        ref_close = None
        if r is not None:
            ref_close = r.close
            basis_bps = (b.close - r.close) / r.close * 10000.0 if r.close else None
            abs_basis_bps = abs(basis_bps) if basis_bps is not None else None
            if basis_bps is not None:
                basis_bps_values.append(basis_bps)
                abs_basis_bps_values.append(abs_basis_bps)
        sess = b.session or session_utc(ts)
        by_session.setdefault(sess, {"spread_points": [], "spread_cost_bps": [], "abs_basis_bps": []})
        if sp is not None:
            by_session[sess]["spread_points"].append(sp)
        if spread_cost_bps is not None:
            by_session[sess]["spread_cost_bps"].append(spread_cost_bps)
        if abs_basis_bps is not None:
            by_session[sess]["abs_basis_bps"].append(abs_basis_bps)
        if len(aligned_rows) < 5000:
            aligned_rows.append({
                "time_utc": ts.isoformat().replace("+00:00", "Z"),
                "session_utc": sess,
                "broker_close": b.close,
                "reference_close": ref_close,
                "basis_bps": basis_bps,
                "abs_basis_bps": abs_basis_bps,
                "spread_points": sp,
                "spread_price": spread_price,
                "spread_cost_bps": spread_cost_bps,
            })

    aligned_count = len(common_ts)
    aligned_days = 0.0
    if common_ts:
        aligned_days = (common_ts[-1] - common_ts[0]).total_seconds() / 86400.0

    # LoaderFix1: raw broker spread coverage must be measured on the full accepted
    # broker export, not on the aligned subset divided by all broker rows. The
    # previous denominator incorrectly reported ~6% coverage when the AMarkets
    # file actually had ~100% row-level spread. Keep aligned coverage separately.
    broker_raw_spread_coverage_pct = (float(broker_meta.get("numeric_spread_rows", 0)) / max(1, len(broker_candles))) * 100.0
    aligned_spread_coverage_pct = (len(spread_cost_bps_values) / max(1, aligned_count)) * 100.0 if aligned_count else 0.0
    spread_coverage_pct = broker_raw_spread_coverage_pct

    spread_cost_desc = describe(spread_cost_bps_values)
    spread_points_desc = describe(spread_points_values)
    basis_desc = describe(basis_bps_values)
    abs_basis_desc = describe(abs_basis_bps_values)

    session_rows = []
    for sess, vals in sorted(by_session.items()):
        spd = describe(vals["spread_points"])
        costd = describe(vals["spread_cost_bps"])
        absbd = describe(vals["abs_basis_bps"])
        session_rows.append({
            "session_utc": sess,
            "rows": len(vals["spread_cost_bps"]),
            "median_spread_points": spd.get("median"),
            "p90_spread_points": spd.get("p90"),
            "p95_spread_points": spd.get("p95"),
            "p99_spread_points": spd.get("p99"),
            "median_spread_cost_bps": costd.get("median"),
            "p90_spread_cost_bps": costd.get("p90"),
            "p95_spread_cost_bps": costd.get("p95"),
            "p99_spread_cost_bps": costd.get("p99"),
            "median_abs_basis_bps": absbd.get("median"),
            "p95_abs_basis_bps": absbd.get("p95"),
        })

    # Recommended model: p90 spread cost + explicit slippage/buffer, and stress p95/p99.
    median_cost = spread_cost_desc.get("median")
    p90_cost = spread_cost_desc.get("p90")
    p95_cost = spread_cost_desc.get("p95")
    p99_cost = spread_cost_desc.get("p99")
    recommended_cost_bps = (p90_cost if p90_cost is not None else 0.0) + args.slippage_buffer_bps
    stress_cost_bps = (p95_cost if p95_cost is not None else recommended_cost_bps) + args.slippage_buffer_bps
    extreme_cost_bps = (p99_cost if p99_cost is not None else stress_cost_bps) + args.slippage_buffer_bps

    ready_reasons = []
    if not broker_candles:
        ready_reasons.append("no_broker_rows")
    if len(broker_candles) < 5000:
        ready_reasons.append("broker_rows_lt_5000")
    if broker_raw_spread_coverage_pct < 80:
        ready_reasons.append("broker_raw_spread_coverage_lt_80pct")
    if reference_candles and aligned_count < args.min_aligned_rows:
        ready_reasons.append(f"aligned_rows_lt_{args.min_aligned_rows}")
    if reference_candles and aligned_days < args.min_aligned_days:
        ready_reasons.append(f"aligned_days_lt_{args.min_aligned_days}")
    if reference_candles and aligned_spread_coverage_pct < 80:
        ready_reasons.append("aligned_spread_coverage_lt_80pct")

    status = "COST_MODEL_READY_NO_PROMOTION" if not ready_reasons else "COST_MODEL_INSUFFICIENT_NO_PROMOTION"
    next_allowed = "BROKER_REAL_COST_AWARE_THESIS_DESIGN_OR_RERUN_NO_PROMOTION" if status.startswith("COST_MODEL_READY") else "FIX_ALIGNMENT_OR_BROKER_EXPORT_NO_PROMOTION"

    cost_model = {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "broker_csv": str(broker_path),
        "reference_csv": str(reference_path) if reference_path else None,
        "timeframe": args.timeframe,
        "point_size": args.point_size,
        "selected_broker_time_offset_hours": selected_offset,
        "broker_raw_spread_coverage_pct": broker_raw_spread_coverage_pct,
        "aligned_spread_coverage_pct": aligned_spread_coverage_pct,
        "aligned_rows": aligned_count,
        "aligned_coverage_days": aligned_days,
        "spread_points": spread_points_desc,
        "spread_price": describe(spread_price_values),
        "spread_cost_bps": spread_cost_desc,
        "basis_bps": basis_desc,
        "abs_basis_bps": abs_basis_desc,
        "slippage_buffer_bps": args.slippage_buffer_bps,
        "recommended_cost_bps": recommended_cost_bps,
        "stress_cost_bps": stress_cost_bps,
        "extreme_cost_bps": extreme_cost_bps,
        "recommended_usage": {
            "default_scan_cost_bps": recommended_cost_bps,
            "stress_scan_cost_bps": stress_cost_bps,
            "extreme_spread_filter_reference_bps": extreme_cost_bps,
            "note": "Use this for broker-real backtests only. This does not authorize EA, paper-live, or live trading.",
        },
        "session_cost_profile": session_rows,
    }

    summary = {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": next_allowed,
        "broker_csv": str(broker_path),
        "reference_csv": str(reference_path) if reference_path else None,
        "broker_rows": len(broker_candles),
        "broker_start_utc": broker_meta.get("start_utc"),
        "broker_end_utc": broker_meta.get("end_utc"),
        "broker_coverage_days": broker_meta.get("coverage_days"),
        "broker_spread_coverage_pct": spread_coverage_pct,
        "broker_raw_spread_coverage_pct": broker_raw_spread_coverage_pct,
        "aligned_spread_coverage_pct": aligned_spread_coverage_pct,
        "reference_rows": len(reference_candles),
        "aligned_rows": aligned_count,
        "aligned_coverage_days": aligned_days,
        "selected_broker_time_offset_hours": selected_offset,
        "offset_meta": offset_meta,
        "point_size": args.point_size,
        "spread_cost_bps": spread_cost_desc,
        "abs_basis_bps": abs_basis_desc,
        "recommended_cost_bps": recommended_cost_bps,
        "stress_cost_bps": stress_cost_bps,
        "extreme_cost_bps": extreme_cost_bps,
        "ready_failure_reasons": ready_reasons,
        "broker_load_meta": broker_meta,
        "reference_load_meta": reference_meta,
    }

    summary_path = out / "stage48f_broker_reference_alignment_cost_model_summary.json"
    cost_model_path = out / "stage48f_cost_model.json"
    session_path = out / "stage48f_session_cost_profile.csv"
    sample_path = out / "stage48f_alignment_sample.csv"
    report_path = out / "stage48f_broker_reference_alignment_cost_model_report.md"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    cost_model_path.write_text(json.dumps(cost_model, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(session_path, session_rows, ["session_utc", "rows", "median_spread_points", "p90_spread_points", "p95_spread_points", "p99_spread_points", "median_spread_cost_bps", "p90_spread_cost_bps", "p95_spread_cost_bps", "p99_spread_cost_bps", "median_abs_basis_bps", "p95_abs_basis_bps"])
    write_csv(sample_path, aligned_rows, ["time_utc", "session_utc", "broker_close", "reference_close", "basis_bps", "abs_basis_bps", "spread_points", "spread_price", "spread_cost_bps"])

    def fmt(x: Any, nd: int = 4) -> str:
        if x is None:
            return "n/a"
        if isinstance(x, float):
            return f"{x:.{nd}f}"
        return str(x)

    report = f"""# Stage48F Broker Reference Alignment and Cost Model Calibration

- status: `{status}`
- next_allowed_step: `{next_allowed}`
- promotion: `NO_GO`
- EA: `NO_GO`
- paper_live: `NO_GO`
- live: `NO_GO`

## Inputs

- broker_csv: `{broker_path}`
- reference_csv: `{reference_path if reference_path else 'NOT_FOUND'}`
- timeframe: `{args.timeframe}`
- point_size: `{args.point_size}`
- selected_broker_time_offset_hours: `{selected_offset}`

## Coverage

- broker_rows: `{len(broker_candles)}`
- broker_coverage_days: `{fmt(broker_meta.get('coverage_days'))}`
- broker_raw_spread_coverage_pct: `{fmt(broker_raw_spread_coverage_pct)}`
- aligned_spread_coverage_pct: `{fmt(aligned_spread_coverage_pct)}`
- reference_rows: `{len(reference_candles)}`
- aligned_rows: `{aligned_count}`
- aligned_coverage_days: `{fmt(aligned_days)}`

## Spread cost model

- median_spread_points: `{fmt(spread_points_desc.get('median'))}`
- p90_spread_points: `{fmt(spread_points_desc.get('p90'))}`
- p95_spread_points: `{fmt(spread_points_desc.get('p95'))}`
- p99_spread_points: `{fmt(spread_points_desc.get('p99'))}`
- median_spread_cost_bps: `{fmt(spread_cost_desc.get('median'))}`
- p90_spread_cost_bps: `{fmt(p90_cost)}`
- p95_spread_cost_bps: `{fmt(p95_cost)}`
- p99_spread_cost_bps: `{fmt(p99_cost)}`
- slippage_buffer_bps: `{fmt(args.slippage_buffer_bps)}`
- recommended_cost_bps: `{fmt(recommended_cost_bps)}`
- stress_cost_bps: `{fmt(stress_cost_bps)}`
- extreme_cost_bps: `{fmt(extreme_cost_bps)}`

## Broker-reference alignment

- median_basis_bps: `{fmt(basis_desc.get('median'))}`
- median_abs_basis_bps: `{fmt(abs_basis_desc.get('median'))}`
- p95_abs_basis_bps: `{fmt(abs_basis_desc.get('p95'))}`
- p99_abs_basis_bps: `{fmt(abs_basis_desc.get('p99'))}`

## Decision

ready_failure_reasons: `{ready_reasons}`

LoaderFix1 note: broker raw spread coverage is measured on accepted broker rows; aligned spread coverage is measured on aligned rows. Price basis is diagnostic and does not by itself authorize trading.

This stage calibrates cost and alignment only. It does not generate trading signals and does not allow EA, paper-live, or live action.
"""
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"stage": STAGE, "status": status, "broker_rows": len(broker_candles), "aligned_rows": aligned_count, "recommended_cost_bps": recommended_cost_bps, "out": str(out)}))
    return 0 if status.startswith("COST_MODEL_READY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
