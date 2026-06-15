#!/usr/bin/env python3
"""Stage36B — Session / Regime Baseline Scout.

HF3: robust OHLC source detection and schema audit.

This module intentionally avoids changing EA/paper/live behavior. It only reads the
local SQLite store, builds an H1 OHLC frame when possible, evaluates a small set of
session/regime baselines, and writes research-only reports.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

DB_PATH = Path("data/local/xauusd_local_store.sqlite")
OUT_DIR = Path("data/reports/stage36b_session_regime_baseline_scout")

EXECUTION_STATUS = "RESEARCH_ONLY"
COMMERCIAL_TRANSITION_AUTHORIZED = False
NO_EA_CHANGE = True
NO_PAPER_LIVE = True
NO_ORDER_AUTHORIZATION = True

MIN_EVENTS_REVIEW = 40
MIN_EVENTS_BACKGROUND = 25
MIN_PF_REVIEW = 1.25
MIN_AVG_REVIEW = 0.15
MIN_WR_REVIEW = 0.52
MIN_TAIL_PF_REVIEW = 1.0
MIN_COST1_PF_REVIEW = 1.05
MAX_DRAWDOWN_REVIEW = -45.0
MIN_RECENT_PF_REVIEW = 1.0
COST_PENALTY_X4 = 1.0
TAIL_N = 20
RECENT_N = 20

# Do not treat these as time columns even though they contain "time".
TIMESTAMP_EXCLUDE_EXACT = {
    "timeframe",
    "tf",
    "period",
    "interval",
    "source_timeframe",
    "bar_timeframe",
    "time_frame",
}
TIMESTAMP_EXCLUDE_CONTAINS = ("timeframe", "time_frame", "interval", "period")

TIMESTAMP_EXACT_PRIORITY = [
    "ts",
    "timestamp",
    "datetime",
    "date_time",
    "datetime_utc",
    "time_utc",
    "utc_time",
    "utc_datetime",
    "bar_time_utc",
    "candle_time_utc",
    "open_time_utc",
    "entry_time",
    "event_time_utc",
    "time",
    "date",
    "open_time",
    "candle_time",
    "bar_time",
]
TIMESTAMP_CONTAINS_PRIORITY = (
    "timestamp",
    "datetime",
    "utc_time",
    "time_utc",
    "open_time",
    "candle_time",
    "bar_time",
)

OPEN_ALIASES = ["open", "o", "open_price", "bid_open", "ask_open"]
HIGH_ALIASES = ["high", "h", "high_price", "bid_high", "ask_high"]
LOW_ALIASES = ["low", "l", "low_price", "bid_low", "ask_low"]
CLOSE_ALIASES = ["close", "c", "close_price", "bid_close", "ask_close", "last"]
SYMBOL_ALIASES = ["symbol", "ticker", "instrument", "market"]
TIMEFRAME_ALIASES = ["timeframe", "tf", "period", "interval", "source_timeframe"]


@dataclass
class SourceMeta:
    db_path: str
    table: str = ""
    source_rows: int = 0
    timestamp_col: str = ""
    date_col: str = ""
    time_col: str = ""
    open_col: str = ""
    high_col: str = ""
    low_col: str = ""
    close_col: str = ""
    symbol_col: str = ""
    timeframe_col: str = ""
    selected_rows: int = 0
    h1_rows: int = 0
    h1_start_ts: str = ""
    h1_end_ts: str = ""
    h1_median_delta_min: float | str = ""
    error: str = ""
    columns: str = ""
    sample_row_json: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows if r and r[0] and not str(r[0]).startswith("sqlite_")]


def get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    return [r[1] for r in rows]


def get_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {qident(table)}").fetchone()[0])
    except Exception:
        return 0


def sample_row(conn: sqlite3.Connection, table: str, columns: list[str]) -> str:
    try:
        row = conn.execute(f"SELECT * FROM {qident(table)} LIMIT 1").fetchone()
        if row is None:
            return ""
        data = {c: row[i] for i, c in enumerate(columns[: len(row)])}
        return json.dumps(data, ensure_ascii=False, default=str)[:2000]
    except Exception as exc:
        return json.dumps({"sample_error": str(exc)}, ensure_ascii=False)[:2000]


def normalize_col_map(columns: list[str]) -> dict[str, str]:
    return {c.lower().strip(): c for c in columns}


def pick_alias(columns: list[str], aliases: Iterable[str]) -> str:
    cmap = normalize_col_map(columns)
    for alias in aliases:
        key = alias.lower().strip()
        if key in cmap:
            return cmap[key]
    # Conservative contains fallback only for OHLC price names.
    for alias in aliases:
        key = alias.lower().strip()
        for lower, original in cmap.items():
            if lower == key or lower.endswith("_" + key) or lower.startswith(key + "_"):
                return original
    return ""


def is_bad_timestamp_name(name: str) -> bool:
    n = name.lower().strip()
    if n in TIMESTAMP_EXCLUDE_EXACT:
        return True
    return any(piece in n for piece in TIMESTAMP_EXCLUDE_CONTAINS)


def pick_timestamp_col(columns: list[str]) -> str:
    cmap = normalize_col_map(columns)
    # Exact only, excluding timeframe-like fields.
    for alias in TIMESTAMP_EXACT_PRIORITY:
        key = alias.lower().strip()
        if key in cmap and not is_bad_timestamp_name(cmap[key]):
            return cmap[key]
    # Conservative contains fallback.
    for piece in TIMESTAMP_CONTAINS_PRIORITY:
        for lower, original in cmap.items():
            if is_bad_timestamp_name(original):
                continue
            if piece in lower:
                return original
    return ""


def pick_date_time_pair(columns: list[str]) -> tuple[str, str]:
    cmap = normalize_col_map(columns)
    date_col = ""
    time_col = ""
    for cand in ("date", "day", "trade_date", "bar_date"):
        if cand in cmap:
            date_col = cmap[cand]
            break
    for cand in ("time", "clock", "bar_clock"):
        if cand in cmap and not is_bad_timestamp_name(cmap[cand]):
            time_col = cmap[cand]
            break
    if date_col and time_col and date_col != time_col:
        return date_col, time_col
    return "", ""


def coerce_ts(series: pd.Series) -> pd.Series:
    # First try direct datetime parsing.
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    good_ratio = float(parsed.notna().mean()) if len(parsed) else 0.0
    if good_ratio >= 0.50:
        return parsed

    # Try numeric epoch seconds/milliseconds/microseconds/nanoseconds.
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() < 0.50:
        return parsed
    med = float(numeric.dropna().median()) if numeric.notna().any() else 0.0
    unit = "s"
    if med > 1e17:
        unit = "ns"
    elif med > 1e14:
        unit = "us"
    elif med > 1e11:
        unit = "ms"
    else:
        unit = "s"
    return pd.to_datetime(numeric, errors="coerce", utc=True, unit=unit)


def to_float(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = series.astype(str).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False)
    return pd.to_numeric(series, errors="coerce")


def build_select_sql(table: str, ts_col: str, open_col: str, high_col: str, low_col: str, close_col: str, symbol_col: str, timeframe_col: str, date_col: str = "", time_col: str = "") -> str:
    selects: list[str] = []
    if ts_col:
        selects.append(f"{qident(ts_col)} AS ts")
    elif date_col and time_col:
        selects.append(f"({qident(date_col)} || ' ' || {qident(time_col)}) AS ts")
    else:
        raise ValueError("missing timestamp column")
    selects.extend([
        f"{qident(open_col)} AS open",
        f"{qident(high_col)} AS high",
        f"{qident(low_col)} AS low",
        f"{qident(close_col)} AS close",
    ])
    if symbol_col:
        selects.append(f"{qident(symbol_col)} AS symbol")
    else:
        selects.append("NULL AS symbol")
    if timeframe_col:
        selects.append(f"{qident(timeframe_col)} AS timeframe")
    else:
        selects.append("NULL AS timeframe")
    return f"SELECT {', '.join(selects)} FROM {qident(table)}"


def clean_ohlc(df: pd.DataFrame, symbol_filter: str = "XAUUSD") -> pd.DataFrame:
    if df.empty or "ts" not in df.columns:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "symbol", "timeframe"])
    out = df.copy()
    out["ts"] = coerce_ts(out["ts"])
    for c in ["open", "high", "low", "close"]:
        out[c] = to_float(out[c])
    if "symbol" not in out.columns:
        out["symbol"] = ""
    if "timeframe" not in out.columns:
        out["timeframe"] = ""
    out = out.dropna(subset=["ts", "open", "high", "low", "close"])
    # Avoid impossible OHLC rows.
    out = out[(out["high"] >= out[["open", "close", "low"]].max(axis=1)) & (out["low"] <= out[["open", "close", "high"]].min(axis=1))]
    if symbol_filter and out["symbol"].notna().any():
        sym = out["symbol"].astype(str).str.upper()
        mask = sym.str.contains(symbol_filter.upper(), regex=False) | sym.eq("") | sym.eq("NONE") | sym.eq("NAN")
        if int(mask.sum()) > 0:
            out = out[mask]
    out = out.sort_values("ts").drop_duplicates(subset=["ts"], keep="last").reset_index(drop=True)
    return out


def infer_median_delta_min(df: pd.DataFrame) -> float:
    if df.empty or len(df) < 3:
        return math.nan
    diffs = df["ts"].sort_values().diff().dropna().dt.total_seconds() / 60.0
    if diffs.empty:
        return math.nan
    # remove zero duplicates/outliers before median.
    diffs = diffs[(diffs > 0) & (diffs < 7 * 24 * 60)]
    if diffs.empty:
        return math.nan
    return float(diffs.median())


def to_h1(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close"])
    x = df[["ts", "open", "high", "low", "close"]].copy()
    x = x.sort_values("ts").set_index("ts")
    h1 = x.resample("1h", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    h1 = h1.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return h1


def load_best_ohlc_source(db_path: Path) -> tuple[pd.DataFrame, SourceMeta, list[dict[str, Any]]]:
    audit: list[dict[str, Any]] = []
    best_h1 = pd.DataFrame(columns=["ts", "open", "high", "low", "close"])
    best_meta = SourceMeta(db_path=str(db_path), error="no_ohlc_table_found")
    if not db_path.exists():
        best_meta.error = "db_not_found"
        return best_h1, best_meta, audit

    conn = sqlite3.connect(str(db_path))
    try:
        for table in list_tables(conn):
            columns = get_columns(conn, table)
            count = get_count(conn, table)
            meta = SourceMeta(db_path=str(db_path), table=table, source_rows=count, columns=";".join(columns), sample_row_json=sample_row(conn, table, columns))
            open_col = pick_alias(columns, OPEN_ALIASES)
            high_col = pick_alias(columns, HIGH_ALIASES)
            low_col = pick_alias(columns, LOW_ALIASES)
            close_col = pick_alias(columns, CLOSE_ALIASES)
            symbol_col = pick_alias(columns, SYMBOL_ALIASES)
            timeframe_col = pick_alias(columns, TIMEFRAME_ALIASES)
            ts_col = pick_timestamp_col(columns)
            date_col, time_col = ("", "") if ts_col else pick_date_time_pair(columns)
            meta.timestamp_col = ts_col
            meta.date_col = date_col
            meta.time_col = time_col
            meta.open_col = open_col
            meta.high_col = high_col
            meta.low_col = low_col
            meta.close_col = close_col
            meta.symbol_col = symbol_col
            meta.timeframe_col = timeframe_col

            if not all([open_col, high_col, low_col, close_col]) or not (ts_col or (date_col and time_col)):
                meta.error = "missing_ohlc_or_timestamp_columns"
                audit.append(meta.__dict__.copy())
                continue

            try:
                sql = build_select_sql(table, ts_col, open_col, high_col, low_col, close_col, symbol_col, timeframe_col, date_col, time_col)
                raw = pd.read_sql_query(sql, conn)
                cleaned = clean_ohlc(raw)
                meta.selected_rows = int(len(cleaned))
                if cleaned.empty:
                    meta.error = "no_valid_ohlc_rows_after_cleaning"
                    audit.append(meta.__dict__.copy())
                    continue
                h1 = to_h1(cleaned)
                meta.h1_rows = int(len(h1))
                meta.h1_start_ts = str(h1["ts"].min()) if not h1.empty else ""
                meta.h1_end_ts = str(h1["ts"].max()) if not h1.empty else ""
                meta.h1_median_delta_min = infer_median_delta_min(h1)
                meta.error = "" if not h1.empty else "no_h1_rows_after_resample"
                audit.append(meta.__dict__.copy())
                if len(h1) > len(best_h1):
                    best_h1 = h1
                    best_meta = meta
            except Exception as exc:
                meta.error = f"load_error:{type(exc).__name__}:{exc}"
                audit.append(meta.__dict__.copy())
    finally:
        conn.close()

    if best_h1.empty and not best_meta.table:
        best_meta.error = "no_ohlc_table_found"
    return best_h1, best_meta, audit


def add_atr(h1: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    x = h1.copy().sort_values("ts").reset_index(drop=True)
    prev_close = x["close"].shift(1)
    tr = pd.concat([
        (x["high"] - x["low"]).abs(),
        (x["high"] - prev_close).abs(),
        (x["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    x["atr"] = tr.rolling(period, min_periods=max(3, period // 2)).mean()
    return x


def profit_factor(vals: pd.Series | list[float]) -> float:
    s = pd.Series(vals, dtype="float64").dropna()
    gains = float(s[s > 0].sum())
    losses = float(-s[s < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def max_drawdown(vals: pd.Series | list[float]) -> float:
    s = pd.Series(vals, dtype="float64").fillna(0.0)
    if s.empty:
        return 0.0
    eq = s.cumsum()
    dd = eq - eq.cummax()
    return float(dd.min())


def summarize_returns(returns: list[float], cost_penalty_x4: float = 0.0, tail_n: int = TAIL_N, recent_n: int = RECENT_N) -> dict[str, float]:
    s = pd.Series(returns, dtype="float64").dropna()
    if cost_penalty_x4:
        s = s - float(cost_penalty_x4)
    if s.empty:
        return {"signal_count": 0, "pf_x4": 0.0, "avg_net_x4": 0.0, "win_rate_x4": 0.0, "tail_pf_x4": 0.0, "recent_pf_x4": 0.0, "max_drawdown_x4": 0.0}
    return {
        "signal_count": int(len(s)),
        "pf_x4": float(profit_factor(s)),
        "avg_net_x4": float(s.mean()),
        "win_rate_x4": float((s > 0).mean()),
        "tail_pf_x4": float(profit_factor(s.tail(tail_n))),
        "recent_pf_x4": float(profit_factor(s.tail(recent_n))),
        "max_drawdown_x4": float(max_drawdown(s)),
    }


def x4_return(entry: float, exit_: float, atr: float, direction: int, atr_mult: float = 0.75) -> float:
    if not np.isfinite(entry) or not np.isfinite(exit_) or not np.isfinite(atr) or atr <= 0:
        return float("nan")
    # x4 means normalized return scaled by 4 units, consistent with prior reports.
    return float(direction * (exit_ - entry) / max(atr * atr_mult, 1e-9) * 4.0)


def generate_session_events(h1: pd.DataFrame) -> pd.DataFrame:
    if h1.empty:
        return pd.DataFrame()
    x = add_atr(h1)
    x["hour"] = x["ts"].dt.hour
    x["date"] = x["ts"].dt.date
    variants = [
        ("stage36b_london_open_continuation_h4_atr075", "london_open", "continuation", 8, 4),
        ("stage36b_london_open_reversal_h4_atr075", "london_open", "reversal", 8, 4),
        ("stage36b_ny_open_continuation_h4_atr075", "ny_open", "continuation", 13, 4),
        ("stage36b_ny_open_reversal_h4_atr075", "ny_open", "reversal", 13, 4),
        ("stage36b_ny_late_reversal_h8_atr075", "ny_late", "reversal", 18, 8),
        ("stage36b_ny_late_continuation_h8_atr075", "ny_late", "continuation", 18, 8),
    ]
    rows: list[dict[str, Any]] = []
    # Use previous H1 bar direction as the impulse around session open.
    for i in range(1, len(x)):
        row = x.iloc[i]
        hour = int(row["hour"])
        for variant_id, family, mode, signal_hour, horizon in variants:
            if hour != signal_hour:
                continue
            exit_i = i + horizon
            if exit_i >= len(x):
                continue
            impulse = np.sign(float(x.iloc[i]["close"] - x.iloc[i - 1]["close"]))
            if impulse == 0:
                continue
            direction = int(impulse if mode == "continuation" else -impulse)
            ret = x4_return(float(row["close"]), float(x.iloc[exit_i]["close"]), float(row["atr"]), direction)
            if not np.isfinite(ret):
                continue
            rows.append({
                "variant_id": variant_id,
                "session_family": family,
                "direction_mode": mode,
                "horizon_hours": horizon,
                "entry_ts": row["ts"],
                "exit_ts": x.iloc[exit_i]["ts"],
                "direction": direction,
                "net_x4": ret,
            })
    return pd.DataFrame(rows)


def evaluate_events(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    variants = [
        ("stage36b_london_open_continuation_h4_atr075", "london_open", "continuation", 4),
        ("stage36b_london_open_reversal_h4_atr075", "london_open", "reversal", 4),
        ("stage36b_ny_open_continuation_h4_atr075", "ny_open", "continuation", 4),
        ("stage36b_ny_open_reversal_h4_atr075", "ny_open", "reversal", 4),
        ("stage36b_ny_late_reversal_h8_atr075", "ny_late", "reversal", 8),
        ("stage36b_ny_late_continuation_h8_atr075", "ny_late", "continuation", 8),
    ]
    rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []
    for variant_id, family, mode, horizon in variants:
        subset = events[events["variant_id"] == variant_id] if not events.empty else pd.DataFrame()
        vals = subset["net_x4"].tolist() if not subset.empty else []
        base = summarize_returns(vals)
        cost = summarize_returns(vals, cost_penalty_x4=COST_PENALTY_X4)
        row = {
            "variant_id": variant_id,
            "session_family": family,
            "direction_mode": mode,
            "horizon_hours": horizon,
            "signal_count": base["signal_count"],
            "pf_x4": base["pf_x4"],
            "avg_net_x4": base["avg_net_x4"],
            "win_rate_x4": base["win_rate_x4"],
            "tail_pf_x4": base["tail_pf_x4"],
            "recent_pf_x4": base["recent_pf_x4"],
            "cost1_pf_x4": cost["pf_x4"],
            "max_drawdown_x4": base["max_drawdown_x4"],
        }
        checks = [
            ("event_count", row["signal_count"], MIN_EVENTS_REVIEW, row["signal_count"] >= MIN_EVENTS_REVIEW),
            ("pf", row["pf_x4"], MIN_PF_REVIEW, row["pf_x4"] >= MIN_PF_REVIEW),
            ("avg_net", row["avg_net_x4"], MIN_AVG_REVIEW, row["avg_net_x4"] >= MIN_AVG_REVIEW),
            ("win_rate", row["win_rate_x4"], MIN_WR_REVIEW, row["win_rate_x4"] >= MIN_WR_REVIEW),
            ("tail_pf", row["tail_pf_x4"], MIN_TAIL_PF_REVIEW, row["tail_pf_x4"] >= MIN_TAIL_PF_REVIEW),
            ("cost1_pf", row["cost1_pf_x4"], MIN_COST1_PF_REVIEW, row["cost1_pf_x4"] >= MIN_COST1_PF_REVIEW),
            ("drawdown", row["max_drawdown_x4"], MAX_DRAWDOWN_REVIEW, row["max_drawdown_x4"] >= MAX_DRAWDOWN_REVIEW),
            ("recent_pf", row["recent_pf_x4"], MIN_RECENT_PF_REVIEW, row["recent_pf_x4"] >= MIN_RECENT_PF_REVIEW),
        ]
        failed = [name for name, _, _, passed in checks if not passed]
        for name, value, threshold, passed in checks:
            gate_rows.append({"variant_id": variant_id, "gate": name, "value": value, "threshold": threshold, "passed": bool(passed)})
        row["fatal_failed_gates"] = ";".join(failed)
        if not failed:
            row["stage36b_decision"] = "STRICT_REVIEW_READY_RESEARCH_ONLY"
            row["next_action"] = "RUN_STAGE36C_STRICT_SESSION_REGIME_REVIEW_NO_EA_NO_PAPER"
        elif row["signal_count"] >= MIN_EVENTS_BACKGROUND and row["pf_x4"] >= 1.05 and row["avg_net_x4"] >= 0.0:
            row["stage36b_decision"] = "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"
            row["next_action"] = "KEEP_BACKGROUND_ONLY_AND_RERUN_AFTER_NEW_DATA"
        else:
            row["stage36b_decision"] = "KILL_OR_REPAIR_RESEARCH_ONLY"
            row["next_action"] = "MOVE_TO_NEXT_STAGE36_THESIS_BRANCH_DO_NOT_WAIT_FOR_N40"
        rows.append(row)
    summary = pd.DataFrame(rows)
    gates = pd.DataFrame(gate_rows)
    strict = summary[summary["stage36b_decision"] == "STRICT_REVIEW_READY_RESEARCH_ONLY"].copy()
    background = summary[summary["stage36b_decision"] == "BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"].copy()
    kill = summary[summary["stage36b_decision"] == "KILL_OR_REPAIR_RESEARCH_ONLY"].copy()
    return summary, gates, strict, background, kill


def write_outputs(h1: pd.DataFrame, meta: SourceMeta, audit: list[dict[str, Any]], events: pd.DataFrame, candidate_summary: pd.DataFrame, gates: pd.DataFrame, strict: pd.DataFrame, background: pd.DataFrame, kill: pd.DataFrame) -> None:
    ensure_out_dir()
    generated = utc_now_iso()
    h1_rows = int(len(h1))
    event_rows = int(len(events))
    if h1_rows == 0:
        decision = "STAGE36B_NO_OHLC_DATA_AVAILABLE_RESEARCH_ONLY"
        recommended = "FIX_OHLC_DATA_SOURCE_OR_IMPORT_AMARKETS_HISTORY_BEFORE_SESSION_SCOUT"
    elif len(strict) > 0:
        decision = "STAGE36B_HAS_SESSION_REGIME_STRICT_REVIEW_CANDIDATE_RESEARCH_ONLY"
        recommended = "RUN_STAGE36C_STRICT_SESSION_REGIME_REVIEW_NO_EA_NO_PAPER"
    elif len(background) > 0:
        decision = "STAGE36B_SESSION_REGIME_BACKGROUND_ACCELERATION_ONLY_RESEARCH_ONLY"
        recommended = "KEEP_BACKGROUND_AND_MOVE_TO_NEXT_STAGE36_THESIS_BRANCH"
    else:
        decision = "STAGE36B_NO_SESSION_REGIME_EDGE_RESEARCH_ONLY"
        recommended = "MOVE_TO_NEXT_STAGE36_THESIS_BRANCH_DO_NOT_WAIT_FOR_N40"

    audit_df = pd.DataFrame(audit)
    audit_df.to_csv(OUT_DIR / "stage36b_data_source_audit.csv", index=False)
    h1.to_csv(OUT_DIR / "stage36b_h1_ohlc.csv", index=False)
    events.to_csv(OUT_DIR / "stage36b_session_regime_events.csv", index=False)
    candidate_summary.to_csv(OUT_DIR / "stage36b_session_regime_candidate_summary.csv", index=False)
    gates.to_csv(OUT_DIR / "stage36b_variant_gate_checks.csv", index=False)
    strict.to_csv(OUT_DIR / "stage36b_strict_review_queue.csv", index=False)
    background.to_csv(OUT_DIR / "stage36b_background_queue.csv", index=False)
    kill.to_csv(OUT_DIR / "stage36b_kill_or_repair_queue.csv", index=False)

    summary = {
        "generated_utc": generated,
        "decision": decision,
        "execution_status": EXECUTION_STATUS,
        "commercial_transition_authorized": COMMERCIAL_TRANSITION_AUTHORIZED,
        "no_ea_change": NO_EA_CHANGE,
        "no_paper_live": NO_PAPER_LIVE,
        "no_order_authorization": NO_ORDER_AUTHORIZATION,
        "primary_objective": "SESSION_REGIME_BASELINE_SCOUT_AS_DISTINCT_THESIS_BRANCH_WITH_HF3_SCHEMA_AUDIT_AND_TS_FIX",
        "recommended_next_stage": recommended,
        "stage36a_decision": "STAGE36A_START_NEW_THESIS_BRANCHES_WHILE_STAGE35C_WAITS_RESEARCH_ONLY",
        "db_path": str(DB_PATH),
        "ohlc_table": meta.table,
        "source_timeframe": meta.timeframe_col,
        "source_rows": int(meta.source_rows),
        "selected_rows": int(meta.selected_rows),
        "h1_rows": h1_rows,
        "event_rows": event_rows,
        "variant_rows": int(len(candidate_summary)),
        "strict_review_ready_rows": int(len(strict)),
        "background_rows": int(len(background)),
        "kill_or_repair_rows": int(len(kill)),
        "data_source_meta": meta.__dict__,
        "thresholds": {
            "min_events_review": MIN_EVENTS_REVIEW,
            "min_events_background": MIN_EVENTS_BACKGROUND,
            "min_pf_review": MIN_PF_REVIEW,
            "min_avg_review": MIN_AVG_REVIEW,
            "min_wr_review": MIN_WR_REVIEW,
            "min_tail_pf_review": MIN_TAIL_PF_REVIEW,
            "min_cost1_pf_review": MIN_COST1_PF_REVIEW,
            "max_drawdown_review": MAX_DRAWDOWN_REVIEW,
            "min_recent_pf_review": MIN_RECENT_PF_REVIEW,
            "cost_penalty_x4": COST_PENALTY_X4,
            "tail_n": TAIL_N,
            "recent_n": RECENT_N,
        },
    }
    (OUT_DIR / "stage36b_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    def md_table(df: pd.DataFrame, max_rows: int = 20) -> str:
        if df is None or df.empty:
            return "No rows."
        return df.head(max_rows).to_markdown(index=False)

    lines = [
        "# XAUUSD Stage36B — Session / Regime Baseline Scout",
        f"Generated UTC: {generated}",
        "",
        "## Decision",
        f"DECISION = {decision}",
        f"EXECUTION_STATUS = {EXECUTION_STATUS}",
        f"COMMERCIAL_TRANSITION_AUTHORIZED = {COMMERCIAL_TRANSITION_AUTHORIZED}",
        f"NO_EA_CHANGE = {NO_EA_CHANGE}",
        f"NO_PAPER_LIVE = {NO_PAPER_LIVE}",
        f"NO_ORDER_AUTHORIZATION = {NO_ORDER_AUTHORIZATION}",
        "PRIMARY_OBJECTIVE = SESSION_REGIME_BASELINE_SCOUT_AS_DISTINCT_THESIS_BRANCH_WITH_HF3_SCHEMA_AUDIT_AND_TS_FIX",
        f"RECOMMENDED_NEXT_STAGE = {recommended}",
        "",
        "## Data source audit",
        md_table(audit_df.drop(columns=[c for c in ["sample_row_json"] if c in audit_df.columns], errors="ignore"), 25),
        "",
        "## Summary",
        f"stage36a_decision = STAGE36A_START_NEW_THESIS_BRANCHES_WHILE_STAGE35C_WAITS_RESEARCH_ONLY",
        f"ohlc_table = {meta.table}",
        f"selected_rows = {meta.selected_rows}",
        f"h1_rows = {h1_rows}",
        f"event_rows = {event_rows}",
        f"variant_rows = {len(candidate_summary)}",
        f"strict_review_ready_rows = {len(strict)}",
        f"background_rows = {len(background)}",
        f"kill_or_repair_rows = {len(kill)}",
        "",
        "## Session regime candidate summary",
        md_table(candidate_summary, 20),
        "",
        "## Strict review queue",
        md_table(strict, 20),
        "",
        "## Background queue",
        md_table(background, 20),
        "",
        "## Kill / repair queue",
        md_table(kill, 20),
        "",
        "## Operational interpretation",
        "1. This HF3 version fixes the previous timestamp alias bug by excluding timeframe-like fields from timestamp detection.",
        "2. If OHLC still cannot be found, the data-source audit now includes schema and sample-row details for a direct fix.",
        "3. A positive result here only authorizes stricter research review, not EA, paper-live, or orders.",
        "4. Stage35C remains scheduled in the background for h13/h14 forward confirmation.",
        "",
        "## Output files",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_session_regime_baseline_scout.md`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_summary.json`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_data_source_audit.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_h1_ohlc.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_session_regime_events.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_session_regime_candidate_summary.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_variant_gate_checks.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_strict_review_queue.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_background_queue.csv`",
        "- `data/reports/stage36b_session_regime_baseline_scout/stage36b_kill_or_repair_queue.csv`",
    ]
    (OUT_DIR / "stage36b_session_regime_baseline_scout.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"DECISION={decision}")
    print(f"RECOMMENDED_NEXT_STAGE={recommended}")
    print(f"OHLC_TABLE={meta.table}")
    print(f"SELECTED_ROWS={meta.selected_rows}")
    print(f"H1_ROWS={h1_rows}")
    print(f"EVENT_ROWS={event_rows}")


def main() -> None:
    ensure_out_dir()
    h1, meta, audit = load_best_ohlc_source(DB_PATH)
    events = generate_session_events(h1)
    candidate_summary, gates, strict, background, kill = evaluate_events(events)
    write_outputs(h1, meta, audit, events, candidate_summary, gates, strict, background, kill)


if __name__ == "__main__":
    main()
