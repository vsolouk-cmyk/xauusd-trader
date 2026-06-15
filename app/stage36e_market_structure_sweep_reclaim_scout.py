#!/usr/bin/env python3
'''
XAUUSD Stage36E — Market Structure Sweep / Reclaim Scout

Research-only scout for a distinct thesis branch:
prior high/low sweep, reclaim, and continuation/reversal behavior on H1 data.

No EA, no paper-live, no order authorization.
'''

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


DB_PATH = Path("data/local/xauusd_local_store.sqlite")
REPORT_DIR = Path("data/reports/stage36e_market_structure_sweep_reclaim_scout")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

COST_PENALTY_X4 = 1.0

THRESHOLDS = {
    "min_events_review": 40,
    "min_events_background": 25,
    "min_pf_review": 1.25,
    "min_avg_review": 0.15,
    "min_wr_review": 0.52,
    "min_tail_pf_review": 1.0,
    "min_cost1_pf_review": 1.05,
    "max_drawdown_review": -45.0,
    "min_recent_pf_review": 1.0,
    "tail_n": 20,
    "recent_n": 20,
}


def _profit_factor(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return 0.0
    gross_pos = values[values > 0].sum()
    gross_neg = -values[values < 0].sum()
    if gross_pos <= 0 and gross_neg <= 0:
        return 0.0
    if gross_neg == 0:
        return float("inf")
    return float(gross_pos / gross_neg)


def _max_drawdown(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").fillna(0.0)
    if values.empty:
        return 0.0
    equity = values.cumsum()
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())


def _score_series(net: pd.Series) -> Dict[str, float]:
    net = pd.to_numeric(net, errors="coerce").dropna()
    n = int(len(net))
    if n == 0:
        return {
            "signal_count": 0,
            "pf_x4": 0.0,
            "avg_net_x4": 0.0,
            "win_rate_x4": 0.0,
            "tail_pf_x4": 0.0,
            "recent_pf_x4": 0.0,
            "cost1_pf_x4": 0.0,
            "max_drawdown_x4": 0.0,
        }
    tail = net.tail(int(THRESHOLDS["tail_n"]))
    recent = net.tail(int(THRESHOLDS["recent_n"]))
    cost_net = net - COST_PENALTY_X4
    return {
        "signal_count": n,
        "pf_x4": _profit_factor(net),
        "avg_net_x4": float(net.mean()),
        "win_rate_x4": float((net > 0).mean()),
        "tail_pf_x4": _profit_factor(tail),
        "recent_pf_x4": _profit_factor(recent),
        "cost1_pf_x4": _profit_factor(cost_net),
        "max_drawdown_x4": _max_drawdown(net),
    }


def _decision(metrics: Dict[str, float]) -> Tuple[str, str, str]:
    failed = []
    if metrics["signal_count"] < THRESHOLDS["min_events_review"]:
        failed.append("event_count")
    if metrics["pf_x4"] < THRESHOLDS["min_pf_review"]:
        failed.append("pf")
    if metrics["avg_net_x4"] < THRESHOLDS["min_avg_review"]:
        failed.append("avg_net")
    if metrics["win_rate_x4"] < THRESHOLDS["min_wr_review"]:
        failed.append("win_rate")
    if metrics["tail_pf_x4"] < THRESHOLDS["min_tail_pf_review"]:
        failed.append("tail_pf")
    if metrics["recent_pf_x4"] < THRESHOLDS["min_recent_pf_review"]:
        failed.append("recent_pf")
    if metrics["cost1_pf_x4"] < THRESHOLDS["min_cost1_pf_review"]:
        failed.append("cost1_pf")
    if metrics["max_drawdown_x4"] < THRESHOLDS["max_drawdown_review"]:
        failed.append("drawdown")

    if not failed:
        return (
            "STRICT_REVIEW_READY_RESEARCH_ONLY",
            "",
            "RUN_STAGE36F_STRICT_STRUCTURE_SWEEP_RECLAIM_REVIEW_NO_EA_NO_PAPER_LIVE",
        )

    if (
        metrics["signal_count"] >= THRESHOLDS["min_events_background"]
        and metrics["pf_x4"] >= 1.08
        and metrics["avg_net_x4"] > 0
        and metrics["tail_pf_x4"] >= 0.9
        and metrics["recent_pf_x4"] >= 0.9
    ):
        return (
            "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY",
            ";".join(failed),
            "KEEP_BACKGROUND_ONLY_AND_RERUN_AFTER_NEW_DATA",
        )

    return (
        "KILL_OR_REPAIR_RESEARCH_ONLY",
        ";".join(failed),
        "MOVE_TO_NEXT_STAGE36_THESIS_BRANCH_DO_NOT_WAIT_FOR_N40",
    )


def _table_names(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except Exception:
        return 0


def load_h1_ohlc(db_path: Path) -> Tuple[pd.DataFrame, Dict[str, object], pd.DataFrame]:
    audit_rows = []
    if not db_path.exists():
        return pd.DataFrame(), {"error": "db_not_found", "db_path": str(db_path)}, pd.DataFrame()

    conn = sqlite3.connect(str(db_path))
    try:
        for table in _table_names(conn):
            cols = _table_columns(conn, table)
            colset = set(cols)
            nrows = _row_count(conn, table)

            ts_col = "utc_time" if "utc_time" in colset else None
            if ts_col is None:
                for c in ["timestamp", "ts", "time", "datetime", "date_time"]:
                    if c in colset and c not in {"timeframe", "tf", "period", "interval"}:
                        ts_col = c
                        break

            open_col = "open" if "open" in colset else None
            high_col = "high" if "high" in colset else None
            low_col = "low" if "low" in colset else None
            close_col = "close" if "close" in colset else None
            symbol_col = "symbol" if "symbol" in colset else ""
            timeframe_col = "timeframe" if "timeframe" in colset else ""

            audit = {
                "db_path": str(db_path),
                "table": table,
                "source_rows": nrows,
                "timestamp_col": ts_col or "",
                "open_col": open_col or "",
                "high_col": high_col or "",
                "low_col": low_col or "",
                "close_col": close_col or "",
                "symbol_col": symbol_col,
                "timeframe_col": timeframe_col,
                "selected_rows": 0,
                "h1_rows": 0,
                "h1_start_ts": "",
                "h1_end_ts": "",
                "h1_median_delta_min": "",
                "error": "",
                "columns": ";".join(cols),
            }

            if not all([ts_col, open_col, high_col, low_col, close_col]):
                audit["error"] = "missing_ohlc_or_timestamp_columns"
                audit_rows.append(audit)
                continue

            where = []
            if symbol_col:
                where.append(f'UPPER("{symbol_col}") LIKE "%XAU%"')
            if timeframe_col:
                where.append(f'(LOWER(CAST("{timeframe_col}" AS TEXT)) IN ("1h","h1","60","60m","m60") OR "{timeframe_col}" IS NULL OR "{timeframe_col}"="")')
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""
            sql = f'''
                SELECT
                    "{ts_col}" AS ts,
                    "{open_col}" AS open,
                    "{high_col}" AS high,
                    "{low_col}" AS low,
                    "{close_col}" AS close
                FROM "{table}"
                {where_sql}
            '''
            try:
                df = pd.read_sql_query(sql, conn)
            except Exception as exc:
                audit["error"] = f"select_failed:{exc}"
                audit_rows.append(audit)
                continue

            if df.empty and timeframe_col:
                where2 = []
                if symbol_col:
                    where2.append(f'UPPER("{symbol_col}") LIKE "%XAU%"')
                where2_sql = (" WHERE " + " AND ".join(where2)) if where2 else ""
                sql2 = f'''
                    SELECT
                        "{ts_col}" AS ts,
                        "{open_col}" AS open,
                        "{high_col}" AS high,
                        "{low_col}" AS low,
                        "{close_col}" AS close
                    FROM "{table}"
                    {where2_sql}
                '''
                try:
                    df = pd.read_sql_query(sql2, conn)
                except Exception as exc:
                    audit["error"] = f"fallback_select_failed:{exc}"
                    audit_rows.append(audit)
                    continue

            audit["selected_rows"] = int(len(df))
            if df.empty:
                audit["error"] = "empty_table_after_select"
                audit_rows.append(audit)
                continue

            df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
            for c in ["open", "high", "low", "close"]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
            df = df.drop_duplicates(subset=["ts"], keep="last")
            if df.empty:
                audit["error"] = "no_valid_ohlc_rows_after_cleaning"
                audit_rows.append(audit)
                continue

            median_delta = df["ts"].diff().dropna().dt.total_seconds().median() / 60.0
            if np.isnan(median_delta):
                median_delta = 0

            if 55 <= median_delta <= 65:
                h1 = df.copy()
            else:
                h1 = (
                    df.set_index("ts")
                    .resample("1h")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
                    .dropna()
                    .reset_index()
                )

            h1 = h1.sort_values("ts").reset_index(drop=True)
            audit["h1_rows"] = int(len(h1))
            if len(h1) > 0:
                audit["h1_start_ts"] = str(h1["ts"].iloc[0])
                audit["h1_end_ts"] = str(h1["ts"].iloc[-1])
                audit["h1_median_delta_min"] = 60.0
                audit["error"] = ""
                audit_rows.append(audit)
                return h1, audit, pd.DataFrame(audit_rows)
            audit["error"] = "h1_empty_after_resample"
            audit_rows.append(audit)

        return pd.DataFrame(), {"error": "no_ohlc_table_found", "db_path": str(db_path)}, pd.DataFrame(audit_rows)
    finally:
        conn.close()


def make_structure_events(h1: pd.DataFrame) -> pd.DataFrame:
    df = h1.copy()
    daily = (
        df.assign(day=df["ts"].dt.floor("D"))
        .groupby("day")
        .agg(day_high=("high", "max"), day_low=("low", "min"), day_close=("close", "last"))
        .reset_index()
    )
    daily["day"] = daily["day"] + pd.Timedelta(days=1)
    ref = daily.rename(columns={"day_high": "prev_day_high", "day_low": "prev_day_low", "day_close": "prev_day_close"})
    df["day"] = df["ts"].dt.floor("D")
    df = df.merge(ref[["day", "prev_day_high", "prev_day_low", "prev_day_close"]], on="day", how="left")

    for w in [12, 24, 48]:
        df[f"roll_high_{w}"] = df["high"].rolling(w, min_periods=w).max().shift(1)
        df[f"roll_low_{w}"] = df["low"].rolling(w, min_periods=w).min().shift(1)

    return df


def build_variant_nets(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    horizons = [4, 8, 12]

    def add_variant(variant_id: str, setup: str, direction: str, signal_mask: pd.Series, horizon: int):
        idxs = np.where(signal_mask.fillna(False).to_numpy())[0]
        for i in idxs:
            j = i + horizon
            if j >= len(events):
                continue
            entry = float(events["close"].iloc[i])
            exitp = float(events["close"].iloc[j])
            if not np.isfinite(entry) or not np.isfinite(exitp):
                continue
            raw = exitp - entry
            net = raw if direction == "long" else -raw
            rows.append({
                "variant_id": variant_id,
                "setup": setup,
                "direction": direction,
                "horizon_hours": horizon,
                "entry_ts": events["ts"].iloc[i].isoformat(),
                "exit_ts": events["ts"].iloc[j].isoformat(),
                "net_x4": float(net),
            })

    high_sweep = events["high"] > events["prev_day_high"]
    high_reclaim_fail = high_sweep & (events["close"] < events["prev_day_high"])
    high_hold = high_sweep & (events["close"] > events["prev_day_high"])

    low_sweep = events["low"] < events["prev_day_low"]
    low_reclaim = low_sweep & (events["close"] > events["prev_day_low"])
    low_break_hold = low_sweep & (events["close"] < events["prev_day_low"])

    for h in horizons:
        add_variant(f"stage36e_prevday_high_sweep_reversal_short_h{h}", "prevday_high_sweep_reversal", "short", high_reclaim_fail, h)
        add_variant(f"stage36e_prevday_high_sweep_continuation_long_h{h}", "prevday_high_sweep_continuation", "long", high_hold, h)
        add_variant(f"stage36e_prevday_low_sweep_reclaim_long_h{h}", "prevday_low_sweep_reclaim", "long", low_reclaim, h)
        add_variant(f"stage36e_prevday_low_break_continuation_short_h{h}", "prevday_low_break_continuation", "short", low_break_hold, h)

    for w in [12, 24, 48]:
        rh = events[f"roll_high_{w}"]
        rl = events[f"roll_low_{w}"]
        roll_high_sweep = events["high"] > rh
        roll_high_fail = roll_high_sweep & (events["close"] < rh)
        roll_high_hold = roll_high_sweep & (events["close"] > rh)

        roll_low_sweep = events["low"] < rl
        roll_low_reclaim = roll_low_sweep & (events["close"] > rl)
        roll_low_hold = roll_low_sweep & (events["close"] < rl)

        for h in horizons:
            add_variant(f"stage36e_roll{w}_high_sweep_reversal_short_h{h}", f"roll{w}_high_sweep_reversal", "short", roll_high_fail, h)
            add_variant(f"stage36e_roll{w}_high_sweep_continuation_long_h{h}", f"roll{w}_high_sweep_continuation", "long", roll_high_hold, h)
            add_variant(f"stage36e_roll{w}_low_sweep_reclaim_long_h{h}", f"roll{w}_low_sweep_reclaim", "long", roll_low_reclaim, h)
            add_variant(f"stage36e_roll{w}_low_break_continuation_short_h{h}", f"roll{w}_low_break_continuation", "short", roll_low_hold, h)

    return pd.DataFrame(rows)


def evaluate_variants(ledger: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cols = [
        "variant_id", "setup", "direction", "horizon_hours", "signal_count", "pf_x4",
        "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4",
        "max_drawdown_x4", "fatal_failed_gates", "stage36e_decision", "next_action"
    ]
    if ledger.empty:
        return pd.DataFrame(columns=cols)

    for (variant_id, setup, direction, horizon), g in ledger.groupby(["variant_id", "setup", "direction", "horizon_hours"], dropna=False):
        g = g.sort_values("entry_ts")
        metrics = _score_series(g["net_x4"])
        dec, failed, action = _decision(metrics)
        rows.append({
            "variant_id": variant_id,
            "setup": setup,
            "direction": direction,
            "horizon_hours": int(horizon),
            **metrics,
            "fatal_failed_gates": failed,
            "stage36e_decision": dec,
            "next_action": action,
        })

    out = pd.DataFrame(rows)
    return out.sort_values(["stage36e_decision", "pf_x4", "avg_net_x4", "signal_count"], ascending=[True, False, False, False])


def write_report(summary: Dict[str, object], audit: pd.DataFrame, candidate_summary: pd.DataFrame,
                 strict_q: pd.DataFrame, background_q: pd.DataFrame, kill_q: pd.DataFrame,
                 structure_diag: pd.DataFrame):
    path = REPORT_DIR / "stage36e_market_structure_sweep_reclaim_scout.md"
    with path.open("w", encoding="utf-8") as f:
        f.write("# XAUUSD Stage36E — Market Structure Sweep / Reclaim Scout\n")
        f.write(f"Generated UTC: {summary['generated_utc']}\n\n")
        f.write("## Decision\n")
        for k in ["decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage"]:
            f.write(f"{k.upper()} = {summary[k]}\n")
        f.write("\n## Why this stage exists\n")
        f.write("Stage36B, Stage36C, and Stage36D did not produce strict review candidates. Stage36E starts the next distinct thesis branch: market-structure sweeps and reclaim/continuation behavior around prior-day and rolling swing levels. This is not h13/h14 variant mining and authorizes no execution.\n\n")

        f.write("## Summary\n")
        for k in ["stage36d_decision", "ohlc_table", "h1_rows", "structure_event_rows", "variant_rows", "strict_review_ready_rows", "background_rows", "kill_or_repair_rows"]:
            f.write(f"{k} = {summary.get(k)}\n")

        f.write("\n## Data source audit\n")
        f.write(audit.to_markdown(index=False) if not audit.empty else "No audit rows.")
        f.write("\n\n## Structure diagnostics\n")
        f.write(structure_diag.to_markdown(index=False) if not structure_diag.empty else "No diagnostics.")
        f.write("\n\n## Market structure candidate summary\n")
        f.write(candidate_summary.to_markdown(index=False) if not candidate_summary.empty else "No candidate rows.")
        f.write("\n\n## Strict review queue\n")
        f.write(strict_q.to_markdown(index=False) if not strict_q.empty else "No rows.")
        f.write("\n\n## Background queue\n")
        f.write(background_q.to_markdown(index=False) if not background_q.empty else "No rows.")
        f.write("\n\n## Kill / repair queue\n")
        f.write(kill_q.head(40).to_markdown(index=False) if not kill_q.empty else "No rows.")
        f.write("\n\n## Operational interpretation\n")
        f.write("1. If no strict review candidate exists, do not mine unlimited structure variants inside this branch.\n")
        f.write("2. Background rows can remain cheap monitors only; they do not authorize EA, paper-live, or orders.\n")
        f.write("3. Stage35C remains scheduled in the background for h13/h14 forward confirmation.\n")
        f.write("4. If this branch fails, move to the next Stage36 thesis branch: broker cost-window guard.\n\n")
        f.write("## Output files\n")
        for name in [
            "stage36e_market_structure_sweep_reclaim_scout.md",
            "stage36e_summary.json",
            "stage36e_data_source_audit.csv",
            "stage36e_structure_diagnostics.csv",
            "stage36e_signal_ledger.csv",
            "stage36e_candidate_summary.csv",
            "stage36e_strict_review_queue.csv",
            "stage36e_background_queue.csv",
            "stage36e_kill_or_repair_queue.csv",
        ]:
            f.write(f"- `data/reports/stage36e_market_structure_sweep_reclaim_scout/{name}`\n")


def main():
    from datetime import datetime, timezone

    h1, meta, audit = load_h1_ohlc(DB_PATH)
    stage36d_summary_path = Path("data/reports/stage36d_volatility_compression_breakout_scout/stage36d_summary.json")
    stage36d_decision = ""
    if stage36d_summary_path.exists():
        try:
            stage36d_decision = json.loads(stage36d_summary_path.read_text(encoding="utf-8")).get("decision", "")
        except Exception:
            stage36d_decision = ""

    if h1.empty:
        candidate_summary = pd.DataFrame()
        strict_q = pd.DataFrame()
        background_q = pd.DataFrame()
        kill_q = pd.DataFrame()
        structure_diag = pd.DataFrame()
        decision = "STAGE36E_NO_OHLC_DATA_AVAILABLE_RESEARCH_ONLY"
        recommended = "FIX_OHLC_DATA_SOURCE_BEFORE_STRUCTURE_SCOUT"
        ledger = pd.DataFrame()
    else:
        structure_events = make_structure_events(h1)
        ledger = build_variant_nets(structure_events)
        candidate_summary = evaluate_variants(ledger)
        strict_q = candidate_summary[candidate_summary["stage36e_decision"] == "STRICT_REVIEW_READY_RESEARCH_ONLY"].copy() if not candidate_summary.empty else pd.DataFrame()
        background_q = candidate_summary[candidate_summary["stage36e_decision"] == "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"].copy() if not candidate_summary.empty else pd.DataFrame()
        kill_q = candidate_summary[candidate_summary["stage36e_decision"] == "KILL_OR_REPAIR_RESEARCH_ONLY"].copy() if not candidate_summary.empty else pd.DataFrame()

        if len(strict_q) > 0:
            decision = "STAGE36E_HAS_STRUCTURE_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY"
            recommended = "RUN_STAGE36F_STRICT_STRUCTURE_SWEEP_RECLAIM_REVIEW_NO_EA_NO_PAPER_LIVE"
        elif len(background_q) > 0:
            decision = "STAGE36E_STRUCTURE_BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"
            recommended = "KEEP_BACKGROUND_AND_MOVE_TO_NEXT_STAGE36_THESIS_BRANCH"
        else:
            decision = "STAGE36E_NO_STRUCTURE_EDGE_RESEARCH_ONLY"
            recommended = "MOVE_TO_STAGE36F_BROKER_COST_WINDOW_GUARD_SCOUT"

        diag_rows = []
        if not structure_events.empty:
            diag_rows.append({
                "state": "prevday_high_sweep",
                "rows": int(((structure_events["high"] > structure_events["prev_day_high"]).fillna(False)).sum()),
            })
            diag_rows.append({
                "state": "prevday_low_sweep",
                "rows": int(((structure_events["low"] < structure_events["prev_day_low"]).fillna(False)).sum()),
            })
            for w in [12, 24, 48]:
                diag_rows.append({
                    "state": f"roll{w}_high_sweep",
                    "rows": int(((structure_events["high"] > structure_events[f"roll_high_{w}"]).fillna(False)).sum()),
                })
                diag_rows.append({
                    "state": f"roll{w}_low_sweep",
                    "rows": int(((structure_events["low"] < structure_events[f"roll_low_{w}"]).fillna(False)).sum()),
                })
        structure_diag = pd.DataFrame(diag_rows)

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "MARKET_STRUCTURE_SWEEP_RECLAIM_SCOUT_AS_DISTINCT_THESIS_BRANCH",
        "recommended_next_stage": recommended,
        "stage36d_decision": stage36d_decision,
        "db_path": str(DB_PATH),
        "ohlc_table": meta.get("table", ""),
        "h1_rows": int(len(h1)),
        "structure_event_rows": int(len(ledger)),
        "variant_rows": int(len(candidate_summary)),
        "strict_review_ready_rows": int(len(strict_q)),
        "background_rows": int(len(background_q)),
        "kill_or_repair_rows": int(len(kill_q)),
        "data_source_meta": meta,
        "thresholds": THRESHOLDS,
    }

    audit.to_csv(REPORT_DIR / "stage36e_data_source_audit.csv", index=False)
    structure_diag.to_csv(REPORT_DIR / "stage36e_structure_diagnostics.csv", index=False)
    ledger.to_csv(REPORT_DIR / "stage36e_signal_ledger.csv", index=False)
    candidate_summary.to_csv(REPORT_DIR / "stage36e_candidate_summary.csv", index=False)
    strict_q.to_csv(REPORT_DIR / "stage36e_strict_review_queue.csv", index=False)
    background_q.to_csv(REPORT_DIR / "stage36e_background_queue.csv", index=False)
    kill_q.to_csv(REPORT_DIR / "stage36e_kill_or_repair_queue.csv", index=False)
    (REPORT_DIR / "stage36e_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(summary, audit, candidate_summary, strict_q, background_q, kill_q, structure_diag)

    print(f"DECISION={summary['decision']}")
    print(f"RECOMMENDED_NEXT_STAGE={summary['recommended_next_stage']}")
    print(f"H1_ROWS={summary['h1_rows']}")
    print(f"STRUCTURE_EVENT_ROWS={summary['structure_event_rows']}")
    print(f"STRICT_REVIEW_READY_ROWS={summary['strict_review_ready_rows']}")
    print(f"BACKGROUND_ROWS={summary['background_rows']}")
    print(f"KILL_OR_REPAIR_ROWS={summary['kill_or_repair_rows']}")
    print(f"REPORT_DIR={REPORT_DIR}")


if __name__ == "__main__":
    main()
