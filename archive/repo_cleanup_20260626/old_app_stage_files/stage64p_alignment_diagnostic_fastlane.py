#!/usr/bin/env python3
"""Stage64P alignment diagnostic fastlane (no order).

Runs a broker/spot alignment diagnostic across available broker timeframes and daily
session cutoffs. It does not generate signals, connect to a broker, or authorize orders.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


STAGE = "Stage64P_ALIGNMENT_DIAGNOSTIC_FASTLANE_NO_ORDER"
NO_ORDER_FLAGS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE64P",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
    "NO_COMMERCIALIZATION_WITHOUT_BROKER_SPOT_ALIGNMENT",
]


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_ts(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # tolerate timestamps with spaces and without tz
    try:
        x = dt.datetime.fromisoformat(s)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d"):
            try:
                x = dt.datetime.strptime(str(value).strip(), fmt)
                break
            except Exception:
                x = None  # type: ignore[assignment]
        if x is None:
            return None
    if x.tzinfo is not None:
        x = x.astimezone(dt.UTC).replace(tzinfo=None)
    return x


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        v = float(s)
    except Exception:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def date_only(value: dt.datetime) -> str:
    return value.date().isoformat()


def load_reference_returns(path: Path, date_col: str, close_col: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
    info: Dict[str, Any] = {
        "path": str(path),
        "found": path.exists(),
        "raw_rows": 0,
        "parsed_rows": 0,
        "parse_errors": 0,
        "date_col": date_col,
        "close_col": close_col,
    }
    closes: Dict[str, float] = {}
    if not path.exists():
        return {}, info
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        info["fields"] = reader.fieldnames or []
        for row in reader:
            info["raw_rows"] += 1
            t = parse_ts(row.get(date_col))
            c = parse_float(row.get(close_col))
            if t is None or c is None:
                info["parse_errors"] += 1
                continue
            closes[date_only(t)] = c
            info["parsed_rows"] += 1
    return close_to_returns(closes), info


def close_to_returns(closes: Dict[str, float]) -> Dict[str, float]:
    returns: Dict[str, float] = {}
    prev_date: Optional[str] = None
    prev_close: Optional[float] = None
    for d in sorted(closes.keys()):
        c = closes[d]
        if prev_close is not None and prev_close != 0:
            returns[d] = (c / prev_close) - 1.0
        prev_date = d
        prev_close = c
    return returns


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [str(r[1]) for r in cur.fetchall()]


def detect_col(columns: List[str], candidates: List[str]) -> Optional[str]:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def available_timeframes(conn: sqlite3.Connection, table: str, timeframe_col: str, symbol_col: Optional[str], symbol_like: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    params: List[Any] = []
    where = ""
    if symbol_col and symbol_like:
        where = f" WHERE {symbol_col} LIKE ?"
        params.append(symbol_like)
    q = f"SELECT {timeframe_col}, COUNT(*) FROM {table}{where} GROUP BY {timeframe_col} ORDER BY COUNT(*) DESC"
    out = []
    for tf, cnt in cur.execute(q, params).fetchall():
        out.append({"timeframe": str(tf), "row_count": int(cnt)})
    return out


def read_broker_rows(conn: sqlite3.Connection, table: str, time_col: str, close_col: str, timeframe_col: str,
                     timeframe: str, symbol_col: Optional[str], symbol_like: str,
                     row_limit: Optional[int] = None) -> Tuple[List[Tuple[dt.datetime, float]], Dict[str, Any]]:
    params: List[Any] = [timeframe]
    where = f"WHERE {timeframe_col} = ?"
    if symbol_col and symbol_like:
        where += f" AND {symbol_col} LIKE ?"
        params.append(symbol_like)
    limit_clause = ""
    if row_limit:
        limit_clause = f" LIMIT {int(row_limit)}"
    q = f"SELECT {time_col}, {close_col} FROM {table} {where} ORDER BY {time_col}{limit_clause}"
    rows: List[Tuple[dt.datetime, float]] = []
    info = {"raw_rows": 0, "parsed_rows": 0, "parse_errors": 0}
    for t_raw, c_raw in conn.execute(q, params):
        info["raw_rows"] += 1
        t = parse_ts(t_raw)
        c = parse_float(c_raw)
        if t is None or c is None:
            info["parse_errors"] += 1
            continue
        rows.append((t, c))
        info["parsed_rows"] += 1
    return rows, info


def derive_daily_closes(rows: List[Tuple[dt.datetime, float]], offset_hour: int) -> Dict[str, float]:
    # Daily session date is defined after subtracting cutoff offset hours; last tick/bar close per session date wins.
    # offset_hour=0 means UTC calendar day; offset_hour=22 means session day ending around 22:00 UTC.
    out: Dict[str, Tuple[dt.datetime, float]] = {}
    delta = dt.timedelta(hours=offset_hour)
    for t, c in rows:
        session_date = (t - delta).date().isoformat()
        prev = out.get(session_date)
        if prev is None or t >= prev[0]:
            out[session_date] = (t, c)
    return {d: c for d, (_, c) in out.items()}


def corr(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(vx * vy)


def percentile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    w = pos - lo
    return vals[lo] * (1 - w) + vals[hi] * w


def alignment_metrics(ref_returns: Dict[str, float], broker_closes: Dict[str, float]) -> Dict[str, Any]:
    br = close_to_returns(broker_closes)
    dates = sorted(set(ref_returns.keys()).intersection(br.keys()))
    xs = [ref_returns[d] for d in dates]
    ys = [br[d] for d in dates]
    diffs_bps = [abs((ys[i] - xs[i]) * 10000.0) for i in range(len(dates))]
    sign_agree = None
    if dates:
        sign_agree = sum((xs[i] >= 0) == (ys[i] >= 0) for i in range(len(dates))) / len(dates)
    return {
        "overlap_return_days": len(dates),
        "first_overlap_date": dates[0] if dates else None,
        "last_overlap_date": dates[-1] if dates else None,
        "return_correlation": corr(xs, ys),
        "sign_agreement": sign_agree,
        "median_abs_return_diff_bps": percentile(diffs_bps, 0.5),
        "p90_abs_return_diff_bps": percentile(diffs_bps, 0.9),
    }


def gate_metrics(metrics: Dict[str, Any], gates: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    specs = [
        ("min_overlap_days", "overlap_return_days", ">=", gates.get("min_overlap_days", 500)),
        ("return_correlation", "return_correlation", ">=", gates.get("return_correlation_min", 0.95)),
        ("sign_agreement", "sign_agreement", ">=", gates.get("sign_agreement_min", 0.70)),
        ("median_abs_return_diff_bps", "median_abs_return_diff_bps", "<=", gates.get("median_abs_return_diff_bps_max", 20.0)),
        ("p90_abs_return_diff_bps", "p90_abs_return_diff_bps", "<=", gates.get("p90_abs_return_diff_bps_max", 100.0)),
    ]
    out = []
    all_pass = True
    for gate_name, key, op, th in specs:
        val = metrics.get(key)
        passed = False
        if val is not None:
            if op == ">=":
                passed = float(val) >= float(th)
            elif op == "<=":
                passed = float(val) <= float(th)
        all_pass = all_pass and passed
        out.append({"gate": gate_name, "value": val, "op": op, "threshold": th, "pass": passed})
    return out, all_pass


def safe_float_for_sort(v: Any, default: float) -> float:
    try:
        if v is None:
            return default
        x = float(v)
        if math.isnan(x):
            return default
        return x
    except Exception:
        return default


def score_candidate(row: Dict[str, Any]) -> Tuple[int, float, float, float, float]:
    # Higher is better. Pass count, correlation, sign agreement, negative median/p90 diff.
    pass_count = int(row.get("gate_pass_count", 0))
    return (
        pass_count,
        safe_float_for_sort(row.get("return_correlation"), -999.0),
        safe_float_for_sort(row.get("sign_agreement"), -999.0),
        -safe_float_for_sort(row.get("median_abs_return_diff_bps"), 999999.0),
        -safe_float_for_sort(row.get("p90_abs_return_diff_bps"), 999999.0),
    )


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_broker_raw_csv(path: Path, daily_closes: Dict[str, float], source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = sorted(daily_closes.keys())
    # We only have derived closes. For contract compatibility, OHLC are set to close and volume blank/0.
    with path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["date_utc", "open", "high", "low", "close", "volume", "source", "available_after_utc"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in dates:
            c = daily_closes[d]
            writer.writerow({
                "date_utc": f"{d}T00:00:00Z",
                "open": f"{c:.6f}",
                "high": f"{c:.6f}",
                "low": f"{c:.6f}",
                "close": f"{c:.6f}",
                "volume": "0",
                "source": source,
                "available_after_utc": f"{d}T23:59:59Z",
            })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    cfg = load_json(root / args.config, {})
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_utc = utc_now()
    stage64o_summary_path = root / cfg.get("stage64o_summary", "reports/stage64o_external_replication_broker_alignment_fastlane/stage64o_external_replication_broker_alignment_fastlane_summary.json")
    stage64o = load_json(stage64o_summary_path, {}) or {}

    ref_path = root / cfg.get("gold_reference_csv", "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv")
    ref_returns, ref_info = load_reference_returns(ref_path, cfg.get("gold_reference_date_col", "date_utc"), cfg.get("gold_reference_close_col", "close"))

    sqlite_path = root / cfg.get("broker_sqlite", "data/broker_normalized/amarkets_multitf.sqlite")
    table = cfg.get("broker_table", "amarkets_bars")
    symbol_like = cfg.get("symbol_like", "%XAUUSD%")
    gates_cfg = cfg.get("alignment_gates", {})
    offsets = cfg.get("session_close_offset_hours_scan", list(range(0, 24)))
    preferred_tfs = cfg.get("timeframe_preference", ["D1", "H1", "M30", "M15", "M5"])
    include_m1 = bool(cfg.get("include_m1_scan", False))
    if include_m1 and "M1" not in preferred_tfs:
        preferred_tfs.append("M1")

    broker_info: Dict[str, Any] = {"sqlite_path": str(sqlite_path), "found": sqlite_path.exists(), "table": table}
    all_rows: List[Dict[str, Any]] = []
    best_daily_closes: Dict[str, float] = {}
    best_source = ""

    if sqlite_path.exists() and ref_returns:
        try:
            conn = sqlite3.connect(str(sqlite_path))
            columns = table_columns(conn, table)
            broker_info["columns"] = columns
            time_col = detect_col(columns, ["time_utc", "utc_time", "date_utc", "timestamp", "time"])
            close_col = detect_col(columns, ["close", "Close", "bid_close", "ask_close"])
            tf_col = detect_col(columns, ["timeframe", "tf", "source_timeframe"])
            symbol_col = detect_col(columns, ["symbol", "instrument", "ticker"])
            broker_info.update({"time_col": time_col, "close_col": close_col, "timeframe_col": tf_col, "symbol_col": symbol_col})
            if not time_col or not close_col or not tf_col:
                broker_info["issue"] = "required_columns_missing_after_loaderfix"
            else:
                available = available_timeframes(conn, table, tf_col, symbol_col, symbol_like)
                broker_info["available_timeframes"] = available
                available_set = {x["timeframe"] for x in available}
                scan_tfs = [tf for tf in preferred_tfs if tf in available_set]
                if not include_m1 and "M1" in scan_tfs:
                    scan_tfs.remove("M1")
                broker_info["scanned_timeframes"] = scan_tfs
                for tf in scan_tfs:
                    rows, rinfo = read_broker_rows(conn, table, time_col, close_col, tf_col, tf, symbol_col, symbol_like)
                    for off in offsets:
                        closes = derive_daily_closes(rows, int(off))
                        metrics = alignment_metrics(ref_returns, closes)
                        gates, passed = gate_metrics(metrics, gates_cfg)
                        pass_count = sum(1 for g in gates if g["pass"])
                        row: Dict[str, Any] = {
                            "timeframe": tf,
                            "session_close_offset_hours": int(off),
                            "broker_raw_rows": rinfo["raw_rows"],
                            "broker_parsed_rows": rinfo["parsed_rows"],
                            "broker_daily_rows": len(closes),
                            **metrics,
                            "gate_pass_count": pass_count,
                            "alignment_pass": passed,
                        }
                        for g in gates:
                            row[f"gate_{g['gate']}"] = g["pass"]
                        all_rows.append(row)
                conn.close()
        except Exception as e:
            broker_info["issue"] = f"sqlite_alignment_exception: {type(e).__name__}: {e}"
    else:
        if not sqlite_path.exists():
            broker_info["issue"] = "sqlite_missing"
        elif not ref_returns:
            broker_info["issue"] = "reference_returns_missing"

    all_rows_sorted = sorted(all_rows, key=score_candidate, reverse=True)
    best = all_rows_sorted[0] if all_rows_sorted else None
    if best:
        # Rebuild best daily closes for optional output.
        try:
            conn = sqlite3.connect(str(sqlite_path))
            columns = table_columns(conn, table)
            time_col = detect_col(columns, ["time_utc", "utc_time", "date_utc", "timestamp", "time"])
            close_col = detect_col(columns, ["close", "Close", "bid_close", "ask_close"])
            tf_col = detect_col(columns, ["timeframe", "tf", "source_timeframe"])
            symbol_col = detect_col(columns, ["symbol", "instrument", "ticker"])
            if time_col and close_col and tf_col:
                rows, _ = read_broker_rows(conn, table, time_col, close_col, tf_col, str(best["timeframe"]), symbol_col, symbol_like)
                best_daily_closes = derive_daily_closes(rows, int(best["session_close_offset_hours"]))
                best_source = f"AMARKETS_SQLITE_DERIVED_{best['timeframe']}_OFFSET_{best['session_close_offset_hours']}H_NO_BROKER_CONNECTION"
            conn.close()
        except Exception:
            pass

    accepted_broker_file = root / cfg.get("accepted_broker_spot_output_csv", "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv")
    broker_alignment_pass = bool(best and best.get("alignment_pass"))
    if broker_alignment_pass and best_daily_closes:
        write_broker_raw_csv(accepted_broker_file, best_daily_closes, best_source)

    decision = (
        "BROKER_SPOT_ALIGNMENT_DIAGNOSTIC_PASS_STAGE64Q_BROKER_VALIDATION_DESIGN_NO_ORDER"
        if broker_alignment_pass else
        "BROKER_SPOT_ALIGNMENT_DIAGNOSTIC_FAIL_REFERENCE_OR_BROKER_DATA_REDESIGN_REQUIRED_NO_ORDER"
    )

    summary: Dict[str, Any] = {
        "stage": STAGE,
        "status": "ALIGNMENT_DIAGNOSTIC_FASTLANE_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": generated_utc,
        "root": str(root),
        "inputs": {
            "config": str(root / args.config),
            "stage64o_summary": str(stage64o_summary_path),
            "gold_reference_csv": str(ref_path),
            "broker_sqlite": str(sqlite_path),
        },
        "stage64o_input_decision": stage64o.get("decision"),
        "reference_info": ref_info,
        "broker_info": broker_info,
        "scan": {
            "candidate_rows": len(all_rows_sorted),
            "timeframes_scanned": broker_info.get("scanned_timeframes", []),
            "offsets_scanned": offsets,
            "alignment_gates": gates_cfg,
        },
        "best_alignment": best,
        "top10_alignment_candidates": all_rows_sorted[:10],
        "broker_alignment_pass": broker_alignment_pass,
        "accepted_broker_spot_output_csv": str(accepted_broker_file) if broker_alignment_pass else None,
        "executive_conclusion": (
            "Broker/spot alignment passed under the selected session/timeframe diagnostic. The accepted broker D1 file was written for later no-order broker-specific validation design."
            if broker_alignment_pass else
            "Broker/spot alignment did not pass the declared gates under the tested timeframe/session variants. Keep the survivor research-only and redesign/acquire broker/reference alignment data before any broker claim."
        ),
        "next_allowed_step": (
            "Stage64Q_BROKER_SPECIFIC_VALIDATION_DESIGN_NO_ORDER"
            if broker_alignment_pass else
            "Stage64Q_ALIGNMENT_REDESIGN_OR_EXTERNAL_BROKER_D1_ACQUISITION_NO_ORDER"
        ),
        "hard_blocks": NO_ORDER_FLAGS,
        "outputs": {
            "summary_json": str(out_dir / "stage64p_alignment_diagnostic_fastlane_summary.json"),
            "report_md": str(out_dir / "stage64p_alignment_diagnostic_fastlane_report.md"),
            "candidate_metrics_csv": str(out_dir / "stage64p_alignment_candidate_metrics.csv"),
            "top10_alignment_candidates_json": str(out_dir / "stage64p_top10_alignment_candidates.json"),
        },
    }

    write_csv(out_dir / "stage64p_alignment_candidate_metrics.csv", all_rows_sorted)
    write_json(out_dir / "stage64p_top10_alignment_candidates.json", all_rows_sorted[:10])
    write_json(out_dir / "stage64p_alignment_diagnostic_fastlane_summary.json", summary)

    # Report
    lines: List[str] = []
    lines.append("# Stage64P - Alignment Diagnostic Fastlane (No Order)\n")
    lines.append(f"Generated UTC: `{generated_utc}`\n")
    lines.append("## Status\n")
    lines.append("- status: `ALIGNMENT_DIAGNOSTIC_FASTLANE_COMPLETE_NO_PROMOTION`")
    lines.append(f"- decision: `{decision}`")
    lines.append("- promotion/paper/live: `NO_GO`")
    lines.append("- validation_allowed_for_order_or_promotion: `False`\n")
    lines.append("## Executive conclusion\n")
    lines.append(summary["executive_conclusion"] + "\n")
    lines.append("## Best alignment candidate\n")
    if best:
        lines.append("| metric | value |")
        lines.append("|---|---:|")
        for k in ["timeframe", "session_close_offset_hours", "broker_daily_rows", "overlap_return_days", "return_correlation", "sign_agreement", "median_abs_return_diff_bps", "p90_abs_return_diff_bps", "gate_pass_count", "alignment_pass"]:
            lines.append(f"| `{k}` | `{best.get(k)}` |")
        lines.append("")
    else:
        lines.append("No alignment candidate could be computed.\n")
    lines.append("## Top candidates\n")
    if all_rows_sorted:
        lines.append("| timeframe | offset_h | overlap | corr | sign | median_diff_bps | p90_diff_bps | pass_count | alignment_pass |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in all_rows_sorted[:10]:
            lines.append(
                f"| `{r.get('timeframe')}` | `{r.get('session_close_offset_hours')}` | `{r.get('overlap_return_days')}` | "
                f"`{r.get('return_correlation')}` | `{r.get('sign_agreement')}` | `{r.get('median_abs_return_diff_bps')}` | "
                f"`{r.get('p90_abs_return_diff_bps')}` | `{r.get('gate_pass_count')}` | `{r.get('alignment_pass')}` |"
            )
        lines.append("")
    lines.append("## Broker info\n")
    lines.append(f"- sqlite_found: `{broker_info.get('found')}`")
    lines.append(f"- time_col: `{broker_info.get('time_col')}`")
    lines.append(f"- close_col: `{broker_info.get('close_col')}`")
    lines.append(f"- timeframe_col: `{broker_info.get('timeframe_col')}`")
    lines.append(f"- scanned_timeframes: `{broker_info.get('scanned_timeframes')}`\n")
    lines.append("## Hard blocks\n")
    for x in NO_ORDER_FLAGS:
        lines.append(f"- `{x}`")
    lines.append("\n## Next allowed step\n")
    lines.append(f"`{summary['next_allowed_step']}`\n")
    (out_dir / "stage64p_alignment_diagnostic_fastlane_report.md").write_text("\n".join(lines), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
