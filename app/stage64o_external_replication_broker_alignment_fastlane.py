#!/usr/bin/env python3
"""Stage64O external replication bundle + broker/spot alignment fastlane.

No order, no broker connection, no validation scan. This stage consumes existing local
artifacts and, if a local broker history exists, performs an offline alignment audit.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STAGE = "Stage64O_EXTERNAL_REPLICATION_BROKER_ALIGNMENT_FASTLANE_NO_ORDER"
EXPECTED_N4_DECISION = "FASTLANE_REPLICATION_PASSED_ALIGNMENT_CONTRACT_DECLARED_STAGE64O_ALLOWED_NO_ORDER"
NO_GO = "NO_GO"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(root: Path, rel: str) -> Dict[str, Any]:
    p = root / rel
    return {
        "path": rel,
        "found": p.exists() and p.is_file(),
        "size_bytes": p.stat().st_size if p.exists() and p.is_file() else 0,
        "sha256": sha256_file(p),
    }


def parse_time(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        d = value
    elif isinstance(value, dt.date):
        d = dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)
    else:
        s = str(value).strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        # accept date-only and common broker formats
        for fmt in (None, "%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d", "%Y-%m-%d"):
            try:
                if fmt is None:
                    d = dt.datetime.fromisoformat(s)
                else:
                    d = dt.datetime.strptime(s, fmt)
                break
            except Exception:
                d = None  # type: ignore[assignment]
        if d is None:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.UTC)
    else:
        d = d.astimezone(dt.UTC)
    return d


def parse_date_key(value: Any) -> Optional[str]:
    d = parse_time(value)
    if d is None:
        return None
    return d.date().isoformat()


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def read_csv_dicts(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def load_daily_close_csv(path: Path, date_candidates: Sequence[str], close_candidates: Sequence[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, fields = read_csv_dicts(path)
    field_map = {c.lower(): c for c in fields}
    date_col = next((field_map[c.lower()] for c in date_candidates if c.lower() in field_map), None)
    close_col = next((field_map[c.lower()] for c in close_candidates if c.lower() in field_map), None)
    out: List[Dict[str, Any]] = []
    parse_errors = 0
    for r in rows:
        if date_col is None or close_col is None:
            break
        dk = parse_date_key(r.get(date_col))
        close = to_float(r.get(close_col))
        if dk is None or close is None:
            parse_errors += 1
            continue
        out.append({"date": dk, "close": close})
    out.sort(key=lambda x: x["date"])
    # deduplicate by keeping last close per date
    dedup: Dict[str, Dict[str, Any]] = {}
    for r in out:
        dedup[r["date"]] = r
    out = [dedup[k] for k in sorted(dedup)]
    return out, {"path": str(path), "fields": fields, "date_col": date_col, "close_col": close_col, "raw_rows": len(rows), "parsed_rows": len(out), "parse_errors": parse_errors}


def add_returns(rows: List[Dict[str, Any]], prefix: str) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    prev_close: Optional[float] = None
    for r in rows:
        c = float(r["close"])
        ret = None
        if prev_close is not None and prev_close > 0:
            ret = (c / prev_close - 1.0) * 10000.0
        out[r["date"]] = {f"{prefix}_close": c}
        if ret is not None and math.isfinite(ret):
            out[r["date"]][f"{prefix}_ret_bps"] = ret
        prev_close = c
    return out


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def percentile(values: Sequence[float], q: float) -> Optional[float]:
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
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def derive_broker_d1_from_sqlite(root: Path, sqlite_rel: str, table: str, preferred_timeframes: Sequence[str], symbol: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    db_path = root / sqlite_rel
    info: Dict[str, Any] = {"source": "sqlite_derived", "sqlite_path": sqlite_rel, "found": db_path.exists(), "table": table, "selected_timeframe": None}
    if not db_path.exists():
        info["issue"] = "sqlite_missing"
        return [], info
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        info["columns"] = cols
        required = {"utc_time", "open", "high", "low", "close"}
        if not required.issubset(set(cols)):
            info["issue"] = "required_columns_missing"
            con.close()
            return [], info
        has_tf = "timeframe" in cols
        has_symbol = "symbol" in cols
        best_tf = None
        best_count = 0
        for tf in preferred_timeframes:
            wheres = []
            params: List[Any] = []
            if has_tf:
                wheres.append("timeframe = ?")
                params.append(tf)
            if has_symbol and symbol:
                wheres.append("upper(symbol) = upper(?)")
                params.append(symbol)
            where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
            q = f"SELECT COUNT(*) AS n FROM {table}{where_sql}"
            n = int(con.execute(q, params).fetchone()["n"])
            info[f"count_{tf}"] = n
            if n > best_count:
                best_count = n
                best_tf = tf
        if best_tf is None or best_count <= 0:
            info["issue"] = "no_rows_for_preferred_timeframes"
            con.close()
            return [], info
        info["selected_timeframe"] = best_tf
        wheres = []
        params = []
        if has_tf:
            wheres.append("timeframe = ?")
            params.append(best_tf)
        if has_symbol and symbol:
            wheres.append("upper(symbol) = upper(?)")
            params.append(symbol)
        where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
        select_cols = "utc_time, open, high, low, close" + (", volume" if "volume" in cols else "")
        q = f"SELECT {select_cols} FROM {table}{where_sql} ORDER BY utc_time ASC"
        daily: Dict[str, Dict[str, Any]] = {}
        parse_errors = 0
        for r in con.execute(q, params):
            d = parse_time(r["utc_time"])
            o = to_float(r["open"]); h = to_float(r["high"]); l = to_float(r["low"]); c = to_float(r["close"])
            if d is None or o is None or h is None or l is None or c is None:
                parse_errors += 1
                continue
            dk = d.date().isoformat()
            vol = to_float(r["volume"]) if "volume" in r.keys() else 0.0
            if dk not in daily:
                daily[dk] = {"date": dk, "open": o, "high": h, "low": l, "close": c, "volume": vol or 0.0, "first_time": d.isoformat(), "last_time": d.isoformat(), "bars": 1}
            else:
                row = daily[dk]
                row["high"] = max(float(row["high"]), h)
                row["low"] = min(float(row["low"]), l)
                row["close"] = c
                row["volume"] = float(row.get("volume") or 0.0) + float(vol or 0.0)
                row["last_time"] = d.isoformat()
                row["bars"] = int(row.get("bars") or 0) + 1
        con.close()
        rows = [daily[k] for k in sorted(daily)]
        info.update({"raw_rows": best_count, "parsed_d1_rows": len(rows), "parse_errors": parse_errors, "first_date": rows[0]["date"] if rows else None, "last_date": rows[-1]["date"] if rows else None})
        return rows, info
    except Exception as e:
        info["issue"] = f"sqlite_error:{type(e).__name__}:{e}"
        return [], info


def write_broker_derived_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["date_utc", "open", "high", "low", "close", "volume", "bars"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({
                "date_utc": r["date"] + "T00:00:00Z",
                "open": r.get("open", ""),
                "high": r.get("high", ""),
                "low": r.get("low", ""),
                "close": r.get("close", ""),
                "volume": r.get("volume", ""),
                "bars": r.get("bars", ""),
            })


def alignment_metrics(gold_rows: List[Dict[str, Any]], broker_rows: List[Dict[str, Any]], gates: Dict[str, Any]) -> Dict[str, Any]:
    g = add_returns(gold_rows, "gold_ref")
    b = add_returns(broker_rows, "broker")
    dates = sorted(set(g) & set(b))
    pairs: List[Dict[str, float]] = []
    ratios: List[float] = []
    for d in dates:
        gr = g[d]
        br = b[d]
        if gr.get("gold_ref_close") and br.get("broker_close"):
            ratios.append(float(br["broker_close"]) / float(gr["gold_ref_close"]))
        if "gold_ref_ret_bps" in gr and "broker_ret_bps" in br:
            pairs.append({
                "gold_ref_ret_bps": float(gr["gold_ref_ret_bps"]),
                "broker_ret_bps": float(br["broker_ret_bps"]),
                "abs_diff_bps": abs(float(br["broker_ret_bps"]) - float(gr["gold_ref_ret_bps"])),
                "same_sign": 1.0 if (float(br["broker_ret_bps"]) == 0 and float(gr["gold_ref_ret_bps"]) == 0) or (float(br["broker_ret_bps"]) * float(gr["gold_ref_ret_bps"]) > 0) else 0.0,
            })
    xs = [p["gold_ref_ret_bps"] for p in pairs]
    ys = [p["broker_ret_bps"] for p in pairs]
    absdiff = [p["abs_diff_bps"] for p in pairs]
    overlap_days = len(pairs)
    corr = pearson(xs, ys)
    sign_agreement = statistics.fmean([p["same_sign"] for p in pairs]) if pairs else None
    med_abs = statistics.median(absdiff) if absdiff else None
    p90_abs = percentile(absdiff, 0.90)
    ratio_median = statistics.median(ratios) if ratios else None
    ratio_iqr = None
    if ratios:
        q75 = percentile(ratios, 0.75)
        q25 = percentile(ratios, 0.25)
        if q75 is not None and q25 is not None:
            ratio_iqr = q75 - q25
    gate_rows = [
        ("overlap_days", overlap_days, ">=", int(gates.get("min_overlap_days", 500)), overlap_days >= int(gates.get("min_overlap_days", 500))),
        ("return_correlation", corr, ">=", float(gates.get("min_return_correlation", 0.95)), (corr is not None and corr >= float(gates.get("min_return_correlation", 0.95)))),
        ("sign_agreement", sign_agreement, ">=", float(gates.get("min_sign_agreement", 0.70)), (sign_agreement is not None and sign_agreement >= float(gates.get("min_sign_agreement", 0.70)))),
        ("median_abs_return_diff_bps", med_abs, "<=", float(gates.get("max_median_abs_return_diff_bps", 20.0)), (med_abs is not None and med_abs <= float(gates.get("max_median_abs_return_diff_bps", 20.0)))),
        ("p90_abs_return_diff_bps", p90_abs, "<=", float(gates.get("max_p90_abs_return_diff_bps", 100.0)), (p90_abs is not None and p90_abs <= float(gates.get("max_p90_abs_return_diff_bps", 100.0)))),
    ]
    return {
        "overlap_start": pairs and dates[1] if len(dates) > 1 else (dates[0] if dates else None),
        "overlap_end": dates[-1] if dates else None,
        "overlap_return_days": overlap_days,
        "gold_ref_rows": len(gold_rows),
        "broker_d1_rows": len(broker_rows),
        "return_correlation": None if corr is None else round(corr, 8),
        "sign_agreement": None if sign_agreement is None else round(sign_agreement, 6),
        "median_abs_return_diff_bps": None if med_abs is None else round(med_abs, 6),
        "p90_abs_return_diff_bps": None if p90_abs is None else round(p90_abs, 6),
        "close_ratio_median_broker_over_reference": None if ratio_median is None else round(ratio_median, 8),
        "close_ratio_iqr": None if ratio_iqr is None else round(ratio_iqr, 8),
        "gate_rows": [
            {"metric": m, "value": v, "operator": op, "threshold": th, "pass": bool(p)} for m, v, op, th, p in gate_rows
        ],
        "alignment_pass": bool(gate_rows and all(bool(p[4]) for p in gate_rows)),
    }


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fields: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        keys: List[str] = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        fields = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def render_report(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Stage64O - External Replication Bundle and Broker/Spot Alignment Fastlane (No Order)")
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
    lines.append(summary["executive_conclusion"])
    lines.append("")
    lines.append("## N4 input")
    lines.append("")
    for k, v in summary["n4_input_checks"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## External replication bundle")
    lines.append("")
    lines.append(f"- manifest: `{summary['outputs']['external_replication_bundle_manifest_json']}`")
    lines.append(f"- input_files_hashed: `{len(summary['external_replication_bundle']['input_file_manifest'])}`")
    lines.append("")
    lines.append("## Broker/spot alignment")
    lines.append("")
    bam = summary.get("broker_spot_alignment", {})
    lines.append(f"- data_available: `{bam.get('data_available')}`")
    lines.append(f"- alignment_pass: `{bam.get('alignment_pass')}`")
    lines.append(f"- broker_source_mode: `{bam.get('broker_source_mode')}`")
    metrics = bam.get("metrics") or {}
    if metrics:
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|---|---:|")
        for k in ["overlap_return_days", "return_correlation", "sign_agreement", "median_abs_return_diff_bps", "p90_abs_return_diff_bps", "close_ratio_median_broker_over_reference", "close_ratio_iqr"]:
            lines.append(f"| `{k}` | `{metrics.get(k)}` |")
        lines.append("")
        lines.append("### Alignment gates")
        lines.append("")
        lines.append("| metric | value | threshold | pass |")
        lines.append("|---|---:|---:|---:|")
        for row in metrics.get("gate_rows", []):
            lines.append(f"| `{row['metric']}` | `{row.get('value')}` | `{row.get('operator')} {row.get('threshold')}` | `{row.get('pass')}` |")
    else:
        lines.append("")
        lines.append("No broker/spot alignment metrics were produced because usable broker D1 data was unavailable.")
    lines.append("")
    lines.append("## Hard blocks")
    lines.append("")
    for b in summary["hard_blocks"]:
        lines.append(f"- `{b}`")
    lines.append("")
    lines.append("## Next allowed step")
    lines.append("")
    lines.append(f"`{summary['next_allowed_step']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = read_json(config_path)
    paths = cfg.get("paths", {})
    stage64n4_summary_rel = paths.get("stage64n4_summary", "reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_summary.json")
    stage64n4_report_rel = paths.get("stage64n4_report", "reports/stage64n4_fastlane_replication_alignment_audit/stage64n4_fastlane_replication_alignment_audit_report.md")
    n4_path = root / stage64n4_summary_rel
    n4 = read_json(n4_path)

    n4_decision = n4.get("decision")
    n4_ok = n4_decision == EXPECTED_N4_DECISION and n4.get("replication_pass") is True
    n4_flags_ok = all(n4.get(k) == NO_GO for k in ["promotion", "EA", "paper_order", "paper_live", "live"])

    input_rels = [
        stage64n4_summary_rel,
        stage64n4_report_rel,
        paths.get("stage64k_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv"),
        paths.get("stage64l_summary", "reports/stage64l_full_scope_walk_forward_validation_design/stage64l_full_scope_walk_forward_validation_design_summary.json"),
        paths.get("stage64m_summary", "reports/stage64m_full_scope_walk_forward_validation_run/stage64m_full_scope_walk_forward_validation_run_summary.json"),
        paths.get("stage64n1b_summary", "reports/stage64n1b_a2_nonparametric_reconciliation/stage64n1b_a2_nonparametric_reconciliation_summary.json"),
        paths.get("stage64n3_summary", "reports/stage64n3_corrected_survivor_replication_alignment_decision/stage64n3_corrected_survivor_replication_alignment_decision_summary.json"),
        str(config_path.relative_to(root)) if str(config_path).startswith(str(root)) else str(config_path),
    ]
    input_manifest = [file_meta(root, rel) for rel in input_rels]

    target = n4.get("target_survivor", {})
    replication = n4.get("independent_replication", {})
    external_bundle = {
        "stage": STAGE,
        "created_utc": utc_now(),
        "purpose": "Local manifest for external/no-order reproduction of the Stage64 survivor. Data files may be local-only and are represented by hashes.",
        "target_survivor": target,
        "n4_independent_replication_headline": replication,
        "input_file_manifest": input_manifest,
        "no_order_policy": "This bundle does not authorize order generation, broker connection, paper-live, live, or commercialization claims.",
    }

    gold_rel = paths.get("gold_reference_file", "data/macro_regime/raw/gold_d1_ohlc_2011_present.csv")
    broker_rel = paths.get("broker_d1_file", "data/macro_regime/raw/broker_or_spot_gold_d1_ohlc_2011_present.csv")
    gold_rows, gold_info = load_daily_close_csv(root / gold_rel, ["date_utc", "utc_time", "date"], ["close", "gold_close"])

    broker_rows: List[Dict[str, Any]] = []
    broker_info: Dict[str, Any]
    broker_source_mode = "none"
    direct_broker_path = root / broker_rel
    if direct_broker_path.exists():
        broker_rows, broker_info = load_daily_close_csv(direct_broker_path, ["date_utc", "utc_time", "date"], ["close", "broker_close"])
        broker_source_mode = "direct_csv"
    else:
        broker_rows, broker_info = derive_broker_d1_from_sqlite(
            root=root,
            sqlite_rel=paths.get("broker_sqlite", "data/broker_normalized/amarkets_multitf.sqlite"),
            table=paths.get("broker_sqlite_table", "amarkets_bars"),
            preferred_timeframes=cfg.get("broker_alignment", {}).get("preferred_timeframes", ["H1", "M30", "M15", "M5"]),
            symbol=cfg.get("broker_alignment", {}).get("symbol", "XAUUSD"),
        )
        broker_source_mode = "sqlite_derived" if broker_rows else "missing"

    derived_csv_rel = "reports/stage64o_external_replication_broker_alignment_fastlane/stage64o_derived_broker_d1.csv"
    if broker_rows and broker_source_mode == "sqlite_derived":
        write_broker_derived_csv(root / derived_csv_rel, broker_rows)

    gates = cfg.get("broker_alignment", {}).get("gates", {})
    align: Dict[str, Any]
    if gold_rows and broker_rows:
        metrics = alignment_metrics(gold_rows, broker_rows, gates)
        align = {
            "data_available": True,
            "alignment_pass": bool(metrics.get("alignment_pass")),
            "broker_source_mode": broker_source_mode,
            "gold_reference_info": gold_info,
            "broker_info": broker_info,
            "metrics": metrics,
            "derived_broker_d1_csv": derived_csv_rel if broker_source_mode == "sqlite_derived" else None,
        }
    else:
        align = {
            "data_available": False,
            "alignment_pass": False,
            "broker_source_mode": broker_source_mode,
            "gold_reference_info": gold_info,
            "broker_info": broker_info,
            "metrics": {},
            "issue": "missing_gold_reference_or_broker_d1_data",
        }

    if not n4_ok or not n4_flags_ok:
        decision = "BLOCKED_N4_INPUT_NOT_VALID_FOR_STAGE64O_NO_ORDER"
        next_step = "FIX_STAGE64N4_INPUTS_NO_ORDER"
        conclusion = "Stage64N4 input is not valid for Stage64O. No continuation, tuning, or order path is authorized."
    elif align.get("data_available") and align.get("alignment_pass"):
        decision = "EXTERNAL_REPLICATION_READY_BROKER_SPOT_ALIGNMENT_SUBSET_PASS_STAGE64P_DECISION_ALLOWED_NO_ORDER"
        next_step = "Stage64P_BROKER_ALIGNMENT_AND_EXTERNAL_REPLICATION_DECISION_NO_ORDER"
        conclusion = "External replication bundle was created and offline broker/spot alignment passed the precommercial subset gates. The survivor remains no-order; Stage64P may decide the next research-only gate."
    elif align.get("data_available"):
        decision = "EXTERNAL_REPLICATION_READY_BROKER_SPOT_ALIGNMENT_SUBSET_FAILS_STAGE64P_DECISION_NO_ORDER"
        next_step = "Stage64P_BROKER_ALIGNMENT_AND_EXTERNAL_REPLICATION_DECISION_NO_ORDER"
        conclusion = "External replication bundle was created, but offline broker/spot alignment did not pass the precommercial subset gates. The survivor remains research-only and no order path is authorized."
    else:
        decision = "EXTERNAL_REPLICATION_BUNDLE_READY_BROKER_ALIGNMENT_DATA_REQUIRED_NO_ORDER"
        next_step = "ACQUIRE_BROKER_SPOT_D1_DATA_OR_RUN_STAGE64P_DECISION_NO_ORDER"
        conclusion = "External replication bundle was created. Broker/spot alignment data is still unavailable, so broker XAUUSD claims and any order path remain blocked."

    summary = {
        "stage": STAGE,
        "status": "EXTERNAL_REPLICATION_BROKER_ALIGNMENT_FASTLANE_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": NO_GO,
        "EA": NO_GO,
        "paper_order": NO_GO,
        "paper_live": NO_GO,
        "live": NO_GO,
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": False,
        "generated_utc": utc_now(),
        "root": str(root),
        "inputs": {"config": str(config_path), "stage64n4_summary": str(n4_path)},
        "n4_input_checks": {
            "stage64n4_decision": n4_decision,
            "expected_decision": EXPECTED_N4_DECISION,
            "n4_decision_ok": n4_decision == EXPECTED_N4_DECISION,
            "n4_replication_pass": n4.get("replication_pass"),
            "n4_no_order_flags_ok": n4_flags_ok,
            "input_ok": n4_ok and n4_flags_ok,
        },
        "target_survivor": target,
        "external_replication_bundle": external_bundle,
        "broker_spot_alignment": align,
        "executive_conclusion": conclusion,
        "next_allowed_step": next_step,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE64O",
            "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
            "NO_POST_HOC_EVENT_EXCLUSION",
            "NO_REDUCED_SCOPE_RETEST",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_COMMERCIALIZATION_WITHOUT_BROKER_SPOT_ALIGNMENT",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64o_external_replication_broker_alignment_fastlane_summary.json"),
            "report_md": str(out_dir / "stage64o_external_replication_broker_alignment_fastlane_report.md"),
            "external_replication_bundle_manifest_json": str(out_dir / "stage64o_external_replication_bundle_manifest.json"),
            "broker_spot_alignment_metrics_json": str(out_dir / "stage64o_broker_spot_alignment_metrics.json"),
            "broker_spot_alignment_gates_csv": str(out_dir / "stage64o_broker_spot_alignment_gates.csv"),
        },
    }

    write_json(out_dir / "stage64o_external_replication_bundle_manifest.json", external_bundle)
    write_json(out_dir / "stage64o_broker_spot_alignment_metrics.json", align)
    if align.get("metrics", {}).get("gate_rows"):
        write_csv(out_dir / "stage64o_broker_spot_alignment_gates.csv", align["metrics"]["gate_rows"], fields=["metric", "value", "operator", "threshold", "pass"])
    else:
        write_csv(out_dir / "stage64o_broker_spot_alignment_gates.csv", [], fields=["metric", "value", "operator", "threshold", "pass"])

    write_json(out_dir / "stage64o_external_replication_broker_alignment_fastlane_summary.json", summary)
    (out_dir / "stage64o_external_replication_broker_alignment_fastlane_report.md").write_text(render_report(summary), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
