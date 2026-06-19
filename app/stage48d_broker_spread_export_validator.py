#!/usr/bin/env python3
"""
Stage48D Broker Spread Export Validator
Research-only utility. It validates whether a broker/MT5-style CSV export contains enough
row-level numeric spread/bid/ask history to support execution-realism studies.
No trading signals are generated.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

STAGE = "Stage48D_BROKER_SPREAD_EXPORT_VALIDATOR"
PATCH = "Stage48D_LOADERFIX1_MT5_TAB_ANGLE_DATE_TIME_HEADER_SUPPORT"

TS_ALIASES = ["time_utc", "utc_time", "timestamp_utc", "timestamp", "datetime", "bar_time_utc", "server_time"]
DATE_ALIASES = ["date", "bar_date", "day"]
TIME_ALIASES = ["time", "bar_time", "hour"]
SYMBOL_ALIASES = ["symbol", "instrument", "pair"]
TIMEFRAME_ALIASES = ["timeframe", "interval", "tf", "period"]
OPEN_ALIASES = ["open", "o"]
HIGH_ALIASES = ["high", "h"]
LOW_ALIASES = ["low", "l"]
CLOSE_ALIASES = ["close", "c"]
SPREAD_ALIASES = ["spread_points", "spread", "spread_close", "spread_pips", "spread_raw"]
BID_ALIASES = ["bid", "bid_close", "close_bid"]
ASK_ALIASES = ["ask", "ask_close", "close_ask"]
SESSION_ALIASES = ["session_utc", "session"]
SOURCE_ALIASES = ["source", "provider", "broker", "server"]


def norm_name(s: str) -> str:
    # MT5 history-center exports often use headers like <DATE>, <TIME>, <OPEN>.
    # Normalize those to date/time/open so schema matching is robust.
    x = (s or "").strip().lower()
    for ch in "<>[](){}":
        x = x.replace(ch, "")
    return x.replace(" ", "_").replace("-", "_").replace(".", "_")


def pick(fieldnames: List[str], aliases: List[str]) -> Optional[str]:
    norm_to_real = {norm_name(f): f for f in fieldnames}
    for a in aliases:
        if norm_name(a) in norm_to_real:
            return norm_to_real[norm_name(a)]
    return None


def parse_ts(value: str) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    # MT5 exports may use 'YYYY.MM.DD HH:MM:SS'
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S.%f%z",
    ]
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def parse_ts_from_date_time(date_value: str, time_value: str) -> Optional[datetime]:
    date_s = str(date_value or "").strip()
    time_s = str(time_value or "").strip()
    if not date_s and not time_s:
        return None
    return parse_ts((date_s + " " + time_s).strip())


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "nan", "null", "false", "true"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def canonical_timeframe(s: Optional[str]) -> str:
    v = (s or "").strip().lower().replace(" ", "")
    aliases = {
        "m1": "M1", "1m": "M1", "1min": "M1", "1minute": "M1",
        "m5": "M5", "5m": "M5", "5min": "M5", "5minute": "M5",
        "m15": "M15", "15m": "M15", "15min": "M15", "15minute": "M15",
        "h1": "H1", "1h": "H1", "1hour": "H1", "60min": "H1",
    }
    return aliases.get(v, (s or "").strip().upper())


def infer_session(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 7:
        return "asia"
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 21:
        return "new_york"
    return "late_us"


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)


@dataclass
class Row:
    ts: datetime
    symbol: str
    timeframe: str
    spread: Optional[float]
    session: str


def read_csv_rows(path: Path, timeframe: str, symbol_contains: str) -> Tuple[List[Row], Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "raw_rows": 0,
        "accepted_rows": 0,
        "parse_fail_rows": 0,
        "timeframe_filtered_rows": 0,
        "symbol_filtered_rows": 0,
        "bad_timestamp_rows": 0,
        "bad_ohlc_rows": 0,
    }
    rows: List[Row] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except Exception:
            # Explicitly fall back to tab if the first line looks like a MT5 tab export.
            class _Tab(csv.excel):
                delimiter = "\t"
            first_line = sample.splitlines()[0] if sample.splitlines() else ""
            dialect = _Tab if first_line.count("\t") >= first_line.count(",") else csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = reader.fieldnames or []
        meta["fieldnames"] = fieldnames
        ts_col = pick(fieldnames, TS_ALIASES)
        date_col = pick(fieldnames, DATE_ALIASES)
        time_col = pick(fieldnames, TIME_ALIASES)
        sym_col = pick(fieldnames, SYMBOL_ALIASES)
        tf_col = pick(fieldnames, TIMEFRAME_ALIASES)
        spread_col = pick(fieldnames, SPREAD_ALIASES)
        bid_col = pick(fieldnames, BID_ALIASES)
        ask_col = pick(fieldnames, ASK_ALIASES)
        session_col = pick(fieldnames, SESSION_ALIASES)
        o_col = pick(fieldnames, OPEN_ALIASES)
        h_col = pick(fieldnames, HIGH_ALIASES)
        l_col = pick(fieldnames, LOW_ALIASES)
        c_col = pick(fieldnames, CLOSE_ALIASES)
        meta["mapping"] = {
            "ts": ts_col, "date": date_col, "time": time_col, "symbol": sym_col, "timeframe": tf_col,
            "spread": spread_col, "bid": bid_col, "ask": ask_col, "session": session_col,
            "open": o_col, "high": h_col, "low": l_col, "close": c_col,
        }
        # If there is a lone `time` column with no separate date column, treat it as timestamp.
        if not ts_col and time_col and not date_col:
            ts_col = time_col
            meta["mapping"]["ts"] = ts_col
        if not ts_col and not (date_col and time_col):
            meta["error"] = "NO_TIMESTAMP_OR_DATE_TIME_COLUMNS"
            return rows, meta
        meta["delimiter"] = getattr(dialect, "delimiter", None)
        target_tf = canonical_timeframe(timeframe)
        for r in reader:
            meta["raw_rows"] += 1
            if ts_col:
                dt = parse_ts(r.get(ts_col, ""))
            else:
                dt = parse_ts_from_date_time(r.get(date_col, ""), r.get(time_col, ""))
            if not dt:
                meta["bad_timestamp_rows"] += 1
                continue
            sym = (r.get(sym_col, "") if sym_col else "").strip()
            if symbol_contains and sym and symbol_contains.upper() not in sym.upper().replace("/", ""):
                meta["symbol_filtered_rows"] += 1
                continue
            tf = canonical_timeframe(r.get(tf_col, "") if tf_col else target_tf)
            if tf != target_tf:
                meta["timeframe_filtered_rows"] += 1
                continue
            # OHLC sanity if present; do not require OHLC for pure spread exports, but reject malformed OHLC if mapped.
            if all([o_col, h_col, l_col, c_col]):
                o, h, l, c = [to_float(r.get(col)) for col in [o_col, h_col, l_col, c_col]]
                if any(x is None for x in [o, h, l, c]) or h < l:
                    meta["bad_ohlc_rows"] += 1
                    continue
            spread = None
            if spread_col:
                spread = to_float(r.get(spread_col))
            if spread is None and bid_col and ask_col:
                bid = to_float(r.get(bid_col))
                ask = to_float(r.get(ask_col))
                if bid is not None and ask is not None and ask >= bid:
                    spread = ask - bid
            sess = (r.get(session_col, "") if session_col else "").strip() or infer_session(dt)
            rows.append(Row(dt, sym, tf, spread, sess))
    meta["accepted_rows"] = len(rows)
    return rows, meta


def summarize(rows: List[Row], min_rows: int, min_days: float, min_spread_coverage_pct: float) -> Dict[str, Any]:
    if not rows:
        return {
            "row_count": 0,
            "coverage_days": 0.0,
            "numeric_spread_rows": 0,
            "numeric_spread_coverage_pct": 0.0,
            "broker_spread_export_ready": False,
            "ready_failure_reasons": ["no_accepted_rows"],
        }
    rows_sorted = sorted(rows, key=lambda r: r.ts)
    start = rows_sorted[0].ts
    end = rows_sorted[-1].ts
    coverage_days = (end - start).total_seconds() / 86400.0 if end >= start else 0.0
    spreads = [r.spread for r in rows_sorted if r.spread is not None and r.spread > 0]
    spread_cov = 100.0 * len(spreads) / max(1, len(rows_sorted))
    failures = []
    if len(rows_sorted) < min_rows:
        failures.append(f"rows_lt_min_rows_{min_rows}")
    if coverage_days < min_days:
        failures.append(f"coverage_days_lt_min_days_{min_days}")
    if spread_cov < min_spread_coverage_pct:
        failures.append(f"numeric_spread_coverage_pct_lt_{min_spread_coverage_pct}")
    if not spreads:
        failures.append("no_positive_numeric_spread_rows")
    session_summary: Dict[str, Dict[str, Any]] = {}
    for sess in sorted(set(r.session for r in rows_sorted)):
        svals = [r.spread for r in rows_sorted if r.session == sess and r.spread is not None and r.spread > 0]
        session_summary[sess] = {
            "rows": sum(1 for r in rows_sorted if r.session == sess),
            "numeric_spread_rows": len(svals),
            "spread_coverage_pct": round(100.0 * len(svals) / max(1, sum(1 for r in rows_sorted if r.session == sess)), 3),
            "median_spread": median(svals) if svals else None,
            "p90_spread": percentile(svals, 0.90) if svals else None,
            "p95_spread": percentile(svals, 0.95) if svals else None,
            "p99_spread": percentile(svals, 0.99) if svals else None,
        }
    return {
        "row_count": len(rows_sorted),
        "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_days": coverage_days,
        "numeric_spread_rows": len(spreads),
        "numeric_spread_coverage_pct": spread_cov,
        "median_spread": median(spreads) if spreads else None,
        "p50_spread": percentile(spreads, 0.50) if spreads else None,
        "p90_spread": percentile(spreads, 0.90) if spreads else None,
        "p95_spread": percentile(spreads, 0.95) if spreads else None,
        "p99_spread": percentile(spreads, 0.99) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "session_summary": session_summary,
        "broker_spread_export_ready": len(failures) == 0,
        "ready_failure_reasons": failures,
    }


def discover_csvs(root: Path) -> List[Path]:
    dirs = [root / "data" / "broker_export", root / "data" / "mt5_export", root / "data" / "broker", root / "data" / "local"]
    out: List[Path] = []
    for d in dirs:
        if d.exists():
            out.extend(sorted(d.glob("*.csv")))
    return out


def write_report(out_dir: Path, summary: Dict[str, Any]) -> None:
    report_path = out_dir / "stage48d_broker_spread_export_validator_report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Stage48D Broker Spread Export Validator\n\n")
        for key in ["status", "next_allowed_step", "promotion", "EA", "paper_live", "live"]:
            f.write(f"- {key}: `{summary.get(key)}`\n")
        f.write("\n## Decision\n\n")
        d = summary.get("decision", {})
        for key in ["broker_spread_export_ready", "row_count", "coverage_days", "numeric_spread_rows", "numeric_spread_coverage_pct", "median_spread", "p90_spread", "p95_spread", "p99_spread"]:
            f.write(f"- {key}: `{d.get(key)}`\n")
        f.write("\nNo trading signal, EA, paper-live, or live action is allowed from this validation stage.\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--csv", dest="csv_path", default=None)
    ap.add_argument("--timeframe", default="M5")
    ap.add_argument("--symbol-contains", default="XAU")
    ap.add_argument("--min-rows", type=int, default=5000)
    ap.add_argument("--min-days", type=float, default=20.0)
    ap.add_argument("--min-spread-coverage-pct", type=float, default=80.0)
    ap.add_argument("--out", default="reports/stage48d")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_paths = [Path(args.csv_path)] if args.csv_path else discover_csvs(root)
    csv_paths = [p if p.is_absolute() else (root / p) for p in csv_paths]

    all_rows: List[Row] = []
    file_metas: List[Dict[str, Any]] = []
    for p in csv_paths:
        if not p.exists():
            file_metas.append({"path": str(p), "error": "FILE_NOT_FOUND"})
            continue
        rows, meta = read_csv_rows(p, args.timeframe, args.symbol_contains)
        all_rows.extend(rows)
        file_metas.append(meta)

    decision = summarize(all_rows, args.min_rows, args.min_days, args.min_spread_coverage_pct)
    ready = bool(decision.get("broker_spread_export_ready"))
    status = "BROKER_SPREAD_EXPORT_READY_NO_PROMOTION" if ready else "BROKER_SPREAD_EXPORT_INSUFFICIENT_NO_PROMOTION"
    next_step = "STAGE48E_BROKER_REALISM_DECISION_MEMO" if ready else "MT5_OR_BROKER_SPREAD_EXPORT_COLLECTION_REQUIRED"

    summary = {
        "stage": STAGE,
        "patch": PATCH,
        "status": status,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "next_allowed_step": next_step,
        "root": str(root),
        "csv_files_audited": len(csv_paths),
        "csv_paths": [str(p) for p in csv_paths],
        "thresholds": {
            "min_rows": args.min_rows,
            "min_days": args.min_days,
            "min_spread_coverage_pct": args.min_spread_coverage_pct,
        },
        "decision": decision,
        "file_metas_limited": file_metas[:20],
    }
    (out_dir / "stage48d_broker_spread_export_validator_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(out_dir, summary)
    print(json.dumps({"stage": STAGE, "status": status, "broker_spread_export_ready": ready, "row_count": decision.get("row_count"), "numeric_spread_coverage_pct": decision.get("numeric_spread_coverage_pct"), "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
