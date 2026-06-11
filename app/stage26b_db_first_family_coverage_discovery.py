from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from app.stage25c_deduped_filter_validation import load_bars_from_db as load_bars_from_db_stage25c
except Exception:  # pragma: no cover - reported clearly in run()
    load_bars_from_db_stage25c = None


STAGE = "stage26b_db_first_family_coverage_discovery"
REPORT_DIR = Path("data/reports") / STAGE
DEFAULT_DB_PATH = Path(os.environ.get("STAGE26B_DB_PATH", "data/local/xauusd_local_store.sqlite"))
ROUNDTRIP_COST_X1 = float(os.environ.get("STAGE26B_ROUNDTRIP_COST_X1", "0.35"))
MAX_RUNTIME_SECONDS = int(os.environ.get("STAGE26B_MAX_RUNTIME_SECONDS", "180"))
EXACT_RESERVED_SECONDS = int(os.environ.get("STAGE26B_EXACT_RESERVED_SECONDS", "55"))
MAX_CANDIDATES_TOTAL = int(os.environ.get("STAGE26B_MAX_CANDIDATES_TOTAL", "64"))
MAX_EXACT = int(os.environ.get("STAGE26B_MAX_EXACT", "12"))
MAX_EXACT_PER_FAMILY = int(os.environ.get("STAGE26B_MAX_EXACT_PER_FAMILY", "3"))
MIN_EVENTS = int(os.environ.get("STAGE26B_MIN_EVENTS", "45"))
BOOT_N = int(os.environ.get("STAGE26B_BOOT_N", "120"))
RNG_SEED = int(os.environ.get("STAGE26B_RNG_SEED", "26002"))


class DBFirstLoaderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    family: str
    name: str
    params: Dict[str, Any]


def ensure_report_dir() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_name(name: str) -> str:
    return name.strip().lower().replace("<", "").replace(">", "").replace(" ", "_")


def table_info(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f"PRAGMA table_info('{table}')", conn)


def list_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def find_col(columns: Sequence[str], groups: Sequence[Sequence[str]]) -> Optional[str]:
    norm_map = {normalize_name(c): c for c in columns}
    for group in groups:
        for token in group:
            t = normalize_name(token)
            if t in norm_map:
                return norm_map[t]
    for group in groups:
        for token in group:
            t = normalize_name(token)
            for nc, orig in norm_map.items():
                if t == nc or t in nc:
                    return orig
    return None


def infer_mapping(columns: Sequence[str]) -> Optional[Dict[str, str]]:
    time_col = find_col(columns, [("timestamp", "datetime", "time", "date_time", "broker_time", "bar_time", "dt")])
    open_col = find_col(columns, [("open", "o")])
    high_col = find_col(columns, [("high", "h")])
    low_col = find_col(columns, [("low", "l")])
    close_col = find_col(columns, [("close", "c")])
    tf_col = find_col(columns, [("timeframe", "tf", "frame", "period", "interval")])
    symbol_col = find_col(columns, [("symbol", "ticker", "instrument")])
    if not all([time_col, open_col, high_col, low_col, close_col]):
        return None
    mapping = {
        "timestamp": str(time_col),
        "open": str(open_col),
        "high": str(high_col),
        "low": str(low_col),
        "close": str(close_col),
    }
    if tf_col:
        mapping["timeframe"] = str(tf_col)
    if symbol_col:
        mapping["symbol"] = str(symbol_col)
    return mapping


def tf_matches(series: pd.Series, wanted: str) -> pd.Series:
    s = series.astype(str).str.lower().str.strip()
    if wanted == "M1":
        vals = {"m1", "1m", "1min", "1", "60", "minute", "min1"}
    elif wanted == "H1":
        vals = {"h1", "1h", "60m", "60min", "60", "3600", "hour", "hr1"}
    else:
        vals = {wanted.lower()}
    return s.isin(vals)


def load_table_frame(conn: sqlite3.Connection, table: str, mapping: Dict[str, str], timeframe: str) -> pd.DataFrame:
    cols = [mapping[k] for k in ["timestamp", "open", "high", "low", "close"]]
    extra = []
    for k in ("timeframe", "symbol"):
        if k in mapping:
            extra.append(mapping[k])
    all_cols = list(dict.fromkeys(cols + extra))
    qcols = ", ".join([f'"{c}"' for c in all_cols])
    df = pd.read_sql_query(f'SELECT {qcols} FROM "{table}"', conn)
    if df.empty:
        return df
    if "timeframe" in mapping:
        df = df[tf_matches(df[mapping["timeframe"]], timeframe)].copy()
    # If table has no timeframe column, infer later by median delta.
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df[mapping["timestamp"]], utc=True, errors="coerce"),
            "open": pd.to_numeric(df[mapping["open"]], errors="coerce"),
            "high": pd.to_numeric(df[mapping["high"]], errors="coerce"),
            "low": pd.to_numeric(df[mapping["low"]], errors="coerce"),
            "close": pd.to_numeric(df[mapping["close"]], errors="coerce"),
        }
    )
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"]).drop_duplicates("timestamp")
    out = out.sort_values("timestamp").reset_index(drop=True)
    if out.empty:
        return out
    if "timeframe" not in mapping:
        diffs = out["timestamp"].diff().dropna().dt.total_seconds()
        med = float(diffs.median()) if not diffs.empty else 0.0
        if timeframe == "M1" and not (40 <= med <= 90):
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
        if timeframe == "H1" and not (3000 <= med <= 4200):
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
    return out


def load_bars_from_db(db_path: Path, timeframe: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not db_path.exists():
        raise DBFirstLoaderError(f"SQLite DB not found: {db_path}")
    diagnostics: List[Dict[str, Any]] = []
    with sqlite3.connect(str(db_path)) as conn:
        for table in list_tables(conn):
            info = table_info(conn, table)
            cols = info["name"].astype(str).tolist() if not info.empty else []
            mapping = infer_mapping(cols)
            diag = {"table": table, "columns": ",".join(cols), "mapping_found": bool(mapping)}
            if not mapping:
                diagnostics.append(diag)
                continue
            try:
                df = load_table_frame(conn, table, mapping, timeframe)
            except Exception as exc:  # diagnostic only
                diag["error"] = repr(exc)
                diagnostics.append(diag)
                continue
            diag["rows_for_timeframe"] = len(df)
            diagnostics.append(diag)
            if len(df) > 1000:
                pd.DataFrame(diagnostics).to_csv(REPORT_DIR / "stage26b_db_schema_diagnostic.csv", index=False)
                return df, {"table": table, "mode": "db_schema_introspection", "diagnostics": diagnostics}
    pd.DataFrame(diagnostics).to_csv(REPORT_DIR / "stage26b_db_schema_diagnostic.csv", index=False)
    raise DBFirstLoaderError(f"No {timeframe} OHLC candles found in SQLite DB. CSV fallback is intentionally disabled.")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    x = df.set_index("timestamp").sort_index()
    out = x.resample(rule, label="right", closed="right").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    out = out.dropna().reset_index()
    return out


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(period, min_periods=max(3, period // 2)).mean()
    out["date"] = out["timestamp"].dt.date
    out["hour"] = out["timestamp"].dt.hour
    return out


def session_features(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    x = add_atr(m15, 32)
    h = add_atr(h1, 20)
    h["sma20"] = h["close"].rolling(20, min_periods=10).mean()
    h["sma50"] = h["close"].rolling(50, min_periods=20).mean()
    h["h1_bias"] = np.where(h["sma20"] > h["sma50"], 1, np.where(h["sma20"] < h["sma50"], -1, 0))
    rows: List[Dict[str, Any]] = []
    dates = sorted(x["date"].dropna().unique().tolist())
    h_idx = h.set_index("timestamp")
    for d in dates:
        day = x[x["date"] == d]
        if day.empty:
            continue
        asia = day[(day["hour"] >= 0) & (day["hour"] < 7)]
        london = day[(day["hour"] >= 7) & (day["hour"] < 13)]
        pre_entry13 = day[(day["hour"] >= 0) & (day["hour"] <= 13)]
        if asia.empty or london.empty or pre_entry13.empty:
            continue
        entry_ts_13 = pd.Timestamp(f"{d} 13:00:00", tz="UTC")
        entry_ts_14 = pd.Timestamp(f"{d} 14:00:00", tz="UTC")
        h_until = h_idx[h_idx.index <= entry_ts_13]
        bias = int(h_until["h1_bias"].iloc[-1]) if not h_until.empty else 0
        atr = float(pre_entry13["atr"].dropna().iloc[-1]) if not pre_entry13["atr"].dropna().empty else float((london["high"].max() - london["low"].min()) or 1.0)
        atr = max(atr, 1e-6)
        asia_open = float(asia["open"].iloc[0])
        asia_close = float(asia["close"].iloc[-1])
        asia_hi = float(asia["high"].max())
        asia_lo = float(asia["low"].min())
        london_open = float(london["open"].iloc[0])
        london_close = float(london["close"].iloc[-1])
        london_hi = float(london["high"].max())
        london_lo = float(london["low"].min())
        london_range = london_hi - london_lo
        london_move = london_close - london_open
        london_eff = abs(london_move) / max(london_range, 1e-6)
        london_dir = 1 if london_move > 0 else -1 if london_move < 0 else 0
        entry_close_13 = day[day["timestamp"] <= entry_ts_13]["close"].iloc[-1] if not day[day["timestamp"] <= entry_ts_13].empty else np.nan
        entry_close_14 = day[day["timestamp"] <= entry_ts_14]["close"].iloc[-1] if not day[day["timestamp"] <= entry_ts_14].empty else np.nan
        rows.append(
            {
                "date": d,
                "entry_ts_13": entry_ts_13,
                "entry_ts_14": entry_ts_14,
                "atr": atr,
                "h1_bias": bias,
                "asia_high": asia_hi,
                "asia_low": asia_lo,
                "asia_range_atr": (asia_hi - asia_lo) / atr,
                "asia_dir": 1 if asia_close > asia_open else -1 if asia_close < asia_open else 0,
                "london_high": london_hi,
                "london_low": london_lo,
                "london_mid": (london_hi + london_lo) / 2.0,
                "london_range_atr": london_range / atr,
                "london_move_atr": abs(london_move) / atr,
                "london_dir": london_dir,
                "london_eff": london_eff,
                "entry_close_13": float(entry_close_13) if pd.notna(entry_close_13) else np.nan,
                "entry_close_14": float(entry_close_14) if pd.notna(entry_close_14) else np.nan,
            }
        )
    feats = pd.DataFrame(rows)
    if not feats.empty:
        feats["prior_london_range_q30"] = feats["london_range_atr"].rolling(250, min_periods=60).quantile(0.30).shift(1)
        feats["prior_asia_range_q30"] = feats["asia_range_atr"].rolling(250, min_periods=60).quantile(0.30).shift(1)
    return feats


def generate_candidates() -> List[Candidate]:
    c: List[Candidate] = []
    for lm in [0.75, 1.0]:
        for eff in [0.55, 0.70]:
            for pb in [0.15, 0.30]:
                for h in [90, 180]:
                    c.append(Candidate("htf_bias_pullback_v2", f"htf_pb_lm{lm}_eff{eff}_pb{pb}_h{h}_tp08_sl08", {"lm": lm, "eff": eff, "pb": pb, "horizon": h, "tp": 0.8, "sl": 0.8, "entry_hour": 13}))
    for ar in [0.45, 0.70]:
        for hold in [0.05, 0.15]:
            for h in [90, 180]:
                c.append(Candidate("asia_breakout_pullback_v2", f"asia_br_pb_ar{ar}_hold{hold}_h{h}_tp08_sl08", {"asia_range_min": ar, "hold": hold, "horizon": h, "tp": 0.8, "sl": 0.8, "entry_hour": 13}))
    for lm in [0.75, 1.0]:
        for eff in [0.55, 0.70]:
            for h in [90, 180]:
                c.append(Candidate("session_transition_imbalance_v2", f"sess_imb_lm{lm}_eff{eff}_h{h}_tp08_sl08", {"lm": lm, "eff": eff, "horizon": h, "tp": 0.8, "sl": 0.8, "entry_hour": 13}))
    for q in [0.30]:
        for lm in [0.7, 1.0]:
            for h in [90, 180]:
                c.append(Candidate("squeeze_release_continuation_v2", f"squeeze_release_q{q}_lm{lm}_h{h}_tp08_sl08", {"q": q, "lm": lm, "horizon": h, "tp": 0.8, "sl": 0.8, "entry_hour": 13}))
    return c[:MAX_CANDIDATES_TOTAL]


def events_for_candidate(feats: pd.DataFrame, cand: Candidate) -> pd.DataFrame:
    if feats.empty:
        return pd.DataFrame()
    p = cand.params
    df = feats.copy()
    entry_col = "entry_ts_13" if int(p.get("entry_hour", 13)) == 13 else "entry_ts_14"
    price_col = "entry_close_13" if entry_col == "entry_ts_13" else "entry_close_14"
    direction = np.zeros(len(df), dtype=int)
    if cand.family == "htf_bias_pullback_v2":
        mask = (df["h1_bias"] != 0) & (df["london_dir"] == df["h1_bias"]) & (df["london_move_atr"] >= p["lm"]) & (df["london_eff"] >= p["eff"])
        pull_long = (df["london_high"] - df[price_col]) / df["atr"]
        pull_short = (df[price_col] - df["london_low"]) / df["atr"]
        mask &= np.where(df["h1_bias"] > 0, pull_long <= p["pb"], pull_short <= p["pb"])
        direction = df["h1_bias"].to_numpy(dtype=int)
    elif cand.family == "asia_breakout_pullback_v2":
        long_break = (df[price_col] > df["asia_high"] + p["hold"] * df["atr"]) & (df["asia_range_atr"] >= p["asia_range_min"])
        short_break = (df[price_col] < df["asia_low"] - p["hold"] * df["atr"]) & (df["asia_range_atr"] >= p["asia_range_min"])
        mask = long_break | short_break
        direction = np.where(long_break, 1, np.where(short_break, -1, 0))
    elif cand.family == "session_transition_imbalance_v2":
        mask = (df["london_move_atr"] >= p["lm"]) & (df["london_eff"] >= p["eff"]) & (df["london_dir"] != 0)
        hold = np.where(df["london_dir"] > 0, df[price_col] >= df["london_mid"], df[price_col] <= df["london_mid"])
        mask &= hold
        direction = df["london_dir"].to_numpy(dtype=int)
    elif cand.family == "squeeze_release_continuation_v2":
        qcol = "prior_london_range_q30"
        mask = (df["london_range_atr"] <= df[qcol]) & (df["london_move_atr"] >= p["lm"]) & (df["london_dir"] != 0)
        direction = df["london_dir"].to_numpy(dtype=int)
    else:
        return pd.DataFrame()
    ev = df[mask & np.isfinite(df[price_col])].copy()
    if ev.empty:
        return pd.DataFrame()
    ev["entry_time"] = ev[entry_col]
    ev["entry_price"] = ev[price_col]
    ev["direction"] = direction[ev.index]
    ev["candidate"] = cand.name
    ev["family"] = cand.family
    ev["horizon_min"] = int(p["horizon"])
    ev["tp_atr"] = float(p["tp"])
    ev["sl_atr"] = float(p["sl"])
    keep = ["entry_time", "entry_price", "direction", "atr", "candidate", "family", "horizon_min", "tp_atr", "sl_atr", "date"]
    ev = ev[keep].dropna()
    ev = ev[ev["direction"] != 0]
    return ev.reset_index(drop=True)


def replay_events(m1: pd.DataFrame, events: pd.DataFrame, cost_mult: float = 1.0) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    times = m1["timestamp"].to_numpy(dtype="datetime64[ns]")
    high = m1["high"].to_numpy(dtype=float)
    low = m1["low"].to_numpy(dtype=float)
    close = m1["close"].to_numpy(dtype=float)
    rows: List[Dict[str, Any]] = []
    cost = ROUNDTRIP_COST_X1 * cost_mult
    for _, e in events.iterrows():
        et = np.datetime64(pd.Timestamp(e["entry_time"]).to_datetime64())
        start = int(np.searchsorted(times, et, side="right"))
        end_time = et + np.timedelta64(int(e["horizon_min"]), "m")
        end = int(np.searchsorted(times, end_time, side="right"))
        if start >= len(times) or end <= start:
            continue
        d = int(e["direction"])
        ep = float(e["entry_price"])
        atr = max(float(e["atr"]), 1e-6)
        tp = ep + d * float(e["tp_atr"]) * atr
        sl = ep - d * float(e["sl_atr"]) * atr
        exit_price = float(close[min(end - 1, len(close) - 1)])
        exit_reason = "horizon_close"
        exit_time = pd.Timestamp(times[min(end - 1, len(times) - 1)])
        for j in range(start, min(end, len(times))):
            if d > 0:
                hit_tp = high[j] >= tp
                hit_sl = low[j] <= sl
            else:
                hit_tp = low[j] <= tp
                hit_sl = high[j] >= sl
            if hit_tp and hit_sl:
                exit_price = sl
                exit_reason = "sl_conservative"
                exit_time = pd.Timestamp(times[j])
                break
            if hit_sl:
                exit_price = sl
                exit_reason = "sl"
                exit_time = pd.Timestamp(times[j])
                break
            if hit_tp:
                exit_price = tp
                exit_reason = "tp"
                exit_time = pd.Timestamp(times[j])
                break
        gross = d * (exit_price - ep)
        rows.append({**e.to_dict(), "exit_time": exit_time, "exit_price": exit_price, "exit_reason": exit_reason, "gross": gross, f"net_x{int(cost_mult)}": gross - cost})
    return pd.DataFrame(rows)


def profit_factor(vals: Sequence[float]) -> float:
    arr = np.asarray(vals, dtype=float)
    if arr.size == 0:
        return 0.0
    gains = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def bootstrap_pf_p05(vals: Sequence[float], n: int = BOOT_N) -> float:
    arr = np.asarray(vals, dtype=float)
    if arr.size < 20:
        return 0.0
    rng = np.random.default_rng(RNG_SEED)
    pfs = []
    for _ in range(n):
        sample = rng.choice(arr, size=arr.size, replace=True)
        pfs.append(profit_factor(sample))
    finite = np.asarray([x for x in pfs if np.isfinite(x)], dtype=float)
    if finite.size == 0:
        return float("inf")
    return float(np.quantile(finite, 0.05))


def metrics_from_replay(r: pd.DataFrame, net_col: str) -> Dict[str, Any]:
    vals = r[net_col].astype(float).to_numpy() if net_col in r else np.array([])
    return {
        "events": int(len(vals)),
        "pf": profit_factor(vals),
        "total": float(np.sum(vals)) if vals.size else 0.0,
        "median": float(np.median(vals)) if vals.size else 0.0,
        "win_rate": float(np.mean(vals > 0)) if vals.size else 0.0,
        "boot_pf_p05": bootstrap_pf_p05(vals),
    }


def evaluate_candidate(m1: pd.DataFrame, events: pd.DataFrame) -> Dict[str, Any]:
    if events.empty:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "pf_x6": 0.0, "total_x4": 0.0, "median_x4": 0.0, "win_rate_x4": 0.0, "boot_pf_p05_x4": 0.0}
    # Replay once without cost, then compute x1/x4/x6 from gross to save time.
    r = replay_events(m1, events, 0.0)
    if r.empty:
        return {"events": 0, "pf_x1": 0.0, "pf_x4": 0.0, "pf_x6": 0.0, "total_x4": 0.0, "median_x4": 0.0, "win_rate_x4": 0.0, "boot_pf_p05_x4": 0.0}
    gross = r["gross"].astype(float)
    r["net_x1"] = gross - ROUNDTRIP_COST_X1
    r["net_x4"] = gross - 4 * ROUNDTRIP_COST_X1
    r["net_x6"] = gross - 6 * ROUNDTRIP_COST_X1
    m4 = metrics_from_replay(r, "net_x4")
    return {
        "events": int(len(r)),
        "pf_x1": profit_factor(r["net_x1"]),
        "pf_x4": profit_factor(r["net_x4"]),
        "pf_x6": profit_factor(r["net_x6"]),
        "total_x4": m4["total"],
        "median_x4": m4["median"],
        "win_rate_x4": m4["win_rate"],
        "boot_pf_p05_x4": m4["boot_pf_p05"],
        "trades": r,
    }


def rank_score(m: Dict[str, Any]) -> float:
    events = m.get("events", 0)
    if events < MIN_EVENTS:
        return -1e9
    # Penalize very high frequency generic behavior and weak hard-cost results.
    freq_pen = max(0.0, (events - 350) / 250.0)
    return float(2.5 * min(m.get("pf_x4", 0.0), 5.0) + 1.5 * min(m.get("pf_x6", 0.0), 4.0) + min(m.get("boot_pf_p05_x4", 0.0), 3.0) - freq_pen)


def select_family_balanced(proxy_df: pd.DataFrame) -> pd.DataFrame:
    if proxy_df.empty:
        return proxy_df
    picks = []
    for fam, g in proxy_df.sort_values("rank_score", ascending=False).groupby("family", sort=False):
        gg = g[g["events"] >= MIN_EVENTS].head(MAX_EXACT_PER_FAMILY)
        if not gg.empty:
            picks.append(gg)
    if not picks:
        return proxy_df.head(0)
    out = pd.concat(picks, ignore_index=True).sort_values("rank_score", ascending=False).head(MAX_EXACT)
    return out.reset_index(drop=True)


def fmt(v: Any) -> str:
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def markdown_table(df: pd.DataFrame, cols: List[str], n: int = 20) -> str:
    if df.empty:
        return "No rows."
    show = df[cols].head(n).copy()
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(fmt(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def decision_for(row: pd.Series) -> str:
    if row.get("events", 0) >= 50 and row.get("pf_x4", 0) >= 1.35 and row.get("pf_x6", 0) >= 1.05 and row.get("boot_pf_p05_x4", 0) >= 0.95 and row.get("total_x4", 0) > 0:
        return "STAGE26B_PROMOTION_CANDIDATE_REVIEW_ONLY"
    if row.get("events", 0) >= 45 and row.get("pf_x4", 0) >= 1.05 and row.get("total_x4", 0) > 0:
        return "STAGE26B_KEEP_WATCHLIST_ONLY"
    return "STAGE26B_REJECT"


def run() -> Dict[str, Any]:
    ensure_report_dir()
    t0 = time.time()
    exact_deadline = t0 + max(30, MAX_RUNTIME_SECONDS - EXACT_RESERVED_SECONDS)
    if load_bars_from_db_stage25c is None:
        raise DBFirstLoaderError(
            "Stage26B DB-first loader could not import load_bars_from_db from "
            "app.stage25c_deduped_filter_validation. Apply Stage25C before Stage26B. "
            "CSV fallback is intentionally disabled."
        )
    try:
        m1, h1, db_meta, schema_diag = load_bars_from_db_stage25c(DEFAULT_DB_PATH)
    except Exception as exc:
        raise DBFirstLoaderError(
            f"Stage26B DB-first load failed via Stage25C schema introspection: {exc}. "
            "CSV fallback is intentionally disabled."
        ) from exc
    if isinstance(schema_diag, pd.DataFrame):
        schema_diag.to_csv(REPORT_DIR / "stage26b_db_schema_diagnostic.csv", index=False)
    if m1 is None or m1.empty:
        raise DBFirstLoaderError(
            "No M1 OHLC candles found in SQLite DB via Stage25C schema introspection. "
            "CSV fallback is intentionally disabled."
        )
    if h1 is None or h1.empty:
        h1 = resample_ohlc(m1, "1h")
        h1_mode = "derived_from_m1_resample"
    else:
        h1_mode = str(db_meta.get("h1_mode", "db_schema_introspection"))
    candle_table = str(db_meta.get("candle_table") or db_meta.get("table") or "")
    m1_meta = {"table": candle_table, "mode": str(db_meta.get("m1_mode", "db_schema_introspection")), **dict(db_meta)}
    h1_meta = {"table": candle_table, "mode": h1_mode, **dict(db_meta)}
    m15 = resample_ohlc(m1, "15min")
    feats = session_features(m15, h1)
    candidates = generate_candidates()
    proxy_rows: List[Dict[str, Any]] = []
    event_cache: Dict[str, pd.DataFrame] = {}
    proxy_timed_out = False
    for cand in candidates:
        if time.time() > exact_deadline:
            proxy_timed_out = True
            break
        ev = events_for_candidate(feats, cand)
        event_cache[cand.name] = ev
        m = evaluate_candidate(m1, ev)
        row = {"family": cand.family, "name": cand.name, **{k: v for k, v in m.items() if k != "trades"}}
        row["rank_score"] = rank_score(row)
        row["decision"] = decision_for(pd.Series(row))
        proxy_rows.append(row)
    proxy_df = pd.DataFrame(proxy_rows).sort_values("rank_score", ascending=False) if proxy_rows else pd.DataFrame()
    exact_seed = select_family_balanced(proxy_df)
    exact_rows: List[Dict[str, Any]] = []
    all_trades: List[pd.DataFrame] = []
    exact_timed_out = False
    for _, seed in exact_seed.iterrows():
        if time.time() > t0 + MAX_RUNTIME_SECONDS:
            exact_timed_out = True
            break
        cand_name = str(seed["name"])
        ev = event_cache.get(cand_name, pd.DataFrame())
        m = evaluate_candidate(m1, ev)
        row = {"family": seed["family"], "name": cand_name, **{k: v for k, v in m.items() if k != "trades"}}
        row["decision"] = decision_for(pd.Series(row))
        exact_rows.append(row)
        trades = m.get("trades")
        if isinstance(trades, pd.DataFrame) and not trades.empty:
            trades = trades.copy()
            trades["candidate"] = cand_name
            trades["family"] = seed["family"]
            all_trades.append(trades)
    exact_df = pd.DataFrame(exact_rows).sort_values("rank_score" if "rank_score" in exact_rows else "pf_x4", ascending=False) if exact_rows else pd.DataFrame()
    if not exact_df.empty:
        exact_df = exact_df.sort_values(["decision", "pf_x4", "pf_x6"], ascending=[True, False, False])
    family_cov = []
    for fam in sorted({c.family for c in candidates}):
        pg = proxy_df[proxy_df["family"] == fam] if not proxy_df.empty else pd.DataFrame()
        eg = exact_df[exact_df["family"] == fam] if not exact_df.empty else pd.DataFrame()
        family_cov.append({"family": fam, "proxy_tested": int(len(pg)), "proxy_passing_min_events": int((pg["events"] >= MIN_EVENTS).sum()) if not pg.empty else 0, "exact_replayed": int(len(eg)), "best_proxy_pf_x4": float(pg["pf_x4"].max()) if not pg.empty else 0.0, "best_exact_pf_x4": float(eg["pf_x4"].max()) if not eg.empty else 0.0})
    family_df = pd.DataFrame(family_cov)
    promotion_count = int((exact_df["decision"] == "STAGE26B_PROMOTION_CANDIDATE_REVIEW_ONLY").sum()) if not exact_df.empty else 0
    watch_count = int((exact_df["decision"] == "STAGE26B_KEEP_WATCHLIST_ONLY").sum()) if not exact_df.empty else 0
    decision = "STAGE26B_HAS_PROMOTION_REVIEW_CANDIDATE_RESEARCH_ONLY" if promotion_count else "STAGE26B_HAS_WATCHLIST_ONLY" if watch_count else "STAGE26B_NO_PROMOTION_KEEP_DISCOVERY_OPEN"
    proxy_df.to_csv(REPORT_DIR / "stage26b_proxy_candidates.csv", index=False)
    exact_df.to_csv(REPORT_DIR / "stage26b_exact_candidates.csv", index=False)
    family_df.to_csv(REPORT_DIR / "stage26b_family_coverage.csv", index=False)
    if all_trades:
        pd.concat(all_trades, ignore_index=True).to_csv(REPORT_DIR / "stage26b_exact_trades.csv", index=False)
    else:
        pd.DataFrame().to_csv(REPORT_DIR / "stage26b_exact_trades.csv", index=False)
    result = {
        "decision": decision,
        "db_path": str(DEFAULT_DB_PATH),
        "m1_rows": len(m1),
        "m1_span": [str(m1["timestamp"].min()), str(m1["timestamp"].max())],
        "h1_rows": len(h1),
        "h1_span": [str(h1["timestamp"].min()), str(h1["timestamp"].max())],
        "m15_rows": len(m15),
        "m15_span": [str(m15["timestamp"].min()), str(m15["timestamp"].max())],
        "m1_table": m1_meta.get("table"),
        "h1_table": h1_meta.get("table"),
        "h1_mode": h1_meta.get("mode"),
        "proxy_candidates_tested": len(proxy_df),
        "proxy_candidates_passing_min_events": int((proxy_df["events"] >= MIN_EVENTS).sum()) if not proxy_df.empty else 0,
        "exact_replayed": len(exact_df),
        "promotion_review_candidates": promotion_count,
        "watchlist_only_candidates": watch_count,
        "proxy_timed_out": proxy_timed_out,
        "exact_timed_out": exact_timed_out,
        "runtime_seconds": round(time.time() - t0, 2),
    }
    with open(REPORT_DIR / f"{STAGE}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    render_markdown(result, proxy_df, exact_df, family_df)
    return result


def render_markdown(result: Dict[str, Any], proxy_df: pd.DataFrame, exact_df: pd.DataFrame, family_df: pd.DataFrame) -> None:
    lines = [
        "# Stage26B DB-First Family-Coverage Discovery",
        "",
        "## Decision",
        "",
        "```text",
        str(result["decision"]),
        "```",
        "",
        "## Scope guardrails",
        "",
        "- Research/shadow discovery only.",
        "- Stage18A v2 remains the active operational forward-shadow runner.",
        "- Stage23D and Stage25D remain separate DB-first trackers.",
        "- No EA change, no automatic trading, no paper/live/order authorization.",
        "- Candles are DB-first from SQLite; AMarkets CSV fallback is disabled.",
        "",
        "## DB source of truth",
        f"- db_path: `{result['db_path']}`",
        f"- candle_table: `{result.get('m1_table')}`",
        "- db_first: `True`",
        "- csv_fallback_enabled: `False`",
        f"- m1_rows: `{result['m1_rows']}` | span: `{result['m1_span'][0]} → {result['m1_span'][1]}`",
        f"- h1_rows: `{result['h1_rows']}` | span: `{result['h1_span'][0]} → {result['h1_span'][1]}`",
        f"- h1_mode: `{result.get('h1_mode')}`",
        f"- m15_rows: `{result['m15_rows']}` | span: `{result['m15_span'][0]} → {result['m15_span'][1]}`",
        "",
        "## Discovery families",
        "",
        "1. `htf_bias_pullback_v2` — H1 bias, London impulse, controlled pullback continuation.",
        "2. `asia_breakout_pullback_v2` — Asia range breakout with hold/pullback continuation.",
        "3. `session_transition_imbalance_v2` — London imbalance carried into NY transition.",
        "4. `squeeze_release_continuation_v2` — low prior London range regime followed by release.",
        "",
        "## Counts",
        f"- proxy_candidates_tested: `{result['proxy_candidates_tested']}`",
        f"- proxy_candidates_passing_min_events: `{result['proxy_candidates_passing_min_events']}`",
        f"- exact_replayed: `{result['exact_replayed']}`",
        f"- promotion_review_candidates: `{result['promotion_review_candidates']}`",
        f"- watchlist_only_candidates: `{result['watchlist_only_candidates']}`",
        f"- proxy_timed_out: `{result['proxy_timed_out']}`",
        f"- exact_timed_out: `{result['exact_timed_out']}`",
        f"- runtime_seconds: `{result['runtime_seconds']}`",
        "",
        "## Family coverage diagnostics",
        markdown_table(family_df, ["family", "proxy_tested", "proxy_passing_min_events", "exact_replayed", "best_proxy_pf_x4", "best_exact_pf_x4"], 20),
        "",
        "## Top exact M1 results",
        markdown_table(exact_df, ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "total_x4", "win_rate_x4"], 20),
        "",
        "## Top M15 proxy results",
        markdown_table(proxy_df, ["decision", "family", "name", "events", "pf_x1", "pf_x4", "pf_x6", "boot_pf_p05_x4", "median_x4", "rank_score"], 20),
        "",
        "## Interpretation",
        "",
        "- Stage26B is a DB-first continuation of structured discovery with explicit family coverage diagnostics.",
        "- Exact replay is selected per family first, then globally capped, to avoid the Stage26A failure mode where one family consumed all exact slots.",
        "- A promotion-review result here remains research-only and requires separate validation and forward-shadow tracking.",
        "",
        "## Operational reminder",
        "",
        "```bash",
        "cd ~/Desktop/xauusd-trader",
        "python3 -m app.stage18a_unified_shadow_ops_cycle",
        "python3 -m app.stage23d_forward_shadow_candidate",
        "python3 -m app.stage25d_db_first_filtered_forward_shadow",
        "```",
        "",
        "## Output files",
        f"- `data/reports/{STAGE}/{STAGE}.json`",
        f"- `data/reports/{STAGE}/{STAGE}.md`",
        f"- `data/reports/{STAGE}/stage26b_proxy_candidates.csv`",
        f"- `data/reports/{STAGE}/stage26b_exact_candidates.csv`",
        f"- `data/reports/{STAGE}/stage26b_exact_trades.csv`",
        f"- `data/reports/{STAGE}/stage26b_family_coverage.csv`",
        f"- `data/reports/{STAGE}/stage26b_db_schema_diagnostic.csv`",
    ]
    (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_report_dir()
    try:
        run()
    except Exception as exc:
        ensure_report_dir()
        decision = "STAGE26B_ERROR_DIAGNOSTIC_ONLY"
        md = [
            "# Stage26B DB-First Family-Coverage Discovery",
            "",
            "## Decision",
            "",
            "```text",
            decision,
            "```",
            "",
            "## Error",
            "",
            "```text",
            f"{type(exc).__name__}: {exc}",
            "```",
            "",
            "- DB-first is enabled.",
            "- CSV fallback is intentionally disabled.",
            "- Stage18A, Stage23D, and Stage25D remain unchanged.",
        ]
        (REPORT_DIR / f"{STAGE}.md").write_text("\n".join(md), encoding="utf-8")
        with open(REPORT_DIR / f"{STAGE}.json", "w", encoding="utf-8") as f:
            json.dump({"decision": decision, "error": f"{type(exc).__name__}: {exc}"}, f, indent=2)
        raise


if __name__ == "__main__":
    main()
