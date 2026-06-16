from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

DB_PATH = Path("data/local/xauusd_local_store.sqlite")
REPORT_DIR = Path("data/reports/stage36d_volatility_compression_breakout_scout")

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
    excluded = {norm_name(x) for x in exclude if x}
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
        return "STRICT_REVIEW_READY_RESEARCH_ONLY", "RUN_STAGE36E_STRICT_VOL_COMPRESSION_REVIEW_NO_EA_NO_PAPER", ""
    if row["signal_count"] >= THRESHOLDS["min_events_background"] and row["pf_x4"] >= 1.08 and row["avg_net_x4"] > 0 and row["tail_pf_x4"] >= 1.0:
        return "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY", "KEEP_BACKGROUND_ONLY_AND_RERUN_AFTER_NEW_DATA", ";".join(failed)
    return "KILL_OR_REPAIR_RESEARCH_ONLY", "MOVE_TO_NEXT_STAGE36_THESIS_BRANCH_DO_NOT_WAIT_FOR_N40", ";".join(failed)


def add_variant(rows: List[Dict[str, Any]], df: pd.DataFrame, variant_id: str, setup: str, mask: pd.Series, direction: pd.Series, horizon: int) -> None:
    fwd_col = f"fwd_ret_{horizon}h"
    m = mask.fillna(False) & direction.notna() & df[fwd_col].notna()
    tmp = df.loc[m, ["utc_time", fwd_col]].copy()
    if tmp.empty:
        net = pd.Series(dtype=float)
    else:
        d = direction.loc[m].astype(float)
        net = pd.Series((d.to_numpy() * tmp[fwd_col].to_numpy()) / 4.0)
    mt = metrics(net)
    row = {"variant_id": variant_id, "setup": setup, "horizon_hours": horizon, **mt}
    decision, next_action, failed = classify(row)
    row["fatal_failed_gates"] = failed
    row["stage36d_decision"] = decision
    row["next_action"] = next_action
    rows.append(row)


def build_variants(h1: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = h1.copy().sort_values("utc_time")
    df["utc_time"] = pd.to_datetime(df["utc_time"], utc=True)
    df["range"] = df["high"] - df["low"]
    df["body"] = df["close"] - df["open"]
    df["prev_ret"] = df["close"].diff()
    df["range_q20_250"] = df["range"].rolling(250, min_periods=100).quantile(0.20)
    df["range_q30_250"] = df["range"].rolling(250, min_periods=100).quantile(0.30)
    df["range_med_250"] = df["range"].rolling(250, min_periods=100).median()
    df["comp_q20_prev"] = df["range"].shift(1) <= df["range_q20_250"].shift(1)
    df["comp_q30_prev"] = df["range"].shift(1) <= df["range_q30_250"].shift(1)
    for w in [8, 12, 24]:
        df[f"prev_high_{w}"] = df["high"].shift(1).rolling(w, min_periods=max(3, w // 2)).max()
        df[f"prev_low_{w}"] = df["low"].shift(1).rolling(w, min_periods=max(3, w // 2)).min()
    for h in [4, 8, 12]:
        df[f"fwd_ret_{h}h"] = df["close"].shift(-h) - df["close"]

    rows: List[Dict[str, Any]] = []

    # Breakout after compression: direction only when current close breaks prior range.
    for qname, comp_col in [("q20", "comp_q20_prev"), ("q30", "comp_q30_prev")]:
        for w in [8, 12, 24]:
            up = df["close"] > df[f"prev_high_{w}"]
            down = df["close"] < df[f"prev_low_{w}"]
            direction = pd.Series(np.where(up, 1.0, np.where(down, -1.0, np.nan)), index=df.index)
            mask = df[comp_col] & (up | down)
            for horizon in [4, 8]:
                add_variant(rows, df, f"stage36d_comp_{qname}_breakout_follow_w{w}_h{horizon}", "compression_breakout_follow", mask, direction, horizon)
                add_variant(rows, df, f"stage36d_comp_{qname}_breakout_fade_w{w}_h{horizon}", "compression_breakout_fade", mask, -direction, horizon)

    # Expansion after compression: current range expands after compressed prior bar, direction follows/fades candle body.
    for qname, comp_col in [("q20", "comp_q20_prev"), ("q30", "comp_q30_prev")]:
        expansion = df["range"] > df["range_med_250"]
        body_dir = pd.Series(np.sign(df["body"].replace(0, np.nan)), index=df.index)
        mask = df[comp_col] & expansion
        for horizon in [4, 8, 12]:
            add_variant(rows, df, f"stage36d_comp_{qname}_range_expansion_follow_body_h{horizon}", "compression_range_expansion_follow", mask, body_dir, horizon)
            add_variant(rows, df, f"stage36d_comp_{qname}_range_expansion_fade_body_h{horizon}", "compression_range_expansion_fade", mask, -body_dir, horizon)

    diag = []
    for label, mask in [("compression_q20_prev", df["comp_q20_prev"]), ("compression_q30_prev", df["comp_q30_prev"]), ("non_compression", ~(df["comp_q30_prev"].fillna(False)) )]:
        tmp = df.loc[mask.fillna(False) & df["fwd_ret_4h"].notna()].copy()
        diag.append({
            "state": label,
            "rows": int(len(tmp)),
            "avg_abs_4h_move": float(tmp["fwd_ret_4h"].abs().mean()) if len(tmp) else 0.0,
            "median_abs_4h_move": float(tmp["fwd_ret_4h"].abs().median()) if len(tmp) else 0.0,
            "avg_range": float(tmp["range"].mean()) if len(tmp) else 0.0,
        })
    return pd.DataFrame(rows), pd.DataFrame(diag)


def write_report(summary: Dict[str, Any], audit: pd.DataFrame, candidates: pd.DataFrame, state_diag: pd.DataFrame) -> None:
    lines: List[str] = []
    lines.append("# XAUUSD Stage36D — Volatility Compression Breakout Scout")
    lines.append(f"Generated UTC: {summary['generated_utc']}")
    lines.append("")
    lines.append("## Decision")
    for k in ["decision", "execution_status", "commercial_transition_authorized", "no_ea_change", "no_paper_live", "no_order_authorization", "primary_objective", "recommended_next_stage"]:
        lines.append(f"{k.upper()} = {summary[k]}")
    lines.append("")
    lines.append("## Why this stage exists")
    lines.append("Stage36B and Stage36C found no strict review candidate in session/regime or event-risk branches. Stage36D starts the next distinct thesis: ATR/range compression followed by breakout, fade, or range expansion. This is not a continuation of h13/h14 variant mining and authorizes no execution.")
    lines.append("")
    lines.append("## Summary")
    for k in ["stage36c_decision", "ohlc_table", "h1_rows", "variant_rows", "strict_review_ready_rows", "background_rows", "kill_or_repair_rows"]:
        lines.append(f"{k} = {summary[k]}")
    lines.append("")
    lines.append("## Data source audit")
    lines.append(audit.head(8).to_markdown(index=False))
    lines.append("")
    lines.append("## Compression state diagnostics")
    lines.append(state_diag.to_markdown(index=False))
    lines.append("")
    lines.append("## Volatility compression candidate summary")
    show_cols = ["variant_id", "setup", "horizon_hours", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4", "max_drawdown_x4", "fatal_failed_gates", "stage36d_decision", "next_action"]
    lines.append(candidates[show_cols].sort_values(["stage36d_decision", "pf_x4"], ascending=[True, False]).to_markdown(index=False))
    lines.append("")
    lines.append("## Strict review queue")
    strict = candidates[candidates["stage36d_decision"].str.contains("STRICT_REVIEW_READY", na=False)]
    lines.append("No rows." if strict.empty else strict[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Background queue")
    bg = candidates[candidates["stage36d_decision"].str.contains("BACKGROUND", na=False)]
    lines.append("No rows." if bg.empty else bg[show_cols].to_markdown(index=False))
    lines.append("")
    lines.append("## Kill / repair queue")
    kr = candidates[candidates["stage36d_decision"].str.contains("KILL_OR_REPAIR", na=False)]
    lines.append("No rows." if kr.empty else kr[show_cols].head(30).to_markdown(index=False))
    lines.append("")
    lines.append("## Operational interpretation")
    lines.append("1. If no strict review candidate exists, do not mine unlimited compression variants inside this branch.")
    lines.append("2. Background rows can remain cheap monitors only; they do not authorize EA, paper-live, or orders.")
    lines.append("3. Stage35C remains scheduled in the background for h13/h14 forward confirmation.")
    lines.append("4. If this branch fails, move to the next Stage36 thesis branch: market-structure sweep/reclaim.")
    lines.append("")
    lines.append("## Output files")
    for fn in [
        "stage36d_volatility_compression_breakout_scout.md", "stage36d_summary.json", "stage36d_data_source_audit.csv", "stage36d_compression_state_diagnostics.csv", "stage36d_candidate_summary.csv", "stage36d_strict_review_queue.csv", "stage36d_background_queue.csv", "stage36d_kill_or_repair_queue.csv"
    ]:
        lines.append(f"- `data/reports/stage36d_volatility_compression_breakout_scout/{fn}`")
    (REPORT_DIR / "stage36d_volatility_compression_breakout_scout.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_report_dir()
    generated = pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    stage36c_summary_path = Path("data/reports/stage36c_event_risk_guard_scout/stage36c_summary.json")
    stage36c_decision = "UNKNOWN"
    if stage36c_summary_path.exists():
        try:
            stage36c_decision = json.loads(stage36c_summary_path.read_text(encoding="utf-8")).get("decision", "UNKNOWN")
        except Exception:
            stage36c_decision = "UNKNOWN"

    if not DB_PATH.exists():
        summary = {
            "generated_utc": generated, "decision": "STAGE36D_NO_LOCAL_DB_RESEARCH_ONLY", "execution_status": "RESEARCH_ONLY",
            "commercial_transition_authorized": False, "no_ea_change": True, "no_paper_live": True, "no_order_authorization": True,
            "primary_objective": "VOLATILITY_COMPRESSION_BREAKOUT_SCOUT_AS_DISTINCT_THESIS_BRANCH",
            "recommended_next_stage": "FIX_LOCAL_DB_PATH_OR_IMPORT_DATA", "stage36c_decision": stage36c_decision,
            "ohlc_table": "", "h1_rows": 0, "variant_rows": 0, "strict_review_ready_rows": 0, "background_rows": 0, "kill_or_repair_rows": 0,
            "thresholds": THRESHOLDS,
        }
        (REPORT_DIR / "stage36d_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    with sqlite3.connect(DB_PATH) as conn:
        h1, meta, audit = load_h1_bars(conn)

    if h1.empty:
        candidates = pd.DataFrame(columns=["variant_id", "setup", "horizon_hours", "signal_count", "pf_x4", "avg_net_x4", "win_rate_x4", "tail_pf_x4", "recent_pf_x4", "cost1_pf_x4", "max_drawdown_x4", "fatal_failed_gates", "stage36d_decision", "next_action"])
        state_diag = pd.DataFrame(columns=["state", "rows", "avg_abs_4h_move", "median_abs_4h_move", "avg_range"])
        decision = "STAGE36D_NO_OHLC_DATA_AVAILABLE_RESEARCH_ONLY"
        recommended = "FIX_OHLC_DATA_SOURCE_BEFORE_VOL_COMPRESSION_SCOUT"
    else:
        candidates, state_diag = build_variants(h1)
        strict_rows = int(candidates["stage36d_decision"].str.contains("STRICT_REVIEW_READY", na=False).sum())
        bg_rows = int(candidates["stage36d_decision"].str.contains("BACKGROUND", na=False).sum())
        if strict_rows > 0:
            decision = "STAGE36D_HAS_VOL_COMPRESSION_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY"
            recommended = "RUN_STAGE36E_STRICT_VOL_COMPRESSION_REVIEW_NO_EA_NO_PAPER"
        elif bg_rows > 0:
            decision = "STAGE36D_VOL_COMPRESSION_BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"
            recommended = "KEEP_BACKGROUND_AND_MOVE_TO_NEXT_STAGE36_THESIS_BRANCH"
        else:
            decision = "STAGE36D_NO_VOL_COMPRESSION_EDGE_RESEARCH_ONLY"
            recommended = "MOVE_TO_STAGE36E_STRUCTURE_SWEEP_RECLAIM_BRANCH"

    strict = candidates[candidates["stage36d_decision"].str.contains("STRICT_REVIEW_READY", na=False)]
    bg = candidates[candidates["stage36d_decision"].str.contains("BACKGROUND", na=False)]
    kr = candidates[candidates["stage36d_decision"].str.contains("KILL_OR_REPAIR", na=False)]

    audit.to_csv(REPORT_DIR / "stage36d_data_source_audit.csv", index=False)
    candidates.to_csv(REPORT_DIR / "stage36d_candidate_summary.csv", index=False)
    state_diag.to_csv(REPORT_DIR / "stage36d_compression_state_diagnostics.csv", index=False)
    strict.to_csv(REPORT_DIR / "stage36d_strict_review_queue.csv", index=False)
    bg.to_csv(REPORT_DIR / "stage36d_background_queue.csv", index=False)
    kr.to_csv(REPORT_DIR / "stage36d_kill_or_repair_queue.csv", index=False)

    summary = {
        "generated_utc": generated,
        "decision": decision,
        "execution_status": "RESEARCH_ONLY",
        "commercial_transition_authorized": False,
        "no_ea_change": True,
        "no_paper_live": True,
        "no_order_authorization": True,
        "primary_objective": "VOLATILITY_COMPRESSION_BREAKOUT_SCOUT_AS_DISTINCT_THESIS_BRANCH",
        "recommended_next_stage": recommended,
        "stage36c_decision": stage36c_decision,
        "db_path": str(DB_PATH),
        "ohlc_table": meta.get("table", ""),
        "h1_rows": int(len(h1)) if not h1.empty else 0,
        "variant_rows": int(len(candidates)),
        "strict_review_ready_rows": int(len(strict)),
        "background_rows": int(len(bg)),
        "kill_or_repair_rows": int(len(kr)),
        "data_source_meta": meta,
        "thresholds": THRESHOLDS,
    }
    (REPORT_DIR / "stage36d_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_report(summary, audit, candidates, state_diag)
    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"H1_ROWS={summary['h1_rows']}")
    print(f"STRICT_REVIEW_READY_ROWS={len(strict)}")
    print(f"BACKGROUND_ROWS={len(bg)}")


if __name__ == "__main__":
    main()
