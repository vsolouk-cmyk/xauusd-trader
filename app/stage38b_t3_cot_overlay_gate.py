#!/usr/bin/env python3
"""
Stage38B / T3 COT Overlay Gate

Purpose
-------
Read-only restricted gate after the COT interaction diagnostic.

This is NOT a trading strategy, NOT an optimized backtest, NOT ML, NOT EA,
NOT paper-live, NOT live-order execution, and NOT Stage39.

It tests only whether a small set of pre-declared COT x ATR overlays has enough
risk/regime value to justify a later baseline-overlay retest.

Primary panel
-------------
Only event_level rows from cot_gold_t3_interaction_forward_returns are used.
This avoids treating repeated H1 bars within one weekly COT report as independent.

Pre-declared overlays
---------------------
1. AVOID_LONG_HOSTILE:
   cot_state == MM_SHORT_CROWDED and atr_bucket == ATR_EXPANSION

2. SQUEEZE_DO_NOT_SHORT:
   cot_state == MM_EXTREME_SHORT and atr_bucket == ATR_EXPANSION

3. LOW_CONVICTION_BLOCK:
   cot_state == MM_NEUTRAL and atr_bucket == ATR_LOW

Default outputs
---------------
    cot_gold_t3_overlay_gate_events
    cot_gold_t3_overlay_gate_summary
    cot_gold_t3_overlay_gate_audit

Reports
-------
    data/reports/stage38b_t3_cot_overlay_gate/stage38b_t3_cot_overlay_gate.json
    data/reports/stage38b_t3_cot_overlay_gate/stage38b_t3_cot_overlay_gate.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UTC = dt.timezone.utc
DEFAULT_HORIZONS = [120, 240]

REQUIRED_RETURN_COLUMNS = [
    "sample_level",
    "bar_ts_utc",
    "horizon_bars",
    "future_bar_ts_utc",
    "cot_available_from_utc",
    "cot_state",
    "atr_bucket",
    "close_t",
    "return_bps",
    "year",
]

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    sample_level TEXT NOT NULL,
    bar_ts_utc TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    future_bar_ts_utc TEXT NOT NULL,
    cot_as_of_date TEXT,
    cot_available_from_utc TEXT NOT NULL,
    cot_state TEXT NOT NULL,
    atr_bucket TEXT NOT NULL,
    t1_locked_structural_state TEXT,
    d1_trend_bucket TEXT,
    h4_trend_bucket TEXT,
    macro_bucket TEXT,
    close_t REAL NOT NULL,
    return_bps REAL NOT NULL,
    stress_p90_cost_bps REAL,
    return_bps_after_stress_cost REAL,
    year INTEGER NOT NULL,
    avoid_long_hostile INTEGER NOT NULL,
    squeeze_do_not_short INTEGER NOT NULL,
    low_conviction_block INTEGER NOT NULL,
    overlay_category TEXT NOT NULL,
    long_overlay_policy TEXT NOT NULL,
    short_overlay_policy TEXT NOT NULL,
    PRIMARY KEY (sample_level, bar_ts_utc, horizon_bars)
)
"""

SUMMARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    created_utc TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    group_type TEXT NOT NULL,
    group_value TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    first_bar_ts_utc TEXT,
    last_bar_ts_utc TEXT,
    mean_return_bps REAL,
    median_return_bps REAL,
    stdev_return_bps REAL,
    t_stat_mean_bps REAL,
    win_rate_long REAL,
    p10_return_bps REAL,
    p25_return_bps REAL,
    p75_return_bps REAL,
    p90_return_bps REAL,
    min_return_bps REAL,
    max_return_bps REAL,
    mean_stress_p90_cost_bps REAL,
    mean_return_bps_after_stress_cost REAL,
    median_return_bps_after_stress_cost REAL,
    diff_vs_all_mean_bps REAL,
    positive_year_count INTEGER,
    negative_year_count INTEGER,
    max_positive_year_share REAL,
    note TEXT,
    PRIMARY KEY (horizon_bars, group_type, group_value)
)
"""

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table_name} (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT NOT NULL,
    returns_table TEXT NOT NULL,
    events_table TEXT NOT NULL,
    summary_table TEXT NOT NULL,
    source_event_rows INTEGER NOT NULL,
    events_written INTEGER NOT NULL,
    summary_rows_written INTEGER NOT NULL,
    horizon_list TEXT NOT NULL,
    min_event_samples INTEGER NOT NULL,
    stress_p90_cost_price REAL NOT NULL,
    warning_count INTEGER NOT NULL,
    note_count INTEGER NOT NULL,
    json_report TEXT NOT NULL,
    md_report TEXT NOT NULL
)
"""


def utc_now_iso() -> str:
    return dt.datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def quote_ident(name: str) -> str:
    if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "select 1 from sqlite_master where type='table' and name=? limit 1",
        (table,),
    ).fetchone() is not None


def table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    if not table_exists(con, table):
        raise RuntimeError(f"Missing table: {table}")
    return [r[1] for r in con.execute(f"pragma table_info({quote_ident(table)})").fetchall()]


def require_columns(con: sqlite3.Connection, table: str, required: Sequence[str]) -> None:
    cols = set(table_columns(con, table))
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"Table {table!r} missing required columns: {missing}. Existing: {sorted(cols)}")


def parse_horizons(raw: str) -> List[int]:
    vals = []
    for part in raw.split(','):
        part = part.strip()
        if part:
            vals.append(int(part))
    if not vals:
        raise ValueError("At least one horizon is required")
    return sorted(set(vals))


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(value)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None and not math.isnan(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return vals[int(pos)]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def stdev_sample(values: Sequence[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    n = len(vals)
    if n < 2:
        return None
    mu = mean(vals)
    return math.sqrt(sum((x - mu) ** 2 for x in vals) / (n - 1))


def year_concentration(rows: Sequence[Dict[str, Any]]) -> Tuple[int, int, Optional[float], Dict[int, float]]:
    totals: Dict[int, float] = {}
    for r in rows:
        y = int(r["year"])
        totals[y] = totals.get(y, 0.0) + float(r["return_bps"])
    pos = {y: v for y, v in totals.items() if v > 0}
    neg = {y: v for y, v in totals.items() if v < 0}
    if not pos:
        return 0, len(neg), None, totals
    total_pos = sum(pos.values())
    share = max(pos.values()) / total_pos if total_pos > 0 else None
    return len(pos), len(neg), share, totals


def summarize(
    rows: Sequence[Dict[str, Any]],
    created_utc: str,
    horizon: int,
    group_type: str,
    group_value: str,
    all_mean: Optional[float],
    min_event_samples: int,
) -> Dict[str, Any]:
    returns = [float(r["return_bps"]) for r in rows]
    after_cost = [float(r["return_bps_after_stress_cost"]) for r in rows if r.get("return_bps_after_stress_cost") is not None]
    costs = [float(r["stress_p90_cost_bps"]) for r in rows if r.get("stress_p90_cost_bps") is not None]
    n = len(returns)
    mu = mean(returns) if returns else None
    med = median(returns) if returns else None
    sd = stdev_sample(returns)
    t_stat = (mu / (sd / math.sqrt(n))) if (mu is not None and sd and n > 1) else None
    pos_years, neg_years, max_pos_share, _ = year_concentration(rows)

    notes: List[str] = []
    if n < min_event_samples:
        notes.append(f"LOW_EVENT_SAMPLE_LT_{min_event_samples}")
    if max_pos_share is not None and max_pos_share >= 0.75:
        notes.append("YEAR_CONCENTRATED")
    if after_cost and mean(after_cost) < 0 <= (mu or 0):
        notes.append("STRESS_COST_FLIPS_MEAN_NEGATIVE")

    return {
        "created_utc": created_utc,
        "horizon_bars": horizon,
        "group_type": group_type,
        "group_value": group_value,
        "sample_count": n,
        "first_bar_ts_utc": min(r["bar_ts_utc"] for r in rows) if rows else None,
        "last_bar_ts_utc": max(r["bar_ts_utc"] for r in rows) if rows else None,
        "mean_return_bps": mu,
        "median_return_bps": med,
        "stdev_return_bps": sd,
        "t_stat_mean_bps": t_stat,
        "win_rate_long": sum(1 for x in returns if x > 0) / n if n else None,
        "p10_return_bps": percentile(returns, 0.10),
        "p25_return_bps": percentile(returns, 0.25),
        "p75_return_bps": percentile(returns, 0.75),
        "p90_return_bps": percentile(returns, 0.90),
        "min_return_bps": min(returns) if returns else None,
        "max_return_bps": max(returns) if returns else None,
        "mean_stress_p90_cost_bps": mean(costs) if costs else None,
        "mean_return_bps_after_stress_cost": mean(after_cost) if after_cost else None,
        "median_return_bps_after_stress_cost": median(after_cost) if after_cost else None,
        "diff_vs_all_mean_bps": (mu - all_mean) if (mu is not None and all_mean is not None) else None,
        "positive_year_count": pos_years,
        "negative_year_count": neg_years,
        "max_positive_year_share": max_pos_share,
        "note": ";".join(notes) if notes else None,
    }


def classify_overlay(row: sqlite3.Row, stress_p90_cost_price: float) -> Dict[str, Any]:
    d = dict(row)
    cot_state = str(d.get("cot_state") or "")
    atr_bucket = str(d.get("atr_bucket") or "")
    close_t = safe_float(d.get("close_t"))
    ret = safe_float(d.get("return_bps"))

    avoid_long = int(cot_state == "MM_SHORT_CROWDED" and atr_bucket == "ATR_EXPANSION")
    squeeze = int(cot_state == "MM_EXTREME_SHORT" and atr_bucket == "ATR_EXPANSION")
    low_conviction = int(cot_state == "MM_NEUTRAL" and atr_bucket == "ATR_LOW")

    if avoid_long:
        overlay_category = "AVOID_LONG_HOSTILE"
    elif squeeze:
        overlay_category = "SQUEEZE_DO_NOT_SHORT"
    elif low_conviction:
        overlay_category = "LOW_CONVICTION_BLOCK"
    else:
        overlay_category = "LONG_PERMITTED"

    long_policy = "LONG_BLOCKED" if (avoid_long or low_conviction) else "LONG_PERMITTED"
    short_policy = "SHORT_BLOCKED" if squeeze else "SHORT_NOT_ASSESSED"

    cost_bps = (stress_p90_cost_price / close_t * 10000.0) if close_t and close_t > 0 else None
    ret_after_cost = (ret - cost_bps) if (ret is not None and cost_bps is not None) else None

    d.update(
        {
            "stress_p90_cost_bps": cost_bps,
            "return_bps_after_stress_cost": ret_after_cost,
            "avoid_long_hostile": avoid_long,
            "squeeze_do_not_short": squeeze,
            "low_conviction_block": low_conviction,
            "overlay_category": overlay_category,
            "long_overlay_policy": long_policy,
            "short_overlay_policy": short_policy,
        }
    )
    return d


def load_event_rows(con: sqlite3.Connection, returns_table: str, horizons: Sequence[int], stress_p90_cost_price: float) -> List[Dict[str, Any]]:
    require_columns(con, returns_table, REQUIRED_RETURN_COLUMNS)
    cols = table_columns(con, returns_table)
    optional = [
        "cot_as_of_date",
        "t1_locked_structural_state",
        "d1_trend_bucket",
        "h4_trend_bucket",
        "macro_bucket",
    ]
    select_cols = list(REQUIRED_RETURN_COLUMNS)
    for c in optional:
        if c in cols and c not in select_cols:
            select_cols.append(c)
    horizon_ph = ",".join("?" for _ in horizons)
    sql = f"""
        select {', '.join(quote_ident(c) for c in select_cols)}
        from {quote_ident(returns_table)}
        where sample_level = 'event_level'
          and horizon_bars in ({horizon_ph})
        order by horizon_bars, bar_ts_utc
    """
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, tuple(horizons)).fetchall()
    return [classify_overlay(r, stress_p90_cost_price) for r in rows]


def recreate_table(con: sqlite3.Connection, table: str, schema: str) -> None:
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")
    con.execute(schema.format(table_name=quote_ident(table)))


def write_events(con: sqlite3.Connection, table: str, rows: Sequence[Dict[str, Any]]) -> int:
    fields = [
        "sample_level",
        "bar_ts_utc",
        "horizon_bars",
        "future_bar_ts_utc",
        "cot_as_of_date",
        "cot_available_from_utc",
        "cot_state",
        "atr_bucket",
        "t1_locked_structural_state",
        "d1_trend_bucket",
        "h4_trend_bucket",
        "macro_bucket",
        "close_t",
        "return_bps",
        "stress_p90_cost_bps",
        "return_bps_after_stress_cost",
        "year",
        "avoid_long_hostile",
        "squeeze_do_not_short",
        "low_conviction_block",
        "overlay_category",
        "long_overlay_policy",
        "short_overlay_policy",
    ]
    placeholders = ",".join("?" for _ in fields)
    sql = f"INSERT OR REPLACE INTO {quote_ident(table)} ({', '.join(quote_ident(f) for f in fields)}) VALUES ({placeholders})"
    data = []
    for r in rows:
        data.append(tuple(r.get(f) for f in fields))
    con.executemany(sql, data)
    return len(data)


def build_summaries(created_utc: str, rows: Sequence[Dict[str, Any]], horizons: Sequence[int], min_event_samples: int) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    group_specs = [
        ("all", lambda r: "ALL"),
        ("cot_state", lambda r: r["cot_state"]),
        ("atr_bucket", lambda r: r["atr_bucket"]),
        ("overlay_category", lambda r: r["overlay_category"]),
        ("long_overlay_policy", lambda r: r["long_overlay_policy"]),
        ("short_overlay_policy", lambda r: r["short_overlay_policy"]),
        ("cot_state_x_atr_bucket", lambda r: f"{r['cot_state']}__{r['atr_bucket']}"),
    ]
    for h in horizons:
        h_rows = [r for r in rows if int(r["horizon_bars"]) == h]
        all_mean = mean([float(r["return_bps"]) for r in h_rows]) if h_rows else None
        for group_type, key_fn in group_specs:
            buckets: Dict[str, List[Dict[str, Any]]] = {}
            for r in h_rows:
                buckets.setdefault(str(key_fn(r)), []).append(r)
            for key, b_rows in sorted(buckets.items()):
                summaries.append(summarize(b_rows, created_utc, h, group_type, key, all_mean, min_event_samples))
    return summaries


def write_summaries(con: sqlite3.Connection, table: str, summaries: Sequence[Dict[str, Any]]) -> int:
    fields = [
        "created_utc",
        "horizon_bars",
        "group_type",
        "group_value",
        "sample_count",
        "first_bar_ts_utc",
        "last_bar_ts_utc",
        "mean_return_bps",
        "median_return_bps",
        "stdev_return_bps",
        "t_stat_mean_bps",
        "win_rate_long",
        "p10_return_bps",
        "p25_return_bps",
        "p75_return_bps",
        "p90_return_bps",
        "min_return_bps",
        "max_return_bps",
        "mean_stress_p90_cost_bps",
        "mean_return_bps_after_stress_cost",
        "median_return_bps_after_stress_cost",
        "diff_vs_all_mean_bps",
        "positive_year_count",
        "negative_year_count",
        "max_positive_year_share",
        "note",
    ]
    placeholders = ",".join("?" for _ in fields)
    sql = f"INSERT OR REPLACE INTO {quote_ident(table)} ({', '.join(quote_ident(f) for f in fields)}) VALUES ({placeholders})"
    con.executemany(sql, [tuple(s.get(f) for f in fields) for s in summaries])
    return len(summaries)


def get_summary(summaries: Sequence[Dict[str, Any]], horizon: int, group_type: str, group_value: str) -> Optional[Dict[str, Any]]:
    for s in summaries:
        if int(s["horizon_bars"]) == horizon and s["group_type"] == group_type and s["group_value"] == group_value:
            return s
    return None


def decide(summaries: Sequence[Dict[str, Any]], horizons: Sequence[int], min_event_samples: int) -> Tuple[str, List[str]]:
    notes: List[str] = []
    avoid_passes = 0
    squeeze_passes = 0
    low_block_passes = 0

    for h in horizons:
        avoid = get_summary(summaries, h, "overlay_category", "AVOID_LONG_HOSTILE")
        if avoid:
            n = int(avoid["sample_count"])
            med = avoid.get("median_return_bps")
            wr = avoid.get("win_rate_long")
            if n >= min_event_samples and med is not None and med < 0 and wr is not None and wr < 0.45:
                avoid_passes += 1
            if avoid.get("note"):
                notes.append(f"h{h}_avoid_long_note={avoid['note']}")

        squeeze = get_summary(summaries, h, "overlay_category", "SQUEEZE_DO_NOT_SHORT")
        if squeeze:
            n = int(squeeze["sample_count"])
            med = squeeze.get("median_return_bps")
            wr = squeeze.get("win_rate_long")
            if n >= min_event_samples and med is not None and med > 0 and wr is not None and wr > 0.60:
                squeeze_passes += 1
            if squeeze.get("note"):
                notes.append(f"h{h}_squeeze_note={squeeze['note']}")

        low = get_summary(summaries, h, "overlay_category", "LOW_CONVICTION_BLOCK")
        if low:
            n = int(low["sample_count"])
            med = low.get("median_return_bps")
            if n >= min_event_samples and med is not None and med <= 0:
                low_block_passes += 1
            if low.get("note"):
                notes.append(f"h{h}_low_conviction_note={low['note']}")

    if avoid_passes >= 1 or squeeze_passes >= 1 or low_block_passes >= 1:
        decision = "PROCEED_TO_RESTRICTED_BASELINE_OVERLAY_RETEST_WITH_CAUTION"
    else:
        decision = "NO_GO_FOR_OVERLAY_PROMOTION"

    if any("YEAR_CONCENTRATED" in n for n in notes):
        notes.append("YEAR_CONCENTRATION_REQUIRES_RESTRICTED_RETEST_NOT_PROMOTION")
    return decision, notes


def json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def write_reports(report: Dict[str, Any], reports_dir: Path) -> Tuple[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage38b_t3_cot_overlay_gate.json"
    md_path = reports_dir / "stage38b_t3_cot_overlay_gate.md"
    json_path.write_text(json.dumps(json_safe(report), indent=2, sort_keys=True), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Stage38B / T3 COT Overlay Gate")
    lines.append("")
    lines.append(f"- created_utc: `{report['created_utc']}`")
    lines.append(f"- status: `{report['status']}`")
    lines.append(f"- decision: `{report['decision']}`")
    lines.append(f"- source_event_rows: `{report['source_event_rows']}`")
    lines.append(f"- events_written: `{report['events_written']}`")
    lines.append(f"- summary_rows_written: `{report['summary_rows_written']}`")
    lines.append(f"- stress_p90_cost_price: `{report['stress_p90_cost_price']}`")
    lines.append("")
    lines.append("## Decision Notes")
    lines.append("")
    for n in report.get("decision_notes", []):
        lines.append(f"- {n}")
    if not report.get("decision_notes"):
        lines.append("- None")
    lines.append("")
    lines.append("## Primary Overlay Summaries")
    lines.append("")
    lines.append("| horizon | group | n | mean bps | median bps | WR long | after cost mean bps | note |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---|")
    for s in report.get("primary_summaries", []):
        lines.append(
            f"| {s['horizon_bars']} | {s['group_value']} | {s['sample_count']} | "
            f"{fmt(s.get('mean_return_bps'))} | {fmt(s.get('median_return_bps'))} | "
            f"{fmt(s.get('win_rate_long'))} | {fmt(s.get('mean_return_bps_after_stress_cost'))} | "
            f"{s.get('note') or ''} |"
        )
    lines.append("")
    lines.append("## Guardrail")
    lines.append("")
    lines.append("This file is read-only research output. It is not a strategy, not ML, not paper-live, not EA, not Stage39, and not a live-order module.")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(md_path)


def fmt(x: Any) -> str:
    if x is None:
        return ""
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def write_audit(
    con: sqlite3.Connection,
    table: str,
    report: Dict[str, Any],
    returns_table: str,
    events_table: str,
    summary_table: str,
    horizons: Sequence[int],
    min_event_samples: int,
    stress_p90_cost_price: float,
    json_report: str,
    md_report: str,
) -> None:
    con.execute(AUDIT_SCHEMA.format(table_name=quote_ident(table)))
    con.execute(
        f"""
        INSERT INTO {quote_ident(table)} (
            created_utc, status, decision, returns_table, events_table, summary_table,
            source_event_rows, events_written, summary_rows_written,
            horizon_list, min_event_samples, stress_p90_cost_price,
            warning_count, note_count, json_report, md_report
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report["created_utc"],
            report["status"],
            report["decision"],
            returns_table,
            events_table,
            summary_table,
            report["source_event_rows"],
            report["events_written"],
            report["summary_rows_written"],
            ",".join(str(h) for h in horizons),
            min_event_samples,
            stress_p90_cost_price,
            report["warning_count"],
            report["note_count"],
            json_report,
            md_report,
        ),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage38B T3 COT overlay gate")
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--returns-table", default="cot_gold_t3_interaction_forward_returns")
    ap.add_argument("--events-table", default="cot_gold_t3_overlay_gate_events")
    ap.add_argument("--summary-table", default="cot_gold_t3_overlay_gate_summary")
    ap.add_argument("--audit-table", default="cot_gold_t3_overlay_gate_audit")
    ap.add_argument("--reports-dir", default="data/reports/stage38b_t3_cot_overlay_gate")
    ap.add_argument("--horizons", default="120,240")
    ap.add_argument("--min-event-samples", type=int, default=8)
    ap.add_argument("--stress-p90-cost-price", type=float, default=0.49)
    args = ap.parse_args(argv)

    horizons = parse_horizons(args.horizons)
    created = utc_now_iso()
    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    warnings: List[str] = []
    notes: List[str] = []

    rows = load_event_rows(con, args.returns_table, horizons, args.stress_p90_cost_price)
    if not rows:
        raise SystemExit("No event_level rows found for requested horizons")

    recreate_table(con, args.events_table, EVENTS_SCHEMA)
    recreate_table(con, args.summary_table, SUMMARY_SCHEMA)
    events_written = write_events(con, args.events_table, rows)

    summaries = build_summaries(created, rows, horizons, args.min_event_samples)
    summaries_written = write_summaries(con, args.summary_table, summaries)
    decision, decision_notes = decide(summaries, horizons, args.min_event_samples)
    notes.extend(decision_notes)

    primary_values = [
        "ALL",
        "LONG_PERMITTED",
        "LONG_BLOCKED",
        "AVOID_LONG_HOSTILE",
        "SQUEEZE_DO_NOT_SHORT",
        "LOW_CONVICTION_BLOCK",
    ]
    primary_summaries: List[Dict[str, Any]] = []
    for h in horizons:
        for gt, gv in [
            ("all", "ALL"),
            ("long_overlay_policy", "LONG_PERMITTED"),
            ("long_overlay_policy", "LONG_BLOCKED"),
            ("overlay_category", "AVOID_LONG_HOSTILE"),
            ("overlay_category", "SQUEEZE_DO_NOT_SHORT"),
            ("overlay_category", "LOW_CONVICTION_BLOCK"),
        ]:
            s = get_summary(summaries, h, gt, gv)
            if s:
                primary_summaries.append(s)

    report = {
        "created_utc": created,
        "status": "PASS" if not warnings else "PASS_WITH_WARNINGS",
        "decision": decision,
        "db": str(db_path),
        "returns_table": args.returns_table,
        "events_table": args.events_table,
        "summary_table": args.summary_table,
        "audit_table": args.audit_table,
        "source_event_rows": len(rows),
        "events_written": events_written,
        "summary_rows_written": summaries_written,
        "horizons": horizons,
        "min_event_samples": args.min_event_samples,
        "stress_p90_cost_price": args.stress_p90_cost_price,
        "warning_count": len(warnings),
        "warnings": warnings,
        "note_count": len(notes),
        "decision_notes": notes,
        "primary_summaries": primary_summaries,
    }

    json_report, md_report = write_reports(report, Path(args.reports_dir))
    report["json_report"] = json_report
    report["md_report"] = md_report

    write_audit(
        con,
        args.audit_table,
        report,
        args.returns_table,
        args.events_table,
        args.summary_table,
        horizons,
        args.min_event_samples,
        args.stress_p90_cost_price,
        json_report,
        md_report,
    )
    con.commit()
    con.close()

    print(json.dumps(json_safe({
        "status": report["status"],
        "decision": report["decision"],
        "source_event_rows": report["source_event_rows"],
        "events_written": report["events_written"],
        "summary_rows_written": report["summary_rows_written"],
        "warning_count": report["warning_count"],
        "note_count": report["note_count"],
        "json_report": json_report,
        "md_report": md_report,
        "events_table": args.events_table,
        "summary_table": args.summary_table,
        "audit_table": args.audit_table,
    }), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
