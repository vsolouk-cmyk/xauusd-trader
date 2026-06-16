from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

DB_PATH = Path("data/local/xauusd_local_store.sqlite")
REPORT_DIR = Path("data/reports/stage36c_event_risk_guard_scout")

COST_PENALTY_X4 = 1.0
TAIL_N = 20
RECENT_N = 20

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
}

TIMESTAMP_CANDIDATES = [
    "utc_time", "timestamp", "ts", "time", "datetime", "date_time", "bar_time", "open_time",
    "event_time_utc", "source_time", "created_utc", "imported_utc",
]
DATE_CANDIDATES = ["date", "day", "obs_date", "<DATE>"]
TIME_CANDIDATES = ["time", "hour", "<TIME>"]
BAD_TS_NAMES = {"timeframe", "tf", "period", "interval"}
OPEN_CANDIDATES = ["open", "o", "<OPEN>"]
HIGH_CANDIDATES = ["high", "h", "<HIGH>"]
LOW_CANDIDATES = ["low", "l", "<LOW>"]
CLOSE_CANDIDATES = ["close", "c", "close_h1", "<CLOSE>"]
SYMBOL_CANDIDATES = ["symbol", "ticker", "instrument"]
TIMEFRAME_CANDIDATES = ["timeframe", "tf", "period", "interval"]

EVENT_TABLES = [
    "news_events", "numeric_shock_events", "event_pipeline_staging", "macro_events"
]


def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def table_names(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def norm_name(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def find_col(cols: Iterable[str], candidates: Iterable[str], *, exclude: Iterable[str] = ()) -> str:
    cols_list = list(cols)
    norm_map = {norm_name(c): c for c in cols_list}
    excluded = {norm_name(x) for x in exclude}
    for cand in candidates:
        n = norm_name(cand)
        if n in norm_map and n not in excluded:
            return norm_map[n]
    for c in cols_list:
        n = norm_name(c)
        if n in excluded:
            continue
        for cand in candidates:
            cn = norm_name(cand)
            if cn and (n == cn or n.endswith("_" + cn) or cn in n):
                return c
    return ""


def parse_ts(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        vals = pd.to_numeric(series, errors="coerce")
        finite = vals[np.isfinite(vals)]
        if len(finite) == 0:
            return pd.to_datetime(series, errors="coerce", utc=True)
        med = float(finite.median())
        unit = "ms" if med > 10_000_000_000 else "s"
        return pd.to_datetime(vals, errors="coerce", utc=True, unit=unit)
    return pd.to_datetime(series, errors="coerce", utc=True)


def load_h1_bars(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, Dict[str, Any], pd.DataFrame]:
    audit: List[Dict[str, Any]] = []
    best: Optional[pd.DataFrame] = None
    best_meta: Dict[str, Any] = {}

    for table in table_names(conn):
        cols = table_columns(conn, table)
        source_rows = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        ts_col = find_col(cols, TIMESTAMP_CANDIDATES, exclude=BAD_TS_NAMES)
        date_col = find_col(cols, DATE_CANDIDATES)
        time_col = find_col(cols, TIME_CANDIDATES, exclude=BAD_TS_NAMES | {date_col})
        o_col = find_col(cols, OPEN_CANDIDATES)
        h_col = find_col(cols, HIGH_CANDIDATES)
        l_col = find_col(cols, LOW_CANDIDATES)
        c_col = find_col(cols, CLOSE_CANDIDATES)
        sym_col = find_col(cols, SYMBOL_CANDIDATES)
        tf_col = find_col(cols, TIMEFRAME_CANDIDATES)

        row = {
            "db_path": str(DB_PATH), "table": table, "source_rows": source_rows,
            "timestamp_col": ts_col, "date_col": date_col, "time_col": time_col,
            "open_col": o_col, "high_col": h_col, "low_col": l_col, "close_col": c_col,
            "symbol_col": sym_col, "timeframe_col": tf_col, "selected_rows": 0,
            "h1_rows": 0, "h1_start_ts": "", "h1_end_ts": "", "h1_median_delta_min": "",
            "error": "", "columns": ";".join(cols),
        }

        if not (o_col and h_col and l_col and c_col and (ts_col or (date_col and time_col))):
            row["error"] = "missing_ohlc_or_timestamp_columns"
            audit.append(row)
            continue

        select_parts = []
        if ts_col:
            select_parts.append(f'"{ts_col}" AS ts_raw')
        else:
            select_parts.append(f'("{date_col}" || " " || "{time_col}") AS ts_raw')
        select_parts += [
            f'"{o_col}" AS open', f'"{h_col}" AS high', f'"{l_col}" AS low', f'"{c_col}" AS close'
        ]
        if sym_col:
            select_parts.append(f'"{sym_col}" AS symbol')
        if tf_col:
            select_parts.append(f'"{tf_col}" AS timeframe')
        query = f'SELECT {", ".join(select_parts)} FROM "{table}"'
        try:
            df = pd.read_sql_query(query, conn)
        except Exception as exc:
            row["error"] = f"select_failed:{type(exc).__name__}:{exc}"
            audit.append(row)
            continue

        df["ts"] = parse_ts(df["ts_raw"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["ts", "open", "high", "low", "close"])
        if "symbol" in df.columns:
            sym = df["symbol"].astype(str).str.upper()
            if sym.str.contains("XAU", regex=False).any():
                df = df[sym.str.contains("XAU", regex=False)]
        if "timeframe" in df.columns:
            tf = df["timeframe"].astype(str).str.lower()
            if tf.str.contains("1h|h1|60", regex=True).any():
                # Prefer 1h rows but do not require exact timeframe when mixed imports exist.
                df_pref = df[tf.str.contains("1h|h1|60", regex=True)]
                if len(df_pref) >= 100:
                    df = df_pref
        df = df.sort_values("ts").drop_duplicates("ts")
        row["selected_rows"] = len(df)
        if len(df) < 100:
            row["error"] = "no_valid_ohlc_rows_after_cleaning"
            audit.append(row)
            continue

        tmp = df.set_index("ts")[["open", "high", "low", "close"]].sort_index()
        # Always resample to H1; if already H1 this is a no-op aggregation.
        h1 = tmp.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        if len(h1) < 100:
            row["error"] = "not_enough_h1_rows_after_resample"
            audit.append(row)
            continue
        deltas = h1.index.to_series().diff().dropna().dt.total_seconds() / 60.0
        row["h1_rows"] = len(h1)
        row["h1_start_ts"] = str(h1.index.min())
        row["h1_end_ts"] = str(h1.index.max())
        row["h1_median_delta_min"] = float(deltas.median()) if len(deltas) else ""
        audit.append(row)
        if best is None or len(h1) > len(best):
            best = h1.reset_index().rename(columns={"ts": "utc_time"})
            best_meta = row.copy()

    if best is None:
        return pd.DataFrame(), {"error": "no_ohlc_table_found", "db_path": str(DB_PATH)}, pd.DataFrame(audit)
    return best, best_meta, pd.DataFrame(audit)


def load_events(conn: sqlite3.Connection) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[pd.DataFrame] = []
    audit: List[Dict[str, Any]] = []
    tables = set(table_names(conn))
    for table in EVENT_TABLES:
        if table not in tables:
            audit.append({"table": table, "status": "missing", "rows": 0, "event_time_col": ""})
            continue
        cols = table_columns(conn, table)
        time_col = find_col(cols, ["event_time_utc", "event_time", "time_utc", "utc_time", "timestamp", "ts"])
        title_col = find_col(cols, ["title", "label", "event_class", "event_channel", "category"])
        dir_col = find_col(cols, ["expected_gold_direction", "event_gold_bias", "direction", "bias"])
        importance_col = find_col(cols, ["initial_importance", "impact", "importance", "confidence"])
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        audit.append({"table": table, "status": "ok" if time_col else "missing_event_time", "rows": count, "event_time_col": time_col})
        if not time_col or count == 0:
            continue
        parts = [f'"{time_col}" AS event_time']
        if title_col:
            parts.append(f'"{title_col}" AS title')
        else:
            parts.append("'' AS title")
        if dir_col:
            parts.append(f'"{dir_col}" AS expected_direction')
        else:
            parts.append("'' AS expected_direction")
        if importance_col:
            parts.append(f'"{importance_col}" AS importance')
        else:
            parts.append("'' AS importance")
        try:
            df = pd.read_sql_query(f'SELECT {", ".join(parts)} FROM "{table}"', conn)
        except Exception:
            continue
        df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce", utc=True)
        df = df.dropna(subset=["event_time"])
        df["source_table"] = table
        rows.append(df)
    if not rows:
        return pd.DataFrame(columns=["event_time", "title", "expected_direction", "importance", "source_table"]), pd.DataFrame(audit)
    events = pd.concat(rows, ignore_index=True)
    events = events.sort_values("event_time").drop_duplicates(["event_time", "title", "source_table"])
    return events, pd.DataFrame(audit)


def profit_factor(vals: Iterable[float]) -> float:
    arr = np.asarray(list(vals), dtype=float)
    pos = arr[arr > 0].sum()
    neg = -arr[arr < 0].sum()
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / neg)


def max_drawdown(vals: Iterable[float]) -> float:
    arr = np.asarray(list(vals), dtype=float)
    if len(arr) == 0:
        return 0.0
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return float(dd.min())


def metrics(net: pd.Series) -> Dict[str, float]:
    arr = pd.to_numeric(net, errors="coerce").dropna().astype(float)
    if arr.empty:
        return {"signal_count": 0, "pf_x4": 0.0, "avg_net_x4": 0.0, "win_rate_x4": 0.0, "tail_pf_x4": 0.0, "recent_pf_x4": 0.0, "cost1_pf_x4": 0.0, "max_drawdown_x4": 0.0}
    cost_arr = arr - COST_PENALTY_X4
    return {
        "signal_count": int(len(arr)),
        "pf_x4": profit_factor(arr),
        "avg_net_x4": float(arr.mean()),
        "win_rate_x4": float((arr > 0).mean()),
        "tail_pf_x4": profit_factor(arr.tail(TAIL_N)),
        "recent_pf_x4": profit_factor(arr.tail(RECENT_N)),
        "cost1_pf_x4": profit_factor(cost_arr),
        "max_drawdown_x4": max_drawdown(arr),
    }


def classify(row: Dict[str, Any]) -> Tuple[str, str, str]:
    failed: List[str] = []
    if row["signal_count"] < THRESHOLDS["min_events_review"]:
        failed.append("event_count")
    if row["pf_x4"] < THRESHOLDS["min_pf_review"]:
        failed.append("pf")
    if row["avg_net_x4"] < THRESHOLDS["min_avg_review"]:
        failed.append("avg_net")
    if row["win_rate_x4"] < THRESHOLDS["min_wr_review"]:
        failed.append("win_rate")
    if row["tail_pf_x4"] < THRESHOLDS["min_tail_pf_review"]:
        failed.append("tail_pf")
    if row["cost1_pf_x4"] < THRESHOLDS["min_cost1_pf_review"]:
        failed.append("cost1_pf")
    if row["max_drawdown_x4"] < THRESHOLDS["max_drawdown_review"]:
        failed.append("drawdown")
    if row["recent_pf_x4"] < THRESHOLDS["min_recent_pf_review"]:
        failed.append("recent_pf")
    if not failed:
        return "STRICT_REVIEW_READY_RESEARCH_ONLY", "RUN_STRICT_EVENT_RISK_REVIEW_NO_EA_NO_PAPER", ""
    if row["signal_count"] >= THRESHOLDS["min_events_background"] and row["pf_x4"] >= 1.08 and row["avg_net_x4"] > 0 and row["tail_pf_x4"] >= 1.0:
        return "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY", "KEEP_BACKGROUND_ONLY_AND_RERUN_AFTER_NEW_DATA", ";".join(failed)
    return "KILL_OR_REPAIR_RESEARCH_ONLY", "MOVE_TO_NEXT_STAGE36_THESIS_BRANCH_DO_NOT_WAIT_FOR_N40", ";".join(failed)


def expected_dir_to_sign(x: Any) -> float:
    s = str(x).lower()
    if any(k in s for k in ["long", "bull", "up", "buy", "positive"]):
        return 1.0
    if any(k in s for k in ["short", "bear", "down", "sell", "negative"]):
        return -1.0
    return np.nan


def attach_event_flags(bars: pd.DataFrame, events: pd.DataFrame, guard_hours: int = 2) -> pd.DataFrame:
    out = bars.copy()
    out["event_risk"] = False
    out["nearest_event_dir"] = np.nan
    if events.empty:
        return out
    event_times = pd.to_datetime(events["event_time"], utc=True).sort_values().to_numpy(dtype="datetime64[ns]")
    bar_times = pd.to_datetime(out["utc_time"], utc=True).to_numpy(dtype="datetime64[ns]")
    # Mark risk if any event lies within +/- guard_hours.
    left = np.searchsorted(event_times, bar_times - np.timedelta64(guard_hours, "h"), side="left")
    right = np.searchsorted(event_times, bar_times + np.timedelta64(guard_hours, "h"), side="right")
    out["event_risk"] = right > left
    # nearest expected direction for event-risk rows
    events2 = events.copy().sort_values("event_time")
    events2["dir_sign"] = events2["expected_direction"].apply(expected_dir_to_sign)
    ev_df = events2.dropna(subset=["dir_sign"])
    if not ev_df.empty:
        ev_times = pd.to_datetime(ev_df["event_time"], utc=True).to_numpy(dtype="datetime64[ns]")
        dirs = ev_df["dir_sign"].to_numpy(dtype=float)
        idx = np.searchsorted(ev_times, bar_times)
        nearest = np.full(len(out), np.nan)
        for i in range(len(out)):
            cand = []
            if idx[i] > 0:
                cand.append(idx[i] - 1)
            if idx[i] < len(ev_times):
                cand.append(idx[i])
            if cand:
                diffs = [abs((bar_times[i] - ev_times[j]) / np.timedelta64(1, "h")) for j in cand]
                best = cand[int(np.argmin(diffs))]
                if diffs[int(np.argmin(diffs))] <= guard_hours:
                    nearest[i] = dirs[best]
        out["nearest_event_dir"] = nearest
    return out


def build_variant_rows(h1: pd.DataFrame, events: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = h1.copy().sort_values("utc_time")
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True)
    df["prev_ret"] = df["close"].diff()
    df["atr_proxy"] = (df["high"] - df["low"]).rolling(14, min_periods=5).mean()
    df = attach_event_flags(df, events, guard_hours=2)
    for h in [4, 8, 12]:
        df[f"fwd_ret_{h}h"] = df["close"].shift(-h) - df["close"]

    variants = []

    def add_variant(variant_id: str, thesis_family: str, mask: pd.Series, direction: pd.Series, horizon: int, diagnostic: bool = False) -> None:
        m = mask.fillna(False) & direction.notna() & df[f"fwd_ret_{horizon}h"].notna()
        tmp = df.loc[m, ["utc_time", f"fwd_ret_{horizon}h", "event_risk", "nearest_event_dir"]].copy()
        if tmp.empty:
            net = pd.Series(dtype=float)
        else:
            d = direction.loc[m].astype(float)
            # Normalize to a stable x4-like unit: raw USD move scaled down by 4. This avoids overstating H1 price moves.
            net = (d.to_numpy() * tmp[f"fwd_ret_{horizon}h"].to_numpy()) / 4.0
            tmp["net_x4"] = net
        mt = metrics(pd.Series(net))
        row = {"variant_id": variant_id, "thesis_family": thesis_family, "horizon_hours": horizon, "diagnostic_only": diagnostic, **mt}
        decision, next_action, failed = classify(row)
        if diagnostic:
            decision = "DIAGNOSTIC_ONLY_NO_PROMOTION_RESEARCH_ONLY"
            next_action = "KEEP_OUT_OF_PROMOTION_QUEUE"
        row["fatal_failed_gates"] = failed
        row["stage36c_decision"] = decision
        row["next_action"] = next_action
        variants.append(row)

    prev_sign = np.sign(df["prev_ret"].replace(0, np.nan))
    clean = ~df["event_risk"]
    risk = df["event_risk"]

    add_variant("stage36c_clean_no_news_momentum_h4_guard2", "event_risk_regime", clean, prev_sign, 4)
    add_variant("stage36c_clean_no_news_reversal_h4_guard2", "event_risk_regime", clean, -prev_sign, 4)
    add_variant("stage36c_event_window_momentum_h4_guard2", "event_risk_regime", risk, prev_sign, 4)
    add_variant("stage36c_event_window_reversal_h4_guard2", "event_risk_regime", risk, -prev_sign, 4)
    add_variant("stage36c_event_expected_direction_h4_guard2", "event_risk_regime", risk, df["nearest_event_dir"], 4)
    add_variant("stage36c_event_contra_expected_direction_h4_guard2", "event_risk_regime", risk, -df["nearest_event_dir"], 4)
    add_variant("stage36c_clean_no_news_momentum_h8_guard2", "event_risk_regime", clean, prev_sign, 8)
    add_variant("stage36c_clean_no_news_reversal_h8_guard2", "event_risk_regime", clean, -prev_sign, 8)

    # Diagnostic comparison of absolute movement/noise under event vs clean regimes.
    diag_rows = []
    for name, mask in [("event_risk", risk), ("clean_no_news", clean)]:
        tmp = df.loc[mask & df["fwd_ret_4h"].notna()].copy()
        diag_rows.append({
            "regime": name,
            "rows": int(len(tmp)),
            "avg_abs_4h_move": float(tmp["fwd_ret_4h"].abs().mean()) if len(tmp) else 0.0,
            "median_abs_4h_move": float(tmp["fwd_ret_4h"].abs().median()) if len(tmp) else 0.0,
            "avg_range": float((tmp["high"] - tmp["low"]).mean()) if len(tmp) else 0.0,
        })
    return pd.DataFrame(variants), pd.DataFrame(diag_rows), df


def write_report(summary: Dict[str, Any], audit: pd.DataFrame, event_audit: pd.DataFrame, candidates: pd.DataFrame, regime_diag: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage36C — Event Risk / No-News Guard Scout")
    lines.append(f"Generated UTC: {summary['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    for k in ["decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage"]:
        lines.append(f"{k.upper()} = {summary[k]}")
    lines.append("")
    lines.append("## Why this stage exists")
    lines.append("Stage36B found no strict session/regime review candidate and only one weak background path. Stage36C moves to the next distinct Stage36 thesis branch: event-risk versus clean/no-news regimes. This is not a continuation of h13/h14 variant mining and it authorizes no execution.")
    lines.append("")
    lines.append("## Summary")
    for k in ["stage36b_decision", "ohlc_table", "h1_rows", "event_rows", "variant_rows", "strict_review_ready_rows", "background_rows", "diagnostic_only_rows", "kill_or_repair_rows"]:
        lines.append(f"{k} = {summary[k]}")
    lines.append("")
    lines.append("## Data source audit")
    lines.append(audit.head(12).to_markdown(index=False))
    lines.append("")
    lines.append("## Event source audit")
    lines.append(event_audit.to_markdown(index=False))
    lines.append("")
    lines.append("## Event regime diagnostics")
    lines.append(regime_diag.to_markdown(index=False))
    lines.append("")
    lines.append("## Event-risk candidate summary")
    show_cols = ["variant_id", "horizon_hours", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4", "max_drawdown_x4", "fatal_failed_gates", "stage36c_decision", "next_action"]
    lines.append(candidates[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Strict review queue")
    strict = candidates[candidates["stage36c_decision"].str.contains("STRICT_REVIEW_READY", na=False)]
    lines.append("No rows." if strict.empty else strict[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Background queue")
    bg = candidates[candidates["stage36c_decision"].str.contains("BACKGROUND", na=False)]
    lines.append("No rows." if bg.empty else bg[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Kill / repair queue")
    kr = candidates[candidates["stage36c_decision"].str.contains("KILL_OR_REPAIR", na=False)]
    lines.append("No rows." if kr.empty else kr[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Operational interpretation")
    lines.append("1. If event-risk/no-news variants do not produce a strict candidate, move to the next Stage36 thesis branch quickly.")
    lines.append("2. Diagnostic-only rows must not be promoted directly.")
    lines.append("3. Stage35C remains scheduled in the background for h13/h14 forward confirmation.")
    lines.append("4. No EA, paper-live, or order transition is authorized here.")
    lines.append("")
    lines.append("## Output files")
    for fn in [
        "stage36c_event_risk_guard_scout.md", "stage36c_summary.json", "stage36c_event_source_audit.csv", "stage36c_event_regime_diagnostics.csv", "stage36c_candidate_summary.csv", "stage36c_strict_review_queue.csv", "stage36c_background_queue.csv", "stage36c_kill_or_repair_queue.csv"
    ]:
        lines.append(f"- `data/reports/stage36c_event_risk_guard_scout/{fn}`")
    (REPORT_DIR / "stage36c_event_risk_guard_scout.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_report_dir()
    generated = pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if not DB_PATH.exists():
        summary = {
            "generated_utc": generated,
            "decision": "STAGE36C_NO_LOCAL_DB_RESEARCH_ONLY",
            "execution_status": "RESEARCH_ONLY",
            "commercial_transition_authorized": False,
            "no_ea_change": True,
            "no_paper_live": True,
            "no_order_authorization": True,
            "primary_objective": "EVENT_RISK_GUARD_SCOUT_AS_DISTINCT_THESIS_BRANCH",
            "recommended_next_stage": "FIX_LOCAL_DB_PATH_OR_IMPORT_DATA",
            "stage36b_decision": "UNKNOWN",
            "ohlc_table": "", "h1_rows": 0, "event_rows": 0, "variant_rows": 0,
            "strict_review_ready_rows": 0, "background_rows": 0, "diagnostic_only_rows": 0, "kill_or_repair_rows": 0,
        }
        (REPORT_DIR / "stage36c_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    with sqlite3.connect(DB_PATH) as conn:
        h1, meta, audit = load_h1_bars(conn)
        events, event_audit = load_events(conn)

    if h1.empty:
        candidates = pd.DataFrame()
        regime_diag = pd.DataFrame()
        decision = "STAGE36C_NO_OHLC_DATA_AVAILABLE_RESEARCH_ONLY"
        recommended = "FIX_OHLC_DATA_SOURCE_BEFORE_EVENT_RISK_SCOUT"
    elif events.empty:
        candidates = pd.DataFrame()
        regime_diag = pd.DataFrame()
        decision = "STAGE36C_NO_EVENT_DATA_AVAILABLE_RESEARCH_ONLY"
        recommended = "IMPORT_OR_VALIDATE_EVENT_DATA_BEFORE_EVENT_RISK_SCOUT"
    else:
        candidates, regime_diag, enriched = build_variant_rows(h1, events)
        candidates.to_csv(REPORT_DIR / "stage36c_candidate_summary.csv", index=False)
        enriched[["utc_time", "open", "high", "low", "close", "event_risk", "nearest_event_dir"]].to_csv(REPORT_DIR / "stage36c_h1_event_flags.csv", index=False)
        strict_rows = int(candidates["stage36c_decision"].str.contains("STRICT_REVIEW_READY", na=False).sum())
        bg_rows = int(candidates["stage36c_decision"].str.contains("BACKGROUND", na=False).sum())
        if strict_rows > 0:
            decision = "STAGE36C_HAS_EVENT_RISK_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY"
            recommended = "RUN_STAGE36D_STRICT_EVENT_RISK_REVIEW_NO_EA_NO_PAPER"
        elif bg_rows > 0:
            decision = "STAGE36C_EVENT_RISK_BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"
            recommended = "KEEP_BACKGROUND_AND_MOVE_TO_NEXT_STAGE36_THESIS_BRANCH"
        else:
            decision = "STAGE36C_NO_EVENT_RISK_EDGE_RESEARCH_ONLY"
            recommended = "MOVE_TO_STAGE36D_VOLATILITY_COMPRESSION_BRANCH"

    if candidates.empty:
        candidates = pd.DataFrame(columns=["variant_id", "horizon_hours", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4", "max_drawdown_x4", "fatal_failed_gates", "stage36c_decision", "next_action"])
    if regime_diag.empty:
        regime_diag = pd.DataFrame(columns=["regime", "rows", "avg_abs_4h_move", "median_abs_4h_move", "avg_range"])

    strict = candidates[candidates["stage36c_decision"].str.contains("STRICT_REVIEW_READY", na=False)]
    bg = candidates[candidates["stage36c_decision"].str.contains("BACKGROUND", na=False)]
    diag_only = candidates[candidates["stage36c_decision"].str.contains("DIAGNOSTIC", na=False)]
    kr = candidates[candidates["stage36c_decision"].str.contains("KILL_OR_REPAIR", na=False)]

    audit.to_csv(REPORT_DIR / "stage36c_data_source_audit.csv", index=False)
    event_audit.to_csv(REPORT_DIR / "stage36c_event_source_audit.csv", index=False)
    regime_diag.to_csv(REPORT_DIR / "stage36c_event_regime_diagnostics.csv", index=False)
    candidates.to_csv(REPORT_DIR / "stage36c_candidate_summary.csv", index=False)
    strict.to_csv(REPORT_DIR / "stage36c_strict_review_queue.csv", index=False)
    bg.to_csv(REPORT_DIR / "stage36c_background_queue.csv", index=False)
    kr.to_csv(REPORT_DIR / "stage36c_kill_or_repair_queue.csv", index=False)

    summary = {
        "generated_utc": generated,
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "EVENT_RISK_NO_NEWS_GUARD_SCOUT_AS_DISTINCT_THESIS_BRANCH",
        "recommended_next_stage": recommended,
        "stage36b_decision": "STAGE36B_SESSION_REGIME_BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY",
        "db_path": str(DB_PATH),
        "ohlc_table": meta.get("table", ""),
        "h1_rows": int(len(h1)),
        "event_rows": int(len(events)),
        "variant_rows": int(len(candidates)),
        "strict_review_ready_rows": int(len(strict)),
        "background_rows": int(len(bg)),
        "diagnostic_only_rows": int(len(diag_only)),
        "kill_or_repair_rows": int(len(kr)),
        "data_source_meta": meta,
        "thresholds": {**THRESHOLDS, "cost_penalty_x4": COST_PENALTY_X4, "tail_n": TAIL_N, "recent_n": RECENT_N},
    }
    (REPORT_DIR / "stage36c_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_report(summary, audit, event_audit, candidates, regime_diag)
    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"REPORT={REPORT_DIR / 'stage36c_event_risk_guard_scout.md'}")


if __name__ == "__main__":
    main()
