from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path.cwd()
DB_PATH = ROOT / "data/local/xauusd_local_store.sqlite"
OUT_DIR = ROOT / "data/reports/stage36f_broker_cost_window_guard_scout"
STAGE36E_DIR = ROOT / "data/reports/stage36e_market_structure_sweep_reclaim_scout"
STAGE35C_SUMMARY = ROOT / "data/reports/stage35c_forward_confirmation_trigger_queue_pruner/stage35c_summary.json"

MIN_EVENTS_REVIEW = 40
MIN_EVENTS_BACKGROUND = 25
MIN_PF_REVIEW = 1.25
MIN_AVG_REVIEW = 0.15
MIN_WR_REVIEW = 0.52
MIN_TAIL_PF_REVIEW = 1.0
MIN_COST1_PF_REVIEW = 1.05
MAX_DD_REVIEW = -45.0
MIN_RECENT_PF_REVIEW = 1.0
TAIL_N = 20
RECENT_N = 20


def ensure_out() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pf(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    gains = s[s > 0].sum()
    losses = -s[s < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def max_drawdown(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if s.empty:
        return 0.0
    eq = s.cumsum()
    dd = eq - eq.cummax()
    return float(dd.min())


def metrics(df: pd.DataFrame, net_col: str = "net_x4") -> Dict:
    if df is None or df.empty or net_col not in df.columns:
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
    d = df.copy()
    d[net_col] = pd.to_numeric(d[net_col], errors="coerce")
    d = d.dropna(subset=[net_col])
    if d.empty:
        return metrics(pd.DataFrame(), net_col)
    net = d[net_col]
    cost_net = net - 1.0
    return {
        "signal_count": int(len(d)),
        "pf_x4": pf(net),
        "avg_net_x4": float(net.mean()),
        "win_rate_x4": float((net > 0).mean()),
        "tail_pf_x4": pf(net.tail(TAIL_N)),
        "recent_pf_x4": pf(net.tail(RECENT_N)),
        "cost1_pf_x4": pf(cost_net),
        "max_drawdown_x4": max_drawdown(net),
    }


def candidate_time_cols(cols: List[str]) -> List[str]:
    banned = {"timeframe", "tf", "period", "interval", "time_exit_h1_bars"}
    preferred = [
        "entry_ts", "entry_time", "signal_ts", "signal_time", "timestamp", "ts", "utc_time",
        "time", "datetime", "date_time", "event_time_utc", "signal_closed_h1_utc",
    ]
    out = [c for c in preferred if c in cols and c not in banned]
    out += [c for c in cols if ("time" in c.lower() or "utc" in c.lower() or "date" in c.lower()) and c not in out and c not in banned]
    return out


def read_sqlite_table_names(db_path: Path) -> List[str]:
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def load_h1_bars(db_path: Path) -> Tuple[pd.DataFrame, Dict]:
    meta = {"db_path": str(db_path), "error": ""}
    if not db_path.exists():
        meta["error"] = "db_missing"
        return pd.DataFrame(), meta
    con = sqlite3.connect(db_path)
    try:
        tables = read_sqlite_table_names(db_path)
        if "bars" not in tables:
            meta["error"] = "bars_table_missing"
            return pd.DataFrame(), meta
        cols_df = pd.read_sql_query("PRAGMA table_info(bars)", con)
        cols = cols_df["name"].astype(str).tolist()
        meta["columns"] = ";".join(cols)
        needed = {"open", "high", "low", "close"}
        if not needed.issubset(set(cols)):
            meta["error"] = "missing_ohlc_columns"
            return pd.DataFrame(), meta
        ts_col = "utc_time" if "utc_time" in cols else None
        if ts_col is None:
            for c in candidate_time_cols(cols):
                ts_col = c
                break
        if ts_col is None:
            meta["error"] = "missing_timestamp_column"
            return pd.DataFrame(), meta
        symbol_filter = "WHERE symbol='XAUUSD'" if "symbol" in cols else ""
        tf_filter = ""
        if "timeframe" in cols:
            tf_filter = " AND timeframe IN ('1h','H1','1H','60m','60min')" if symbol_filter else "WHERE timeframe IN ('1h','H1','1H','60m','60min')"
        q = f"SELECT {ts_col} AS ts, open, high, low, close" + (", spread" if "spread" in cols else "") + f" FROM bars {symbol_filter}{tf_filter}"
        df = pd.read_sql_query(q, con)
        if df.empty and "timeframe" in cols:
            q = f"SELECT {ts_col} AS ts, open, high, low, close" + (", spread" if "spread" in cols else "") + f" FROM bars {symbol_filter}"
            df = pd.read_sql_query(q, con)
        meta["source_rows"] = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM bars", con)["n"].iloc[0])
        meta["selected_rows"] = int(len(df))
    finally:
        con.close()
    if df.empty:
        meta["error"] = "empty_after_select"
        return pd.DataFrame(), meta
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    for c in ["open", "high", "low", "close", "spread"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
    df = df.drop_duplicates(subset=["ts"], keep="last")
    if df.empty:
        meta["error"] = "empty_after_clean"
        return pd.DataFrame(), meta
    # If lower timeframe slipped through, resample to H1.
    med = df["ts"].diff().dt.total_seconds().dropna().median() / 60 if len(df) > 1 else 60
    if med and med < 50:
        r = df.set_index("ts").resample("1h").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "spread": "median" if "spread" in df.columns else "first"
        }).dropna(subset=["open", "high", "low", "close"]).reset_index()
        df = r
    if "spread" not in df.columns:
        df["spread"] = 0.0
    meta.update({
        "h1_rows": int(len(df)),
        "h1_start_ts": str(df["ts"].min()),
        "h1_end_ts": str(df["ts"].max()),
        "h1_median_delta_min": float(df["ts"].diff().dt.total_seconds().dropna().median() / 60) if len(df) > 1 else 0.0,
        "spread_median": float(df["spread"].median()) if "spread" in df.columns else 0.0,
        "spread_q75": float(df["spread"].quantile(0.75)) if "spread" in df.columns else 0.0,
        "spread_q90": float(df["spread"].quantile(0.90)) if "spread" in df.columns else 0.0,
    })
    return df, meta


def load_stage36e_ledger() -> pd.DataFrame:
    candidates = [
        STAGE36E_DIR / "stage36e_signal_ledger.csv",
        STAGE36E_DIR / "stage36e_candidate_summary.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_csv(p)
                if len(df):
                    return df
            except Exception:
                pass
    return pd.DataFrame()


def normalize_signal_ledger(df: pd.DataFrame, bars: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    meta = {"source_rows": int(len(df)), "error": ""}
    if df.empty:
        meta["error"] = "stage36e_ledger_missing"
        return pd.DataFrame(), meta
    out = df.copy()
    cols = list(out.columns)
    # Preserve only signal/event ledger-like rows; candidate summary has no per-signal net.
    variant_col = None
    for c in ["variant_id", "candidate", "set_name", "setup"]:
        if c in cols:
            variant_col = c
            break
    net_col = None
    for c in ["net_x4", "net", "outcome_net_x4", "ret_x4", "pnl_x4"]:
        if c in cols:
            net_col = c
            break
    ts_col = None
    for c in candidate_time_cols(cols):
        ts_col = c
        break
    if not variant_col or not net_col or not ts_col:
        meta["error"] = "missing_variant_net_or_timestamp_columns"
        meta["columns"] = ";".join(cols)
        return pd.DataFrame(), meta
    out = out.rename(columns={variant_col: "variant_id", net_col: "net_x4", ts_col: "ts"})
    out["ts"] = pd.to_datetime(out["ts"], errors="coerce", utc=True)
    out["net_x4"] = pd.to_numeric(out["net_x4"], errors="coerce")
    out = out.dropna(subset=["ts", "net_x4", "variant_id"])
    if out.empty:
        meta["error"] = "empty_after_normalize"
        return pd.DataFrame(), meta
    # Join broker spread/cost features from bars.
    b = bars[["ts", "spread"]].copy()
    b["hour"] = b["ts"].dt.hour
    b["weekday"] = b["ts"].dt.weekday
    out = pd.merge_asof(out.sort_values("ts"), b.sort_values("ts"), on="ts", direction="nearest", tolerance=pd.Timedelta("59min"))
    out["hour"] = out["ts"].dt.hour
    out["weekday"] = out["ts"].dt.weekday
    meta["normalized_rows"] = int(len(out))
    return out, meta


def session_name(hour: int) -> str:
    if 0 <= hour <= 5:
        return "asia_late"
    if 6 <= hour <= 11:
        return "london_morning"
    if 12 <= hour <= 16:
        return "ny_overlap"
    if 17 <= hour <= 22:
        return "ny_late"
    return "rollover"


def evaluate_filters(sig: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    if sig.empty:
        return pd.DataFrame()
    spread_q50 = bars["spread"].quantile(0.50) if "spread" in bars.columns else 0.0
    spread_q75 = bars["spread"].quantile(0.75) if "spread" in bars.columns else 0.0
    rows = []
    # Focus on Stage36E background variants first if present.
    variants = sorted(sig["variant_id"].dropna().unique().tolist())
    if len(variants) > 20:
        # Keep variants that look like structure continuation background if many raw ledger ids exist.
        variants = [v for v in variants if "high_sweep_continuation" in str(v)][:20] or variants[:20]
    filter_defs = [
        ("all_hours", lambda d: pd.Series(True, index=d.index)),
        ("low_spread_le_q50", lambda d: d["spread"].fillna(0) <= spread_q50),
        ("normal_spread_le_q75", lambda d: d["spread"].fillna(0) <= spread_q75),
        ("exclude_rollover_23_00", lambda d: ~d["hour"].isin([23, 0])),
        ("london_ny_only_06_16", lambda d: d["hour"].between(6, 16)),
        ("ny_overlap_only_12_16", lambda d: d["hour"].between(12, 16)),
        ("avoid_friday_late", lambda d: ~((d["weekday"] == 4) & (d["hour"] >= 17))),
    ]
    for vid in variants:
        base = sig[sig["variant_id"] == vid].copy()
        if base.empty:
            continue
        for fname, f in filter_defs:
            try:
                sub = base[f(base)].copy()
            except Exception:
                sub = pd.DataFrame()
            m = metrics(sub)
            fatal = []
            if m["signal_count"] < MIN_EVENTS_REVIEW: fatal.append("event_count")
            if m["pf_x4"] < MIN_PF_REVIEW: fatal.append("pf")
            if m["avg_net_x4"] < MIN_AVG_REVIEW: fatal.append("avg_net")
            if m["win_rate_x4"] < MIN_WR_REVIEW: fatal.append("win_rate")
            if m["tail_pf_x4"] < MIN_TAIL_PF_REVIEW: fatal.append("tail_pf")
            if m["recent_pf_x4"] < MIN_RECENT_PF_REVIEW: fatal.append("recent_pf")
            if m["cost1_pf_x4"] < MIN_COST1_PF_REVIEW: fatal.append("cost1_pf")
            if m["max_drawdown_x4"] < MAX_DD_REVIEW: fatal.append("drawdown")
            if not fatal:
                decision = "STRICT_REVIEW_READY_RESEARCH_ONLY"
                next_action = "RUN_STRICT_COST_WINDOW_REVIEW_NO_EA_NO_PAPER"
            elif m["signal_count"] >= MIN_EVENTS_BACKGROUND and m["pf_x4"] >= 1.10 and m["avg_net_x4"] > 0:
                decision = "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"
                next_action = "KEEP_BACKGROUND_ONLY_AND_RERUN_AFTER_NEW_DATA"
            else:
                decision = "KILL_OR_REPAIR_RESEARCH_ONLY"
                next_action = "DO_NOT_WAIT_FOR_N40_MOVE_TO_BRANCH_DECISION"
            rows.append({
                "variant_id": vid,
                "guard_filter": fname,
                **m,
                "fatal_failed_gates": ";".join(fatal),
                "stage36f_decision": decision,
                "next_action": next_action,
            })
    return pd.DataFrame(rows)


def classify_decision(cand: pd.DataFrame) -> Tuple[str, str]:
    if cand.empty:
        return "STAGE36F_NO_EVALUABLE_SIGNAL_LEDGER_RESEARCH_ONLY", "FIX_STAGE36E_SIGNAL_LEDGER_OR_MOVE_TO_BRANCH_DECISION"
    strict = int((cand["stage36f_decision"] == "STRICT_REVIEW_READY_RESEARCH_ONLY").sum())
    bg = int((cand["stage36f_decision"] == "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY").sum())
    if strict > 0:
        return "STAGE36F_HAS_COST_WINDOW_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY", "RUN_STAGE36G_STRICT_COST_WINDOW_REVIEW_NO_EA_NO_PAPER"
    if bg > 0:
        return "STAGE36F_COST_WINDOW_BACKGROUND_ONLY_RESEARCH_ONLY", "KEEP_BACKGROUND_AND_PREPARE_BRANCH_LEVEL_DECISION"
    return "STAGE36F_NO_COST_WINDOW_EDGE_RESEARCH_ONLY", "PREPARE_BRANCH_LEVEL_DECISION_OR_NEXT_DISTINCT_THESIS"


def write_report(summary: Dict, source_meta: Dict, ledger_meta: Dict, cand: pd.DataFrame) -> None:
    strict_df = cand[cand["stage36f_decision"] == "STRICT_REVIEW_READY_RESEARCH_ONLY"].copy() if not cand.empty else pd.DataFrame()
    bg_df = cand[cand["stage36f_decision"] == "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"].copy() if not cand.empty else pd.DataFrame()
    kill_df = cand[cand["stage36f_decision"] == "KILL_OR_REPAIR_RESEARCH_ONLY"].copy() if not cand.empty else pd.DataFrame()
    source_df = pd.DataFrame([source_meta])
    ledger_df = pd.DataFrame([ledger_meta])
    source_df.to_csv(OUT_DIR / "stage36f_data_source_audit.csv", index=False)
    ledger_df.to_csv(OUT_DIR / "stage36f_signal_ledger_audit.csv", index=False)
    cand.to_csv(OUT_DIR / "stage36f_cost_window_candidate_summary.csv", index=False)
    strict_df.to_csv(OUT_DIR / "stage36f_strict_review_queue.csv", index=False)
    bg_df.to_csv(OUT_DIR / "stage36f_background_queue.csv", index=False)
    kill_df.to_csv(OUT_DIR / "stage36f_kill_or_repair_queue.csv", index=False)
    (OUT_DIR / "stage36f_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    def md_table(df: pd.DataFrame, max_rows: int = 25) -> str:
        if df.empty:
            return "No rows."
        return df.head(max_rows).to_markdown(index=False)

    md = f"""# XAUUSD Stage36F — Broker Cost / Time-Window Guard Scout
Generated UTC: {summary['generated_utc']}

## Decision
DECISION = {summary['decision']}
EXECUTION_STATUS = RESEARCH_ONLY
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True
PRIMARY_OBJECTIVE = BROKER_COST_WINDOW_GUARD_AS_DISTINCT_THESIS_BRANCH
RECOMMENDED_NEXT_STAGE = {summary['recommended_next_stage']}

## Why this stage exists
Stage36B/C/D/E did not produce strict review candidates. Stage36E did find market-structure continuation rows with strong raw PF, but drawdown blocked promotion. Stage36F tests whether broker spread, rollover, hour, and session-window guards can reduce the drawdown enough to create a strict research review candidate. This authorizes no execution.

## Summary
stage36e_decision = {summary.get('stage36e_decision','')}
ohlc_table = {summary.get('ohlc_table','')}
h1_rows = {summary.get('h1_rows',0)}
ledger_rows = {summary.get('ledger_rows',0)}
normalized_signal_rows = {summary.get('normalized_signal_rows',0)}
variant_guard_rows = {summary.get('variant_guard_rows',0)}
strict_review_ready_rows = {summary.get('strict_review_ready_rows',0)}
background_rows = {summary.get('background_rows',0)}
kill_or_repair_rows = {summary.get('kill_or_repair_rows',0)}

## Data source audit
{md_table(source_df)}

## Signal ledger audit
{md_table(ledger_df)}

## Cost-window candidate summary
{md_table(cand, 30)}

## Strict review queue
{md_table(strict_df)}

## Background queue
{md_table(bg_df)}

## Kill / repair queue
{md_table(kill_df, 20)}

## Operational interpretation
1. Cost-window filtering can only promote a path if it fixes drawdown while preserving PF, tail, recent, and cost-stressed PF.
2. If no strict row appears here, do not continue mining the same Stage36 branches indefinitely.
3. Stage35C remains scheduled in the background for h13/h14 forward confirmation.
4. No EA, paper-live, or order transition is authorized here.

## Output files
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_broker_cost_window_guard_scout.md`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_summary.json`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_data_source_audit.csv`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_signal_ledger_audit.csv`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_cost_window_candidate_summary.csv`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_strict_review_queue.csv`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_background_queue.csv`
- `data/reports/stage36f_broker_cost_window_guard_scout/stage36f_kill_or_repair_queue.csv`
"""
    (OUT_DIR / "stage36f_broker_cost_window_guard_scout.md").write_text(md, encoding="utf-8")


def main() -> None:
    ensure_out()
    bars, source_meta = load_h1_bars(DB_PATH)
    stage36e_summary = safe_read_json(STAGE36E_DIR / "stage36e_summary.json")
    ledger_raw = load_stage36e_ledger()
    ledger, ledger_meta = normalize_signal_ledger(ledger_raw, bars) if not bars.empty else (pd.DataFrame(), {"error": "bars_missing", "source_rows": int(len(ledger_raw))})
    cand = evaluate_filters(ledger, bars) if not ledger.empty and not bars.empty else pd.DataFrame()
    decision, next_stage = classify_decision(cand)
    summary = {
        "generated_utc": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "BROKER_COST_WINDOW_GUARD_AS_DISTINCT_THESIS_BRANCH",
        "recommended_next_stage": next_stage,
        "stage36e_decision": stage36e_summary.get("decision", ""),
        "db_path": str(DB_PATH),
        "ohlc_table": "bars" if not bars.empty else "",
        "h1_rows": int(len(bars)),
        "ledger_rows": int(len(ledger_raw)),
        "normalized_signal_rows": int(len(ledger)),
        "variant_guard_rows": int(len(cand)),
        "strict_review_ready_rows": int((cand.get("stage36f_decision", pd.Series(dtype=str)) == "STRICT_REVIEW_READY_RESEARCH_ONLY").sum()) if not cand.empty else 0,
        "background_rows": int((cand.get("stage36f_decision", pd.Series(dtype=str)) == "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY").sum()) if not cand.empty else 0,
        "kill_or_repair_rows": int((cand.get("stage36f_decision", pd.Series(dtype=str)) == "KILL_OR_REPAIR_RESEARCH_ONLY").sum()) if not cand.empty else 0,
        "data_source_meta": source_meta,
        "signal_ledger_meta": ledger_meta,
        "thresholds": {
            "min_events_review": MIN_EVENTS_REVIEW,
            "min_events_background": MIN_EVENTS_BACKGROUND,
            "min_pf_review": MIN_PF_REVIEW,
            "min_avg_review": MIN_AVG_REVIEW,
            "min_wr_review": MIN_WR_REVIEW,
            "min_tail_pf_review": MIN_TAIL_PF_REVIEW,
            "min_cost1_pf_review": MIN_COST1_PF_REVIEW,
            "max_drawdown_review": MAX_DD_REVIEW,
            "min_recent_pf_review": MIN_RECENT_PF_REVIEW,
        },
    }
    write_report(summary, source_meta, ledger_meta, cand)
    print(f"DECISION={decision}")
    print(f"REPORT={OUT_DIR / 'stage36f_broker_cost_window_guard_scout.md'}")
    print(f"SUMMARY={OUT_DIR / 'stage36f_summary.json'}")


if __name__ == "__main__":
    main()
