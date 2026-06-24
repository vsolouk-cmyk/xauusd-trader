#!/usr/bin/env python3
"""
Stage38I Drift-Adjusted Survivor Audit

Read-only diagnostic.
Compares prior Stage38 context/gate rows against Stage38H bull-drift references.
Does not create trading signals, strategy, Stage39, EA, paper-live, or live logic.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


GATE_TABLES = [
    ("Stage38E_MACRO_GATE", "stage38e_macro_pass_gate_summary"),
    ("Stage38F_GLD_GATE", "stage38f_gld_pass_gate_summary"),
    ("Stage38G_COMPOSITE_GATE", "stage38g_exogenous_composite_gate_summary"),
]

CONTEXT_TABLES = [
    ("Stage38E_MACRO_CONTEXT", "stage38e_macro_context_era_summary"),
    ("Stage38F_GLD_CONTEXT", "stage38f_gld_feature_context_summary"),
]

HORIZONS = (24, 72, 120)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db: str) -> sqlite3.Connection:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where type='table' and name=? limit 1", (table,)
    ).fetchone()
    return row is not None


def col_exists(con: sqlite3.Connection, table: str, col: str) -> bool:
    if not table_exists(con, table):
        return False
    cols = [r[1] for r in con.execute(f'pragma table_info("{table}")').fetchall()]
    return col in cols


def fnum(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def inum(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None


def norm_year(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def recreate_tables(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute('drop table if exists stage38i_drift_adjusted_survivor_items')
    cur.execute('drop table if exists stage38i_drift_adjusted_survivor_audit')

    cur.execute(
        '''
        create table stage38i_drift_adjusted_survivor_items (
            item_id integer primary key autoincrement,
            created_at_utc text not null,
            source_stage text not null,
            source_table text not null,
            item_type text not null,
            horizon_bars integer not null,
            item_name text not null,
            policy_role text,
            source_event_count integer,
            trade_count integer,
            skipped_count integer,
            raw_mean_bps real,
            raw_median_bps real,
            raw_win_rate real,
            raw_t_stat real,
            event_clock_mean_bps real,
            baseline_event_clock_mean_bps real,
            stage_uplift_bps real,
            drift_reference_family text,
            drift_reference_mean_bps real,
            drift_adjusted_bps real,
            event_clock_max_drawdown_bps real,
            dd_delta_vs_baseline_bps real,
            positive_year_count integer,
            negative_year_count integer,
            max_positive_year_share real,
            positive_month_count integer,
            negative_month_count integer,
            max_positive_month_share real,
            pre2025_mean_bps real,
            exclude_2025_mean_bps real,
            y2025_mean_bps real,
            y2026_mean_bps real,
            first_half_mean_bps real,
            second_half_mean_bps real,
            worst_loo_mean_bps real,
            worst_loo_excluded_year text,
            original_decision text,
            survivor_decision text not null,
            note text
        )
        '''
    )

    cur.execute(
        '''
        create table stage38i_drift_adjusted_survivor_audit (
            audit_id integer primary key autoincrement,
            created_at_utc text not null,
            status text not null,
            decision text not null,
            drift_reference_rows integer not null,
            source_tables_scanned integer not null,
            missing_source_table_count integer not null,
            items_written integer not null,
            strict_pass_count integer not null,
            watch_count integer not null,
            context_only_watch_count integer not null,
            no_promotion_count integer not null,
            warning_count integer not null,
            note_count integer not null,
            min_drift_horizon integer,
            max_drift_horizon integer,
            report_json_path text,
            report_md_path text
        )
        '''
    )
    con.commit()


def load_drift_refs(con: sqlite3.Connection, table: str) -> Tuple[Dict[int, Tuple[str, float]], List[str]]:
    notes: List[str] = []
    refs: Dict[int, Tuple[str, float]] = {}
    if not table_exists(con, table):
        raise RuntimeError(f"Required drift table does not exist: {table}")

    # Prefer DAILY_ANCHOR, then H1_ALL.
    for family in ("DAILY_ANCHOR", "H1_ALL"):
        rows = con.execute(
            f'''
            select event_family, horizon_bars, long_mean_return_bps
            from "{table}"
            where event_family=?
            ''',
            (family,),
        ).fetchall()
        for r in rows:
            h = inum(r["horizon_bars"])
            m = fnum(r["long_mean_return_bps"])
            if h in HORIZONS and m is not None and h not in refs:
                refs[h] = (family, m)

    for h in HORIZONS:
        if h not in refs:
            notes.append(f"MISSING_DRIFT_REFERENCE_H{h}")
    return refs, notes


def decide_gate_item(
    residual: Optional[float],
    source_event_count: Optional[int],
    positive_years: Optional[int],
    max_year_share: Optional[float],
    worst_loo: Optional[float],
    note_in: Optional[str],
) -> Tuple[str, str]:
    notes: List[str] = []
    if residual is None:
        return "NO_PROMOTION", "MISSING_RESIDUAL"

    if residual < 3.0:
        notes.append("LOW_DRIFT_ADJUSTED_RESIDUAL_LT_3BPS")
    elif residual < 8.0:
        notes.append("MARGINAL_DRIFT_ADJUSTED_RESIDUAL_LT_8BPS")

    if source_event_count is not None and source_event_count < 150:
        notes.append("LOW_SOURCE_EVENT_COUNT_LT_150")
    if positive_years is not None and positive_years < 4:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_4")
    if max_year_share is not None and max_year_share > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if worst_loo is not None and worst_loo <= 5.0:
        notes.append("WEAK_WORST_LOO_LE_5BPS")
    if note_in:
        if "CHRONO_HALF_SIGN_MISMATCH" in note_in:
            notes.append("CHRONO_HALF_SIGN_MISMATCH")
        if "WORST_LOO_NON_POSITIVE" in note_in or "LEAVE_ONE_YEAR_OUT" in note_in:
            notes.append("LOO_WARNING_FROM_SOURCE")
        if "YEAR_CONCENTRATED" in note_in and "YEAR_CONCENTRATED_GT_55PCT" not in notes:
            notes.append("YEAR_CONCENTRATED_FROM_SOURCE")

    strict_ok = (
        residual >= 8.0
        and (source_event_count is None or source_event_count >= 150)
        and (positive_years is None or positive_years >= 4)
        and (max_year_share is None or max_year_share <= 0.55)
        and (worst_loo is None or worst_loo > 5.0)
        and not any(n in notes for n in ["CHRONO_HALF_SIGN_MISMATCH", "LOO_WARNING_FROM_SOURCE"])
    )
    if strict_ok:
        return "PASS_DRIFT_ADJUSTED_SURVIVOR_WATCH", ";".join(notes) if notes else None

    if residual >= 3.0 and (positive_years is None or positive_years >= 3):
        return "WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY", ";".join(notes) if notes else None

    return "NO_PROMOTION", ";".join(notes) if notes else None


def decide_context_item(
    residual: Optional[float],
    sample_count: Optional[int],
    positive_years: Optional[int],
    max_year_share: Optional[float],
    worst_loo: Optional[float],
    note_in: Optional[str],
) -> Tuple[str, str]:
    notes: List[str] = ["CONTEXT_ONLY_NO_EVENT_CLOCK_PROMOTION"]
    if residual is None:
        notes.append("MISSING_RESIDUAL")
        return "NO_PROMOTION", ";".join(notes)
    if sample_count is not None and sample_count < 60:
        notes.append("LOW_SAMPLE_LT_60")
    if residual < 8.0:
        notes.append("LOW_DRIFT_ADJUSTED_CONTEXT_RESIDUAL_LT_8BPS")
    if positive_years is not None and positive_years < 4:
        notes.append("LOW_POSITIVE_YEAR_COUNT_LT_4")
    if max_year_share is not None and max_year_share > 0.55:
        notes.append("YEAR_CONCENTRATED_GT_55PCT")
    if worst_loo is not None and worst_loo <= 5.0:
        notes.append("WEAK_WORST_LOO_LE_5BPS")
    if note_in:
        if "CHRONO_HALF_SIGN_MISMATCH" in note_in:
            notes.append("CHRONO_HALF_SIGN_MISMATCH")
        if "YEAR_CONCENTRATED" in note_in and "YEAR_CONCENTRATED_GT_55PCT" not in notes:
            notes.append("YEAR_CONCENTRATED_FROM_SOURCE")

    if residual >= 8.0 and (sample_count is None or sample_count >= 60) and (positive_years is None or positive_years >= 4):
        return "WATCH_CONTEXT_ONLY_NEEDS_EVENT_CLOCK_GATE", ";".join(notes)
    return "NO_PROMOTION", ";".join(notes)


def insert_item(con: sqlite3.Connection, item: Dict[str, Any]) -> None:
    cols = list(item.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f'insert into stage38i_drift_adjusted_survivor_items ({",".join(cols)}) values ({placeholders})'
    con.execute(sql, [item[c] for c in cols])


def scan_gate_table(
    con: sqlite3.Connection,
    created: str,
    source_stage: str,
    table: str,
    drift_refs: Dict[int, Tuple[str, float]],
) -> int:
    if not table_exists(con, table):
        return 0

    rows = con.execute(f'select * from "{table}"').fetchall()
    n = 0
    for r in rows:
        h = inum(r["horizon_bars"]) if "horizon_bars" in r.keys() else None
        if h not in drift_refs:
            continue
        policy_name = str(r["policy_name"]) if "policy_name" in r.keys() else "UNKNOWN_POLICY"
        if policy_name == "BASELINE_ALWAYS_LONG":
            # Keep baseline rows too, but mark them as references.
            pass
        drift_family, drift_mean = drift_refs[h]
        event_clock_mean = fnum(r["event_clock_mean_bps"]) if "event_clock_mean_bps" in r.keys() else None
        stage_uplift = fnum(r["uplift_vs_baseline_event_clock_mean_bps"]) if "uplift_vs_baseline_event_clock_mean_bps" in r.keys() else None
        residual = event_clock_mean - drift_mean if event_clock_mean is not None else None
        source_event_count = inum(r["source_event_count"]) if "source_event_count" in r.keys() else None
        positive_years = inum(r["positive_year_count"]) if "positive_year_count" in r.keys() else None
        max_year_share = fnum(r["max_positive_year_share"]) if "max_positive_year_share" in r.keys() else None
        worst_loo = fnum(r["worst_loo_event_clock_mean_bps"]) if "worst_loo_event_clock_mean_bps" in r.keys() else None
        source_note = str(r["note"]) if "note" in r.keys() and r["note"] is not None else None
        original_decision = str(r["decision"]) if "decision" in r.keys() and r["decision"] is not None else None

        if policy_name == "BASELINE_ALWAYS_LONG":
            survivor_decision = "DRIFT_BASELINE_REFERENCE"
            note = "REFERENCE_ROW_NOT_CANDIDATE"
        else:
            survivor_decision, note = decide_gate_item(
                residual, source_event_count, positive_years, max_year_share, worst_loo, source_note
            )

        item = {
            "created_at_utc": created,
            "source_stage": source_stage,
            "source_table": table,
            "item_type": "EVENT_CLOCK_GATE",
            "horizon_bars": h,
            "item_name": policy_name,
            "policy_role": str(r["policy_role"]) if "policy_role" in r.keys() and r["policy_role"] is not None else None,
            "source_event_count": source_event_count,
            "trade_count": inum(r["trade_count"]) if "trade_count" in r.keys() else None,
            "skipped_count": inum(r["skipped_count"]) if "skipped_count" in r.keys() else None,
            "raw_mean_bps": fnum(r["trade_mean_bps"]) if "trade_mean_bps" in r.keys() else None,
            "raw_median_bps": fnum(r["trade_median_bps"]) if "trade_median_bps" in r.keys() else None,
            "raw_win_rate": fnum(r["trade_win_rate"]) if "trade_win_rate" in r.keys() else None,
            "raw_t_stat": fnum(r["trade_t_stat"]) if "trade_t_stat" in r.keys() else None,
            "event_clock_mean_bps": event_clock_mean,
            "baseline_event_clock_mean_bps": fnum(r["baseline_event_clock_mean_bps"]) if "baseline_event_clock_mean_bps" in r.keys() else None,
            "stage_uplift_bps": stage_uplift,
            "drift_reference_family": drift_family,
            "drift_reference_mean_bps": drift_mean,
            "drift_adjusted_bps": residual,
            "event_clock_max_drawdown_bps": fnum(r["event_clock_max_drawdown_bps"]) if "event_clock_max_drawdown_bps" in r.keys() else None,
            "dd_delta_vs_baseline_bps": fnum(r["dd_delta_vs_baseline_bps"]) if "dd_delta_vs_baseline_bps" in r.keys() else None,
            "positive_year_count": positive_years,
            "negative_year_count": inum(r["negative_year_count"]) if "negative_year_count" in r.keys() else None,
            "max_positive_year_share": max_year_share,
            "positive_month_count": None,
            "negative_month_count": None,
            "max_positive_month_share": None,
            "pre2025_mean_bps": None,
            "exclude_2025_mean_bps": None,
            "y2025_mean_bps": None,
            "y2026_mean_bps": None,
            "first_half_mean_bps": None,
            "second_half_mean_bps": None,
            "worst_loo_mean_bps": worst_loo,
            "worst_loo_excluded_year": norm_year(r["worst_loo_excluded_year"]) if "worst_loo_excluded_year" in r.keys() else None,
            "original_decision": original_decision,
            "survivor_decision": survivor_decision,
            "note": note,
        }
        insert_item(con, item)
        n += 1
    return n


def scan_context_table(
    con: sqlite3.Connection,
    created: str,
    source_stage: str,
    table: str,
    drift_refs: Dict[int, Tuple[str, float]],
) -> int:
    if not table_exists(con, table):
        return 0
    rows = con.execute(f'select * from "{table}"').fetchall()
    n = 0
    for r in rows:
        h = inum(r["horizon_bars"]) if "horizon_bars" in r.keys() else None
        if h not in drift_refs:
            continue
        group_type = str(r["group_type"]) if "group_type" in r.keys() else "GROUP"
        group_value = str(r["group_value"]) if "group_value" in r.keys() else "UNKNOWN"
        decision = str(r["decision"]) if "decision" in r.keys() and r["decision"] is not None else "UNKNOWN"
        # Keep only rows that were previously not totally irrelevant, plus baseline reference.
        if not (decision.startswith("PASS") or decision.startswith("WATCH") or decision == "BASELINE_CONTEXT_REFERENCE"):
            continue

        drift_family, drift_mean = drift_refs[h]
        raw_mean = fnum(r["mean_return_bps"]) if "mean_return_bps" in r.keys() else None
        residual = raw_mean - drift_mean if raw_mean is not None else None
        sample_count = inum(r["sample_count"]) if "sample_count" in r.keys() else None
        positive_years = inum(r["positive_year_count"]) if "positive_year_count" in r.keys() else None
        max_year_share = fnum(r["max_positive_year_share"]) if "max_positive_year_share" in r.keys() else None
        worst_loo = fnum(r["worst_loo_mean_return_bps"]) if "worst_loo_mean_return_bps" in r.keys() else None
        source_note = str(r["note"]) if "note" in r.keys() and r["note"] is not None else None

        if decision == "BASELINE_CONTEXT_REFERENCE":
            survivor_decision = "DRIFT_BASELINE_REFERENCE"
            note = "REFERENCE_ROW_NOT_CANDIDATE"
        else:
            survivor_decision, note = decide_context_item(
                residual, sample_count, positive_years, max_year_share, worst_loo, source_note
            )

        item = {
            "created_at_utc": created,
            "source_stage": source_stage,
            "source_table": table,
            "item_type": "CONTEXT_ONLY_NO_EVENT_CLOCK",
            "horizon_bars": h,
            "item_name": f"{group_type}={group_value}",
            "policy_role": group_type,
            "source_event_count": sample_count,
            "trade_count": None,
            "skipped_count": None,
            "raw_mean_bps": raw_mean,
            "raw_median_bps": fnum(r["median_return_bps"]) if "median_return_bps" in r.keys() else None,
            "raw_win_rate": fnum(r["win_rate_long"]) if "win_rate_long" in r.keys() else None,
            "raw_t_stat": fnum(r["t_stat_mean_bps"]) if "t_stat_mean_bps" in r.keys() else None,
            "event_clock_mean_bps": None,
            "baseline_event_clock_mean_bps": None,
            "stage_uplift_bps": fnum(r["diff_vs_all_mean_bps"]) if "diff_vs_all_mean_bps" in r.keys() else None,
            "drift_reference_family": drift_family,
            "drift_reference_mean_bps": drift_mean,
            "drift_adjusted_bps": residual,
            "event_clock_max_drawdown_bps": None,
            "dd_delta_vs_baseline_bps": None,
            "positive_year_count": positive_years,
            "negative_year_count": inum(r["negative_year_count"]) if "negative_year_count" in r.keys() else None,
            "max_positive_year_share": max_year_share,
            "positive_month_count": inum(r["positive_month_count"]) if "positive_month_count" in r.keys() else None,
            "negative_month_count": inum(r["negative_month_count"]) if "negative_month_count" in r.keys() else None,
            "max_positive_month_share": fnum(r["max_positive_month_share"]) if "max_positive_month_share" in r.keys() else None,
            "pre2025_mean_bps": fnum(r["pre2025_mean_return_bps"]) if "pre2025_mean_return_bps" in r.keys() else None,
            "exclude_2025_mean_bps": fnum(r["exclude_2025_mean_return_bps"]) if "exclude_2025_mean_return_bps" in r.keys() else None,
            "y2025_mean_bps": fnum(r["y2025_mean_return_bps"]) if "y2025_mean_return_bps" in r.keys() else None,
            "y2026_mean_bps": fnum(r["y2026_mean_return_bps"]) if "y2026_mean_return_bps" in r.keys() else None,
            "first_half_mean_bps": fnum(r["first_half_mean_return_bps"]) if "first_half_mean_return_bps" in r.keys() else None,
            "second_half_mean_bps": fnum(r["second_half_mean_return_bps"]) if "second_half_mean_return_bps" in r.keys() else None,
            "worst_loo_mean_bps": worst_loo,
            "worst_loo_excluded_year": norm_year(r["worst_loo_excluded_year"]) if "worst_loo_excluded_year" in r.keys() else None,
            "original_decision": decision,
            "survivor_decision": survivor_decision,
            "note": note,
        }
        insert_item(con, item)
        n += 1
    return n


def write_reports(con: sqlite3.Connection, reports_dir: Path) -> Tuple[str, str]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows = con.execute(
        '''
        select * from stage38i_drift_adjusted_survivor_items
        order by
          case survivor_decision
            when 'PASS_DRIFT_ADJUSTED_SURVIVOR_WATCH' then 1
            when 'WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY' then 2
            when 'WATCH_CONTEXT_ONLY_NEEDS_EVENT_CLOCK_GATE' then 3
            when 'DRIFT_BASELINE_REFERENCE' then 4
            else 5
          end,
          coalesce(drift_adjusted_bps, -999999) desc
        '''
    ).fetchall()
    payload = {"created_at_utc": now_utc(), "items": [dict(r) for r in rows]}
    json_path = reports_dir / "stage38i_drift_adjusted_survivor_audit.json"
    md_path = reports_dir / "stage38i_drift_adjusted_survivor_audit.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Stage38I Drift-Adjusted Survivor Audit",
        "",
        f"Created: {payload['created_at_utc']}",
        "",
        "## Top rows",
        "",
        "| Decision | Horizon | Source | Type | Item | Drift adjusted bps | Event-clock bps | Drift ref bps | Note |",
        "|---|---:|---|---|---|---:|---:|---:|---|",
    ]
    for r in rows[:80]:
        lines.append(
            "| {decision} | {h} | {src} | {typ} | {name} | {res} | {ec} | {drift} | {note} |".format(
                decision=r["survivor_decision"],
                h=r["horizon_bars"],
                src=r["source_stage"],
                typ=r["item_type"],
                name=str(r["item_name"]).replace("|", "/"),
                res="" if r["drift_adjusted_bps"] is None else round(r["drift_adjusted_bps"], 2),
                ec="" if r["event_clock_mean_bps"] is None else round(r["event_clock_mean_bps"], 2),
                drift="" if r["drift_reference_mean_bps"] is None else round(r["drift_reference_mean_bps"], 2),
                note="" if r["note"] is None else str(r["note"]).replace("|", "/"),
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/local/xauusd_local_store.sqlite")
    ap.add_argument("--drift-table", default="stage38h_bull_drift_summary")
    ap.add_argument("--reports-dir", default="data/reports/stage38i_drift_adjusted_survivor_audit")
    args = ap.parse_args()

    con = connect(args.db)
    recreate_tables(con)
    created = now_utc()

    warnings: List[str] = []
    notes: List[str] = []
    try:
        drift_refs, drift_notes = load_drift_refs(con, args.drift_table)
        notes.extend(drift_notes)
    except Exception as e:
        con.execute(
            '''
            insert into stage38i_drift_adjusted_survivor_audit
            (created_at_utc,status,decision,drift_reference_rows,source_tables_scanned,missing_source_table_count,
             items_written,strict_pass_count,watch_count,context_only_watch_count,no_promotion_count,warning_count,note_count,
             min_drift_horizon,max_drift_horizon,report_json_path,report_md_path)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (created, "FAIL", f"DRIFT_REFERENCE_LOAD_FAILED: {e}", 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, None, None, None, None),
        )
        con.commit()
        raise

    source_tables = GATE_TABLES + CONTEXT_TABLES
    missing = 0
    scanned = 0
    items_written = 0
    for source_stage, table in GATE_TABLES:
        if table_exists(con, table):
            scanned += 1
            items_written += scan_gate_table(con, created, source_stage, table, drift_refs)
        else:
            missing += 1
            warnings.append(f"MISSING_SOURCE_TABLE:{table}")

    for source_stage, table in CONTEXT_TABLES:
        if table_exists(con, table):
            scanned += 1
            items_written += scan_context_table(con, created, source_stage, table, drift_refs)
        else:
            missing += 1
            warnings.append(f"MISSING_SOURCE_TABLE:{table}")

    con.commit()
    json_path, md_path = write_reports(con, Path(args.reports_dir))

    counts = {r["survivor_decision"]: r["c"] for r in con.execute(
        "select survivor_decision, count(*) c from stage38i_drift_adjusted_survivor_items group by survivor_decision"
    ).fetchall()}
    strict_pass = counts.get("PASS_DRIFT_ADJUSTED_SURVIVOR_WATCH", 0)
    watch = counts.get("WATCH_DRIFT_ADJUSTED_RESIDUAL_ONLY", 0)
    context_watch = counts.get("WATCH_CONTEXT_ONLY_NEEDS_EVENT_CLOCK_GATE", 0)
    no_promo = counts.get("NO_PROMOTION", 0)

    if strict_pass > 0:
        decision = "REVIEW_STRICT_DRIFT_ADJUSTED_SURVIVORS_READ_ONLY"
    elif watch > 0 or context_watch > 0:
        decision = "DRIFT_ADJUSTED_WATCH_ONLY_NO_PROMOTION"
    else:
        decision = "NO_DRIFT_ADJUSTED_SURVIVORS_ARCHIVE_STAGE38"

    horizons = sorted(drift_refs.keys())
    con.execute(
        '''
        insert into stage38i_drift_adjusted_survivor_audit
        (created_at_utc,status,decision,drift_reference_rows,source_tables_scanned,missing_source_table_count,
         items_written,strict_pass_count,watch_count,context_only_watch_count,no_promotion_count,warning_count,note_count,
         min_drift_horizon,max_drift_horizon,report_json_path,report_md_path)
        values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''',
        (
            created,
            "PASS",
            decision,
            len(drift_refs),
            scanned,
            missing,
            items_written,
            strict_pass,
            watch,
            context_watch,
            no_promo,
            len(warnings),
            len(notes),
            min(horizons) if horizons else None,
            max(horizons) if horizons else None,
            json_path,
            md_path,
        ),
    )
    con.commit()

    print(json.dumps({
        "status": "PASS",
        "decision": decision,
        "items_written": items_written,
        "strict_pass_count": strict_pass,
        "watch_count": watch,
        "context_only_watch_count": context_watch,
        "no_promotion_count": no_promo,
        "warnings": warnings,
        "notes": notes,
        "report_json_path": json_path,
        "report_md_path": md_path,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
