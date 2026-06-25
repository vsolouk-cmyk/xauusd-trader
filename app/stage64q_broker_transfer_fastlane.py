#!/usr/bin/env python3
"""
Stage64Q - Broker Transfer Fastlane (No Order)

Fastlane response to Stage64P alignment failure:
- no order, no broker connection, no new hypothesis scan
- derives broker D1 from local SQLite historical bars
- reruns the locked H64L_H1 / h120 survivor as a broker-specific transfer diagnostic
- keeps all promotion/paper/live/live-governance hard-blocked
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
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Optional, Tuple


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def parse_dt(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%Y-%m-%d"):
        try:
            if fmt is None:
                x = dt.datetime.fromisoformat(s)
            else:
                x = dt.datetime.strptime(s, fmt)
            if x.tzinfo is not None:
                x = x.astimezone(dt.UTC).replace(tzinfo=None)
            return x
        except Exception:
            pass
    return None


def parse_date(value: Any) -> Optional[dt.date]:
    x = parse_dt(value)
    return x.date() if x else None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        s = str(value).strip().replace(",", "")
        if s == "" or s.lower() in {"nan", "none", "null"}:
            return None
        return float(s)
    except Exception:
        return None


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_stage64k_dataset(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    info = {"found": path.exists(), "rows": 0, "parse_errors": 0, "columns": []}
    if not path.exists():
        return rows, info
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        info["columns"] = list(reader.fieldnames or [])
        for raw in reader:
            d = parse_date(raw.get("feature_date_utc") or raw.get("date_utc") or raw.get("date"))
            if not d:
                info["parse_errors"] += 1
                continue
            raw["_date"] = d
            rows.append(raw)
    rows.sort(key=lambda r: r["_date"])
    info["rows"] = len(rows)
    return rows, info


def sqlite_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [str(r[1]) for r in cur.fetchall()]


def choose_col(cols: Iterable[str], names: List[str]) -> Optional[str]:
    lower = {c.lower(): c for c in cols}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def derive_broker_d1_from_sqlite(root: Path, cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    broker_cfg = cfg.get("broker_sqlite", {})
    sqlite_path = root / broker_cfg.get("path", "data/broker_normalized/amarkets_multitf.sqlite")
    table = broker_cfg.get("table", "amarkets_bars")
    preferred_tfs = broker_cfg.get("preferred_timeframes", ["M5", "M15", "H1", "M30", "M1"])
    offset_h = int(broker_cfg.get("session_close_offset_hours", 0))
    symbol_like = broker_cfg.get("symbol_like", "XAU")

    info: Dict[str, Any] = {
        "sqlite_path": str(sqlite_path),
        "found": sqlite_path.exists(),
        "table": table,
        "selected_timeframe": None,
        "session_close_offset_hours": offset_h,
        "raw_rows": 0,
        "parsed_rows": 0,
        "daily_rows": 0,
        "parse_errors": 0,
        "issue": None,
    }
    if not sqlite_path.exists():
        info["issue"] = "sqlite_missing"
        return [], info

    conn = sqlite3.connect(str(sqlite_path))
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if table not in tables:
            info["issue"] = "table_missing"
            info["available_tables"] = tables
            return [], info
        cols = sqlite_columns(conn, table)
        info["columns"] = cols
        time_col = choose_col(cols, ["time_utc", "utc_time", "date_utc", "datetime", "time"])
        close_col = choose_col(cols, ["close", "Close"])
        open_col = choose_col(cols, ["open", "Open"])
        high_col = choose_col(cols, ["high", "High"])
        low_col = choose_col(cols, ["low", "Low"])
        tf_col = choose_col(cols, ["timeframe", "tf"])
        sym_col = choose_col(cols, ["symbol", "instrument_symbol"])
        info.update({"time_col": time_col, "close_col": close_col, "open_col": open_col, "high_col": high_col, "low_col": low_col, "timeframe_col": tf_col, "symbol_col": sym_col})
        required = [time_col, close_col]
        if not all(required):
            info["issue"] = "required_columns_missing"
            return [], info
        if tf_col:
            tfs = conn.execute(f"SELECT {tf_col}, COUNT(*) FROM {table} GROUP BY {tf_col}").fetchall()
            info["available_timeframes"] = [{"timeframe": str(a), "row_count": int(b)} for a, b in tfs]
        else:
            info["available_timeframes"] = []

        selected_tf = None
        if tf_col:
            available = {str(x["timeframe"]) for x in info["available_timeframes"]}
            for tf in preferred_tfs:
                if tf in available:
                    selected_tf = tf
                    break
        info["selected_timeframe"] = selected_tf

        select_cols = [time_col, close_col]
        for c in (open_col, high_col, low_col, tf_col, sym_col):
            if c and c not in select_cols:
                select_cols.append(c)
        sql = f"SELECT {', '.join(select_cols)} FROM {table}"
        conds: List[str] = []
        params: List[Any] = []
        if selected_tf and tf_col:
            conds.append(f"{tf_col} = ?")
            params.append(selected_tf)
        if sym_col and symbol_like:
            conds.append(f"UPPER({sym_col}) LIKE ?")
            params.append(f"%{str(symbol_like).upper()}%")
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += f" ORDER BY {time_col} ASC"
        cur = conn.execute(sql, params)
        raw_rows = cur.fetchall()
        info["raw_rows"] = len(raw_rows)
        idx = {c: i for i, c in enumerate(select_cols)}

        by_day: Dict[dt.date, List[Tuple[dt.datetime, Optional[float], Optional[float], Optional[float], float]]] = defaultdict(list)
        for rec in raw_rows:
            t = parse_dt(rec[idx[time_col]])
            c = to_float(rec[idx[close_col]])
            if not t or c is None:
                info["parse_errors"] += 1
                continue
            o = to_float(rec[idx[open_col]]) if open_col in idx else c
            h = to_float(rec[idx[high_col]]) if high_col in idx else c
            l = to_float(rec[idx[low_col]]) if low_col in idx else c
            session_date = (t - dt.timedelta(hours=offset_h)).date()
            by_day[session_date].append((t, o, h, l, c))
            info["parsed_rows"] += 1

        d1: List[Dict[str, Any]] = []
        for day, bars in by_day.items():
            bars.sort(key=lambda x: x[0])
            opens = [x[1] for x in bars if x[1] is not None]
            highs = [x[2] for x in bars if x[2] is not None]
            lows = [x[3] for x in bars if x[3] is not None]
            closes = [x[4] for x in bars if x[4] is not None]
            if not closes:
                continue
            d1.append({
                "date": day,
                "date_utc": day.isoformat() + "T00:00:00Z",
                "open": opens[0] if opens else closes[0],
                "high": max(highs) if highs else max(closes),
                "low": min(lows) if lows else min(closes),
                "close": closes[-1],
                "source": "AMARKETS_SQLITE_DERIVED_D1_NO_BROKER_CONNECTION",
                "source_timeframe": selected_tf or "ALL",
                "session_close_offset_hours": offset_h,
            })
        d1.sort(key=lambda r: r["date"])
        info["daily_rows"] = len(d1)
        if not d1:
            info["issue"] = "no_daily_rows"
        return d1, info
    finally:
        conn.close()


def add_broker_trend(d1: List[Dict[str, Any]]) -> None:
    closes: List[float] = []
    for r in d1:
        closes.append(float(r["close"]))
        for n in (20, 50, 200):
            if len(closes) >= n:
                r[f"sma{n}"] = sum(closes[-n:]) / n
            else:
                r[f"sma{n}"] = None
        r["broker_sma20_over_50"] = None if r.get("sma20") is None or r.get("sma50") is None else r["sma20"] - r["sma50"]
        r["broker_sma50_over_200"] = None if r.get("sma50") is None or r.get("sma200") is None else r["sma50"] - r["sma200"]


def fnum(row: Dict[str, Any], col: str) -> Optional[float]:
    return to_float(row.get(col))


def is_b1(row: Dict[str, Any]) -> bool:
    return (fnum(row, "broker_sma20_over_50") or -1e99) > 0 and (fnum(row, "broker_sma50_over_200") or -1e99) > 0


def is_h1(row: Dict[str, Any]) -> bool:
    return (
        is_b1(row)
        and (fnum(row, "dxy_ret_20d") or 1e99) < 0
        and (fnum(row, "real_yield_change_20d") or 1e99) < 0
        and (fnum(row, "etf_flow_tonnes_3m") or -1e99) > 0
        and (fnum(row, "central_bank_demand_tonnes_6m") or -1e99) > 0
    )


def split_id_for_date(d: dt.date) -> Optional[str]:
    if dt.date(2011, 1, 1) <= d <= dt.date(2015, 12, 31):
        return "2011_2015"
    if dt.date(2016, 1, 1) <= d <= dt.date(2019, 12, 31):
        return "2016_2019"
    if dt.date(2020, 1, 1) <= d <= dt.date(2022, 12, 31):
        return "2020_2022"
    if dt.date(2023, 1, 1) <= d <= dt.date(2026, 12, 31):
        return "2023_present"
    return None


def one_sided_p_mean_gt(values: List[float], threshold: float) -> float:
    n = len(values)
    if n < 2:
        return 1.0
    mu = mean(values)
    sd = pstdev(values)
    if sd <= 1e-12:
        return 0.0 if mu > threshold else 1.0
    z = (mu - threshold) / (sd / math.sqrt(n))
    # P(Z >= observed z) under standard normal
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def safe_mean(xs: List[float]) -> Optional[float]:
    return mean(xs) if xs else None


def run_transfer_validation(stage_rows: List[Dict[str, Any]], broker_d1: List[Dict[str, Any]], horizon: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    macro_by_date = {r["_date"]: r for r in stage_rows}
    add_broker_trend(broker_d1)
    # map future index by broker trading day order
    by_date = {r["date"]: r for r in broker_d1}
    dates = [r["date"] for r in broker_d1]

    joined: List[Dict[str, Any]] = []
    returns_by_split_candidate: Dict[str, List[float]] = defaultdict(list)
    returns_by_split_benchmark: Dict[str, List[float]] = defaultdict(list)
    candidate_returns: List[float] = []
    benchmark_returns: List[float] = []
    candidate_dates: List[dt.date] = []
    benchmark_dates: List[dt.date] = []

    for i, d in enumerate(dates):
        if i + horizon >= len(dates):
            continue
        macro = macro_by_date.get(d)
        broker = by_date[d]
        future = by_date[dates[i + horizon]]
        if not macro:
            continue
        cur_close = to_float(broker.get("close"))
        fut_close = to_float(future.get("close"))
        if cur_close is None or fut_close is None or cur_close <= 0:
            continue
        row = dict(macro)
        row.update({
            "broker_close": cur_close,
            "broker_future_close": fut_close,
            "broker_sma20_over_50": broker.get("broker_sma20_over_50"),
            "broker_sma50_over_200": broker.get("broker_sma50_over_200"),
        })
        ret_bps = (fut_close / cur_close - 1.0) * 10000.0
        split_id = split_id_for_date(d) or "OTHER"
        b1 = is_b1(row)
        h1 = is_h1(row)
        if b1:
            benchmark_returns.append(ret_bps)
            benchmark_dates.append(d)
            returns_by_split_benchmark[split_id].append(ret_bps)
        if h1:
            candidate_returns.append(ret_bps)
            candidate_dates.append(d)
            returns_by_split_candidate[split_id].append(ret_bps)
        joined.append({
            "date_utc": d.isoformat() + "T00:00:00Z",
            "split_id": split_id,
            "broker_close": cur_close,
            "future_close_h120": fut_close,
            "return_bps_h120": ret_bps,
            "b1_active": b1,
            "h1_active": h1,
        })

    cand_mean = safe_mean(candidate_returns)
    bench_mean = safe_mean(benchmark_returns)
    excess = None if cand_mean is None or bench_mean is None else cand_mean - bench_mean
    p_unc = one_sided_p_mean_gt(candidate_returns, bench_mean) if bench_mean is not None else 1.0
    split_rows: List[Dict[str, Any]] = []
    positive_splits = 0
    available_splits = 0
    for sid in ["2011_2015", "2016_2019", "2020_2022", "2023_present"]:
        cr = returns_by_split_candidate.get(sid, [])
        br = returns_by_split_benchmark.get(sid, [])
        cm = safe_mean(cr)
        bm = safe_mean(br)
        ex = None if cm is None or bm is None else cm - bm
        pos = bool(ex is not None and ex > 0 and len(cr) > 0 and len(br) > 0)
        if len(cr) > 0 and len(br) > 0:
            available_splits += 1
        if pos:
            positive_splits += 1
        split_rows.append({
            "split_id": sid,
            "candidate_active_days": len(cr),
            "benchmark_active_days": len(br),
            "candidate_mean_bps": cm,
            "benchmark_mean_bps": bm,
            "excess_vs_broker_B1_bps": ex,
            "positive_excess": pos,
        })

    # concentration over candidate active days
    split_counts = defaultdict(int)
    year_counts = defaultdict(int)
    for d in candidate_dates:
        split_counts[split_id_for_date(d) or "OTHER"] += 1
        year_counts[str(d.year)] += 1
    max_split_share = max(split_counts.values()) / len(candidate_dates) if candidate_dates else None
    max_year_share = max(year_counts.values()) / len(candidate_dates) if candidate_dates else None

    overall = {
        "horizon_days": horizon,
        "joined_return_days": len(joined),
        "first_joined_date": joined[0]["date_utc"] if joined else None,
        "last_joined_date": joined[-1]["date_utc"] if joined else None,
        "candidate_active_days": len(candidate_returns),
        "candidate_mean_bps": cand_mean,
        "broker_B1_active_days": len(benchmark_returns),
        "broker_B1_mean_bps": bench_mean,
        "mean_excess_vs_broker_B1_bps": excess,
        "one_sided_p_uncorrected_z_approx": p_unc,
        "positive_excess_splits_vs_broker_B1": positive_splits,
        "available_splits_with_candidate_and_benchmark": available_splits,
        "max_split_share_of_candidate_active_days": max_split_share,
        "max_year_share_of_candidate_active_days": max_year_share,
        "candidate_split_counts": dict(split_counts),
        "candidate_year_counts_top10": dict(sorted(year_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]),
    }
    return overall, split_rows, joined


def gate_transfer(overall: Dict[str, Any], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    gates_cfg = cfg.get("broker_transfer_gates", {})
    gates = [
        ("min_joined_return_days", overall.get("joined_return_days"), ">=", gates_cfg.get("min_joined_return_days", 500)),
        ("min_candidate_active_days", overall.get("candidate_active_days"), ">=", gates_cfg.get("min_candidate_active_days", 80)),
        ("mean_excess_vs_broker_B1_bps", overall.get("mean_excess_vs_broker_B1_bps"), ">", gates_cfg.get("min_mean_excess_bps", 0.0)),
        ("one_sided_p_uncorrected_z_approx", overall.get("one_sided_p_uncorrected_z_approx"), "<=", gates_cfg.get("max_one_sided_p", 0.05)),
        ("positive_excess_splits_vs_broker_B1", overall.get("positive_excess_splits_vs_broker_B1"), ">=", gates_cfg.get("min_positive_splits", 1)),
        ("max_split_share_of_candidate_active_days", overall.get("max_split_share_of_candidate_active_days"), "<=", gates_cfg.get("max_split_share", 0.70)),
        ("max_year_share_of_candidate_active_days", overall.get("max_year_share_of_candidate_active_days"), "<=", gates_cfg.get("max_year_share", 0.55)),
    ]
    out = []
    for name, val, op, threshold in gates:
        ok = False
        if val is not None:
            if op == ">=":
                ok = float(val) >= float(threshold)
            elif op == ">":
                ok = float(val) > float(threshold)
            elif op == "<=":
                ok = float(val) <= float(threshold)
        out.append({"gate": name, "value": val, "op": op, "threshold": threshold, "pass": ok})
    return out


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys = []
        for r in rows:
            for k in r.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


def fmt(x: Any) -> str:
    if x is None:
        return "None"
    if isinstance(x, float):
        return f"{x:.6f}"
    return str(x)


def make_report(summary: Dict[str, Any]) -> str:
    o = summary.get("broker_transfer_validation", {}).get("overall", {})
    gates = summary.get("broker_transfer_validation", {}).get("gates", [])
    split_rows = summary.get("broker_transfer_validation", {}).get("split_rows", [])
    lines = []
    lines.append("# Stage64Q - Broker Transfer Fastlane (No Order)\n")
    lines.append(f"Generated UTC: `{summary.get('generated_utc')}`\n")
    lines.append("## Status\n")
    for k in ["status", "decision", "promotion", "paper_order", "paper_live", "live", "validation_allowed_for_order_or_promotion"]:
        lines.append(f"- {k}: `{summary.get(k)}`")
    lines.append("\n## Executive conclusion\n")
    lines.append(summary.get("executive_conclusion", ""))
    lines.append("\n## Broker-derived D1 source\n")
    bi = summary.get("broker_info", {})
    for k in ["found", "selected_timeframe", "session_close_offset_hours", "raw_rows", "parsed_rows", "daily_rows", "issue"]:
        lines.append(f"- {k}: `{bi.get(k)}`")
    lines.append("\n## Broker transfer validation headline\n")
    lines.append("| metric | value |")
    lines.append("|---|---:|")
    for k in ["joined_return_days", "candidate_active_days", "candidate_mean_bps", "broker_B1_active_days", "broker_B1_mean_bps", "mean_excess_vs_broker_B1_bps", "one_sided_p_uncorrected_z_approx", "positive_excess_splits_vs_broker_B1", "max_split_share_of_candidate_active_days", "max_year_share_of_candidate_active_days"]:
        lines.append(f"| `{k}` | `{fmt(o.get(k))}` |")
    lines.append("\n## Transfer gates\n")
    lines.append("| gate | value | op | threshold | pass |")
    lines.append("|---|---:|---|---:|---:|")
    for g in gates:
        lines.append(f"| `{g['gate']}` | `{fmt(g.get('value'))}` | `{g.get('op')}` | `{fmt(g.get('threshold'))}` | `{g.get('pass')}` |")
    lines.append("\n## Split diagnostics\n")
    lines.append("| split | cand_days | b1_days | cand_mean | b1_mean | excess | positive |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in split_rows:
        lines.append(f"| `{r.get('split_id')}` | `{r.get('candidate_active_days')}` | `{r.get('benchmark_active_days')}` | `{fmt(r.get('candidate_mean_bps'))}` | `{fmt(r.get('benchmark_mean_bps'))}` | `{fmt(r.get('excess_vs_broker_B1_bps'))}` | `{r.get('positive_excess')}` |")
    lines.append("\n## Hard blocks\n")
    for x in summary.get("hard_blocks", []):
        lines.append(f"- `{x}`")
    lines.append("\n## Next allowed step\n")
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
    cfg_path = Path(args.config) if Path(args.config).is_absolute() else root / args.config
    out_dir = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = read_json(cfg_path)

    stage64p_summary_path = root / cfg.get("stage64p_summary", "reports/stage64p_alignment_diagnostic_fastlane/stage64p_alignment_diagnostic_fastlane_summary.json")
    dataset_path = root / cfg.get("stage64k_dataset", "data/macro_regime/normalized/stage64k_full_scope_lag_safe_feature_dataset.csv")
    stage64p = read_json(stage64p_summary_path) if stage64p_summary_path.exists() else {}
    p_decision = stage64p.get("decision")
    expected_p = cfg.get("required_stage64p_decision", "BROKER_SPOT_ALIGNMENT_DIAGNOSTIC_FAIL_REFERENCE_OR_BROKER_DATA_REDESIGN_REQUIRED_NO_ORDER")

    stage_rows, dataset_info = load_stage64k_dataset(dataset_path)
    broker_d1, broker_info = derive_broker_d1_from_sqlite(root, cfg)

    horizon = int(cfg.get("target_survivor", {}).get("horizon_days", 120))
    if stage_rows and broker_d1:
        overall, split_rows, joined_rows = run_transfer_validation(stage_rows, broker_d1, horizon)
        gates = gate_transfer(overall, cfg)
    else:
        overall, split_rows, joined_rows, gates = {}, [], [], []

    transfer_pass = bool(gates) and all(g.get("pass") for g in gates)
    data_available = bool(stage_rows and broker_d1)
    if transfer_pass:
        decision = "BROKER_TRANSFER_VALIDATION_PASS_RESEARCH_ONLY_STAGE64R_ALLOWED_NO_ORDER"
        next_allowed = "Stage64R_FASTLANE_EXTERNAL_REPLICATION_AND_GOVERNANCE_PREP_NO_ORDER"
        conclusion = "Broker-derived D1 transfer validation passed the declared research-only transfer gates. This is not an order authorization; it only allows the next no-order governance/replication step."
    elif data_available:
        decision = "BROKER_TRANSFER_VALIDATION_FAIL_OR_INCONCLUSIVE_EXTERNAL_SPOT_D1_REQUIRED_NO_ORDER"
        next_allowed = "ACQUIRE_EXTERNAL_BROKER_OR_SPOT_D1_REFERENCE_OR_REDESIGN_MACRO_THESIS_NO_ORDER"
        conclusion = "Broker-derived D1 transfer validation did not pass the declared gates. The survivor remains research-only; broker XAUUSD claims require external broker/spot D1 acquisition or thesis-level redesign."
    else:
        decision = "BROKER_TRANSFER_DATA_UNAVAILABLE_EXTERNAL_BROKER_D1_REQUIRED_NO_ORDER"
        next_allowed = "ACQUIRE_EXTERNAL_BROKER_OR_SPOT_D1_REFERENCE_NO_ORDER"
        conclusion = "Broker transfer validation could not run because required local dataset/broker-derived D1 data was unavailable."

    # outputs
    broker_d1_csv = out_dir / "stage64q_broker_derived_d1.csv"
    if broker_d1:
        write_csv(broker_d1_csv, broker_d1, ["date_utc", "open", "high", "low", "close", "source", "source_timeframe", "session_close_offset_hours"])
    transfer_rows_csv = out_dir / "stage64q_broker_transfer_joined_returns.csv"
    if joined_rows:
        write_csv(transfer_rows_csv, joined_rows)
    gates_csv = out_dir / "stage64q_broker_transfer_gates.csv"
    if gates:
        write_csv(gates_csv, gates, ["gate", "value", "op", "threshold", "pass"])
    splits_csv = out_dir / "stage64q_broker_transfer_splits.csv"
    if split_rows:
        write_csv(splits_csv, split_rows)

    summary = {
        "stage": "Stage64Q_BROKER_TRANSFER_FASTLANE_NO_ORDER",
        "status": "BROKER_TRANSFER_FASTLANE_COMPLETE_NO_PROMOTION",
        "decision": decision,
        "promotion": "NO_GO",
        "EA": "NO_GO",
        "paper_order": "NO_GO",
        "paper_live": "NO_GO",
        "live": "NO_GO",
        "validation_allowed_for_order_or_promotion": False,
        "validation_run_performed": True,
        "order_path": "NONE",
        "broker_connection": "NONE",
        "generated_utc": utc_now_iso(),
        "root": str(root),
        "inputs": {
            "config": str(cfg_path),
            "stage64p_summary": str(stage64p_summary_path),
            "stage64k_dataset": str(dataset_path),
        },
        "stage64p_input_decision": p_decision,
        "stage64p_expected_decision": expected_p,
        "stage64p_decision_ok": p_decision == expected_p,
        "target_survivor": cfg.get("target_survivor", {"hypothesis_id": "H64L_H1_FULL_MACRO_TAILWIND_LONG", "horizon_days": 120, "primary_benchmark_id": "BROKER_B1_TREND_ONLY_REFERENCE"}),
        "dataset_info": dataset_info,
        "broker_info": broker_info,
        "broker_transfer_validation": {
            "data_available": data_available,
            "transfer_pass": transfer_pass,
            "overall": overall,
            "split_rows": split_rows,
            "gates": gates,
        },
        "executive_conclusion": conclusion,
        "next_allowed_step": next_allowed,
        "hard_blocks": [
            "NO_PAPER_ORDER",
            "NO_EA_PROMOTION",
            "NO_PAPER_LIVE",
            "NO_LIVE",
            "NO_BROKER_CONNECTION",
            "NO_ORDER_AUTHORIZATION_FROM_STAGE64Q",
            "NO_HISTORICAL_EVENT_FILTER_FROM_FORWARD_ONLY_GOVERNANCE",
            "NO_POST_HOC_EVENT_EXCLUSION",
            "NO_REDUCED_SCOPE_RETEST",
            "NO_RESCUE_FILTERING",
            "NO_NEW_INTRADAY_SCAN",
            "NO_COMMERCIALIZATION_WITHOUT_BROKER_TRANSFER_OR_EXTERNAL_ALIGNMENT",
        ],
        "outputs": {
            "summary_json": str(out_dir / "stage64q_broker_transfer_fastlane_summary.json"),
            "report_md": str(out_dir / "stage64q_broker_transfer_fastlane_report.md"),
            "broker_d1_csv": str(broker_d1_csv),
            "joined_returns_csv": str(transfer_rows_csv),
            "gates_csv": str(gates_csv),
            "splits_csv": str(splits_csv),
        },
    }
    # add hashes of key local outputs to help reproducibility
    summary["output_hashes"] = {k: sha256_file(Path(v)) for k, v in summary["outputs"].items() if k.endswith("csv")}

    summary_path = out_dir / "stage64q_broker_transfer_fastlane_summary.json"
    report_path = out_dir / "stage64q_broker_transfer_fastlane_report.md"
    write_json(summary_path, summary)
    report_path.write_text(make_report(summary), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
