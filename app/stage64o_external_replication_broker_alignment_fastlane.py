#!/usr/bin/env python3
"""
Stage64O LoaderFix1 - External replication bundle and broker/spot D1 alignment fastlane.

No order path, no broker connection, no paper/live authorization.

Fix: derive broker D1 from the actual AMarkets SQLite schema using `time_utc`
when `utc_time` is not present, and aggregate intraday bars to D1 before alignment.
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

STAGE = "Stage64O_EXTERNAL_REPLICATION_BROKER_ALIGNMENT_FASTLANE_NO_ORDER_LOADERFIX1"
REQUIRED_N4_DECISION = "FASTLANE_REPLICATION_PASSED_ALIGNMENT_CONTRACT_DECLARED_STAGE64O_ALLOWED_NO_ORDER"

HARD_BLOCKS = [
    "NO_PAPER_ORDER",
    "NO_EA_PROMOTION",
    "NO_PAPER_LIVE",
    "NO_LIVE",
    "NO_BROKER_CONNECTION",
    "NO_ORDER_AUTHORIZATION_FROM_STAGE64O_LOADERFIX1",
    "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
    "NO_POST_HOC_EVENT_EXCLUSION",
    "NO_REDUCED_SCOPE_RETEST",
    "NO_RESCUE_FILTERING",
    "NO_NEW_INTRADAY_SCAN",
    "NO_COMMERCIALIZATION_WITHOUT_BROKER_SPOT_ALIGNMENT",
]


def utc_now_z() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_col(c: str) -> str:
    return (c or "").strip().lower().replace(" ", "_").replace("-", "_")


def pick_col(fieldnames: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    fields = list(fieldnames or [])
    by_norm = {norm_col(c): c for c in fields}
    for cand in candidates:
        if norm_col(cand) in by_norm:
            return by_norm[norm_col(cand)]
    return None


def parse_dt(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Common MT5 / CSV formats.
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y.%m.%d",
    ]
    try:
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.UTC)
        return d.astimezone(dt.UTC)
    except Exception:
        pass
    for fmt in formats:
        try:
            d = dt.datetime.strptime(s, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.UTC)
            return d.astimezone(dt.UTC)
        except Exception:
            continue
    return None


def to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        s = str(v).strip().replace(",", "")
        if s == "":
            return None
        x = float(s)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return None


def read_daily_csv(path: Path) -> Tuple[Dict[str, float], Dict[str, Any]]:
    info: Dict[str, Any] = {
        "path": str(path), "found": path.exists(), "raw_rows": 0, "parsed_rows": 0,
        "parse_errors": 0, "fields": [], "date_col": None, "close_col": None,
    }
    out: Dict[str, float] = {}
    if not path.exists():
        return out, info
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        fields = rdr.fieldnames or []
        info["fields"] = fields
        date_col = pick_col(fields, ["date_utc", "time_utc", "utc_time", "timestamp", "time", "date"])
        close_col = pick_col(fields, ["close", "Close", "close_price", "bid_close"])
        info["date_col"] = date_col
        info["close_col"] = close_col
        if not date_col or not close_col:
            info["issue"] = "required_columns_missing"
            return out, info
        for row in rdr:
            info["raw_rows"] += 1
            d = parse_dt(row.get(date_col))
            c = to_float(row.get(close_col))
            if d is None or c is None:
                info["parse_errors"] += 1
                continue
            out[d.date().isoformat()] = c
            info["parsed_rows"] += 1
    return out, info


def sqlite_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def select_sqlite_timeframe(conn: sqlite3.Connection, table: str, tf_col: Optional[str], symbol_col: Optional[str], symbol_like: str, preferences: List[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {"selected_timeframe": None, "available_timeframes": [], "symbol_filter_used": False}
    if not tf_col:
        return info
    where = ""
    params: List[Any] = []
    if symbol_col:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {symbol_col} LIKE ?", (symbol_like,)).fetchone()[0]
        if cnt > 0:
            where = f"WHERE {symbol_col} LIKE ?"
            params = [symbol_like]
            info["symbol_filter_used"] = True
    rows = conn.execute(
        f"SELECT {tf_col}, COUNT(*) FROM {table} {where} GROUP BY {tf_col}", params
    ).fetchall()
    avail = [{"timeframe": str(r[0]), "row_count": int(r[1])} for r in rows]
    info["available_timeframes"] = avail
    norm_to_actual = {str(r[0]).strip().upper(): str(r[0]) for r in rows}
    for pref in preferences:
        p = pref.strip().upper()
        if p in norm_to_actual:
            info["selected_timeframe"] = norm_to_actual[p]
            return info
    if rows:
        # Fallback to the smallest row count that still likely covers enough history.
        # Prefer higher timeframe over M1 when explicit preferences did not match.
        sorted_rows = sorted(rows, key=lambda r: int(r[1]))
        info["selected_timeframe"] = str(sorted_rows[0][0])
    return info


def derive_daily_from_sqlite(sqlite_path: Path, table: str, preferences: List[str], symbol_like: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
    info: Dict[str, Any] = {
        "source": "sqlite_derived", "sqlite_path": str(sqlite_path), "found": sqlite_path.exists(),
        "table": table, "selected_timeframe": None, "columns": [], "raw_rows": 0,
        "parsed_rows": 0, "daily_rows": 0, "parse_errors": 0,
    }
    if not sqlite_path.exists():
        info["issue"] = "sqlite_missing"
        return {}, info
    out: Dict[str, float] = {}
    daily_rows: Dict[str, List[Tuple[dt.datetime, float, Optional[float], Optional[float], Optional[float]]]] = {}
    conn = sqlite3.connect(str(sqlite_path))
    try:
        if not sqlite_table_exists(conn, table):
            info["issue"] = "table_missing"
            return {}, info
        cols = sqlite_columns(conn, table)
        info["columns"] = cols
        time_col = pick_col(cols, ["time_utc", "utc_time", "date_utc", "timestamp", "time", "server_time"])
        close_col = pick_col(cols, ["close", "Close"])
        open_col = pick_col(cols, ["open", "Open"])
        high_col = pick_col(cols, ["high", "High"])
        low_col = pick_col(cols, ["low", "Low"])
        tf_col = pick_col(cols, ["timeframe", "source_timeframe", "tf"])
        symbol_col = pick_col(cols, ["symbol", "instrument", "ticker"])
        info.update({"time_col": time_col, "close_col": close_col, "open_col": open_col, "high_col": high_col, "low_col": low_col, "timeframe_col": tf_col, "symbol_col": symbol_col})
        if not time_col or not close_col:
            info["issue"] = "required_columns_missing"
            return {}, info
        tf_info = select_sqlite_timeframe(conn, table, tf_col, symbol_col, symbol_like, preferences)
        info.update(tf_info)
        selected_tf = tf_info.get("selected_timeframe")
        where_parts: List[str] = []
        params: List[Any] = []
        if selected_tf is not None and tf_col:
            where_parts.append(f"{tf_col} = ?")
            params.append(selected_tf)
        if symbol_col and tf_info.get("symbol_filter_used"):
            where_parts.append(f"{symbol_col} LIKE ?")
            params.append(symbol_like)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        cols_select = [time_col, close_col]
        # Keep aliases simple by positional row access.
        q = f"SELECT {', '.join(cols_select)} FROM {table} {where} ORDER BY {time_col} ASC"
        for t_raw, c_raw in conn.execute(q, params):
            info["raw_rows"] += 1
            t = parse_dt(t_raw)
            c = to_float(c_raw)
            if t is None or c is None:
                info["parse_errors"] += 1
                continue
            dkey = t.date().isoformat()
            daily_rows.setdefault(dkey, []).append((t, c, None, None, None))
            info["parsed_rows"] += 1
        for dkey, vals in daily_rows.items():
            vals.sort(key=lambda x: x[0])
            out[dkey] = vals[-1][1]
        info["daily_rows"] = len(out)
        if not out:
            info["issue"] = "no_derived_daily_rows"
    finally:
        conn.close()
    return out, info


def returns_from_closes(closes: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    prev_date = None
    prev_close = None
    for d in sorted(closes):
        c = closes[d]
        if prev_close is not None and prev_close > 0:
            out[d] = (c / prev_close) - 1.0
        prev_date, prev_close = d, c
    return out


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def quantile(vals: List[float], q: float) -> Optional[float]:
    if not vals:
        return None
    vals = sorted(vals)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def alignment_metrics(gold: Dict[str, float], broker: Dict[str, float], thresholds: Dict[str, float]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    gr = returns_from_closes(gold)
    br = returns_from_closes(broker)
    common = sorted(set(gr).intersection(br))
    xs = [gr[d] for d in common]
    ys = [br[d] for d in common]
    diffs_bps = [abs((ys[i] - xs[i]) * 10000.0) for i in range(len(common))]
    sign_agree = [1 for i in range(len(common)) if (xs[i] == 0 and ys[i] == 0) or (xs[i] > 0 and ys[i] > 0) or (xs[i] < 0 and ys[i] < 0)]
    metrics: Dict[str, Any] = {
        "overlap_return_days": len(common),
        "first_overlap_date": common[0] if common else None,
        "last_overlap_date": common[-1] if common else None,
        "return_correlation": pearson(xs, ys),
        "sign_agreement": (len(sign_agree) / len(common)) if common else None,
        "median_abs_return_diff_bps": statistics.median(diffs_bps) if diffs_bps else None,
        "p90_abs_return_diff_bps": quantile(diffs_bps, 0.90),
    }
    gates = [
        ("min_overlap_days", metrics["overlap_return_days"], ">=", thresholds.get("min_overlap_days", 500)),
        ("return_correlation", metrics["return_correlation"], ">=", thresholds.get("return_correlation_min", 0.95)),
        ("sign_agreement", metrics["sign_agreement"], ">=", thresholds.get("sign_agreement_min", 0.70)),
        ("median_abs_return_diff_bps", metrics["median_abs_return_diff_bps"], "<=", thresholds.get("median_abs_return_diff_bps_max", 20.0)),
        ("p90_abs_return_diff_bps", metrics["p90_abs_return_diff_bps"], "<=", thresholds.get("p90_abs_return_diff_bps_max", 100.0)),
    ]
    gate_rows: List[Dict[str, Any]] = []
    for name, value, op, threshold in gates:
        passed = False
        if value is not None:
            passed = (value >= threshold) if op == ">=" else (value <= threshold)
        gate_rows.append({"gate": name, "value": value, "op": op, "threshold": threshold, "pass": bool(passed)})
    metrics["alignment_pass"] = all(r["pass"] for r in gate_rows)
    return metrics, gate_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_report(summary: Dict[str, Any]) -> str:
    ba = summary.get("broker_spot_alignment", {})
    metrics = ba.get("metrics", {}) or {}
    gates = ba.get("gates", []) or []
    lines = []
    lines.append("# Stage64O LoaderFix1 - External Replication Bundle and Broker/Spot Alignment Fastlane (No Order)")
    lines.append("")
    lines.append(f"Generated UTC: `{summary['generated_utc']}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    for k in ["status", "decision", "promotion", "paper_order", "paper_live", "live", "validation_allowed_for_order_or_promotion"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append(summary.get("executive_conclusion", ""))
    lines.append("")
    lines.append("## LoaderFix1")
    lines.append("")
    lines.append("SQLite broker derivation now accepts `time_utc` as the primary timestamp column and derives D1 closes from the selected broker timeframe before alignment.")
    lines.append("")
    lines.append("## External replication bundle")
    lines.append("")
    erb = summary.get("external_replication_bundle", {})
    lines.append(f"- manifest: `{summary['outputs']['external_replication_bundle_manifest_json']}`")
    lines.append(f"- input_files_hashed: `{len(erb.get('input_file_manifest', []))}`")
    lines.append("")
    lines.append("## Broker/spot alignment")
    lines.append("")
    lines.append(f"- data_available: `{ba.get('data_available')}`")
    lines.append(f"- alignment_pass: `{ba.get('alignment_pass')}`")
    lines.append(f"- broker_source_mode: `{ba.get('broker_source_mode')}`")
    if ba.get("broker_info"):
        bi = ba["broker_info"]
        lines.append(f"- broker_selected_timeframe: `{bi.get('selected_timeframe')}`")
        lines.append(f"- broker_daily_rows: `{bi.get('daily_rows')}`")
        if bi.get("time_col"):
            lines.append(f"- broker_time_col: `{bi.get('time_col')}`")
    if metrics:
        lines.append("")
        lines.append("### Metrics")
        lines.append("")
        for k, v in metrics.items():
            if k == "alignment_pass":
                continue
            lines.append(f"- {k}: `{v}`")
    if gates:
        lines.append("")
        lines.append("### Gates")
        lines.append("")
        lines.append("| gate | value | op | threshold | pass |")
        lines.append("|---|---:|---|---:|---:|")
        for g in gates:
            lines.append(f"| `{g['gate']}` | `{g['value']}` | `{g['op']}` | `{g['threshold']}` | `{g['pass']}` |")
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for h in summary.get("hard_blocks", []):
        lines.append(f"- `{h}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary.get('next_allowed_step')}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    cfg = read_json(config_path, {}) or {}

    n4_path = root / cfg.get("stage64n4_summary", "reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_summary.json")
    n4 = read_json(n4_path, {}) or {}
    n4_checks = {
        "stage64n4_decision": n4.get("decision"),
        "expected_decision": REQUIRED_N4_DECISION,
        "n4_decision_ok": n4.get("decision") == REQUIRED_N4_DECISION,
        "n4_replication_pass": bool(n4.get("replication_pass")),
        "n4_no_order_flags_ok": all(n4.get(k) == "NO_GO" for k in ["promotion", "EA", "paper_order", "paper_live", "live"]),
    }
    n4_checks["input_ok"] = all([n4_checks["n4_decision_ok"], n4_checks["n4_replication_pass"], n4_checks["n4_no_order_flags_ok"]])

    bundle_paths = cfg.get("external_bundle_input_paths") or [
        "reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_summary.json",
        "reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_report.md",
        "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv",
        "reports/stage64l_full_scope_walk_forward_validation_design/stage64l_full_scope_walk_forward_validation_design_summary.json",
        "reports/stage64m_full_scope_walk_forward_validation_run/stage64m_full_scope_walk_forward_validation_run_summary.json",
        "reports/stage64n1b_a2_nonparametric_reconciliation/stage64n1b_a2_nonparametric_reconciliation_summary.json",
        "reports/stage64n3_corrected_survivor_replication_alignment_decision/stage64n3_corrected_survivor_replication_alignment_decision_summary.json",
        str(config_path.relative_to(root)) if str(config_path).startswith(str(root)) else str(config_path),
    ]
    file_manifest = []
    for rel in bundle_paths:
        p = Path(rel)
        if not p.is_absolute():
            p = root / p
        file_manifest.append({
            "path": str(Path(rel)),
            "found": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() and p.is_file() else 0,
            "sha256": sha256_file(p),
        })
    target = n4.get("target_survivor") or {"hypothesis_id": "H64L_H1_FULL_MACRO_TAILWIND_LONG", "horizon_days": 120, "primary_benchmark_id": "H64L_B1_GOLD_TREND_ONLY_REFERENCE"}
    external_bundle = {
        "stage": STAGE,
        "created_utc": utc_now_z(),
        "purpose": "Local manifest for external/no-order reproduction of the Stage64 survivor. Data files may be local-only and are represented by hashes.",
        "target_survivor": target,
        "n4_independent_replication_headline": n4.get("independent_replication", {}),
        "input_file_manifest": file_manifest,
        "no_order_policy": "This bundle does not authorize order generation, broker connection, paper-live, live, or commercialization claims.",
    }

    gold_path = root / cfg.get("gold_reference_csv", "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv")
    gold_closes, gold_info = read_daily_csv(gold_path)

    broker_d1_csv = root / cfg.get("broker_spot_d1_csv", "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv")
    broker_closes, broker_info = read_daily_csv(broker_d1_csv)
    broker_source_mode = "csv" if broker_closes else "missing"
    if not broker_closes:
        sqlite_path = root / cfg.get("broker_sqlite", "data/broker_normalized/amarkets_multitf.sqlite")
        broker_closes, broker_info = derive_daily_from_sqlite(
            sqlite_path=sqlite_path,
            table=cfg.get("broker_sqlite_table", "amarkets_bars"),
            preferences=cfg.get("timeframe_preference", ["D1", "DAILY", "1D", "H1", "1H", "M30", "30M", "M15", "15M", "M5", "5M", "M1", "1M"]),
            symbol_like=cfg.get("broker_symbol_like", "%XAU%"),
        )
        if broker_closes:
            broker_source_mode = "sqlite_derived"

    thresholds = cfg.get("alignment_thresholds", {}) or {}
    metrics: Dict[str, Any] = {}
    gates: List[Dict[str, Any]] = []
    if gold_closes and broker_closes:
        metrics, gates = alignment_metrics(gold_closes, broker_closes, thresholds)
    data_available = bool(gold_closes and broker_closes and metrics.get("overlap_return_days", 0) > 0)
    alignment_pass = bool(metrics.get("alignment_pass")) if data_available else False

    broker_alignment = {
        "data_available": data_available,
        "alignment_pass": alignment_pass,
        "broker_source_mode": broker_source_mode,
        "gold_reference_info": gold_info,
        "broker_info": broker_info,
        "metrics": metrics,
        "gates": gates,
    }
    if not data_available:
        broker_alignment["issue"] = "missing_gold_reference_or_broker_d1_data"

    if not n4_checks["input_ok"]:
        decision = "INPUT_BLOCKED_STAGE64O_LOADERFIX1_NO_ORDER"
        next_step = "FIX_STAGE64N4_INPUTS_NO_ORDER"
        conclusion = "Stage64N4 input checks failed. No continuation, order, or broker claim is authorized."
    elif alignment_pass:
        decision = "EXTERNAL_REPLICATION_BUNDLE_READY_BROKER_ALIGNMENT_PASSED_STAGE64P_ALLOWED_NO_ORDER"
        next_step = "Stage64P_REPLICATION_ALIGNMENT_DECISION_NO_ORDER"
        conclusion = "External replication bundle is ready and offline broker/spot alignment passed. The survivor remains research-only; proceed only to no-order decision governance."
    elif data_available:
        decision = "EXTERNAL_REPLICATION_BUNDLE_READY_BROKER_ALIGNMENT_FAILED_STAGE64P_DECISION_NO_ORDER"
        next_step = "Stage64P_ALIGNMENT_FAIL_OR_REDESIGN_DECISION_NO_ORDER"
        conclusion = "External replication bundle is ready, but broker/spot alignment failed at least one gate. No broker XAUUSD claim or order path is authorized."
    else:
        decision = "EXTERNAL_REPLICATION_BUNDLE_READY_BROKER_ALIGNMENT_DATA_REQUIRED_NO_ORDER"
        next_step = "ACQUIRE_BROKER_SPOT_D1_DATA_OR_RUN_STAGE64P_DECISION_NO_ORDER"
        conclusion = "External replication bundle was created. Broker/spot alignment data is still unavailable, so broker XAUUSD claims and any order path remain blocked."

    outputs = {
        "summary_json": str(out_dir / "stage64o_external_replication_broker_alignment_fastlane_summary.json"),
        "report_md": str(out_dir / "stage64o_external_replication_broker_alignment_fastlane_report.md"),
        "external_replication_bundle_manifest_json": str(out_dir / "stage64o_external_replication_bundle_manifest.json"),
        "broker_spot_alignment_metrics_json": str(out_dir / "stage64o_broker_spot_alignment_metrics.json"),
        "broker_spot_alignment_gates_csv": str(out_dir / "stage64o_broker_spot_alignment_gates.csv"),
    }
    summary = {
        "stage": STAGE,
        "status": "EXTERNAL_REPLICATION_BROKER_ALIGNMENT_FASTLANE_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": external_bundle["created_utc"],
        "root": str(root),
        "inputs": {"config": str(config_path), "stage64n4_summary": str(n4_path)},
        "n4_input_checks": n4_checks,
        "target_survivor": target,
        "external_replication_bundle": external_bundle,
        "broker_spot_alignment": broker_alignment,
        "executive_conclusion": conclusion,
        "next_allowed_step": next_step,
        "hard_blocks": HARD_BLOCKS,
        "outputs": outputs,
    }
    write_json(Path(outputs["external_replication_bundle_manifest_json"]), external_bundle)
    write_json(Path(outputs["broker_spot_alignment_metrics_json"]), broker_alignment)
    write_csv(Path(outputs["broker_spot_alignment_gates_csv"]), gates)
    write_json(Path(outputs["summary_json"]), summary)
    Path(outputs["report_md"]).write_text(build_report(summary), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
